"""Test debug picchetti Cecchino — Quota Cecchino breakdown (Fase 25)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.services.cecchino.cecchino_constants import (
    CECCHINO_1X2_WEIGHTS,
    CECCHINO_1X2_WEIGHTS_VERSION,
    CECCHINO_GOAL_MARKET_WEIGHTS,
    CECCHINO_GOAL_WEIGHTS_VERSION,
    FINAL_QUOTA_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
)
from app.services.cecchino.cecchino_engine import (
    CecchinoCalculationInput,
    WDLRecord,
    build_full_cecchino_output,
    compute_final_odds,
    compute_picchetto,
)
from app.services.cecchino.cecchino_picchetti_debug import (
    build_cecchino_picchetti_debug,
    build_picchetti_debug_summary,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_X_TWO,
)


def _san_lorenzo_input() -> CecchinoCalculationInput:
    return CecchinoCalculationInput(
        home_away=(
            WDLRecord(wins=3, draws=2, losses=3),
            WDLRecord(wins=0, draws=3, losses=5),
        ),
        totals=(
            WDLRecord(wins=5, draws=7, losses=4),
            WDLRecord(wins=1, draws=8, losses=7),
        ),
        last5_home_away=(
            WDLRecord(wins=1, draws=2, losses=2),
            WDLRecord(wins=0, draws=2, losses=3),
        ),
        last6_totals=(
            WDLRecord(wins=2, draws=3, losses=1),
            WDLRecord(wins=1, draws=2, losses=3),
        ),
    )


def _output_dict(inp: CecchinoCalculationInput | None = None) -> dict:
    calc = build_full_cecchino_output(inp or _san_lorenzo_input())
    return calc.to_dict()


def _picchetto_prob(picchetti: dict, name: str, outcome: str) -> float | None:
    pic = picchetti.get(name) or {}
    key = {"1": "prob_1", "X": "prob_x", "2": "prob_2"}[outcome]
    probs = pic.get("probabilities") or {}
    return probs.get(key)


def test_debug_returns_correct_weights():
    debug = build_cecchino_picchetti_debug(cecchino_output=_output_dict())
    weights = debug["weights"]
    assert weights["1x2"]["totals"] == 0.30
    assert weights["1x2"]["home_away"] == 0.30
    assert weights["1x2"]["last6_totals"] == 0.20
    assert weights["1x2"]["last5_home_away"] == 0.20
    assert weights["1x2"]["version"] == CECCHINO_1X2_WEIGHTS_VERSION
    assert weights["goal_markets"]["totals"] == 0.20
    assert weights["goal_markets"]["home_away"] == 0.30
    assert weights["goal_markets"]["version"] == CECCHINO_GOAL_WEIGHTS_VERSION
    assert debug["version"] == "cecchino_picchetti_debug_v3"


def test_debug_1x2_formula_uses_current_weights():
    debug = build_cecchino_picchetti_debug(cecchino_output=_output_dict())
    formula = debug["markets"][SEL_HOME]["formula"]
    assert "0.3" in formula
    assert "quota_totals" in formula
    assert "0.25" not in formula


def test_home_away_prob_1():
    block = compute_picchetto(
        PICCHETTO_KEY_HOME_AWAY,
        WDLRecord(3, 2, 3),
        WDLRecord(0, 3, 5),
    )
    total = block.total_matches
    expected = (3 + 5) / total
    assert block.outcome_1.prob == pytest.approx(expected, abs=1e-6)

    out = {
        "picchetti": {PICCHETTO_KEY_HOME_AWAY: block.to_dict()},
        "final": {},
        "warnings": [],
    }
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    row = debug["markets"][SEL_HOME]["picchetti"][1]
    assert row["name"] == PICCHETTO_KEY_HOME_AWAY
    assert row["probability"] == pytest.approx(expected, abs=1e-4)


def test_home_away_prob_x():
    block = compute_picchetto(
        PICCHETTO_KEY_HOME_AWAY,
        WDLRecord(3, 2, 3),
        WDLRecord(0, 3, 5),
    )
    expected = (2 + 3) / block.total_matches
    assert block.outcome_x.prob == pytest.approx(expected, abs=1e-6)


def test_home_away_prob_2():
    block = compute_picchetto(
        PICCHETTO_KEY_HOME_AWAY,
        WDLRecord(3, 2, 3),
        WDLRecord(0, 3, 5),
    )
    expected = (3 + 0) / block.total_matches
    assert block.outcome_2.prob == pytest.approx(expected, abs=1e-6)


def test_totals_calculates_odds():
    block = compute_picchetto(
        PICCHETTO_KEY_TOTALS,
        WDLRecord(5, 7, 4),
        WDLRecord(1, 8, 7),
    )
    assert block.outcome_1.quota == pytest.approx(2.67, abs=0.02)
    assert block.outcome_x.quota == pytest.approx(2.13, abs=0.02)
    assert block.outcome_2.quota == pytest.approx(6.40, abs=0.02)


def test_last6_totals_calculates_odds():
    block = compute_picchetto(
        PICCHETTO_KEY_LAST6_TOTALS,
        WDLRecord(2, 3, 1),
        WDLRecord(1, 2, 3),
    )
    assert block.outcome_1.quota == pytest.approx(2.40, abs=0.02)
    assert block.outcome_x.quota == pytest.approx(2.40, abs=0.02)
    assert block.outcome_2.quota == pytest.approx(6.00, abs=0.02)


def test_last5_home_away_calculates_odds():
    block = compute_picchetto(
        PICCHETTO_KEY_LAST5_HOME_AWAY,
        WDLRecord(1, 2, 2),
        WDLRecord(0, 2, 3),
    )
    assert block.outcome_1.quota == pytest.approx(2.50, abs=0.02)
    assert block.outcome_x.quota == pytest.approx(2.50, abs=0.02)
    assert block.outcome_2.quota == pytest.approx(5.00, abs=0.02)


def test_final_quota_1_uses_weights():
    out = _output_dict()
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    mkt = debug["markets"][SEL_HOME]
    contrib_sum = sum(
        p["weighted_contribution"]
        for p in mkt["picchetti"]
        if p.get("weighted_contribution") is not None
    )
    assert contrib_sum == pytest.approx(mkt["final_odd"], abs=0.02)
    assert mkt["final_odd"] == pytest.approx(out["final"]["quota_1"], abs=0.02)


def test_final_quota_x_uses_weights():
    out = _output_dict()
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    mkt = debug["markets"][SEL_DRAW]
    contrib_sum = sum(
        p["weighted_contribution"]
        for p in mkt["picchetti"]
        if p.get("weighted_contribution") is not None
    )
    assert contrib_sum == pytest.approx(mkt["final_odd"], abs=0.02)


def test_final_quota_2_uses_weights():
    out = _output_dict()
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    mkt = debug["markets"][SEL_AWAY]
    contrib_sum = sum(
        p["weighted_contribution"]
        for p in mkt["picchetti"]
        if p.get("weighted_contribution") is not None
    )
    assert contrib_sum == pytest.approx(mkt["final_odd"], abs=0.02)


def test_one_x_derived_from_prob_1_and_x():
    out = _output_dict()
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    p1 = out["final"]["prob_1"]
    px = out["final"]["prob_x"]
    expected = round(1.0 / (p1 + px), 2)
    assert debug["markets"][SEL_ONE_X]["final_odd"] == pytest.approx(expected, abs=0.02)


def test_x_two_derived_from_prob_x_and_2():
    out = _output_dict()
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    px = out["final"]["prob_x"]
    p2 = out["final"]["prob_2"]
    expected = round(1.0 / (px + p2), 2)
    assert debug["markets"][SEL_X_TWO]["final_odd"] == pytest.approx(expected, abs=0.02)


def test_one_two_derived_from_prob_1_and_2():
    out = _output_dict()
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    p1 = out["final"]["prob_1"]
    p2 = out["final"]["prob_2"]
    expected = round(1.0 / (p1 + p2), 2)
    assert debug["markets"][SEL_ONE_TWO]["final_odd"] == pytest.approx(expected, abs=0.02)


def test_zero_probability_does_not_crash():
    block = compute_picchetto(
        PICCHETTO_KEY_HOME_AWAY,
        WDLRecord(0, 10, 0),
        WDLRecord(0, 10, 0),
    )
    assert block.outcome_1.quota is None
    out = {
        "picchetti": {PICCHETTO_KEY_HOME_AWAY: block.to_dict()},
        "final": {"status": "insufficient_data"},
        "warnings": [],
    }
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    assert any("zero_probability" in w for w in debug["warnings"])


def test_insufficient_data_generates_warning():
    out = _output_dict()
    del out["picchetti"][PICCHETTO_KEY_TOTALS]
    final = compute_final_odds(
        {
            PICCHETTO_KEY_HOME_AWAY: compute_picchetto(
                PICCHETTO_KEY_HOME_AWAY,
                WDLRecord(3, 2, 3),
                WDLRecord(0, 3, 5),
            ),
            PICCHETTO_KEY_LAST5_HOME_AWAY: compute_picchetto(
                PICCHETTO_KEY_LAST5_HOME_AWAY,
                WDLRecord(1, 2, 2),
                WDLRecord(0, 2, 3),
            ),
            PICCHETTO_KEY_LAST6_TOTALS: compute_picchetto(
                PICCHETTO_KEY_LAST6_TOTALS,
                WDLRecord(2, 3, 1),
                WDLRecord(1, 2, 3),
            ),
        },
    )
    out["final"] = final.to_dict()
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    assert any("missing_picchetto" in w for w in debug["warnings"])


def test_debug_final_odd_matches_kpi_within_tolerance():
    out = _output_dict()
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    kpi_panel = {
        "rows": [
            {"market_key": SEL_HOME, "quota_cecchino": debug["markets"][SEL_HOME]["final_odd"]},
            {"market_key": SEL_DRAW, "quota_cecchino": debug["markets"][SEL_DRAW]["final_odd"]},
            {"market_key": SEL_AWAY, "quota_cecchino": debug["markets"][SEL_AWAY]["final_odd"]},
            {"market_key": SEL_ONE_X, "quota_cecchino": debug["markets"][SEL_ONE_X]["final_odd"]},
        ],
    }
    debug_ok = build_cecchino_picchetti_debug(cecchino_output=out, kpi_panel=kpi_panel)
    assert not any("kpi_debug_mismatch" in w for w in debug_ok["warnings"])

    kpi_bad = {
        "rows": [{"market_key": SEL_HOME, "quota_cecchino": 999.0}],
    }
    debug_bad = build_cecchino_picchetti_debug(cecchino_output=out, kpi_panel=kpi_bad)
    assert any("kpi_debug_mismatch:HOME" in w for w in debug_bad["warnings"])


def test_missing_formulas_listed_without_goal_markets():
    debug = build_cecchino_picchetti_debug(cecchino_output=_output_dict())
    keys = {m["market_key"] for m in debug["missing_formulas"]}
    assert "OVER_1_5" in keys
    assert "UNDER_PT_1_5" in keys
    assert all(m["formula_status"] == "missing_formula" for m in debug["missing_formulas"])


def test_missing_formulas_empty_when_goal_markets_present():
    out = _output_dict()
    out["goal_markets"] = {
        "OVER_1_5": {
            "formula_version": "goal_market_poisson_empirical_v2",
            "final_odd": 2.1,
            "status": "available",
            "weights": dict(CECCHINO_GOAL_MARKET_WEIGHTS),
            "summary": {"final_odd": 2.1, "final_probability": 0.476},
            "contexts": [
                {
                    "name": "last5_home_away",
                    "label": "Ultime 5 casa/fuori",
                    "original_weight": 0.30,
                    "effective_weight": 0.30,
                    "weight_renormalized": False,
                    "sample_home": 5,
                    "sample_away": 5,
                    "status": "available",
                },
            ],
            "legacy_excel_parity": {"final_odd": 1.6, "enabled_for_kpi": False},
        },
        "OVER_2_5": {
            "formula_version": "goal_market_poisson_empirical_v2",
            "final_odd": 2.4,
            "status": "available",
            "summary": {"final_odd": 2.4},
        },
        "UNDER_2_5": {"formula_version": "goal_market_poisson_empirical_v2", "final_odd": 1.9, "status": "available"},
        "UNDER_3_5": {"formula_version": "goal_market_poisson_empirical_v2", "final_odd": 1.7, "status": "available"},
        "OVER_PT_0_5": {"formula_version": "goal_market_poisson_empirical_v2", "final_odd": 1.4, "status": "available"},
        "OVER_PT_1_5": {"formula_version": "goal_market_poisson_empirical_v2", "final_odd": 3.0, "status": "available"},
        "UNDER_PT_1_5": {"formula_version": "goal_market_poisson_empirical_v2", "final_odd": 1.5, "status": "available"},
    }
    debug = build_cecchino_picchetti_debug(cecchino_output=out)
    assert debug["missing_formulas"] == []
    assert "OVER_1_5" in debug["markets"]
    assert debug["markets"]["OVER_1_5"]["final_odd"] == 2.1
    assert debug["markets"]["OVER_1_5"]["weights"] == CECCHINO_GOAL_MARKET_WEIGHTS
    ctx0 = debug["markets"]["OVER_1_5"]["contexts"][0]
    assert ctx0["original_weight"] == 0.30
    assert ctx0["effective_weight"] == 0.30
    assert ctx0["weight_renormalized"] is False
    assert debug["markets"]["OVER_1_5"]["legacy_excel_parity"]["final_odd"] == 1.6
    assert debug["markets"]["OVER_2_5"]["final_odd"] == 2.4
    assert debug["weights"]["1x2"] == {**CECCHINO_1X2_WEIGHTS, "version": CECCHINO_1X2_WEIGHTS_VERSION}


def test_summary_from_full_debug():
    full = build_cecchino_picchetti_debug(cecchino_output=_output_dict())
    summary = build_picchetti_debug_summary(full)
    assert summary["missing_formulas_count"] == 7
    assert summary["formula_status"] == full["formula_status"]
