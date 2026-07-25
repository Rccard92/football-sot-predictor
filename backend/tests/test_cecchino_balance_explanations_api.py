"""Test API GET /api/cecchino/today/{id}/balance-explanations."""

from __future__ import annotations

import os
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes.cecchino_today import router


def _eligible_row(**overrides):
    base = dict(
        id=11,
        local_fixture_id=2,
        provider_fixture_id=777,
        home_team_name="Home",
        away_team_name="Away",
        kickoff=None,
        scan_date=date(2026, 7, 25),
        eligibility_status="eligible",
        cecchino_output_json={
            "final": {
                "status": "available",
                "quota_1": 4.59,
                "quota_x": 3.40,
                "quota_2": 2.13,
                "prob_1": 0.20,
                "prob_x": 0.29,
                "prob_2": 0.51,
            },
            "goal_markets": {
                "under_2_5": {"final_odd": 1.35},
                "over_2_5": {"final_odd": 3.90},
            },
        },
        kpi_panel_json=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def client_fixture(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = MagicMock()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override

    def boom(*_a, **_k):
        raise AssertionError("builder operativo proibito")

    for name in (
        "get_today_fixture_detail",
        "build_today_payload",
        "run_scan",
        "sync_cecchino_signal_activations",
        "update_today_fixture_results",
    ):
        monkeypatch.setattr(
            f"app.services.cecchino.cecchino_today_service.{name}",
            boom,
            raising=False,
        )

    return TestClient(app), db


def test_api_not_found(monkeypatch):
    c, db = client_fixture(monkeypatch)
    db.get.return_value = None
    with c:
        r = c.get("/api/cecchino/today/1/balance-explanations")
    assert r.status_code == 404


def test_api_not_eligible(monkeypatch):
    c, db = client_fixture(monkeypatch)
    row = _eligible_row()
    row.eligibility_status = "excluded_cup"
    db.get.return_value = row
    with c:
        r = c.get("/api/cecchino/today/11/balance-explanations")
    assert r.status_code == 422
    assert r.json()["code"] == "not_eligible"


def test_api_balance_missing(monkeypatch):
    c, db = client_fixture(monkeypatch)
    row = _eligible_row(cecchino_output_json={})
    db.get.return_value = row
    with c:
        r = c.get("/api/cecchino/today/11/balance-explanations")
    assert r.status_code == 422
    assert r.json()["code"] == "balance_not_available"


def test_api_ok(monkeypatch):
    c, db = client_fixture(monkeypatch)
    db.get.return_value = _eligible_row()
    with c:
        r = c.get("/api/cecchino/today/11/balance-explanations")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "partial")
    assert body["diagnostic_re_evaluation_only"] is True
    assert body["no_operational_recalculation"] is True
    assert len(body["pillars"]) == 4
    assert db.commit.call_count == 0


def test_api_four_pillars_order(monkeypatch):
    c, db = client_fixture(monkeypatch)
    db.get.return_value = _eligible_row()
    with c:
        r = c.get("/api/cecchino/today/11/balance-explanations")
    body = r.json()
    keys = list(body["pillars"].keys())
    assert keys == ["geometry", "conviction", "draw_credibility", "coherence_1_2"]
    assert body["pillars"]["geometry"]["pillar_number"] == 1
    assert body["pillars"]["coherence_1_2"]["pillar_number"] == 4
