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


@patch("app.services.sportapi.lineup_refresh_impact_orchestrator.LineupRefreshImpactOrchestrator.load_latest_impact_by_fixture_ids")
@patch("app.services.sportapi.sportapi_lineup_status.load_lineups_by_fixture_ids", return_value={})
@patch("app.services.tracked_betting_pick_service.TrackedBettingPickService")
@patch("app.services.sot_betting_advice_service.build_upcoming_report_markets", return_value=[])
@patch("app.services.sot_betting_advice_service.advice_context_from_upcoming_lineup", return_value={})
@patch("app.services.sportapi.sportapi_lineup_status.formation_status_from_lineup", return_value="probable")
@patch("app.services.sportapi.sportapi_lineup_status.next_round_sportapi_lineup_stats")
@patch("app.services.next_round_quick_report_service._load_upcoming_fixtures_for_competition")
@patch("app.services.next_round_quick_report_service._load_prediction_context")
def test_quick_report_v21_does_not_attach_v20_lineup_impact(
    mock_ctx,
    mock_upcoming,
    mock_nr_stats,
    mock_formation,
    mock_advice,
    mock_markets,
    mock_pick_svc,
    mock_lineups,
    mock_load_impact,
    mock_db,
):
    fx = MagicMock()
    fx.id = 551
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.kickoff_at = None
    fx.round = "Regular Season - 5"
    fx.status = "NS"
    fx.api_fixture_id = 999
    mock_upcoming.return_value = (None, [fx], "Regular Season - 5")
    mock_nr_stats.return_value = {"next_round_coverage_pct": 100, "next_round_sportapi_lineups_count": 1}

    pred_home = MagicMock()
    pred_home.predicted_sot = 4.1
    pred_away = MagicMock()
    pred_away.predicted_sot = 4.17
    pred_map = {
        (551, 1, BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS): pred_home,
        (551, 2, BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS): pred_away,
    }

    def pick_v21(_fx):
        return BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS

    mock_ctx.return_value = (
        pred_map,
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        [],
        pick_v21,
    )
    mock_load_impact.return_value = {}
    mock_pick_svc.return_value.load_open_picks_by_fixture_ids.return_value = {}
    mock_db.scalars.return_value.all.return_value = []

    payload, code = build_next_round_quick_report_payload(
        mock_db,
        2026,
        competition_id=2,
        model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    )

    assert code == 200
    assert payload["model_limitations"]["lineups_considered"] is True
    assert payload["model_limitations"]["injuries_considered"] is True
    assert "macroaree pesate" in str(payload["model_limitations"]["note"])
    match = payload["matches"][0]
    assert match["model_version_used"] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    assert match["predicted_total_sot"] == 8.27
    assert match["variation_delta"] is None
    assert match["lineup_refresh_impact"]["has_comparison"] is False
    mock_load_impact.assert_called_with(
        mock_db,
        [551],
        model_id=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    )
