"""Ingestion availability-upcoming — solo injuries?fixture=."""

from unittest.mock import MagicMock, patch

from app.models.player_availability import SCOPE_FIXTURE_LEVEL
from app.services.availability.availability_league import SerieALeagueContext
from app.services.availability.availability_upcoming_ingestion import ingest_serie_a_availability_upcoming


@patch("app.services.availability.availability_upcoming_ingestion.upsert_fixture_injury_record")
@patch("app.services.availability.availability_upcoming_ingestion.deactivate_fixture_injuries")
@patch("app.services.availability.availability_upcoming_ingestion.ApiFootballClient")
@patch("app.services.availability.availability_upcoming_ingestion.resolve_serie_a_league_context")
@patch("app.services.availability.availability_upcoming_ingestion.IngestionService")
def test_upcoming_uses_only_fixture_api(
    mock_ing_cls,
    mock_ctx,
    mock_client_cls,
    mock_deactivate,
    mock_upsert,
):
    db = MagicMock()
    season_row = MagicMock()
    season_row.id = 1
    season_row.year = 2025
    mock_ing_cls.return_value._serie_a_season_row.return_value = season_row
    mock_ctx.return_value = SerieALeagueContext(
        league_internal_id=1,
        api_league_id=135,
        league_name="Serie A",
        season_row_id=1,
    )

    fx = MagicMock()
    fx.id = 371
    fx.api_fixture_id = 1378173
    fx.season_id = 1
    fx.kickoff_at = MagicMock()
    fx.kickoff_at.tzinfo = None
    fx.home_team = MagicMock()
    fx.home_team.name = "Lazio"
    fx.away_team = MagicMock()
    fx.away_team.name = "Pisa"

    with patch(
        "app.services.availability.availability_upcoming_ingestion._upcoming_fixtures",
        return_value=[fx],
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_injuries_by_fixture.return_value = [
            {
                "player": {"id": 99, "name": "Nicolò Rovella", "type": "Yellow Cards"},
                "team": {"id": 487, "name": "Lazio"},
                "fixture": {"id": 1378173, "date": "2025-05-17T15:00:00+00:00"},
            },
        ]
        mock_upsert.return_value = (MagicMock(record_scope=SCOPE_FIXTURE_LEVEL), True)
        mock_deactivate.return_value = 0

        summary = ingest_serie_a_availability_upcoming(
            db,
            2025,
            fixture_id=371,
            client=mock_client,
        )

    mock_client.get_injuries_by_fixture.assert_called_once_with(1378173)
    mock_client.get_injuries.assert_not_called()
    assert summary["records_saved"] == 1
    assert summary["api_calls"] == 1
    assert len(summary["fixtures_with_availability"]) == 1
