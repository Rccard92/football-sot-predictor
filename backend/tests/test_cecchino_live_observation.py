"""Osservazione live: gruppi di pattern per mercato, esiti, precisione motori con riferimento Bet365."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cecchino_live.observation import (
    BOOK_REFERENCE,
    book_fair_probabilities,
    group_active_patterns,
    group_outcome,
    observation_dashboard,
)


def _p(pid, key, threshold=None, direction=1, ttype="synthetic", win=60.0, roi=None, dev=5.0, n=100):
    return {
        "id": pid, "target_type": ttype, "target_key": key, "threshold": threshold, "direction": direction,
        "market_label": f"{key} {threshold}", "conditions_text": "c", "total_n": n,
        "win_rate_pct": win, "roi_pct": roi, "avg_deviation_pct": dev, "quota_book": 1.9 if ttype == "market" else None,
    }


def test_group_active_patterns_merges_same_market_line_direction():
    active = [
        _p(1, "total_sot", 9.5), _p(2, "total_sot", 9.5, win=70.0), _p(3, "total_sot", 9.5, direction=-1),
        _p(4, "DRAW", ttype="market", roi=12.0), _p(5, "DRAW", ttype="market", roi=4.0),
    ]
    groups = group_active_patterns(active)
    assert [g["patterns_count"] for g in groups] == [2, 2, 1]
    draw = groups[0]
    assert draw["target_key"] == "DRAW" and draw["hist_roi_pct_best"] == 12.0
    sot_over = next(g for g in groups if g["target_key"] == "total_sot" and g["direction"] == 1)
    assert sot_over["pattern_ids"] == [1, 2] and sot_over["hist_win_rate_pct"] == 65.0


def _pred(fid, model, *, scan_date=date(2026, 9, 14), status="settled", probs=None, quotas=None, won=None, active=None, pattern_results=None):
    markets = {k: {"probability": v, "quota_book": (quotas or {}).get(k)} for k, v in (probs or {}).items()}
    res = {"markets": {k: {"won": w, "profit": (((quotas or {}).get(k) or 0) - 1) if w else -1.0} for k, w in (won or {}).items()},
           "patterns": pattern_results or {}}
    return SimpleNamespace(
        id=fid * 10 + (1 if model == "V2" else 2), today_fixture_id=fid, scan_date=scan_date, model=model, status=status,
        markets_json=markets, modules_json={"patterns": {"active": active or []}}, result_json=res if status == "settled" else None,
    )


def test_group_outcome_market_and_synthetic():
    g_market = group_active_patterns([_p(4, "DRAW", ttype="market")])[0]
    g_syn = group_active_patterns([_p(1, "total_sot", 9.5), _p(2, "total_sot", 9.5)])[0]
    pred = _pred(1, "V2.5", probs={"DRAW": 0.3}, quotas={"DRAW": 3.4}, won={"DRAW": True},
                 pattern_results={"2": {"won": False, "actual": 8.0}})
    assert group_outcome(pred, g_market) == {"won": True, "profit": 2.4}
    assert group_outcome(pred, g_syn)["won"] is False


def test_book_fair_probabilities_needs_full_family():
    pred = _pred(1, "V2.5", probs={"HOME": 0.5, "DRAW": 0.3, "AWAY": 0.2}, quotas={"HOME": 2.0, "DRAW": 3.5, "AWAY": 4.0})
    fair = book_fair_probabilities(pred, ("HOME", "DRAW", "AWAY"))
    assert abs(sum(fair.values()) - 1.0) < 1e-9 and fair["HOME"] > fair["AWAY"]
    pred.markets_json["AWAY"]["quota_book"] = None
    assert book_fair_probabilities(pred, ("HOME", "DRAW", "AWAY")) is None


def test_observation_dashboard_common_fixtures_and_patterns():
    probs = {"HOME": 0.6, "DRAW": 0.25, "AWAY": 0.15, "OVER_2_5": 0.55, "UNDER_2_5": 0.45}
    quotas = {"HOME": 1.8, "DRAW": 3.6, "AWAY": 5.0, "OVER_2_5": 1.9, "UNDER_2_5": 1.9}
    won = {"HOME": True, "DRAW": False, "AWAY": False, "OVER_2_5": False, "UNDER_2_5": True}
    active = [_p(1, "total_sot", 9.5), _p(2, "total_sot", 9.5), _p(4, "HOME", ttype="market", roi=8.0)]
    rows = [
        _pred(1, "V2", probs=probs, quotas=quotas, won=won),
        _pred(1, "V2.5", probs=probs, quotas=quotas, won=won, active=active, pattern_results={"1": {"won": True, "actual": 11}}),
        _pred(2, "V2.5", probs=probs, quotas=quotas, won=won),  # solo V2.5: fuori dal confronto comune
        _pred(3, "V2.5", status="open", probs=probs, active=[_p(1, "total_sot", 9.5)]),
    ]
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    out = observation_dashboard(db)
    assert out["models"] == ["V2", "V2.5"]
    assert out["totals"]["common_fixtures"] == 1
    assert out["engines"]["V2.5"]["1X2"]["favourite_hit_pct"] == 100.0
    assert out["engines"][BOOK_REFERENCE]["1X2"]["fixtures"] == 1
    assert out["engines"]["V2"]["Over/Under 2.5"]["favourite_hit_pct"] == 0.0
    sot = next(g for g in out["pattern_groups"] if g["target_key"] == "total_sot")
    assert sot["signals"] == 2 and sot["won"] == 1 and sot["pending"] == 1 and sot["avg_patterns"] == 1.5
    home = next(g for g in out["pattern_groups"] if g["target_key"] == "HOME")
    assert home["won"] == 1 and home["roi_pct"] == 80.0
    band = {b["band"]: b for b in out["concordance"]}
    assert band["2-4 pattern"]["won"] == 1 and band["1 pattern"]["won"] == 1
    assert out["days"][0]["fixtures"] == 3 and out["days"][0]["groups_pending"] == 1
    assert len(out["engines_daily"]) == 1 and out["engines_daily"][0]["cumulative_fixtures"] == 1
