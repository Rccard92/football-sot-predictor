from __future__ import annotations

from datetime import datetime, timezone

from app.services.sot_feature_math import (
    PriorMatch,
    compute_row_features,
    fixture_key_before,
    last_n_matches,
    mean_numeric,
)


def dt(day: int) -> datetime:
    return datetime(2025, 8, day, tzinfo=timezone.utc)


def test_fixture_key_before_no_future_ordering():
    t = dt(1)
    assert fixture_key_before(t, 1, t, 2) is True
    assert fixture_key_before(t, 2, t, 1) is False
    assert fixture_key_before(dt(1), 1, dt(2), 1) is True
    assert fixture_key_before(dt(2), 1, dt(1), 1) is False


def test_no_future_match_in_team_priors_averages():
    """Se si includesse la partita corrente nei prior, la media stagionale cambierebbe."""
    current_kick = dt(10)
    clean_priors = [
        PriorMatch(dt(1), 1, True, 2, 1),
        PriorMatch(dt(3), 2, True, 4, 1),
        PriorMatch(dt(5), 3, True, 6, 1),
    ]
    polluted = clean_priors + [
        PriorMatch(current_kick, 99, True, 100, 1),
    ]
    fb = 0.0
    clean_out = compute_row_features(
        current_kickoff=current_kick,
        team_priors=clean_priors,
        is_home_current=True,
        opponent_priors=[],
        opponent_is_home_current=False,
        league_fallback=fb,
        actual_sot=5,
    )
    bad_out = compute_row_features(
        current_kickoff=current_kick,
        team_priors=polluted,
        is_home_current=True,
        opponent_priors=[],
        opponent_is_home_current=False,
        league_fallback=fb,
        actual_sot=5,
    )
    assert clean_out["season_avg_sot_for"] == 4.0
    assert bad_out["season_avg_sot_for"] != clean_out["season_avg_sot_for"]


def test_home_away_averages_respect_side():
    priors = [
        PriorMatch(dt(1), 1, True, 10, 0),
        PriorMatch(dt(2), 2, True, 20, 0),
        PriorMatch(dt(3), 3, True, 30, 0),
        PriorMatch(dt(4), 4, False, 1, 0),
        PriorMatch(dt(5), 5, False, 2, 0),
        PriorMatch(dt(6), 6, False, 3, 0),
    ]
    fb = 5.0
    opp_side = [
        PriorMatch(dt(1), 101, False, 0, 4),
        PriorMatch(dt(2), 102, False, 0, 4),
        PriorMatch(dt(3), 103, False, 0, 4),
    ]
    out_home = compute_row_features(
        current_kickoff=dt(10),
        team_priors=priors,
        is_home_current=True,
        opponent_priors=opp_side,
        opponent_is_home_current=False,
        league_fallback=fb,
        actual_sot=7,
    )
    assert out_home["home_away_avg_sot_for"] == 20.0
    out_away = compute_row_features(
        current_kickoff=dt(10),
        team_priors=priors,
        is_home_current=False,
        opponent_priors=[
            PriorMatch(dt(1), 201, True, 0, 4),
            PriorMatch(dt(2), 202, True, 0, 4),
            PriorMatch(dt(3), 203, True, 0, 4),
        ],
        opponent_is_home_current=True,
        league_fallback=fb,
        actual_sot=7,
    )
    assert out_away["home_away_avg_sot_for"] == 2.0


def test_last5_uses_at_most_five_most_recent():
    priors = [
        PriorMatch(dt(i), i, True, i, 0) for i in range(1, 8)
    ]
    window = last_n_matches(priors, 5)
    assert [p.sot_for for p in window] == [3, 4, 5, 6, 7]
    assert mean_numeric([p.sot_for for p in window]) == 5.0

    fb = 0.0
    opp = [PriorMatch(dt(1), 1, True, 1, 1)] * 3
    out = compute_row_features(
        current_kickoff=dt(20),
        team_priors=priors,
        is_home_current=True,
        opponent_priors=opp,
        opponent_is_home_current=False,
        league_fallback=fb,
        actual_sot=9,
    )
    assert out["last5_avg_sot_for"] == 5.0


def test_actual_sot_passthrough():
    out = compute_row_features(
        current_kickoff=dt(1),
        team_priors=[],
        is_home_current=True,
        opponent_priors=[],
        opponent_is_home_current=False,
        league_fallback=0.0,
        actual_sot=8,
    )
    assert out["actual_sot"] == 8
