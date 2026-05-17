from datetime import datetime, timezone

from app.services.player_data.profile_aggregation_helpers import (
    MatchRowView,
    PlayerSeasonAgg,
    build_recent_windows,
    build_team_fixture_order,
    recent_fixture_ids_before_latest,
)


def test_recent_window_five_before_latest():
    fids = [1, 2, 3, 4, 5, 6, 7]
    assert recent_fixture_ids_before_latest(fids, window=5) == [2, 3, 4, 5, 6]


def test_recent_window_fewer_than_five():
    fids = [10, 11, 12]
    assert recent_fixture_ids_before_latest(fids, window=5) == [10]


def test_recent_window_only_one_fixture():
    assert recent_fixture_ids_before_latest([99], window=5) == []


def _row(fixture_id: int, minutes: int, shots: int) -> MatchRowView:
    return MatchRowView(
        fixture_id=fixture_id,
        api_team_id=100,
        api_player_id=1,
        player_id="p",
        team_id=1,
        kickoff_at=datetime(2025, 1, fixture_id, tzinfo=timezone.utc),
        minutes=minutes,
        substitute=False,
        rating=None,
        shots_total=shots,
        shots_on=shots,
        goals_total=None,
        goals_assists=None,
        passes_key=None,
    )


def test_aggregate_recent_last5_sums():
    rows = [_row(i, 90, i) for i in range(1, 8)]
    order = build_team_fixture_order(rows)
    windows = build_recent_windows(order)
    recent_ids = windows[100]
    agg = PlayerSeasonAgg(api_team_id=100, api_player_id=1, player_id="p", team_id=1, rows=rows)
    base = agg.aggregate_base(recent_ids)
    assert base["recent_shots_total_last5"] == 2 + 3 + 4 + 5 + 6
    assert base["recent_minutes_last5"] == 5 * 90
