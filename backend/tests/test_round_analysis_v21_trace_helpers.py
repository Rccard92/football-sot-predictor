"""Test helper trace v2.1."""

from __future__ import annotations

from app.services.backtest.round_analysis_v21_trace_helpers import (
    extract_v21_calibration_fields,
    extract_v21_macro_averages,
    extract_v21_split_status,
    split_status_summary,
)


def test_split_avg_from_home_away_split_key():
    expl = {
        "home": {
            "macros": [{"key": "home_away_split", "macro_index": 1.02, "status": "available"}],
        },
        "away": {
            "macros": [{"key": "home_away_split", "macro_index": 0.98, "status": "available"}],
        },
    }
    out = extract_v21_macro_averages(expl)
    assert out["split_avg"] == 1.0


def test_split_status_available():
    expl = {
        "home": {"macros": [{"key": "home_away_split", "macro_index": 1.0, "status": "available"}]},
        "away": {"macros": [{"key": "home_away_split", "macro_index": 1.0, "status": "available"}]},
    }
    assert extract_v21_split_status(expl) == "available"


def test_split_status_partial():
    expl = {
        "home": {"macros": [{"key": "home_away_split", "macro_index": 1.0, "status": "partial_low_sample"}]},
        "away": {"macros": [{"key": "home_away_split", "macro_index": 1.0, "status": "available"}]},
    }
    assert extract_v21_split_status(expl) == "partial_low_sample"


def test_split_status_missing():
    assert extract_v21_split_status(None) == "missing"
    assert extract_v21_split_status({}) == "missing"


def test_calibration_fields_split_index():
    expl = {
        "home": {"macros": [{"key": "home_away_split", "macro_index": 1.05, "status": "available"}]},
        "away": {"macros": [{"key": "home_away_split", "macro_index": 1.01, "status": "available"}]},
        "leakage_guard": True,
    }
    out = extract_v21_calibration_fields(expl)
    assert out["split_index_home"] == 1.05
    assert out["split_status"] == "available"


def test_split_status_summary():
    rows = [
        {
            "analysis_id": 1,
            "fixture_id": 10,
            "explanation_v21": {
                "home": {"macros": [{"key": "home_away_split", "status": "available", "macro_index": 1.0}]},
                "away": {"macros": [{"key": "home_away_split", "status": "available", "macro_index": 1.0}]},
            },
        },
        {
            "analysis_id": 1,
            "fixture_id": 10,
            "explanation_v21": {
                "home": {"macros": [{"key": "home_away_split", "status": "available", "macro_index": 1.0}]},
                "away": {"macros": [{"key": "home_away_split", "status": "available", "macro_index": 1.0}]},
            },
        },
    ]
    summary = split_status_summary(rows)
    assert summary["available"] == 1
