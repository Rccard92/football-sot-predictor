"""CRUD mapping mercati odds SportAPI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sportapi_odds_market_mapping import (
    CONFIDENCE_MANUAL,
    SportApiOddsMarketMapping,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SportApiOddsMarketMappingService:
    def list_active(self, db: Session, provider_slug: str | None = None) -> list[SportApiOddsMarketMapping]:
        q = select(SportApiOddsMarketMapping).where(SportApiOddsMarketMapping.is_active.is_(True))
        if provider_slug:
            q = q.where(SportApiOddsMarketMapping.provider_slug == provider_slug.strip().lower())
        return list(
            db.scalars(q.order_by(SportApiOddsMarketMapping.raw_market_name.asc())).all(),
        )

    def list_payload(self, db: Session, provider_slug: str | None = None) -> dict[str, Any]:
        rows = self.list_active(db, provider_slug)
        return {
            "status": "success",
            "count": len(rows),
            "mappings": [self._row_dict(r) for r in rows],
        }

    @staticmethod
    def _row_dict(r: SportApiOddsMarketMapping) -> dict[str, Any]:
        return {
            "id": int(r.id),
            "provider_slug": r.provider_slug,
            "provider_id_used": r.provider_id_used,
            "raw_market_name": r.raw_market_name,
            "raw_market_id": r.raw_market_id,
            "normalized_market_key": r.normalized_market_key,
            "confidence": r.confidence,
            "is_active": bool(r.is_active),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }

    def upsert_mapping(
        self,
        db: Session,
        *,
        provider_slug: str,
        raw_market_name: str,
        normalized_market_key: str,
        provider_id_used: int | None = None,
        raw_market_id: str | None = None,
        confidence: str = CONFIDENCE_MANUAL,
        sample_raw_market: dict[str, Any] | None = None,
    ) -> SportApiOddsMarketMapping:
        slug = provider_slug.strip().lower()
        name = raw_market_name.strip()
        key = normalized_market_key.strip()
        existing = db.scalar(
            select(SportApiOddsMarketMapping).where(
                SportApiOddsMarketMapping.provider_slug == slug,
                SportApiOddsMarketMapping.raw_market_name == name,
                SportApiOddsMarketMapping.normalized_market_key == key,
            ),
        )
        if existing:
            existing.is_active = True
            existing.confidence = confidence
            existing.provider_id_used = provider_id_used
            existing.raw_market_id = raw_market_id
            if sample_raw_market is not None:
                existing.sample_raw_market = sample_raw_market
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing

        row = SportApiOddsMarketMapping(
            provider_slug=slug,
            provider_id_used=provider_id_used,
            raw_market_name=name,
            raw_market_id=raw_market_id,
            normalized_market_key=key,
            confidence=confidence,
            is_active=True,
            sample_raw_market=sample_raw_market,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def deactivate(self, db: Session, mapping_id: int) -> bool:
        row = db.get(SportApiOddsMarketMapping, int(mapping_id))
        if row is None:
            return False
        row.is_active = False
        db.add(row)
        db.commit()
        return True

    def find_match_total_mapping(
        self,
        db: Session,
        provider_slug: str,
    ) -> list[SportApiOddsMarketMapping]:
        from app.models.sportapi_odds_market_mapping import MARKET_KEY_MATCH_TOTAL_SOT

        return list(
            db.scalars(
                select(SportApiOddsMarketMapping).where(
                    SportApiOddsMarketMapping.provider_slug == provider_slug.strip().lower(),
                    SportApiOddsMarketMapping.normalized_market_key == MARKET_KEY_MATCH_TOTAL_SOT,
                    SportApiOddsMarketMapping.is_active.is_(True),
                ),
            ).all(),
        )
