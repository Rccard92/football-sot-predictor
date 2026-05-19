"""Debug flusso availability fixture."""

from unittest.mock import MagicMock, patch

from app.services.availability.availability_fixture_flow_debug import build_availability_fixture_flow_debug


@patch("app.services.availability.availability_fixture_flow_debug.build_fixture_availability_debug")
@patch("app.services.availability.availability_fixture_flow_debug.load_fixture_availability_buckets")
def test_fixture_flow_includes_fixture_request(mock_buckets, mock_audit):
    db = MagicMock()
    fx = MagicMock()
    fx.id = 371
    fx.api_fixture_id = 1378173
    fx.season_id = 1
    fx.league_id = 1
    fx.kickoff_at = MagicMock()
    fx.kickoff_at.isoformat.return_value = "2025-05-17T15:00:00+00:00"
    fx.home_team = MagicMock()
    fx.home_team.name = "Lazio"
    fx.away_team = MagicMock()
    fx.away_team.name = "Pisa"

    season_row = MagicMock()
    season_row.year = 2025

    db.scalar.side_effect = [fx, season_row]
    db.scalars.return_value.all.return_value = []

    mock_buckets.return_value = MagicMock(applicable=[])
    mock_audit.return_value = {"status": "success", "home": {}, "away": {}}

    out = build_availability_fixture_flow_debug(
        db,
        2025,
        371,
        api_items=[{"player": {"id": 1, "name": "Test"}}],
    )

    assert out["request"] == "injuries?fixture=1378173"
    assert out["api_results_count"] == 1
    assert "diagnosis" in out
