"""Test micro-fix Goal v5 monitoring + Balance export v11."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_goal_intensity_v5_preview import (
    SNAPSHOT_COMPLETED,
    SNAPSHOT_ERROR,
    SNAPSHOT_INCOMPLETE,
    SNAPSHOT_LOCKED,
    SNAPSHOT_PENDING,
)
from app.services.cecchino.cecchino_balance_v5_readiness import (
    build_balance_empirical_reconciliation,
    build_balance_readiness_decision,
)
from app.services.cecchino.cecchino_goal_intensity_v5 import (
    attach_results_for_rows,
    build_calibration,
    build_candidates,
    build_dimensions,
)
from app.services.cecchino.cecchino_goal_intensity_v5_dimension_registry import (
    GOAL_INTENSITY_V5_DIMENSION_REGISTRY,
    build_dimensions_from_snapshots,
    compute_metric_stats,
    extract_metric_values_from_snapshots,
)
from app.services.cecchino.cecchino_goal_intensity_v5_monitoring_adapter import (
    normalize_goal_v5_monitoring_contract,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    SCHEMA_CONTRACTS,
    _build_balance_readiness_export_placeholders,
)


def _snap(
    status: str,
    *,
    attached: bool = False,
    scan_date: date | None = date(2026, 1, 10),
    pillar: dict | None = None,
):
    s = MagicMock()
    s.snapshot_status = status
    s.result_attached_at = (
        datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc) if attached else None
    )
    s.scan_date = scan_date
    s.competition_id = 1
    s.pillar_scores_payload = pillar or {
        "OP1_HOME_LONG_TERM": 1.2,
        "OP2_HOME_RECENCY": 0.8,
        "DV1_MEAN_CONCEDED": 1.1,
        "DV2_WEAKEST_DEFENCE": 0.9,
        "defensive_solidity_display": 0.7,
        "MT1_LONG_TERM": 2.0,
        "MT2_LONG_TERM_PLUS_RECENCY": 1.5,
        "OV1_STD": 0.5,
        "offensive_stability_display": 0.6,
    }
    s.no_target_used_in_score = True
    return s


def test_export_version_is_v11():
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v11"


def test_balance_schema_includes_reconciliation_file():
    required = SCHEMA_CONTRACTS["balance-v5"]["required_files"]
    assert "balance_empirical_reconciliation.json" in required


def test_registry_extracts_all_source_keys():
    snaps = [_snap(SNAPSHOT_COMPLETED, attached=True)]
    for spec in GOAL_INTENSITY_V5_DIMENSION_REGISTRY.values():
        for source_key in (spec.get("metrics") or {}).values():
            vals, missing, invalid = extract_metric_values_from_snapshots(snaps, str(source_key))
            assert len(vals) == 1
            assert missing == 0
            assert invalid == 0


def test_registry_partial_and_invalid_values():
    snaps = [
        _snap(
            SNAPSHOT_COMPLETED,
            attached=True,
            pillar={"OP1_HOME_LONG_TERM": float("nan"), "OP2_HOME_RECENCY": True},
        )
    ]
    row = compute_metric_stats(
        metric_key="long_term",
        source_key="OP1_HOME_LONG_TERM",
        snapshots=snaps,
    )
    assert row["n"] == 0
    assert row["invalid"] == 1
    dims = build_dimensions_from_snapshots(snaps)
    assert dims["offensive_production"]["data_quality_status"] in {"partial", "missing"}


def test_adapter_counts_from_snapshots():
    snaps = [
        _snap(SNAPSHOT_COMPLETED, attached=True),
        _snap(SNAPSHOT_PENDING),
        _snap(SNAPSHOT_LOCKED),
        _snap(SNAPSHOT_INCOMPLETE),
        _snap(SNAPSHOT_ERROR),
    ]
    out = normalize_goal_v5_monitoring_contract(
        monitoring={
            "completed_prospective_matches": 1,
            "prospective_protocol": {"prospective_matches_collected": 5},
        },
        snapshots=snaps,
    )
    assert out["completed_n"] == 1
    assert out["pending_n"] == 1
    assert out["locked_snapshots"] == 1
    assert out["incomplete_snapshots"] == 1
    assert out["error_snapshots"] == 1
    assert out["total_snapshots"] == 5
    assert isinstance(out["completed_n"], int)
    assert isinstance(out["pending_n"], int)


def test_adapter_zero_snapshots_uses_protocol():
    out = normalize_goal_v5_monitoring_contract(
        monitoring={
            "completed_prospective_matches": 0,
            "prospective_protocol": {"prospective_matches_collected": 14},
        },
        snapshots=[],
    )
    assert out["completed_n"] == 0
    assert out["pending_n"] == 14
    assert out["total_snapshots"] == 14


def test_adapter_period_filter_respects_date_to():
    snaps = [
        _snap(SNAPSHOT_COMPLETED, attached=True, scan_date=date(2026, 1, 5)),
        _snap(SNAPSHOT_PENDING, scan_date=date(2026, 1, 20)),
    ]
    out = normalize_goal_v5_monitoring_contract(
        monitoring={"completed_prospective_matches": 1},
        snapshots=snaps,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 10),
    )
    period = out["coverage_in_period"]
    assert period["snapshots"] == 1
    assert period["last_snapshot"] == "2026-01-05"


def test_build_candidates_completed_pending_always_int():
    db = MagicMock()
    bundle = MagicMock()
    bundle.id = 1
    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.get_active_bundle",
            return_value=bundle,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.build_prospective_monitoring",
            return_value={
                "status": "ok",
                "metrics_by_candidate": {},
                "completed_prospective_matches": 3,
                "prospective_protocol": {"prospective_matches_collected": 10},
            },
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5._bundle_summary",
            return_value={"collected": 10, "completed": 3, "pending": 7},
        ),
    ):
        db.scalars.return_value.all.return_value = []
        out = build_candidates(db)
    assert out["completed_n"] == 3
    assert out["pending_n"] == 7
    assert out["total_snapshots"] == 10
    assert isinstance(out["completed_n"], int)
    assert isinstance(out["pending_n"], int)


@pytest.mark.parametrize(
    ("completed", "expected_status"),
    [
        (0, "empty"),
        (4, "insufficient_sample"),
        (5, "ok"),
        (199, "ok"),
    ],
)
def test_build_calibration_sample_gates(completed, expected_status):
    db = MagicMock()
    bundle = MagicMock()
    bundle.id = 1
    snaps = [_snap(SNAPSHOT_COMPLETED, attached=True) for _ in range(completed)]
    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.get_active_bundle",
            return_value=bundle,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.build_prospective_monitoring",
            return_value={"metrics_by_candidate": {"GI_A_STRICT_CORE": {"n": completed}}},
        ),
    ):
        db.scalars.return_value.all.return_value = snaps
        out = build_calibration(db)
    assert out["status"] == expected_status
    assert out["completed_n"] == completed


def test_build_dimensions_with_registry_payload():
    db = MagicMock()
    bundle = MagicMock()
    bundle.id = 1
    snaps = [_snap(SNAPSHOT_COMPLETED, attached=True)]
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.get_active_bundle",
        return_value=bundle,
    ):
        db.scalars.return_value.all.return_value = snaps
        out = build_dimensions(db)
    assert out["status"] == "ok"
    assert "offensive_production" in out["dimensions"]
    assert out["dimensions_list"]
    assert out["dimensions"]["offensive_production"]["metrics"][0]["n"] == 1


def test_attach_results_skipped_reason_codes():
    db = MagicMock()
    row = MagicMock()
    row.id = 99
    row.goals_home = None
    row.goals_away = None
    bundle = MagicMock()
    bundle.id = 1
    snap = MagicMock()
    snap.result_attached_at = None
    snap.snapshot_status = SNAPSHOT_PENDING
    snap.local_fixture_id = 1
    snap.kickoff = datetime(2099, 1, 1, tzinfo=timezone.utc)
    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.get_active_bundle",
            return_value=bundle,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_preview._load_fixture",
            return_value=None,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.clear_goal_intensity_v5_readiness_cache",
        ) as clear_cache,
    ):
        db.scalars.return_value.first.return_value = snap
        out = attach_results_for_rows(db, [row], commit=False)
    assert out["attached"] == 0
    assert out["skipped_by_reason"]
    clear_cache.assert_not_called()


def test_balance_maturity_collecting_with_pending_only():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_technical_gates",
        return_value={"gates": [{"status": "pass", "promotion_blocking": True}]},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_scientific_gates",
        return_value={"gates": [{"status": "wait", "promotion_blocking": True}], "prospective_settled": 0},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_prospective_progress",
        return_value={
            "prospective_pending": 14,
            "ratios": {"prospective_settled": {"numerator": 0, "denominator": 1500}},
            "earliest_theoretical_review_at": None,
        },
    ):
        decision = build_balance_readiness_decision(
            db, filters={"date_from": date(2026, 1, 1), "date_to": date(2026, 7, 1)}
        )
    assert decision["scientific_maturity"] == "prospective_collecting"
    assert decision["scientific_maturity_label_it"] == "Raccolta prospettica in corso"


def test_balance_readiness_export_placeholders_cover_required_files():
    files = _build_balance_readiness_export_placeholders(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 7, 1),
        competition_id=None,
        error="TestError",
    )
    for name in (
        "balance_readiness_overview.json",
        "balance_readiness_policy.json",
        "balance_readiness_gates.csv",
        "balance_pillar_readiness.json",
        "balance_prospective_progress.json",
        "balance_readiness_history.csv",
        "balance_current_decision.json",
        "balance_decision_contract.json",
        "balance_prospective_collection_health.json",
        "balance_governance_decisions.csv",
        "metadata.json",
    ):
        assert name in files
        assert len(files[name]) > 0


def test_balance_reconciliation_explained_historical_diagnostic_only():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_balance_v5_monitoring.build_balance_monitoring_rows",
        return_value=[{"today_fixture_id": 1, "source_cohort": "prospective"}],
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_empirical.query_balance_empirical_rows",
        side_effect=[
            {
                "items": [
                    {"today_fixture_id": 1, "source_cohort": "prospective"},
                    {"today_fixture_id": 2, "source_cohort": "historical_diagnostic"},
                    {"today_fixture_id": 3, "source_cohort": "historical_diagnostic"},
                ],
                "total": 3,
            }
        ],
    ):
        out = build_balance_empirical_reconciliation(
            db,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 7, 1),
        )
    assert out["only_empirical_count"] == 2
    assert out["reconciliation_status"] == "explained"
    assert "historical_diagnostic" in out["explanation"]
