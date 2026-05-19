"""Debug flusso availability fixture (solo DB)."""

from unittest.mock import MagicMock, patch

from app.services.availability.availability_fixture_flow_debug import build_availability_fixture_flow_debug


@patch("app.services.availability.availability_fixture_flow_debug.get_last_availability_upcoming_run")
@patch("app.services.availability.availability_fixture_flow_debug.resolve_serie_a_league_context")
@patch("app.services.availability.availability_fixture_flow_debug.load_fixture_availability_buckets")
@patch("app.services.availability.availability_fixture_flow_debug.build_fixture_context")
def test_fixture_flow_db_only_response(mock_ctx, mock_buckets, mock_league, mock_last_run):
    db = MagicMock()
    ctx = MagicMock()
    ctx.fixture_id = 371
    ctx.api_fixture_id = 1378173
    ctx.season_year = 2025
    ctx.league_id = 1
    ctx.kickoff = MagicMock()
    ctx.home_team_id = 10
    ctx.away_team_id = 11
    ctx.api_home_team_id = 487
    ctx.api_away_team_id = 499
    ctx.home_name = "Lazio"
    ctx.away_name = "Pisa"
    mock_ctx.return_value = ctx

    league_ctx = MagicMock()
    league_ctx.api_league_id = 135
    mock_league.return_value = league_ctx

    buckets = MagicMock()
    buckets.applicable = []
    buckets.generic_not_applied = []
    buckets.excluded = []
    buckets.ctx = ctx
    mock_buckets.return_value = buckets
    mock_last_run.return_value = {
        "season": 2025,
        "last_run_at": "2025-05-18T10:00:00+00:00",
        "upcoming_api_fixture_ids": [1378173],
        "per_fixture": {"1378173": {"records_matching": 2, "records_saved": 2}},
    }

    fx = MagicMock()
    fx.kickoff_at = MagicMock()
    fx.kickoff_at.isoformat.return_value = "2025-05-17T15:00:00+00:00"
    fx.status = "NS"
    db.scalar.side_effect = [fx, None]
    db.scalars.return_value.all.return_value = []

    out = build_availability_fixture_flow_debug(db, 2025, 371)

    assert out["status"] == "success"
    assert out["fixture"]["api_fixture_id"] == 1378173
    assert out["api_football_expected_request"]["fixture_request"] == "injuries?fixture=1378173"
    assert out["api_football_expected_request"]["api_league_id"] == 135
    assert "db_checks" in out
    assert "excluded_records" in out
    assert "diagnosis" in out
    assert "api_results_count" not in out
    assert "last_availability_upcoming" in out
    assert out["last_availability_upcoming"]["records_saved_this_fixture"] == 2
