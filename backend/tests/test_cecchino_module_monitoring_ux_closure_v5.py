"""Test UX closure v5 — data quality, TECH/SCI, card semantics."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_purchasability_evaluation import (
    EVAL_LOST,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    COHORT_HISTORICAL_DIAGNOSTIC,
    resolve_balance_v5_monitoring_snapshot,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    SCHEMA_CONTRACTS,
    _build_export_audit,
    build_goal_intensity_module_overview,
    build_purchasability_module_overview,
    build_signals_module_overview,
)
from app.services.cecchino.cecchino_purchasability_validation import (
    _purchasability_data_quality_fields,
    _serialize_validation_row_forensic,
)
from app.services.cecchino.cecchino_purchasability_validation_aggregation import (
    _invalid_book_odds_rows,
    _performance_eligible_rows,
    build_purchasability_validation_summary,
)


def _eval(**kwargs):
    defaults = dict(
        id=1,
        evaluation_status=EVAL_WON,
        quota_book=Decimal("2.10"),
        snapshot_timestamp_verified=True,
        snapshot_before_kickoff=True,
        promotion_eligible=False,
        purchasability_score=50,
        today_fixture_id=1,
        source_cohort="historical_diagnostic",
        profit_units=Decimal("0.5"),
        market_key="1X2_1",
        phase_1_score=Decimal("1.0"),
        phase_2_score=Decimal("1.0"),
        scan_date=date(2026, 6, 1),
        fair_book_probability=Decimal("0.48"),
        competition_id=1,
        purchasability_class="medium",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_invalid_book_odds_data_quality_fields():
    row = _eval(quota_book=Decimal("0.97"))
    dq = _purchasability_data_quality_fields(row)
    assert dq["analysis_eligible"] is False
    assert dq["data_quality_status"] == "invalid"
    assert dq["analysis_exclusion_reason"] == "invalid_decimal_book_odds"


def test_invalid_book_odds_excluded_from_performance_but_counted():
    rows = [
        _eval(quota_book=Decimal("0.97"), evaluation_status=EVAL_WON),
        _eval(quota_book=Decimal("1.00"), evaluation_status=EVAL_LOST),
        _eval(quota_book=Decimal("2.10"), evaluation_status=EVAL_WON),
        _eval(quota_book=Decimal("0.97"), evaluation_status=EVAL_PENDING),
    ]
    assert len(_invalid_book_odds_rows(rows)) == 3
    assert len(_performance_eligible_rows(rows)) == 1


def test_serialize_forensic_includes_data_quality():
    row = _eval(quota_book=Decimal("0.97"), id=99, scan_date=date(2026, 6, 1))
    dq = _purchasability_data_quality_fields(row)
    assert dq["analysis_eligible"] is False
    assert dq["data_quality_status"] == "invalid"
    assert dq["analysis_exclusion_reason"] == "invalid_decimal_book_odds"


def test_reconciliation_block_in_summary():
    rows = [
        _eval(evaluation_status=EVAL_WON),
        _eval(evaluation_status=EVAL_LOST),
        _eval(evaluation_status=EVAL_PENDING, quota_book=Decimal("2.0")),
        _eval(evaluation_status=EVAL_RESULT_MISSING, quota_book=Decimal("2.0")),
        _eval(evaluation_status=EVAL_WON, quota_book=Decimal("0.97")),
    ]
    db = MagicMock()

    with patch(
        "app.services.cecchino.cecchino_purchasability_validation_aggregation.query_validation_rows",
        return_value=rows,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_validation_aggregation._cluster_bootstrap_spearman",
        return_value={"point": None, "ci_low": None, "ci_high": None},
    ), patch(
        "app.services.cecchino.cecchino_purchasability_validation_aggregation._top_bottom_residual_spread",
        return_value={},
    ):
        summary = build_purchasability_validation_summary(
            db,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 12, 31),
            promotion_eligible_only=False,
            bootstrap_iterations=10,
        )

    rec = summary["reconciliation"]
    assert rec["raw_rows"] == 5
    assert rec["invalid_book_odds"] == 1
    assert rec["performance_eligible_rows"] == 2
    assert rec["pending"] == 1
    assert rec["result_missing"] == 1
    assert rec["excluded_from_performance_count"] == 1


def test_purchasability_overview_separates_historical_and_prospective():
    db = MagicMock()
    health = {
        "fixtures_with_persisted_preview": 0,
        "historical_fixtures": 964,
        "result_settled_count": 8074,
        "evaluated_rows": 8074,
        "historical_rows_available": 8890,
        "prospective_rows_available": 0,
        "result_pending_count": 814,
        "result_missing_count": 2,
        "data_quality_excluded_rows": 4,
        "invalid_book_odds_count": 4,
        "validation_rows_total": 8890,
        "snapshot_persistence_coverage": None,
        "fixtures_with_kpi_panel": 964,
        "persistence_blocking_reason": "only_legacy_derived_available",
    }
    summary = {
        "metrics": {"settled": 8070},
        "reconciliation": {
            "raw_rows": 8890,
            "performance_eligible_rows": 8070,
            "invalid_book_odds": 4,
        },
    }
    readiness = {"status": "collecting_data", "warnings": [], "prima_data_teorica_promozione": None}

    with patch(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_purchasability_validation_health",
        return_value=health,
    ), patch(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_purchasability_validation_summary",
        return_value=summary,
    ), patch(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_purchasability_promotion_readiness",
        return_value=readiness,
    ):
        overview = build_purchasability_module_overview(
            db, date_from=date(2026, 6, 1), date_to=date(2026, 7, 20)
        )

    assert overview["prospective_fixtures"] == 0
    assert overview["historical_fixtures"] == 964
    assert overview["evaluated_rows"] == 8074
    assert overview["data_quality_excluded_rows"] == 4
    assert overview["reconciliation"]["raw_rows"] == 8890


def test_balance_derived_unverified_timestamp_source_mode():
    fx = SimpleNamespace(
        cecchino_output_json={},
        scan_date=date(2026, 6, 1),
        kickoff=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc),
        odds_snapshot_json={},
        kpi_panel_json={},
        score_fulltime_home=None,
        score_fulltime_away=None,
    )
    derived_payload = {
        "status": "ok",
        "version": "balance_v5",
        "pillars": {
            "f36": {"index": 1},
            "dominance": {"index": 1},
            "draw_credibility": {"index": 1},
            "gap_coherence": {"index": 1},
        },
        "inputs": {"prob_1_norm": 0.4, "prob_x_norm": 0.3, "prob_2_norm": 0.3},
    }
    with patch(
        "app.services.cecchino.cecchino_balance_v5_monitoring.build_balance_v5_from_stored_row",
        return_value=derived_payload,
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_monitoring._odds_meta_verified_pre_kickoff",
        return_value=False,
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_monitoring._extract_odds_snapshot_at",
        return_value=None,
    ):
        resolved = resolve_balance_v5_monitoring_snapshot(fx)

    assert resolved["source_cohort"] == COHORT_HISTORICAL_DIAGNOSTIC
    assert resolved["mode"] == "derived_read_only_from_stored_inputs_unverified_timestamp"
    assert resolved["payload"]["source_mode"] == (
        "derived_read_only_from_stored_inputs_unverified_timestamp"
    )
    assert resolved["payload"].get("snapshot_timestamp") is None


def test_goal_overview_global_vs_filtered_snapshots():
    db = MagicMock()
    bundle = SimpleNamespace(id=1, version="goal_v5_test")
    all_snaps = [
        SimpleNamespace(scan_date=date(2026, 5, 1), result_attached_at=None),
        SimpleNamespace(scan_date=date(2026, 6, 20), result_attached_at=None),
        SimpleNamespace(scan_date=date(2026, 7, 10), result_attached_at=None),
    ]

    with patch(
        "app.services.cecchino.cecchino_module_monitoring_exports._eligible_fixture_counts",
        return_value=(100, 80),
    ), patch(
        "app.services.cecchino.cecchino_module_monitoring_exports._active_goal_bundle",
        return_value=bundle,
    ), patch(
        "app.services.cecchino.cecchino_module_monitoring_exports.select"
    ), patch(
        "app.models.cecchino_goal_intensity_v5_preview.CecchinoGoalIntensityV5PreviewSnapshot"
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.MINIMUM_PROSPECTIVE_MATCHES",
        200,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.build_prospective_monitoring",
        return_value={"status": "collecting"},
    ):
        db.scalars.return_value.all.side_effect = [all_snaps]
        overview = build_goal_intensity_module_overview(
            db, date_from=date(2026, 6, 19), date_to=date(2026, 7, 20)
        )

    assert overview["global_snapshots"] == 3
    assert overview["snapshots_in_period"] == 2
    assert overview["completed_snapshots"] == 0
    assert overview["snapshot_collection_progress"] == pytest.approx(3 / 200)
    assert overview["completed_results_progress"] == 0.0


def test_signals_overview_explicit_units():
    db = MagicMock()
    summary = {
        "overall": {
            "eligible_fixtures_count": 500,
            "fixtures_with_signals_count": 120,
            "activations": 300,
            "won": 50,
            "lost": 40,
        },
        "warnings": [],
    }
    items = [
        {
            "today_fixture_id": 1,
            "is_current": True,
            "model_key": "DEFAULT",
            "evaluation_status": "won",
            "source_cohort": "historical_persisted_verified",
        },
        {
            "today_fixture_id": 2,
            "is_current": True,
            "model_key": "DEFAULT",
            "evaluation_status": "pending",
            "source_cohort": "unusable",
        },
        {
            "today_fixture_id": 3,
            "is_current": False,
            "model_key": "OLD",
            "evaluation_status": "won",
            "source_cohort": "historical_persisted_verified",
        },
    ]

    with patch(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_signals_summary",
        return_value=summary,
    ), patch(
        "app.services.cecchino.cecchino_module_monitoring_exports.list_signal_activations",
        return_value={"items": items},
    ), patch(
        "app.services.cecchino.cecchino_module_monitoring_exports.CECCHINO_DEFAULT_WEIGHT_MODEL_KEY",
        "DEFAULT",
    ):
        overview = build_signals_module_overview(
            db, date_from=date(2026, 1, 1), date_to=date(2026, 12, 31)
        )

    assert overview["fixtures_with_current_signals"] == 2
    assert overview["current_activations"] == 2
    assert overview["current_activations_evaluated"] == 1
    assert overview["historical_activations_total"] == 3
    assert overview["post_kickoff_excluded_count"] == 1


def test_technical_pass_despite_scientific_warnings():
    schema = SCHEMA_CONTRACTS["purchasability"]
    files = {
        name: b"x" for name in schema["required_files"] if name.endswith(".json")
    }
    header = ",".join(schema["required_columns"]).encode("utf-8")
    row_line = b",".join([b"1"] * len(schema["required_columns"]))
    files["rows.csv"] = b"\xef\xbb\xbf" + header + b"\n" + row_line + b"\n"
    files["distributions_by_score_band.csv"] = b"\xef\xbb\xbfscore_band,rows\n"
    files["distributions_by_market.csv"] = b"\xef\xbb\xbfmarket_key,rows\n"
    files["distributions_by_cohort.csv"] = b"\xef\xbb\xbfsource_cohort,rows\n"

    audit = _build_export_audit(
        files,
        {
            "source_total_rows": 1,
            "warnings": ["Persistenza bloccata: only_legacy_derived_available"],
            "completeness": "partial",
            "settled_count": 8074,
            "blocking_reasons": ["only_legacy_derived_available"],
        },
        "purchasability",
        schema["required_files"],
        schema,
    )
    assert audit["technical_status"] == "pass"
    assert audit["scientific_status"] in {"partial", "partial_collecting"}


def test_purchasability_schema_no_distributions_csv_in_required():
    required = SCHEMA_CONTRACTS["purchasability"]["required_files"]
    assert "distributions.csv" not in required
    assert "distributions_by_score_band.csv" in required
    aliases = SCHEMA_CONTRACTS["purchasability"]["optional_aliases"]
    assert aliases["distributions.csv"] == "distributions_by_score_band.csv"


def test_signals_optional_aliases_not_unexpected():
    schema = SCHEMA_CONTRACTS["signals"]
    header = ",".join(schema["required_columns"]).encode("utf-8")
    row_line = b",".join([b"1"] * len(schema["required_columns"]))
    row_csv = b"\xef\xbb\xbf" + header + b"\n" + row_line + b"\n"
    files = {name: row_csv for name in schema["required_files"] if name.endswith(".csv")}
    files["field_availability.json"] = b"{}"
    files["overall.json"] = b"{}"
    files["version_definition.json"] = b"{}"
    files["activations_all_rows.csv"] = files["activations_all_models.csv"]
    files["activations_current_rows.csv"] = files["activations_current_model.csv"]
    audit = _build_export_audit(
        files,
        {"source_total_rows": 1, "completeness": "complete", "settled_count": 1},
        "signals",
        schema["required_files"],
        schema,
    )
    assert "activations_all_rows.csv" not in audit["unexpected_files"]
    assert audit["technical_status"] == "pass"


def test_module_overview_grid_does_not_use_progress_ring():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    grid = (root / "frontend/src/components/module-monitoring/ModuleOverviewGrid.tsx").read_text(
        encoding="utf-8"
    )
    assert "MonitoringProgressRing" not in grid
