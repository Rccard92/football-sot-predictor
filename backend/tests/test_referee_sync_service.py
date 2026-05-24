"""Test sync arbitro da API-Sports (mock client)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from app.services.api_football_fixture_detail import parse_fixture_detail_item
from app.services.referee_sync_service import RefereeSyncService


FIXTURE_JSON = Path(__file__).resolve().parent / "fixtures" / "api_football" / "sample_fixture.json"


def test_parse_fixture_detail_extracts_referee():
    raw = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    item = {
        "fixture": raw["fixture"],
        "teams": raw["teams"],
        "league": {"id": 135, "season": 2024},
    }
    detail = parse_fixture_detail_item(item)
    assert detail["referee"] == "M. Mariani"
    assert detail["api_fixture_id"] == 999


def test_sync_fixture_referee_not_available(monkeypatch):
    svc = RefereeSyncService(client=MagicMock())
    db = MagicMock()
    fx = MagicMock()
    fx.id = 1
    fx.api_fixture_id = 999
    fx.referee = "old"
    monkeypatch.setattr(svc, "_resolve_fixture", lambda *a, **k: fx)
    monkeypatch.setattr(svc, "_match_name", lambda *a, **k: "Inter - Milan")
    svc._client.get_fixture_by_id.return_value = {
        "fixture": {"id": 999, "referee": None, "date": "2025-01-15T18:00:00+00:00", "status": {"short": "NS"}},
        "teams": {"home": {"name": "Inter"}, "away": {"name": "Milan"}},
        "league": {"id": 135, "season": 2024},
    }
    monkeypatch.setattr(svc, "_upsert_fixture_referee", lambda *a, **k: MagicMock())

    out = svc.sync_fixture(db, fixture_id=1)
    assert out["saved"] is False
    assert out["reason"] == "referee_not_available"
    assert out["referee"] is None
