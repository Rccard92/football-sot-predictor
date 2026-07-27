"""Test API e job scansione storica Cecchino Lab."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes import cecchino_lab
from app.services.cecchino_data_lab.constants import HISTORICAL_SCAN_CONFIRM_TOKEN
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_scan_service import start_historical_scan


def _app() -> tuple[TestClient, MagicMock]:
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")
    app.include_router(cecchino_lab.admin_router, prefix="/api")
    db = MagicMock()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app), db


def test_preflight_endpoint():
    client, _db = _app()
    with patch(
        "app.routes.cecchino_lab.run_historical_scan_preflight",
        return_value={"season_label": "2021/2022", "status": "ready", "matches_total": 0},
    ):
        res = client.post(
            "/api/admin/cecchino-lab/historical-scans/preflight",
            json={"season_label": "2021/2022"},
        )
    assert res.status_code == 200
    assert res.json()["status"] == "ready"


def test_start_requires_confirm():
    db = MagicMock()
    with pytest.raises(CecchinoLabImportError) as ei:
        start_historical_scan(db, season_label="2021/2022", confirm="WRONG", background=False)
    assert ei.value.code == "confirm_required"


def test_start_endpoint_with_confirm_mocked():
    client, _db = _app()
    fake_run = {
        "id": 1,
        "season_label": "2021/2022",
        "status": "pending",
        "scan_version": "v1",
        "requested_at": None,
        "started_at": None,
        "completed_at": None,
        "current_dataset_id": None,
        "current_match_id": None,
        "current_competition": None,
        "matches_total": 10,
        "matches_processed": 0,
        "matches_eligible_core": 0,
        "matches_excluded": 0,
        "matches_error": 0,
        "progress_pct": 0,
    }
    with patch(
        "app.routes.cecchino_lab.start_historical_scan",
        return_value=fake_run,
    ):
        res = client.post(
            "/api/admin/cecchino-lab/historical-scans",
            json={
                "season_label": "2021/2022",
                "confirm": HISTORICAL_SCAN_CONFIRM_TOKEN,
            },
        )
    assert res.status_code == 202
    assert res.json()["id"] == 1


def test_list_scans_endpoint():
    client, _db = _app()
    with patch("app.routes.cecchino_lab.list_historical_scans", return_value=[]):
        res = client.get("/api/cecchino-lab/historical-scans")
    assert res.status_code == 200
    assert res.json() == []


def test_duplicate_lock():
    db = MagicMock()
    with patch(
        "app.services.cecchino_data_lab.historical_scan_service.run_historical_scan_preflight",
        return_value={"status": "ready"},
    ):
        active = SimpleNamespace(id=99, status="running")
        db.scalars.return_value.first.return_value = active
        with pytest.raises(CecchinoLabImportError) as ei:
            start_historical_scan(
                db,
                season_label="2021/2022",
                confirm=HISTORICAL_SCAN_CONFIRM_TOKEN,
                background=False,
            )
        assert ei.value.code == "duplicate_active_run"


def test_ai_report_zip_structure():
    import io
    import zipfile

    from app.services.cecchino_data_lab.historical_ai_report import build_ai_report_zip_bytes

    run = SimpleNamespace(
        id=7,
        season_label="2021/2022",
        scan_version="cecchino_lab_historical_scan_v1",
        source_git_commit="abc",
        preflight_json={"status": "ready"},
    )
    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [[], []]
    filename, data = build_ai_report_zip_bytes(db, 7)
    assert "2021_2022" in filename
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "matches.jsonl" in names
    assert "markets.jsonl" in names
    assert "AI_INSTRUCTIONS.md" in names
    assert "SCHEMA.md" in names
