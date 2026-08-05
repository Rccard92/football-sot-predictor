"""Test matematici Fase 1B — complementarità OU e famiglia 1X2 PT."""

from __future__ import annotations

from math import exp
from types import SimpleNamespace

import pytest

from app.services.cecchino.cecchino_constants import (
    STATUS_INSUFFICIENT_DATA,
)
from app.services.cecchino.cecchino_fixture_history import (
    CONTEXT_KEY_HOME_AWAY,
    CONTEXT_KEY_LAST5_HOME_AWAY,
    CONTEXT_KEY_LAST6_TOTALS,
    CONTEXT_KEY_TOTALS,
    GoalContextSlice,
    GoalMarketContexts,
    GoalTotals,
)
from app.services.cecchino.cecchino_goal_poisson_v2 import (
    BLEND_EMPIRICAL,
    BLEND_POISSON,
    COMPLEMENT_TOLERANCE,
    FAMILY_SUM_TOLERANCE,
    FORMULA_HT_1X2_V2,
    FORMULA_V2,
    MIN_PROB,
    blend_and_shrink,
    calculate_first_half_1x2_family_v2,
    calculate_goal_market_pair_v2,
    poisson_cumulative,
    poisson_market_probability_ft,
    poisson_market_probability_ht,
    poisson_pmf,
    probability_to_odd,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY_PT,
    SEL_DRAW_PT,
    SEL_HOME_PT,
    SEL_OVER_1_5,
    SEL_OVER_3_5,
    SEL_OVER_PT_0_5,
    SEL_UNDER_1_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
)


