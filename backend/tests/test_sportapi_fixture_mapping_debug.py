"""Test debug mapping fixture SportAPI (Step K.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models import Competition, Fixture, Team
from app.models.fixture_provider_mapping import FixtureProviderMapping
from app.services.sportapi.sportapi_fixture_mapping_debug_service import SportApiFixtureMappingDebugService
from app.services.sportapi.sportapi_fixture_mapping_scoring import ScoredMappingCandidate


@patch("app.services.sportapi.sportapi_fixture_mapping_debug_service.SportApiFixtureMappingDiscovery")
def test_debug_mapping_dry_run_high(mock_discovery_cls):
    kickoff = datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc)
    comp = MagicMock(spec=Competition)
    comp.id = 1
    comp.name = "Serie A"
    fixture = MagicMock(spec=Fixture)
    fixture.id = 146
    fixture.competition_id = 1
    fixture.home_team_id = 10
    fixture.away_team_id = 20
    fixture.round = "Regular Season - 37"
    fixture.kickoff_at = kickoff
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
        "scheduled_events_count": 5,
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

    with patch(
        "app.services.sportapi.sportapi_fixture_mapping_debug_service.resolve_fixture_or_error",
        return_value=(fixture, None),
    ):
        result = SportApiFixtureMappingDebugService().debug_fixture(
            db,
            fixture_id=146,
            competition_id=1,
            dry_run=True,
        )

    assert result.status == "ok"
    assert result.dry_run is True
    assert result.match_confidence == "high"
    assert result.would_write_mapping is False
    assert result.mapping_written is False
    assert result.best_candidate is not None
    assert result.best_candidate.provider_event_id == 9001


@patch("app.services.sportapi.sportapi_fixture_mapping_debug_service.SportApiLineupService")
@patch("app.services.sportapi.sportapi_fixture_mapping_debug_service.SportApiFixtureMappingDiscovery")
def test_debug_mapping_write_when_not_dry_run(mock_discovery_cls, mock_lineup_cls):
    kickoff = datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc)
    comp = MagicMock(spec=Competition)
    comp.id = 1
    comp.name = "Serie A"
    fixture = MagicMock(spec=Fixture)
    fixture.id = 146
    fixture.competition_id = 1
    fixture.home_team_id = 10
    fixture.away_team_id = 20
    fixture.round = "Regular Season - 37"
    fixture.kickoff_at = kickoff
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
        raw_event={"id": 9001, "startTimestamp": int(kickoff.timestamp())},
    )

    mock_discovery_cls.return_value.discover_for_fixture.return_value = {
        "status": "ok",
        "candidates": [best],
        "best": best,
        "ambiguous_high": False,
        "warnings": [],
        "scheduled_events_count": 5,
        "api_calls": 1,
    }
    mock_lineup_cls.return_value.confirm_mapping.return_value = {"status": "success"}

    mapping = MagicMock(spec=FixtureProviderMapping)
    mapping.provider_event_id = 9001
    mapping.confidence_score = 100.0
    mapping.matched_by = "sportapi_fixture_discovery"

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
    db.scalar.side_effect = [None, mapping]

    with patch(
        "app.services.sportapi.sportapi_fixture_mapping_debug_service.resolve_fixture_or_error",
        return_value=(fixture, None),
    ):
        svc = SportApiFixtureMappingDebugService(
            discovery=mock_discovery_cls.return_value,
            lineup_svc=mock_lineup_cls.return_value,
        )
        result = svc.debug_fixture(
            db,
            fixture_id=146,
            competition_id=1,
            dry_run=False,
        )

    assert result.would_write_mapping is True
    assert result.mapping_written is True
    mock_lineup_cls.return_value.confirm_mapping.assert_called_once()


@patch("app.services.sportapi.sportapi_fixture_mapping_debug_service.SportApiFixtureMappingDiscovery")
def test_debug_mapping_existing_skip_discovery(mock_discovery_cls):
    kickoff = datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc)
    comp = MagicMock(spec=Competition)
    comp.id = 1
    comp.name = "Serie A"
    fixture = MagicMock(spec=Fixture)
    fixture.id = 146
    fixture.competition_id = 1
    fixture.home_team_id = 10
    fixture.away_team_id = 20
    fixture.round = "Regular Season - 37"
    fixture.kickoff_at = kickoff
    home = MagicMock(spec=Team)
    home.name = "Inter"
    away = MagicMock(spec=Team)
    away.name = "Lazio"
    mapping = MagicMock(spec=FixtureProviderMapping)
    mapping.provider_event_id = 555
    mapping.confidence_score = 95.0
    mapping.matched_by = "sportapi_fixture_discovery"

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

    with patch(
        "app.services.sportapi.sportapi_fixture_mapping_debug_service.resolve_fixture_or_error",
        return_value=(fixture, None),
    ):
        result = SportApiFixtureMappingDebugService().debug_fixture(
            db,
            fixture_id=146,
            competition_id=1,
            dry_run=True,
            force_refresh=False,
        )

    assert result.existing_mapping.found is True
    assert result.existing_mapping.provider_fixture_id == 555
    assert result.api_calls == 0
    mock_discovery_cls.return_value.discover_for_fixture.assert_not_called()
