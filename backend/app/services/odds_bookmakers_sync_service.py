"""Sync bookmakers da API-Football GET /odds/bookmakers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.odds_bookmaker import PROVIDER_API_SPORTS, OddsBookmaker
from app.services.api_football_client import ApiFootballClient, ApiFootballError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_bookmaker_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    raw_id = item.get("id")
    if raw_id is None:
        return None
    try:
        bid = int(raw_id)
    except (TypeError, ValueError):
        return None
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    return {"id": bid, "name": name, "raw": item}


class OddsBookmakersSyncService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def list_bookmakers(self, db: Session) -> list[OddsBookmaker]:
        return list(
            db.scalars(select(OddsBookmaker).order_by(OddsBookmaker.name.asc(), OddsBookmaker.id.asc())).all(),
        )

    def list_payload(self, db: Session) -> dict[str, Any]:
        rows = self.list_bookmakers(db)
        last_synced = db.scalar(select(func.max(OddsBookmaker.last_synced_at)))
        return {
            "status": "success",
            "total": len(rows),
            "last_synced_at": last_synced.isoformat() if last_synced else None,
            "bookmakers": [self._row_to_dict(r) for r in rows],
        }

    def _row_to_dict(self, row: OddsBookmaker) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "provider": row.provider,
            "provider_bookmaker_id": int(row.provider_bookmaker_id),
            "name": row.name,
            "is_selected": bool(row.is_selected),
            "is_active": bool(row.is_active),
            "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
        }

    def sync_from_api(self, db: Session) -> dict[str, Any]:
        errors: list[str] = []
        try:
            raw_items = self._client.get_odds_bookmakers()
        except ApiFootballError as exc:
            logger.exception("odds bookmakers API error")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("odds bookmakers unexpected error")
            raise ApiFootballError(str(exc)) from exc

        if not raw_items:
            raise ApiFootballError("Nessun bookmaker nella risposta API")

        now = _utcnow()
        created = 0
        updated = 0
        skipped = 0

        for item in raw_items:
            norm = _normalize_bookmaker_item(item)
            if norm is None:
                skipped += 1
                logger.warning("bookmaker item skipped: %s", item)
                continue

            bid = int(norm["id"])
            existing = db.scalar(
                select(OddsBookmaker).where(
                    OddsBookmaker.provider == PROVIDER_API_SPORTS,
                    OddsBookmaker.provider_bookmaker_id == bid,
                ),
            )
            if existing is not None:
                existing.name = norm["name"]
                existing.raw_payload = norm["raw"]
                existing.last_synced_at = now
                db.add(existing)
                updated += 1
            else:
                db.add(
                    OddsBookmaker(
                        provider=PROVIDER_API_SPORTS,
                        provider_bookmaker_id=bid,
                        name=norm["name"],
                        is_selected=False,
                        is_active=True,
                        raw_payload=norm["raw"],
                        last_synced_at=now,
                    ),
                )
                created += 1

        db.commit()
        total_saved = db.scalar(
            select(func.count()).select_from(OddsBookmaker).where(OddsBookmaker.provider == PROVIDER_API_SPORTS),
        )
        return {
            "status": "success",
            "fetched_count": len(raw_items),
            "created_count": created,
            "updated_count": updated,
            "skipped_count": skipped,
            "total_saved": int(total_saved or 0),
            "last_synced_at": now.isoformat(),
            "errors": errors,
        }
