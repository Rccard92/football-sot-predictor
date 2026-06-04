"""Test discovery provider bookmaker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.bookmakers.bookmaker_providers_discovery import (
    BookmakerProvidersDiscoveryService,
    STATUS_NOT_CONFIGURED,
)


@patch("app.services.bookmakers.bookmaker_providers_discovery.get_settings")
@patch("app.services.bookmakers.bookmaker_providers_discovery.sportapi_configured")
def test_providers_shape_not_configured_without_keys(mock_sa_cfg, mock_settings):
    settings = MagicMock()
    settings.api_football_key = ""
    mock_settings.return_value = settings
    mock_sa_cfg.return_value = False

    db = MagicMock()
    db.scalar.return_value = 0

    out = BookmakerProvidersDiscoveryService().list_sources(db)
    assert "sources" in out
    assert len(out["sources"]) == 2
    assert out["sources"][0]["provider_source"] == "api_football"
    assert out["sources"][0]["status"] == STATUS_NOT_CONFIGURED
    assert out["sources"][1]["provider_source"] == "sportapi"
    assert out["sources"][1]["status"] == STATUS_NOT_CONFIGURED
