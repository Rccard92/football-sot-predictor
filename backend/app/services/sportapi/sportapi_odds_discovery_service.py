"""Discovery quote SportAPI per singolo evento/provider."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import sportapi_configured
from app.models import Fixture
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.models.odds_bookmaker import PROVIDER_API_SPORTS, OddsBookmaker
from app.models.odds_discovery_snapshot import PROVIDER_SPORTAPI, OddsDiscoverySnapshot
from app.services.sportapi.sportapi_client import SportApiClient, SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_odds_normalize import normalize_sportapi_odds_payload

logger = logging.getLogger(__name__)

COMPARISON_NOTE = (
    "API-Sports espone una lista bookmaker globale; SportAPI viene analizzata per singolo evento/provider."
)


class MappingNotFoundError(Exception):
    """Fixture senza mapping SportAPI."""


class SportApiOddsDiscoveryService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    @staticmethod
    def _api_sports_bookmakers_count(db: Session) -> int:
        return int(
            db.scalar(
                select(func.count()).select_from(OddsBookmaker).where(
                    OddsBookmaker.provider == PROVIDER_API_SPORTS,
                ),
            )
            or 0,
        )

    def resolve_event(
        self,
        db: Session,
        *,
        fixture_id: int | None,
        api_fixture_id: int | None,
        sportapi_event_id: int | None,
    ) -> tuple[int, int | None, int | None]:
        """
        Ritorna (sportapi_event_id, internal_fixture_id, api_fixture_id).
        """
        if sportapi_event_id is not None:
            fid: int | None = int(fixture_id) if fixture_id is not None else None
            afx: int | None = int(api_fixture_id) if api_fixture_id is not None else None
            if fid is None and (fixture_id is not None or api_fixture_id is not None):
                fx = None
                if fixture_id is not None:
                    fx = db.get(Fixture, int(fixture_id))
                elif api_fixture_id is not None:
                    fx = db.scalar(select(Fixture).where(Fixture.api_fixture_id == int(api_fixture_id)))
                if fx:
                    fid = int(fx.id)
                    afx = int(fx.api_fixture_id)
            return int(sportapi_event_id), fid, afx

        fx: Fixture | None = None
        if fixture_id is not None:
            fx = db.get(Fixture, int(fixture_id))
        elif api_fixture_id is not None:
            fx = db.scalar(select(Fixture).where(Fixture.api_fixture_id == int(api_fixture_id)))

        if fx is None:
            raise ValueError("Fixture non trovata per fixture_id o api_fixture_id indicato.")

        mapping = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == int(fx.id),
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        if mapping is None:
            raise MappingNotFoundError("Mapping SportAPI non disponibile per questa fixture.")

        return int(mapping.provider_event_id), int(fx.id), int(fx.api_fixture_id)

    def discover(
        self,
        db: Session,
        *,
        fixture_id: int | None = None,
        api_fixture_id: int | None = None,
        sportapi_event_id: int | None = None,
        provider_id: int = 1,
        save_snapshot: bool = True,
    ) -> dict[str, Any]:
        if not sportapi_configured():
            raise SportApiDisabledError(
                "SportAPI disabilitata: imposta SPORTAPI_ENABLED=true e SPORTAPI_RAPIDAPI_KEY",
            )

        try:
            event_id, resolved_fid, resolved_afx = self.resolve_event(
                db,
                fixture_id=fixture_id,
                api_fixture_id=api_fixture_id,
                sportapi_event_id=sportapi_event_id,
            )
        except MappingNotFoundError as exc:
            return {
                "status": "error",
                "message": str(exc),
            }
        except ValueError as exc:
            return {
                "status": "error",
                "message": str(exc),
            }

        pid = int(provider_id)
        try:
            raw = self._client.get_event_odds(event_id, pid)
        except SportApiDisabledError:
            raise
        except SportApiError as exc:
            logger.warning("sportapi odds discovery failed event=%s: %s", event_id, exc)
            return {
                "status": "error",
                "message": str(exc),
                "sportapi_event_id": event_id,
                "provider_id": pid,
            }

        if raw is None or (isinstance(raw, (list, dict)) and len(raw) == 0):
            normalized: list[dict[str, Any]] = []
            bk_count = None
            message = "Nessuna quota restituita da SportAPI per questo evento/provider."
        else:
            normalized, bk_count = normalize_sportapi_odds_payload(raw, provider_id=pid)
            message = None
            if not normalized:
                message = "Payload SportAPI ricevuto ma nessun mercato normalizzato; consulta il raw payload."

        api_total = self._api_sports_bookmakers_count(db)
        snapshot_id: int | None = None

        if save_snapshot:
            snap = OddsDiscoverySnapshot(
                provider=PROVIDER_SPORTAPI,
                fixture_id=resolved_fid,
                api_fixture_id=resolved_afx,
                sportapi_event_id=int(event_id),
                sportapi_provider_id=pid,
                markets_count=len(normalized),
                bookmakers_count=bk_count,
                raw_payload=raw if isinstance(raw, dict) else {"data": raw},
                normalized_payload=normalized,
            )
            db.add(snap)
            db.commit()
            db.refresh(snap)
            snapshot_id = int(snap.id)

        out: dict[str, Any] = {
            "status": "success",
            "provider": PROVIDER_SPORTAPI,
            "fixture_id": resolved_fid,
            "api_fixture_id": resolved_afx,
            "sportapi_event_id": int(event_id),
            "provider_id": pid,
            "markets_count": len(normalized),
            "bookmakers_count": bk_count,
            "raw_payload": raw if isinstance(raw, (dict, list)) else {"data": raw},
            "normalized_markets": normalized,
            "snapshot_id": snapshot_id,
            "comparison": {
                "api_sports_bookmakers_total": api_total,
                "sportapi_markets_on_event": len(normalized),
                "sportapi_bookmakers_deduced": bk_count,
                "note": COMPARISON_NOTE,
            },
        }
        if message:
            out["message"] = message
        return out
