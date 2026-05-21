"""Sync lista provider odds SportAPI (IT/app)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.sportapi_odds_provider import DEFAULT_PROVIDER_SLUG, SportApiOddsProvider
from app.services.sportapi.sportapi_client import SportApiClient, SportApiError
from app.services.sportapi.sportapi_odds_response import unwrap_list

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_list_item(item: Any, country: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    slug = str(item.get("slug") or item.get("providerSlug") or "").strip().lower()
    if not slug:
        return None
    name = str(item.get("name") or item.get("providerName") or slug).strip()
    if not name:
        return None
    return {
        "provider_slug": slug,
        "provider_name": name,
        "provider_country": str(item.get("country") or country).strip() or country,
        "raw": item,
    }


class SportApiOddsProvidersSyncService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    def list_payload(self, db: Session) -> dict[str, Any]:
        rows = list(
            db.scalars(
                select(SportApiOddsProvider).order_by(
                    SportApiOddsProvider.is_selected.desc(),
                    SportApiOddsProvider.provider_name.asc(),
                ),
            ).all(),
        )
        last = db.scalar(select(func.max(SportApiOddsProvider.last_synced_at)))
        return {
            "status": "success",
            "total": len(rows),
            "last_synced_at": last.isoformat() if last else None,
            "providers": [self._row_dict(r) for r in rows],
        }

    @staticmethod
    def _row_dict(row: SportApiOddsProvider) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "provider_slug": row.provider_slug,
            "provider_name": row.provider_name,
            "provider_country": row.provider_country,
            "provider_id": row.provider_id,
            "odds_from_id": row.odds_from_id,
            "odds_from_slug": row.odds_from_slug,
            "odds_from_name": row.odds_from_name,
            "live_odds_from_id": row.live_odds_from_id,
            "working_odds_provider_id": row.working_odds_provider_id,
            "is_selected": bool(row.is_selected),
            "is_active": bool(row.is_active),
            "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
        }

    def sync_it_app(self, db: Session, *, country: str = "IT", channel: str = "app") -> dict[str, Any]:
        try:
            raw = self._client.get_odds_providers(country=country, channel=channel)
        except SportApiError:
            raise

        items = unwrap_list(raw)
        now = _utcnow()
        created = updated = skipped = 0

        for item in items:
            norm = _normalize_list_item(item, country)
            if norm is None:
                skipped += 1
                continue
            slug = norm["provider_slug"]
            existing = db.scalar(
                select(SportApiOddsProvider).where(SportApiOddsProvider.provider_slug == slug),
            )
            if existing is None:
                existing = SportApiOddsProvider(
                    provider_slug=slug,
                    provider_name=norm["provider_name"],
                    provider_country=norm["provider_country"],
                    is_selected=(slug == DEFAULT_PROVIDER_SLUG),
                    raw_payload=norm["raw"],
                    last_synced_at=now,
                )
                db.add(existing)
                created += 1
            else:
                existing.provider_name = norm["provider_name"]
                existing.provider_country = norm["provider_country"]
                existing.raw_payload = norm["raw"]
                existing.last_synced_at = now
                existing.is_active = True
                updated += 1

        db.commit()
        return {
            "status": "success",
            "country": country,
            "channel": channel,
            "fetched": len(items),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "total_in_db": int(
                db.scalar(select(func.count()).select_from(SportApiOddsProvider)) or 0,
            ),
        }
