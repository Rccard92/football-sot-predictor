"""Test backfill unavailable SportAPI (Step K.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models import Competition, Fixture, Team
from app.models.fixture_provider_mapping import FixtureProviderMapping
from app.schemas.backtest_point_in_time import BacktestFixtureCandidate, BacktestFixtureTeamBrief
from app.schemas.sportapi_unavailable_debug import SportApiUnavailableDebugResponse
from app.services.sportapi.sportapi_unavailable_backfill_service import SportApiUnavailableBackfillService


@patch("app.services.sportapi.sportapi_unavailable_backfill_service.SportApiUnavailableDebugService")
@patch("app.services.sportapi.sportapi_unavailable_backfill_service.BacktestFixtureDebugService")
def test_backfill_dry_run(mock_fixture_svc_cls, mock_debug_svc_cls):
    cutoff = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
    candidate = BacktestFixtureCandidate(
        fixture_id=146,
        kickoff_at=cutoff,
        status="FT",
        home_team=BacktestFixtureTeamBrief(id=10, name="Home"),
        away_team=BacktestFixtureTeamBrief(id=20, name="Away"),
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
    home.name = "Home"
    away = MagicMock(spec=Team)
    away.name = "Away"
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

    mock_debug_svc_cls.return_value.debug_fixture.return_value = SportApiUnavailableDebugResponse(
        competition_id=1,
        internal_fixture_id=146,
        source_fixture_id=146,
        mapping_status="ok",
        total_unavailable_found=2,
        would_write_count=2,
        home_unavailable_count=1,
        away_unavailable_count=1,
    )

    result = SportApiUnavailableBackfillService().backfill(
        db,
        competition_id=1,
        round_number=37,
        dry_run=True,
        limit=10,
    )

    assert result.status == "ok"
    assert result.dry_run is True
    assert result.fixtures_processed == 1
    assert result.total_unavailable_found == 2
    assert result.total_written == 0
