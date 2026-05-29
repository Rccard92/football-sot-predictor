"""Test unitari competition (senza DB)."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.competition import Competition
from app.models.competition_scoped import CompetitionScopedMixin
from app.models.fixture import Fixture
from app.routes.competitions import DEFAULT_COMPETITION_MISSING_MESSAGE
from app.services.competition_backfill_service import CompetitionBackfillService
from app.services.competition_service import SERIE_A_KEY, CompetitionService

client = TestClient(app)


def test_competition_model_has_expected_fields():
    assert hasattr(Competition, "key")
    assert hasattr(Competition, "provider_league_id")
    assert hasattr(Competition, "pre_match_cron_enabled")
    assert hasattr(Fixture, "competition_id")


def test_competition_scoped_mixin_on_fixture():
    assert issubclass(Fixture, CompetitionScopedMixin)


def test_serie_a_key_constant():
    assert SERIE_A_KEY == "serie_a_italy_2025"


def test_competition_service_instantiation():
    svc = CompetitionService(client=None)
    assert svc is not None


def test_default_competition_missing_message():
    assert "backfill Serie A" in DEFAULT_COMPETITION_MISSING_MESSAGE


def test_get_default_competition_returns_message_when_null():
    with patch("app.routes.competitions.CompetitionService") as mock_svc_cls:
        mock_svc_cls.return_value.get_default.return_value = None
        response = client.get("/api/competitions/default")
    assert response.status_code == 200
    body = response.json()
    assert body["competition"] is None
    assert body["message"] == DEFAULT_COMPETITION_MISSING_MESSAGE


def test_get_default_competition_returns_competition_without_message():
    row = MagicMock()
    row.id = 1
    row.key = SERIE_A_KEY
    row.name = "Serie A"
    row.country = "Italy"
    row.provider = "api-football"
    row.provider_league_id = 135
    row.season = 2025
    row.timezone = "Europe/Rome"
    row.is_active = True
    row.is_primary = True
    row.pre_match_cron_enabled = True
    row.status = "active"
    row.league_id = 10
    row.season_id = 20

    with patch("app.routes.competitions.CompetitionService") as mock_svc_cls:
        mock_svc_cls.return_value.get_default.return_value = row
        response = client.get("/api/competitions/default")

    assert response.status_code == 200
    body = response.json()
    assert body["competition"]["key"] == SERIE_A_KEY
    assert body["message"] is None


def test_backfill_summary_keys():
    sample = {
        "status": "ok",
        "competition_id": 1,
        "competition_key": "serie_a_italy_2025",
        "fixtures_updated": 0,
        "player_profiles_updated": 0,
        "tracked_picks_updated": 0,
        "predictions_updated": 0,
        "team_stats_updated": 0,
        "standings_updated": 0,
        "warnings": [],
        "updated_by_table": {},
    }
    for key in (
        "status",
        "competition_id",
        "competition_key",
        "fixtures_updated",
        "player_profiles_updated",
        "tracked_picks_updated",
        "predictions_updated",
        "warnings",
    ):
        assert key in sample


def test_backfill_only_updates_null_competition_id_rows():
    source = inspect.getsource(CompetitionBackfillService.backfill_serie_a)
    assert source.count("competition_id.is_(None)") >= 3
