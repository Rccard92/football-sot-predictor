"""Ingestion availability-upcoming — multi-source."""

from unittest.mock import MagicMock, patch

from app.models.player_availability import SCOPE_FIXTURE_LEVEL
from app.services.availability.availability_injuries_sources import (
    InjuriesFetchResult,
    SourceFetchStats,
)
from app.services.availability.availability_league import SerieALeagueContext
from app.services.availability.availability_upcoming_ingestion import ingest_serie_a_availability_upcoming


def _item(api_fx: int) -> dict:
    return {
        "player": {"id": 99, "name": "Nicolò Rovella", "type": "Yellow Cards"},
        "team": {"id": 487, "name": "Lazio"},
        "fixture": {"id": api_fx, "date": "2025-05-17T15:00:00+00:00"},
    }


@patch("app.services.availability.availability_upcoming_ingestion.persist_availability_upcoming_run")
@patch("app.services.availability.availability_upcoming_ingestion.upsert_fixture_injury_record")
@patch("app.services.availability.availability_upcoming_ingestion.fetch_injuries_multi_source")
@patch("app.services.availability.availability_upcoming_ingestion.resolve_serie_a_league_context")
@patch("app.services.availability.availability_upcoming_ingestion.IngestionService")
def test_upcoming_multisource_saves_fixture_level(
    mock_ing_cls,
    mock_ctx,
    mock_fetch,
    mock_upsert,
    mock_persist_run,
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

    fetch_result = InjuriesFetchResult(
        sources={
            "ids_batch": SourceFetchStats(called=True, results_total=0, records_matching_upcoming=0),
            "league_season_filtered": SourceFetchStats(
                called=True,
                results_total=2857,
                records_matching_upcoming=1,
            ),
            "fixture_direct": SourceFetchStats(called=True, results_total=0, records_matching_upcoming=0),
        },
        merged_items=[(_item(1378173), "api_football_injuries_league_season_filtered")],
        api_calls=12,
    )
    mock_fetch.return_value = fetch_result

    with patch(
        "app.services.availability.availability_upcoming_ingestion._upcoming_fixtures",
        return_value=[fx],
    ):
        mock_upsert.return_value = (MagicMock(record_scope=SCOPE_FIXTURE_LEVEL), True, True)
        summary = ingest_serie_a_availability_upcoming(
            db,
            2025,
            fixture_id=371,
            client=MagicMock(),
        )

    mock_fetch.assert_called_once()
    mock_upsert.assert_called_once()
    call_kw = mock_upsert.call_args.kwargs
    assert call_kw["source_detail"] == "api_football_injuries_league_season_filtered"
    assert summary["records_saved"] == 1
    assert summary["sources"]["league_season_filtered"]["records_matching_upcoming"] == 1
    assert summary["upcoming_api_fixture_ids"] == [1378173]
    assert summary["provider_future_availability_coverage"] == "ok"
    mock_persist_run.assert_called_once()


@patch("app.services.availability.availability_upcoming_ingestion.persist_availability_upcoming_run")
@patch("app.services.availability.availability_upcoming_ingestion.fetch_injuries_multi_source")
@patch("app.services.availability.availability_upcoming_ingestion.resolve_serie_a_league_context")
@patch("app.services.availability.availability_upcoming_ingestion.IngestionService")
def test_upcoming_empty_coverage_warning(mock_ing_cls, mock_ctx, mock_fetch, mock_persist):
    db = MagicMock()
    season_row = MagicMock()
    season_row.id = 1
    season_row.year = 2025
    mock_ing_cls.return_value._serie_a_season_row.return_value = season_row
    mock_ctx.return_value = SerieALeagueContext(1, 135, "Serie A", 1)

    fx = MagicMock()
    fx.id = 1
    fx.api_fixture_id = 100
    fx.home_team = MagicMock(name="A")
    fx.away_team = MagicMock(name="B")

    mock_fetch.return_value = InjuriesFetchResult(
        sources={
            "ids_batch": SourceFetchStats(called=True, results_total=0, records_matching_upcoming=0),
            "league_season_filtered": SourceFetchStats(
                called=True,
                results_total=100,
                records_matching_upcoming=0,
            ),
            "fixture_direct": SourceFetchStats(called=True, results_total=0, records_matching_upcoming=0),
        },
        merged_items=[],
        api_calls=5,
    )

    with patch(
        "app.services.availability.availability_upcoming_ingestion._upcoming_fixtures",
        return_value=[fx],
    ):
        summary = ingest_serie_a_availability_upcoming(db, 2025, client=MagicMock())

    assert summary["provider_future_availability_coverage"] == "empty"
    assert len(summary["warnings"]) >= 1
