from app.services.player_data.profile_aggregation_helpers import (
    MINUTES_FOR_IMPACT,
    compute_reliability_score,
)


def test_reliability_tiers():
    low = compute_reliability_score(
        minutes_total=MINUTES_FOR_IMPACT - 1,
        matches_played=2,
        recent_minutes_last5=None,
        avg_rating=None,
        has_shot_data=False,
    )
    assert low < 25

    mid = compute_reliability_score(
        minutes_total=500,
        matches_played=6,
        recent_minutes_last5=200.0,
        avg_rating=7.0,
        has_shot_data=True,
    )
    assert 55 <= mid <= 100

    high = compute_reliability_score(
        minutes_total=1000,
        matches_played=15,
        recent_minutes_last5=400.0,
        avg_rating=7.5,
        has_shot_data=True,
    )
    assert high >= 85
