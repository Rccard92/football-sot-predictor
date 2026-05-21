"""Sync dettaglio provider odds SportAPI per slug."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sportapi_odds_provider import DEFAULT_PROVIDER_SLUG, SportApiOddsProvider
from app.services.sportapi.sportapi_client import SportApiClient, SportApiError
from app.services.sportapi.sportapi_odds_response import nested_id_name, unwrap_odds_provider

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SportApiOddsProviderDetailService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    def sync_detail(self, db: Session, slug: str) -> dict[str, Any]:
        slug_norm = slug.strip().lower()
        try:
            raw = self._client.get_odds_provider_detail(slug_norm)
        except SportApiError:
            raise

        op = unwrap_odds_provider(raw)
        if not op:
            raise SportApiError(f"Dettaglio provider vuoto per slug={slug_norm}")

        provider_id, _, provider_name = nested_id_name(op)
        if provider_name is None:
            provider_name = str(op.get("displayName") or slug_norm).strip()

        odds_from_id, odds_from_slug, odds_from_name = nested_id_name(
            op.get("oddsFrom") or op.get("odds_from"),
        )
        live_id, live_slug, live_name = nested_id_name(
            op.get("liveOddsFrom") or op.get("live_odds_from"),
        )

        row = db.scalar(
            select(SportApiOddsProvider).where(SportApiOddsProvider.provider_slug == slug_norm),
        )
        now = _utcnow()
        if row is None:
            row = SportApiOddsProvider(
                provider_slug=slug_norm,
                provider_name=provider_name or slug_norm,
                is_selected=(slug_norm == DEFAULT_PROVIDER_SLUG),
            )
            db.add(row)

        row.provider_name = provider_name or row.provider_name
        row.provider_id = provider_id
        row.odds_from_id = odds_from_id
        row.odds_from_slug = odds_from_slug
        row.odds_from_name = odds_from_name
        row.live_odds_from_id = live_id
        row.live_odds_from_slug = live_slug
        row.live_odds_from_name = live_name
        row.default_bet_slip_link = str(op.get("defaultBetSlipLink") or op.get("default_bet_slip_link") or "").strip() or None
        colors = op.get("colors") or op.get("color")
        if isinstance(colors, dict):
            row.primary_color = str(colors.get("primary") or colors.get("primaryColor") or "").strip() or None
        elif isinstance(colors, str):
            row.primary_color = colors.strip() or None
        row.raw_payload = raw if isinstance(raw, dict) else {"response": raw}
        row.last_synced_at = now
        row.is_active = True
        if slug_norm == DEFAULT_PROVIDER_SLUG:
            row.is_selected = True

        db.commit()
        db.refresh(row)

        return {
            "status": "success",
            "provider": {
                "provider_slug": row.provider_slug,
                "provider_name": row.provider_name,
                "provider_id": row.provider_id,
                "odds_from_id": row.odds_from_id,
                "odds_from_slug": row.odds_from_slug,
                "odds_from_name": row.odds_from_name,
                "live_odds_from_id": row.live_odds_from_id,
                "live_odds_from_slug": row.live_odds_from_slug,
                "live_odds_from_name": row.live_odds_from_name,
                "default_bet_slip_link": row.default_bet_slip_link,
                "primary_color": row.primary_color,
                "working_odds_provider_id": row.working_odds_provider_id,
                "is_selected": bool(row.is_selected),
                "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
            },
            "raw": row.raw_payload,
        }
