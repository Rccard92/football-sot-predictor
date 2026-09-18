"""Bet Builder V3: opportunita' per modello dal registro live, conferma pattern, Combo V2.5+V3."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.cecchino_live import bet_builder_v3 as bb


def _pred(model, markets, patterns=(), status="open", results=None):
    return SimpleNamespace(
        model=model,
        status=status,
        frozen_at=datetime(2026, 9, 18, 8, tzinfo=timezone.utc),
        modules_json={
            "purchasability_index": {"status": "ok", "markets": markets},
            "patterns": {"active": list(patterns)},
        },
        result_json={"markets": results or {}},
    )


def _pattern(pid, key, uses_book=False, win=60.0, roi=8.0):
    return {
        "id": pid,
        "target_type": "market",
        "target_key": key,
        "threshold": None,
        "direction": 1,
        "market_label": key,
        "quota_book": 2.0,
        "win_rate_pct": win,
        "roi_pct": roi,
        "total_n": 80,
        "uses_book": uses_book,
    }


@pytest.fixture(autouse=True)
def _no_db_annotation(monkeypatch):
    monkeypatch.setattr(bb, "_annotated_patterns", lambda db, pred: pred.modules_json["patterns"]["active"])


def _m(score, quota, p=0.5):
    return {"score": score, "quota": quota, "probability": p, "base_rate": 0.4, "min_quota": round(1 / p, 4)}


def test_only_70_plus_are_opportunities_sorted_and_playable_flag():
    block = bb._model_block(None, _pred("V2.5", {"HOME": _m(82, 1.9), "DRAW": _m(69.9, 3.4), "OVER_2_5": _m(75, 1.35)}))
    assert [p["market_key"] for p in block["predictions"]] == ["HOME", "OVER_2_5"]
    assert block["predictions"][0]["playable"] is True
    assert block["predictions"][1]["playable"] is False  # quota sotto 1,50


def test_pattern_relation_confirmed_conflict_and_book_patterns_ignored():
    pred = _pred(
        "V3",
        {"HOME": _m(80, 2.0), "UNDER_2_5": _m(74, 1.8)},
        patterns=[_pattern(1, "HOME"), _pattern(2, "OVER_2_5"), _pattern(3, "UNDER_2_5", uses_book=True)],
    )
    rel = {p["market_key"]: p["pattern"] for p in bb._model_block(None, pred)["predictions"]}
    assert rel == {"HOME": "confermata", "UNDER_2_5": "in_contrasto"}


def test_won_only_when_settled():
    open_block = bb._model_block(None, _pred("V2.5", {"HOME": _m(80, 2.0)}, results={"HOME": {"won": True}}))
    settled = bb._model_block(
        None, _pred("V2.5", {"HOME": _m(80, 2.0)}, status="settled", results={"HOME": {"won": True}})
    )
    assert open_block["predictions"][0]["won"] is None
    assert settled["predictions"][0]["won"] is True


def test_combo_same_market_both_models_without_conflicting_patterns():
    v25 = bb._model_block(None, _pred("V2.5", {"HOME": _m(85, 2.1), "OVER_2_5": _m(78, 1.9)}))
    v3 = bb._model_block(
        None, _pred("V3", {"HOME": _m(72, 2.0), "OVER_2_5": _m(90, 1.85)}, patterns=[_pattern(9, "UNDER_2_5")])
    )
    combo = bb._combo(v25, v3)
    assert [c["market_key"] for c in combo] == ["HOME"]  # OVER_2_5 escluso: pattern V3 su Under 2.5
    assert combo[0]["score"] == 72  # il piu' prudente dei due
    assert combo[0]["quota"] == 2.0  # quota V3


def test_combo_empty_when_a_model_is_missing():
    v25 = bb._model_block(None, _pred("V2.5", {"HOME": _m(85, 2.1)}))
    assert bb._combo(v25, None) == []
