"""Discovery completa mercati odds SportAPI per evento/provider."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sportapi_odds_provider import SportApiOddsProvider
from app.services.sportapi.sportapi_client import SportApiClient, SportApiError
from app.services.sportapi.sportapi_event_odds_test_service import candidate_provider_ids
from app.services.sportapi.sportapi_odds_markets_normalize import normalize_all_markets_from_event_odds
from app.services.sportapi.sportapi_odds_sot_candidates import find_sot_candidate_markets

logger = logging.getLogger(__name__)


class SportApiMarketsDiscoveryService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    def discover(
        self,
        db: Session,
        *,
        sportapi_event_id: int,
        provider_slug: str,
        provider_id: int | None = None,
    ) -> dict[str, Any]:
        slug = provider_slug.strip().lower()
        row = db.scalar(
            select(SportApiOddsProvider).where(SportApiOddsProvider.provider_slug == slug),
        )
        candidates = candidate_provider_ids(row, explicit_provider_id=provider_id)
        if not candidates:
            raise SportApiError(
                f"Nessun provider_id candidato per {slug}. Esegui sync dettaglio o passa provider_id.",
            )

        attempts: list[dict[str, Any]] = []
        working_id: int | None = None
        raw_payload: Any = None
        normalized: list[dict[str, Any]] = []
        last_error: str | None = None

        for pid in candidates:
            try:
                raw = self._client.get_event_odds(int(sportapi_event_id), pid)
                markets = normalize_all_markets_from_event_odds(raw)
                attempts.append({"provider_id": pid, "status": "ok", "markets_count": len(markets)})
                if markets or raw:
                    working_id = pid
                    raw_payload = raw
                    normalized = markets
                    break
                attempts.append({"provider_id": pid, "status": "empty"})
                last_error = "Payload senza mercati"
            except SportApiError as exc:
                last_error = str(exc)
                attempts.append({"provider_id": pid, "status": "error", "message": last_error})

        if working_id is None:
            return {
                "status": "error",
                "message": last_error or "Nessun provider_id ha restituito mercati",
                "sportapi_event_id": int(sportapi_event_id),
                "provider_slug": slug,
                "candidate_provider_ids": candidates,
                "attempts": attempts,
            }

        if row is not None and row.working_odds_provider_id != working_id:
            row.working_odds_provider_id = working_id
            db.commit()

        sot_candidates = find_sot_candidate_markets(normalized)

        return {
            "status": "success",
            "sportapi_event_id": int(sportapi_event_id),
            "provider_slug": slug,
            "working_provider_id": working_id,
            "candidate_provider_ids": candidates,
            "attempts": attempts,
            "markets_count": len(normalized),
            "normalized_markets": normalized,
            "sot_candidate_markets": sot_candidates,
            "sot_candidates_count": len(sot_candidates),
            "raw_payload": raw_payload,
        }
