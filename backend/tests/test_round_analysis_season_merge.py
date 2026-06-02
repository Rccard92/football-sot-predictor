"""Test unitari: dedup latest-per-round e merge helper."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.backtest.round_analysis_merge import selected_models_already_present
from app.services.backtest.round_analysis_visible_selection import pick_visible_latest_per_round

client = TestClient(app)


def test_pick_visible_latest_per_round_selects_highest_version():
    now = datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(round_number=37, analysis_version=1, status="completed", created_at=now),
        SimpleNamespace(round_number=37, analysis_version=2, status="completed", created_at=now),
        SimpleNamespace(round_number=36, analysis_version=1, status="completed", created_at=now),
        SimpleNamespace(round_number=36, analysis_version=2, status="completed_with_warnings", created_at=now),
    ]
    visible = pick_visible_latest_per_round(rows)  # type: ignore[arg-type]
    by_round = {int(r.round_number): int(r.analysis_version) for r in visible}
    assert by_round[36] == 2
    assert by_round[37] == 2


def test_selected_models_already_present_true_only_when_all_blocks_valid():
    fx1 = SimpleNamespace(
        status="ok",
        models_json={
            "baseline_v3_0_sot_value_selector": {"status": "ok"},
        },
    )
    fx2 = SimpleNamespace(
        status="ok",
        models_json={
            "baseline_v3_0_sot_value_selector": {"status": "ok"},
        },
    )
    assert selected_models_already_present(
        [fx1, fx2],  # type: ignore[arg-type]
        selected_models=["baseline_v3_0_sot_value_selector"],
    )

    fx3 = SimpleNamespace(status="ok", models_json={"baseline_v3_0_sot_value_selector": {"status": "no_prediction"}})
    assert not selected_models_already_present(
        [fx1, fx3],  # type: ignore[arg-type]
        selected_models=["baseline_v3_0_sot_value_selector"],
    )

    fx4 = SimpleNamespace(status="failed", models_json={"baseline_v3_0_sot_value_selector": {"status": "ok"}})
    assert not selected_models_already_present(
        [fx1, fx4],  # type: ignore[arg-type]
        selected_models=["baseline_v3_0_sot_value_selector"],
    )


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_analyze_endpoint_accepts_wrapper_dict(mock_svc_cls):
    mock_svc_cls.return_value.analyze.return_value = {
        "status": "skipped",
        "reason": "missing_v30_dependencies",
        "round_number": 37,
        "missing_dependencies": ["baseline_v1_1_sot", "baseline_v2_1_weighted_components"],
        "message": "v3.0 richiede v1.1 e v2.1 già calcolate per questa giornata.",
        "selected_models": ["baseline_v3_0_sot_value_selector"],
    }
    res = client.post(
        "/api/backtest/round-analysis/analyze",
        json={
            "competition_id": 2,
            "season_year": 2025,
            "round_number": 37,
            "merge_mode": "upsert_selected_models",
            "selected_models": ["baseline_v3_0_sot_value_selector"],
            "only_missing_models": True,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "skipped"
    assert res.json()["round_number"] == 37
    assert res.json()["reason"] == "missing_v30_dependencies"


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_list_endpoint_passes_latest_only_default_true(mock_svc_cls):
    mock_svc_cls.return_value.list_analyses.return_value = {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }
    res = client.get("/api/backtest/round-analysis?competition_id=2&season_year=2025")
    assert res.status_code == 200
    assert mock_svc_cls.return_value.list_analyses.call_args.kwargs["latest_only_per_round"] is True

