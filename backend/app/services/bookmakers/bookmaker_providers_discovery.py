"""Aggregazione provider bookmaker + stato configurazione."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings, sportapi_configured
from app.models.odds_bookmaker import OddsBookmaker, PROVIDER_API_SPORTS
from app.models.sportapi_odds_provider import SportApiOddsProvider
from app.services.bookmakers.bookmaker_constants import (
    PROVIDER_SOURCE_API_FOOTBALL,
    PROVIDER_SOURCE_SPORTAPI,
)

STATUS_AVAILABLE = "available"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_ERROR = "error"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class BookmakerProvidersDiscoveryService:
    def list_sources(self, db: Session) -> dict[str, Any]:
        settings = get_settings()
        sources: list[dict[str, Any]] = []

        af_key = bool(settings.api_football_key.strip())
        af_status = STATUS_AVAILABLE if af_key else STATUS_NOT_CONFIGURED
        af_count = int(
            db.scalar(
                select(func.count()).select_from(OddsBookmaker).where(
                    OddsBookmaker.provider == PROVIDER_API_SPORTS,
                    OddsBookmaker.is_active.is_(True),
                ),
            )
            or 0,
        )
        af_last = db.scalar(
            select(func.max(OddsBookmaker.last_synced_at)).where(
                OddsBookmaker.provider == PROVIDER_API_SPORTS,
            ),
        )
        sources.append(
            {
                "provider_source": PROVIDER_SOURCE_API_FOOTBALL,
                "label": "API-Football (API-Sports)",
                "status": af_status,
                "bookmakers_count": af_count,
                "last_synced_at": _iso(af_last),
                "supports_fixture_odds": False,
                "note": "Lista bookmaker; quote fixture 1X2 non ancora integrate nel client.",
            },
        )

        sa_cfg = sportapi_configured()
        sa_status = STATUS_AVAILABLE if sa_cfg else STATUS_NOT_CONFIGURED
        sa_count = int(
            db.scalar(
                select(func.count()).select_from(SportApiOddsProvider).where(
                    SportApiOddsProvider.is_active.is_(True),
                ),
            )
            or 0,
        )
        sa_last = db.scalar(select(func.max(SportApiOddsProvider.last_synced_at)))
        sources.append(
            {
                "provider_source": PROVIDER_SOURCE_SPORTAPI,
                "label": "SportAPI",
                "status": sa_status,
                "bookmakers_count": sa_count,
                "last_synced_at": _iso(sa_last),
                "supports_fixture_odds": sa_cfg,
                "note": None,
            },
        )

        return {
            "sources": sources,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def list_unified_bookmakers(self, db: Session) -> dict[str, Any]:
        """Elenco bookmaker da entrambe le fonti (per tabella UI)."""
        items: list[dict[str, Any]] = []
        for row in db.scalars(
            select(OddsBookmaker)
            .where(OddsBookmaker.is_active.is_(True))
            .order_by(OddsBookmaker.name),
        ):
            items.append(
                {
                    "provider_source": PROVIDER_SOURCE_API_FOOTBALL,
                    "provider_bookmaker_id": str(row.provider_bookmaker_id),
                    "name": row.name,
                    "is_selected": row.is_selected,
                    "last_synced_at": _iso(row.last_synced_at),
                },
            )
        for row in db.scalars(
            select(SportApiOddsProvider)
            .where(SportApiOddsProvider.is_active.is_(True))
            .order_by(SportApiOddsProvider.provider_name),
        ):
            pid = row.provider_id or row.working_odds_provider_id
            items.append(
                {
                    "provider_source": PROVIDER_SOURCE_SPORTAPI,
                    "provider_bookmaker_id": str(pid or row.provider_slug),
                    "provider_slug": row.provider_slug,
                    "name": row.provider_name,
                    "is_selected": row.is_selected,
                    "last_synced_at": _iso(row.last_synced_at),
                    "working_odds_provider_id": row.working_odds_provider_id,
                },
            )
        return {"bookmakers": items, "total": len(items)}
