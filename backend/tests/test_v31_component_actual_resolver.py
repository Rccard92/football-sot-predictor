"""Test resolver actual componenti post-match."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.backtest.v31_component_actual_resolver import resolve_actual_component_value


def _stat(**kwargs):
    st = MagicMock()
    for k, v in kwargs.items():
        setattr(st, k, v)
    return st


HOME_STAT = _stat(
    shots_on_target=5.0,
    total_shots=12.0,
    expected_goals=1.2,
    shots_inside_box=8.0,
)
AWAY_STAT = _stat(shots_on_target=3.0, total_shots=9.0, expected_goals=0.8)


def _load_stat(_db, fixture_id: int, team_id: int):
    if team_id == 1:
        return HOME_STAT
    if team_id == 2:
        return AWAY_STAT
    return None


@pytest.fixture
def db():
    return MagicMock()


@patch(
    "app.services.backtest.v31_component_actual_resolver._load_team_stat",
    side_effect=_load_stat,
)
def test_direct_avg_sot_for(_mock_load, db):
    r = resolve_actual_component_value(
        db,
        fixture_id=100,
        team_id=1,
        opponent_team_id=2,
        variable_key="avg_sot_for",
    )
    assert r.actual_comparison_type == "direct"
    assert r.value == 5.0
    assert r.status == "available"


@patch(
    "app.services.backtest.v31_component_actual_resolver._load_team_stat",
    side_effect=_load_stat,
)
def test_derived_shot_accuracy(_mock_load, db):
    r = resolve_actual_component_value(
        db,
        fixture_id=100,
        team_id=1,
        opponent_team_id=2,
        variable_key="shot_accuracy",
    )
    assert r.actual_comparison_type == "derived"
    assert r.value == pytest.approx(5.0 / 12.0, rel=1e-3)


@patch(
    "app.services.backtest.v31_component_actual_resolver._load_team_stat",
    side_effect=_load_stat,
)
def test_opponent_conceded_sot(_mock_load, db):
    r = resolve_actual_component_value(
        db,
        fixture_id=100,
        team_id=1,
        opponent_team_id=2,
        variable_key="opponent_conceded_sot_avg",
    )
    assert r.actual_comparison_type == "direct"
    assert r.value == 3.0


@patch(
    "app.services.backtest.v31_component_actual_resolver._load_team_stat",
    side_effect=_load_stat,
)
def test_diagnostic_only_macro(_mock_load, db):
    r = resolve_actual_component_value(
        db,
        fixture_id=100,
        team_id=1,
        opponent_team_id=2,
        variable_key="recent_form_index",
    )
    assert r.actual_comparison_type == "diagnostic_only"
    assert r.value is None
    assert r.status == "diagnostic_only"
