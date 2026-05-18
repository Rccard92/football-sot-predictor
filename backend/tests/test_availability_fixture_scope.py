"""Classificazione applicabilità record per fixture."""

from datetime import date
from unittest.mock import MagicMock

from app.models.player_availability import SCOPE_FIXTURE_LEVEL, SCOPE_SEASON_LEVEL, SCOPE_TEAM_LEVEL
from app.services.availability.availability_fixture_scope import (
    FixtureContext,
    classify_record_for_fixture,
    infer_record_scope,
)


def _ctx() -> FixtureContext:
    return FixtureContext(
        fixture_id=10,
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


def _row(**kwargs) -> MagicMock:
    r = MagicMock()
    r.record_scope = kwargs.get("record_scope")
    r.api_fixture_id = kwargs.get("api_fixture_id")
    r.fixture_id = kwargs.get("fixture_id")
    r.api_team_id = kwargs.get("api_team_id", 487)
    r.team_id = kwargs.get("team_id", 1)
    r.start_date = kwargs.get("start_date")
    r.end_date = kwargs.get("end_date")
    r.source = kwargs.get("source", "api_football_injuries")
    return r


def test_infer_record_scope_fixture_level():
    assert infer_record_scope(source="api_football_injuries", api_fixture_id=99, api_team_id=487) == SCOPE_FIXTURE_LEVEL


def test_infer_record_scope_team_level():
    assert infer_record_scope(source="api_football_injuries", api_fixture_id=None, api_team_id=487) == SCOPE_TEAM_LEVEL


def test_infer_record_scope_season_level():
    assert infer_record_scope(source="api_football_injuries", api_fixture_id=None, api_team_id=None) == SCOPE_SEASON_LEVEL


def test_fixture_level_applicable_only_matching_fixture():
    ctx = _ctx()
    row = _row(record_scope=SCOPE_FIXTURE_LEVEL, api_fixture_id=1378173, api_team_id=487)
    assert classify_record_for_fixture(row, ctx) == "applicable"


def test_fixture_level_excluded_other_fixture():
    ctx = _ctx()
    row = _row(record_scope=SCOPE_FIXTURE_LEVEL, api_fixture_id=999999, api_team_id=487)
    assert classify_record_for_fixture(row, ctx) == "excluded"


def test_team_level_applicable_in_date_range():
    ctx = _ctx()
    row = _row(
        record_scope=SCOPE_TEAM_LEVEL,
        api_fixture_id=None,
        start_date=date(2025, 5, 1),
        end_date=date(2025, 5, 20),
    )
    assert classify_record_for_fixture(row, ctx) == "applicable"


def test_team_level_generic_without_start_date():
    ctx = _ctx()
    row = _row(record_scope=SCOPE_TEAM_LEVEL, api_fixture_id=None, start_date=None, end_date=None)
    assert classify_record_for_fixture(row, ctx) == "generic_not_applied"


def test_team_level_excluded_after_end_date():
    ctx = _ctx()
    row = _row(
        record_scope=SCOPE_TEAM_LEVEL,
        api_fixture_id=None,
        start_date=date(2025, 4, 1),
        end_date=date(2025, 5, 10),
    )
    assert classify_record_for_fixture(row, ctx) == "excluded"


def test_season_level_excluded():
    ctx = _ctx()
    row = _row(record_scope=SCOPE_SEASON_LEVEL, api_team_id=487)
    assert classify_record_for_fixture(row, ctx) == "excluded"
