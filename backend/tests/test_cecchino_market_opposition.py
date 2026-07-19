"""Test mappa mercati opposti — Acquistabilità Fase 2."""

from __future__ import annotations

from app.services.cecchino.cecchino_market_opposition import get_opposition
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)


def test_opposition_home_away_draw():
    assert get_opposition(SEL_HOME)["comparator_selections"] == [SEL_AWAY]
    assert get_opposition(SEL_HOME)["complement_selection"] == SEL_X_TWO
    assert get_opposition(SEL_AWAY)["comparator_selections"] == [SEL_HOME]
    assert get_opposition(SEL_DRAW)["comparator_selections"] == [SEL_HOME, SEL_AWAY]


def test_opposition_double_chance():
    assert get_opposition(SEL_ONE_X)["comparator_selections"] == [SEL_AWAY]
    assert get_opposition(SEL_X_TWO)["comparator_selections"] == [SEL_HOME]
    assert get_opposition(SEL_ONE_TWO)["comparator_selections"] == [SEL_DRAW]


def test_opposition_ou_ft_and_pt():
    assert get_opposition(SEL_OVER_2_5)["comparator_selections"] == [SEL_UNDER_2_5]
    assert get_opposition(SEL_UNDER_2_5)["comparator_selections"] == [SEL_OVER_2_5]
    assert get_opposition(SEL_OVER_PT_1_5)["comparator_selections"] == [SEL_UNDER_PT_1_5]
    assert get_opposition(SEL_UNDER_PT_1_5)["comparator_selections"] == [SEL_OVER_PT_1_5]


def test_comparator_distinct_from_complement_home():
    home = get_opposition(SEL_HOME)
    assert home["comparator_selections"] != [home["complement_selection"]]
    assert home["complement_selection"] == SEL_X_TWO


def test_no_cross_line_or_period_in_supported_ou():
    o25 = get_opposition(SEL_OVER_2_5)
    assert o25["line"] == 2.5
    assert o25["period"] == "FT"
    assert SEL_UNDER_PT_1_5 not in o25["comparator_selections"]
    assert SEL_UNDER_3_5 not in o25["comparator_selections"]


def test_unsupported_incomplete_panel_markets():
    for sel in (SEL_OVER_1_5, SEL_UNDER_3_5, SEL_OVER_PT_0_5, SEL_DRAW_PT):
        opp = get_opposition(sel)
        assert opp["opposition_status"] == "unsupported"
        assert opp["comparator_selections"] == []
