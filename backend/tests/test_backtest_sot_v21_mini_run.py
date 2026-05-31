"""Test POST /api/backtest/debug/sot-v21-mini-run (Step F)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_point_in_time import ActualsForScoring
from app.schemas.backtest_sot_v21_mini_run import (
    SotV21MiniRunActualTotalBreakdown,
    SotV21MiniRunBucketStats,
    SotV21MiniRunCaseBrief,
    SotV21MiniRunFailedFixture,
    SotV21MiniRunFixtureResult,
    SotV21MiniRunResponse,
    SotV21MiniRunSampleBreakdown,
    SotV21MiniRunSelection,
    SotV21MiniRunSplitSummary,
    SotV21MiniRunSummary,
)
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
    base_anchor_sot={"formula": "anchor", "value": 5.2},
    weighted_macro_multiplier=1.05,
    expected_sot_v21_pit=5.46,
    macros=[],
)

_RESULT = SotV21MiniRunFixtureResult(
    fixture_id=146,
    round="Regular Season - 15",
    kickoff_at=_CUTOFF,
    home_team="AC Milan",
    away_team="Sassuolo",
    predicted_home_sot=5.46,
    predicted_away_sot=4.12,
    predicted_total_sot=9.58,
    actual_home_sot=6,
    actual_away_sot=4,
    actual_total_sot=10,
    home_error=-0.54,
    away_error=0.12,
    total_error=-0.42,
    total_abs_error=0.42,
    leakage_guard=True,
    actuals_used_as_input=False,
    latest_fixture_used_at=_LATEST,
    cutoff_time=_CUTOFF,
    home_prior_matches_count=14,
    away_prior_matches_count=14,
    warnings=["player_layer_point_in_time_not_built_yet"],
)

_MOCK_RESPONSE = SotV21MiniRunResponse(
    status="ok",
    preview_only=True,
    competition_id=1,
    competition_name="Serie A",
    mode="pre_lineup",
    selection=SotV21MiniRunSelection(
        limit=20,
        offset=0,
        round_number=15,
        round_contains=None,
        round_filter_mode="exact_round_number",
        fixture_ids=None,
        order_by="kickoff_at asc",
    ),
    summary=SotV21MiniRunSummary(
        fixtures_requested=20,
        fixtures_processed=1,
        fixtures_failed=0,
        total_mae=0.42,
        home_mae=0.54,
        away_mae=0.12,
        total_rmse=0.42,
        total_bias=-0.42,
        home_bias=-0.54,
        away_bias=0.12,
        avg_predicted_total_sot=9.58,
        avg_actual_total_sot=10.0,
        overestimated_count=0,
        underestimated_count=1,
        exact_or_near_count=1,
        high_error_count=0,
    ),
    split_summary=SotV21MiniRunSplitSummary(
        available_count=1,
        partial_count=0,
        fallback_count=0,
        avg_home_split_index=1.08,
        avg_away_split_index=0.94,
    ),
    sample_breakdown=SotV21MiniRunSampleBreakdown(
        medium_sample=SotV21MiniRunBucketStats(
            fixtures_count=1,
            total_mae=0.42,
            total_bias=-0.42,
            avg_predicted_total_sot=9.58,
            avg_actual_total_sot=10.0,
        ),
    ),
    actual_total_breakdown=SotV21MiniRunActualTotalBreakdown(
        medium_total=SotV21MiniRunBucketStats(
            fixtures_count=1,
            total_mae=0.42,
            total_bias=-0.42,
            avg_predicted_total_sot=9.58,
            avg_actual_total_sot=10.0,
        ),
    ),
    worst_cases=[
        SotV21MiniRunCaseBrief(
            fixture_id=146,
            kickoff_at=_CUTOFF,
            round="Regular Season - 15",
            home_team="AC Milan",
            away_team="Sassuolo",
            predicted_total_sot=9.58,
            actual_total_sot=10,
            total_error=-0.42,
            total_abs_error=0.42,
            home_prior_matches_count=14,
            away_prior_matches_count=14,
            warnings_count=1,
        ),
    ],
    best_cases=[
        SotV21MiniRunCaseBrief(
            fixture_id=146,
            kickoff_at=_CUTOFF,
            round="Regular Season - 15",
            home_team="AC Milan",
            away_team="Sassuolo",
            predicted_total_sot=9.58,
            actual_total_sot=10,
            total_error=-0.42,
            total_abs_error=0.42,
            home_prior_matches_count=14,
            away_prior_matches_count=14,
            warnings_count=1,
        ),
    ],
    results=[_RESULT],
    failed_fixtures=[],
    db_writes=False,
)


@patch("app.routes.backtest_debug.SotV21MiniRunPreviewService")
def test_sot_v21_mini_run_success(mock_svc_cls):
    mock_svc_cls.return_value.run_preview.return_value = _MOCK_RESPONSE

    response = client.post(
        "/api/backtest/debug/sot-v21-mini-run",
        json={
            "competition_id": 1,
            "mode": "pre_lineup",
            "limit": 20,
            "offset": 0,
            "round_number": 15,
            "include_trace": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db_writes"] is False
    assert body["preview_only"] is True
    assert body["summary"]["fixtures_processed"] == 1
    assert body["split_summary"]["available_count"] == 1
    assert body["results"][0]["leakage_guard"] is True
    assert body["results"][0]["actuals_used_as_input"] is False
    assert body["results"][0].get("home_trace") is None


@patch("app.routes.backtest_debug.SotV21MiniRunPreviewService")
def test_sot_v21_mini_run_mode_not_supported(mock_svc_cls):
    mock_svc_cls.return_value.run_preview.side_effect = HTTPException(
        status_code=422,
        detail={"code": "mode_not_supported_yet", "message": "La mini-run supporta solo pre_lineup in questa fase."},
    )

    response = client.post(
        "/api/backtest/debug/sot-v21-mini-run",
        json={"competition_id": 1, "mode": "post_lineup"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "mode_not_supported_yet"


@patch("app.routes.backtest_debug.SotV21MiniRunPreviewService")
def test_sot_v21_mini_run_competition_not_found(mock_svc_cls):
    mock_svc_cls.return_value.run_preview.side_effect = HTTPException(
        status_code=404,
        detail={"code": "competition_not_found", "message": "Competition 999 not found"},
    )

    response = client.post(
        "/api/backtest/debug/sot-v21-mini-run",
        json={"competition_id": 999},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "competition_not_found"


@patch("app.routes.backtest_debug.SotV21MiniRunPreviewService")
def test_sot_v21_mini_run_include_trace(mock_svc_cls):
    traced = _RESULT.model_copy(
        update={"home_trace": _SIDE_TRACE, "away_trace": _SIDE_TRACE},
    )
    payload = _MOCK_RESPONSE.model_copy(update={"results": [traced]})
    mock_svc_cls.return_value.run_preview.return_value = payload

    response = client.post(
        "/api/backtest/debug/sot-v21-mini-run",
        json={"competition_id": 1, "include_trace": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["home_trace"] is not None
    assert body["results"][0]["away_trace"] is not None
    mock_svc_cls.return_value.run_preview.assert_called_once()
    assert mock_svc_cls.return_value.run_preview.call_args.kwargs["include_trace"] is True


@patch("app.routes.backtest_debug.SotV21MiniRunPreviewService")
def test_sot_v21_mini_run_partial_ok(mock_svc_cls):
    partial = _MOCK_RESPONSE.model_copy(
        update={
            "status": "partial_ok",
            "summary": _MOCK_RESPONSE.summary.model_copy(
                update={"fixtures_processed": 1, "fixtures_failed": 1},
            ),
            "failed_fixtures": [
                SotV21MiniRunFailedFixture(
                    fixture_id=999,
                    error_code="fixture_not_found",
                    message="Fixture 999 not found",
                ),
            ],
        },
    )
    mock_svc_cls.return_value.run_preview.return_value = partial

    response = client.post(
        "/api/backtest/debug/sot-v21-mini-run",
        json={"competition_id": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial_ok"
    assert len(body["failed_fixtures"]) == 1


def test_sot_v21_mini_run_service_no_db_writes():
    from app.services.backtest.sot_v21_mini_run_preview_service import SotV21MiniRunPreviewService

    db = MagicMock()
    db.get.return_value = MagicMock(name="Serie A")

    preview = SotV21PreviewResponse(
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
        home_prior_matches_count=14,
        away_prior_matches_count=14,
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
    )

    selection_item = MagicMock()
    selection_item.fixture_id = 146

    with patch(
        "app.services.backtest.sot_v21_mini_run_preview_service.BacktestFixtureDebugService",
    ) as mock_fixture_cls, patch(
        "app.services.backtest.sot_v21_mini_run_preview_service.SotV21PointInTimePreviewService",
    ) as mock_preview_cls:
        mock_fixture_cls.return_value.select_fixtures_for_mini_run.return_value = MagicMock(
            items=[selection_item],
            order_by="kickoff_at asc",
            fixtures_requested=1,
        )
        mock_preview_cls.return_value.build_preview.return_value = preview

        result = SotV21MiniRunPreviewService().run_preview(
            db,
            competition_id=1,
            include_trace=False,
        )

    assert result.db_writes is False
    assert result.summary.fixtures_processed == 1
    assert result.split_summary is not None
    assert result.results[0].home_trace is None
    db.add.assert_not_called()
    db.commit.assert_not_called()
