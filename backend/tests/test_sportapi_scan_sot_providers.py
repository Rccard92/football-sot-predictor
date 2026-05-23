"""Test scansione provider SOT (unit, client mock)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.sportapi_odds_provider import SportApiOddsProvider
from app.services.sportapi.sportapi_scan_sot_providers_service import (
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


def test_scan_returns_no_sot_message_when_only_non_sot_markets():
    db = MagicMock()
    prov = SportApiOddsProvider(
        provider_slug="sisal-italy-affiliate",
        provider_name="Sisal",
        provider_country="IT",
        provider_id=2325,
        odds_from_id=226,
        is_active=True,
    )
    db.scalars.return_value.all.return_value = [prov]

    client = MagicMock()
    client.get_event_odds.return_value = _sisal_payload_no_sot()

    svc = SportApiScanSotProvidersService(client=client)
    with patch.object(svc._detail_svc, "sync_detail"):
        out = svc.scan(db, sportapi_event_id=13980080, country="IT")

    assert out["status"] == "success"
    assert out["providers_with_sot"] == 0
    assert out["providers_with_odds"] == 1
    assert out["message"] == NO_SOT_MESSAGE
    row = out["rows"][0]
    assert row["has_sot_market"] is False
    assert row["markets_count"] == 2
