"""Test modello goal Poisson+empirico v2 — Fase 27."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_fixture_history import (
    GoalContextSlice,
    GoalMarketContexts,
    GoalTotals,
)
from app.services.cecchino.cecchino_goal_poisson_v2 import (
    BLEND_EMPIRICAL,
    BLEND_POISSON,
    FORMULA_V2,
    blend_and_shrink,
    context_reliability,
    empirical_probability_for_context,
    lambda_for_context,
    league_event_probabilities,
    poisson_cumulative,
    poisson_market_probability_ft,
    poisson_market_probability_ht,
    poisson_pmf,
    probability_to_odd,
    weighted_lambda,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
)


def _totals(sample: int = 10, gf: int = 15, ga: int = 10, **hits) -> GoalTotals:
    return GoalTotals(
        sample=sample,
        goals_for=gf,
        goals_against=ga,
        total_goals=gf + ga,
        over_1_5_hits=hits.get("o15", sample),
        over_2_5_hits=hits.get("o25", sample),
        under_2_5_hits=hits.get("u25", 0),
        under_3_5_hits=hits.get("u35", 0),
        over_pt_0_5_hits=hits.get("pt05", sample),
        over_pt_1_5_hits=hits.get("pt15", 2),
        under_pt_1_5_hits=hits.get("upt15", 3),
        fixture_ids=list(range(sample)),
    )


def _ctx(name: str, label: str, sh: int = 10, sa: int = 10) -> GoalContextSlice:
    return GoalContextSlice(
        name=name,
        label=label,
        home_fixtures=[],
        away_fixtures=[],
        home_totals=_totals(sh),
        away_totals=_totals(sa, gf=12, ga=8),
        target_sample=10,
        min_sample=6,
    )


def test_poisson_pmf_known_values():
    assert poisson_pmf(0, 2.0) == pytest.approx(0.1353, abs=0.001)
    assert poisson_pmf(1, 2.0) == pytest.approx(0.2707, abs=0.001)
    assert poisson_pmf(0, 0) == 1.0


def test_over_15_probability():
    lam = 2.5
    p_under = poisson_cumulative(lam, 1)
    assert poisson_market_probability_ft(SEL_OVER_1_5, lam) == pytest.approx(1 - p_under, abs=0.0001)


def test_over_25_probability():
    lam = 2.5
    p_under = poisson_cumulative(lam, 2)
    assert poisson_market_probability_ft(SEL_OVER_2_5, lam) == pytest.approx(1 - p_under, abs=0.0001)


def test_under_25_probability():
    lam = 2.0
    assert poisson_market_probability_ft(SEL_UNDER_2_5, lam) == pytest.approx(poisson_cumulative(lam, 2), abs=0.0001)


def test_under_35_probability():
    lam = 2.0
    assert poisson_market_probability_ft(SEL_UNDER_3_5, lam) == pytest.approx(poisson_cumulative(lam, 3), abs=0.0001)


def test_over_pt_05_probability():
    lam = 1.2
    assert poisson_market_probability_ht(SEL_OVER_PT_0_5, lam) == pytest.approx(1 - poisson_pmf(0, lam), abs=0.0001)


def test_over_pt_15_probability():
    lam = 1.2
    assert poisson_market_probability_ht(SEL_OVER_PT_1_5, lam) == pytest.approx(
        1 - poisson_cumulative(lam, 1),
        abs=0.0001,
    )


def test_under_pt_15_probability():
    lam = 0.8
    assert poisson_market_probability_ht(SEL_UNDER_PT_1_5, lam) == pytest.approx(poisson_cumulative(lam, 1), abs=0.0001)


def test_lambda_for_context():
    home = _totals(10, gf=20, ga=10)
    away = _totals(10, gf=15, ga=12)
    out = lambda_for_context(home, away)
    assert out["lambda_home"] == pytest.approx((2.0 + 1.2) / 2, abs=0.0001)
    assert out["lambda_away"] == pytest.approx((1.5 + 1.0) / 2, abs=0.0001)
    assert out["lambda_total"] == pytest.approx(out["lambda_home"] + out["lambda_away"], abs=0.0001)


def test_weighted_lambda_uses_context_weights():
    contexts = [
        _ctx("totals", "Totali", 10, 10),
        _ctx("home_away", "Casa/Fuori", 5, 5),
        _ctx("last6_totals", "Ultime 6", 6, 6),
        _ctx("last5_home_away", "Ultime 5", 5, 5),
    ]
    for c in contexts[1:]:
        c.target_sample = 5
        c.min_sample = 3
    lam, _, rel, _ = weighted_lambda(contexts)
    assert lam is not None
    assert lam > 0
    assert rel > 0


def test_context_reliability():
    assert context_reliability(10, 8, 10) == 0.8
    assert context_reliability(12, 15, 10) == 1.0


def test_blend_65_35():
    base = BLEND_POISSON * 0.5 + BLEND_EMPIRICAL * 0.4
    assert blend_and_shrink(0.5, 0.4, 1.0, None) == pytest.approx(base, abs=0.0001)


def test_reliability_shrinkage_toward_league():
    shrunk = blend_and_shrink(0.6, 0.5, 0.5, 0.3)
    base = BLEND_POISSON * 0.6 + BLEND_EMPIRICAL * 0.5
    expected = 0.5 * base + 0.5 * 0.3
    assert shrunk == pytest.approx(expected, abs=0.0001)


def test_probability_to_odd():
    odd, raw, capped, warnings = probability_to_odd(0.5)
    assert odd == 2.0
    assert raw == 0.5
    assert capped == 0.5
    assert not warnings


def test_probability_zero_no_crash():
    odd, _, _, warnings = probability_to_odd(0.0)
    assert odd is None
    assert warnings


def test_over_15_and_over_25_differ_same_lambda():
    lam = 2.3
    p15 = poisson_market_probability_ft(SEL_OVER_1_5, lam)
    p25 = poisson_market_probability_ft(SEL_OVER_2_5, lam)
    assert p15 != p25
    assert p15 > p25


def test_under_25_and_under_35_differ_same_lambda():
    lam = 2.8
    u25 = poisson_market_probability_ft(SEL_UNDER_2_5, lam)
    u35 = poisson_market_probability_ft(SEL_UNDER_3_5, lam)
    assert u25 != u35
    assert u35 > u25


def test_kpi_formula_version_constant():
    assert FORMULA_V2 == "goal_market_poisson_empirical_v2"


def test_league_event_probabilities_empty():
    probs = league_event_probabilities([])
    assert probs[SEL_OVER_1_5] is None


def test_insufficient_contexts_returns_none_lambda():
    bad = GoalContextSlice(
        name="totals",
        label="Totali",
        home_fixtures=[],
        away_fixtures=[],
        home_totals=_totals(2),
        away_totals=_totals(2),
        target_sample=10,
        min_sample=6,
    )
    lam, _, _, warnings = weighted_lambda([bad])
    assert lam is None
    assert any("low_sample" in w for w in warnings)
