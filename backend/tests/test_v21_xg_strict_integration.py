"""Integrazione xG strict v2.1: side context → 5 micro Qualità occasioni available."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v21.v21_feature_collectors import collect_v21_micro_variables
from app.services.predictions_v21.v21_feature_context import build_v21_side_context
from app.services.predictions_v21.v21_macro_aggregators import aggregate_v21_macro_score
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS


def _team_stat(**kwargs) -> SimpleNamespace:
    base = dict(
        expected_goals=1.2,
        raw_json=None,
        shots_on_target=4,
        total_shots=12,
        shots_inside_box=6,
        shots_outside_box=3,
        blocked_shots=2,
        shots_off_goal=5,
        ball_possession_pct=None,
        total_passes=None,
        accurate_passes=None,
        pass_accuracy_pct=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _stat(*, xg: float = 1.35, sot: float = 4.0) -> SimpleNamespace:
    return _team_stat(expected_goals=xg, shots_on_target=sot)


def _fx(fid: int, day: int, *, home: int, away: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=fid,
        kickoff_at=datetime(2026, 5, day, 15, 0, tzinfo=timezone.utc),
        home_team_id=home,
        away_team_id=away,
        status="FT",
        season_id=1,
        competition_id=1,
        goals_home=1,
        goals_away=0,
    )


def _chance_quality_macro():
    for macro in V21_MANIFEST_DEFINITIONS:
        if macro.key == "chance_quality":
            return macro
    raise KeyError("chance_quality")


def _prior_context(*, team_id: int = 10, opponent_id: int = 20) -> V10PriorContext:
    team_fx = [_fx(i, i, home=team_id, away=90 + i) for i in range(1, 8)]
    opp_fx = [_fx(100 + i, i, home=88 + i, away=opponent_id) for i in range(1, 8)]
    stats_map: dict = {}
    for f in team_fx:
        stats_map[(int(f.id), team_id)] = _stat(xg=1.45)
    for f in opp_fx:
        other = int(f.away_team_id) if int(f.home_team_id) == opponent_id else int(f.home_team_id)
        stats_map[(int(f.id), other)] = _stat(xg=1.30)
    return V10PriorContext(
        season_id=1,
        cutoff_kickoff=datetime(2026, 5, 25, 18, 0, tzinfo=timezone.utc),
        cutoff_fixture_id=500,
        team_id=team_id,
        opponent_id=opponent_id,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=4.0,
        stats_map=stats_map,
        team_prior_count=len(team_fx),
        opponent_prior_count=len(opp_fx),
        team_prior_fixtures=team_fx,
        opponent_prior_fixtures=opp_fx,
        league_baselines={
            "league_avg_sot_for": 4.0,
            "league_avg_sot_conceded": 4.0,
        },
    )


def _target_fixture() -> SimpleNamespace:
    return SimpleNamespace(
        id=500,
        home_team_id=10,
        away_team_id=20,
        kickoff_at=datetime(2026, 5, 26, 18, 0, tzinfo=timezone.utc),
        season_id=1,
        competition_id=1,
    )


@patch("app.services.predictions_v21.v21_feature_context.build_lineup_history")
@patch("app.services.predictions_v21.v21_feature_context.load_team_profile_rows")
@patch("app.services.predictions_v21.v21_feature_context.build_sportapi_lineups_audit")
@patch("app.services.predictions_v21.v21_feature_context.compute_v21_xg_league_baselines")
@patch("app.services.predictions_v21.v21_feature_context.build_prior_context")
def test_build_v21_side_context_strict_xg_all_micros_available(
    mock_prior,
    mock_xg_lb,
    mock_lineups,
    mock_profiles,
    mock_lineup_history,
):
    mock_prior.return_value = _prior_context()
    mock_xg_lb.return_value = {
        "league_avg_xg_for": 1.25,
        "league_avg_xg_conceded": 1.20,
        "league_avg_sot_for": 4.0,
        "league_avg_sot_conceded": 4.0,
        "leakage_guard": True,
        "sample_fixtures": 14,
    }
    mock_lineups.return_value = {"available": False, "home": {}, "away": {}}
    mock_profiles.return_value = []
    mock_lineup_history.return_value = {"sufficient": False, "matches": []}

    db = MagicMock()
    db.get.return_value = SimpleNamespace(name="Team", api_team_id=1, league_id=1, season=2026)
    db.scalars.return_value.first.return_value = None

    fixture = _target_fixture()
    ctx = build_v21_side_context(
        db,
        fixture,
        team_id=10,
        opponent_id=20,
        competition_id=1,
    )

    assert ctx.league_xg_available is True
    assert ctx.strict_xg is not None
    assert ctx.strict_xg.status == "ok"
    assert ctx.strict_xg.team_xg_n >= 5
    assert ctx.strict_xg.opp_xg_n >= 5
    assert ctx.xg_leakage_trace.get("leakage_guard") is True
    assert ctx.xg_leakage_trace.get("latest_fixture_used_at") is not None

    macro = _chance_quality_macro()
    micro_results = collect_v21_micro_variables(macro, ctx)
    assert len(micro_results) == 5
    for m in micro_results:
        assert m.status == "available", m.key
        assert m.raw_value is not None
        assert m.normalized_value is not None
        assert m.leakage_guard is True
        assert m.latest_fixture_used_at is not None
        assert m.fallback_used is False
        assert m.sample_count is not None and m.sample_count >= 5

    macro_result = aggregate_v21_macro_score(macro, micro_results)
    assert macro_result.status == "available"
    assert macro_result.coverage_pct == 100.0
