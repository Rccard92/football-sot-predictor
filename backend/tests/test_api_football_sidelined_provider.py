"""Test parse sidelined e provider."""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.models import PlayerSeasonProfile
from app.services.availability.availability_sidelined_parsing import parse_sidelined_entries
from app.services.availability.providers.api_football_sidelined_provider import (
    ApiFootballSidelinedProvider,
    SidelinedPlayerPick,
    _top_players_for_team,
)
from app.services.availability.providers.base import ProviderContext


def test_parse_sidelined_entries_dates():
    items = [{"start": "2025-05-01", "end": "2025-05-31", "type": "Knee Injury"}]
    rows = parse_sidelined_entries(
        items,
        api_player_id=42,
        player_name="Player A",
        api_team_id=487,
        team_name="Lazio",
    )
    assert len(rows) == 1
    assert rows[0]["start_date"].isoformat() == "2025-05-01"
    assert rows[0]["end_date"].isoformat() == "2025-05-31"
    assert rows[0]["api_player_id"] == 42


def test_top_players_for_team_uses_registry_name():
    pid = uuid.uuid4()
    profile = PlayerSeasonProfile(
        season=2025,
        league_id=1,
        api_team_id=487,
        player_id=pid,
        api_player_id=99,
        minutes_total=Decimal("1500"),
        reliability_score=80,
        shots_on_per90=Decimal("0.5"),
        shooting_impact_score=Decimal("75"),
    )
    reg = MagicMock()
    reg.id = pid
    reg.api_player_id = 99
    reg.name = "Registry Player Name"
    profile.registry = reg

    db = MagicMock()
    db.scalars.return_value.all.return_value = [profile]

    picks = _top_players_for_team(db, season=2025, league_id=1, api_team_id=487, limit=20)
    assert len(picks) == 1
    assert picks[0].api_player_id == 99
    assert picks[0].player_name == "Registry Player Name"
    assert picks[0].player_id == pid


@patch("app.services.availability.providers.api_football_sidelined_provider._top_players_for_team")
def test_sidelined_provider_fetches_by_player(mock_top_players):
    mock_top_players.return_value = [
        SidelinedPlayerPick(
            player_id=uuid.uuid4(),
            api_player_id=99,
            player_name="Test Player",
            team_id=10,
            api_team_id=487,
        ),
    ]
    fx = MagicMock()
    fx.id = 1
    fx.api_fixture_id = 1378236
    fx.kickoff_at = MagicMock()
    fx.kickoff_at.date.return_value = MagicMock()
    fx.home_team = MagicMock()
    fx.home_team.api_team_id = 487
    fx.home_team.id = 10
    fx.home_team.name = "Fiorentina"
    fx.away_team = MagicMock()
    fx.away_team.api_team_id = 499
    fx.away_team.id = 11
    fx.away_team.name = "Atalanta"

    api = MagicMock()
    api.get_sidelined_by_player.return_value = [
        {"start": "2025-05-10", "end": "2025-05-20", "type": "Injury"},
    ]

    ctx = ProviderContext(
        db=MagicMock(),
        season_year=2025,
        league_internal_id=1,
        api_league_id=135,
        upcoming_fixtures=[fx],
        upcoming_api_fixture_ids=[1378236],
        fx_by_api_id={1378236: fx},
        api_client=api,
    )

    result = ApiFootballSidelinedProvider().fetch_candidates(ctx)
    assert result.called is True
    assert result.players_checked >= 1
    assert len(result.candidates) >= 1
    assert result.candidates[0].source == "api_football_sidelined"
    assert result.candidates[0].api_fixture_id == 1378236
    assert result.status == "success"


def test_sidelined_not_available_without_client_method():
    fx = MagicMock()
    fx.id = 1
    fx.api_fixture_id = 100
    fx.home_team = MagicMock(api_team_id=487, id=10, name="H")
    fx.away_team = None

    api = MagicMock(spec=[])
    ctx = ProviderContext(
        db=MagicMock(),
        season_year=2025,
        league_internal_id=1,
        api_league_id=135,
        upcoming_fixtures=[fx],
        upcoming_api_fixture_ids=[100],
        fx_by_api_id={100: fx},
        api_client=api,
    )

    result = ApiFootballSidelinedProvider().fetch_candidates(ctx)
    assert result.status == "not_available"
    assert result.called is False


@patch("app.services.availability.providers.api_football_sidelined_provider._top_players_for_team")
def test_sidelined_skips_team_without_api_id(mock_top_players):
    mock_top_players.return_value = [
        SidelinedPlayerPick(
            player_id=uuid.uuid4(),
            api_player_id=1,
            player_name="P",
            team_id=11,
            api_team_id=499,
        ),
    ]
    fx = MagicMock()
    fx.id = 1
    fx.api_fixture_id = 100
    fx.kickoff_at = MagicMock()
    fx.kickoff_at.date.return_value = MagicMock()
    fx.home_team = MagicMock(api_team_id=None, id=10, name="H")
    fx.away_team = MagicMock(api_team_id=499, id=11, name="A")

    api = MagicMock()
    api.get_sidelined_by_player.return_value = []

    ctx = ProviderContext(
        db=MagicMock(),
        season_year=2025,
        league_internal_id=1,
        api_league_id=135,
        upcoming_fixtures=[fx],
        upcoming_api_fixture_ids=[100],
        fx_by_api_id={100: fx},
        api_client=api,
    )

    result = ApiFootballSidelinedProvider().fetch_candidates(ctx)
    assert result.status == "success"
    mock_top_players.assert_called_once()
