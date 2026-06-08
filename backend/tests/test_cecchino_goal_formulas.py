"""Test formule goal Cecchino — Fase 26."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_fixture_history import GoalFixtureSlices, GoalTotals
from app.services.cecchino.cecchino_goal_formulas import (
    FORMULA_FT_OVER,
    FORMULA_FT_UNDER,
    FORMULA_PT,
    build_goal_market_cecchino_odds,
    calculate_first_half_rate_to_odd,
    calculate_over_fulltime_excel_parity,
    calculate_under_fulltime_excel_parity,
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


def _totals(
    *,
    sample: int = 5,
    gf: int = 10,
    ga: int = 5,
    pt05: int = 4,
    pt15: int = 2,
    upt15: int = 3,
) -> GoalTotals:
    return GoalTotals(
        sample=sample,
        goals_for=gf,
        goals_against=ga,
        total_goals=gf + ga,
        over_1_5_hits=sample,
        over_2_5_hits=sample,
        under_2_5_hits=sample,
        under_3_5_hits=sample,
        over_pt_0_5_hits=pt05,
        over_pt_1_5_hits=pt15,
        under_pt_1_5_hits=upt15,
        fixture_ids=list(range(sample)),
    )


def _full_slices() -> GoalFixtureSlices:
    return GoalFixtureSlices(
        home_home_5=_totals(sample=5, gf=10, ga=5),
        away_away_5=_totals(sample=5, gf=8, ga=12),
        home_total_10=_totals(sample=10, gf=20, ga=15),
        away_total_10=_totals(sample=10, gf=18, ga=22),
        home_home_ht_5=_totals(sample=5, pt05=4, pt15=2, upt15=3),
        away_away_ht_5=_totals(sample=5, pt05=3, pt15=1, upt15=4),
        skipped_missing_halftime_score=2,
    )


def _thin_slices() -> GoalFixtureSlices:
    return GoalFixtureSlices(
        home_home_5=_totals(sample=2, gf=4, ga=2),
        away_away_5=_totals(sample=2, gf=3, ga=5),
        home_total_10=_totals(sample=4, gf=8, ga=6),
        away_total_10=_totals(sample=4, gf=7, ga=9),
        home_home_ht_5=_totals(sample=2, pt05=1, pt15=0, upt15=2),
        away_away_ht_5=_totals(sample=2, pt05=1, pt15=0, upt15=1),
        skipped_missing_halftime_score=0,
    )


def test_over_15_uses_excel_parity_formula():
    markets = build_goal_market_cecchino_odds(_full_slices())
    assert markets[SEL_OVER_1_5]["formula_version"] == FORMULA_FT_OVER


def test_over_25_uses_excel_parity_formula():
    markets = build_goal_market_cecchino_odds(_full_slices())
    assert markets[SEL_OVER_2_5]["formula_version"] == FORMULA_FT_OVER


def test_under_25_uses_excel_parity_formula():
    markets = build_goal_market_cecchino_odds(_full_slices())
    assert markets[SEL_UNDER_2_5]["formula_version"] == FORMULA_FT_UNDER


def test_under_35_uses_excel_parity_formula():
    markets = build_goal_market_cecchino_odds(_full_slices())
    assert markets[SEL_UNDER_3_5]["formula_version"] == FORMULA_FT_UNDER


def test_over_cf_block_divisor_6():
    out = calculate_over_fulltime_excel_parity(_full_slices())
    block = out["blocks"]["home_away"]
    assert block["divisor_home"] == 6
    assert block["divisor_away"] == 6
    assert block["home_component"] == pytest.approx((10 + 12) / 6, abs=0.0001)
    assert block["away_component"] == pytest.approx((8 + 5) / 6, abs=0.0001)


def test_over_totals_block_divisor_11():
    out = calculate_over_fulltime_excel_parity(_full_slices())
    block = out["blocks"]["totals"]
    assert block["divisor"] == 11
    assert block["home_component"] == pytest.approx((20 + 22) / 11, abs=0.0001)


def test_over_mixed_block_divisor_16():
    out = calculate_over_fulltime_excel_parity(_full_slices())
    block = out["blocks"]["mixed"]
    assert block["divisor"] == 16
    home_for = (10 + 20) / 16
    home_against = (5 + 15) / 16
    assert block["home_coeff"] == pytest.approx((home_for + home_against) / 2, abs=0.0001)


def test_under_cf_block_divisor_4():
    out = calculate_under_fulltime_excel_parity(_full_slices())
    block = out["blocks"]["home_away"]
    assert block["divisor_home"] == 4
    assert block["home_component"] == pytest.approx((10 + 12) / 4, abs=0.0001)


def test_under_totals_block_divisor_9():
    out = calculate_under_fulltime_excel_parity(_full_slices())
    block = out["blocks"]["totals"]
    assert block["divisor"] == 9


def test_under_mixed_block_divisor_14():
    out = calculate_under_fulltime_excel_parity(_full_slices())
    block = out["blocks"]["mixed"]
    assert block["divisor"] == 14


def test_ft_final_is_average_of_three_blocks():
    out = calculate_over_fulltime_excel_parity(_full_slices())
    coeffs = [
        out["blocks"]["home_away"]["block_value"],
        out["blocks"]["totals"]["block_value"],
        out["blocks"]["mixed"]["block_value"],
    ]
    assert out["final_odd"] == pytest.approx(sum(coeffs) / 3, abs=0.01)


def test_over_15_and_over_25_same_odd():
    markets = build_goal_market_cecchino_odds(_full_slices())
    assert markets[SEL_OVER_1_5]["final_odd"] == markets[SEL_OVER_2_5]["final_odd"]


def test_under_25_and_under_35_same_odd():
    markets = build_goal_market_cecchino_odds(_full_slices())
    assert markets[SEL_UNDER_2_5]["final_odd"] == markets[SEL_UNDER_3_5]["final_odd"]


def test_ft_insufficient_sample_returns_null():
    out = calculate_over_fulltime_excel_parity(_thin_slices())
    assert out["final_odd"] is None
    assert out["status"] == STATUS_INSUFFICIENT_DATA


def test_over_pt_05_event_ge_1():
    out = calculate_first_half_rate_to_odd(SEL_OVER_PT_0_5, _full_slices())
    assert out["event"] == "halftime_total_goals >= 1"
    assert out["formula_version"] == FORMULA_PT
    assert out["home"]["hits"] == 4
    assert out["home"]["rate"] == pytest.approx(0.8, abs=0.0001)


def test_over_pt_15_event_ge_2():
    out = calculate_first_half_rate_to_odd(SEL_OVER_PT_1_5, _full_slices())
    assert out["event"] == "halftime_total_goals >= 2"
    assert out["home"]["hits"] == 2


def test_under_pt_15_event_le_1():
    out = calculate_first_half_rate_to_odd(SEL_UNDER_PT_1_5, _full_slices())
    assert out["event"] == "halftime_total_goals <= 1"
    assert out["away"]["hits"] == 4


def test_pt_rate_away_calculated():
    out = calculate_first_half_rate_to_odd(SEL_OVER_PT_0_5, _full_slices())
    assert out["away"]["rate"] == pytest.approx(3 / 5, abs=0.0001)


def test_pt_quota_is_inverse_probability():
    out = calculate_first_half_rate_to_odd(SEL_OVER_PT_0_5, _full_slices())
    prob = (4 / 5 + 3 / 5) / 2
    assert out["probability"] == pytest.approx(prob, abs=0.0001)
    assert out["final_odd"] == pytest.approx(1 / prob, abs=0.01)


def test_pt_zero_probability_no_crash():
    zero = GoalFixtureSlices(
        home_home_5=_totals(sample=5, pt05=0, pt15=0, upt15=5),
        away_away_5=_totals(sample=5, pt05=0, pt15=0, upt15=5),
        home_total_10=_totals(sample=10),
        away_total_10=_totals(sample=10),
        home_home_ht_5=_totals(sample=5, pt05=0, pt15=0, upt15=5),
        away_away_ht_5=_totals(sample=5, pt05=0, pt15=0, upt15=5),
    )
    out = calculate_first_half_rate_to_odd(SEL_OVER_PT_0_5, zero)
    assert out["final_odd"] is None
    assert out["status"] == STATUS_INSUFFICIENT_DATA


def test_pt_insufficient_sample_returns_null():
    out = calculate_first_half_rate_to_odd(SEL_OVER_PT_0_5, _thin_slices())
    assert out["final_odd"] is None
    assert out["status"] == STATUS_INSUFFICIENT_DATA
