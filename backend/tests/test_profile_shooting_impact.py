from app.services.player_data.profile_aggregation_helpers import (
    MINUTES_FOR_IMPACT,
    compute_shooting_impact_score,
    min_max_normalize,
)


def test_min_max_normalize_single_peer():
    assert min_max_normalize(1.0, [1.0, 1.0]) == 0.5


def test_impact_requires_minimum_minutes():
    assert (
        compute_shooting_impact_score(
            minutes_total=MINUTES_FOR_IMPACT - 1,
            shots_on_per90=1.0,
            shots_total_per90=2.0,
            team_sot_share=0.1,
            recent_shots_on_last5=3,
            avg_rating=7.0,
            peer_shots_on_per90=[1.0],
            peer_shots_total_per90=[2.0],
            peer_team_sot_share=[0.1],
            peer_recent_shots_on_last5=[3],
            peer_avg_rating=[7.0],
        )
        is None
    )


def test_impact_requires_shot_per90():
    assert (
        compute_shooting_impact_score(
            minutes_total=500,
            shots_on_per90=None,
            shots_total_per90=None,
            team_sot_share=0.1,
            recent_shots_on_last5=3,
            avg_rating=7.0,
            peer_shots_on_per90=[None],
            peer_shots_total_per90=[None],
            peer_team_sot_share=[0.1],
            peer_recent_shots_on_last5=[3],
            peer_avg_rating=[7.0],
        )
        is None
    )


def test_impact_renormalizes_when_rating_null():
    score = compute_shooting_impact_score(
        minutes_total=500,
        shots_on_per90=1.0,
        shots_total_per90=2.0,
        team_sot_share=0.2,
        recent_shots_on_last5=4,
        avg_rating=None,
        peer_shots_on_per90=[0.5, 1.0, 1.5],
        peer_shots_total_per90=[1.0, 2.0, 3.0],
        peer_team_sot_share=[0.1, 0.2, 0.3],
        peer_recent_shots_on_last5=[2, 4, 6],
        peer_avg_rating=[6.0, 7.0, None],
    )
    assert score is not None
    assert 0 <= score <= 100
