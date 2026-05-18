"""Debug availability — fixture applicable only."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from app.models.player_availability import SCOPE_FIXTURE_LEVEL, SCOPE_TEAM_LEVEL
from app.services.availability.availability_debug import build_fixture_availability_debug
from app.services.availability.availability_fixture_scope import FixtureAvailabilityBuckets, FixtureContext


def _ctx() -> FixtureContext:
    return FixtureContext(
        fixture_id=371,
        api_fixture_id=1378173,
        kickoff=date(2025, 5, 17),
        season_year=2025,
        league_id=1,
        home_team_id=1,
        away_team_id=2,
        api_home_team_id=487,
        api_away_team_id=1001,
        home_name="Lazio",
        away_name="Pisa",
    )


@patch("app.services.availability.availability_debug.load_fixture_availability_buckets")
def test_audit_excludes_team_level_without_dates_from_applicable(mock_buckets):
    db = MagicMock()
    ctx = _ctx()

    applicable_row = MagicMock()
    applicable_row.api_player_id = 1
    applicable_row.player_name = "Rovella"
    applicable_row.api_team_id = 487
    applicable_row.team_id = 1
    applicable_row.availability_status = "suspended"
    applicable_row.availability_type = "suspension"
    applicable_row.reason = "Yellow Cards"
    applicable_row.source = "api_football_injuries"
    applicable_row.record_scope = SCOPE_FIXTURE_LEVEL
    applicable_row.api_fixture_id = 1378173
    applicable_row.fixture_id = 371
    applicable_row.fixture_date = None
    applicable_row.start_date = date(2025, 5, 1)
    applicable_row.end_date = None

    generic_row = MagicMock()
    generic_row.api_player_id = 2
    generic_row.player_name = "Old Injury"
    generic_row.api_team_id = 487
    generic_row.team_id = 1
    generic_row.availability_status = "injured"
    generic_row.availability_type = "injury"
    generic_row.reason = "Knee"
    generic_row.source = "api_football_injuries"
    generic_row.record_scope = SCOPE_TEAM_LEVEL
    generic_row.api_fixture_id = None
    generic_row.fixture_id = None
    generic_row.fixture_date = None
    generic_row.start_date = None
    generic_row.end_date = None

    mock_buckets.return_value = FixtureAvailabilityBuckets(
        ctx=ctx,
        applicable=[applicable_row],
        generic_not_applied=[generic_row],
        excluded=[],
    )

    fx = MagicMock()
    fx.id = 371
    fx.api_fixture_id = 1378173
    fx.kickoff_at = datetime(2025, 5, 17, 15, 0)

    home = MagicMock()
    home.id = 1
    home.name = "Lazio"
    home.api_team_id = 487

    away = MagicMock()
    away.id = 2
    away.name = "Pisa"
    away.api_team_id = 1001

    db.scalar.side_effect = [fx]
    db.get.side_effect = lambda _model, pk: home if pk == 1 else away
    db.scalars.return_value.all.return_value = []

    out = build_fixture_availability_debug(db, 371)

    assert out["status"] == "success"
    assert out["availability_scope"] == "fixture_applicable_only"
    home_applicable = out["home"]["applicable_records"]
    assert len(home_applicable) == 1
    assert home_applicable[0]["player_name"] == "Rovella"
    generic = out["home"]["generic_records_not_applied"]
    assert len(generic) == 1
    assert generic[0]["player_name"] == "Old Injury"
