"""Regressione: value selector v3.0-C non modifica motori predizione."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROTECTED = (
    "predictions_v11",
    "predictions_v20",
    "predictions_v21",
    "compute_v11_side",
    "SotV21PointInTimePreviewService",
)


def test_value_selector_modules_do_not_import_model_engines():
    paths = [
        ROOT / "app/services/backtest/round_analysis_low_total_risk_v2.py",
        ROOT / "app/services/backtest/round_analysis_value_selector_helpers.py",
        ROOT / "app/services/backtest/round_analysis_value_selector_strategies.py",
        ROOT / "app/services/backtest/round_analysis_calibration_simulator.py",
        ROOT / "app/services/backtest/round_analysis_calibration_simulator_loader.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in PROTECTED:
            assert token not in text, f"{token} found in {path.name}"
