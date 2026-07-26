"""Test API Cecchino Lab (router + dependency override)."""

from __future__ import annotations

import os
from io import BytesIO
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes import cecchino_lab
from app.services.cecchino_data_lab.constants import IMPORT_CONFIRM_TOKEN

SAMPLE = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
    "E0,10/08/2024,15:00,Arsenal,Wolves,2,0,H,1.45,4.50,7.00\n"
)


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")
    app.include_router(cecchino_lab.admin_router, prefix="/api")
    db = MagicMock()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app), db


def test_preview_endpoint_no_write():
    client, db = _app()
    files = {"file": ("E0.csv", BytesIO(SAMPLE.encode("utf-8")), "text/csv")}
    data = {
        "competition_key": "premier_league",
        "season_label": "2024/2025",
    }
    res = client.post("/api/admin/cecchino-lab/imports/preview", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["rows_total"] == 1
    assert body["summary"]["importable"] is True
    assert body["division_code"] == "E0"
    db.commit.assert_not_called()
    db.add.assert_not_called()


def test_import_endpoint_with_confirm():
    client, db = _app()
    with patch(
        "app.routes.cecchino_lab.import_csv_bytes",
        return_value={
            "status": "completed",
            "import_id": 1,
            "dataset_id": 2,
            "rows_imported": 1,
            "rows_skipped": 0,
            "rows_total": 1,
            "warnings_count": 0,
            "errors_count": 0,
            "bet365_coverage": {},
            "file_sha256": "abc",
            "parser_version": "football_data_uk_bet365_v1",
            "dataset_key": "england-premier-league-2024-2025",
        },
    ) as mocked:
        files = {"file": ("E0.csv", BytesIO(SAMPLE.encode("utf-8")), "text/csv")}
        data = {
            "competition_key": "premier_league",
            "season_label": "2024/2025",
            "confirm": IMPORT_CONFIRM_TOKEN,
        }
        res = client.post("/api/admin/cecchino-lab/imports", files=files, data=data)
        assert res.status_code == 200
        assert res.json()["status"] == "completed"
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["confirm"] == IMPORT_CONFIRM_TOKEN
        assert mocked.call_args.kwargs["competition_key"] == "premier_league"


def test_overview_endpoint():
    client, db = _app()
    with patch(
        "app.routes.cecchino_lab.get_overview",
        return_value={"is_empty": True, "matches_total": 0, "datasets_count": 0},
    ):
        res = client.get("/api/cecchino-lab/overview")
        assert res.status_code == 200
        assert res.json()["is_empty"] is True


def test_matches_filters_passed():
    client, db = _app()
    with patch(
        "app.routes.cecchino_lab.list_matches",
        return_value={"items": [], "total": 0, "page": 1, "page_size": 50},
    ) as mocked:
        res = client.get(
            "/api/cecchino-lab/matches",
            params={
                "dataset_id": 3,
                "team": "Arsenal",
                "has_bet365_1x2": True,
                "page": 2,
                "page_size": 25,
                "sort_by": "home_team",
                "sort_dir": "asc",
            },
        )
        assert res.status_code == 200
        kwargs = mocked.call_args.kwargs
        assert kwargs["dataset_id"] == 3
        assert kwargs["team"] == "Arsenal"
        assert kwargs["has_bet365_1x2"] is True
        assert kwargs["page"] == 2
        assert kwargs["page_size"] == 25


def test_data_quality_issues_endpoint():
    client, db = _app()
    with patch(
        "app.routes.cecchino_lab.list_data_quality_issues",
        return_value={"items": [], "total": 0, "top_issue_codes": [], "severity_counts": {}},
    ) as mocked:
        res = client.get(
            "/api/cecchino-lab/data-quality/issues",
            params={"severity": "warning", "dataset_id": 1},
        )
        assert res.status_code == 200
        assert mocked.call_args.kwargs["severity"] == "warning"
        assert mocked.call_args.kwargs["dataset_id"] == 1
