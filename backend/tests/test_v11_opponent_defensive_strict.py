"""Test resistenza difensiva avversaria strict v1.1."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.predictions_v11.opponent_stats_agg import agg_conceded_by_opponent
from app.services.predictions_v11.opponent_defensive_resistance_strict import (
    compute_opponent_defensive_resistance_component,
)
from app.services.predictions_v10.v10_prior_context import V10PriorContext


def _stat(**kwargs):
    return SimpleNamespace(**kwargs)


def _fx(fid: int, kickoff: datetime, home: int = 20, away: int = 30, gh: int = 1, ga: int = 0):
    return SimpleNamespace(
        id=fid,
        kickoff_at=kickoff,
        home_team_id=home,
        away_team_id=away,
        goals_home=gh,
        goals_away=ga,
        status="FT",
    )


def _league_baselines():
    return {
        "league_avg_sot_conceded": 3.5,
        "league_avg_total_shots_conceded": 12.0,
        "league_avg_inside_box_shots_conceded": 5.0,
        "league_avg_outside_box_shots_conceded": 4.0,
        "league_avg_blocked_shots_conceded": 2.0,
    }


def test_agg_conceded_by_opponent():
    """Stats della squadra che affronta l'avversario = concessi."""
    fixtures = [
        _fx(1, datetime(2025, 1, 1, tzinfo=timezone.utc), home=20, away=99),
        _fx(2, datetime(2025, 1, 2, tzinfo=timezone.utc), home=88, away=20),
    ]
    stats_map = {
        (1, 99): _stat(shots_on_target=5, total_shots=10, shots_inside_box=4, shots_outside_box=2, blocked_shots=1),
        (2, 88): _stat(shots_on_target=3, total_shots=8, shots_inside_box=2, shots_outside_box=1, blocked_shots=1),
    }
    agg = agg_conceded_by_opponent(fixtures=fixtures, stats_map=stats_map, opponent_id=20)
    assert agg["sot_mean"] == 4.0
    assert agg["sot_n"] == 2


def test_insufficient_opponent_sample():
    fixtures = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc)) for i in range(1, 4)]
    ctx = V10PriorContext(
        season_id=1,
        cutoff_kickoff=datetime(2025, 6, 1, tzinfo=timezone.utc),
        cutoff_fixture_id=999,
        team_id=10,
        opponent_id=20,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=3.5,
        stats_map={},
        team_prior_count=0,
        opponent_prior_count=len(fixtures),
        team_prior_fixtures=[],
        opponent_prior_fixtures=fixtures,
        league_baselines={},
    )
    comp, missing, status, n = compute_opponent_defensive_resistance_component(ctx, league_baselines=_league_baselines())
    assert comp is None
    assert status == "insufficient_sample"
    assert n == 3


def test_valid_six_inputs():
    opponent_fixtures = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=20, away=90 + i) for i in range(1, 7)]
    stats_map = {}
    for f in opponent_fixtures:
        other = int(f.away_team_id)
        stats_map[(int(f.id), other)] = _stat(
            shots_on_target=4,
            total_shots=12,
            shots_inside_box=6,
            shots_outside_box=3,
            blocked_shots=2,
        )
    ctx = V10PriorContext(
        season_id=1,
        cutoff_kickoff=datetime(2025, 6, 1, tzinfo=timezone.utc),
        cutoff_fixture_id=999,
        team_id=10,
        opponent_id=20,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=3.5,
        stats_map=stats_map,
        team_prior_count=0,
        opponent_prior_count=len(opponent_fixtures),
        team_prior_fixtures=[],
        opponent_prior_fixtures=opponent_fixtures,
        league_baselines={},
    )
    comp, missing, status, _ = compute_opponent_defensive_resistance_component(ctx, league_baselines=_league_baselines())
    assert comp is not None
    assert status == "ok"
    assert len(comp["inputs"]) == 6
    wsum = sum(float(inp["internal_weight"]) for inp in comp["inputs"])
    assert abs(wsum - 1.0) < 1e-6
