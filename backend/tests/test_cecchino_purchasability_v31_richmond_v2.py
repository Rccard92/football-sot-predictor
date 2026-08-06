"""Regressione Richmond (fixture 1493931 / today 15825) — V3.1 empirical_v2."""

from __future__ import annotations

from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_AUDIT_VERSION,
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION_V1,
)
from app.services.cecchino.cecchino_historical_reliability import (
    MIN_SAMPLE,
    calculate_historical_reliability,
)
from app.services.cecchino.cecchino_purchasability_candidate import (
    round_purchasability_score_half_up,
)
from app.services.cecchino.cecchino_purchasability_v31_candidate import (
    calculate_purchasability_v31_item,
    evaluate_v31_gate,
)
from app.services.cecchino.cecchino_purchasability_v31_historical_policy import (
    historical_multiplier_from_score,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME
from app.services.cecchino_data_lab.historical_purchasability_replay_formula_registry import (
    get_replay_formula_config,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_go_no_go import (
    GO_NO_GO_VERSION_V2,
    evaluate_purchasability_v31_go_no_go_v2,
)

# Caso reale Richmond — nessun risultato post-match nel payload formula
RICHMOND = {
    "provider_fixture_id": 1493931,
    "today_fixture_id": 15825,
    "competition_id": 57,
    "market": SEL_HOME,
    "quota_book": 2.55,
    "quota_cecchino": 1.91,
    "edge_pct": 33.51,
    "probability_advantage_pp": 13.14,
    "rating": 86,
    "probability_cecchino_pct": 56.059957173447536,
    "fair_book_probability": 0.354983922829582,
    "complement_fair_probability": 0.645016077170418,
    "execution_quote_source": "betfair_raw_match_winner",
}


def _richmond_row() -> dict:
    r = RICHMOND
    return {
        "market_key": SEL_HOME,
        "segno": SEL_HOME,
        "rating": r["rating"],
        "edge_pct": r["edge_pct"],
        "vantaggio_prob": r["probability_advantage_pp"] / 100.0,
        "prob_cecchino": r["probability_cecchino_pct"] / 100.0,
        "quota_book": r["quota_book"],
        "quota_cecchino": r["quota_cecchino"],
        "book_source": r["execution_quote_source"],
    }


def _richmond_fair() -> dict:
    p = RICHMOND["fair_book_probability"]
    c = RICHMOND["complement_fair_probability"]
    # Approssima DRAW/AWAY per set completo (solo HOME è sotto test)
    draw = 0.30
    away = max(0.01, 1.0 - p - draw)
    return {
        SEL_HOME: {
            "fair_book_probability": p,
            "fair_book_probability_verified": True,
            "fair_book_probability_source": "betfair_normalized",
            "normalization_payload": {
                "normalized_map": {SEL_HOME: p, SEL_DRAW: draw, SEL_AWAY: away},
            },
        },
        SEL_DRAW: {
            "fair_book_probability": draw,
            "fair_book_probability_verified": True,
            "fair_book_probability_source": "betfair_normalized",
        },
        SEL_AWAY: {
            "fair_book_probability": away,
            "fair_book_probability_verified": True,
            "fair_book_probability_source": "betfair_normalized",
        },
    }


def _calc(hr: dict | None):
    by = {
        SEL_HOME: _richmond_row(),
        SEL_DRAW: {
            "market_key": SEL_DRAW,
            "edge_pct": 2.0,
            "vantaggio_prob": 0.01,
            "rating": 60,
            "prob_cecchino": 0.30,
            "quota_book": 3.2,
            "quota_cecchino": 3.0,
            "book_source": "betfair_raw_match_winner",
        },
        SEL_AWAY: {
            "market_key": SEL_AWAY,
            "edge_pct": 1.0,
            "vantaggio_prob": 0.01,
            "rating": 55,
            "prob_cecchino": 0.25,
            "quota_book": 3.5,
            "quota_cecchino": 3.3,
            "book_source": "betfair_raw_match_winner",
        },
    }
    fair = _richmond_fair()
    model = {k: r.get("prob_cecchino") for k, r in by.items()}
    return calculate_purchasability_v31_item(
        SEL_HOME,
        by[SEL_HOME],
        by,
        fair_by=fair,
        model_probs=model,
        historical_reliability_item=hr,
        gate_by_market={k: evaluate_v31_gate(r) for k, r in by.items()},
        edge_by_market={k: r.get("edge_pct") for k, r in by.items()},
        policy="v2",
    )


def test_richmond_gate_passed():
    g = evaluate_v31_gate(_richmond_row())
    assert g["gate_status"] == "passed"
    assert g["gate_reason_codes"] == []


def test_richmond_theoretical_raw():
    it = _calc(None)
    theor = it["theoretical"]
    assert abs(theor["value_score"] - 67.02) < 0.05
    assert abs(theor["opposite_market_pressure_penalty"] - 20.3023) < 0.05
    assert abs(theor["theoretical_quality_score"] - 79.6977) < 0.1
    assert abs(theor["theoretical_raw_score"] - 53.4134) < 0.15


def test_richmond_no_history_provisional_score_53():
    it = _calc(None)
    assert it["status"] == "score_provisional"
    assert it["calculation_quality"] == "provisional"
    assert it["historical"]["historical_reliability_score"] == 50
    assert abs(it["historical"]["historical_multiplier"] - 1.0) < 1e-9
    assert it["score"] == 53
    assert "non_calculable" != it["status"]
    assert "historical_sample_insufficient" not in it["reason_codes"]
    assert it["gate_reason_codes"] == []


def test_richmond_small_neutral_sample_16():
    hr = {
        "status": "provisional_insufficient_sample",
        "score": 50,
        "selected_sample_size": 16,
        "sample_size": 16,
        "sample_confidence": 0.16,
        "raw_evidence_score": 50.0,
        "wins": 8,
        "losses": 8,
        "voids": 0,
        "roi": 0.0,
        "realized_margin": 0.0,
        "stability_ratio": None,
        "stability_status": "insufficient_periods",
        "stability_component": 50,
        "cohort_scope": "all_competitions_fallback",
        "fallback_used": True,
    }
    it = _calc(hr)
    assert it["status"] == "score_provisional"
    assert abs(it["historical"]["historical_multiplier"] - 1.0) < 1e-9
    assert it["score"] == 53
    assert it["historical"]["sample_size"] == 16
    assert it["historical"]["min_sample"] == MIN_SAMPLE


def test_richmond_hr70_score_64():
    hr = {
        "status": "ok",
        "score": 70,
        "selected_sample_size": 40,
        "sample_size": 40,
        "sample_confidence": 0.4,
    }
    it = _calc(hr)
    assert abs(historical_multiplier_from_score(70) - 1.20) < 1e-9
    assert abs(it["historical"]["historical_multiplier"] - 1.20) < 1e-9
    theor = it["theoretical"]["theoretical_raw_score"]
    raw = theor * 1.20
    assert abs(raw - 64.0961) < 0.2
    assert it["score"] == 64
    assert it["class"] == "Alta"
    assert it["status"] == "score"


def test_richmond_hr30_score_43():
    hr = {
        "status": "ok",
        "score": 30,
        "selected_sample_size": 40,
        "sample_size": 40,
        "sample_confidence": 0.4,
    }
    it = _calc(hr)
    assert abs(it["historical"]["historical_multiplier"] - 0.80) < 1e-9
    theor = it["theoretical"]["theoretical_raw_score"]
    raw = theor * 0.80
    assert abs(raw - 42.7307) < 0.2
    assert it["score"] == 43
    assert it["class"] == "Media"


def test_richmond_definitive_sample_30():
    hr = {
        "status": "ok",
        "score": 55,
        "selected_sample_size": 30,
        "sample_size": 30,
        "sample_confidence": 0.3,
    }
    it = _calc(hr)
    assert it["status"] == "score"
    assert it["calculation_quality"] == "full"


def test_richmond_audit_complete_with_insufficient_history():
    it = _calc(None)
    assert it["theoretical"]["theoretical_raw_score"] is not None
    assert it["formula_steps"]
    assert any("theoretical_raw" in s for s in it["formula_steps"])
    assert it["candidate_version"] == PURCHASABILITY_V31_CANDIDATE_VERSION
    assert it["audit_version"] == PURCHASABILITY_V31_AUDIT_VERSION
    assert it["formula_version"] == PURCHASABILITY_V31_FORMULA_VERSION
    assert "historical_sample_insufficient" not in it["gate_reason_codes"]


def test_multiplier_anchors():
    assert abs(historical_multiplier_from_score(0) - 0.50) < 1e-9
    assert abs(historical_multiplier_from_score(25) - 0.75) < 1e-9
    assert abs(historical_multiplier_from_score(50) - 1.00) < 1e-9
    assert abs(historical_multiplier_from_score(75) - 1.25) < 1e-9
    assert abs(historical_multiplier_from_score(100) - 1.50) < 1e-9


def test_hr_metrics_under_min_sample():
    metrics = {
        "sample_size": 16,
        "wins": 8,
        "losses": 8,
        "voids": 0,
        "win_rate": 0.5,
        "average_odds": 2.0,
        "average_break_even_probability": 0.5,
        "realized_margin": 0.0,
        "total_profit": 0.0,
        "roi": 0.0,
        "stability_ratio": None,
        "positive_periods": 0,
        "total_periods": 1,
    }
    out = calculate_historical_reliability(
        metrics,
        selection=SEL_HOME,
        rating=86,
        cohort_meta={
            "selected_sample_size": 16,
            "global_sample_size": 16,
            "local_sample_size": 0,
            "fallback_used": True,
            "fallback_reason": "global_below_minimum",
        },
    )
    assert out["status"] == "provisional_insufficient_sample"
    assert out["score"] is not None
    assert out["wins"] == 8
    assert out["roi"] == 0.0
    assert out["stability_status"] == "insufficient_periods"
    assert out["stability_component"] == 50


def test_registry_v1_v2_distinct_idempotency_inputs():
    v2 = get_replay_formula_config("v31")
    v1 = get_replay_formula_config("v31_v1")
    assert v2.formula_version == PURCHASABILITY_V31_FORMULA_VERSION
    assert v1.formula_version == PURCHASABILITY_V31_FORMULA_VERSION_V1
    assert v2.formula_version != v1.formula_version
    assert v2.replay_schema_version != v1.replay_schema_version


def test_go_no_go_v2_blocks_final_on_provisional_only():
    analytics = {
        "coverage": {
            "score_production_rate": 0.5,
            "definitive_score_count": 0,
            "provisional_score_count": 100,
            "theoretical_score_count": 100,
            "reason_code_counts": {},
            "reconciliation": {"ok": True},
        },
        "positive_signal_health": {
            "scored_real_count": 100,
            "high_count": 40,
            "very_high_count": 10,
            "positive_tail_sample_sufficient": True,
            "all_negative_collapse": False,
            "positive_tail_detected": True,
        },
        "performance_blocks": {"counts": {"definitive_only": 0, "provisional_only": 100}},
        "replay": {"formula_version": PURCHASABILITY_V31_FORMULA_VERSION},
    }
    decision = evaluate_purchasability_v31_go_no_go_v2(
        analytics,
        context={
            "formula_version": PURCHASABILITY_V31_FORMULA_VERSION,
            "leakage_detected": False,
            "reconciliation_ok": True,
        },
    )
    assert decision["decision_version"] == GO_NO_GO_VERSION_V2
    assert decision["decision"] != "GO_FINAL"
    assert decision["promotion_allowed"] is False
