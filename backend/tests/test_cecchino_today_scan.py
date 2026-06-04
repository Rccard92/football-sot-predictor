"""Test endpoint e orchestrazione Cecchino Today."""

from __future__ import annotations

import os
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_scan_endpoint_delegates_to_service():
    report = {
        "status": "ok",
        "version": "cecchino_today_v0_1_manual_discovery",
        "scan_date": "2026-06-04",
        "total_discovered": 2,
        "eligible": 1,
        "excluded": {"excluded_cup": 1},
        "excluded_total": 1,
        "warnings": [],
        "fixtures_processed": 2,
    }
    with patch("app.routes.cecchino_today.run_scan", return_value=report) as mock_run:
        resp = client.post("/api/admin/cecchino/today/scan", json={"scan_date": "2026-06-04"})
    assert resp.status_code == 200
    assert resp.json()["eligible"] == 1
    mock_run.assert_called_once()


def test_list_endpoint_eligible_only():
    payload = {
        "status": "ok",
        "version": "cecchino_today_v0_1_manual_discovery",
        "scan_date": "2026-06-04",
        "total": 1,
        "countries": [
            {
                "country_name": "Italy",
                "leagues": [
                    {
                        "league_name": "Serie A",
                        "fixtures": [{"id": 99, "home_team_name": "Bologna", "away_team_name": "Inter"}],
                    },
                ],
            },
        ],
    }
    with patch("app.routes.cecchino_today.list_eligible_today", return_value=payload):
        resp = client.get("/api/cecchino/today?date=2026-06-04")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_excluded_admin_endpoint():
    payload = {
        "status": "ok",
        "version": "cecchino_today_v0_1_manual_discovery",
        "scan_date": "2026-06-04",
        "total": 1,
        "fixtures": [{"id": 1, "eligibility_status": "excluded_cup"}],
    }
    with patch("app.routes.cecchino_today.list_excluded_today", return_value=payload):
        resp = client.get("/api/admin/cecchino/today/excluded?date=2026-06-04")
    assert resp.status_code == 200
    assert resp.json()["fixtures"][0]["eligibility_status"] == "excluded_cup"


def test_run_scan_saves_excluded_competition():
    from datetime import timezone as tz

    from app.services.cecchino.cecchino_today_service import run_scan

    db = MagicMock()
    db.scalar.return_value = None
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()

    client_mock = MagicMock()
    client_mock.get_fixtures_by_date.return_value = [
        {
            "league": {"name": "Coppa Italia", "country": "Italy", "type": "Cup", "season": 2025, "id": 1},
            "fixture": {"id": 100, "date": "2026-06-04T20:00:00+00:00", "status": {"short": "NS"}},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        },
    ]

    fixed_now = datetime(2026, 6, 4, 12, 0, tzinfo=tz.utc)
    with (
        patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=tz.utc),
        patch("app.services.cecchino.cecchino_today_service.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        report = run_scan(db, scan_date=date(2026, 6, 4), client=client_mock)
    assert report["status"] == "ok"
    assert report["eligible"] == 0
    assert report["excluded"].get("excluded_cup") == 1
    db.add.assert_called()
