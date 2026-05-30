"""Test API Backtest Runs (Step C)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.markets.registry import MARKET_REGISTRY, MARKET_SHOTS_ON_TARGET
from app.models.backtest import BacktestRun
from app.schemas.backtest_runs import BacktestRunCreateRequest, BacktestRunFilters
from app.services.backtest_run_service import BacktestRunDetail, BacktestRunService

client = TestClient(app)

_CREATE_BODY = {
    "competition_id": 2,
    "season_year": 2026,
    "market_key": "shots_on_target",
    "algorithm_version": "baseline_v2_1_weighted_components",
    "mode": "pre_lineup",
    "fixture_scope": "full_season",
    "config_json": {"default_ou_lines": [5.5, 6.5, 7.5, 8.5, 9.5]},
}


def _mock_run(run_id: int = 1) -> MagicMock:
    run = MagicMock(spec=BacktestRun)
    run.id = run_id
    run.competition_id = 2
    run.season_id = None
    run.season_year = 2026
    run.market_key = "shots_on_target"
    run.algorithm_version = "baseline_v2_1_weighted_components"
    run.mode = "pre_lineup"
    run.fixture_scope = "full_season"
    run.date_from = None
    run.date_to = None
    run.status = "pending"
    run.config_json = {"default_ou_lines": [5.5, 6.5, 7.5, 8.5, 9.5]}
    run.summary_json = None
    run.error_json = None
    run.algorithm_config_hash = "abc123"
    run.model_manifest_version = None
    run.git_commit_sha = None
    run.created_at = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    run.completed_at = None
    return run


@patch("app.routes.backtest_runs.BacktestRunService")
def test_create_run_success(mock_svc_cls):
    mock_svc_cls.return_value.create_run.return_value = _mock_run(1)

    response = client.post("/api/backtest/runs", json=_CREATE_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["status"] == "pending"
    assert body["competition_id"] == 2
    assert body["market_key"] == "shots_on_target"


def test_validate_invalid_market_key():
    svc = BacktestRunService()
    with pytest.raises(HTTPException) as exc:
        svc.validate_market_and_algorithm("corners_fake", "baseline_v2_1_weighted_components")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_market_key"


def test_validate_market_not_active():
    svc = BacktestRunService()
    with pytest.raises(HTTPException) as exc:
        svc.validate_market_and_algorithm("corners", "corners_v1_0")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "market_not_active"


def test_validate_invalid_algorithm_for_market():
    svc = BacktestRunService()
    with pytest.raises(HTTPException) as exc:
        svc.validate_market_and_algorithm("shots_on_target", "corners_v1_0")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_algorithm_for_market"


def test_create_competition_not_found():
    svc = BacktestRunService()
    db = MagicMock()
    with patch("app.services.backtest_run_service.CompetitionService") as mock_comp:
        mock_comp.return_value.get_by_id.return_value = None
        with pytest.raises(HTTPException) as exc:
            svc.create_run(db, BacktestRunCreateRequest.model_validate(_CREATE_BODY))
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "competition_not_found"


def test_compute_algorithm_config_hash_stable():
    svc = BacktestRunService()
    market = MARKET_REGISTRY[MARKET_SHOTS_ON_TARGET]
    kwargs = dict(
        market=market,
        market_key="shots_on_target",
        algorithm_version="baseline_v2_1_weighted_components",
        mode="pre_lineup",
        fixture_scope="full_season",
        season_year=2026,
        date_from=None,
        date_to=None,
        config_json={"default_ou_lines": [5.5, 6.5]},
    )
    h1 = svc.compute_algorithm_config_hash(**kwargs)
    h2 = svc.compute_algorithm_config_hash(**kwargs)
    assert h1 == h2
    assert len(h1) == 64


@patch("app.routes.backtest_runs.BacktestRunService")
def test_list_runs(mock_svc_cls):
    run = _mock_run(3)
    mock_svc_cls.return_value.list_runs.return_value = ([(run, "Brasileirão Série A")], 1)

    response = client.get("/api/backtest/runs?competition_id=2&market_key=shots_on_target")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["competition_name"] == "Brasileirão Série A"


@patch("app.routes.backtest_runs.BacktestRunService")
def test_get_run_not_found(mock_svc_cls):
    mock_svc_cls.return_value.get_run.return_value = None

    response = client.get("/api/backtest/runs/99999")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "backtest_run_not_found"


@patch("app.routes.backtest_runs.BacktestRunService")
def test_get_run_counts_zero(mock_svc_cls):
    run = _mock_run(5)
    mock_svc_cls.return_value.get_run.return_value = BacktestRunDetail(
        run=run,
        competition_name="Brasileirão Série A",
        predictions_count=0,
        picks_count=0,
        metrics_count=0,
    )

    response = client.get("/api/backtest/runs/5")

    assert response.status_code == 200
    body = response.json()
    assert body["predictions_count"] == 0
    assert body["picks_count"] == 0
    assert body["metrics_count"] == 0
    assert body["status"] == "pending"


def test_import_app_main():
    from app.main import app as fastapi_app

    assert fastapi_app.title
