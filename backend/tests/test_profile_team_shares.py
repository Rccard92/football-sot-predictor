from app.services.player_data.profile_aggregation_helpers import team_share


def test_team_share_null_when_denominator_zero():
    assert team_share(5, 0) is None


def test_team_share_computed():
    assert team_share(3, 10) == 0.3
