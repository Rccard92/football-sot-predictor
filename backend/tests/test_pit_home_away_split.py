"""Test split casa/trasferta point-in-time backtest SOT v2.1 PIT (Step G1)."""

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
    TeamPointInTimeStats,
    TeamSplitPointInTimeStats,
)
from app.services.backtest.pit_split_stats_builder import _split_status, build_pit_split_stats
from app.services.backtest.sot_v21_mini_run_preview_service import _aggregate_split_summary
from app.services.backtest.sot_v21_pit_macro_builder import (
    PIT_MACRO_INDEX_MAX,
    PIT_MACRO_INDEX_MIN,
    _compute_home_away_split_macro,
)
from app.schemas.backtest_sot_v21_preview import (
    SotV21PreviewErrors,
    SotV21PreviewFixtureBrief,
    SotV21PreviewMacroTrace,
    SotV21PreviewPrediction,
    SotV21PreviewResponse,
    SotV21PreviewSideTrace,
)
from app.services.predictions_v10.v10_prior_context import V10PriorContext

client = TestClient(app)

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
_LATEST = datetime(2026, 3, 10, 20, 45, tzinfo=timezone.utc)


def _ctx(
    *,
    home_split_count: int = 6,
    away_split_count: int = 6,
    home_split_sot_for: float = 6.0,
    home_overall_sot_for: float = 5.0,
    away_split_sot_against: float = 5.0,
    away_overall_sot_against: float = 4.0,
    away_split_sot_for: float = 3.5,
    away_overall_sot_for: float = 4.0,
    home_split_sot_against: float = 4.5,
    home_overall_sot_against: float = 4.0,
) -> PointInTimeContextResponse:
    home_status = _split_status(home_split_count)
    away_status = _split_status(away_split_count)
    return PointInTimeContextResponse(
        competition_id=1,
        competition_key="serie_a",
        competition_name="Serie A",
        fixture_id=146,
        fixture_kickoff_at=_CUTOFF,
        fixture_status="FT",
        home_team_id=1,
        home_team_name="AC Milan",
        away_team_id=2,
        away_team_name="Sassuolo",
        mode="pre_lineup",
        cutoff_time=_CUTOFF,
        leakage_guard=True,
        home_team_stats=TeamPointInTimeStats(
            team_id=1,
            team_name="AC Milan",
            avg_sot_for=home_overall_sot_for,
            avg_sot_against=home_overall_sot_against,
            sample_count=14,
        ),
        away_team_stats=TeamPointInTimeStats(
            team_id=2,
            team_name="Sassuolo",
            avg_sot_for=away_overall_sot_for,
            avg_sot_against=away_overall_sot_against,
            sample_count=14,
        ),
        home_split_stats=TeamSplitPointInTimeStats(
            team_id=1,
            split_context="home",
            matches_count=home_split_count,
            avg_sot_for=home_split_sot_for,
            avg_sot_against=home_split_sot_against,
            status=home_status,
        ),
        away_split_stats=TeamSplitPointInTimeStats(
            team_id=2,
            split_context="away",
            matches_count=away_split_count,
            avg_sot_for=away_split_sot_for,
            avg_sot_against=away_split_sot_against,
            status=away_status,
        ),
        league_baselines=LeaguePointInTimeBaselines(),
        home_player_stats=PlayerStatsDiagnostic(),
        away_player_stats=PlayerStatsDiagnostic(),
        lineup_diagnostic=LineupDiagnostic(lineup_mode="pre_lineup_no_official"),
        actuals_for_scoring=ActualsForScoring(),
    )


def test_split_status_thresholds():
    assert _split_status(0) == "neutral_fallback"
    assert _split_status(1) == "partial_low_sample"
    assert _split_status(4) == "partial_low_sample"
    assert _split_status(5) == "available"


