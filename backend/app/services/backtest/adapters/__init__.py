"""Adapter modelli Round Analysis."""

from app.services.backtest.adapters.sot_v11_round_analysis_adapter import SotV11RoundAnalysisAdapter
from app.services.backtest.adapters.sot_v20_round_analysis_adapter import SotV20RoundAnalysisAdapter
from app.services.backtest.adapters.sot_v21_round_analysis_adapter import SotV21RoundAnalysisAdapter

__all__ = [
    "SotV11RoundAnalysisAdapter",
    "SotV20RoundAnalysisAdapter",
    "SotV21RoundAnalysisAdapter",
]
