"""Chiavi di mercato: analisi, famiglia, etichette italiane."""

from __future__ import annotations

import pytest

from app.services.cecchino_v4.constants import CLASSIC_MARKETS
from app.services.cecchino_v4.selection.labels import (
    KIND_AH,
    KIND_CLASSIC,
    KIND_STAT,
    ah_market_key,
    family_label,
    format_line,
    market_family,
    market_label,
    parse_market_key,
    stat_market_key,
)


def test_parse_classic_over_under():
    parsed = parse_market_key("OVER_2_5")
    assert parsed.kind == KIND_CLASSIC
    assert parsed.family == "FT_OVER_UNDER"
    assert parsed.direction == "over"
    assert parsed.line == 2.5


def test_parse_ah_and_stat():
    ah = parse_market_key("AH_AWAY:+0.25")
    assert (ah.kind, ah.side, ah.line, ah.family) == (KIND_AH, "away", 0.25, "AH")
    stat = parse_market_key("STAT:sot:away:over:6.5")
    assert (stat.kind, stat.stat, stat.side, stat.direction, stat.line, stat.family) == (KIND_STAT, "sot", "away", "over", 6.5, "STAT_sot")


@pytest.mark.parametrize("bad", ["", "FOO", "AH_HOME", "AH_HOME:-0.3", "AH_MID:-0.5", "STAT:sot:away:over", "STAT:xg:home:over:1.5", "STAT:sot:left:over:1.5", "STAT:sot:home:above:1.5", "STAT:sot:home:over:x"])
def test_parse_invalid_keys_raise(bad):
    with pytest.raises(ValueError):
        parse_market_key(bad)


def test_all_classic_markets_have_family_and_label():
    for key in CLASSIC_MARKETS:
        assert market_family(key) in {"FT_1X2", "DOUBLE_CHANCE", "FT_OVER_UNDER", "HT_1X2"}
        assert market_label(key, "Milan", "Inter")


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("HOME", "1"),
        ("DRAW", "X"),
        ("AWAY", "2"),
        ("ONE_X", "1X"),
        ("X_TWO", "X2"),
        ("ONE_TWO", "12"),
        ("OVER_2_5", "Over 2,5"),
        ("UNDER_1_5", "Under 1,5"),
        ("HOME_PT", "1 primo tempo"),
        ("DRAW_PT", "X primo tempo"),
        ("AH_HOME:-0.5", "Casa −0,5 (handicap asiatico)"),
        ("AH_HOME:+0.25", "Casa +0,25 (handicap asiatico)"),
        ("AH_AWAY:0.0", "Ospite 0 (handicap asiatico)"),
        ("AH_AWAY:-1.75", "Ospite −1,75 (handicap asiatico)"),
        ("STAT:sot:away:over:6.5", "Inter over 6,5 tiri in porta"),
        ("STAT:corners:total:under:9.5", "Corner totali under 9,5"),
        ("STAT:cards:home:over:2.5", "Milan over 2,5 cartellini"),
        ("STAT:shots:total:over:24.5", "Tiri totali over 24,5"),
        ("STAT:fouls:away:under:12.5", "Inter under 12,5 falli"),
    ],
)
def test_market_label(key, expected):
    assert market_label(key, "Milan", "Inter") == expected


def test_family_for_each_kind():
    assert market_family("HOME") == "FT_1X2"
    assert market_family("X_TWO") == "DOUBLE_CHANCE"
    assert market_family("HOME_PT") == "HT_1X2"
    assert market_family("AH_HOME:-1.0") == "AH"
    assert market_family("STAT:cards:total:over:4.5") == "STAT_cards"


def test_key_builders_round_trip():
    assert ah_market_key("home", -0.5) == "AH_HOME:-0.5"
    assert ah_market_key("away", 0.25) == "AH_AWAY:+0.25"
    assert ah_market_key("home", 0) == "AH_HOME:0.0"
    assert ah_market_key("home", -1.0) == "AH_HOME:-1.0"
    assert ah_market_key("home", -1.75) == "AH_HOME:-1.75"
    assert stat_market_key("sot", "away", "over", 6.5) == "STAT:sot:away:over:6.5"
    for key in ("AH_HOME:-0.5", "AH_AWAY:+0.25", "AH_HOME:0.0", "STAT:sot:away:over:6.5"):
        parse_market_key(key)


def test_format_line_and_family_label():
    assert format_line(6.5) == "6,5"
    assert format_line(1.0) == "1"
    assert format_line(0.25) == "0,25"
    assert family_label("STAT_sot") == "Tiri in porta"
    assert family_label("FT_1X2") == "Esito finale"
