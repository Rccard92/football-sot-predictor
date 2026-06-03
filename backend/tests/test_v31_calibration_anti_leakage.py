"""Unit test anti-leakage v3.1 — solo row.features."""

from __future__ import annotations

from app.services.backtest.v31_calibration_anti_leakage import (
    find_forbidden_in_features,
    validate_v31_features_no_leakage,
    validate_v31_rows,
)


def test_actuals_used_as_input_allowed_in_features():
    features = {
        "data_quality": {"actuals_used_as_input": False, "leakage_guard": True},
        "team_raw_features": {"home": {"avg_sot_for": 5.0}},
    }
    assert validate_v31_features_no_leakage(features)["status"] == "ok"


def test_predicted_total_in_features_fails():
    features = {"team_raw_features": {"home": {"predicted_total_sot": 8.5}}}
    check = validate_v31_features_no_leakage(features)
    assert check["status"] == "failed"
    assert "predicted_total_sot" in str(check["forbidden_fields_found"])


def test_comparisons_not_scanned_in_rows():
    rows = [
        {
            "metadata": {"fixture_id": 1},
            "features": {"team_raw_features": {"home": {"avg_sot_for": 1.0}}},
            "comparisons": {"v2_1_predicted_total": 9.0, "predicted_total_sot": 9.0},
            "target": {"actual_total_sot": 10},
        },
    ]
    assert validate_v31_rows(rows)["status"] == "ok"


def test_collect_samples_limit():
    rows = [
        {
            "metadata": {"fixture_id": i},
            "features": {"bad": {"predicted_total_sot": i}},
        }
        for i in range(5)
    ]
    anti = validate_v31_rows(rows, sample_limit=3)
    assert anti["status"] == "failed"
    assert len(anti["sample_forbidden_fields"]) <= 3


def test_find_forbidden_paths():
    pairs = find_forbidden_in_features({"outcome": 1, "nested": {"win": 2}})
    fields = {f for _, f in pairs}
    assert "outcome" in fields
    assert "win" in fields
