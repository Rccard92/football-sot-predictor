"""Ingestion operativa indisponibili via Availability Provider Layer."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.api_football_client import ApiFootballClient
from app.services.availability.providers.availability_provider_orchestrator import (
    DEFAULT_DAYS_AHEAD,
    run_availability_upcoming_orchestrator,
)

__all__ = ["DEFAULT_DAYS_AHEAD", "ingest_serie_a_availability_upcoming"]


def ingest_serie_a_availability_upcoming(
    db: Session,
    season_year: int,
    *,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    force: bool = False,
    fixture_id: int | None = None,
    client: ApiFootballClient | None = None,
    use_sidelined: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    return run_availability_upcoming_orchestrator(
        db,
        int(season_year),
        days_ahead=int(days_ahead),
        force=force,
        fixture_id=fixture_id,
        client=client,
        use_sidelined=use_sidelined,
        dry_run=dry_run,
    )
