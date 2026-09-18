"""Precaricamento Master Pattern: stessa funzione e stessa cache della prima scheda aperta, nessuna scrittura."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.cecchino_live import pattern_signals as ps


def test_warm_loads_every_model_and_never_commits(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)
    seen = []
    monkeypatch.setattr(ps, "load_winners", lambda session, model: seen.append((session, model)))
    ps.warm_winners_cache()
    assert seen == [(db, "V2"), (db, "V2.5"), (db, "V3")]
    db.commit.assert_not_called()
    db.close.assert_called_once()


def test_warm_continues_after_one_model_fails(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)
    seen = []

    def fake(session, model):
        seen.append(model)
        if model == "V2":
            raise RuntimeError("build mancante")

    monkeypatch.setattr(ps, "load_winners", fake)
    ps.warm_winners_cache()
    assert seen == ["V2", "V2.5", "V3"]
    db.close.assert_called_once()
