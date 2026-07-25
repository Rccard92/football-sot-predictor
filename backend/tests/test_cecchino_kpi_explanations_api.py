"""Test API GET /api/cecchino/today/{id}/kpi-explanations."""

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
from app.services.cecchino.cecchino_constants import (
    FINAL_QUOTA_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import _prob_from_odd
from app.services.cecchino.cecchino_selection_keys import SEL_HOME


def _pic(odd: float) -> dict:
    return {
        "status": "available",
        "sample_home": 10,
        "sample_away": 10,
        "home_context": {"wins": 5, "draws": 3, "losses": 2},
        "away_context": {"wins": 2, "draws": 3, "losses": 5},
        "outcome_1": {"prob": 1 / odd, "quota": odd},
        "outcome_x": {"prob": 0.3, "quota": 3.33},
        "outcome_2": {"prob": 0.2, "quota": 5.0},
        "warnings": [],
    }


def _eligible_row() -> SimpleNamespace:
    q1 = 2.06
    pb = _prob_from_odd(2.40)
    pc = _prob_from_odd(q1)
    return SimpleNamespace(
        id=7,
        local_fixture_id=1,
        provider_fixture_id=555,
        home_team_name="A",
        away_team_name="B",
        kickoff=None,
        scan_date=date(2026, 7, 25),
        competition_id=1,
        eligibility_status="eligible",
        odds_snapshot_json={},
        cecchino_output_json={
            "picchetti": {
                PICCHETTO_KEY_TOTALS: _pic(1.95),
                PICCHETTO_KEY_HOME_AWAY: _pic(2.10),
                PICCHETTO_KEY_LAST6_TOTALS: _pic(2.20),
                PICCHETTO_KEY_LAST5_HOME_AWAY: _pic(2.00),
            },
            "final": {
                "status": "available",
                "quota_1": q1,
                "quota_x": 3.4,
                "quota_2": 4.5,
                "prob_1": pc,
                "prob_x": 0.2941,
                "prob_2": 0.2222,
                "weights": dict(FINAL_QUOTA_WEIGHTS),
            },
            "goal_markets": {},
            "purchasability_preview": {
                "snapshot_version": "cecchino_purchasability_snapshot_v1",
                "contract_version": "cecchino_purchasability_v1_preview_contract",
                "candidate_version": "cecchino_purchasability_v1_preview_candidate_2",
                "candidate_name": "balanced_geometric_v1_1",
                "status": "available",
                "items": [],
                "summary": {},
                "contains_result_fields": False,
                "contains_settlement_fields": False,
                "signals_integration": False,
            },
        },
        kpi_panel_json={
            "version": "cecchino_kpi_v2_betfair",
            "rows": [
                {
                    "market_key": SEL_HOME,
                    "segno": "1",
                    "label": "1",
                    "quota_book": 2.40,
                    "quota_cecchino": q1,
                    "prob_book": pb,
                    "prob_cecchino": pc,
                    "vantaggio_prob": round(pc - pb, 4),
                    "edge_pct": round((2.40 / q1 - 1) * 100, 2),
                    "score_acquisto": round(pc * round((2.40 / q1 - 1) * 100, 2) / 100, 3),
                    "rating": 50,
                    "rating_label": "Sufficiente",
                    "status": "available",
                },
            ],
            "warnings": [],
        },
    )


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    db = MagicMock()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_explanations._build_hr_index_for_fixture",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_explanations._rebuild_purchasability_candidate",
        lambda row, kpi: (None, (row.cecchino_output_json or {}).get("purchasability_preview") or {}),
    )

    # Builder proibiti: se chiamati falliscono
    def boom(*_a, **_k):
        raise AssertionError("builder proibito")

    for mod, name in [
        ("app.services.cecchino.cecchino_today_service", "get_today_fixture_detail"),
        ("app.services.cecchino.cecchino_today_service", "build_today_payload"),
    ]:
        monkeypatch.setattr(f"{mod}.{name}", boom, raising=False)

    with TestClient(app) as c:
        yield c, db


def test_api_not_found(client):
    c, db = client
    db.get.return_value = None
    r = c.get("/api/cecchino/today/1/kpi-explanations")
    assert r.status_code == 404


def test_api_not_eligible(client):
    c, db = client
    row = _eligible_row()
    row.eligibility_status = "excluded_cup"
    db.get.return_value = row
    r = c.get("/api/cecchino/today/7/kpi-explanations")
    assert r.status_code == 422
    assert r.json()["code"] == "not_eligible"


def test_api_kpi_not_available(client):
    c, db = client
    row = _eligible_row()
    row.kpi_panel_json = None
    db.get.return_value = row
    r = c.get("/api/cecchino/today/7/kpi-explanations")
    assert r.status_code == 422
    assert r.json()["code"] == "kpi_not_available"


def test_api_eligible_ok(client):
    c, db = client
    db.get.return_value = _eligible_row()
    r = c.get("/api/cecchino/today/7/kpi-explanations")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "partial")
    assert body["no_model_recalculation"] is True
    assert "segno" not in body["markets"][SEL_HOME]
    assert "quota_book" not in body["markets"][SEL_HOME]
    assert "prob_book" in body["markets"][SEL_HOME]
    assert db.commit.call_count == 0
    assert db.add.call_count == 0
