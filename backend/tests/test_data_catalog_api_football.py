"""Test endpoint catalogo API-Football (read-only)."""

from fastapi.testclient import TestClient

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT
from app.data.api_football_catalog import CATALOG_KEY_TO_FRAMEWORK_KEYS, count_catalog_parameters
from app.main import app
from app.services.model_applied_variable_manifest import manifest_for_model

client = TestClient(app)


def test_count_catalog_parameters_is_69():
    assert count_catalog_parameters() == 69


def test_get_api_football_catalog():
    r = client.get("/api/data-catalog/api-football")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == "api_football_catalog_v0_1"
    assert "areas" in data
    assert isinstance(data["areas"], list)
    assert len(data["areas"]) >= 11

    keys: set[str] = set()
    for area in data["areas"]:
        for p in area["parameters"]:
            keys.add(p["key"])
            assert "api_status" in p
            assert "db_status" in p
            assert "model_v04_status" in p
            assert "framework_keys" in p
            assert "in_v04_manifest" in p

    assert "shots_on_target" in keys
    assert "standing_rank" in keys
    assert len(keys) == 69
    assert data.get("model_version_reference") == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT


def test_framework_mapping_coherent_with_manifest():
    v04_fw = {s.framework_key for s in manifest_for_model(BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT) if s.framework_key}

    for catalog_key, fw_keys in CATALOG_KEY_TO_FRAMEWORK_KEYS.items():
        for fk in fw_keys:
            assert fk in v04_fw, f"framework key {fk!r} for catalog {catalog_key!r} missing from v0.4 manifest"
