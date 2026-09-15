"""Osservazione live per modello: indice e pattern separati, giocate, profitto, accordo V2.5/V3."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.models.cecchino_live_prediction import LIVE_STATUS_SETTLED
from app.services.cecchino_live import observation_models as om
from app.services.cecchino_live import pattern_signals


def _pattern(pid, key, quota, uses_book=False):
    return {"id": pid, "target_type": "market", "target_key": key, "threshold": None, "direction": 1, "market_label": key,
            "quota_book": quota, "win_rate_pct": 55.0, "roi_pct": 6.0, "total_n": 80, "uses_book": uses_book}


def _row(model, fid, index_markets, active, won, day=date(2026, 9, 16), status=LIVE_STATUS_SETTLED):
    predictions = [k for k, m in index_markets.items() if m["score"] >= 70]
    return SimpleNamespace(
        model=model, today_fixture_id=fid, scan_date=day, status=status, country_name="Brasile", league_name="Serie B",
        home_team_name="A", away_team_name="B", kickoff=datetime(2026, 9, 16, 20, tzinfo=timezone.utc),
        modules_json={"purchasability_index": {"status": "ok", "markets": index_markets, "predictions": predictions},
                      "patterns": {"active": active}},
        result_json={"score": {"ft_home": 1, "ft_away": 0}, "markets": {k: {"won": v} for k, v in won.items()}},
    )


def test_overview_splits_index_and_patterns(monkeypatch):
    monkeypatch.setattr(pattern_signals, "annotate_book_conditions", lambda db, model, block: None)
    m = lambda score, quota: {"score": score, "quota": quota}
    rows = [
        _row("V2.5", 1, {"HOME": m(92, 2.0), "UNDER_2_5": m(75, 1.3), "AWAY": m(20, 4.0)},
             [_pattern(1, "HOME", 2.0), _pattern(2, "HOME", 2.0), _pattern(3, "OVER_2_5", 1.9, uses_book=True)],
             {"HOME": True, "UNDER_2_5": True, "AWAY": False, "OVER_2_5": False}),
        _row("V3", 1, {"HOME": m(95, 2.0), "AWAY": m(10, 4.0)}, [], {"HOME": True, "AWAY": False}),
    ]
    out = om.models_overview(None, rows, today=date(2026, 9, 17))
    v25 = out["models"]["V2.5"]
    # indice: 2 predizioni 70+, una sola giocabile (Under a 1,30)
    assert v25["index"]["all_predictions"]["plays"] == 2 and v25["index"]["plays"]["plays"] == 1
    assert v25["index"]["plays"]["roi_pct"] == 100.0 and v25["index"]["by_pattern"]["confermate"]["won"] == 1
    assert v25["index"]["top"]["90-100"]["plays"] == 1
    # pattern: due pattern sul 1 = un segnale; quello con condizione sulla quota resta a parte
    assert v25["patterns"]["plays"]["plays"] == 1 and v25["patterns"]["with_book_conditions"]["plays"] == 1
    assert v25["patterns"]["concordance"][1]["plays"] == 1
    assert v25["daily"][0]["cumulative_index_profit"] == 1.0 and len(v25["daily"][0]["fixtures"]) == 1
    assert out["agreement"]["entrambi_90+"]["plays"] == 1 and out["agreement"]["entrambi_90+"]["won"] == 1
    assert v25["index"]["plays"]["sample"] == "presto per dirlo"


def test_pending_rows_do_not_count_as_closed(monkeypatch):
    monkeypatch.setattr(pattern_signals, "annotate_book_conditions", lambda db, model, block: None)
    row = _row("V3", 2, {"DRAW": {"score": 80, "quota": 3.2}}, [], {}, status="open")
    out = om.models_overview(None, [row], today=date(2026, 9, 17))["models"]["V3"]["index"]["plays"]
    assert out["plays"] == 1 and out["pending"] == 1 and out["closed"] == 0 and out["roi_pct"] is None
