"""Test upsert fixture_bookmaker_odds."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.fixture_bookmaker_odds import FixtureBookmakerOdds
from app.services.bookmakers.fixture_bookmaker_odds_repository import upsert_fixture_odds


def test_upsert_inserts_when_missing():
    db = MagicMock()
    db.scalar.return_value = None
    row = upsert_fixture_odds(
        db,
        competition_id=1,
        fixture_id=10,
        provider_source="sportapi",
        provider_bookmaker_id="42",
        bookmaker_name="Sisal",
        normalized_market="MATCH_WINNER_1X2",
        home_odds=2.1,
        draw_odds=3.2,
        away_odds=3.5,
    )
    db.add.assert_called_once()
    assert isinstance(row, FixtureBookmakerOdds)
    assert row.fixture_id == 10
    assert row.home_odds == 2.1


def test_upsert_updates_existing():
    existing = FixtureBookmakerOdds(
        competition_id=1,
        fixture_id=10,
        provider_source="sportapi",
        provider_bookmaker_id="42",
        bookmaker_name="Sisal",
        normalized_market="MATCH_WINNER_1X2",
        home_odds=1.9,
        draw_odds=3.0,
        away_odds=4.0,
        odds_updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.scalar.return_value = existing
    row = upsert_fixture_odds(
        db,
        competition_id=1,
        fixture_id=10,
        provider_source="sportapi",
        provider_bookmaker_id="42",
        bookmaker_name="Sisal IT",
        normalized_market="MATCH_WINNER_1X2",
        home_odds=2.0,
        draw_odds=3.1,
        away_odds=3.6,
    )
    db.add.assert_not_called()
    assert row.bookmaker_name == "Sisal IT"
    assert row.home_odds == 2.0
