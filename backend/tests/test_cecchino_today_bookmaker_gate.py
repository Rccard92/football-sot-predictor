"""Test gate bookmaker Cecchino Today (Betfair-only)."""

from __future__ import annotations

from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER
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


def test_betfair_complete_passes():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    odds = {bid: _mock_1x2()}
    ok, snap, reason, blocking = verify_complete_1x2_odds(odds)
    assert ok
    assert reason is None
    assert blocking == []
    assert set(snap["bookmakers"].keys()) == {"Betfair"}
    assert "bookmaker_average" not in snap


def test_betfair_not_required_bet365():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    odds = {bid: _mock_1x2()}
    ok, _, _, blocking = verify_complete_1x2_odds(odds)
    assert ok
    assert not any("Bet365" in b for b in blocking)


def test_betfair_not_required_pinnacle():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    odds = {bid: _mock_1x2()}
    ok, _, _, blocking = verify_complete_1x2_odds(odds)
    assert ok
    assert not any("Pinnacle" in b for b in blocking)


def test_missing_betfair_excludes():
    ok, _, reason, blocking = verify_complete_1x2_odds({})
    assert not ok
    assert reason == "missing_bookmaker"
    assert any("missing_bookmaker:Betfair" in b for b in blocking)


def test_betfair_without_1x2_excludes():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
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
    ok, _, reason, blocking = verify_complete_1x2_odds({bid: partial})
    assert not ok
    assert reason == "missing_1x2_market"
    assert any("missing_selection:Betfair" in b for b in blocking)
