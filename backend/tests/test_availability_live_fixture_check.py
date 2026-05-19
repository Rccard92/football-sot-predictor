"""Controllo live API injuries per fixture."""

from unittest.mock import MagicMock, patch

from app.services.availability.availability_live_fixture_check import build_availability_live_fixture_check


@patch("app.services.availability.availability_live_fixture_check.parse_injuries_item")
@patch("app.services.availability.availability_live_fixture_check.ApiFootballClient")
def test_live_fixture_check_no_persist(mock_client_cls, mock_parse):
    db = MagicMock()
    fx = MagicMock()
    fx.id = 371
    fx.api_fixture_id = 1378173
    fx.season_id = 1

    season_row = MagicMock()
    season_row.year = 2025

    db.scalar.side_effect = [fx, season_row]

    api = MagicMock()
    api.get_injuries_by_fixture.return_value = [
        {
            "player": {"id": 1, "name": "Test Player", "type": "Missing", "reason": "Injury"},
            "team": {"id": 487, "name": "Lazio"},
        },
    ]
    mock_client_cls.return_value = api

    parsed = MagicMock()
    parsed.availability_status = "out"
    parsed.availability_type = "injury"
    mock_parse.return_value = parsed

    out = build_availability_live_fixture_check(db, 2025, 371, client=api)

    assert out["status"] == "success"
    assert out["request"] == "injuries?fixture=1378173"
    assert out["results"] == 1
    assert len(out["records"]) == 1
    assert out["records"][0]["player_name"] == "Test Player"
    db.commit.assert_not_called()
    db.add.assert_not_called()
