"""Discovery mercati normalizzati in bookmaker_markets."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bookmaker_market import BookmakerMarket
from app.models.sportapi_odds_market_mapping import SportApiOddsMarketMapping
from app.services.bookmakers.bookmaker_constants import (
    MARKET_MATCH_WINNER_1X2,
    PROVIDER_SOURCE_SPORTAPI,
)
from app.services.bookmakers.market_normalize import normalize_market_name


def seed_from_sportapi_mappings(db: Session) -> int:
    """Importa mapping legacy SportAPI nel catalogo bookmaker_markets."""
    upserted = 0
    for m in db.scalars(select(SportApiOddsMarketMapping)):
        norm = normalize_market_name(m.raw_market_name, raw_market_key=m.normalized_market_key)
        market_id = (m.raw_market_id or m.raw_market_name or "").strip()[:128]
        existing = db.scalar(
            select(BookmakerMarket).where(
                BookmakerMarket.provider_source == PROVIDER_SOURCE_SPORTAPI,
                BookmakerMarket.provider_market_id == market_id,
            ),
        )
        if existing is None:
            db.add(
                BookmakerMarket(
                    provider_source=PROVIDER_SOURCE_SPORTAPI,
                    provider_market_id=market_id,
                    market_key=m.normalized_market_key or "",
                    market_name=m.raw_market_name,
                    normalized_market=norm,
                    raw_payload_json=m.sample_raw_market,
                    is_active=True,
                ),
            )
            upserted += 1
        else:
            existing.normalized_market = norm
            existing.market_name = m.raw_market_name
            existing.market_key = m.normalized_market_key or existing.market_key
    db.flush()
    return upserted


def upsert_market_from_discovery(
    db: Session,
    *,
    provider_source: str,
    market_name: str,
    provider_market_id: str = "",
    market_key: str = "",
    raw_payload: dict[str, Any] | None = None,
) -> BookmakerMarket:
    norm = normalize_market_name(market_name, raw_market_key=market_key or None)
    pid = (provider_market_id or market_name).strip()[:128]
    row = db.scalar(
        select(BookmakerMarket).where(
            BookmakerMarket.provider_source == provider_source,
            BookmakerMarket.provider_market_id == pid,
        ),
    )
    if row is None:
        row = BookmakerMarket(
            provider_source=provider_source,
            provider_market_id=pid,
            market_key=market_key or "",
            market_name=market_name,
            normalized_market=norm,
            raw_payload_json=raw_payload,
            is_active=True,
        )
        db.add(row)
    else:
        row.market_name = market_name
        row.market_key = market_key or row.market_key
        row.normalized_market = norm
        if raw_payload:
            row.raw_payload_json = raw_payload
    db.flush()
    return row


class BookmakerMarketsDiscoveryService:
    def list_markets(
        self,
        db: Session,
        *,
        provider_source: str | None = None,
    ) -> dict[str, Any]:
        seed_from_sportapi_mappings(db)
        q = select(BookmakerMarket).where(BookmakerMarket.is_active.is_(True))
        if provider_source:
            q = q.where(BookmakerMarket.provider_source == provider_source)
        q = q.order_by(
            BookmakerMarket.provider_source,
            BookmakerMarket.normalized_market,
            BookmakerMarket.market_name,
        )
        markets = [
            {
                "id": int(m.id),
                "provider_source": m.provider_source,
                "provider_market_id": m.provider_market_id,
                "market_key": m.market_key,
                "market_name": m.market_name,
                "normalized_market": m.normalized_market,
                "is_unknown": m.normalized_market == "UNKNOWN",
            }
            for m in db.scalars(q)
        ]
        if not markets:
            markets.append(
                {
                    "id": None,
                    "provider_source": PROVIDER_SOURCE_SPORTAPI,
                    "provider_market_id": "match_1x2",
                    "market_key": "match_1x2",
                    "market_name": "1X2 (seed)",
                    "normalized_market": MARKET_MATCH_WINNER_1X2,
                    "is_unknown": False,
                },
            )
        return {"markets": markets, "total": len(markets)}
