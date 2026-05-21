"""Test risoluzione event_id per odds discovery (logica pura)."""

from __future__ import annotations

import pytest

from app.services.sportapi.sportapi_odds_discovery_service import MappingNotFoundError


def test_mapping_not_found_is_distinct():
    exc = MappingNotFoundError("Mapping SportAPI non disponibile per questa fixture.")
    assert "Mapping" in str(exc)
