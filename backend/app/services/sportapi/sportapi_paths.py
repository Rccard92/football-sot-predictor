"""Path template SportAPI7 RapidAPI — unico punto da aggiornare se l'API cambia."""

from __future__ import annotations


def scheduled_events_path(date_yyyy_mm_dd: str) -> str:
    """Eventi calcio programmati per data (YYYY-MM-DD).

    RapidAPI: GET /api/v1/sport/football/scheduled-events/{date}
    """
    return f"api/v1/sport/football/scheduled-events/{date_yyyy_mm_dd}"


def event_path(event_id: int) -> str:
    return f"api/v1/event/{int(event_id)}"


def lineups_path(event_id: int) -> str:
    return f"api/v1/event/{int(event_id)}/lineups"
