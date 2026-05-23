"""Test scansione provider SOT (unit, client mock)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.sportapi_odds_provider import SportApiOddsProvider
from app.services.sportapi.sportapi_scan_sot_providers_service import (
    NO_PROVIDERS_IN_DB_MESSAGE,
    NO_SOT_MESSAGE,
    SportApiScanSotProvidersService,
)


def _sisal_payload_no_sot() -> dict:
    return {
        "markets": [
            {
                "marketName": "Full time",
                "choices": [{"name": "1", "price": 2.0}, {"name": "X", "price": 3.0}, {"name": "2", "price": 4.0}],
            },
            {
                "marketName": "Corners 2-Way",
                "choiceGroups": [
                    {"choiceGroup": "9,5", "choices": [{"name": "Under", "price": 1.75}, {"name": "Over", "price": 2.0}]},
                ],
            },
        ],
    }


def test_scan_includes_provider_with_null_country():
    db = MagicMock()
    prov = SportApiOddsProvider(
        provider_slug="sisal-italy-affiliate",
        provider_name="Sisal",
        provider_country=None,
        provider_id=2325,
        odds_from_id=226,
        is_active=True,
    )

    def _scalars_side_effect(stmt):
        result = MagicMock()
        result.all.return_value = [prov]
        return result

    db.scalars.side_effect = _scalars_side_effect

    client = MagicMock()
    client.get_event_odds.return_value = _sisal_payload_no_sot()

    svc = SportApiScanSotProvidersService(client=client)
    with patch.object(svc._detail_svc, "sync_detail"):
        out = svc.scan(db, sportapi_event_id=13980080, country="IT")

    assert out["providers_in_db"] == 1
    assert out["providers_matching_country"] == 1
    assert out["providers_scanned"] == 1
    assert out["providers_with_sot"] == 0
    assert out["providers_with_odds"] == 1
    assert out["scan_status"] == "ok"
    assert out["message"] == NO_SOT_MESSAGE


def test_scan_no_providers_in_db_message():
    db = MagicMock()
    empty = MagicMock()
    empty.all.return_value = []
    db.scalars.return_value = empty

    svc = SportApiScanSotProvidersService(client=MagicMock())
    out = svc.scan(db, sportapi_event_id=13980080, country="IT")

    assert out["providers_scanned"] == 0
    assert out["scan_status"] == "no_providers_in_db"
    assert out["message"] == NO_PROVIDERS_IN_DB_MESSAGE
