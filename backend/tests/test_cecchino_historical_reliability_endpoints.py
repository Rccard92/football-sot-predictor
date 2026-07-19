"""Test endpoint Affidabilità storica + alias legacy purchasability-empirical."""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

# Settings richiesto da app.core.database al primo import.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes.cecchino_kpi_signals import router


def _fake_payload() -> dict:
    return {
        "metric_kind": "historical_reliability",
        "version": "cecchino_historical_reliability_v1_1",
        "legacy_version": "cecchino_purchasability_empirical_rating_v1_1",
        "dataset_version": "cecchino_purchasability_dataset_v1_1",
        "status": "ok",
        "items": {
            "1:HOME": {
                "metric_kind": "historical_reliability",
                "version": "cecchino_historical_reliability_v1_1",
                "status": "ok",
                "score": 61,
                "class": "Incerta",
                "market_key": "HOME",
                "sample_size": 40,
                "selected_sample_size": 40,
                "local_sample_size": 40,
                "global_sample_size": 40,
                "wins": 22,
                "losses": 18,
                "voids": 0,
                "win_rate": 0.55,
                "roi": 0.05,
                "stability_ratio": 0.75,
                "cohort_scope": "same_competition",
                "fallback_used": False,
            }
        },
        "summary": {"rows_requested": 1, "rows_scored": 1, "no_db_writes": True},
        "filters": {
            "date_from": "2026-03-15",
            "date_to": "2026-03-15",
            "competition_id": None,
        },
    }


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def test_historical_reliability_endpoint():
    fake = _fake_payload()
    with patch(
        "app.routes.cecchino_kpi_signals.build_historical_reliability_for_panel",
        return_value=dict(fake),
    ) as mock_build:
        client = _client()
        res = client.get(
            "/api/cecchino/kpi-signals/historical-reliability",
            params={"date_from": "2026-03-15", "date_to": "2026-03-15"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["metric_kind"] == "historical_reliability"
    assert body["version"] == "cecchino_historical_reliability_v1_1"
    assert body["items"]["1:HOME"]["score"] == 61
    assert "deprecated" not in body
    mock_build.assert_called_once()
    kwargs = mock_build.call_args.kwargs
    assert kwargs["date_from"] == date(2026, 3, 15)
    assert kwargs["date_to"] == date(2026, 3, 15)


def test_purchasability_empirical_legacy_alias():
    fake = _fake_payload()
    with patch(
        "app.routes.cecchino_kpi_signals.build_historical_reliability_for_panel",
        return_value=dict(fake),
    ) as mock_build:
        client = _client()
        res = client.get(
            "/api/cecchino/kpi-signals/purchasability-empirical",
            params={
                "date_from": "2026-03-15",
                "date_to": "2026-03-15",
                "competition_id": 7,
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["deprecated"] is True
    assert (
        body["replacement_endpoint"]
        == "/api/cecchino/kpi-signals/historical-reliability"
    )
    assert body["items"]["1:HOME"]["score"] == 61
    assert body["items"]["1:HOME"]["class"] == "Incerta"
    mock_build.assert_called_once()
    assert mock_build.call_args.kwargs["competition_id"] == 7


def test_both_endpoints_same_scores():
    fake = _fake_payload()
    with patch(
        "app.routes.cecchino_kpi_signals.build_historical_reliability_for_panel",
        return_value=dict(fake),
    ):
        client = _client()
        a = client.get(
            "/api/cecchino/kpi-signals/historical-reliability",
            params={"date_from": "2026-03-15", "date_to": "2026-03-15"},
        ).json()
        b = client.get(
            "/api/cecchino/kpi-signals/purchasability-empirical",
            params={"date_from": "2026-03-15", "date_to": "2026-03-15"},
        ).json()
    assert a["items"]["1:HOME"]["score"] == b["items"]["1:HOME"]["score"]
    assert a["items"]["1:HOME"]["class"] == b["items"]["1:HOME"]["class"]
    assert set(a["items"]) == set(b["items"])
