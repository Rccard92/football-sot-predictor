"""Test filtri competizione e fixture Cecchino Today."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_EXCLUDED_CUP,
    ELIGIBILITY_EXCLUDED_FRIENDLY,
    ELIGIBILITY_EXCLUDED_WOMEN,
    ELIGIBILITY_EXCLUDED_YOUTH,
)
from app.services.cecchino.cecchino_today_competition_filter import is_cecchino_allowed_competition
from app.services.cecchino.cecchino_today_fixture_filter import is_fixture_not_started


def _item(*, league_name="Serie A", league_type="League", round="", status="NS", kickoff=None):
    return {
        "league": {"name": league_name, "country": "Italy", "type": league_type, "round": round, "season": 2025, "id": 135},
        "fixture": {
            "id": 1,
            "date": kickoff or "2026-06-04T18:45:00+00:00",
            "status": {"short": status},
        },
        "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
    }


def test_excludes_women_league():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Serie A Women"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_cup_type():
    allowed, status = is_cecchino_allowed_competition(_item(league_type="Cup", league_name="Coppa Italia"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_CUP


def test_excludes_friendly_keyword():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Club Friendlies"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_FRIENDLY


def test_excludes_youth_keyword():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Premier League U21"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_YOUTH


def test_allows_league():
    allowed, status = is_cecchino_allowed_competition(_item())
    assert allowed
    assert status is None


def test_fixture_not_started_future():
    now = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
    assert is_fixture_not_started(_item(kickoff="2026-06-04T18:45:00+00:00"), now)


def test_fixture_started_past_kickoff():
    now = datetime(2026, 6, 4, 20, 0, tzinfo=timezone.utc)
    assert not is_fixture_not_started(_item(kickoff="2026-06-04T18:45:00+00:00"), now)


def test_fixture_live_status():
    now = datetime(2026, 6, 4, 20, 0, tzinfo=timezone.utc)
    assert not is_fixture_not_started(_item(status="1H", kickoff="2026-06-04T18:45:00+00:00"), now)
