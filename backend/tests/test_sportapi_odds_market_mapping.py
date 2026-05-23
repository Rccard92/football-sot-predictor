"""Test upsert mapping mercati SportAPI."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models.sportapi_odds_market_mapping import SportApiOddsMarketMapping
from app.services.sportapi.sportapi_odds_market_mapping_service import SportApiOddsMarketMappingService


def test_upsert_reactivates_existing():
    db = MagicMock()
    existing = MagicMock(spec=SportApiOddsMarketMapping)
    existing.is_active = False
    db.scalar.return_value = existing
    svc = SportApiOddsMarketMappingService()
    row = svc.upsert_mapping(
        db,
        provider_slug="sisal-italy-affiliate",
        raw_market_name="Total Shots on Target",
        normalized_market_key="match_total_sot",
    )
    assert row is existing
    assert existing.is_active is True
    db.commit.assert_called()


def test_upsert_creates_new_row():
    db = MagicMock()
    db.scalar.return_value = None

    def _refresh(obj):
        obj.id = 1

    db.refresh.side_effect = _refresh
    svc = SportApiOddsMarketMappingService()
    svc.upsert_mapping(
        db,
        provider_slug="sisal-italy-affiliate",
        raw_market_name="Team Shots on Target",
        normalized_market_key="match_total_sot",
    )
    db.add.assert_called_once()
    db.commit.assert_called()
