"""Lettura quote bookmaker Cecchino da DB."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.bookmakers.fixture_bookmaker_odds_repository import list_odds_for_fixture
from app.services.cecchino.cecchino_bookmaker_derive import build_bookmaker_structures
from app.services.cecchino.cecchino_constants import (
    CECCHINO_BOOKMAKER,
    CECCHINO_BOOKMAKERS,
    PROVIDER_API_FOOTBALL,
)


def load_fixture_bookmaker_odds_payload(
    db: Session,
    *,
    competition_id: int,
    fixture_id: int,
) -> dict[str, Any]:
    ids = [str(b["provider_bookmaker_id"]) for b in CECCHINO_BOOKMAKERS]
    rows = list_odds_for_fixture(
        db,
        competition_id=competition_id,
        fixture_id=fixture_id,
        provider_source=PROVIDER_API_FOOTBALL,
    )
    rows = [r for r in rows if str(r.provider_bookmaker_id) in ids]

    bookmakers_list, avg, warnings, status = build_bookmaker_structures(
        rows,
        bookmaker_defs=CECCHINO_BOOKMAKERS,
    )

    return {
        "fixture_id": int(fixture_id),
        "competition_id": int(competition_id),
        "provider_source": PROVIDER_API_FOOTBALL,
        "bookmakers": bookmakers_list,
        "bookmaker_average": avg,
        "status": status,
        "warnings": warnings,
    }


def load_betfair_odds_payload(
    db: Session,
    *,
    competition_id: int,
    fixture_id: int,
) -> dict[str, Any]:
    """Carica quote Betfair-only per Cecchino Today KPI v2."""
    bid = str(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    rows = list_odds_for_fixture(
        db,
        competition_id=competition_id,
        fixture_id=fixture_id,
        provider_source=PROVIDER_API_FOOTBALL,
    )
    rows = [r for r in rows if str(r.provider_bookmaker_id) == bid]

    bookmakers_list, avg, warnings, status = build_bookmaker_structures(
        rows,
        bookmaker_defs=[CECCHINO_BOOKMAKER],
    )

    return {
        "fixture_id": int(fixture_id),
        "competition_id": int(competition_id),
        "provider_source": PROVIDER_API_FOOTBALL,
        "bookmakers": bookmakers_list,
        "bookmaker_average": avg,
        "status": status,
        "warnings": warnings,
    }
