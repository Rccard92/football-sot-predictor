"""Test parse sidelined e provider."""

from unittest.mock import MagicMock, patch

from app.services.availability.availability_sidelined_parsing import parse_sidelined_entries
from app.services.availability.providers.api_football_sidelined_provider import (
    ApiFootballSidelinedProvider,
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


@patch("app.services.availability.providers.api_football_sidelined_provider._top_api_player_ids")
def test_sidelined_provider_fetches_by_player(mock_top_ids):
    mock_top_ids.return_value = [(99, "Test Player")]
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
