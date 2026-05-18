"""Test Player layer v1.1 (stage 6) — selezione, pesi, baseline, no import circolari."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.predictions_v11.player_layer_feature_sources import (
    PLAYER_INTERNAL_WEIGHTS,
    PLAYER_NUMERIC_INPUT_ORDER,
)
from app.services.predictions_v11.player_layer_strict import (
    MissingPlayerLeagueBaselineError,
    _ProfileRow,
    compute_league_player_baselines_strict,
    select_top_player_profiles,
    team_signals_from_top,
)


def _profile(
    *,
    api_player_id: int,
    minutes: float = 500,
    sot90: float = 0.5,
    shots90: float = 2.0,
    impact: float = 10.0,
    reliability: int = 80,
) -> _ProfileRow:
    p = SimpleNamespace(
        api_player_id=api_player_id,
        minutes_total=Decimal(str(minutes)),
        shots_on_per90=Decimal(str(sot90)),
        shots_total_per90=Decimal(str(shots90)),
        team_sot_share=Decimal("0.2"),
        team_shots_share=Decimal("0.15"),
        recent_minutes_last5=Decimal("200"),
        avg_rating=Decimal("7.0"),
        reliability_score=reliability,
        shooting_impact_score=Decimal(str(impact)),
    )
    return _ProfileRow(profile=p, name=f"P{api_player_id}", position="FW")


def test_internal_weights_sum_to_one():
    total = sum(PLAYER_INTERNAL_WEIGHTS[k] for k in PLAYER_NUMERIC_INPUT_ORDER)
    assert abs(total - 1.0) < 1e-9


def test_select_top_five_min_three():
    rows = [
        _profile(api_player_id=1, impact=30),
        _profile(api_player_id=2, impact=20),
        _profile(api_player_id=3, impact=10),
        _profile(api_player_id=4, impact=5, minutes=50),
        _profile(api_player_id=5, impact=1),
    ]
    top = select_top_player_profiles(rows)
    assert len(top) == 3
    assert [r.profile.api_player_id for r in top] == [1, 2, 3]


def test_insufficient_when_fewer_than_three_eligible():
    rows = [_profile(api_player_id=1), _profile(api_player_id=2, minutes=50)]
    top = select_top_player_profiles(rows)
    assert len(top) == 1


def test_team_signals_averages():
    top = select_top_player_profiles(
        [
            _profile(api_player_id=1, sot90=1.0),
            _profile(api_player_id=2, sot90=3.0),
            _profile(api_player_id=3, sot90=2.0),
        ],
    )
    sig = team_signals_from_top(top)
    assert sig["top_players_sot_per90_signal"] == pytest.approx(2.0)


def test_league_baseline_zero_raises(monkeypatch):
    class _FakeSession:
        def scalars(self, *_a, **_k):
            return []

    with pytest.raises(MissingPlayerLeagueBaselineError):
        compute_league_player_baselines_strict(_FakeSession(), season_year=2025, league_id=1)


def test_no_circular_import_from_explanation():
    import importlib

    mod = importlib.import_module("app.services.predictions_v11.player_layer_strict")
    assert "sot_fixture_explanation_service" not in mod.__file__
