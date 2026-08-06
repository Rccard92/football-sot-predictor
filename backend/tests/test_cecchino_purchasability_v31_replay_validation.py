"""Test Step 2B — validazione replay Acquistabilità V3.1 (sintetici)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.cecchino_purchasability_v3 import PURCHASABILITY_V3_FORMULA_VERSION
from app.schemas.cecchino_purchasability_v31 import PURCHASABILITY_V31_FORMULA_VERSION
from app.services.cecchino_data_lab.historical_purchasability_operational import (
    PROMOTE_CONFIRM_TOKEN,
    ROLLBACK_CONFIRM_TOKEN,
    get_operational_purchasability_config,
    promote_purchasability_v31,
    rollback_purchasability_to_v3,
)
from app.services.cecchino_data_lab.historical_purchasability_replay_formula_registry import (
    V31_MARKET_ORDER,
    V3_MARKET_ORDER,
    get_replay_formula_config,
    invoke_formula,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_analytics import (
    compute_decomposition,
    compute_matched_v3_v31_comparison,
    compute_positive_signal_health,
    compute_ordering_diagnostics,
    reconstruct_historical_factor,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_go_no_go import (
    DECISION_GO_FINAL,
    DECISION_GO_PROVISIONAL,
    DECISION_NO_GO_DATA,
    DECISION_NO_GO_OVER_SEVERE,
    DECISION_NO_GO_PERFORMANCE,
    DECISION_NO_GO_TECHNICAL,
    evaluate_purchasability_v31_go_no_go,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_replay_hr import (
    WalkForwardHREvent,
    resolve_hr_as_of,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError


def test_registry_v3_unchanged_markets_and_versions():
    cfg = get_replay_formula_config("v3")
    assert cfg.formula_version == PURCHASABILITY_V3_FORMULA_VERSION
    assert len(cfg.market_order) == 8
    assert cfg.market_order == V3_MARKET_ORDER
    assert cfg.requires_historical_reliability is False


def test_registry_v31_19_markets_and_hr_required():
    cfg = get_replay_formula_config("v31")
    assert cfg.formula_version == PURCHASABILITY_V31_FORMULA_VERSION
    assert len(cfg.market_order) == 19
    assert cfg.market_order == V31_MARKET_ORDER
    assert cfg.requires_historical_reliability is True


def test_invoke_v3_batch_no_hr():
    cfg = get_replay_formula_config("v3")
    batch = invoke_formula(
        cfg,
        kpi_panel={
            "rows": [
                {
                    "market_key": "HOME",
                    "edge_pct": 10.0,
                    "vantaggio_prob": 0.05,
                    "prob_cecchino": 0.55,
                    "quota_book": 2.0,
                    "quota_cecchino": 1.8,
                    "quote_source": "historical_bet365",
                    "derived_quote": False,
                    "not_real_book_quote": False,
                }
            ]
        },
        fixture_meta={"today_fixture_id": 1},
    )
    assert "items" in batch


def test_hr_walk_forward_excludes_same_kickoff_and_future():
    ko = datetime(2021, 9, 1, 15, 0, tzinfo=timezone.utc)
    same = datetime(2021, 9, 1, 15, 0, tzinfo=timezone.utc)
    future = datetime(2021, 9, 2, 15, 0, tzinfo=timezone.utc)
    past = datetime(2021, 8, 1, 15, 0, tzinfo=timezone.utc)
    prior = []
    for i in range(40):
        prior.append(
            WalkForwardHREvent(
                market_key="HOME",
                competition_id="c1",
                competition_name="C1",
                kickoff=past,
                rating=70,
                odds=2.0,
                settlement_status="won" if i % 2 == 0 else "lost",
                unit_stake_profit=1.0 if i % 2 == 0 else -1.0,
                snapshot_id=i,
                market_result_id=i,
            )
        )
    # same kickoff + future must be ignored even if present in list
    prior.append(
        WalkForwardHREvent(
            market_key="HOME",
            competition_id="c1",
            competition_name="C1",
            kickoff=same,
            rating=70,
            odds=2.0,
            settlement_status="won",
            unit_stake_profit=1.0,
            snapshot_id=999,
            market_result_id=999,
        )
    )
    prior.append(
        WalkForwardHREvent(
            market_key="HOME",
            competition_id="c1",
            competition_name="C1",
            kickoff=future,
            rating=70,
            odds=2.0,
            settlement_status="won",
            unit_stake_profit=1.0,
            snapshot_id=1000,
            market_result_id=1000,
        )
    )
    hr = resolve_hr_as_of(
        panel_rows=[{"market_key": "HOME", "rating": 70}],
        competition_id="c1",
        kickoff=ko,
        prior_events=prior,
        same_kickoff_group_size=3,
    )
    item = hr["HOME"]
    assert item["same_kickoff_results_excluded"] is True
    assert item["future_events_excluded"] is True
    assert item["prior_events_count"] == 40
    assert item["status"] == "ok"


def test_positive_signal_health_collapse_and_tail():
    low = [
        {
            "score": 10,
            "calculation_status": "score",
            "quote_quality": "real",
            "is_real_book_quote": True,
            "is_derived_quote": False,
            "market_key": "HOME",
            "competition_name": "A",
            "kickoff_at": f"2021-08-{i:02d}T15:00:00+00:00",
        }
        for i in range(1, 35)
    ]
    psh = compute_positive_signal_health(low)
    assert psh["all_negative_collapse"] is True
    assert psh["positive_tail_detected"] is False

    high = list(low)
    for i in range(30):
        high.append(
            {
                "score": 75,
                "calculation_status": "score",
                "quote_quality": "real",
                "is_real_book_quote": True,
                "is_derived_quote": False,
                "market_key": "AWAY",
                "competition_name": "B",
                "kickoff_at": f"2021-09-{(i % 28) + 1:02d}T15:00:00+00:00",
            }
        )
    high.append(
        {
            "score": 88,
            "calculation_status": "score",
            "quote_quality": "real",
            "is_real_book_quote": True,
            "is_derived_quote": False,
            "market_key": "DRAW",
            "competition_name": "B",
            "kickoff_at": "2021-10-01T15:00:00+00:00",
        }
    )
    psh2 = compute_positive_signal_health(high)
    assert psh2["positive_tail_detected"] is True
    assert psh2["all_negative_collapse"] is False
    assert psh2["very_high_count"] >= 1


def test_go_no_go_technical_leakage():
    d = evaluate_purchasability_v31_go_no_go({}, context={"leakage_detected": True})
    assert d["decision"] == DECISION_NO_GO_TECHNICAL
    assert d["promotion_allowed"] is False


def test_go_no_go_over_severe():
    d = evaluate_purchasability_v31_go_no_go(
        {
            "positive_signal_health": {
                "scored_real_count": 100,
                "high_count": 0,
                "very_high_count": 0,
                "max_score": 35,
                "all_negative_collapse": True,
                "positive_tail_detected": False,
                "positive_tail_sample_sufficient": False,
            },
            "coverage": {"score_production_rate": 0.8},
        },
        context={"reconciliation_ok": True, "unclassified_count": 0},
    )
    assert d["decision"] == DECISION_NO_GO_OVER_SEVERE


def test_go_no_go_provisional_without_holdout():
    analytics = {
        "positive_signal_health": {
            "scored_real_count": 100,
            "high_count": 40,
            "very_high_count": 5,
            "max_score": 88,
            "all_negative_collapse": False,
            "positive_tail_detected": True,
            "positive_tail_sample_sufficient": True,
        },
        "coverage": {"score_production_rate": 0.5},
        "performance_real": {
            "score_ge_60": {"roi": 0.12, "realized_margin": 0.04, "selections": 40}
        },
        "ordering": {
            "high_vs_all_uplift": 0.05,
            "high_plus_very_high_vs_low_roi_delta": 0.1,
            "severe_monotonicity_violations": 0,
        },
        "v3_comparison": {
            "roi_delta": 0.02,
            "equal_coverage_roi_delta": 0.01,
            "drawdown_delta": 0.0,
        },
        "top_percentiles": {"top_10pct": {"roi": 0.2}},
        "baseline_scored_real": {"roi": 0.05},
    }
    d = evaluate_purchasability_v31_go_no_go(
        analytics,
        context={
            "has_independent_holdout": False,
            "reconciliation_ok": True,
            "unclassified_count": 0,
            "holdout_high_count": 40,
            "baseline_roi": 0.05,
            "high_vs_all_uplift": 0.05,
        },
    )
    assert d["decision"] == DECISION_GO_PROVISIONAL
    assert d["promotion_allowed"] is False


def test_go_no_go_final_requires_holdout_and_criteria(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PURCHASABILITY_OPERATIONAL_STATE_PATH",
        str(tmp_path / "op.json"),
    )
    analytics = {
        "positive_signal_health": {
            "scored_real_count": 200,
            "high_count": 50,
            "very_high_count": 35,
            "max_score": 92,
            "all_negative_collapse": False,
            "positive_tail_detected": True,
            "positive_tail_sample_sufficient": True,
        },
        "coverage": {"score_production_rate": 0.6},
        "performance_real": {
            "score_ge_60": {"roi": 0.15, "realized_margin": 0.06, "selections": 50},
            "score_ge_80": {"roi": 0.2, "realized_margin": 0.08, "selections": 35},
        },
        "ordering": {
            "high_vs_all_uplift": 0.08,
            "high_plus_very_high_vs_low_roi_delta": 0.12,
            "severe_monotonicity_violations": 0,
        },
        "v3_comparison": {
            "roi_delta": 0.03,
            "equal_coverage_roi_delta": 0.02,
            "drawdown_delta": 0.0,
        },
        "top_percentiles": {"top_10pct": {"roi": 0.25}},
        "baseline_scored_real": {"roi": 0.04},
    }
    d = evaluate_purchasability_v31_go_no_go(
        analytics,
        context={
            "has_independent_holdout": True,
            "reconciliation_ok": True,
            "unclassified_count": 0,
            "holdout_high_count": 50,
            "baseline_roi": 0.04,
            "high_vs_all_uplift": 0.08,
            "temporal_robustness_ok": True,
        },
    )
    assert d["decision"] == DECISION_GO_FINAL
    out = promote_purchasability_v31(
        replay_id=99,
        decision=DECISION_GO_FINAL,
        formula_version=PURCHASABILITY_V31_FORMULA_VERSION,
        confirm_token=PROMOTE_CONFIRM_TOKEN,
        validation_meta={"source_run_id": 3, "decision_version": d["decision_version"]},
    )
    assert out["operational_version"] == "v31"
    assert out["strong_buy_message_allowed"] is True
    # no promote without GO_FINAL
    with pytest.raises(CecchinoLabImportError):
        promote_purchasability_v31(
            replay_id=100,
            decision=DECISION_GO_PROVISIONAL,
            formula_version=PURCHASABILITY_V31_FORMULA_VERSION,
            confirm_token=PROMOTE_CONFIRM_TOKEN,
        )
    rb = rollback_purchasability_to_v3(confirm_token=ROLLBACK_CONFIRM_TOKEN)
    assert rb["operational_version"] == "v3"


def test_no_go_performance_negative_roi():
    d = evaluate_purchasability_v31_go_no_go(
        {
            "positive_signal_health": {
                "scored_real_count": 100,
                "high_count": 40,
                "very_high_count": 5,
                "max_score": 85,
                "all_negative_collapse": False,
                "positive_tail_detected": True,
                "positive_tail_sample_sufficient": True,
            },
            "coverage": {"score_production_rate": 0.5},
            "performance_real": {
                "score_ge_60": {"roi": -0.2, "realized_margin": -0.1, "selections": 40}
            },
            "ordering": {
                "high_vs_all_uplift": -0.1,
                "high_plus_very_high_vs_low_roi_delta": -0.15,
                "severe_monotonicity_violations": 2,
            },
            "v3_comparison": {
                "roi_delta": -0.1,
                "equal_coverage_roi_delta": -0.1,
                "drawdown_delta": -0.2,
            },
            "top_percentiles": {"top_10pct": {"roi": -0.05}},
            "baseline_scored_real": {"roi": 0.0},
        },
        context={
            "reconciliation_ok": True,
            "unclassified_count": 0,
            "baseline_roi": 0.0,
            "high_vs_all_uplift": -0.1,
        },
    )
    assert d["decision"] == DECISION_NO_GO_PERFORMANCE


def test_historical_factor_reconstruct():
    hf, reason = reconstruct_historical_factor(
        {"raw_score": 40, "value_score": 80, "quality_score": 100}
    )
    assert hf == pytest.approx(0.5)
    assert reason is None


def test_matched_comparison_and_decomposition():
    v31 = [
        {
            "source_snapshot_id": 1,
            "market_key": "HOME",
            "score": 70,
            "quote_quality": "real",
            "is_real_book_quote": True,
            "is_derived_quote": False,
            "won": True,
            "profit_1u_real": 1.0,
            "quota_book": 2.0,
            "value_score": 90,
            "quality_score": 90,
            "raw_score": 60,
            "probability_risk_penalty": 5,
            "opposite_market_pressure_penalty": 5,
            "extreme_divergence_penalty": 0,
            "family_ambiguity_penalty": 0,
            "kickoff_at": "2021-08-01T15:00:00+00:00",
        }
    ]
    v3 = [
        {
            "source_snapshot_id": 1,
            "market_key": "HOME",
            "score": 65,
            "quote_quality": "real",
            "is_real_book_quote": True,
            "is_derived_quote": False,
            "won": True,
            "profit_1u_real": 1.0,
            "quota_book": 2.0,
            "kickoff_at": "2021-08-01T15:00:00+00:00",
        }
    ]
    cmp_ = compute_matched_v3_v31_comparison(v31, v3)
    assert cmp_["sample_matched"] == 1
    dec = compute_decomposition(v31)
    assert "mean_losses" in dec


def test_default_operational_remains_v3(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PURCHASABILITY_OPERATIONAL_STATE_PATH",
        str(tmp_path / "op2.json"),
    )
    cfg = get_operational_purchasability_config()
    assert cfg["operational_version"] == "v3"
    assert cfg["v31_is_operational"] is False
    assert cfg["strong_buy_message_allowed"] is False
