"""Test backfill mapping fixture SportAPI (Step K.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models import Competition, Fixture, Team
from app.models.fixture_provider_mapping import FixtureProviderMapping
from app.schemas.backtest_point_in_time import BacktestFixtureCandidate, BacktestFixtureTeamBrief
from app.services.sportapi.sportapi_fixture_mapping_backfill_service import SportApiFixtureMappingBackfillService
from app.services.sportapi.sportapi_fixture_mapping_scoring import ScoredMappingCandidate


@patch("app.services.sportapi.sportapi_fixture_mapping_backfill_service.SportApiLineupService")
@patch("app.services.sportapi.sportapi_fixture_mapping_backfill_service.SportApiFixtureMappingDiscovery")
@patch("app.services.sportapi.sportapi_fixture_mapping_backfill_service.BacktestFixtureDebugService")
def test_backfill_mapping_dry_run(mock_fixture_svc_cls, mock_discovery_cls, mock_lineup_cls):
    kickoff = datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc)
    candidate = BacktestFixtureCandidate(
        fixture_id=146,
        kickoff_at=kickoff,
        status="FT",
        home_team=BacktestFixtureTeamBrief(id=10, name="Inter"),
        away_team=BacktestFixtureTeamBrief(id=20, name="Lazio"),
        has_team_stats=True,
    )
    mock_fixture_svc_cls.return_value.select_fixtures_for_mini_run.return_value = MagicMock(
        items=[candidate],
    )

    comp = MagicMock(spec=Competition)
    comp.id = 1
    comp.name = "Serie A"
    fixture = MagicMock(spec=Fixture)
    fixture.id = 146
    fixture.competition_id = 1
    fixture.home_team_id = 10
    fixture.away_team_id = 20
    fixture.round = "Regular Season - 37"
    home = MagicMock(spec=Team)
    home.name = "Inter"
    away = MagicMock(spec=Team)
    away.name = "Lazio"

    best = ScoredMappingCandidate(
        provider_event_id=9001,
        score=100.0,
        confidence="high",
        home_team_name="Inter",
        away_team_name="Lazio",
        start_timestamp=int(kickoff.timestamp()),
        round_number=37,
        tournament_name="Serie A",
        breakdown={"same_day": True},
        raw_event={"id": 9001},
    )
    mock_discovery_cls.return_value.discover_for_fixture.return_value = {
        "status": "ok",
        "candidates": [best],
        "best": best,
        "ambiguous_high": False,
        "warnings": [],
        "scheduled_events_count": 3,
        "api_calls": 1,
    }

    db = MagicMock()

    def _get(model, pk):
        if model is Competition:
            return comp
        if model is Fixture and pk == 146:
            return fixture
        if pk == 10:
            return home
        if pk == 20:
            return away
        return None

    db.get.side_effect = _get
    db.scalar.return_value = None

    result = SportApiFixtureMappingBackfillService(
        discovery=mock_discovery_cls.return_value,
        lineup_svc=mock_lineup_cls.return_value,
    ).backfill(
        db,
        competition_id=1,
        round_number=37,
        dry_run=True,
        limit=10,
    )

    assert result.status == "ok"
    assert result.dry_run is True
    assert result.fixtures_processed == 1
    assert result.high_confidence_matches == 1
    assert result.written_mappings == 0
    mock_lineup_cls.return_value.confirm_mapping.assert_not_called()


@patch("app.services.sportapi.sportapi_fixture_mapping_backfill_service.SportApiFixtureMappingDiscovery")
@patch("app.services.sportapi.sportapi_fixture_mapping_backfill_service.BacktestFixtureDebugService")
def test_backfill_skips_existing_mapping(mock_fixture_svc_cls, mock_discovery_cls):
    kickoff = datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc)
    candidate = BacktestFixtureCandidate(
        fixture_id=146,
        kickoff_at=kickoff,
        status="FT",
        home_team=BacktestFixtureTeamBrief(id=10, name="Inter"),
        away_team=BacktestFixtureTeamBrief(id=20, name="Lazio"),
        has_team_stats=True,
    )
    mock_fixture_svc_cls.return_value.select_fixtures_for_mini_run.return_value = MagicMock(
        items=[candidate],
    )

    comp = MagicMock(spec=Competition)
    comp.id = 1
    comp.name = "Serie A"
    fixture = MagicMock(spec=Fixture)
    fixture.id = 146
    fixture.competition_id = 1
    fixture.home_team_id = 10
    fixture.away_team_id = 20
    fixture.round = "Regular Season - 37"
    home = MagicMock(spec=Team)
    home.name = "Inter"
    away = MagicMock(spec=Team)
    away.name = "Lazio"
    mapping = MagicMock(spec=FixtureProviderMapping)

    db = MagicMock()

    def _get(model, pk):
        if model is Competition:
            return comp
        if model is Fixture and pk == 146:
            return fixture
        if pk == 10:
            return home
        if pk == 20:
            return away
        return None

    db.get.side_effect = _get
    db.scalar.return_value = mapping

    result = SportApiFixtureMappingBackfillService(
        discovery=mock_discovery_cls.return_value,
    ).backfill(
        db,
        competition_id=1,
        round_number=37,
        dry_run=True,
    )

    assert result.existing_mappings == 1
    assert result.high_confidence_matches == 0
    mock_discovery_cls.return_value.discover_for_fixture.assert_not_called()
