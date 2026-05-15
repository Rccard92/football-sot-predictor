"""Test componente xG v1.1 (strict, nessun fallback)."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.predictions_v11.xg_quality_strict import compute_xg_chance_quality_component
from app.services.predictions_v10.v10_prior_context import V10PriorContext


def _stat(**kwargs) -> SimpleNamespace:
    d = dict(
        shots_on_target=4,
        total_shots=12,
        shots_inside_box=6,
        shots_outside_box=3,
        blocked_shots=2,
        shots_off_goal=5,
        expected_goals=1.2,
    )
    d.update(kwargs)
    return SimpleNamespace(**d)


def _fx(fid: int, day: int, home: int = 10, away: int = 2):
    return SimpleNamespace(
        id=fid,
        kickoff_at=datetime(2025, 1, day, tzinfo=timezone.utc),
        home_team_id=home,
        away_team_id=away,
        goals_home=1,
        goals_away=0,
        status="FT",
    )


LB_OK = {
    "league_avg_xg_for": 1.2,
    "league_avg_xg_conceded": 1.2,
    "league_avg_sot_for": 3.5,
    "league_avg_sot_conceded": 3.5,
}


def _ctx(team_fixtures: list, opponent_fixtures: list, *, team_id: int = 10, opponent_id: int = 20) -> V10PriorContext:
    stats_map: dict = {}
    for f in team_fixtures:
        stats_map[(int(f.id), team_id)] = _stat()
    for f in opponent_fixtures:
        other = int(f.away_team_id) if int(f.home_team_id) == opponent_id else int(f.home_team_id)
        stats_map[(int(f.id), other)] = _stat()
    return V10PriorContext(
        season_id=1,
        cutoff_kickoff=datetime(2025, 6, 1, tzinfo=timezone.utc),
        cutoff_fixture_id=999,
        team_id=team_id,
        opponent_id=opponent_id,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=3.5,
        stats_map=stats_map,
        team_prior_count=len(team_fixtures),
        opponent_prior_count=len(opponent_fixtures),
        team_prior_fixtures=team_fixtures,
        opponent_prior_fixtures=opponent_fixtures,
        league_baselines={},
    )


def test_insufficient_xg_sample():
    team_fx = [_fx(i, i, home=10, away=90 + i) for i in range(1, 7)]
    opp_fx = [_fx(i, i, home=88 + i, away=20) for i in range(1, 7)]
    ctx = _ctx(team_fx, opp_fx)
    # Solo prime 3 partite con xG per la squadra 10 → xg_n < 5
    for f in team_fx[:3]:
        ctx.stats_map[(int(f.id), 10)] = _stat(expected_goals=None)
    comp, _miss, status, tn, _on = compute_xg_chance_quality_component(
        ctx,
        team_fx,
        league_baselines=LB_OK,
    )
    assert comp is None
    assert status == "insufficient_xg_sample"
    assert tn < 5


def test_missing_xg_league_baseline():
    team_fx = [_fx(i, i, home=10, away=90 + i) for i in range(1, 7)]
    opp_fx = [_fx(i, i, home=88 + i, away=20) for i in range(1, 7)]
    ctx = _ctx(team_fx, opp_fx)
    bad_lb = {**LB_OK, "league_avg_xg_for": 0.0}
    comp, _miss, status, _tn, _on = compute_xg_chance_quality_component(
        ctx,
        team_fx,
        league_baselines=bad_lb,
    )
    assert comp is None
    assert status == "missing_required_xg_league_baseline"


def test_ok_component_structure():
    team_fx = [_fx(i, i, home=10, away=90 + i) for i in range(1, 7)]
    opp_fx = [_fx(i, i, home=88 + i, away=20) for i in range(1, 7)]
    ctx = _ctx(team_fx, opp_fx)
    comp, _miss, status, tn, on = compute_xg_chance_quality_component(
        ctx,
        team_fx,
        league_baselines=LB_OK,
    )
    assert comp is not None
    assert status == "ok"
    assert tn >= 5 and on >= 5
    assert len(comp["inputs"]) == 5
    assert comp["value"] is not None
