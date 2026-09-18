"""Cron formazioni Cecchino: nessuna partita in finestra = nessuna chiamata; assenti salvati per lato."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cecchino_live import prematch_lineups as pl


def test_no_fixtures_in_window_makes_no_api_calls(monkeypatch):
    monkeypatch.setattr(pl, "target_fixtures", lambda db, now, lookahead=None: [])
    client = MagicMock()
    out = pl.run_prematch_lineups(MagicMock(), client=client)
    assert out["fixtures_in_window"] == 0 and out["calls"] == 0
    client.get.assert_not_called()


def test_store_injuries_maps_team_side_and_skips_other_teams():
    fixture = SimpleNamespace(id=10, home_team_id=1, away_team_id=2, competition_id=7)
    teams = {1: SimpleNamespace(api_team_id=501), 2: SimpleNamespace(api_team_id=502)}
    added = []
    db = MagicMock()
    db.get.side_effect = lambda model, pk: teams.get(pk)
    db.scalar.return_value = None
    db.add.side_effect = added.append
    items = [
        {"player": {"id": 9, "name": "Rossi", "type": "Missing Fixture", "reason": "Injury"}, "team": {"id": 502}},
        {"player": {"id": 8, "name": "Bianchi", "type": "Questionable", "reason": "Knock"}, "team": {"id": 999}},
        {"player": {"id": 9, "name": "Rossi", "type": "Missing Fixture", "reason": "Injury"}, "team": {"id": 502}},
    ]
    assert pl.store_injuries(db, fixture, items) == 1
    row = added[0]
    assert row.team_side == "away" and row.provider_name == "api_football"
    assert row.external_type == "Missing Fixture" and row.reason == "Injury"


def test_job_paused_makes_no_db_or_api_work(monkeypatch):
    from app.jobs import cecchino_prematch_lineups as job

    monkeypatch.setattr(job, "get_settings", lambda: SimpleNamespace(cecchino_prematch_lineups_enabled=False))
    session = MagicMock(side_effect=AssertionError("database aperto con il cron in pausa"))
    monkeypatch.setattr(job, "SessionLocal", session)
    run = MagicMock()
    monkeypatch.setattr(job, "run_prematch_lineups", run)
    assert job.main([]) == 0
    run.assert_not_called()
