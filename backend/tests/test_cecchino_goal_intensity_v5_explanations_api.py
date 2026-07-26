"""Test API GET /api/cecchino/today/{id}/goal-intensity-v5-explanations."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_goal_intensity_v5_preview import CecchinoGoalIntensityV5PreviewBundle
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.routes.cecchino_today import router
from tests.test_cecchino_goal_intensity_v5_explanations import _row, _snap_from_bundle
from tests.test_cecchino_goal_intensity_v5_preview import _bundle


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
        r = c.get("/api/cecchino/today/1/goal-intensity-v5-explanations")
    assert r.status_code == 404


def test_api_not_eligible(monkeypatch):
    c, db = client_fixture(monkeypatch)
    row = _row()
    row.eligibility_status = "excluded_cup"
    db.get.return_value = row
    with c:
        r = c.get("/api/cecchino/today/100/goal-intensity-v5-explanations")
    assert r.status_code == 422
    assert r.json()["code"] == "not_eligible"


def test_api_snapshot_missing(monkeypatch):
    c, db = client_fixture(monkeypatch)
    db.get.return_value = _row()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations.get_active_bundle",
        return_value=_bundle(),
    ):
        db.scalars.return_value.first.return_value = None
        with c:
            r = c.get("/api/cecchino/today/100/goal-intensity-v5-explanations")
    assert r.status_code == 422
    assert r.json()["code"] == "goal_intensity_v5_not_available"


def test_api_ok(monkeypatch):
    c, db = client_fixture(monkeypatch)
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)

    def _get(model, pk):
        if model is CecchinoTodayFixture:
            return _row()
        if model is CecchinoGoalIntensityV5PreviewBundle:
            return bundle
        return None

    db.get.side_effect = _get
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations.get_active_bundle",
        return_value=bundle,
    ):
        db.scalars.return_value.first.return_value = snap
        with c:
            r = c.get("/api/cecchino/today/100/goal-intensity-v5-explanations")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "partial")
    assert body["diagnostic_re_evaluation_only"] is True
    assert body["no_operational_recalculation"] is True
    assert body["source_mode"] == "persisted_goal_intensity_v5_preview_snapshot"
    assert len(body["dimensions"]) == 4
    assert len(body["candidates"]) == 4
    assert db.commit.call_count == 0
    assert "train_values" not in r.text
