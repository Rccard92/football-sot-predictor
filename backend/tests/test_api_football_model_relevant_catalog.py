"""Test GET catalogo model-relevant (JSON statico)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _collect_classifications(body: dict) -> set[str]:
    out: set[str] = set()
    for area in body.get("areas") or []:
        for p in area.get("parameters") or []:
            c = p.get("classification")
            if c is not None:
                out.add(str(c))
    for p in (body.get("technical_derivative_sources") or {}).get("fields") or []:
        c = p.get("classification")
        if c is not None:
            out.add(str(c))
    return out


def test_get_model_relevant_catalog():
    r = client.get("/api/data-catalog/model-relevant")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "api_football_model_relevant_catalog_v1"
    assert "areas" in body
    assert "technical_derivative_sources" in body
    tech = body["technical_derivative_sources"]["fields"]
    assert isinstance(tech, list)
    assert any(f.get("classification") == "SORGENTE_DERIVATA_TECNICA" for f in tech)

    for c in _collect_classifications(body):
        assert not c.startswith("NASCONDERE_")
        assert c != "DA_NASCONDERE"

    for area in body["areas"]:
        for p in area["parameters"]:
            assert p.get("selectable") is True
            assert p.get("classification") != "SORGENTE_DERIVATA_TECNICA"

    for p in tech:
        assert p.get("classification") == "SORGENTE_DERIVATA_TECNICA"
        assert p.get("selectable") is False
