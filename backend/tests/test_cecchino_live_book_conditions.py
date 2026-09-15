"""Pattern accesi: segnala quelli con condizioni che usano la quota del bookmaker."""

from __future__ import annotations

from app.services.cecchino_live import pattern_signals


def test_annotate_book_conditions_per_model(monkeypatch):
    winners = [
        {"id": 1, "conditions": [{"column": "v3_vs_book", "value": "Q5"}, {"column": "forma", "value": "Q4"}]},
        {"id": 2, "conditions": [{"column": "equilibrio", "value": "alto"}]},
        {"id": 3, "conditions": [{"column": "quota", "value": "Q2"}]},
    ]
    monkeypatch.setattr(pattern_signals, "load_winners", lambda db, model: (1, winners, 1))
    block = {"active": [{"id": 1}, {"id": 2}, {"id": 3}]}
    pattern_signals.annotate_book_conditions(None, "V3", block)
    assert [p["uses_book"] for p in block["active"]] == [True, False, True]


def test_balance_f36_uses_book_only_in_v2(monkeypatch):
    winners = [{"id": 7, "conditions": [{"column": "balance_f36_class", "value": "balance"}]}]
    monkeypatch.setattr(pattern_signals, "load_winners", lambda db, model: (1, winners, 1))
    v2 = {"active": [{"id": 7}]}
    v25 = {"active": [{"id": 7}]}
    pattern_signals.annotate_book_conditions(None, "V2", v2)
    pattern_signals.annotate_book_conditions(None, "V2.5", v25)
    assert v2["active"][0]["uses_book"] is True
    assert v25["active"][0]["uses_book"] is False
