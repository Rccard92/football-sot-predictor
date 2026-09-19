"""Regolamento: ogni ramo per 1X2, doppia chance, over/under, primo tempo, handicap (anche a quarti), statistiche."""

from __future__ import annotations

import pytest

from app.services.cecchino_v4.selection.settlement import (
    HALF_LOST,
    HALF_WON,
    LOST,
    VOID,
    WON,
    ah_outcome,
    cards_points,
    profit_units,
    settle,
    stat_value,
)

R_1_2 = {"ft_home": 1, "ft_away": 2, "ht_home": 0, "ht_away": 1}
R_2_2 = {"ft_home": 2, "ft_away": 2, "ht_home": 1, "ht_away": 1}
R_3_0 = {"ft_home": 3, "ft_away": 0, "ht_home": 2, "ht_away": 0}


@pytest.mark.parametrize(
    ("key", "result", "expected"),
    [
        ("HOME", R_3_0, WON),
        ("HOME", R_1_2, LOST),
        ("HOME", R_2_2, LOST),
        ("DRAW", R_2_2, WON),
        ("DRAW", R_1_2, LOST),
        ("AWAY", R_1_2, WON),
        ("AWAY", R_2_2, LOST),
        ("ONE_X", R_2_2, WON),
        ("ONE_X", R_1_2, LOST),
        ("X_TWO", R_1_2, WON),
        ("X_TWO", R_3_0, LOST),
        ("ONE_TWO", R_3_0, WON),
        ("ONE_TWO", R_2_2, LOST),
        ("OVER_2_5", R_1_2, WON),
        ("OVER_2_5", R_2_2, WON),
        ("UNDER_2_5", R_2_2, LOST),
        ("UNDER_3_5", R_1_2, WON),
        ("OVER_3_5", R_3_0, LOST),
        ("OVER_0_5", R_3_0, WON),
        ("UNDER_0_5", R_3_0, LOST),
        ("HOME_PT", R_3_0, WON),
        ("HOME_PT", R_2_2, LOST),
        ("DRAW_PT", R_2_2, WON),
        ("DRAW_PT", R_1_2, LOST),
        ("AWAY_PT", R_1_2, WON),
        ("AWAY_PT", R_3_0, LOST),
    ],
)
def test_classic_settlement(key, result, expected):
    assert settle(key, result) == expected


def test_half_time_market_without_ht_score_is_none():
    assert settle("HOME_PT", {"ft_home": 2, "ft_away": 0}) is None
    assert settle("HOME", {"ft_home": None, "ft_away": 0}) is None
    assert settle("HOME", None) is None


@pytest.mark.parametrize(
    ("key", "result", "expected"),
    [
        # linee intere e mezze: una sola puntata
        ("AH_HOME:-0.5", R_3_0, WON),
        ("AH_HOME:-0.5", R_2_2, LOST),
        ("AH_HOME:0.0", R_2_2, VOID),
        ("AH_HOME:0.0", R_3_0, WON),
        ("AH_HOME:-1.0", {"ft_home": 2, "ft_away": 1}, VOID),
        ("AH_HOME:-1.0", R_3_0, WON),
        ("AH_HOME:-1.5", {"ft_home": 2, "ft_away": 1}, LOST),
        ("AH_AWAY:-0.5", R_1_2, WON),  # ospite parte da -0,5 e vince
        ("AH_AWAY:-0.5", R_2_2, LOST),
        ("AH_AWAY:+0.5", R_2_2, WON),  # ospite parte da +0,5: pari basta
        ("AH_AWAY:+1.0", {"ft_home": 2, "ft_away": 1}, VOID),
        ("AH_AWAY:-2.0", {"ft_home": 0, "ft_away": 2}, VOID),
        # quarti: metà e metà
        ("AH_HOME:-0.25", R_2_2, HALF_LOST),  # -0 rimborsata, -0,5 persa
        ("AH_HOME:+0.25", R_2_2, HALF_WON),  # +0 rimborsata, +0,5 vinta
        ("AH_HOME:-0.25", R_3_0, WON),
        ("AH_HOME:+0.25", R_1_2, LOST),
        ("AH_HOME:-0.75", {"ft_home": 1, "ft_away": 0}, HALF_WON),  # -0,5 vinta, -1 rimborsata
        ("AH_HOME:-1.25", {"ft_home": 1, "ft_away": 0}, HALF_LOST),  # -1 rimborsata, -1,5 persa
        ("AH_AWAY:-0.75", {"ft_home": 0, "ft_away": 1}, HALF_WON),
        ("AH_AWAY:+0.75", {"ft_home": 1, "ft_away": 0}, HALF_LOST),
        ("AH_AWAY:+1.25", {"ft_home": 1, "ft_away": 0}, HALF_WON),  # +1 rimborsata, +1,5 vinta
        ("AH_AWAY:+1.25", {"ft_home": 0, "ft_away": 0}, WON),
        ("AH_HOME:-1.75", R_3_0, WON),
        ("AH_HOME:-1.75", {"ft_home": 2, "ft_away": 0}, HALF_WON),
    ],
)
def test_asian_handicap_settlement(key, result, expected):
    assert settle(key, result) == expected


