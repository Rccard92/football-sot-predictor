"""Regressione: Step V3.0-A non modifica motori predizione v1.1/v2.0/v2.1."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROTECTED_PREFIXES = (
    "app/services/predictions_v11/",
    "app/services/predictions_v20/",
    "app/services/predictions_v21/",
    "app/services/backtest/v11_round_analysis_engine.py",
    "app/services/backtest/baseline_v2_0",
    "app/services/backtest/sot_v21_point_in_time_preview_service.py",
)


def test_v30_diagnostics_does_not_touch_model_engines():
    """Documenta che lo step diagnostica è read-only rispetto ai motori."""
    diagnostics_files = [
        ROOT / "app/services/backtest/round_analysis_diagnostics_loader.py",
        ROOT / "app/services/backtest/round_analysis_diagnostics_aggregator.py",
        ROOT / "app/services/backtest/round_analysis_diagnostics_service.py",
    ]
    for path in diagnostics_files:
        text = path.read_text(encoding="utf-8")
        for prefix in PROTECTED_PREFIXES:
            assert prefix not in text
        assert "compute_v11_side" not in text
        assert "SotV21PointInTimePreviewService" not in text
