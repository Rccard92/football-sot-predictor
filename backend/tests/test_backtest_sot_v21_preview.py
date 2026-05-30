"""Test GET /api/backtest/debug/sot-v21-preview (Step E)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_point_in_time import ActualsForScoring
from app.schemas.backtest_sot_v21_preview import (
    SotV21PreviewErrors,
    SotV21PreviewFixtureBrief,
    SotV21PreviewPrediction,
    SotV21PreviewResponse,
    SotV21PreviewSideTrace,
)

client = TestClient(app)

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
_LATEST = datetime(2026, 3, 10, 20, 45, tzinfo=timezone.utc)

_SIDE_TRACE = SotV21PreviewSideTrace(
    base_anchor_sot={
        "formula": "0.55 * avg_sot_for + 0.45 * opponent_avg_sot_against",
        "value": 5.2,
    },
    weighted_macro_multiplier=1.05,
    expected_sot_v21_pit=5.46,
    macros=[],
)

_MOCK_PREVIEW = SotV21PreviewResponse(
    status="ok",
    competition_id=1,
    fixture_id=146,
    fixture=SotV21PreviewFixtureBrief(
        home_team="AC Milan",
        away_team="Sassuolo",
        kickoff_at=_CUTOFF,
        round="Regular Season - 15",
    ),
    leakage_guard=True,
    cutoff_time=_CUTOFF,
    latest_fixture_used_at=_LATEST,
    actuals_used_as_input=False,
    prediction=SotV21PreviewPrediction(
        home_predicted_sot=5.46,
        away_predicted_sot=4.12,
        total_predicted_sot=9.58,
    ),
    actuals_for_scoring=ActualsForScoring(
        actual_home_sot=6,
        actual_away_sot=4,
        actual_total_sot=10,
        final_score="2-1",
        fixture_status="FT",
    ),
    errors=SotV21PreviewErrors(
        home_error=-0.54,
        away_error=0.12,
        total_error=-0.42,
        home_abs_error=0.54,
        away_abs_error=0.12,
        total_abs_error=0.42,
    ),
    home_trace=_SIDE_TRACE,
    away_trace=_SIDE_TRACE,
    warnings=["player_layer_point_in_time_not_built_yet"],
    fallback_variables=["player_layer_point_in_time_not_built_yet"],
    feature_snapshot_json={"preview_only": True},
)


@patch("app.routes.backtest_debug.SotV21PointInTimePreviewService")
def test_sot_v21_preview_success(mock_svc_cls):
    mock_svc_cls.return_value.build_preview.return_value = _MOCK_PREVIEW

    response = client.get(
        "/api/backtest/debug/sot-v21-preview",
        params={"competition_id": 1, "fixture_id": 146, "mode": "pre_lineup"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["leakage_guard"] is True
    assert body["actuals_used_as_input"] is False
    assert body["latest_fixture_used_at"] < body["cutoff_time"]
    assert body["prediction"]["home_predicted_sot"] == 5.46
    assert body["prediction"]["total_predicted_sot"] == 9.58
    assert body["errors"]["total_abs_error"] == 0.42


@patch("app.routes.backtest_debug.SotV21PointInTimePreviewService")
def test_sot_v21_preview_fixture_not_found(mock_svc_cls):
    from fastapi import HTTPException

    mock_svc_cls.return_value.build_preview.side_effect = HTTPException(
        status_code=404,
        detail={"code": "fixture_not_found", "message": "Fixture 999 not found"},
    )

    response = client.get(
        "/api/backtest/debug/sot-v21-preview",
        params={"competition_id": 1, "fixture_id": 999},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "fixture_not_found"


@patch("app.routes.backtest_debug.SotV21PointInTimePreviewService")
def test_sot_v21_preview_competition_mismatch(mock_svc_cls):
    from fastapi import HTTPException

    mock_svc_cls.return_value.build_preview.side_effect = HTTPException(
        status_code=422,
        detail={"code": "fixture_competition_mismatch", "message": "mismatch"},
    )

    response = client.get(
        "/api/backtest/debug/sot-v21-preview",
        params={"competition_id": 2, "fixture_id": 146},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "fixture_competition_mismatch"


@patch("app.routes.backtest_debug.SotV21PointInTimePreviewService")
def test_sot_v21_preview_mode_not_supported(mock_svc_cls):
    from fastapi import HTTPException

    mock_svc_cls.return_value.build_preview.side_effect = HTTPException(
        status_code=422,
        detail={"code": "mode_not_supported_yet", "message": "only pre_lineup"},
    )

    response = client.get(
        "/api/backtest/debug/sot-v21-preview",
        params={"competition_id": 1, "fixture_id": 146, "mode": "post_lineup"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "mode_not_supported_yet"
