"""Test preflight storico analisi giornata."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.services.backtest.round_analysis_preflight import (
    accordion_summary_from_models,
    build_no_prediction_block,
    preflight_round_history,
    season_label_from_year,
)


def test_season_label():
    assert season_label_from_year(2025) == "2025/2026"


def test_no_prediction_block_structure():
    block = build_no_prediction_block(
        "baseline_v1_1_sot",
        prior_home=0,
        prior_away=0,
    )
    assert block["status"] == "no_prediction"
    assert block["reason"] == "INSUFFICIENT_HISTORY"
    assert block["aggressive_line"] is None


@patch("app.services.backtest.round_analysis_preflight._prior_counts_for_fixture")
@patch("app.services.backtest.round_analysis_preflight.compute_first_recommended_round")
def test_preflight_insufficient_history_round_1(mock_first_round, mock_prior):
    mock_first_round.return_value = 3
    mock_prior.return_value = (0, 0)
    db = MagicMock()
    cand = MagicMock()
    cand.fixture_id = 10
    cand.has_team_stats = True
    fx = MagicMock()
    fx.id = 10
    db.get.return_value = fx

    result = preflight_round_history(
        db,
        competition_id=1,
        season_year=2025,
        fixtures=[cand],
        prep=None,
    )
    assert result.insufficient_history is True
    assert result.min_prior_matches_home == 0
    assert result.data_quality_status == "critical"


def test_accordion_no_global_motive_when_model_has_predictions():
    model_summary = {
        BASELINE_SOT_MODEL_VERSION_V11_SOT: {
            "predictions_available": 5,
            "display": "OK",
        },
    }
    acc = accordion_summary_from_models(model_summary, insufficient_history=True)
    assert acc.get("v1.1") == "OK"
    assert "motive" not in acc
