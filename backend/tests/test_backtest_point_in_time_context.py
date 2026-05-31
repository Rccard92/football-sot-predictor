"""Test GET /api/backtest/debug/point-in-time-context e /fixtures (Step D)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_point_in_time import (
    ActualsForScoring,
    LeaguePointInTimeBaselines,
    LineupDiagnostic,
    PlayerStatsDiagnostic,
    PointInTimeContextResponse,
    TeamLast5Form,
    TeamPointInTimeStats,
    TeamSplitPointInTimeStats,
)

client = TestClient(app)

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
_LATEST = datetime(2026, 3, 10, 20, 45, tzinfo=timezone.utc)

_MOCK_CONTEXT = PointInTimeContextResponse(
    competition_id=2,
    competition_key="brasileirao",
    competition_name="Brasileirão",
    fixture_id=100,
    fixture_kickoff_at=_CUTOFF,
    fixture_round="Regular Season - 10",
    fixture_status="FT",
    home_team_id=10,
    home_team_name="Flamengo",
    away_team_id=11,
    away_team_name="Palmeiras",
    mode="pre_lineup",
    cutoff_time=_CUTOFF,
    leakage_guard=True,
    latest_fixture_used_at=_LATEST,
    prior_fixtures_count=45,
    home_prior_matches_count=9,
    away_prior_matches_count=9,
    league_prior_matches_count=90,
    home_team_stats=TeamPointInTimeStats(
        team_id=10,
        team_name="Flamengo",
        avg_sot_for=5.2,
        avg_sot_against=4.1,
        sample_count=9,
        latest_fixture_used_at=_LATEST,
        last5=TeamLast5Form(last5_count=5, last5_avg_sot_for=5.0),
    ),
    away_team_stats=TeamPointInTimeStats(
        team_id=11,
        team_name="Palmeiras",
        avg_sot_for=4.8,
        avg_sot_against=3.9,
        sample_count=9,
        latest_fixture_used_at=_LATEST,
    ),
    home_split_stats=TeamSplitPointInTimeStats(
        team_id=10,
        split_context="home",
        matches_count=5,
        avg_sot_for=5.5,
        avg_sot_against=3.8,
        status="available",
        latest_fixture_used_at=_LATEST,
    ),
    away_split_stats=TeamSplitPointInTimeStats(
        team_id=11,
        split_context="away",
        matches_count=4,
        avg_sot_for=4.2,
        avg_sot_against=4.0,
        status="partial_low_sample",
        latest_fixture_used_at=_LATEST,
    ),
    league_baselines=LeaguePointInTimeBaselines(
        league_avg_sot_for=4.5,
        league_avg_xg_for=1.2,
        sample_count=90,
        latest_fixture_used_at=_LATEST,
    ),
    home_player_stats=PlayerStatsDiagnostic(player_match_stats_prior_count=120, unique_players_prior_count=22),
    away_player_stats=PlayerStatsDiagnostic(player_match_stats_prior_count=115, unique_players_prior_count=21),
    lineup_diagnostic=LineupDiagnostic(lineup_mode="pre_lineup_no_official", lineups_available=False),
    actuals_for_scoring=ActualsForScoring(
        actual_home_sot=6,
        actual_away_sot=4,
        actual_total_sot=10,
        final_score="2-1",
        fixture_status="FT",
    ),
    actuals_used_as_input=False,
    warnings=["player_profiles_point_in_time_not_built_yet"],
    feature_snapshot_json={
        "cutoff_time": _CUTOFF.isoformat(),
        "latest_fixture_used_at": _LATEST.isoformat(),
        "leakage_guard": True,
    },
)


@patch("app.routes.backtest_debug.PointInTimeContextService")
def test_point_in_time_context_success(mock_svc_cls):
    mock_svc_cls.return_value.build_sot_context.return_value = _MOCK_CONTEXT

    response = client.get(
        "/api/backtest/debug/point-in-time-context",
        params={"competition_id": 2, "fixture_id": 100, "mode": "pre_lineup"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["leakage_guard"] is True
    assert body["actuals_used_as_input"] is False
    assert body["latest_fixture_used_at"] < body["cutoff_time"]
    assert body["home_team_stats"]["avg_sot_for"] == 5.2
    assert body["actuals_for_scoring"]["actual_total_sot"] == 10


@patch("app.routes.backtest_debug.PointInTimeContextService")
def test_point_in_time_context_fixture_not_found(mock_svc_cls):
    from fastapi import HTTPException

    mock_svc_cls.return_value.build_sot_context.side_effect = HTTPException(
        status_code=404,
        detail={"code": "fixture_not_found", "message": "Fixture 999 not found"},
    )

    response = client.get(
        "/api/backtest/debug/point-in-time-context",
        params={"competition_id": 2, "fixture_id": 999},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "fixture_not_found"


@patch("app.routes.backtest_debug.PointInTimeContextService")
def test_point_in_time_context_competition_mismatch(mock_svc_cls):
    from fastapi import HTTPException

    mock_svc_cls.return_value.build_sot_context.side_effect = HTTPException(
        status_code=422,
        detail={
            "code": "fixture_competition_mismatch",
            "message": "Fixture 100 does not belong to competition 1",
        },
    )

    response = client.get(
        "/api/backtest/debug/point-in-time-context",
        params={"competition_id": 1, "fixture_id": 100},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "fixture_competition_mismatch"


@patch("app.routes.backtest_debug.PointInTimeContextService")
def test_point_in_time_context_market_not_supported(mock_svc_cls):
    from fastapi import HTTPException

    mock_svc_cls.return_value.build_sot_context.side_effect = HTTPException(
        status_code=422,
        detail={
            "code": "market_not_supported_for_context_yet",
            "message": "PointInTimeContext preview supports only shots_on_target for now.",
        },
    )

    response = client.get(
        "/api/backtest/debug/point-in-time-context",
        params={"competition_id": 2, "fixture_id": 100, "market_key": "corners"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "market_not_supported_for_context_yet"


@patch("app.routes.backtest_debug.BacktestFixtureDebugService")
def test_backtest_debug_fixtures_list(mock_svc_cls):
    from app.schemas.backtest_point_in_time import (
        BacktestFixtureCandidate,
        BacktestFixtureListResponse,
        BacktestFixtureTeamBrief,
    )

    mock_svc_cls.return_value.list_candidate_fixtures.return_value = BacktestFixtureListResponse(
        items=[
            BacktestFixtureCandidate(
                fixture_id=100,
                kickoff_at=_CUTOFF,
                status="FT",
                home_team=BacktestFixtureTeamBrief(id=10, name="Flamengo"),
                away_team=BacktestFixtureTeamBrief(id=11, name="Palmeiras"),
                has_team_stats=True,
                actual_total_sot=10,
            ),
        ],
        total=1,
        limit=20,
        offset=0,
    )

    response = client.get(
        "/api/backtest/debug/fixtures",
        params={"competition_id": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["fixture_id"] == 100
    assert body["items"][0]["has_team_stats"] is True


@patch("app.routes.backtest_debug.BacktestFixtureDebugService")
def test_backtest_debug_fixtures_round_filter(mock_svc_cls):
    from app.schemas.backtest_point_in_time import BacktestFixtureListResponse

    mock_svc_cls.return_value.list_candidate_fixtures.return_value = BacktestFixtureListResponse(
        items=[],
        total=0,
        limit=20,
        offset=0,
    )

    response = client.get(
        "/api/backtest/debug/fixtures",
        params={"competition_id": 2, "round_contains": "Regular Season - 20"},
    )

    assert response.status_code == 200
    mock_svc_cls.return_value.list_candidate_fixtures.assert_called_once()
    call_kwargs = mock_svc_cls.return_value.list_candidate_fixtures.call_args.kwargs
    assert call_kwargs["round_contains"] == "Regular Season - 20"
