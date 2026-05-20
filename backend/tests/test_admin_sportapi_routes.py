"""Route admin SportAPI — disabled quando env off."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_confirm_mapping_requires_sportapi_enabled(client):
    with patch("app.routes.admin_sportapi.sportapi_configured", return_value=False):
        r = client.post(
            "/api/admin/sportapi/mappings/1/confirm",
            json={"provider_event_id": 13980080, "confidence_score": 95},
        )
    assert r.status_code == 400
