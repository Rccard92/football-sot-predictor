"""Ingestion lineups — mock API, no predictions_v11 import."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.lineups import lineup_ingestion as li_mod


def test_ingestion_module_no_predictions_v11_import():
    import importlib

    mod = importlib.import_module("app.services.lineups.lineup_ingestion")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "predictions_v11" not in src
    assert "sot_fixture_explanation" not in src


def test_empty_api_response_not_available_yet():
    db = MagicMock()
    season_row = SimpleNamespace(id=1, year=2025, league_id=10)
    fx = SimpleNamespace(
        id=99,
        api_fixture_id=1001,
        season_id=1,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=datetime.now(timezone.utc),
        status="NS",
    )
    ing = MagicMock()
    ing._serie_a_season_row.return_value = season_row

    client = MagicMock()
    client.get_fixture_lineups.return_value = []

    with (
        patch.object(li_mod, "IngestionService", return_value=ing),
        patch.object(li_mod, "_select_fixtures_for_ingestion", return_value=[fx]),
        patch.object(li_mod, "_fixture_has_both_lineups_available", return_value=False),
    ):
        summary = li_mod.ingest_serie_a_lineups(db, 2025, client=client)

    assert summary["fixtures_checked"] == 1
    assert summary["fixtures_without_lineups"] == 1
    assert len(summary["not_available_yet"]) == 1


def test_skip_when_lineups_already_available_and_not_force():
    db = MagicMock()
    season_row = SimpleNamespace(id=1, year=2025, league_id=10)
    fx = SimpleNamespace(id=1, api_fixture_id=1, status="NS", kickoff_at=datetime.now(timezone.utc))

    ing = MagicMock()
    ing._serie_a_season_row.return_value = season_row
    client = MagicMock()

    with (
        patch.object(li_mod, "IngestionService", return_value=ing),
        patch.object(li_mod, "_select_fixtures_for_ingestion", return_value=[fx]),
        patch.object(li_mod, "_fixture_has_both_lineups_available", return_value=True),
    ):
        summary = li_mod.ingest_serie_a_lineups(db, 2025, force=False, client=client)

    client.get_fixture_lineups.assert_not_called()
    assert summary["fixtures_checked"] == 1
    assert summary["lineups_upserted"] == 0