def test_ah_outcome_direct():
    assert ah_outcome("home", -0.5, 1, 0) == WON
    assert ah_outcome("away", 0.0, 1, 1) == VOID


STATS = {
    "home": {"shots": 11, "sot": 3, "corners": 6, "yellow": 2, "red": 0, "fouls": 12},
    "away": {"shots": 16, "sot": 8, "corners": 4, "yellow": 1, "red": 1, "fouls": 14},
}


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("STAT:sot:away:over:6.5", WON),
        ("STAT:sot:away:under:6.5", LOST),
        ("STAT:sot:home:over:3.5", LOST),
        ("STAT:sot:total:over:10.5", WON),  # 3 + 8 = 11
        ("STAT:sot:total:under:10.5", LOST),
        ("STAT:corners:total:under:9.5", LOST),  # 6 + 4 = 10
        ("STAT:corners:home:over:5.5", WON),
        ("STAT:cards:home:over:1.5", WON),  # 2 gialli = 2
        ("STAT:cards:away:over:2.5", WON),  # 1 giallo + 1 rosso (2) = 3
        ("STAT:cards:away:under:3.5", WON),
        ("STAT:cards:total:over:4.5", WON),  # 2 + 3 = 5
        ("STAT:shots:total:under:27.5", WON),
        ("STAT:fouls:away:over:13.5", WON),
    ],
)
def test_stat_settlement(key, expected):
    assert settle(key, {"ft_home": 1, "ft_away": 2}, STATS) == expected


def test_stat_settlement_missing_stats_returns_none():
    assert settle("STAT:sot:away:over:6.5", {"ft_home": 1, "ft_away": 2}, None) is None
    assert settle("STAT:sot:away:over:6.5", None, {"home": {"sot": 3}}) is None  # manca l'ospite
    assert settle("STAT:fouls:home:over:9.5", None, {"home": {"sot": 3}, "away": {"sot": 8}}) is None  # manca la statistica
    assert settle("STAT:sot:total:over:9.5", None, {"home": {"sot": 3}, "away": {}}) is None


def test_stat_settlement_integer_line_void_on_exact():
    assert settle("STAT:corners:total:over:10.0", None, STATS) == VOID


def test_cards_points_and_stat_value():
    assert cards_points({"yellow": 2, "red": 1}) == 4.0
    assert cards_points({"cards": 3}) == 3.0
    assert cards_points({}) is None
    assert stat_value(STATS, "cards", "total") == 5.0
    assert stat_value(STATS, "shots", "away") == 16.0
    assert stat_value(None, "shots", "away") is None


@pytest.mark.parametrize(
    ("outcome", "quota", "expected"),
    [
        (WON, 1.85, 0.85),
        (LOST, 1.85, -1.0),
        (VOID, 1.85, 0.0),
        (HALF_WON, 1.85, 0.425),
        (HALF_LOST, 1.85, -0.5),
        (None, 1.85, None),
        (WON, None, None),
    ],
)
def test_profit_units(outcome, quota, expected):
    result = profit_units(outcome, quota)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_profit_units_unknown_outcome():
    with pytest.raises(ValueError):
        profit_units("boh", 2.0)
