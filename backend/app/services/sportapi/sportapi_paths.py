"""Path template SportAPI7 RapidAPI — unico punto da aggiornare se l'API cambia."""

from __future__ import annotations


def scheduled_events_path(date_yyyy_mm_dd: str) -> str:
    """Eventi programmati per data (YYYY-MM-DD)."""
    return f"api/v1/event/by-date/{date_yyyy_mm_dd}"


def event_path(event_id: int) -> str:
    return f"api/v1/event/{int(event_id)}"


def lineups_path(event_id: int) -> str:
    return f"api/v1/event/{int(event_id)}/lineups"
