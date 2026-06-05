"""Test mapping strict Over/Under full time e primo tempo (Cecchino Fase 15)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.services.bookmakers.api_football_fixture_raw_odds_service import (
    ApiFootballFixtureRawOddsService,
)
from app.services.bookmakers.market_normalize import (
    is_main_first_half_goals_over_under,
    is_main_full_time_goals_over_under,
    normalize_first_half_over_under_selection,
    normalize_over_under_selection,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
)
from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_bookmaker_derive import build_bookmaker_structures
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS
from app.services.cecchino.cecchino_kpi_panel import build_cecchino_kpi_panel
from app.services.cecchino.cecchino_selection_keys import MARKET_OU, MARKET_OU_FH

FIXTURE_1499460_FT = {
    8: {"over_15": 1.80, "over_25": 3.50},
    3: {"over_15": 1.67, "over_25": 3.30},
    4: {"over_15": 1.77, "over_25": 3.08},
}


def _bet(name: str, bet_id: int, values: list[tuple[str, str]]) -> dict:
    return {
        "id": bet_id,
        "name": name,
        "values": [{"value": v, "odd": o} for v, o in values],
    }


def _payload(*bets: dict) -> list[dict]:
    return [{"bookmakers": [{"bets": list(bets)}]}]


def _row(bid: str, mkt: str, sk: str, val: float) -> SimpleNamespace:
    return SimpleNamespace(
        provider_bookmaker_id=bid,
        normalized_market=mkt,
        selection_key=sk,
        odds_value=val,
    )


def test_strict_full_time_goals_over_under_predicate():
    assert is_main_full_time_goals_over_under("Goals Over/Under", 5) is True
    assert is_main_full_time_goals_over_under("Goals Over/Under", "5") is True
    assert is_main_full_time_goals_over_under("Goal Line", 5) is False
    assert is_main_full_time_goals_over_under("Goals Over/Under", 12) is False


def test_strict_first_half_goals_over_under_predicate():
    assert is_main_first_half_goals_over_under("Goals Over/Under First Half") is True
    assert is_main_first_half_goals_over_under("Goals Over/Under - First Half") is True
    assert is_main_first_half_goals_over_under("Goal Line (1st Half)") is False


def test_full_match_over_15_from_goals_over_under_bet_id_5():
    rows, _ = parse_api_football_odds_response(
        _payload(_bet("Goals Over/Under", 5, [("Over 1.5", "1.80")])),
        requested_markets=[MARKET_OU],
    )
    assert len(rows) == 1
    assert rows[0]["selection_key"] == SEL_OVER_1_5
    assert rows[0]["odds_value"] == 1.80
    assert rows[0]["market_label"] == "Goals Over/Under"


def test_full_match_over_25_from_goals_over_under_bet_id_5():
    rows, _ = parse_api_football_odds_response(
        _payload(_bet("Goals Over/Under", 5, [("Over 2.5", "3.50")])),
        requested_markets=[MARKET_OU],
    )
    assert len(rows) == 1
    assert rows[0]["selection_key"] == SEL_OVER_2_5


def test_goal_line_does_not_feed_main_over():
    rows, _ = parse_api_football_odds_response(
        _payload(_bet("Goal Line", 5, [("Over 1.5", "1.50"), ("Over 2.5", "2.50")])),
        requested_markets=[MARKET_OU],
    )
    assert rows == []


def test_result_total_goals_does_not_feed_main_over():
    rows, _ = parse_api_football_odds_response(
        _payload(_bet("Result/Total Goals", 10, [("Over 1.5", "1.50")])),
        requested_markets=[MARKET_OU],
    )
    assert rows == []


def test_total_home_does_not_feed_main_over():
    rows, _ = parse_api_football_odds_response(
        _payload(_bet("Total - Home", 16, [("Over 1.5", "1.50")])),
        requested_markets=[MARKET_OU],
    )
    assert rows == []


def test_first_half_market_feeds_over_pt():
    rows, _ = parse_api_football_odds_response(
        _payload(
            _bet(
                "Goals Over/Under First Half",
                6,
                [("Over 0.5", "1.40"), ("Over 1.5", "2.80")],
            ),
        ),
        requested_markets=[MARKET_OU_FH],
    )
    keys = {r["selection_key"] for r in rows}
    assert SEL_OVER_PT_0_5 in keys
    assert SEL_OVER_PT_1_5 in keys


def test_goal_line_first_half_does_not_feed_over_pt():
    rows, _ = parse_api_football_odds_response(
        _payload(_bet("Goal Line (1st Half)", 7, [("Over 0.5", "1.40")])),
        requested_markets=[MARKET_OU_FH],
    )
    assert rows == []


def test_rtg_h1_does_not_feed_over_pt():
    rows, _ = parse_api_football_odds_response(
        _payload(_bet("RTG_H1", 99, [("Over 0.5", "1.40")])),
        requested_markets=[MARKET_OU_FH],
    )
    assert rows == []


def test_full_match_average_from_visible_books_only():
    rows = []
    for bm in CECCHINO_BOOKMAKERS:
        bid = str(bm["provider_bookmaker_id"])
        vals = FIXTURE_1499460_FT[int(bid)]
        rows.extend(
            [
                _row(bid, "MATCH_WINNER_1X2", "HOME", 2.0),
                _row(bid, "MATCH_WINNER_1X2", "DRAW", 3.0),
                _row(bid, "MATCH_WINNER_1X2", "AWAY", 4.0),
                _row(bid, MARKET_OU, SEL_OVER_1_5, vals["over_15"]),
                _row(bid, MARKET_OU, SEL_OVER_2_5, vals["over_25"]),
            ],
        )
    _, avg, _, _ = build_bookmaker_structures(rows, bookmaker_defs=CECCHINO_BOOKMAKERS)
    assert avg[MARKET_OU][SEL_OVER_1_5] == 1.75
    assert avg[MARKET_OU][SEL_OVER_2_5] == 3.29


def test_first_half_average_from_visible_books_only():
    rows = [
        _row("8", "MATCH_WINNER_1X2", "HOME", 2.0),
        _row("8", "MATCH_WINNER_1X2", "DRAW", 3.0),
        _row("8", "MATCH_WINNER_1X2", "AWAY", 4.0),
        _row("8", MARKET_OU_FH, SEL_OVER_PT_0_5, 1.40),
        _row("3", "MATCH_WINNER_1X2", "HOME", 2.1),
        _row("3", "MATCH_WINNER_1X2", "DRAW", 3.1),
        _row("3", "MATCH_WINNER_1X2", "AWAY", 4.1),
        _row("3", MARKET_OU_FH, SEL_OVER_PT_0_5, 1.60),
    ]
    _, avg, _, status = build_bookmaker_structures(rows, bookmaker_defs=CECCHINO_BOOKMAKERS)
    assert status == "partial"
    assert avg[MARKET_OU_FH][SEL_OVER_PT_0_5] == 1.50
    assert avg[MARKET_OU_FH][SEL_OVER_PT_1_5] is None


def test_average_null_when_no_bookmaker_has_odds():
    rows = [
        _row("8", "MATCH_WINNER_1X2", "HOME", 2.0),
        _row("8", "MATCH_WINNER_1X2", "DRAW", 3.0),
        _row("8", "MATCH_WINNER_1X2", "AWAY", 4.0),
    ]
    _, avg, _, _ = build_bookmaker_structures(rows, bookmaker_defs=CECCHINO_BOOKMAKERS)
    assert avg[MARKET_OU][SEL_OVER_1_5] is None
    assert avg[MARKET_OU_FH][SEL_OVER_PT_0_5] is None


def _bookmaker_payload_with_ou(
    *,
    bet365_ou: dict[str, float] | None = None,
    betfair_ou: dict[str, float] | None = None,
    pinnacle_ou: dict[str, float] | None = None,
    bet365_ou_fh: dict[str, float] | None = None,
) -> dict:
    def _bm(name: str, ou: dict[str, float] | None, ou_fh: dict[str, float] | None = None) -> dict:
        if ou is None:
            return {"bookmaker_name": name, "status": "missing", "markets": {}}
        markets: dict = {
            "MATCH_WINNER_1X2": {"HOME": 2.0, "DRAW": 3.0, "AWAY": 4.0},
            MARKET_OU: ou,
        }
        if ou_fh:
            markets[MARKET_OU_FH] = ou_fh
        return {"bookmaker_name": name, "status": "available", "markets": markets}

    bookmakers = [
        _bm("Bet365", bet365_ou, bet365_ou_fh),
        _bm("Betfair", betfair_ou),
        _bm("Pinnacle", pinnacle_ou),
    ]
    available = [b for b in bookmakers if b["status"] == "available"]

    def _avg(mkt: str, sk: str) -> float | None:
        vals = [
            float(b["markets"][mkt][sk])
            for b in available
            if b["markets"].get(mkt, {}).get(sk) is not None
        ]
        return round(sum(vals) / len(vals), 2) if vals else None

    return {
        "status": "available" if len(available) == 3 else ("partial" if available else "not_available"),
        "bookmakers": bookmakers,
        "bookmaker_average": {
            "MATCH_WINNER_1X2": {"HOME": 2.0, "DRAW": 3.0, "AWAY": 4.0},
            MARKET_OU: {
                SEL_OVER_1_5: _avg(MARKET_OU, SEL_OVER_1_5),
                SEL_OVER_2_5: _avg(MARKET_OU, SEL_OVER_2_5),
            },
            MARKET_OU_FH: {
                SEL_OVER_PT_0_5: _avg(MARKET_OU_FH, SEL_OVER_PT_0_5),
                SEL_OVER_PT_1_5: _avg(MARKET_OU_FH, SEL_OVER_PT_1_5),
            },
        },
        "warnings": [],
    }


def test_kpi_panel_includes_over_pt_rows():
    payload = _bookmaker_payload_with_ou(
        bet365_ou={SEL_OVER_1_5: 1.4, SEL_OVER_2_5: 2.2},
        bet365_ou_fh={SEL_OVER_PT_0_5: 1.35, SEL_OVER_PT_1_5: 2.5},
    )
    panel = build_cecchino_kpi_panel(
        statistical={"status": "not_available"},
        final_odds={"status": "not_available"},
        bookmaker_payload=payload,
    )
    labels = [r["label"] for r in panel["rows"]]
    assert "OVER PT 0.5" in labels
    assert "OVER PT 1.5" in labels
    pt05 = next(r for r in panel["rows"] if r["label"] == "OVER PT 0.5")
    assert pt05["statistica"] is None
    assert pt05["cecchino"] is None
    assert pt05["book"] == 1.35
    assert pt05["media"] == 1.35
    assert pt05["edge"] is None


def test_kpi_over_edge_null_without_cecchino():
    payload = _bookmaker_payload_with_ou(
        bet365_ou={SEL_OVER_1_5: 1.4, SEL_OVER_2_5: 2.2},
    )
    panel = build_cecchino_kpi_panel(
        statistical={"status": "not_available"},
        final_odds={"status": "not_available"},
        bookmaker_payload=payload,
    )
    over_15 = next(r for r in panel["rows"] if r["label"] == "OVER 1.5")
    assert over_15["edge"] is None


def test_first_half_selection_helpers():
    assert normalize_first_half_over_under_selection("Over 0.5") == SEL_OVER_PT_0_5
    assert normalize_first_half_over_under_selection("Over 1.5") == SEL_OVER_PT_1_5
    assert normalize_over_under_selection("Over 1.5") == SEL_OVER_1_5


def test_raw_odds_service_strict_debug_rejects_goal_line():
    svc = ApiFootballFixtureRawOddsService()
    payload = _payload(
        _bet("Goal Line", 5, [("Over 1.5", "1.50"), ("Over 2.5", "2.50")]),
    )
    with patch.object(svc._client, "get_fixture_odds", return_value=payload):
        out = svc.run(provider_fixture_id=1499460, bookmaker_ids=[8])
    assert out["summary"]["over_1_5_found"] is False
    assert len(out["over_under_full_time_debug"]["rejected_from_markets"]) == 2


def test_raw_odds_service_strict_debug_accepts_goals_over_under():
    svc = ApiFootballFixtureRawOddsService()
    payload = _payload(
        _bet("Goals Over/Under", 5, [("Over 1.5", "1.80"), ("Over 2.5", "3.50")]),
    )
    with patch.object(svc._client, "get_fixture_odds", return_value=payload):
        out = svc.run(provider_fixture_id=1499460, bookmaker_ids=[8])
    assert out["summary"]["over_1_5_found"] is True
    assert out["over_under_full_time_debug"]["OVER_1_5"]["bet_id"] == "5"
    assert out["over_under_full_time_debug"]["OVER_1_5"]["raw_market_name"] == "Goals Over/Under"
