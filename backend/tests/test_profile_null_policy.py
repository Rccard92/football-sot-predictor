from app.services.player_data.profile_aggregation_helpers import (
    MatchRowView,
    PlayerSeasonAgg,
    event_count,
    is_played_minutes,
)


def test_minutes_null_excludes_row():
    assert is_played_minutes(None) is False
    assert event_count(None, 3) is None


def test_minutes_zero_excludes_row():
    assert is_played_minutes(0) is False
    assert event_count(0, 2) is None


def test_minutes_positive_null_shot_becomes_zero():
    assert event_count(90, None) == 0
    assert event_count(45, 2) == 2


def test_aggregate_excludes_non_played():
    agg = PlayerSeasonAgg(api_team_id=1, api_player_id=10, player_id="x", team_id=1)
    agg.rows = [
        MatchRowView(
            fixture_id=1,
            api_team_id=1,
            api_player_id=10,
            player_id="x",
            team_id=1,
            kickoff_at=None,
            minutes=None,
            substitute=None,
            rating=None,
            shots_total=None,
            shots_on=None,
            goals_total=None,
            goals_assists=None,
            passes_key=None,
        ),
        MatchRowView(
            fixture_id=2,
            api_team_id=1,
            api_player_id=10,
            player_id="x",
            team_id=1,
            kickoff_at=None,
            minutes=90,
            substitute=False,
            rating=None,
            shots_total=None,
            shots_on=None,
            goals_total=None,
            goals_assists=None,
            passes_key=None,
        ),
    ]
    base = agg.aggregate_base(set())
    assert base["matches_played"] == 1
    assert base["shots_total"] == 0
    assert base["shots_on"] == 0
