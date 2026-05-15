"""Test split casa/trasferta strict v1.1."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.predictions_v11.home_away_split_strict import compute_home_away_split_component
from app.services.predictions_v11.split_fixtures import opponent_split_fixtures, team_split_fixtures
from app.services.predictions_v10.v10_prior_context import V10PriorContext


def _stat(**kwargs):
    return SimpleNamespace(**kwargs)


def _fx(fid: int, kickoff: datetime, home: int, away: int):
    return SimpleNamespace(
        id=fid,
        kickoff_at=kickoff,
        home_team_id=home,
        away_team_id=away,
        goals_home=1,
        goals_away=0,
        status="FT",
    )


def _league_baselines():
    return {
        "home_league_split_avg_sot_for": 3.5,
        "home_league_split_avg_sot_conceded": 3.4,
        "home_league_split_avg_total_shots_for": 12.0,
        "home_league_split_avg_total_shots_conceded": 11.5,
        "away_league_split_avg_sot_for": 3.2,
        "away_league_split_avg_sot_conceded": 3.3,
        "away_league_split_avg_total_shots_for": 11.0,
        "away_league_split_avg_total_shots_conceded": 11.2,
    }


def test_team_split_filter_home():
    team_id, opp_id = 10, 20
    fixtures = [
        _fx(1, datetime(2025, 1, 1, tzinfo=timezone.utc), home=10, away=99),
        _fx(2, datetime(2025, 1, 2, tzinfo=timezone.utc), home=88, away=10),
    ]
    home_only = team_split_fixtures(fixtures, team_id, is_home_context=True)
    assert len(home_only) == 1
    assert int(home_only[0].home_team_id) == 10


def test_opponent_split_filter_when_team_home():
    opp_id = 20
    opp_fixtures = [
        _fx(1, datetime(2025, 1, 1, tzinfo=timezone.utc), home=20, away=99),
        _fx(2, datetime(2025, 1, 2, tzinfo=timezone.utc), home=88, away=20),
    ]
    away_only = opponent_split_fixtures(opp_fixtures, opp_id, team_is_home=True)
    assert len(away_only) == 1
    assert int(away_only[0].away_team_id) == 20


def test_insufficient_split_sample():
    team_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=10, away=90 + i) for i in range(1, 4)]
    opp_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=20, away=80 + i) for i in range(1, 7)]
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
        team_prior_count=len(team_fx),
        opponent_prior_count=len(opp_fx),
        team_prior_fixtures=team_fx,
        opponent_prior_fixtures=opp_fx,
        league_baselines={},
    )
    comp, _, status, team_n, opp_n = compute_home_away_split_component(
        ctx, team_fx, league_baselines=_league_baselines(),
    )
    assert comp is None
    assert status == "insufficient_split_sample"
    assert team_n == 3
    assert opp_n == 6


def test_valid_five_inputs_home_context():
    team_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=10, away=90 + i) for i in range(1, 7)]
    opp_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=88 + i, away=20) for i in range(1, 7)]
    stats_map = {}
    for f in team_fx:
        stats_map[(int(f.id), 10)] = _stat(shots_on_target=4, total_shots=12)
    for f in opp_fx:
        other = int(f.home_team_id)
        stats_map[(int(f.id), other)] = _stat(shots_on_target=3, total_shots=10)
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
        team_prior_count=len(team_fx),
        opponent_prior_count=len(opp_fx),
        team_prior_fixtures=team_fx,
        opponent_prior_fixtures=opp_fx,
        league_baselines={},
    )
    comp, _, status, _, _ = compute_home_away_split_component(
        ctx, team_fx, league_baselines=_league_baselines(),
    )
    assert comp is not None
    assert status == "ok"
    assert comp["split_context"] == "home"
    assert comp["opponent_split_context"] == "away"
    assert len(comp["inputs"]) == 5
    wsum = sum(float(inp["internal_weight"]) for inp in comp["inputs"])
    assert abs(wsum - 1.0) < 1e-6
