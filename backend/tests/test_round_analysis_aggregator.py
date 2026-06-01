"""Test aggregatore analisi giornata (Step I)."""

from __future__ import annotations

from app.services.backtest.round_analysis_aggregator import RoundAnalysisAggregator
from app.services.backtest.round_analysis_data_prep_service import FixturePreflight, RoundAnalysisPrepResult


def test_data_quality_badge_critico_when_no_lineups():
    agg = RoundAnalysisAggregator()
    prep = RoundAnalysisPrepResult(
        fixtures=[],
        fixture_preflights={
            1: FixturePreflight(1, False, False, 0),
            2: FixturePreflight(2, False, True, 0),
        },
        prep_warnings=["lineup_missing"],
    )
    summary = agg.build_data_quality_summary(prep=prep, fixture_results=[])
    assert summary["badge"] == "Critico"
    assert summary["fixtures_with_lineup"] == 0


def test_model_summary_hit_rate():
    agg = RoundAnalysisAggregator()
    rows = [
        {
            "status": "ok",
            "actual_total_sot": 10,
            "models_json": {
                "baseline_v1_1_sot": {
                    "predicted_total_sot": 9.0,
                    "aggressive_outcome": "WIN",
                    "cautious_outcome": "LOSS",
                    "aggressive_advice": "GIOCA",
                    "cautious_advice": "NON GIOCARE",
                },
            },
        },
        {
            "status": "ok",
            "actual_total_sot": 8,
            "models_json": {
                "baseline_v1_1_sot": {
                    "predicted_total_sot": 8.5,
                    "aggressive_outcome": "LOSS",
                    "cautious_outcome": "WIN",
                    "aggressive_advice": "NON GIOCARE",
                    "cautious_advice": "GIOCA",
                },
            },
        },
    ]
    out = agg.build_model_summary(models=["baseline_v1_1_sot"], fixture_results=rows)
    m = out["baseline_v1_1_sot"]
    assert m["aggressive_wins"] == 1
    assert m["aggressive_losses"] == 1
    assert m["aggressive_hit_rate"] == 50.0
    assert m["mae"] == 0.75
