"""Test orchestrator provider layer."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.availability.providers.api_football_injuries_provider import (
    ApiFootballInjuriesProvider,
)
from app.services.availability.providers.api_football_sidelined_provider import (
    ApiFootballSidelinedProvider,
)
from app.services.availability.providers.availability_provider_orchestrator import (
    run_availability_upcoming_orchestrator,
)
from app.services.availability.providers.base import ProviderFetchResult, PROVIDER_INJURIES, PROVIDER_SIDELINED
from app.services.availability.providers.types import NormalizedAvailabilityCandidate
from app.models.player_availability import SCOPE_FIXTURE_LEVEL


def _injury_candidate(api_fx: int) -> NormalizedAvailabilityCandidate:
    return NormalizedAvailabilityCandidate(
        fixture_id=375,
        api_fixture_id=api_fx,
        season=2025,
        league_id=1,
        api_league_id=135,
        team_id=10,
        api_team_id=487,
        team_name="Fiorentina",
        player_id=None,
        api_player_id=1,
        player_name="Player",
        availability_status="injured",
        availability_type="injury",
        reason="test",
        source="api_football_injuries",
        source_detail="api_football_injuries_fixture_direct",
        record_scope=SCOPE_FIXTURE_LEVEL,
        confidence="HIGH",
        applicability_status="applied",
        applicability_reason="injuries_fixture_level_match",
    )


def _low_sidelined(api_fx: int) -> NormalizedAvailabilityCandidate:
    return NormalizedAvailabilityCandidate(
        fixture_id=375,
        api_fixture_id=api_fx,
        season=2025,
        league_id=1,
        api_league_id=135,
        team_id=10,
        api_team_id=487,
        team_name="Fiorentina",
        player_id=None,
        api_player_id=2,
        player_name="Low",
        availability_status="injured",
        availability_type="injury",
        reason="x",
        source="api_football_sidelined",
        source_detail="api_football_sidelined_player",
        record_scope="",
        confidence="LOW",
        applicability_status="not_applied",
        applicability_reason="missing_date_window",
    )


@patch("app.services.availability.providers.availability_provider_orchestrator.persist_availability_upcoming_run")
@patch("app.services.availability.providers.availability_provider_orchestrator.upsert_availability_candidate")
@patch("app.services.availability.providers.availability_provider_orchestrator.ApiFootballSidelinedProvider")
@patch("app.services.availability.providers.availability_provider_orchestrator.ApiFootballInjuriesProvider")
@patch("app.services.availability.providers.availability_provider_orchestrator.resolve_serie_a_league_context")
@patch("app.services.availability.providers.availability_provider_orchestrator.resolve_upcoming_fixtures")
@patch("app.services.availability.providers.availability_provider_orchestrator.IngestionService")
def test_orchestrator_persists_only_applied(
    mock_ing_cls,
    mock_upcoming,
    mock_ctx,
    mock_inj_cls,
    mock_side_cls,
    mock_upsert,
    mock_persist,
):
    db = MagicMock()
    season_row = MagicMock()
    season_row.id = 1
    mock_ing_cls.return_value._serie_a_season_row.return_value = season_row
    mock_ctx.return_value = MagicMock(league_internal_id=1, api_league_id=135)

    fx = MagicMock()
    fx.id = 375
    fx.api_fixture_id = 1378236
    fx.kickoff_at = datetime(2025, 5, 20, 18, 0, tzinfo=timezone.utc)
    fx.home_team = MagicMock(name="Fiorentina", api_team_id=487, id=10)
    fx.away_team = MagicMock(name="Atalanta", api_team_id=499, id=11)
    mock_upcoming.return_value = [fx]

    inj = MagicMock(spec=ApiFootballInjuriesProvider)
    inj.fetch_candidates.return_value = ProviderFetchResult(
        provider_name=PROVIDER_INJURIES,
        called=True,
        candidates=[_injury_candidate(1378236)],
    )
    mock_inj_cls.return_value = inj

    side = MagicMock(spec=ApiFootballSidelinedProvider)
    side.fetch_candidates.return_value = ProviderFetchResult(
        provider_name=PROVIDER_SIDELINED,
        called=True,
        candidates=[_low_sidelined(1378236)],
        players_checked=2,
    )
    mock_side_cls.return_value = side

    mock_upsert.return_value = (MagicMock(), True, True)

    summary = run_availability_upcoming_orchestrator(db, 2025, client=MagicMock())

    assert mock_upsert.call_count == 1
    assert summary["records_saved"] == 1
    assert summary["providers"]["api_football_injuries"]["applicable_saved"] == 1
    assert summary["providers"]["api_football_sidelined"]["candidate_not_applied"] == 1
    per_fx = summary["per_fixture"]["1378236"]
    assert len(per_fx["candidates_applied"]) == 1
    assert len(per_fx["candidates_not_applied"]) == 1
    mock_persist.assert_called_once()
