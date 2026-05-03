import pytest

from app.services.sot_prediction_service import SotPredictionService, WEIGHTS_BASELINE_V0_1


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
    assert svc.expected_sot_from_features(feats) == 4.0


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
    assert svc.expected_sot_from_features(feats) == 3.0


def test_confidence_higher_with_eight_priors_and_no_fallback():
    svc = SotPredictionService()
    hi = {
        "meta": {"n_team_priors": 8, "n_opp_priors": 8, "formula_fallback_count": 0},
    }
    lo = {
        "meta": {"n_team_priors": 2, "n_opp_priors": 2, "formula_fallback_count": 6},
    }
    assert svc.confidence_score(hi) > svc.confidence_score(lo)


def test_confidence_without_meta_is_neutral():
    svc = SotPredictionService()
    assert svc.confidence_score({}) == 50