def _totals(sample: int = 10, gf: int = 15, ga: int = 10, **hits) -> GoalTotals:
    return GoalTotals(
        sample=sample,
        goals_for=gf,
        goals_against=ga,
        total_goals=gf + ga,
        over_1_5_hits=hits.get("o15", sample),
        over_2_5_hits=hits.get("o25", sample // 2),
        under_2_5_hits=hits.get("u25", sample // 2),
        under_3_5_hits=hits.get("u35", sample // 2),
        over_pt_0_5_hits=hits.get("pt05", sample),
        over_pt_1_5_hits=hits.get("pt15", 2),
        under_pt_1_5_hits=hits.get("upt15", 3),
        halftime_draw_hits=hits.get("ht_draw", sample // 3),
        fixture_ids=list(range(sample)),
    )


def _ctx(name: str, label: str, sh: int = 10, sa: int = 10, **hits) -> GoalContextSlice:
    return GoalContextSlice(
        name=name,
        label=label,
        home_fixtures=[],
        away_fixtures=[],
        home_totals=_totals(sh, **hits),
        away_totals=_totals(sa, gf=12, ga=8, **hits),
        target_sample=10 if sh >= 10 else 5,
        min_sample=6 if sh >= 10 else 3,
    )


def _goal_contexts(**hits) -> GoalMarketContexts:
    return GoalMarketContexts(
        totals=_ctx(CONTEXT_KEY_TOTALS, "totals", **hits),
        home_away=_ctx(CONTEXT_KEY_HOME_AWAY, "home_away", 8, 8, **hits),
        last6_totals=_ctx(CONTEXT_KEY_LAST6_TOTALS, "last6", 6, 6, **hits),
        last5_home_away=_ctx(CONTEXT_KEY_LAST5_HOME_AWAY, "last5", 5, 5, **hits),
        ht_totals=_ctx(CONTEXT_KEY_TOTALS, "totals", **hits),
        ht_home_away=_ctx(CONTEXT_KEY_HOME_AWAY, "home_away", 8, 8, **hits),
        ht_last6_totals=_ctx(CONTEXT_KEY_LAST6_TOTALS, "last6", 6, 6, **hits),
        ht_last5_home_away=_ctx(CONTEXT_KEY_LAST5_HOME_AWAY, "last5", 5, 5, **hits),
        home_team_id=1,
        away_team_id=2,
    )


def _legacy():
    return SimpleNamespace()


# --- Under 1.5 / Over 3.5 / Under PT 0.5 formulas ---


def test_under_15_poisson_formula():
    lam = 2.1
    expected = exp(-lam) * (1 + lam)
    assert poisson_market_probability_ft(SEL_UNDER_1_5, lam) == pytest.approx(expected, abs=1e-12)
    assert poisson_market_probability_ft(SEL_UNDER_1_5, lam) == pytest.approx(
        poisson_cumulative(lam, 1), abs=1e-12,
    )


def test_over_35_poisson_tail_formula():
    lam = 2.4
    expected = 1.0 - exp(-lam) * (
        1 + lam + lam**2 / 2 + lam**3 / 6
    )
    assert poisson_market_probability_ft(SEL_OVER_3_5, lam) == pytest.approx(expected, abs=1e-9)
    assert poisson_market_probability_ft(SEL_OVER_3_5, lam) == pytest.approx(
        1.0 - poisson_cumulative(lam, 3), abs=1e-12,
    )


def test_over_35_extreme_lambda():
    assert 0.0 <= poisson_market_probability_ft(SEL_OVER_3_5, 0.01) <= 1.0
    assert 0.0 <= poisson_market_probability_ft(SEL_OVER_3_5, 12.0) <= 1.0


def test_under_pt_05_poisson_formula():
    lam = 0.85
    assert poisson_market_probability_ht(SEL_UNDER_PT_0_5, lam) == pytest.approx(
        exp(-lam), abs=1e-12,
    )
    assert poisson_market_probability_ht(SEL_UNDER_PT_0_5, lam) == pytest.approx(
        poisson_pmf(0, lam), abs=1e-12,
    )


def test_odd_equals_one_over_final_probability():
    odd, raw, capped, _ = probability_to_odd(0.4)
    assert odd == pytest.approx(round(1.0 / capped, 2))
    assert raw == 0.4


# --- Complementary pairs shared pipeline ---


def test_pair_under_over_15_raw_sum_one():
    contexts = _goal_contexts()
    league = {SEL_UNDER_1_5: 0.28, SEL_OVER_1_5: 0.72}
    pair = calculate_goal_market_pair_v2(
        SEL_UNDER_1_5, SEL_OVER_1_5, contexts, league, legacy_slices=_legacy(), is_ht=False,
    )
    u = pair[SEL_UNDER_1_5]
    o = pair[SEL_OVER_1_5]
    assert u["formula_version"] == FORMULA_V2
    assert o["formula_version"] == FORMULA_V2
    assert u["complement_sum_check"]["ok"] is True
    assert u["complement_sum_check"]["sum_raw"] == pytest.approx(1.0, abs=COMPLEMENT_TOLERANCE)
    assert o["complementary_market"] == SEL_UNDER_1_5
    assert u["final_odd"] is not None and o["final_odd"] is not None


def test_pair_over_under_35_raw_sum_one():
    contexts = _goal_contexts()
    league = {SEL_UNDER_3_5: 0.65, SEL_OVER_3_5: 0.35}
    pair = calculate_goal_market_pair_v2(
        SEL_UNDER_3_5, SEL_OVER_3_5, contexts, league, legacy_slices=_legacy(), is_ht=False,
    )
    assert pair[SEL_UNDER_3_5]["complement_sum_check"]["ok"] is True
    assert pair[SEL_UNDER_3_5]["final_odd"] is not None
    assert pair[SEL_OVER_3_5]["final_odd"] is not None


def test_pair_under_over_pt_05_raw_sum_one():
    contexts = _goal_contexts()
    league = {SEL_UNDER_PT_0_5: 0.40, SEL_OVER_PT_0_5: 0.60}
    pair = calculate_goal_market_pair_v2(
        SEL_UNDER_PT_0_5,
        SEL_OVER_PT_0_5,
        contexts,
        league,
        legacy_slices=_legacy(),
        is_ht=True,
    )
    assert pair[SEL_UNDER_PT_0_5]["complement_sum_check"]["ok"] is True
    assert pair[SEL_UNDER_PT_0_5]["event_definition"] == "HT total goals = 0"
    assert pair[SEL_UNDER_PT_0_5]["final_odd"] is not None


def test_poisson_complements_all_ft_lines():
    for lam in (0.5, 1.5, 2.5, 4.0):
        assert (
            poisson_market_probability_ft(SEL_OVER_1_5, lam)
            + poisson_market_probability_ft(SEL_UNDER_1_5, lam)
        ) == pytest.approx(1.0, abs=1e-12)
        assert (
            poisson_market_probability_ft(SEL_OVER_3_5, lam)
            + poisson_market_probability_ft(SEL_UNDER_3_5, lam)
        ) == pytest.approx(1.0, abs=1e-12)


# --- HT 1X2 family ---


def test_ht_1x2_family_sums_to_one():
    contexts = _goal_contexts(ht_draw=4)
    league = {SEL_HOME_PT: 0.33, SEL_DRAW_PT: 0.34, SEL_AWAY_PT: 0.33}
    family = calculate_first_half_1x2_family_v2(contexts, league)
    assert set(family) == {SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT}
    assert family[SEL_HOME_PT]["family"]["sum_check"]["ok"] is True
    assert family[SEL_HOME_PT]["family"]["sum_check"]["sum"] == pytest.approx(
        1.0, abs=FAMILY_SUM_TOLERANCE,
    )
    for mk in family:
        assert family[mk]["formula_version"] == FORMULA_HT_1X2_V2
        assert family[mk]["final_odd"] is not None
        assert family[mk]["final_odd"] > 0


def test_ht_1x2_symmetry_equal_samples():
    contexts = _goal_contexts(ht_draw=3)
    league = {SEL_HOME_PT: 1 / 3, SEL_DRAW_PT: 1 / 3, SEL_AWAY_PT: 1 / 3}
    family = calculate_first_half_1x2_family_v2(contexts, league)
    p1 = family[SEL_HOME_PT]["summary"]["final_probability_raw"]
    p2 = family[SEL_AWAY_PT]["summary"]["final_probability_raw"]
    assert p1 == pytest.approx(p2, abs=1e-9)


def test_ht_1x2_draw_prevalence_increases_x():
    low = calculate_first_half_1x2_family_v2(
        _goal_contexts(ht_draw=1),
        {SEL_HOME_PT: 0.33, SEL_DRAW_PT: 0.34, SEL_AWAY_PT: 0.33},
    )
    high = calculate_first_half_1x2_family_v2(
        _goal_contexts(ht_draw=8),
        {SEL_HOME_PT: 0.33, SEL_DRAW_PT: 0.34, SEL_AWAY_PT: 0.33},
    )
    assert (
        high[SEL_DRAW_PT]["summary"]["empirical_probability"]
        > low[SEL_DRAW_PT]["summary"]["empirical_probability"]
    )


def test_ht_1x2_reliability_zero_uses_league():
    contexts = _goal_contexts(ht_draw=3)
    # Force low reliability by tiny samples on all usable contexts
    for slice_name in (
        "ht_totals", "ht_home_away", "ht_last6_totals", "ht_last5_home_away",
    ):
        sl = getattr(contexts, slice_name)
        sl.home_totals = _totals(10, ht_draw=9)
        sl.away_totals = _totals(10, ht_draw=9)
    league = {SEL_HOME_PT: 0.20, SEL_DRAW_PT: 0.50, SEL_AWAY_PT: 0.30}
    # Monkey: overall_rel via shrink — when rel=0, final_pre = league before normalize
    from app.services.cecchino import cecchino_goal_poisson_v2 as mod

    original = mod._overall_reliability_from_contexts

    def _zero_rel(ctx_list):
        rows, warnings = [], []
        return 0.0, rows, warnings

    mod._overall_reliability_from_contexts = _zero_rel
    try:
        family = calculate_first_half_1x2_family_v2(contexts, league)
    finally:
        mod._overall_reliability_from_contexts = original

    # After floor+normalize, DRAW should remain the largest
    assert (
        family[SEL_DRAW_PT]["summary"]["final_probability_raw"]
        >= family[SEL_HOME_PT]["summary"]["final_probability_raw"]
    )


def test_ht_1x2_insufficient_contexts():
    bad = GoalMarketContexts(
        totals=_ctx(CONTEXT_KEY_TOTALS, "t", 2, 2),
        home_away=_ctx(CONTEXT_KEY_HOME_AWAY, "h", 2, 2),
        last6_totals=_ctx(CONTEXT_KEY_LAST6_TOTALS, "l6", 2, 2),
        last5_home_away=_ctx(CONTEXT_KEY_LAST5_HOME_AWAY, "l5", 2, 2),
        ht_totals=_ctx(CONTEXT_KEY_TOTALS, "t", 2, 2),
        ht_home_away=_ctx(CONTEXT_KEY_HOME_AWAY, "h", 2, 2),
        ht_last6_totals=_ctx(CONTEXT_KEY_LAST6_TOTALS, "l6", 2, 2),
        ht_last5_home_away=_ctx(CONTEXT_KEY_LAST5_HOME_AWAY, "l5", 2, 2),
        home_team_id=1,
        away_team_id=2,
    )
    for sl in (
        bad.ht_totals, bad.ht_home_away, bad.ht_last6_totals, bad.ht_last5_home_away,
    ):
        sl.min_sample = 6
        sl.target_sample = 10
    family = calculate_first_half_1x2_family_v2(bad, {})
    for mk in (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT):
        assert family[mk]["status"] == STATUS_INSUFFICIENT_DATA
        assert family[mk]["final_odd"] is None


def test_no_nan_infinite_odds():
    contexts = _goal_contexts()
    league = {
        SEL_UNDER_1_5: 0.3, SEL_OVER_1_5: 0.7,
        SEL_UNDER_3_5: 0.6, SEL_OVER_3_5: 0.4,
        SEL_UNDER_PT_0_5: 0.4, SEL_OVER_PT_0_5: 0.6,
        SEL_HOME_PT: 0.33, SEL_DRAW_PT: 0.34, SEL_AWAY_PT: 0.33,
    }
    pair15 = calculate_goal_market_pair_v2(
        SEL_UNDER_1_5, SEL_OVER_1_5, contexts, league, legacy_slices=_legacy(), is_ht=False,
    )
    family = calculate_first_half_1x2_family_v2(contexts, league)
    for block in list(pair15.values()) + list(family.values()):
        odd = block["final_odd"]
        assert odd is not None and odd > 0
        import math
        assert math.isfinite(odd)
        raw = block["summary"]["final_probability_raw"]
        assert math.isfinite(raw)
        assert 0.0 <= raw <= 1.0


def test_blend_weights_unchanged():
    assert BLEND_POISSON == 0.65
    assert BLEND_EMPIRICAL == 0.35
    assert MIN_PROB == 0.03


def test_shared_lambda_same_for_pair_sides():
    contexts = _goal_contexts()
    league = {SEL_UNDER_1_5: 0.25, SEL_OVER_1_5: 0.75}
    pair = calculate_goal_market_pair_v2(
        SEL_UNDER_1_5, SEL_OVER_1_5, contexts, league, legacy_slices=_legacy(), is_ht=False,
    )
    assert pair[SEL_UNDER_1_5]["summary"]["lambda"] == pair[SEL_OVER_1_5]["summary"]["lambda"]
    assert pair[SEL_UNDER_1_5]["technical"]["shared_pair_pipeline"] is True
