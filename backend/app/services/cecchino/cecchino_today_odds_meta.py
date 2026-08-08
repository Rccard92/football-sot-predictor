"""Metadata timestamp quote Book in odds_snapshot_json."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.cecchino.cecchino_constants import CECCHINO_BOOK_POLICY_VERSION

ODDS_SOURCE_CACHED = "cached"
ODDS_SOURCE_API_LIVE = "api_live_refresh"
ODDS_SOURCE_BOOK = "book"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_odds_meta(
    *,
    odds_source: str,
    is_cached: bool,
    odds_fetched_at: str | None = None,
    odds_cached_at: str | None = None,
    last_betfair_refresh_at: str | None = None,
    last_book_refresh_at: str | None = None,
    book_policy_version: str | None = None,
) -> dict[str, Any]:
    now = _utcnow_iso()
    refresh_at = last_book_refresh_at or last_betfair_refresh_at
    return {
        "odds_source": odds_source,
        "is_cached": bool(is_cached),
        "odds_fetched_at": odds_fetched_at or now,
        "odds_cached_at": odds_cached_at,
        "last_book_refresh_at": refresh_at,
        "last_betfair_refresh_at": refresh_at,  # alias legacy
        "odds_updated_at": now,
        "book_policy_version": book_policy_version or CECCHINO_BOOK_POLICY_VERSION,
    }


def read_odds_meta(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot or not isinstance(snapshot, dict):
        return {}
    meta = snapshot.get("odds_meta")
    return dict(meta) if isinstance(meta, dict) else {}


def merge_odds_meta_into_snapshot(
    snapshot: dict[str, Any] | None,
    meta: dict[str, Any],
) -> dict[str, Any]:
    out = dict(snapshot or {})
    out["odds_meta"] = dict(meta)
    if meta.get("book_policy_version"):
        out["book_policy_version"] = meta["book_policy_version"]
    return out


def attach_scan_odds_meta(snapshot: dict[str, Any], *, from_cache: bool = False) -> dict[str, Any]:
    """Imposta odds_meta al primo salvataggio durante scan."""
    now = _utcnow_iso()
    existing = read_odds_meta(snapshot)
    cached_at = existing.get("odds_cached_at") or now
    source = ODDS_SOURCE_CACHED if from_cache else ODDS_SOURCE_BOOK
    meta = build_odds_meta(
        odds_source=source,
        is_cached=True,
        odds_fetched_at=existing.get("odds_fetched_at") or now,
        odds_cached_at=cached_at,
        last_book_refresh_at=existing.get("last_book_refresh_at")
        or existing.get("last_betfair_refresh_at"),
        book_policy_version=CECCHINO_BOOK_POLICY_VERSION,
    )
    out = merge_odds_meta_into_snapshot(snapshot, meta)
    out["book_policy_version"] = CECCHINO_BOOK_POLICY_VERSION
    return out


def attach_refresh_odds_meta(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Aggiorna odds_meta dopo refresh live Book."""
    now = _utcnow_iso()
    existing = read_odds_meta(snapshot)
    meta = build_odds_meta(
        odds_source=ODDS_SOURCE_API_LIVE,
        is_cached=False,
        odds_fetched_at=now,
        odds_cached_at=existing.get("odds_cached_at"),
        last_book_refresh_at=now,
        book_policy_version=CECCHINO_BOOK_POLICY_VERSION,
    )
    out = merge_odds_meta_into_snapshot(snapshot, meta)
    out["book_policy_version"] = CECCHINO_BOOK_POLICY_VERSION
    return out


def bookmaker_meta_block(
    meta: dict[str, Any] | None,
    *,
    provider_bookmaker_id: int,
    name: str,
    provider_source: str = "api_football",
) -> dict[str, Any]:
    m = meta or {}
    return {
        "provider_source": provider_source,
        "provider_bookmaker_id": provider_bookmaker_id,
        "name": name,
        "odds_source": m.get("odds_source"),
        "odds_fetched_at": m.get("odds_fetched_at"),
        "odds_cached_at": m.get("odds_cached_at"),
        "odds_updated_at": m.get("odds_updated_at"),
        "last_book_refresh_at": m.get("last_book_refresh_at") or m.get("last_betfair_refresh_at"),
        "last_betfair_refresh_at": m.get("last_betfair_refresh_at") or m.get("last_book_refresh_at"),
        "is_cached": m.get("is_cached"),
        "book_policy_version": m.get("book_policy_version") or CECCHINO_BOOK_POLICY_VERSION,
        "policy_label": "Betfair primario · Bet365 fallback",
    }


def extract_1x2_from_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Estrae quote 1X2 canoniche + meta per before/after."""
    meta = read_odds_meta(snapshot)
    books = (snapshot or {}).get("bookmakers") or {}
    bf = books.get("Canonical") or books.get("Betfair") or {}
    return {
        "HOME": bf.get("HOME"),
        "DRAW": bf.get("DRAW"),
        "AWAY": bf.get("AWAY"),
        "odds_fetched_at": meta.get("odds_fetched_at"),
        "odds_source": meta.get("odds_source"),
        "is_cached": meta.get("is_cached"),
        "selection_sources": (snapshot or {}).get("selection_sources"),
        "book_policy_version": (snapshot or {}).get("book_policy_version")
        or meta.get("book_policy_version"),
    }
