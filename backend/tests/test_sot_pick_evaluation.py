"""Test pick evaluation Over/Under SOT read-only (Step H)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_point_in_time import ActualsForScoring
from app.schemas.backtest_sot_pick_evaluation import (
    SotPickEvaluationResponse,
    SotPickEvaluationSelection,
    SotPickEvaluationSummary,
)
from app.schemas.backtest_sot_v21_preview import (
    SotV21PreviewErrors,
    SotV21PreviewFixtureBrief,
    SotV21PreviewPrediction,
    SotV21PreviewResponse,
    SotV21PreviewSideTrace,
)
from app.services.backtest.sot_pick_evaluation_logic import (
    ConfidenceSignals,
    apply_confidence_caps,
    collect_candidates,
    compute_base_confidence,
    compute_pick_outcome,
    select_recommended_pick,
)

client = TestClient(app)

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def test_over_win():
    assert compute_pick_outcome("over", 7.5, 14) == "win"


def test_over_loss():
    assert compute_pick_outcome("over", 7.5, 5) == "loss"


def test_under_win():
    assert compute_pick_outcome("under", 8.5, 6) == "win"


def test_under_loss():
    assert compute_pick_outcome("under", 8.5, 10) == "loss"


def test_no_pick_when_edge_insufficient():
    _, candidates = collect_candidates(8.0, [7.5], min_edge=0.75)
    assert select_recommended_pick(candidates) is None


def test_recommended_pick_max_abs_edge():
    _, candidates = collect_candidates(9.0, [5.5, 7.5, 8.5], min_edge=0.75)
    pick = select_recommended_pick(candidates)
    assert pick is not None
    assert pick.side == "over"
    assert pick.line == 5.5
    assert abs(pick.edge) == max(abs(c.edge) for c in candidates)


def test_confidence_base_and_caps():
    assert compute_base_confidence(0.80) == "low"
    assert compute_base_confidence(1.50) == "medium"
    assert compute_base_confidence(2.10) == "high"
    capped = apply_confidence_caps(
        "high",
        ConfidenceSignals(
            mode="historical_official_xi",
            min_prior_matches=3,
            warnings_count=0,
            player_layer_neutral=False,
        ),
    )
    assert capped == "low"


def test_confidence_player_layer_fallback_caps_high_to_medium():
    capped = apply_confidence_caps(
        "high",
        ConfidenceSignals(
            mode="historical_official_xi",
            min_prior_matches=10,
            warnings_count=0,
            player_layer_neutral=True,
        ),
    )
    assert capped == "medium"


_MOCK_RESPONSE = SotPickEvaluationResponse(
    status="ok",
    preview_only=True,
    db_writes=False,
    competition_id=1,
    competition_name="Serie A",
    mode="historical_official_xi",
    selection=SotPickEvaluationSelection(
        limit=20,
        offset=0,
        round_number=15,
        lines=[5.5, 6.5, 7.5, 8.5, 9.5],
        min_edge=0.75,
        include_no_pick=True,
    ),
    summary=SotPickEvaluationSummary(
        fixtures_processed=10,
        fixtures_failed=0,
        pick_opportunities=7,
        no_pick_count=3,
        wins=5,
        losses=2,
        hit_rate=71.43,
        avg_edge=1.12,
        over_picks_count=5,
        under_picks_count=2,
    ),
)


@patch("app.routes.backtest_debug.SotPickEvaluationPreviewService")
def test_pick_evaluation_success(mock_svc_cls):
    mock_svc_cls.return_value.run_pick_evaluation.return_value = _MOCK_RESPONSE

    response = client.post(
        "/api/backtest/debug/sot-pick-evaluation-preview",
        json={
            "competition_id": 1,
            "mode": "historical_official_xi",
            "round_number": 15,
            "limit": 20,
            "min_edge": 0.75,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["db_writes"] is False
    assert body["preview_only"] is True
    assert body["summary"]["fixtures_processed"] == 10
    assert body["summary"]["pick_opportunities"] == 7
    assert body["summary"]["hit_rate"] == 71.43


@patch("app.routes.backtest_debug.SotPickEvaluationPreviewService")
def test_pick_evaluation_pre_lineup_mode(mock_svc_cls):
    mock_svc_cls.return_value.run_pick_evaluation.return_value = _MOCK_RESPONSE.model_copy(
        update={"mode": "pre_lineup"},
    )

    response = client.post(
        "/api/backtest/debug/sot-pick-evaluation-preview",
        json={"competition_id": 1, "mode": "pre_lineup"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "pre_lineup"


@patch("app.routes.backtest_debug.SotPickEvaluationPreviewService")
def test_pick_evaluation_mode_not_supported(mock_svc_cls):
    mock_svc_cls.return_value.run_pick_evaluation.side_effect = HTTPException(
        status_code=422,
        detail={"code": "mode_not_supported_yet", "message": "unsupported"},
    )

    response = client.post(
        "/api/backtest/debug/sot-pick-evaluation-preview",
        json={"competition_id": 1, "mode": "post_lineup"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "mode_not_supported_yet"


def test_pick_evaluation_service_no_db_writes():
    from app.services.backtest.sot_pick_evaluation_preview_service import SotPickEvaluationPreviewService

    db = MagicMock()
    comp = MagicMock()
    comp.name = "Serie A"
    db.get.return_value = comp

    preview = SotV21PreviewResponse(
        status="ok",
        competition_id=1,
        fixture_id=359,
        fixture=SotV21PreviewFixtureBrief(
            home_team="AC Milan",
            away_team="Atalanta",
            kickoff_at=_CUTOFF,
            round="Regular Season - 36",
        ),
        leakage_guard=True,
        cutoff_time=_CUTOFF,
        actuals_used_as_input=False,
        prediction=SotV21PreviewPrediction(
            home_predicted_sot=4.5,
            away_predicted_sot=4.13,
            total_predicted_sot=8.63,
        ),
        actuals_for_scoring=ActualsForScoring(actual_total_sot=14),
        errors=SotV21PreviewErrors(total_abs_error=5.37),
        home_trace=SotV21PreviewSideTrace(
            base_anchor_sot={"value": 4.5},
            weighted_macro_multiplier=1.0,
            macros=[],
        ),
        away_trace=SotV21PreviewSideTrace(
            base_anchor_sot={"value": 4.13},
            weighted_macro_multiplier=1.0,
            macros=[],
        ),
        home_prior_matches_count=14,
        away_prior_matches_count=14,
    )

    candidate = MagicMock()
    candidate.fixture_id = 359

    selection = MagicMock()
    selection.items = [candidate]
    selection.order_by = "kickoff_at asc"
    selection.fixtures_requested = 1

    with patch(
        "app.services.backtest.sot_pick_evaluation_preview_service.BacktestFixtureDebugService",
    ) as mock_fixture_cls, patch(
        "app.services.backtest.sot_pick_evaluation_preview_service.SotV21PointInTimePreviewService",
    ) as mock_preview_cls:
        mock_fixture_cls.return_value.select_fixtures_for_mini_run.return_value = selection
        mock_preview_cls.return_value.build_preview.return_value = preview

        result = SotPickEvaluationPreviewService().run_pick_evaluation(
            db,
            competition_id=1,
            mode="historical_official_xi",
            round_number=36,
            limit=20,
        )

    assert result.db_writes is False
    assert len(result.results) == 1
    pick = result.results[0].recommended_pick
    assert pick is not None
    assert pick.side == "over"
    assert pick.outcome == "win"
    db.add.assert_not_called()
    db.commit.assert_not_called()
