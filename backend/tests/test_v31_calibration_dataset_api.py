"""Test API dataset calibrazione v3.1."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.backtest.v31_calibration_csv_export import CSV_COLUMNS

client = TestClient(app)

V31_SUMMARY = {
    "status": "ok",
    "competition_id": 1,
    "season_year": 2025,
    "season_label": "2025/2026",
    "rounds_available": 34,
    "fixtures_available": 340,
    "fixtures_with_target": 340,
    "features": {
        "team_stats_available": 338,
        "player_layer_available": 320,
        "lineups_available": 330,
        "unavailable_available": 280,
        "macro_features_available": 335,
    },
    "anti_leakage_check": {"status": "ok", "forbidden_fields_found": []},
    "last_updated_at": "2026-06-01T18:42:00+00:00",
}

V31_PAYLOAD = {
    "report_type": "v31_calibration_dataset",
    "competition_id": 1,
    "season_year": 2025,
    "fixtures_count": 1,
    "comparisons_are_not_features": True,
    "anti_leakage_check": {"status": "ok", "forbidden_fields_found": []},
    "coverage_summary": {
        "fixtures_count": 1,
        "player_layer_available_pct": 100.0,
        "lineups_available_pct": 100.0,
        "unavailable_available_pct": 100.0,
        "top_warnings": [],
    },
    "rows": [
        {
            "metadata": {"fixture_id": 10, "round_number": 1},
            "target": {
                "actual_home_sot": 4,
                "actual_away_sot": 5,
                "actual_total_sot": 9,
                "final_score": "2-1",
            },
            "features": {
                "team_raw_features": {
                    "home": {"avg_sot_for": 5.2},
                    "away": {"avg_sot_for": 4.8},
                },
                "player_layer": {"home": {}, "away": {}},
                "lineups": {"home": {}, "away": {}},
                "unavailable": {"home": {}, "away": {}},
                "existing_macro_features": {"home": {}, "away": {}},
                "league_context": {"season_phase": "early"},
            },
            "comparisons": {
                "allowed_for_v31_training": False,
                "v1_1_predicted_total": 8.5,
                "v2_1_predicted_total": 9.0,
            },
            "data_quality": {"warning_count": 0, "fallback_count": 0},
        },
    ],
}


def _features_has_forbidden(obj, forbidden: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in forbidden or "predicted_total_sot" in k or k.startswith("actual_"):
                found.append(k)
            found.extend(_features_has_forbidden(v, forbidden))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_features_has_forbidden(item, forbidden))
    return found


@patch("app.routes.backtest_v31.V31CalibrationDatasetService.get_summary")
def test_v31_calibration_dataset_summary_200(mock_summary):
    mock_summary.return_value = V31_SUMMARY
    r = client.get(
        "/api/backtest/v31/calibration-dataset/summary",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["fixtures_with_target"] == 340
    assert body["features"]["player_layer_available"] == 320
    assert body["anti_leakage_check"]["status"] == "ok"
    mock_summary.assert_called_once()


@patch("app.routes.backtest_v31.V31CalibrationDatasetService.get_dataset")
def test_v31_calibration_dataset_json_200(mock_get):
    mock_get.return_value = V31_PAYLOAD
    r = client.get(
        "/api/backtest/v31/calibration-dataset",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["report_type"] == "v31_calibration_dataset"
    assert body["comparisons_are_not_features"] is True
    assert body["anti_leakage_check"]["status"] == "ok"

    row = body["rows"][0]
    assert "actual_total_sot" in row["target"]
    assert "actual_total_sot" not in row["features"]
    feats_forbidden = _features_has_forbidden(
        row["features"],
        {"actual_total_sot", "predicted_total_sot", "final_score"},
    )
    assert feats_forbidden == []
    assert row["comparisons"]["v2_1_predicted_total"] == 9.0


@patch("app.routes.backtest_v31.V31CalibrationDatasetService.get_dataset_csv")
def test_v31_calibration_dataset_csv_200(mock_csv):
    mock_csv.return_value = (
        ",".join(CSV_COLUMNS) + "\n"
        "10,1,Home vs Away,4,5,9,5.2,4.8,,,,,,,,,,,,,,,,,,,,0,0,8.5,,9.0,,\n"
    )
    r = client.get(
        "/api/backtest/v31/calibration-dataset.csv",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    text = r.text
    assert "fixture_id" in text.splitlines()[0]
    assert "comparison_v21_predicted_total" in text.splitlines()[0]
    assert "10,1," in text.splitlines()[1]
