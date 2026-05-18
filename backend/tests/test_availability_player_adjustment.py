"""Penalità Player layer da record applicabili."""

from unittest.mock import MagicMock

from app.services.availability.availability_player_adjustment import (
    MAX_PENALTY,
    compute_player_availability_adjustment,
)


def _av_row(api_player_id: int, status: str = "out") -> MagicMock:
    r = MagicMock()
    r.api_player_id = api_player_id
    r.availability_status = status
    r.player_name = f"Player {api_player_id}"
    return r


def test_no_applicable_records():
    delta, blob = compute_player_availability_adjustment(
        [],
        [1, 2, 3],
        {},
        fixture_id=10,
        api_fixture_id=99,
    )
    assert delta == 0.0
    assert blob["status"] == "no_applicable_records_for_fixture"


def test_top_shooter_penalty_capped():
    applicable = [_av_row(101, "injured"), _av_row(102, "suspended")]
    profiles = {101: MagicMock(), 102: MagicMock()}
    delta, blob = compute_player_availability_adjustment(
        applicable,
        [101, 102, 103],
        profiles,
        fixture_id=10,
        api_fixture_id=99,
    )
    assert blob["status"] == "applied"
    assert delta <= 0.0
    assert delta >= MAX_PENALTY
    assert len(blob["top_shooters_unavailable"]) >= 1
