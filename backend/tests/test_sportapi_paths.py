"""Test path template SportAPI RapidAPI."""

from app.services.sportapi import sportapi_paths


def test_scheduled_events_path():
    assert (
        sportapi_paths.scheduled_events_path("2026-05-22")
        == "api/v1/sport/football/scheduled-events/2026-05-22"
    )


def test_lineups_path_unchanged():
    assert sportapi_paths.lineups_path(13980080) == "api/v1/event/13980080/lineups"


def test_event_path():
    assert sportapi_paths.event_path(13980080) == "api/v1/event/13980080"


def test_odds_providers_path():
    assert sportapi_paths.odds_providers_path("IT", "app") == "api/v1/odds/providers/IT/app"


def test_odds_provider_slug_path():
    assert sportapi_paths.odds_provider_slug_path("Sisal-Italy-Affiliate") == "api/v1/odds/sisal-italy-affiliate"


def test_event_odds_path():
    assert sportapi_paths.event_odds_path(13980080, 2325) == "api/v1/event/13980080/odds/2325/all"
