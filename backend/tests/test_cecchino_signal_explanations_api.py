"""Test API GET /api/cecchino/today/{id}/signal-explanations."""

from __future__ import annotations

import os
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes.cecchino_today import router
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix


def _eligible_row():
    matrix = build_signals_matrix(
        q1=2.11,
        qx=3.40,
        q2=4.50,
        sample_home_away_split=16,
        prob_1=0.47,
        prob_x=0.29,
        prob_2=0.22,
        under_2_5_cecchino_odd=1.85,
    )
    return SimpleNamespace(
        id=11,
        local_fixture_id=2,
        provider_fixture_id=777,
        home_team_name="Home",
        away_team_name="Away",
        kickoff=None,
        scan_date=date(2026, 7, 25),
        eligibility_status="eligible",
        cecchino_output_json={"signals_matrix": matrix},
    )


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = MagicMock()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override

    def boom(*_a, **_k):
        raise AssertionError("builder proibito")

    for name in (
        "get_today_fixture_detail",
        "build_today_payload",
    ):
        monkeypatch.setattr(
            f"app.services.cecchino.cecchino_today_service.{name}",
            boom,
            raising=False,
        )

    with TestClient(app) as c:
        yield c, db


def test_api_not_found(client):
    c, db = client
    db.get.return_value = None
    r = c.get("/api/cecchino/today/1/signal-explanations")
    assert r.status_code == 404


def test_api_not_eligible(client):
    c, db = client
    row = _eligible_row()
    row.eligibility_status = "excluded_cup"
    db.get.return_value = row
    r = c.get("/api/cecchino/today/11/signal-explanations")
    assert r.status_code == 422
    assert r.json()["code"] == "not_eligible"


def test_api_matrix_missing(client):
    c, db = client
    row = _eligible_row()
    row.cecchino_output_json = {}
    db.get.return_value = row
    r = c.get("/api/cecchino/today/11/signal-explanations")
    assert r.status_code == 422
    assert r.json()["code"] == "signals_matrix_not_available"


def test_api_ok(client):
    c, db = client
    db.get.return_value = _eligible_row()
    r = c.get("/api/cecchino/today/11/signal-explanations")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "partial")
    assert body["active_cell_count"] == 26
    assert body["diagnostic_re_evaluation_only"] is True
    assert db.commit.call_count == 0
