"""API Cecchino — scope competition e debug."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_debug_calculate_san_lorenzo_parity():
    body = {
        "home_away": {
            "home": {"wins": 3, "draws": 2, "losses": 3},
            "away": {"wins": 0, "draws": 3, "losses": 5},
        },
        "totals": {
            "home": {"wins": 5, "draws": 7, "losses": 4},
            "away": {"wins": 1, "draws": 8, "losses": 7},
        },
        "last5_home_away": {
            "home": {"wins": 1, "draws": 2, "losses": 2},
            "away": {"wins": 0, "draws": 2, "losses": 3},
        },
        "last6_totals": {
            "home": {"wins": 2, "draws": 3, "losses": 1},
            "away": {"wins": 1, "draws": 2, "losses": 3},
        },
    }
    resp = client.post("/api/admin/cecchino/debug/calculate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["calculation_status"] == "available"
    final = data["output"]["final"]
    assert final["quota_1"] == pytest.approx(2.4067, abs=0.01)


def test_fixture_detail_competition_mismatch():
    mock_comp = MagicMock()
    mock_comp.id = 1
    err_payload = {
        "status": "error",
        "code": "fixture_competition_mismatch",
        "competition_id": 1,
        "fixture_id": 42,
    }

    with (
        patch(
            "app.routes.cecchino.CompetitionService.get_by_id_or_raise",
            return_value=mock_comp,
        ),
        patch(
            "app.routes.cecchino._validate_fixture_for_competition",
            return_value=(None, err_payload, 404),
        ),
    ):
        resp = client.get("/api/competitions/1/cecchino/fixture/42")
        assert resp.status_code == 404
        assert resp.json()["code"] == "fixture_competition_mismatch"


def test_upcoming_endpoint_ok():
    mock_comp = MagicMock()
    mock_comp.id = 7
    payload = {
        "status": "ok",
        "cecchino_version": "cecchino_v0_1_excel_parity",
        "competition_id": 7,
        "fixtures": [],
    }

    with (
        patch(
            "app.routes.cecchino.CompetitionService.get_by_id_or_raise",
            return_value=mock_comp,
        ),
        patch("app.routes.cecchino.build_upcoming_list", return_value=payload),
    ):
        resp = client.get("/api/competitions/7/cecchino/upcoming")
        assert resp.status_code == 200
        assert resp.json()["competition_id"] == 7
