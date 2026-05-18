"""Lista raw indisponibili API — usa api_league_id non internal id."""

from unittest.mock import MagicMock, patch

from app.services.availability.availability_api_raw_list import build_availability_api_raw_list
from app.services.availability.availability_league import SerieALeagueContext


@patch("app.services.availability.availability_api_raw_list.ApiFootballClient")
@patch("app.services.availability.availability_api_raw_list.resolve_serie_a_league_context")
def test_raw_list_request_uses_api_league_id(mock_ctx, mock_client_cls):
    db = MagicMock()
    mock_ctx.return_value = SerieALeagueContext(
        league_internal_id=1,
        api_league_id=135,
        league_name="Serie A",
        season_row_id=10,
    )

    mock_client = mock_client_cls.return_value
    mock_client.get.return_value = {
        "response": [
            {
                "player": {"id": 1, "name": "Nicolò Rovella", "type": "Yellow Cards"},
                "team": {"id": 487, "name": "Lazio"},
                "fixture": {"id": 99, "date": "2025-05-17T15:00:00+00:00"},
            },
        ],
        "errors": [],
    }
    mock_client.get_league_season_coverage.return_value = {"injuries": True}

    out = build_availability_api_raw_list(db, 2025, client=mock_client)

    assert out["api_league_id"] == 135
    assert out["league_internal_id"] == 1
    assert "league=135" in out["request"]
    assert "league=1" not in out["request"]
    mock_client.get.assert_called_once()
    call_params = mock_client.get.call_args[0][1]
    assert call_params["league"] == 135
    assert len(out["records"]) == 1
    assert out["records"][0]["player_name"] == "Nicolò Rovella"
