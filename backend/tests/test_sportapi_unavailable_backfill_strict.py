"""Test backfill unavailable strict + stagione (Step K.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models import Competition, Fixture, Team
from app.schemas.backtest_point_in_time import BacktestFixtureCandidate, BacktestFixtureTeamBrief
from app.services.backtest.backtest_fixture_debug_service import SeasonBackfillSelection
from app.services.sportapi.sportapi_unavailable_backfill_service import SportApiUnavailableBackfillService
from app.services.sportapi.sportapi_unavailable_season_backfill_service import (
    SportApiUnavailableSeasonBackfillService,
)


@patch("app.services.sportapi.sportapi_unavailable_backfill_service.BacktestFixtureDebugService")
def test_unavailable_backfill_strict_skips_without_mapping(mock_fixture_svc_cls):
    kickoff = datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc)
    candidate = BacktestFixtureCandidate(
        fixture_id=359,
        kickoff_at=kickoff,
        status="FT",
        home_team=BacktestFixtureTeamBrief(id=10, name="Milan"),
        away_team=BacktestFixtureTeamBrief(id=20, name="Atalanta"),
        has_team_stats=True,
    )
    mock_fixture_svc_cls.return_value.select_fixtures_for_mini_run.return_value = MagicMock(
        items=[candidate],
    )

    comp = MagicMock(spec=Competition)
    comp.id = 1
    comp.name = "Serie A"
    fixture = MagicMock(spec=Fixture)
    fixture.id = 359
    fixture.competition_id = 1
    fixture.home_team_id = 10
    fixture.away_team_id = 20
    fixture.round = "Regular Season - 36"
    home = MagicMock(spec=Team)
    home.name = "Milan"
    away = MagicMock(spec=Team)
    away.name = "Atalanta"

    db = MagicMock()

    def _get(model, pk):
        if model is Competition:
            return comp
        if model is Fixture and pk == 359:
            return fixture
        if pk == 10:
            return home
        if pk == 20:
            return away
        return None

    db.get.side_effect = _get
    db.scalar.return_value = None

    with patch(
        "app.services.sportapi.sportapi_unavailable_backfill_service.SportApiMatchingService",
    ) as mock_match_cls:
        result = SportApiUnavailableBackfillService().backfill(
            db,
            competition_id=1,
            round_number=36,
            dry_run=True,
        )
        mock_match_cls.return_value.match_fixture_for_competition.assert_not_called()

    assert result.fixtures_mapping_missing == 1
    assert result.fixtures_with_mapping == 0
    assert result.total_unavailable_found == 0


@patch("app.services.sportapi.sportapi_unavailable_season_backfill_service.SportApiUnavailableBackfillService")
@patch("app.services.sportapi.sportapi_unavailable_season_backfill_service.BacktestFixtureDebugService")
def test_unavailable_season_backfill_mapped_only(mock_fixture_svc_cls, mock_round_svc_cls):
    kickoff = datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc)
    candidate = BacktestFixtureCandidate(
        fixture_id=359,
        kickoff_at=kickoff,
        status="FT",
        home_team=BacktestFixtureTeamBrief(id=10, name="Milan"),
        away_team=BacktestFixtureTeamBrief(id=20, name="Atalanta"),
        has_team_stats=True,
    )
    mock_fixture_svc_cls.return_value.select_mapped_fixtures_for_sportapi_unavailable_season.return_value = (
        SeasonBackfillSelection(items=[candidate], total_candidates=1, order_by="kickoff_at asc")
    )

    comp = MagicMock(spec=Competition)
    comp.id = 1
    comp.name = "Serie A"
    fixture = MagicMock(spec=Fixture)
    fixture.id = 359
    fixture.home_team_id = 10
    fixture.away_team_id = 20
    fixture.round = "Regular Season - 36"

    mock_round_svc_cls.return_value._process_one_fixture.return_value = {
        "found": 4,
        "written": 0,
        "skipped_provider_id": 0,
        "api_calls": 1,
        "mapping_missing": False,
        "fetch_error": False,
        "detected_paths": ["lineups.home.missingPlayers"],
        "warnings": [],
        "sample": None,
    }

    db = MagicMock()
    db.get.side_effect = lambda model, pk: comp if model is Competition else fixture if pk == 359 else None

    result = SportApiUnavailableSeasonBackfillService(
        round_svc=mock_round_svc_cls.return_value,
    ).backfill_season(db, competition_id=1, dry_run=True)

    assert result.fixtures_with_mapping == 1
    assert result.total_unavailable_found == 4
    assert "lineups.home.missingPlayers" in result.source_paths_found
