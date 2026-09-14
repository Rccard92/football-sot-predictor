"""Test collegamento dati: linee Bet365 solo a .5, soglia quote Bet365, esiti pattern senza quota."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.cecchino.cecchino_today_final_eligibility import check_primary_book_core_odds
from app.services.cecchino_live.bet365_lines import bet365_block_from_snapshot, extract_half_lines, is_half_line
from app.services.cecchino_live.registry import _synthetic_pattern_outcomes


def test_half_lines_only():
    assert is_half_line(Decimal("9.5"))
    assert is_half_line(Decimal("0.5"))
    assert not is_half_line(Decimal("10"))
    assert not is_half_line(Decimal("9.25"))


def test_extract_half_lines_skips_whole_and_quarter_lines():
    block = {
        "id": 8,
        "bets": [
            {"name": "Corners Over Under", "values": [
                {"value": "Over 9.5", "odd": "1.73"}, {"value": "Under 9.5", "odd": "2.00"},
                {"value": "Over 10", "odd": "1.95"}, {"value": "Under 10", "odd": "1.85"},
            ]},
            {"name": "Total ShotOnGoal", "values": [{"value": "Over 8.5", "odd": "1.83"}, {"value": "Under 8.5", "odd": "1.83"}]},
            {"name": "Goal Line", "values": [{"value": "Over 2.25", "odd": "1.9"}]},
            {"name": "Exact Score", "values": [{"value": "1:0", "odd": "7"}]},
        ],
    }
    lines = extract_half_lines(block)
    assert [(l["market_key"], l["line"]) for l in lines] == [("corners_total", Decimal("9.5")), ("shots_on_target_total", Decimal("8.5"))]
    assert lines[0]["over_odd"] == Decimal("1.73") and lines[0]["under_odd"] == Decimal("2.00")


def test_bet365_block_from_snapshot():
    snap = {"raw_by_bookmaker_id": {"8": [{"update": "2026-09-14T12:57:29+00:00", "bookmakers": [{"id": 8, "bets": []}]}]}}
    block, updated = bet365_block_from_snapshot(snap)
    assert block is not None and updated.startswith("2026-09-14")
    assert bet365_block_from_snapshot({"raw_by_bookmaker_id": {"3": []}}) == (None, None)


def _row(key, quota, name="Bet365", **kw):
    return {"market_key": key, "quota_book": quota, "bookmaker_name": name, **kw}


def test_core_odds_threshold_requires_real_bet365_1x2_and_ou25():
    ok = {"rows": [_row("HOME", 2.0), _row("DRAW", 3.4), _row("AWAY", 3.8), _row("OVER_2_5", 1.9), _row("UNDER_2_5", 1.9)]}
    assert check_primary_book_core_odds(ok) == []
    fallback = {"rows": ok["rows"][:3] + [_row("OVER_2_5", 1.9, "Betfair", book_fallback_used=True), _row("UNDER_2_5", 1.9)]}
    assert check_primary_book_core_odds(fallback) == ["OVER_2_5"]
    missing = {"rows": ok["rows"][:3]}
    assert check_primary_book_core_odds(missing) == ["OVER_2_5", "UNDER_2_5"]


def test_synthetic_pattern_outcomes_follow_direction():
    pred = SimpleNamespace(modules_json={"patterns": {"active": [
        {"id": 1, "target_type": "synthetic", "target_key": "total_sot", "threshold": 9.5, "direction": 1},
        {"id": 2, "target_type": "synthetic", "target_key": "total_corners", "threshold": 10.5, "direction": -1},
        {"id": 3, "target_type": "market", "target_key": "DRAW", "threshold": None, "direction": 1},
    ]}})
    out = _synthetic_pattern_outcomes(pred, {"total_sot": 11.0, "total_corners": 12.0})
    assert out["1"]["won"] is True
    assert out["2"]["won"] is False
    assert "3" not in out
    assert _synthetic_pattern_outcomes(pred, None)["1"]["won"] is None
