"""Test gate bookmaker Cecchino Today."""

from __future__ import annotations

from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS
from app.services.cecchino.cecchino_today_bookmaker_gate import verify_complete_1x2_odds


def _mock_1x2(h: float = 2.0, d: float = 3.2, a: float = 3.8) -> list[dict]:
    return [
        {
            "bookmakers": [
                {
                    "bets": [
                        {
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": str(h)},
                                {"value": "Draw", "odd": str(d)},
                                {"value": "Away", "odd": str(a)},
                            ],
                        },
                    ],
                },
            ],
        },
    ]


def test_all_three_bookmakers_complete():
    odds = {int(b["provider_bookmaker_id"]): _mock_1x2() for b in CECCHINO_BOOKMAKERS}
    ok, snap, reason = verify_complete_1x2_odds(odds)
    assert ok
    assert reason is None
    assert set(snap["bookmakers"].keys()) == {"Bet365", "Betfair", "Pinnacle"}


def test_missing_pinnacle():
    ids = [int(b["provider_bookmaker_id"]) for b in CECCHINO_BOOKMAKERS]
    odds = {ids[0]: _mock_1x2(), ids[1]: _mock_1x2()}
    ok, _, reason = verify_complete_1x2_odds(odds)
    assert not ok
    assert reason == "missing_1x2_market"


def test_missing_all_bookmakers():
    ok, _, reason = verify_complete_1x2_odds({})
    assert not ok
    assert reason == "missing_bookmaker"


def test_incomplete_1x2_market():
    ids = [int(b["provider_bookmaker_id"]) for b in CECCHINO_BOOKMAKERS]
    partial = [
        {
            "bookmakers": [
                {
                    "bets": [
                        {
                            "name": "Match Winner",
                            "values": [{"value": "Home", "odd": "2.0"}],
                        },
                    ],
                },
            ],
        },
    ]
    odds = {bid: partial for bid in ids}
    ok, _, reason = verify_complete_1x2_odds(odds)
    assert not ok
    assert reason == "missing_1x2_market"
