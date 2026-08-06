"""Test Phase 2B: UI contract maturity + benchmark prospettico V4–V5."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.cecchino.cecchino_goal_intensity_analysis import (
    VERSION as V4_VERSION,
    build_cecchino_goal_intensity_analysis_from_expected_goals,
)
from app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark import (
    GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
    V4_MODEL_ID,
    _binary_metrics,
    _continuous_metrics,
    _evidence_level,
    _scientific_interpretation,
    build_goal_intensity_v4_v5_prospective_benchmark,
    build_phase_2b_benchmark_summary,
    clear_goal_intensity_v4_v5_benchmark_cache,
    extract_v4_from_persisted_today,
    extract_v5_calibrated,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    BENCHMARK_ID,
    CHALLENGER_ID,
    DIAGNOSTIC_ID,
    PRIMARY_ID,
    VERSION as V5_BUNDLE_VERSION,
)
from app.services.cecchino.cecchino_goal_intensity_v5_readiness import (
    clear_goal_intensity_v5_readiness_cache,
)
from app.services.cecchino.cecchino_module_monitoring_exports import SCHEMA_CONTRACTS


def test_schema_contract_includes_benchmark_files():
    required = SCHEMA_CONTRACTS["goal-intensity-v5"]["required_files"]
    for name in (
        "benchmark_v4_v5_summary.json",
        "benchmark_v4_v5_models.csv",
        "benchmark_v4_v5_pairwise.csv",
        "benchmark_v4_v5_calibration_ge2.csv",
        "benchmark_v4_v5_calibration_ge3.csv",
        "benchmark_v4_v5_missing_reasons.csv",
    ):
        assert name in required


def test_v4_pure_builder_over_probs_and_no_btts():
    payload = build_cecchino_goal_intensity_analysis_from_expected_goals(2.4)
    assert payload["version"] == V4_VERSION
    assert payload["expected_goals_total"] == 2.4
    assert payload["thresholds"]["over_1_5"]["probability"] is not None
    assert payload["thresholds"]["over_2_5"]["probability"] is not None
    assert "probability_btts" not in payload


def test_extract_v4_from_goal_markets_lambda():
    today = MagicMock()
    today.cecchino_output_json = {
        "goal_markets": {
            "OVER_1_5": {"summary": {"lambda": 2.55}},
        }
    }
    payload, reason = extract_v4_from_persisted_today(today)
    assert reason is None
    assert payload is not None
    assert payload["expected_goals_total"] == 2.55


def test_extract_v4_missing_lambda_excludes():
    today = MagicMock()
    today.cecchino_output_json = {"goal_markets": {}}
    payload, reason = extract_v4_from_persisted_today(today)
    assert payload is None
    assert reason == "missing_persisted_v4_expected_goals"


def test_extract_v4_never_calls_db_builder():
    today = MagicMock()
    today.cecchino_output_json = {
        "goal_markets": {"OVER_2_5": {"summary": {"lambda": 1.8}}}
    }
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_analysis.build_cecchino_goal_intensity_analysis"
    ) as db_builder:
        payload, reason = extract_v4_from_persisted_today(today)
        assert reason is None
        assert payload is not None
        db_builder.assert_not_called()


def test_extract_v5_uses_calibrated_not_raw():
    snap = MagicMock()
    snap.calibrated_predictions_payload = {
        PRIMARY_ID: {
            "raw_score": 72.0,
            "expected_total_goals": 2.1,
            "probability_goals_ge_2": 0.61,
            "probability_goals_ge_3": 0.42,
            "probability_btts": 0.5,
        }
    }
    pred = extract_v5_calibrated(snap, PRIMARY_ID)
    assert pred is not None
    assert pred["expected_total_goals"] == 2.1
    assert pred["expected_total_goals"] != 72.0


def test_continuous_and_binary_metrics_deterministic():
    preds = [1.0, 2.0, 3.0, 4.0]
    actuals = [1.0, 2.0, 2.0, 5.0]
    m = _continuous_metrics(preds, actuals)
    assert m["n"] == 4
    assert m["mae"] == pytest.approx(0.5)
    assert m["rmse"] is not None
    assert m["mean_error"] == pytest.approx(0.0)

    probs = [0.1, 0.9, 0.8, 0.2]
    ys = [0, 1, 1, 0]
    b = _binary_metrics(probs, ys)
    assert b["n"] == 4
    assert b["brier"] is not None
    assert b["log_loss"] is not None
    assert b["auc"] is not None
    assert isinstance(b["calibration_bins"], list)


def test_binary_single_class_auc_none():
    b = _binary_metrics([0.2, 0.3, 0.4], [0, 0, 0])
    assert b["auc"] is None
    assert b["brier"] is not None


def test_evidence_ci_includes_zero_is_low():
    level = _evidence_level(
        n=20,
        ci={"ci_lower": -0.1, "ci_upper": 0.2, "mean": 0.05},
        delta=0.05,
    )
    assert level == "low"


def test_evidence_supported_when_ci_away_from_zero():
    level = _evidence_level(
        n=50,
        ci={"ci_lower": -0.4, "ci_upper": -0.1, "mean": -0.25},
        delta=-0.25,
    )
    assert level in {"supported", "directional"}


def test_scientific_interpretation_no_clear_difference():
    out = _scientific_interpretation(
        paired_n=50,
        primary_vs_v4_mae={
            "evidence_level": "low",
            "preferred_side": "none",
        },
    )
    assert out["status"] == "no_clear_difference"
    assert out["promotes_signals"] is False


def test_scientific_interpretation_insufficient():
    out = _scientific_interpretation(paired_n=2, primary_vs_v4_mae=None)
    assert out["status"] == "paired_coverage_insufficient"


def _make_snap(
    *,
    snap_id: int,
    today_id: int,
    status: str = "completed",
    total_goals: float = 2.0,
    freeze_delta_hours: float = 24,
    pre_kickoff: bool = True,
    eg: float = 2.2,
):
    freeze = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    snap = MagicMock()
    snap.id = snap_id
    snap.today_fixture_id = today_id
    snap.local_fixture_id = 1000 + snap_id
    snap.competition_id = 39
    snap.scan_date = date(2026, 7, 1)
    snap.snapshot_status = status
    snap.total_goals_ft = total_goals
    snap.goals_home_ft = 1
    snap.goals_away_ft = max(0, int(total_goals) - 1)
    snap.goals_ge_2 = total_goals >= 2
    snap.goals_ge_3 = total_goals >= 3
    snap.btts_ft = True
    snap.result_attached_at = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    snap.no_target_used_in_score = True
    snap.source_snapshot_at = freeze + timedelta(hours=freeze_delta_hours)
    if pre_kickoff:
        snap.kickoff = snap.source_snapshot_at + timedelta(hours=3)
    else:
        snap.kickoff = snap.source_snapshot_at - timedelta(hours=1)
    cal = {}
    for cid in (PRIMARY_ID, CHALLENGER_ID, BENCHMARK_ID, DIAGNOSTIC_ID):
        cal[cid] = {
            "raw_score": 50.0,
            "expected_total_goals": eg + (0.05 if cid == CHALLENGER_ID else 0.0),
            "probability_goals_ge_2": 0.6,
            "probability_goals_ge_3": 0.35,
            "probability_btts": 0.48,
        }
    snap.calibrated_predictions_payload = cal
    return snap


def _make_today(today_id: int, lam: float | None = 2.4):
    row = MagicMock()
    row.id = today_id
    if lam is None:
        row.cecchino_output_json = {"goal_markets": {}}
    else:
        row.cecchino_output_json = {
            "goal_markets": {"OVER_1_5": {"summary": {"lambda": lam}}},
        }
    return row


def test_benchmark_paired_cohort_and_exclusions():
    clear_goal_intensity_v4_v5_benchmark_cache()
    bundle = MagicMock()
    bundle.id = 1
    bundle.version = V5_BUNDLE_VERSION
    bundle.candidate_definition_hash = "abc123"
    bundle.frozen_at = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    bundle.candidate_definitions_payload = {
        "prospective_guard": {
            "retrospective_today_fixture_ids": [999],
            "retrospective_local_fixture_ids": [],
        }
    }

    good = [
        _make_snap(snap_id=i, today_id=i, total_goals=float(i % 4), eg=2.0 + i * 0.01)
        for i in range(1, 8)
    ]
    pending = _make_snap(snap_id=50, today_id=50)
    pending.snapshot_status = "pending"
    pending.result_attached_at = None
    pending.total_goals_ft = None
    incomplete = _make_snap(snap_id=51, today_id=51)
    incomplete.snapshot_status = "incomplete"
    error = _make_snap(snap_id=52, today_id=52)
    error.snapshot_status = "error"
    pre_freeze = _make_snap(snap_id=53, today_id=53, freeze_delta_hours=-5)
    post_ko = _make_snap(snap_id=54, today_id=54, pre_kickoff=False)
    retro = _make_snap(snap_id=55, today_id=999)
    missing_v4 = _make_snap(snap_id=56, today_id=56)
    missing_cand = _make_snap(snap_id=57, today_id=57)
    missing_cand.calibrated_predictions_payload = {
        PRIMARY_ID: missing_cand.calibrated_predictions_payload[PRIMARY_ID]
    }

    all_snaps = good + [
        pending,
        incomplete,
        error,
        pre_freeze,
        post_ko,
        retro,
        missing_v4,
        missing_cand,
    ]
    todays = {i: _make_today(i) for i in range(1, 8)}
    todays[56] = _make_today(56, lam=None)
    todays[57] = _make_today(57)
    todays[999] = _make_today(999)
    todays[53] = _make_today(53)
    todays[54] = _make_today(54)
    todays[51] = _make_today(51)
    todays[52] = _make_today(52)

    db = MagicMock()
    call_count = {"n": 0}

    def scalars3(stmt):
        result = MagicMock()
        call_count["n"] += 1
        if call_count["n"] == 1:
            result.all.return_value = all_snaps
        else:
            result.all.return_value = list(todays.values())
        return result

    db.scalars.side_effect = scalars3

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark.get_active_bundle",
            return_value=bundle,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark._prospective_guard",
            return_value=bundle.candidate_definitions_payload["prospective_guard"],
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_analysis.build_goal_market_contexts"
        ) as contexts,
        patch(
            "app.services.cecchino.cecchino_goal_intensity_analysis.weighted_lambda"
        ) as wl,
    ):
        out = build_goal_intensity_v4_v5_prospective_benchmark(db)
        contexts.assert_not_called()
        wl.assert_not_called()

    assert out["status"] == "ok"
    assert out["version"] == GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION
    assert out["v4_version"] == V4_VERSION
    assert out["quality_checks"]["external_api_calls"] == 0
    assert out["quality_checks"]["historical_run_used"] is False
    assert out["quality_checks"]["v4_db_fallback_used"] is False
    assert out["btts"]["v4_status"] == "not_comparable"
    cohort = out["cohort"]
    assert cohort["paired_complete_n"] == 7
    assert cohort["v4_available"] >= 7
    assert "missing_persisted_v4_expected_goals" in cohort["missing_by_reason"]
    metrics = out["continuous_total_goals"]["metrics_by_model"]
    assert PRIMARY_ID in metrics
    assert V4_MODEL_ID in metrics
    assert metrics[PRIMARY_ID]["n"] == metrics[V4_MODEL_ID]["n"] == 7
    assert out["scientific_interpretation"]["promotes_signals"] is False


def test_overview_maturity_ready_for_manual_review():
    from app.services.cecchino.cecchino_goal_intensity_v5 import build_overview

    bundle = MagicMock()
    bundle.version = V5_BUNDLE_VERSION
    monitoring = {
        "phase_2b_readiness": {
            "blocking_issues": [],
            "recommended_next_step": "phase_2b_replacement_review",
        }
    }
    snaps = [
        MagicMock(
            snapshot_status="completed",
            result_attached_at=datetime.now(timezone.utc),
            scan_date=date(2026, 7, 1),
        )
        for _ in range(5)
    ]
    normalized = {
        "completed_snapshots": 250,
        "pending_snapshots": 10,
        "total_snapshots": 260,
        "incomplete_snapshots": 0,
        "error_snapshots": 0,
        "coverage_global": {"snapshots": 260, "completed": 250, "pending": 10},
        "coverage_in_period": {"snapshots": 200, "completed": 180, "pending": 20},
    }
    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5._goal_monitoring_context",
            return_value=(bundle, monitoring, snaps, normalized),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5._bundle_summary",
            return_value={"primary_candidate": PRIMARY_ID},
        ),
    ):
        out = build_overview(db=MagicMock())
    assert out["scientific_maturity"] == "ready_for_manual_review"
    assert out["scientific_maturity_label_it"] == "Pronto per revisione manuale"
    assert out["signals_integration_status"] == "blocked"
    assert out["current_decision"] == "continue_monitoring"
    assert out["recommended_next_step"] == "phase_2b_replacement_review"
    assert out["coverage_global"]["completed"] == 250
    assert out["coverage_in_period"]["pending"] == 20


def test_readiness_progress_fields_and_excess():
    clear_goal_intensity_v5_readiness_cache()
    from app.services.cecchino.cecchino_goal_intensity_v5_readiness import (
        build_goal_intensity_v5_readiness,
    )

    completed_n = 250
    bundle = MagicMock()
    bundle.id = 1
    bundle.candidate_definition_hash = "hash"
    snaps = []
    for _ in range(completed_n):
        s = MagicMock()
        s.snapshot_status = "completed"
        s.result_attached_at = datetime.now(timezone.utc)
        s.no_target_used_in_score = True
        snaps.append(s)
    for _ in range(20):
        s = MagicMock()
        s.snapshot_status = "pending"
        s.result_attached_at = None
        s.no_target_used_in_score = True
        snaps.append(s)

    normalized = {
        "completed_snapshots": completed_n,
        "pending_snapshots": 20,
        "locked_snapshots": 0,
        "incomplete_snapshots": 0,
        "error_snapshots": 0,
        "total_snapshots": completed_n + 20,
        "coverage_global": {"first_snapshot": "2026-06-20"},
        "coverage_in_period": {},
    }

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.get_active_bundle",
            return_value=bundle,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_prospective_monitoring",
            return_value={
                "phase_2b_readiness": {
                    "blocking_issues": [],
                    "recommended_next_step": "phase_2b_replacement_review",
                }
            },
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.normalize_goal_v5_monitoring_contract",
            return_value=normalized,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_data_health",
            return_value={"issues": []},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_overview",
            return_value={"scientific_maturity": "ready_for_manual_review"},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_calibration",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_candidates",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark.build_goal_intensity_v4_v5_prospective_benchmark",
            return_value={
                "status": "ok",
                "version": GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
                "cohort": {
                    "paired_complete_n": 200,
                    "paired_coverage_pct": 80.0,
                    "v4_available": 200,
                },
                "continuous_total_goals": {"comparisons": []},
                "scientific_interpretation": {"status": "no_clear_difference"},
            },
        ),
    ):
        db = MagicMock()
        db.scalars.return_value.all.return_value = snaps
        report = build_goal_intensity_v5_readiness(db)

    prog = report["prospective_progress"]
    assert prog["completed"] == completed_n
    assert prog["pending"] == 20
    assert prog["snapshots"] == completed_n + 20
    assert prog["minimum"] == 200
    assert prog["progress_pct"] > 100
    assert prog["remaining"] == 0
    assert prog["excess"] == completed_n - 200
    assert report["scientific_maturity"] == "ready_for_manual_review"
    assert report["signals_integration_status"] == "blocked"
    assert report["recommended_next_step"] == "phase_2b_replacement_review"
    assert report["phase_2b_benchmark"]["status"] == "available"


def test_phase_2b_summary_builder():
    summary = build_phase_2b_benchmark_summary(
        {
            "status": "ok",
            "version": GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
            "cohort": {
                "paired_complete_n": 10,
                "paired_coverage_pct": 50.0,
                "v4_available": 12,
            },
            "continuous_total_goals": {
                "comparisons": [
                    {
                        "left_id": PRIMARY_ID,
                        "right_id": V4_MODEL_ID,
                        "metric": "mae",
                        "delta": -0.1,
                    }
                ]
            },
            "scientific_interpretation": {"status": "no_clear_difference"},
        }
    )
    assert summary["paired_complete_n"] == 10
    assert summary["primary_vs_v4"]["delta"] == -0.1
    assert summary["recommended_next_step"] == "phase_2b_replacement_review"


def test_bootstrap_seed_deterministic():
    from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import (
        bootstrap_index_matrix,
        bootstrap_paired_delta_ci,
    )

    deltas = [0.1, -0.2, 0.05, -0.01, 0.3, -0.15, 0.0, 0.2]
    idx1 = bootstrap_index_matrix(len(deltas), 100, 42)
    idx2 = bootstrap_index_matrix(len(deltas), 100, 42)
    assert np.array_equal(idx1, idx2)
    ci1 = bootstrap_paired_delta_ci(deltas, iterations=100, seed=42, indices=idx1)
    ci2 = bootstrap_paired_delta_ci(deltas, iterations=100, seed=42, indices=idx2)
    assert ci1 == ci2
