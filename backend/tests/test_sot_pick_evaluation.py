"""Test pick evaluation Over-only SOT read-only (Step H / H.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_point_in_time import ActualsForScoring
from app.schemas.backtest_sot_pick_evaluation import (
    SotPickAdvisedSummary,
    SotPickCalculatedSummary,
    SotPickEvaluationResponse,
    SotPickEvaluationSelection,
)
from app.schemas.backtest_sot_v21_preview import (
    SotV21PreviewErrors,
    SotV21PreviewFixtureBrief,
    SotV21PreviewPrediction,
    SotV21PreviewResponse,
    SotV21PreviewSideTrace,
)
from app.services.backtest.sot_pick_evaluation_logic import (
    DEFAULT_PICK_LINES,
    ConfidenceSignals,
    apply_confidence_caps,
    compute_aggressive_confidence,
    compute_cautious_confidence,
    compute_pick_outcome,
    evaluate_over_picks,
    resolve_aggressive_line,
    resolve_cautious_line,
)

client = TestClient(app)

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
_LINES = list(DEFAULT_PICK_LINES)
_SIGNALS = ConfidenceSignals(min_prior_matches=14, warnings_count=0, player_layer_neutral=False)


def test_over_win():
    assert compute_pick_outcome(7.5, 14) == "win"


def test_over_loss():
    assert compute_pick_outcome(7.5, 5) == "loss"


def test_torino_sassuolo_aggressive_and_cautious():
    aggressive, cautious, warnings = evaluate_over_picks(
        7.98, _LINES, None, cautious_drop_threshold=0.75, signals=_SIGNALS,
    )
    assert aggressive is not None
    assert aggressive.line == 7.5
    assert aggressive.side == "over"
    assert cautious is not None
    assert cautious.line == 6.5
    assert warnings == []


def test_milan_atalanta_both_win():
    aggressive, cautious, _ = evaluate_over_picks(
        8.63, _LINES, 14, cautious_drop_threshold=0.75, signals=_SIGNALS,
    )
    assert aggressive is not None
    assert aggressive.line == 8.5
    assert aggressive.outcome == "win"
    assert cautious is not None
    assert cautious.line == 7.5
    assert cautious.outcome == "win"


def test_lazio_inter_cautious_same_as_aggressive():
    aggressive, cautious, _ = evaluate_over_picks(
        9.32, _LINES, None, cautious_drop_threshold=0.75, signals=_SIGNALS,
    )
    assert aggressive is not None
    assert aggressive.line == 8.5
    assert cautious is not None
    assert cautious.line == 8.5


def test_no_aggressive_pick_when_pred_below_min_line():
    aggressive, cautious, _ = evaluate_over_picks(
        4.20, _LINES, None, cautious_drop_threshold=0.75, signals=_SIGNALS,
    )
    assert aggressive is None
    assert cautious is None


def test_no_under_in_output():
    aggressive, cautious, _ = evaluate_over_picks(
        9.0, _LINES, 10, cautious_drop_threshold=0.75, signals=_SIGNALS,
    )
    assert aggressive is not None
    assert aggressive.side == "over"
    assert cautious is not None
    assert cautious.side == "over"


def test_no_lower_cautious_line_available():
    line, warnings = resolve_cautious_line(4.80, _LINES, cautious_drop_threshold=0.75)
    assert resolve_aggressive_line(4.80, _LINES) == 4.5
    assert line is None
    assert "no_lower_cautious_line_available" in warnings


def test_aggressive_confidence_bands():
    assert compute_aggressive_confidence(0.20) == "low"
    assert compute_aggressive_confidence(0.50) == "medium"
    assert compute_aggressive_confidence(1.0) == "high"


def test_cautious_confidence_bands():
    assert compute_cautious_confidence(0.50) == "medium"
    assert compute_cautious_confidence(1.0) == "high"


def test_confidence_caps_low_sample():
    capped = apply_confidence_caps(
        "high",
        ConfidenceSignals(min_prior_matches=3, warnings_count=0, player_layer_neutral=False),
    )
    assert capped == "low"


def test_confidence_player_layer_fallback_caps_high_to_medium():
    capped = apply_confidence_caps(
        "high",
        ConfidenceSignals(min_prior_matches=10, warnings_count=0, player_layer_neutral=True),
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
        lines=[4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5],
        cautious_drop_threshold=0.75,
        include_no_pick=True,
    ),
    calculated_summary=SotPickCalculatedSummary(
        fixtures_processed=10,
        fixtures_failed=0,
        aggressive_calculated_count=8,
        aggressive_no_pick_count=2,
        aggressive_wins=5,
        aggressive_losses=3,
        aggressive_hit_rate=62.5,
        cautious_calculated_count=7,
        cautious_no_pick_count=3,
        cautious_wins=6,
        cautious_losses=1,
        cautious_hit_rate=85.71,
    ),
    advised_summary=SotPickAdvisedSummary(
        aggressive_play_count=3,
        aggressive_no_play_count=5,
        aggressive_borderline_count=0,
        aggressive_play_wins=2,
        aggressive_play_losses=1,
        aggressive_play_hit_rate=66.67,
        cautious_play_count=4,
        cautious_no_play_count=3,
        cautious_borderline_count=0,
        cautious_play_wins=4,
        cautious_play_losses=0,
        cautious_play_hit_rate=100.0,
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
            "cautious_drop_threshold": 0.75,
            "min_prior_matches_for_play": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["db_writes"] is False
    assert body["preview_only"] is True
    assert body["calculated_summary"]["fixtures_processed"] == 10
    assert body["calculated_summary"]["aggressive_calculated_count"] == 8
    assert body["advised_summary"]["cautious_play_hit_rate"] == 100.0


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
    row = result.results[0]
    assert row.aggressive_pick is not None
    assert row.aggressive_pick.line == 8.5
    assert row.aggressive_pick.outcome == "win"
    assert row.aggressive_pick.play_advice is not None
    assert row.aggressive_pick.play_advice.play_advice == "no_play"
    assert row.cautious_pick is not None
    assert row.cautious_pick.line == 7.5
    assert row.cautious_pick.outcome == "win"
    assert row.cautious_pick.play_advice is not None
    assert row.cautious_pick.play_advice.play_advice == "play"
    db.add.assert_not_called()
    db.commit.assert_not_called()
