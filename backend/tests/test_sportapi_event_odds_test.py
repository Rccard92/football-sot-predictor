"""Test ordine candidate provider_id."""

from __future__ import annotations

from app.models.sportapi_odds_provider import SportApiOddsProvider
from app.services.sportapi.sportapi_event_odds_test_service import candidate_provider_ids


def test_candidate_provider_ids_order():
    row = SportApiOddsProvider(
        provider_slug="sisal",
        provider_name="Sisal",
        provider_id=2325,
        odds_from_id=226,
        live_odds_from_id=99,
        working_odds_provider_id=226,
    )
    ids = candidate_provider_ids(row, explicit_provider_id=1)
    assert ids[0] == 226
    assert 2325 in ids
    assert 226 in ids
    assert 99 in ids
    assert 1 in ids
    assert ids.index(2325) < ids.index(99)


def test_candidate_explicit_only():
    assert candidate_provider_ids(None, explicit_provider_id=2325) == [2325]
