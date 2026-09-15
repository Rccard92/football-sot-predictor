"""Osservazione live: predizioni dell'indice divise per conferma dei pattern."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.cecchino_live_prediction import LIVE_STATUS_SETTLED
from app.services.cecchino_live import observation, pattern_signals


def _row(predictions, markets, active, won):
    return SimpleNamespace(
        model="V2.5",
        status=LIVE_STATUS_SETTLED,
        modules_json={
            "purchasability_index": {"status": "ok", "predictions": predictions, "markets": markets},
            "patterns": {"active": active},
        },
        result_json={"markets": {k: {"won": v} for k, v in won.items()}},
    )


def test_index_observation_buckets_and_roi(monkeypatch):
    def fake_annotate(db, model, block):
        for p in block["active"]:
            p["uses_book"] = p.get("id") == 99

    monkeypatch.setattr(pattern_signals, "annotate_book_conditions", fake_annotate)
    m = lambda score, quota, playable=True: {"score": score, "quota": quota, "playable": playable}
    rows = [
        # X confermata dal pattern, Over 2.5 in contrasto con un pattern Under 2.5
        _row(["DRAW", "OVER_2_5"], {"DRAW": m(85, 3.0), "OVER_2_5": m(72, 1.8)},
             [{"id": 1, "target_type": "market", "target_key": "DRAW"}, {"id": 2, "target_type": "market", "target_key": "UNDER_2_5"}],
             {"DRAW": True, "OVER_2_5": False}),
        # pattern che usa la quota: non conta, la predizione resta senza pattern
        _row(["HOME"], {"HOME": m(91, 1.4, playable=False)}, [{"id": 99, "target_type": "market", "target_key": "HOME"}], {"HOME": True}),
    ]
    out = observation.index_observation(None, rows)["V2.5"]
    assert out["fixtures"] == 2 and out["all"]["predictions"] == 3 and out["all"]["won"] == 2
    assert out["by_pattern"]["confermate"]["won"] == 1 and out["by_pattern"]["confermate"]["roi_pct"] == 200.0
    assert out["by_pattern"]["in_contrasto"]["lost"] == 1 and out["by_pattern"]["in_contrasto"]["roi_pct"] == -100.0
    assert out["by_pattern"]["senza_pattern"]["won"] == 1 and out["by_pattern"]["senza_pattern"]["playable"] == 0
    assert out["by_score"]["90 e oltre"]["predictions"] == 1


def test_markets_conflict_rules():
    assert observation.markets_conflict("OVER_2_5", "UNDER_2_5")
    assert not observation.markets_conflict("OVER_2_5", "UNDER_3_5")
    assert observation.markets_conflict("HOME", "X_TWO")
    assert not observation.markets_conflict("HOME_PT", "AWAY")
