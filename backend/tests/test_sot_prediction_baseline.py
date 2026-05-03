from types import SimpleNamespace

import pytest

from app.services.sot_prediction_service import (
    SotPredictionService,
    WEIGHTS_BASELINE_V0_1,
    confidence_score_from_feature_row,
)


def test_baseline_weights_sum_to_one():
    assert sum(WEIGHTS_BASELINE_V0_1.values()) == pytest.approx(1.0)


def test_expected_sot_formula_numeric():
    svc = SotPredictionService()
    feats = {
        "season_avg_sot_for": 4.0,
        "opponent_season_avg_sot_conceded": 4.0,
        "home_away_avg_sot_for": 4.0,
        "opponent_home_away_avg_sot_conceded": 4.0,
        "last5_avg_sot_for": 4.0,
        "opponent_last5_avg_sot_conceded": 4.0,
        "meta": {"n_team_priors": 8, "n_opp_priors": 8, "formula_fallback_count": 0},
    }
    assert svc.expected_sot_resolved(feats, None) == 4.0


def test_expected_sot_weighted_mix():
    svc = SotPredictionService()
    feats = {
        "season_avg_sot_for": 10.0,
        "opponent_season_avg_sot_conceded": 0.0,
        "home_away_avg_sot_for": 0.0,
        "opponent_home_away_avg_sot_conceded": 0.0,
        "last5_avg_sot_for": 0.0,
        "opponent_last5_avg_sot_conceded": 0.0,
        "meta": {},
    }
    assert svc.expected_sot_resolved(feats, None) == 3.0


def test_confidence_higher_with_eight_priors_and_no_fallback():
    hi = SimpleNamespace(
        previous_matches_count=8,
        opponent_previous_matches_count=8,
        fallback_used=False,
        last5_avg_sot_for=1.0,
        opponent_last5_avg_sot_conceded=1.0,
    )
    lo = SimpleNamespace(
        previous_matches_count=2,
        opponent_previous_matches_count=2,
        fallback_used=True,
        last5_avg_sot_for=None,
        opponent_last5_avg_sot_conceded=None,
    )
    assert confidence_score_from_feature_row(hi) > confidence_score_from_feature_row(lo)


def test_confidence_caps_at_100():
    hi = SimpleNamespace(
        previous_matches_count=8,
        opponent_previous_matches_count=8,
        fallback_used=False,
        last5_avg_sot_for=1.0,
        opponent_last5_avg_sot_conceded=1.0,
    )
    assert confidence_score_from_feature_row(hi) == 100


def test_confidence_base_without_bonuses():
    mid = SimpleNamespace(
        previous_matches_count=3,
        opponent_previous_matches_count=3,
        fallback_used=False,
        last5_avg_sot_for=None,
        opponent_last5_avg_sot_conceded=None,
    )
    assert confidence_score_from_feature_row(mid) == 50
