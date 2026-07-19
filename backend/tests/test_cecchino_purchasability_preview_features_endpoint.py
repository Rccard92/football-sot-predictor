"""Test endpoint purchasability-preview/features — Fase 2."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes.cecchino_kpi_signals import router
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME


def _fixture(panel=None):
    fx = MagicMock()
    fx.id = 42
    fx.local_fixture_id = 777
    fx.provider_fixture_id = 900
    fx.competition_id = 3
    fx.scan_date = None
    fx.kickoff = datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)
    fx.kpi_panel_json = panel
    fx.odds_snapshot_json = {
        "odds_meta": {"odds_fetched_at": "2026-03-15T12:00:00+00:00"}
    }
    fx.odds_checked_at = None
    fx.updated_at = datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc)
    fx.cecchino_output_json = None
    # Spec: nessun attributo legacy obbligatorio; del evita MagicMock auto-attr
    del fx.cecchino_output
    return fx


def _panel_rows():
    return {
        "bookmaker": {"name": "Betfair"},
        "rows": [
            {
                "market_key": SEL_HOME,
                "quota_book": 2.1,
                "quota_cecchino": 1.95,
                "prob_book": 1 / 2.1,
                "prob_cecchino": 0.48,
                "vantaggio_prob": 0.48 - 1 / 2.1,
                "edge_pct": 7.0,
                "score_acquisto": 0.03,
                "rating": 70,
                "rating_label": "Buona",
                "status": "ok",
                "book_source": "betfair",
                "cecchino_source": "model",
            },
            {
                "market_key": SEL_DRAW,
                "quota_book": 3.4,
                "quota_cecchino": 3.2,
                "prob_book": 1 / 3.4,
                "prob_cecchino": 0.30,
                "vantaggio_prob": 0.01,
                "edge_pct": 5.0,
                "score_acquisto": 0.02,
                "rating": 60,
                "status": "ok",
                "book_source": "betfair",
                "cecchino_source": "model",
            },
            {
                "market_key": SEL_AWAY,
                "quota_book": 3.6,
                "quota_cecchino": 3.5,
                "prob_book": 1 / 3.6,
                "prob_cecchino": 0.22,
                "vantaggio_prob": -0.05,
                "edge_pct": 2.0,
                "score_acquisto": 0.01,
                "rating": 55,
                "status": "ok",
                "book_source": "betfair",
                "cecchino_source": "model",
            },
        ],
    }


def _client(fixture_or_none):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = MagicMock()
    db.get.return_value = fixture_or_none

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    return TestClient(app), db


def test_endpoint_fixture_ok():
    client, db = _client(_fixture(_panel_rows()))
    res = client.get("/api/cecchino/kpi-signals/purchasability-preview/features/42")
    assert res.status_code == 200
    body = res.json()
    assert body["no_score_formula"] is True
    assert body["no_db_writes"] is True
    assert body["feature_version"] == "cecchino_purchasability_features_v1"
    assert body["summary"]["total"] == 3
    for item in body["items"]:
        assert item["score"] is None
        assert item["status"] == "not_calculated"
        assert item["class"] is None
    db.commit.assert_not_called()


def test_endpoint_404():
    client, _ = _client(None)
    res = client.get("/api/cecchino/kpi-signals/purchasability-preview/features/999")
    assert res.status_code == 404


def test_endpoint_missing_panel():
    client, _ = _client(_fixture(None))
    res = client.get("/api/cecchino/kpi-signals/purchasability-preview/features/42")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["no_score_formula"] is True
