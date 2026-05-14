"""Test flatten JSON e route catalogo diretto API."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.api_football_direct_catalog_io import direct_catalog_cache_path, save_direct_catalog_cache
from app.services.api_football_json_flatten import flatten_json, merge_flattened_counts

client = TestClient(app)

_FIXTURE = Path(__file__).parent / "fixtures" / "api_football" / "sample_fixture.json"


def test_flatten_fixture_statistics_paths():
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    rows = flatten_json(data, prefix="", max_paths=500)
    m = merge_flattened_counts(rows)
    keys = set(m)
    assert 'statistics["Shots on Goal"]' in keys
    assert 'statistics["Total Shots"]' in keys
    assert m['statistics["Shots on Goal"]']["sample_value"] == "5"


def test_get_direct_catalog_empty():
    path = direct_catalog_cache_path()
    if path.is_file():
        path.unlink()
    r = client.get("/api/data-catalog/api-football/direct")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "api_football_direct_catalog_v0_1"
    assert "message" in body
    assert body["summary"]["direct_fields_found"] == 0


def test_get_direct_catalog_with_cache():
    payload = {
        "version": "api_football_direct_catalog_v0_1",
        "season": 2099,
        "provider": "API-Football / API-Sports",
        "last_scan_at": "2099-01-01T00:00:00+00:00",
        "summary": {
            "endpoints_scanned": 1,
            "endpoints_errors": 0,
            "direct_fields_found": 2,
            "fields_used_by_v04": 0,
            "fields_saved_in_db": 0,
            "fields_raw_json_only": 0,
        },
        "areas": [
            {
                "id": "fixtures",
                "title": "Partite / fixture",
                "endpoints": ["fixtures"],
                "direct_fields_found": 1,
                "fields_saved_in_db": 0,
                "fields_raw_json_only": 0,
                "fields_used_by_v04": 0,
                "parameters": [
                    {
                        "stable_id": "fixtures::fixture.id",
                        "json_path": "fixture.id",
                        "endpoint": "fixtures",
                        "appeared_in_endpoints": ["fixtures"],
                        "area_id": "fixtures",
                        "technical_name": "id",
                        "name_it": "ID partita API",
                        "name_it_auto": False,
                        "description_it": "x",
                        "tooltip_it": None,
                        "sample_value": 1,
                        "sample_type": "numero",
                        "examples_count": 1,
                        "appeared_in_raw_json": False,
                        "api_label": "found_in_scan",
                        "db_status": "saved_column",
                        "db_location_hint": "fixtures.api_fixture_id",
                        "model_v04_status": "not_used_v04",
                        "note_it": None,
                    }
                ],
            }
        ],
        "diagnostics": [{"endpoint": "fixtures", "status": "ok"}],
    }
    save_direct_catalog_cache(payload)
    r = client.get("/api/data-catalog/api-football/direct")
    assert r.status_code == 200
    body = r.json()
    assert "diagnostics" not in body
    assert body["season"] == 2099
    assert len(body["areas"]) >= 1


def test_post_scan_without_api_key_returns_503(monkeypatch):
    from unittest.mock import MagicMock

    import app.routes.admin_debug_api_football_catalog as mod

    def fake() -> MagicMock:
        m = MagicMock()
        m.api_football_key = ""
        m.api_football_base_url = "https://v3.football.api-sports.io"
        m.default_league_id = 135
        m.default_season = 2025
        return m

    monkeypatch.setattr(mod, "get_settings", fake)
    r = client.post("/api/admin/debug/api-football-catalog/serie-a/2025/scan")
    assert r.status_code == 503
