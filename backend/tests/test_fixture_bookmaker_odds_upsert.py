"""Test upsert fixture_bookmaker_odds (per selection)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.fixture_bookmaker_odds import FixtureBookmakerOdds
from app.services.bookmakers.fixture_bookmaker_odds_repository import upsert_selection_odds


def test_upsert_selection_inserts_when_missing():
    db = MagicMock()
    db.scalar.return_value = None
    row = upsert_selection_odds(
        db,
        competition_id=1,
        fixture_id=10,
        provider_source="api_football",
        provider_bookmaker_id="8",
        bookmaker_name="Bet365",
        normalized_market="MATCH_WINNER_1X2",
        selection_key="HOME",
        selection_label="1",
        odds_value=2.1,
    )
    db.add.assert_called_once()
    assert isinstance(row, FixtureBookmakerOdds)
    assert row.selection_key == "HOME"
    assert row.odds_value == 2.1


def test_upsert_selection_updates_existing():
    existing = FixtureBookmakerOdds(
        competition_id=1,
        fixture_id=10,
        provider_source="api_football",
        provider_bookmaker_id="8",
        bookmaker_name="Bet365",
        normalized_market="MATCH_WINNER_1X2",
        selection_key="HOME",
        selection_label="1",
        odds_value=1.9,
        odds_updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.scalar.return_value = existing
    row = upsert_selection_odds(
        db,
        competition_id=1,
        fixture_id=10,
        provider_source="api_football",
        provider_bookmaker_id="8",
        bookmaker_name="Bet365",
        normalized_market="MATCH_WINNER_1X2",
        selection_key="HOME",
        odds_value=2.0,
    )
    db.add.assert_not_called()
    assert row.odds_value == 2.0
