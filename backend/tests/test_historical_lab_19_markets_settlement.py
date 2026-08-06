"""Settlement Data Lab: 19 mercati + period/line + esiti chiave."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS
from app.services.cecchino.cecchino_signal_evaluation import evaluate_market_selection
from app.services.cecchino_data_lab.historical_settlement import (
    _period_line,
    settle_historical_markets,
)


def test_period_line_complete_for_19_markets():
    assert len(KPI_V2_ROW_DEFS) == 19
    expected = {
        "HOME": ("FT", None),
        "DRAW": ("FT", None),
        "AWAY": ("FT", None),
        "HOME_PT": ("HT", None),
        "DRAW_PT": ("HT", None),
        "AWAY_PT": ("HT", None),
        "ONE_X": ("FT", None),
        "X_TWO": ("FT", None),
        "ONE_TWO": ("FT", None),
        "OVER_1_5": ("FT", 1.5),
        "UNDER_1_5": ("FT", 1.5),
        "OVER_2_5": ("FT", 2.5),
        "UNDER_2_5": ("FT", 2.5),
        "OVER_3_5": ("FT", 3.5),
        "UNDER_3_5": ("FT", 3.5),
        "OVER_PT_0_5": ("HT", 0.5),
        "UNDER_PT_0_5": ("HT", 0.5),
        "OVER_PT_1_5": ("HT", 1.5),
        "UNDER_PT_1_5": ("HT", 1.5),
    }
    for key, (period, line) in expected.items():
        got_p, got_l = _period_line(key)
        assert got_p == period, key
        assert got_l == line, key


def test_settlement_emits_exactly_19_market_keys():
    match = SimpleNamespace(
        ft_home_goals=2,
        ft_away_goals=1,
        ht_home_goals=1,
        ht_away_goals=0,
    )
    rows = settle_historical_markets(
        match=match,
        kpi_panel={"rows": []},
        quote_bundle={"quotes": {}},
        signals_json=None,
    )
    keys = [r["market_key"] for r in rows]
    assert len(keys) == 19
    assert len(set(keys)) == 19
    for r in rows:
        assert r["period"] in ("FT", "HT")
        assert r["period"] is not None


def test_key_market_settlement_rules():
    # HOME_PT / DRAW_PT / AWAY_PT on HT
    assert evaluate_market_selection(
        "HOME_PT",
        {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 1, "away": 1}},
    )["evaluation_status"] == "won"
    assert evaluate_market_selection(
        "DRAW_PT",
        {"halftime": {"home": 1, "away": 1}, "fulltime": {"home": 2, "away": 1}},
    )["evaluation_status"] == "won"
    assert evaluate_market_selection(
        "AWAY_PT",
        {"halftime": {"home": 0, "away": 1}, "fulltime": {"home": 2, "away": 1}},
    )["evaluation_status"] == "won"

    # UNDER_1_5: FT totale <= 1
    assert evaluate_market_selection(
        "UNDER_1_5",
        {"fulltime": {"home": 1, "away": 0}, "halftime": {"home": 0, "away": 0}},
    )["evaluation_status"] == "won"
    assert evaluate_market_selection(
        "UNDER_1_5",
        {"fulltime": {"home": 1, "away": 1}, "halftime": {"home": 0, "away": 0}},
    )["evaluation_status"] == "lost"

    # OVER_3_5: FT totale >= 4
    assert evaluate_market_selection(
        "OVER_3_5",
        {"fulltime": {"home": 3, "away": 1}, "halftime": {"home": 1, "away": 0}},
    )["evaluation_status"] == "won"
    assert evaluate_market_selection(
        "OVER_3_5",
        {"fulltime": {"home": 2, "away": 1}, "halftime": {"home": 1, "away": 0}},
    )["evaluation_status"] == "lost"

    # UNDER_PT_0_5: HT totale = 0
    assert evaluate_market_selection(
        "UNDER_PT_0_5",
        {"halftime": {"home": 0, "away": 0}, "fulltime": {"home": 2, "away": 1}},
    )["evaluation_status"] == "won"
    assert evaluate_market_selection(
        "UNDER_PT_0_5",
        {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 2, "away": 1}},
    )["evaluation_status"] == "lost"
