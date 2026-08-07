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


def _item(
    *,
    league_name="Serie A",
    league_type="League",
    country="Italy",
    round="",
    status="NS",
    kickoff=None,
    home="A",
    away="B",
):
    return {
        "league": {
            "name": league_name,
            "country": country,
            "type": league_type,
            "round": round,
            "season": 2025,
            "id": 135,
        },
        "fixture": {
            "id": 1,
            "date": kickoff or "2026-06-04T18:45:00+00:00",
            "status": {"short": status},
        },
        "teams": {"home": {"name": home}, "away": {"name": away}},
    }


def test_excludes_women_league():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Serie A Women"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_colombia_liga_femenina_millonarios_w():
    allowed, status = is_cecchino_allowed_competition(
        _item(
            league_name="Liga Femenina",
            country="Colombia",
            home="Millonarios W",
            away="Santa Fe W",
        )
    )
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_league_femenina():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Liga Femenina", country="Colombia"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_league_feminina():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Campeonato Feminina"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_league_frauen():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Frauen-Bundesliga", country="Germany"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_league_ladies():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="FA Women's Super League"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_league_feminine():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Division 1 Féminine"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_league_womens():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Womens Premier League"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_both_teams_autonomous_w_suffix():
    allowed, status = is_cecchino_allowed_competition(
        _item(league_name="Primera A", country="Colombia", home="Millonarios W", away="Santa Fe (W)")
    )
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_WOMEN


def test_excludes_both_teams_explicit_women_markers():
    allowed, status = is_cecchino_allowed_competition(
        _item(league_name="Friendly Tournament", home="Arsenal Women", away="Chelsea Ladies")
    )
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


def test_excludes_international_friendly():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="International Friendly"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_FRIENDLY


def test_excludes_youth_keyword():
    allowed, status = is_cecchino_allowed_competition(_item(league_name="Premier League U21"))
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_YOUTH


def test_excludes_youth_hyphenated_and_spaced_u_ages():
    for name in (
        "Premier League U-21",
        "U-23 League",
        "Under-21 League",
        "Sub-21 League",
    ):
        allowed, status = is_cecchino_allowed_competition(_item(league_name=name))
        assert not allowed, name
        assert status == ELIGIBILITY_EXCLUDED_YOUTH, name


def test_excludes_youth_u19_u23_and_reserve():
    for name in ("U19 League", "Championship U23", "Reserve League"):
        allowed, status = is_cecchino_allowed_competition(_item(league_name=name))
        assert not allowed, name
        assert status == ELIGIBILITY_EXCLUDED_YOUTH, name


def test_excludes_youth_both_teams_only():
    allowed, status = is_cecchino_allowed_competition(
        _item(league_name="Premier League", home="Arsenal U21", away="Chelsea U23")
    )
    assert not allowed
    assert status == ELIGIBILITY_EXCLUDED_YOUTH


def test_allows_league():
    allowed, status = is_cecchino_allowed_competition(_item())
    assert allowed
    assert status is None


def test_allows_colombia_primera_a_millonarios():
    allowed, status = is_cecchino_allowed_competition(
        _item(
            league_name="Primera A",
            country="Colombia",
            home="Millonarios",
            away="Santa Fe",
        )
    )
    assert allowed
    assert status is None


def test_allows_regular_male_leagues_anti_false_positive():
    cases = [
        ("Serie A", "Italy"),
        ("Serie B", "Italy"),
        ("Premier League", "England"),
        ("Championship", "England"),
        ("Segunda División", "Spain"),
        ("Ligue 2", "France"),
        ("Liga 2", "Romania"),
        ("Primera B", "Colombia"),
    ]
    for name, country in cases:
        allowed, status = is_cecchino_allowed_competition(_item(league_name=name, country=country))
        assert allowed, name
        assert status is None, name


def test_allows_single_team_trailing_w():
    allowed, status = is_cecchino_allowed_competition(
        _item(league_name="Primera A", country="Colombia", home="Millonarios W", away="Santa Fe")
    )
    assert allowed
    assert status is None


def test_allows_internal_w_in_team_name():
    allowed, status = is_cecchino_allowed_competition(
        _item(league_name="Ekstraklasa", country="Poland", home="Wisła Kraków", away="Lech Poznań")
    )
    assert allowed
    assert status is None


def test_allows_club_suffix_b():
    allowed, status = is_cecchino_allowed_competition(
        _item(
            league_name="Primera Federación",
            country="Spain",
            home="Real Madrid B",
            away="Barcelona B",
        )
    )
    assert allowed
    assert status is None


def test_allows_professional_junior_club():
    allowed, status = is_cecchino_allowed_competition(
        _item(
            league_name="Primera A",
            country="Colombia",
            home="Atlético Junior",
            away="Millonarios",
        )
    )
    assert allowed
    assert status is None


def test_allows_single_youth_team_without_competition_marker():
    allowed, status = is_cecchino_allowed_competition(
        _item(league_name="Premier League", home="Arsenal U21", away="Chelsea")
    )
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
