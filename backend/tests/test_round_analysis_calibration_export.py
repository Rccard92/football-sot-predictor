"""Test export calibrazione v3.0."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_calibration_export import (
    build_calibration_csv,
    build_calibration_report,
)
from app.services.backtest.round_analysis_v21_trace_helpers import extract_v21_calibration_fields

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def test_extract_v21_calibration_fields():
    expl = {
        "home": {
            "base_anchor_sot": 4.5,
            "weighted_macro_multiplier": 1.02,
            "macros": [
                {"key": "player_layer", "macro_index": 1.05, "status": "available"},
                {"key": "home_away_split", "macro_index": 0.98, "status": "available"},
            ],
        },
        "away": {"macros": [{"key": "lineups", "macro_index": 1.01, "status": "available"}]},
        "fallback_count": 0,
        "leakage_guard": True,
        "actuals_used_as_input": False,
    }
    out = extract_v21_calibration_fields(expl)
    assert out["player_layer_index_home"] == 1.05
    assert out["actuals_used_as_input"] is False
    assert out["leakage_guard"] is True


@patch("app.services.backtest.round_analysis_calibration_export._select_analyses_for_calibration")
def test_build_calibration_report_structure(mock_select):
    db = MagicMock()
    comp = SimpleNamespace(name="Serie A")
    db.get.return_value = comp

    analysis = SimpleNamespace(
        id=10,
        competition_id=1,
        season_year=2025,
        round_number=10,
        analysis_version=1,
        status="completed",
        config_json={"models": [V11, V21]},
        model_summary_json={},
    )

    fixture_row = SimpleNamespace(
        status="ok",
        fixture_id=95,
        home_team_name="A",
        away_team_name="B",
        actual_home_sot=5,
        actual_away_sot=4,
        actual_total_sot=9,
        models_json={
            V11: {
                "status": "ok",
                "predicted_total_sot": 10.0,
                "aggressive_advice": "GIOCA",
                "aggressive_outcome": "WIN",
                "cautious_advice": "GIOCA",
                "cautious_outcome": "WIN",
            },
            V21: {
                "status": "ok",
                "predicted_total_sot": 10.2,
                "aggressive_advice": "GIOCA",
                "aggressive_outcome": "WIN",
                "cautious_advice": "NON GIOCARE",
                "cautious_outcome": "LOSS",
            },
        },
        explanation_json={
            V21: {
                "home": {"macros": [{"key": "player_layer", "macro_index": 1.0}]},
                "away": {"macros": []},
                "leakage_guard": True,
                "actuals_used_as_input": False,
            },
        },
    )

    with patch.object(db, "query") as q:
        q.return_value.filter.return_value.all.return_value = []
        mock_select.return_value = ([analysis], [], {10: [fixture_row]})
        report = build_calibration_report(
            db,
            competition_id=1,
            season_year=2025,
        )

    assert report["report_type"] == "round_analysis_calibration_v3"
    assert report["metadata"]["competition_name"] == "Serie A"
    assert len(report["fixtures"]) == 1
    v21 = report["fixtures"][0]["models"][V21]
    assert v21["trace_summary_json"]["actuals_used_as_input"] is False
    assert "v21_calibration" in v21["trace_summary_json"]


def test_build_calibration_csv_header():
    report = {
        "fixtures": [
            {
                "round_number": 10,
                "fixture_id": 95,
                "home_team": "A",
                "away_team": "B",
                "actual_total_sot": 9,
                "models": {
                    V11: {
                        "predicted_total_sot": 10,
                        "abs_error": 1,
                        "bias": 1,
                        "aggressive_line": 8.5,
                        "aggressive_outcome": "WIN",
                        "cautious_line": 9.5,
                        "cautious_outcome": "LOSS",
                        "aggressive_advice": "GIOCA",
                        "confidence": "Media",
                        "trace_summary_json": {},
                    },
                },
            },
        ],
    }
    with patch(
        "app.services.backtest.round_analysis_calibration_export.build_calibration_report",
        return_value=report,
    ):
        csv_body = build_calibration_csv(MagicMock(), competition_id=1, season_year=2025)
    header = csv_body.lstrip("\ufeff").splitlines()[0]
    assert "round_number" in header
    assert "model_key" in header
    assert "predicted_total_sot" in header
    assert "actual_bucket" in header
    assert "10,95" in csv_body
