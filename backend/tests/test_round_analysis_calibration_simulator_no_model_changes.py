"""Regressione: simulatore v3.0 non modifica motori predizione."""

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


def test_simulator_modules_do_not_import_model_engines():
    paths = [
        ROOT / "app/services/backtest/round_analysis_calibration_simulator.py",
        ROOT / "app/services/backtest/round_analysis_calibration_simulator_loader.py",
        ROOT / "app/services/backtest/round_analysis_calibration_simulator_service.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in PROTECTED:
            assert token not in text
