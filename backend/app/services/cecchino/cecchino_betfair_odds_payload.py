"""Costruzione payload quote Book (wrapper legacy Betfair → canonical Book)."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_canonical_book_payload import (
    build_canonical_book_payload_from_raw,
    build_canonical_book_payload_from_snapshot,
    build_single_bookmaker_payload,
)
from app.services.cecchino.cecchino_constants import CECCHINO_PRIMARY_BOOKMAKER

_BETFAIR_ID = int(CECCHINO_PRIMARY_BOOKMAKER["provider_bookmaker_id"])


def build_betfair_payload_from_raw(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]] | None,
    *,
    source: str = "betfair",
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> dict[str, Any]:
    """
    Legacy wrapper: costruisce payload Book canonico (Betfair primary → Bet365 fallback).
    source: betfair | cached_betfair_odds | book | cached_book_odds | api_live_refresh
    """
    return build_canonical_book_payload_from_raw(
        odds_by_bookmaker,
        source=source,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )


def build_betfair_payload_from_snapshot(
    odds_snapshot: dict[str, Any] | None,
    *,
    source: str = "cached_betfair_odds",
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> dict[str, Any]:
    """Legacy wrapper offline da odds_snapshot_json."""
    return build_canonical_book_payload_from_snapshot(
        odds_snapshot,
        source=source,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )


def build_betfair_only_payload_from_raw(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]] | None,
    *,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> dict[str, Any]:
    """Solo Betfair (debug / export). Non applica fallback Bet365."""
    raw = (odds_by_bookmaker or {}).get(_BETFAIR_ID) or []
    bm = build_single_bookmaker_payload(
        raw,
        CECCHINO_PRIMARY_BOOKMAKER,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )
    return {
        "provider_source": "api_football",
        "bookmakers": [bm],
        "status": bm.get("status"),
        "warnings": list(bm.get("warnings") or []),
        "odds_source": "betfair",
        "provenance_by_selection": bm.get("provenance_by_selection") or {},
    }
