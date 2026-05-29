"""Strict model_version: nessun fallback cross-version nel quick report."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.next_round_quick_report_service import build_next_round_quick_report_payload


@pytest.fixture
def mock_db():
    return MagicMock()


@patch("app.services.next_round_quick_report_service._load_upcoming_fixtures_for_competition")
@patch("app.services.next_round_quick_report_service._load_prediction_context")
def test_quick_report_strict_missing_v21(mock_ctx, mock_upcoming, mock_db):
    fx = MagicMock()
    fx.id = 551
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.kickoff_at = None
    fx.round = "Regular Season - 5"
    fx.status = "NS"
    fx.api_fixture_id = 999
    mock_upcoming.return_value = (None, [fx], "Regular Season - 5")

    def pick_none(_fx):
        return None

    mock_ctx.return_value = ({}, "baseline_v2_0_lineup_impact", [], pick_none)

    payload, code = build_next_round_quick_report_payload(
        mock_db,
        2026,
        competition_id=2,
        model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    )

    assert code == 200
    assert payload["status"] == "missing_prediction"
    assert payload["model_version"] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    assert payload["matches_count"] == 0
    assert payload["matches"] == []

    mock_ctx.assert_called_once()
    assert mock_ctx.call_args.kwargs.get("strict_model") is True


@patch("app.services.next_round_quick_report_service._load_upcoming_fixtures_for_competition")
@patch("app.services.next_round_quick_report_service._load_prediction_context")
def test_quick_report_no_v20_in_matches_when_v21_requested(mock_ctx, mock_upcoming, mock_db):
    fx = MagicMock()
    fx.id = 551
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.kickoff_at = None
    fx.round = "Regular Season - 5"
    fx.status = "NS"
    fx.api_fixture_id = 999
    mock_upcoming.return_value = (None, [fx], "Regular Season - 5")

    pred_v20 = MagicMock()
    pred_v20.predicted_sot = 4.5
    pred_map = {
        (551, 1, BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT): pred_v20,
        (551, 2, BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT): pred_v20,
    }

    def pick_none(_fx):
        return None

    mock_ctx.return_value = (pred_map, BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT, [], pick_none)

    payload, code = build_next_round_quick_report_payload(
        mock_db,
        2026,
        competition_id=2,
        model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    )

    assert code == 200
    assert payload["status"] == "missing_prediction"
    for m in payload.get("matches") or []:
        assert m.get("model_version_used") != BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