def test_compute_split_macro_available_not_neutral():
    ctx = _ctx(home_split_count=6, away_split_count=6)
    result, trace, fallback = _compute_home_away_split_macro(ctx, is_home=True)

    assert fallback is None
    assert result.key == "home_away_split"
    assert result.macro_index != 1.0
    assert result.status == "available"
    assert "split_home_away_point_in_time_not_built_yet" not in result.warnings
    assert trace["components"]["sample_count"] == 6
    assert PIT_MACRO_INDEX_MIN <= result.macro_index <= PIT_MACRO_INDEX_MAX


def test_compute_split_macro_partial_low_sample():
    ctx = _ctx(home_split_count=3, away_split_count=3)
    result, _, _ = _compute_home_away_split_macro(ctx, is_home=True)

    assert result.status == "partial_low_sample"
    assert "split_home_away_partial_low_sample" in result.warnings
    assert result.macro_index != 1.0


def test_compute_split_macro_fallback_missing_sample():
    ctx = _ctx(home_split_count=0, away_split_count=0)
    result, trace, fallback = _compute_home_away_split_macro(ctx, is_home=True)

    assert result.macro_index == 1.0
    assert result.status == "neutral_fallback"
    assert fallback == "split_home_away"
    assert "split_home_away_missing" in result.warnings
    assert trace["components"]["fallback_reason"] == "split_sample_missing"


def test_compute_split_macro_fallback_null_ratio():
    ctx = _ctx(home_split_count=5, away_split_count=5, home_overall_sot_for=0.0)
    result, _, fallback = _compute_home_away_split_macro(ctx, is_home=True)

    assert result.macro_index == 1.0
    assert result.status == "neutral_fallback"
    assert fallback == "split_home_away"


def test_build_pit_split_stats_from_prior_fixtures():
    kickoff = datetime(2026, 1, 10, 15, 0, tzinfo=timezone.utc)
    fx_home = MagicMock()
    fx_home.id = 10
    fx_home.kickoff_at = kickoff
    fx_home.home_team_id = 1
    fx_home.away_team_id = 99

    fx_away = MagicMock()
    fx_away.id = 11
    fx_away.kickoff_at = kickoff
    fx_away.home_team_id = 88
    fx_away.away_team_id = 2

    st_home = MagicMock()
    st_home.shots_on_target = 5
    st_home.total_shots = 12
    st_home.expected_goals = 1.1
    st_opp = MagicMock()
    st_opp.shots_on_target = 3

    stats_map = {
        (10, 1): st_home,
        (10, 99): st_opp,
        (11, 88): MagicMock(shots_on_target=4, total_shots=10, expected_goals=0.9),
        (11, 2): MagicMock(shots_on_target=6, total_shots=14, expected_goals=1.2),
    }

    home_ctx = V10PriorContext(
        season_id=1,
        cutoff_kickoff=_CUTOFF,
        cutoff_fixture_id=146,
        team_id=1,
        opponent_id=2,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=4.0,
        stats_map=stats_map,
        team_prior_count=1,
        opponent_prior_count=1,
        team_prior_fixtures=[fx_home],
        opponent_prior_fixtures=[fx_away],
        league_baselines={},
    )
    away_ctx = V10PriorContext(
        season_id=1,
        cutoff_kickoff=_CUTOFF,
        cutoff_fixture_id=146,
        team_id=2,
        opponent_id=1,
        is_home=False,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=4.0,
        stats_map=stats_map,
        team_prior_count=1,
        opponent_prior_count=1,
        team_prior_fixtures=[fx_away],
        opponent_prior_fixtures=[fx_home],
        league_baselines={},
    )

    home_split, away_split, split_fixtures, warnings = build_pit_split_stats(
        home_ctx,
        away_ctx,
        home_team_id=1,
        away_team_id=2,
    )

    assert home_split.matches_count == 1
    assert home_split.avg_sot_for == 5.0
    assert home_split.status == "partial_low_sample"
    assert away_split.matches_count == 1
    assert away_split.avg_sot_for == 6.0
    assert "home_split_low_sample" in warnings
    assert "away_split_low_sample" in warnings
    assert len(split_fixtures) == 2


