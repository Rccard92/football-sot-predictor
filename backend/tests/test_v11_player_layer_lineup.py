"""Test Player layer lineup-adjusted (stage 7B)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.predictions_v11.player_layer_feature_sources import (
    LINEUP_INTERNAL_WEIGHTS,
    LINEUP_MODE_STABLE_INPUT_ORDER,
    LINEUP_MODE_STABLE_WEIGHTS,
    LINEUP_NUMERIC_INPUT_ORDER,
    LINEUP_STARTER_TO_TOP_PLAYERS_SIGNAL,
    PLAYER_NUMERIC_INPUT_ORDER,
)
from app.services.predictions_v11.player_layer_lineup_helpers import (
    TOP_SHOOTERS_TOTAL,
    classify_top_shooters_in_lineup,
    lineup_presence_absence_signals,
    normalize_absence_signal,
    normalize_presence_signal,
    select_top_shooter_api_ids,
)


def _profile(
    api_player_id: int,
    *,
    impact: float = 10.0,
    sot90: float = 0.5,
    minutes: float = 500,
    reliability: int = 80,
) -> SimpleNamespace:
    return SimpleNamespace(
        api_player_id=api_player_id,
        minutes_total=Decimal(str(minutes)),
        shots_on_per90=Decimal(str(sot90)),
        shots_total_per90=Decimal("2.0"),
        shooting_impact_score=Decimal(str(impact)),
        reliability_score=reliability,
        team_sot_share=Decimal("0.1"),
        team_shots_share=Decimal("0.1"),
        recent_minutes_last5=Decimal("100"),
        avg_rating=Decimal("7.0"),
    )


def test_lineup_internal_weights_sum_to_one():
    total = sum(LINEUP_INTERNAL_WEIGHTS[k] for k in LINEUP_NUMERIC_INPUT_ORDER)
    assert abs(total - 1.0) < 1e-9


def test_lineup_stable_weights_sum_to_one():
    total = sum(LINEUP_MODE_STABLE_WEIGHTS[k] for k in LINEUP_MODE_STABLE_INPUT_ORDER)
    assert abs(total - 1.0) < 1e-9


def test_starter_to_top_players_maps_all_seven():
    assert set(LINEUP_STARTER_TO_TOP_PLAYERS_SIGNAL.values()) == set(PLAYER_NUMERIC_INPUT_ORDER)
    assert len(LINEUP_STARTER_TO_TOP_PLAYERS_SIGNAL) == 7


def test_classify_top_shooters_starting_bench_missing():
    top_ids = [1, 2, 3, 4, 5]
    profiles = {i: _profile(i) for i in top_ids}
    out = classify_top_shooters_in_lineup(
        top_ids,
        starter_api_ids={1, 2, 3},
        bench_api_ids={4},
        profiles=profiles,
    )
    assert out["top_shooters_total"] == TOP_SHOOTERS_TOTAL
    assert out["top_shooters_starting"] == 3
    assert out["top_shooters_on_bench"] == 1
    assert out["top_shooters_not_in_lineup"] == 1


def test_presence_absence_signals():
    presence, absence = lineup_presence_absence_signals(
        top_shooters_starting=3,
        top_shooters_on_bench=1,
        top_shooters_total=5,
    )
    assert presence == pytest.approx(0.6)
    assert absence == pytest.approx(1.0 - (3 + 1 * 0.35) / 5)


def test_normalize_presence_and_absence():
    lsot = 4.0
    pres_norm = normalize_presence_signal(0.6, lsot)
    assert pres_norm == pytest.approx(4.0 * (0.85 + 0.6 * 0.30))
    abs_norm = normalize_absence_signal(0.5, lsot)
    assert abs_norm == pytest.approx(4.0 * (1.0 - 0.125))


def test_select_top_shooter_api_ids_team_wide():
    profiles = {
        1: _profile(1, impact=30),
        2: _profile(2, impact=20),
        3: _profile(3, impact=15),
        99: _profile(99, impact=1, minutes=50),
    }
    ids = select_top_shooter_api_ids(profiles)
    assert ids == [1, 2, 3]
