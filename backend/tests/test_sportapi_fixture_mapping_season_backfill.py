"""Test backfill mapping stagione SportAPI (Step K.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models import Competition, Fixture, Team
from app.schemas.backtest_point_in_time import BacktestFixtureCandidate, BacktestFixtureTeamBrief
from app.services.backtest.backtest_fixture_debug_service import SeasonBackfillSelection
from app.services.sportapi.sportapi_fixture_mapping_scoring import ScoredMappingCandidate
from app.services.sportapi.sportapi_fixture_mapping_season_backfill_service import (
    SportApiFixtureMappingSeasonBackfillService,
)


@patch("app.services.sportapi.sportapi_fixture_mapping_season_backfill_service.SportApiFixtureMappingDiscovery")
@patch("app.services.sportapi.sportapi_fixture_mapping_season_backfill_service.BacktestFixtureDebugService")
def test_season_mapping_dry_run_groups_by_date(mock_fixture_svc_cls, mock_discovery_cls):
    kickoff = datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc)
    candidate = BacktestFixtureCandidate(
        fixture_id=359,
        kickoff_at=kickoff,
        status="FT",
        home_team=BacktestFixtureTeamBrief(id=10, name="Milan"),
        away_team=BacktestFixtureTeamBrief(id=20, name="Atalanta"),
        has_team_stats=True,
    )
    mock_fixture_svc_cls.return_value.select_fixtures_for_sportapi_season_backfill.return_value = (
        SeasonBackfillSelection(items=[candidate], total_candidates=1, order_by="kickoff_at asc")
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
    fixture.kickoff_at = kickoff
    home = MagicMock(spec=Team)
    home.name = "Milan"
    away = MagicMock(spec=Team)
    away.name = "Atalanta"

    best = ScoredMappingCandidate(
        provider_event_id=13980096,
        score=100.0,
        confidence="high",
        home_team_name="Milan",
        away_team_name="Atalanta",
        start_timestamp=int(kickoff.timestamp()),
        round_number=36,
        tournament_name="Serie A",
        breakdown={"same_day": True},
        raw_event={"id": 13980096},
    )

    mock_discovery = mock_discovery_cls.return_value
    mock_discovery.fetch_scheduled_events_for_date.return_value = ([{"id": 13980096}], 1)
    mock_discovery.discover_for_fixture.return_value = {
        "status": "ok",
        "candidates": [best],
        "best": best,
        "ambiguous_high": False,
        "warnings": [],
        "scheduled_events_count": 1,
        "api_calls": 0,
    }

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

    result = SportApiFixtureMappingSeasonBackfillService(discovery=mock_discovery).backfill_season(
        db,
        competition_id=1,
        dry_run=True,
        limit=400,
    )

    assert result.status == "ok"
    assert result.fixtures_processed == 1
    assert result.high_confidence_matches == 1
    assert result.written_mappings == 0
    assert result.api_calls == 1
    assert result.items_sample[0].would_write_mapping is True
    mock_discovery.fetch_scheduled_events_for_date.assert_called_once()
