"""Scansione provider IT SportAPI alla ricerca di mercati SOT su un evento."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.odds_discovery_snapshot import PROVIDER_SPORTAPI, OddsDiscoverySnapshot
from app.models.sportapi_odds_provider import SportApiOddsProvider
from app.services.sportapi.sportapi_client import SportApiClient, SportApiError
from app.services.sportapi.sportapi_event_odds_test_service import candidate_provider_ids
from app.services.sportapi.sportapi_odds_markets_normalize import normalize_all_markets_from_event_odds
from app.services.sportapi.sportapi_odds_provider_detail_service import SportApiOddsProviderDetailService
from app.services.sportapi.sportapi_odds_providers_sync_service import SportApiOddsProvidersSyncService
from app.services.sportapi.sportapi_odds_sot_candidates import find_sot_candidate_markets

logger = logging.getLogger(__name__)

SLEEP_BETWEEN_PROVIDERS_S = 0.4
RAW_PAYLOAD_MAX_BYTES = 50_000

NO_PROVIDERS_IN_DB_MESSAGE = (
    "Nessun provider SportAPI salvato. Esegui prima Aggiorna provider Italia."
)
NO_PROVIDERS_AFTER_FILTER_MESSAGE = (
    "Nessun provider controllato per il paese selezionato. "
    "Controlla di aver sincronizzato i provider italiani."
)
NO_SOT_MESSAGE = (
    "Nessun mercato SOT trovato nei provider SportAPI controllati per questo evento. "
    "Il mercato può essere disponibile sul sito del bookmaker ma non esposto dal feed SportAPI."
)


def _truncate_raw(raw: Any) -> Any:
    try:
        encoded = json.dumps(raw, default=str)
        if len(encoded) <= RAW_PAYLOAD_MAX_BYTES:
            return raw
        return {"truncated": True, "preview": encoded[:RAW_PAYLOAD_MAX_BYTES]}
    except (TypeError, ValueError):
        return {"truncated": True, "preview": str(raw)[:RAW_PAYLOAD_MAX_BYTES]}


def _country_match_clause(country_norm: str):
    """IT include anche provider con country NULL (es. sync solo dettaglio Sisal)."""
    upper_country = func.upper(SportApiOddsProvider.provider_country)
    return or_(
        upper_country == country_norm,
        SportApiOddsProvider.provider_country.is_(None),
    )


def _query_active_providers(
    db: Session,
    *,
    country_norm: str | None,
    provider_slug: str | None,
    apply_country_filter: bool,
) -> list[SportApiOddsProvider]:
    q = select(SportApiOddsProvider).where(SportApiOddsProvider.is_active.is_(True))
    if apply_country_filter and country_norm:
        q = q.where(_country_match_clause(country_norm))
    if provider_slug:
        q = q.where(SportApiOddsProvider.provider_slug == provider_slug.strip().lower())
    return list(db.scalars(q.order_by(SportApiOddsProvider.provider_name.asc())).all())


class SportApiScanSotProvidersService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()
        self._detail_svc = SportApiOddsProviderDetailService(client=self._client)

    def scan(
        self,
        db: Session,
        *,
        sportapi_event_id: int,
        country: str = "IT",
        max_providers: int | None = None,
        provider_slug: str | None = None,
        save_snapshot: bool = False,
        auto_sync_if_empty: bool = False,
        channel: str = "app",
    ) -> dict[str, Any]:
        country_norm = (country or "IT").strip().upper()
        channel_norm = (channel or "app").strip().lower()

        providers_in_db = len(
            list(db.scalars(select(SportApiOddsProvider).where(SportApiOddsProvider.is_active.is_(True))).all()),
        )

        if providers_in_db == 0 and auto_sync_if_empty:
            try:
                SportApiOddsProvidersSyncService(client=self._client).sync_it_app(
                    db,
                    country=country_norm,
                    channel=channel_norm,
                )
                providers_in_db = len(
                    list(
                        db.scalars(
                            select(SportApiOddsProvider).where(SportApiOddsProvider.is_active.is_(True)),
                        ).all(),
                    ),
                )
            except SportApiError as exc:
                return self._empty_response(
                    sportapi_event_id,
                    country_norm,
                    providers_in_db=0,
                    providers_matching_country=0,
                    scan_status="no_providers_in_db",
                    message=f"{NO_PROVIDERS_IN_DB_MESSAGE} Sync automatico fallito: {exc}",
                )

        if providers_in_db == 0:
            return self._empty_response(
                sportapi_event_id,
                country_norm,
                providers_in_db=0,
                providers_matching_country=0,
                scan_status="no_providers_in_db",
                message=NO_PROVIDERS_IN_DB_MESSAGE,
            )

        providers = _query_active_providers(
            db,
            country_norm=country_norm,
            provider_slug=provider_slug,
            apply_country_filter=True,
        )
        providers_matching_country = len(providers)

        if not providers:
            return self._empty_response(
                sportapi_event_id,
                country_norm,
                providers_in_db=providers_in_db,
                providers_matching_country=0,
                scan_status="no_providers_after_filter",
                message=NO_PROVIDERS_AFTER_FILTER_MESSAGE,
            )

        if max_providers is not None and max_providers > 0:
            providers = providers[: int(max_providers)]

        rows: list[dict[str, Any]] = []
        errors_count = 0
        with_odds = 0
        with_sot = 0

        for idx, prov in enumerate(providers):
            if idx > 0:
                time.sleep(SLEEP_BETWEEN_PROVIDERS_S)
            row = self._scan_one_provider(db, prov, int(sportapi_event_id), save_snapshot=save_snapshot)
            rows.append(row)
            if row.get("status") == "error":
                errors_count += 1
            elif row.get("status") == "ok":
                with_odds += 1
                if row.get("has_sot_market"):
                    with_sot += 1

        message = None
        if with_sot == 0 and with_odds > 0:
            message = NO_SOT_MESSAGE
        elif with_sot == 0 and with_odds == 0 and providers:
            message = "Nessun provider ha restituito quote per questo evento."

        return {
            "status": "success",
            "scan_status": "ok",
            "sportapi_event_id": int(sportapi_event_id),
            "country": country_norm,
            "providers_in_db": providers_in_db,
            "providers_matching_country": providers_matching_country,
            "providers_scanned": len(providers),
            "providers_with_odds": with_odds,
            "providers_with_sot": with_sot,
            "providers_errors": errors_count,
            "rows": rows,
            "message": message,
        }

    @staticmethod
    def _empty_response(
        sportapi_event_id: int,
        country_norm: str,
        *,
        providers_in_db: int,
        providers_matching_country: int,
        scan_status: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "status": "success",
            "scan_status": scan_status,
            "sportapi_event_id": int(sportapi_event_id),
            "country": country_norm,
            "providers_in_db": providers_in_db,
            "providers_matching_country": providers_matching_country,
            "providers_scanned": 0,
            "providers_with_odds": 0,
            "providers_with_sot": 0,
            "providers_errors": 0,
            "rows": [],
            "message": message,
        }

    def _scan_one_provider(
        self,
        db: Session,
        prov: SportApiOddsProvider,
        event_id: int,
        *,
        save_snapshot: bool,
    ) -> dict[str, Any]:
        base = {
            "provider_name": prov.provider_name,
            "provider_slug": prov.provider_slug,
            "working_provider_id": None,
            "markets_count": 0,
            "has_sot_market": False,
            "sot_candidate_markets": [],
            "status": "no_odds",
            "error": None,
            "raw_payload": None,
        }

        if not prov.odds_from_id and not prov.provider_id:
            try:
                self._detail_svc.sync_detail(db, prov.provider_slug)
                db.refresh(prov)
            except SportApiError as exc:
                base["status"] = "error"
                base["error"] = f"sync detail: {exc}"
                return base

        candidates = candidate_provider_ids(prov)
        if not candidates:
            base["status"] = "error"
            base["error"] = "Nessun provider_id candidato"
            return base

        raw_payload: Any = None
        working_id: int | None = None
        last_err: str | None = None
        for pid in candidates:
            try:
                raw_payload = self._client.get_event_odds(event_id, pid)
                markets = normalize_all_markets_from_event_odds(raw_payload)
                if markets or raw_payload:
                    working_id = pid
                    break
                last_err = "Payload senza mercati"
            except SportApiError as exc:
                last_err = str(exc)
                continue

        if working_id is None or raw_payload is None:
            base["status"] = "error" if last_err else "no_odds"
            base["error"] = last_err
            return base

        markets = normalize_all_markets_from_event_odds(raw_payload)
        sot_candidates = find_sot_candidate_markets(markets)
        has_sot = len(sot_candidates) > 0

        if prov.working_odds_provider_id != working_id:
            prov.working_odds_provider_id = working_id
            db.commit()

        base.update(
            {
                "working_provider_id": working_id,
                "markets_count": len(markets),
                "has_sot_market": has_sot,
                "sot_candidate_markets": sot_candidates,
                "status": "ok",
                "raw_payload": _truncate_raw(raw_payload),
            },
        )

        if save_snapshot:
            snap = OddsDiscoverySnapshot(
                provider=PROVIDER_SPORTAPI,
                sportapi_event_id=int(event_id),
                sportapi_provider_id=int(working_id),
                markets_count=len(markets),
                raw_payload=base["raw_payload"] if isinstance(base["raw_payload"], dict) else None,
                normalized_payload={
                    "scan_type": "sot_providers",
                    "provider_slug": prov.provider_slug,
                    "has_sot_market": has_sot,
                    "sot_candidates": sot_candidates,
                    "markets_count": len(markets),
                },
            )
            db.add(snap)
            db.commit()

        return base