def test_aggregate_split_summary_from_previews():
    split_macro = SotV21PreviewMacroTrace(
        key="home_away_split",
        label="Split casa/trasferta",
        macro_weight=10,
        macro_index=1.08,
        status="available",
    )
    partial_macro = split_macro.model_copy(update={"macro_index": 0.95, "status": "partial_low_sample"})
    fallback_macro = split_macro.model_copy(update={"macro_index": 1.0, "status": "neutral_fallback"})
    side_available = SotV21PreviewSideTrace(
        base_anchor_sot={"value": 5.0},
        weighted_macro_multiplier=1.05,
        macros=[split_macro],
    )
    side_partial = SotV21PreviewSideTrace(
        base_anchor_sot={"value": 4.0},
        weighted_macro_multiplier=1.02,
        macros=[partial_macro],
    )
    side_fallback = SotV21PreviewSideTrace(
        base_anchor_sot={"value": 4.0},
        weighted_macro_multiplier=1.0,
        macros=[fallback_macro],
    )

    previews = [
        SotV21PreviewResponse(
            competition_id=1,
            fixture_id=1,
            fixture=SotV21PreviewFixtureBrief(
                home_team="A",
                away_team="B",
                kickoff_at=_CUTOFF,
            ),
            cutoff_time=_CUTOFF,
            prediction=SotV21PreviewPrediction(),
            actuals_for_scoring=ActualsForScoring(),
            errors=SotV21PreviewErrors(),
            home_trace=side_available,
            away_trace=side_available,
        ),
        SotV21PreviewResponse(
            competition_id=1,
            fixture_id=2,
            fixture=SotV21PreviewFixtureBrief(
                home_team="C",
                away_team="D",
                kickoff_at=_CUTOFF,
            ),
            cutoff_time=_CUTOFF,
            prediction=SotV21PreviewPrediction(),
            actuals_for_scoring=ActualsForScoring(),
            errors=SotV21PreviewErrors(),
            home_trace=side_partial,
            away_trace=side_available,
        ),
        SotV21PreviewResponse(
            competition_id=1,
            fixture_id=3,
            fixture=SotV21PreviewFixtureBrief(
                home_team="E",
                away_team="F",
                kickoff_at=_CUTOFF,
            ),
            cutoff_time=_CUTOFF,
            prediction=SotV21PreviewPrediction(),
            actuals_for_scoring=ActualsForScoring(),
            errors=SotV21PreviewErrors(),
            home_trace=side_fallback,
            away_trace=side_available,
        ),
    ]

    summary = _aggregate_split_summary(previews)
    assert summary.available_count == 1
    assert summary.partial_count == 1
    assert summary.fallback_count == 1
    assert summary.avg_home_split_index is not None
    assert summary.avg_away_split_index == 1.08


@patch("app.routes.backtest_debug.SotV21MiniRunPreviewService")
def test_mini_run_response_includes_split_summary(mock_svc_cls):
    from app.schemas.backtest_sot_v21_mini_run import (
        SotV21MiniRunResponse,
        SotV21MiniRunSelection,
        SotV21MiniRunSplitSummary,
        SotV21MiniRunSummary,
    )

    mock_svc_cls.return_value.run_preview.return_value = SotV21MiniRunResponse(
        status="ok",
        competition_id=1,
        competition_name="Serie A",
        selection=SotV21MiniRunSelection(limit=10, offset=0, round_number=15),
        summary=SotV21MiniRunSummary(fixtures_processed=10, fixtures_failed=0),
        split_summary=SotV21MiniRunSplitSummary(
            available_count=8,
            partial_count=2,
            fallback_count=0,
            avg_home_split_index=1.05,
            avg_away_split_index=0.98,
        ),
        db_writes=False,
    )

    response = client.post(
        "/api/backtest/debug/sot-v21-mini-run",
        json={"competition_id": 1, "round_number": 15, "limit": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["split_summary"]["available_count"] == 8
    assert body["split_summary"]["avg_home_split_index"] == 1.05
    assert "split_home_away_point_in_time_not_built_yet" not in str(body)
