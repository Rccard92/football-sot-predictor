"""Test ricalcolo offline Cecchino con nuovi pesi."""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi.testclient import TestClient

from app.main import app
from app.services.cecchino.cecchino_constants import (
    CECCHINO_1X2_WEIGHTS,
    CECCHINO_GOAL_MARKET_WEIGHTS,
    validate_cecchino_weight_sets,
)

client = TestClient(app)


def test_weight_sets_sum_to_one():
    validate_cecchino_weight_sets()
    assert sum(CECCHINO_1X2_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(CECCHINO_GOAL_MARKET_WEIGHTS.values()) == pytest.approx(1.0)


def test_recompute_endpoint_returns_summary():
    payload = {
        "status": "ok",
        "fixtures_found": 3,
        "fixtures_recomputed": 3,
        "kpi_recomputed": 3,
        "signals_synced": 12,
        "signals_deactivated": 1,
        "signals_evaluated": 10,
        "warnings": [],
    }
    with patch(
        "app.routes.cecchino_admin.recompute_cecchino_range",
        return_value=payload,
    ):
        resp = client.post(
            "/api/admin/cecchino/recompute",
            json={
                "date_from": "2026-06-01",
                "date_to": "2026-06-07",
                "scope": "cecchino",
                "refresh_bookmaker_odds": False,
                "use_existing_bookmaker_odds": True,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["fixtures_recomputed"] == 3
    assert data["signals_evaluated"] == 10


def test_recompute_offline_does_not_call_api_football():
    row = MagicMock()
    row.id = 1
    row.local_fixture_id = 10
    row.competition_id = 5
    row.cecchino_output_json = {"final": {"status": "available"}}
    row.odds_snapshot_json = {"bookmakers": {"Betfair": {"HOME": 2.0, "DRAW": 3.2, "AWAY": 4.0}}}
    row.stats_snapshot_json = {"leakage_status": "passed"}
    row.warnings_json = []
    row.home_team_name = "Home"
    row.away_team_name = "Away"
    row.eligibility_status = "eligible"
    row.stats_status = "ok"

    calc_payload = {
        "status": "ok",
        "calculation_status": "available",
        "output": {
            "final": {
                "status": "available",
                "quota_1": 2.38,
                "quota_x": 2.58,
                "quota_2": 5.72,
                "prob_1": 0.42,
                "prob_x": 0.39,
                "prob_2": 0.17,
            },
            "signals_matrix": {"status": "available", "rows": []},
            "warnings": [],
        },
    }

    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    db.get.side_effect = lambda _model, pk: MagicMock(id=pk)
    db.commit = MagicMock()

    with (
        patch(
            "app.services.cecchino.cecchino_recompute_service.calculate_and_persist_for_fixture",
            return_value=calc_payload,
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.build_goal_market_contexts",
            return_value=MagicMock(),
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.build_goal_market_cecchino_odds",
            return_value={"OVER_1_5": {"final_odd": 2.1, "status": "available"}},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.build_cecchino_kpi_panel_v2_betfair",
            return_value={"version": "cecchino_kpi_v2_betfair", "rows": []},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.validate_cecchino_today_final_eligibility",
        ) as mock_elig,
        patch(
            "app.services.cecchino.cecchino_recompute_service.sync_cecchino_signal_activations",
            return_value={"created": 2, "updated": 1, "deactivated": 0},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.evaluate_activations_for_fixture",
            return_value={"evaluated": 3, "pending": 0},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.remap_under_over_activations_in_range",
            return_value=0,
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.refresh_betfair_odds_for_fixture",
        ) as mock_refresh,
    ):
        mock_elig.return_value = MagicMock(
            is_eligible=True,
            eligibility_status="eligible",
            eligibility_reason=None,
            blocking_reasons=[],
            warnings=[],
        )
        from app.services.cecchino.cecchino_recompute_service import recompute_cecchino_range

        result = recompute_cecchino_range(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 7),
            refresh_bookmaker_odds=False,
            use_existing_bookmaker_odds=True,
        )

    assert result["fixtures_recomputed"] == 1
    assert result["kpi_recomputed"] == 1
    assert result["signals_synced"] == 3
    assert result["signals_evaluated"] == 3
    mock_refresh.assert_not_called()
    db.commit.assert_called_once()
