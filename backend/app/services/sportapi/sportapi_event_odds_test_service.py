"""Test quote evento SportAPI con prova candidate provider_id."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sportapi_fixture_odds_snapshot import MARKET_1X2, SportApiFixtureOddsSnapshot
from app.models.sportapi_odds_provider import SportApiOddsProvider
from app.services.sportapi.sportapi_client import SportApiClient, SportApiError
from app.services.sportapi.sportapi_odds_1x2_normalize import extract_1x2_from_event_odds

logger = logging.getLogger(__name__)


def candidate_provider_ids(
    provider_row: SportApiOddsProvider | None,
    *,
    explicit_provider_id: int | None = None,
) -> list[int]:
    """Ordine: working → provider_id → odds_from → live_odds_from → explicit."""
    ordered: list[int | None] = []
    if provider_row is not None:
        ordered.extend(
            [
                provider_row.working_odds_provider_id,
                provider_row.provider_id,
                provider_row.odds_from_id,
                provider_row.live_odds_from_id,
            ],
        )
    ordered.append(explicit_provider_id)
    out: list[int] = []
    for x in ordered:
        if x is None:
            continue
        try:
            pid = int(x)
        except (TypeError, ValueError):
            continue
        if pid > 0 and pid not in out:
            out.append(pid)
    return out


def _enrich_normalized(
    norm: dict[str, Any],
    *,
    provider_id: int | None,
    provider_slug: str,
) -> dict[str, Any]:
    out = dict(norm)
    if provider_id is not None:
        out["provider_id"] = int(provider_id)
    out["provider_slug"] = provider_slug
    return out


def _has_usable_odds(raw: Any) -> bool:
    if raw is None:
        return False
    norm = extract_1x2_from_event_odds(raw)
    if norm.get("market_matched") or norm.get("market_found"):
        return True
    if isinstance(raw, dict) and raw:
        return True
    return bool(isinstance(raw, list) and raw)


class SportApiEventOddsTestService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    def test_event(
        self,
        db: Session,
        *,
        sportapi_event_id: int,
        provider_slug: str,
        provider_id: int | None = None,
        save_snapshot: bool = False,
        fixture_id: int | None = None,
        api_fixture_id: int | None = None,
    ) -> dict[str, Any]:
        slug = provider_slug.strip().lower()
        row = db.scalar(
            select(SportApiOddsProvider).where(SportApiOddsProvider.provider_slug == slug),
        )
        candidates = candidate_provider_ids(row, explicit_provider_id=provider_id)
        if not candidates:
            raise SportApiError(
                f"Nessun provider_id candidato per {slug}. Esegui sync dettaglio o passa provider_id nel body.",
            )

        attempts: list[dict[str, Any]] = []
        working_id: int | None = None
        last_error: str | None = None
        raw_payload: Any = None
        normalized_1x2: dict[str, Any] | None = None

        for pid in candidates:
            try:
                raw = self._client.get_event_odds(int(sportapi_event_id), pid)
                attempts.append({"provider_id": pid, "status": "ok"})
                if _has_usable_odds(raw):
                    working_id = pid
                    raw_payload = raw
                    normalized_1x2 = _enrich_normalized(
                        extract_1x2_from_event_odds(raw),
                        provider_id=pid,
                        provider_slug=slug,
                    )
                    break
                attempts.append({"provider_id": pid, "status": "empty_odds"})
                last_error = "Payload senza mercati utilizzabili"
            except SportApiError as exc:
                last_error = str(exc)
                attempts.append({"provider_id": pid, "status": "error", "message": last_error})

        if working_id is None:
            return {
                "status": "error",
                "message": last_error or "Nessun provider_id ha restituito quote",
                "sportapi_event_id": int(sportapi_event_id),
                "provider_slug": slug,
                "candidate_provider_ids": candidates,
                "attempts": attempts,
            }

        if row is not None and row.working_odds_provider_id != working_id:
            row.working_odds_provider_id = working_id
            db.commit()

        snapshot_id: int | None = None
        if save_snapshot and normalized_1x2:
            snap = SportApiFixtureOddsSnapshot(
                fixture_id=fixture_id,
                api_fixture_id=api_fixture_id,
                sportapi_event_id=int(sportapi_event_id),
                provider_slug=slug,
                provider_id_used=working_id,
                market_key=MARKET_1X2,
                market_name_original=normalized_1x2.get("market_name_original"),
                home_odd=normalized_1x2.get("home_odd"),
                draw_odd=normalized_1x2.get("draw_odd"),
                away_odd=normalized_1x2.get("away_odd"),
                normalized_payload=normalized_1x2,
                raw_payload=raw_payload if isinstance(raw_payload, dict) else {"data": raw_payload},
                fetched_at=datetime.now(timezone.utc),
            )
            db.add(snap)
            db.commit()
            db.refresh(snap)
            snapshot_id = int(snap.id)

        return {
            "status": "success",
            "sportapi_event_id": int(sportapi_event_id),
            "provider_slug": slug,
            "working_provider_id": working_id,
            "candidate_provider_ids": candidates,
            "attempts": attempts,
            "normalized_1x2": normalized_1x2,
            "snapshot_id": snapshot_id,
            "raw_available": raw_payload is not None,
        }
