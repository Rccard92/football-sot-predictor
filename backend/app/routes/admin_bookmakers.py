"""Admin: bookmakers API-Sports (legacy) e provider/quote SportAPI."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings, sportapi_configured
from app.core.database import get_db
from app.schemas.bookmakers import (
    SportApiMarketMappingBody,
    SportApiMarketsDiscoveryBody,
    SportApiNextRound1x2Body,
    SportApiNextRoundSotBody,
    SportApiProvidersSyncBody,
    SportApiScanSotProvidersBody,
    SportApiOddsDiscoveryBody,
    SportApiOddsTestEventBody,
)
from app.services.api_football_client import ApiFootballError
from app.services.odds_bookmakers_sync_service import OddsBookmakersSyncService
from app.services.sportapi.sportapi_client import SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_event_odds_test_service import SportApiEventOddsTestService
from app.services.sportapi.sportapi_markets_discovery_service import SportApiMarketsDiscoveryService
from app.services.sportapi.sportapi_next_round_1x2_service import SportApiNextRound1x2Service
from app.services.sportapi.sportapi_next_round_sot_odds_service import SportApiNextRoundSotOddsService
from app.services.sportapi.sportapi_scan_sot_providers_service import SportApiScanSotProvidersService
from app.services.sportapi.sportapi_odds_market_mapping_service import SportApiOddsMarketMappingService
from app.services.sportapi.sportapi_odds_discovery_service import SportApiOddsDiscoveryService
from app.services.sportapi.sportapi_odds_provider_detail_service import SportApiOddsProviderDetailService
from app.services.sportapi.sportapi_odds_providers_sync_service import SportApiOddsProvidersSyncService
from app.services.bookmakers.bookmaker_markets_discovery import BookmakerMarketsDiscoveryService
from app.services.bookmakers.bookmaker_providers_discovery import BookmakerProvidersDiscoveryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/bookmakers", tags=["admin-bookmakers"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


def _require_sportapi() -> None:
    if not sportapi_configured():
        raise HTTPException(
            status_code=400,
            detail="SportAPI disabilitata: imposta SPORTAPI_ENABLED=true e SPORTAPI_RAPIDAPI_KEY",
        )


@router.get("", response_model=None)
def list_bookmakers(db: Session = Depends(get_db)):
    """Legacy API-Sports — non esposto in UI v2.7."""
    try:
        out = OddsBookmakersSyncService().list_payload(db)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("list bookmakers DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.post("/sync", response_model=None)
def sync_bookmakers(db: Session = Depends(get_db)):
    """Legacy API-Sports sync."""
    _require_api_football_key()
    try:
        out = OddsBookmakersSyncService().sync_from_api(db)
    except ApiFootballError as exc:
        logger.warning("sync bookmakers API failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sync bookmakers DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync bookmakers failed")
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc
    return jsonable_encoder(out)


@router.get("/sportapi/providers", response_model=None)
def list_sportapi_providers(db: Session = Depends(get_db)):
    try:
        out = SportApiOddsProvidersSyncService().list_payload(db)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("list sportapi providers DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.post("/sportapi/providers/sync", response_model=None)
def sync_sportapi_providers(
    body: SportApiProvidersSyncBody | None = None,
    db: Session = Depends(get_db),
):
    _require_sportapi()
    sync_body = body or SportApiProvidersSyncBody()
    try:
        out = SportApiOddsProvidersSyncService().sync_it_app(
            db,
            country=sync_body.country,
            channel=sync_body.channel,
        )
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sync sportapi providers DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.post("/sportapi/providers/{slug}/sync-detail", response_model=None)
def sync_sportapi_provider_detail(slug: str, db: Session = Depends(get_db)):
    _require_sportapi()
    try:
        out = SportApiOddsProviderDetailService().sync_detail(db, slug)
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sync sportapi provider detail DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.post("/sportapi/odds/test-event", response_model=None)
def sportapi_odds_test_event(
    body: SportApiOddsTestEventBody,
    db: Session = Depends(get_db),
):
    _require_sportapi()
    try:
        out = SportApiEventOddsTestService().test_event(
            db,
            sportapi_event_id=int(body.sportapi_event_id),
            provider_slug=body.provider_slug,
            provider_id=body.provider_id,
            save_snapshot=bool(body.save_snapshot),
            fixture_id=body.fixture_id,
            api_fixture_id=body.api_fixture_id,
        )
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi test event DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc

    if out.get("status") == "error":
        raise HTTPException(status_code=502, detail=str(out.get("message") or "Test quote fallito"))
    return jsonable_encoder(out)


@router.post("/sportapi/odds/next-round-1x2", response_model=None)
def sportapi_odds_next_round_1x2(
    body: SportApiNextRound1x2Body,
    db: Session = Depends(get_db),
):
    _require_sportapi()
    try:
        out = SportApiNextRound1x2Service().run(
            db,
            provider_slug=body.provider_slug,
            season_year=body.season_year,
            force=bool(body.force),
        )
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi next round 1x2 DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc

    if out.get("status") == "error":
        raise HTTPException(status_code=400, detail=str(out.get("message") or "Batch 1X2 fallito"))
    return jsonable_encoder(out)


@router.post("/sportapi/odds-discovery", response_model=None)
def sportapi_odds_discovery(
    body: SportApiOddsDiscoveryBody,
    db: Session = Depends(get_db),
):
    """Legacy discovery — deprecato in UI, mantenuto per compatibilità."""
    if not sportapi_configured():
        raise HTTPException(
            status_code=400,
            detail="SportAPI disabilitata: imposta SPORTAPI_ENABLED=true e SPORTAPI_RAPIDAPI_KEY",
        )
    if body.fixture_id is None and body.api_fixture_id is None and body.sportapi_event_id is None:
        raise HTTPException(
            status_code=400,
            detail="Specificare fixture_id, api_fixture_id o sportapi_event_id",
        )
    try:
        out = SportApiOddsDiscoveryService().discover(
            db,
            fixture_id=body.fixture_id,
            api_fixture_id=body.api_fixture_id,
            sportapi_event_id=body.sportapi_event_id,
            provider_id=int(body.provider_id),
            save_snapshot=bool(body.save_snapshot),
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi odds discovery DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if out.get("status") == "error":
        msg = str(out.get("message") or "Errore discovery SportAPI")
        code = 400 if "Mapping" in msg or "Fixture" in msg else 502
        raise HTTPException(status_code=code, detail=msg)

    return jsonable_encoder(out)


@router.post("/sportapi/odds/markets-discovery", response_model=None)
def sportapi_odds_markets_discovery(
    body: SportApiMarketsDiscoveryBody,
    db: Session = Depends(get_db),
):
    _require_sportapi()
    try:
        out = SportApiMarketsDiscoveryService().discover(
            db,
            sportapi_event_id=int(body.sportapi_event_id),
            provider_slug=body.provider_slug,
            provider_id=body.provider_id,
        )
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi markets discovery DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc

    if out.get("status") == "error":
        raise HTTPException(status_code=502, detail=str(out.get("message") or "Discovery mercati fallita"))
    return jsonable_encoder(out)


@router.get("/sportapi/odds/market-mappings", response_model=None)
def list_sportapi_market_mappings(
    provider_slug: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        out = SportApiOddsMarketMappingService().list_payload(db, provider_slug)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("list sportapi market mappings DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.post("/sportapi/odds/market-mappings", response_model=None)
def create_sportapi_market_mapping(
    body: SportApiMarketMappingBody,
    db: Session = Depends(get_db),
):
    try:
        row = SportApiOddsMarketMappingService().upsert_mapping(
            db,
            provider_slug=body.provider_slug,
            raw_market_name=body.raw_market_name,
            normalized_market_key=body.normalized_market_key,
            provider_id_used=body.provider_id_used,
            raw_market_id=body.raw_market_id,
            confidence=body.confidence,
            sample_raw_market=body.sample_raw_market,
        )
        out = SportApiOddsMarketMappingService._row_dict(row)
        return jsonable_encoder({"status": "success", "mapping": out})
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("create sportapi market mapping DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc


@router.patch("/sportapi/odds/market-mappings/{mapping_id}/deactivate", response_model=None)
def deactivate_sportapi_market_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
):
    try:
        ok = SportApiOddsMarketMappingService().deactivate(db, int(mapping_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("deactivate sportapi market mapping DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Mapping non trovato")
    return jsonable_encoder({"status": "success", "id": int(mapping_id), "is_active": False})


@router.post("/sportapi/odds/next-round-sot", response_model=None)
def sportapi_odds_next_round_sot(
    body: SportApiNextRoundSotBody,
    db: Session = Depends(get_db),
):
    _require_sportapi()
    try:
        out = SportApiNextRoundSotOddsService().run(
            db,
            provider_slug=body.provider_slug,
            season_year=body.season_year,
            market_key=body.market_key,
            limit=int(body.limit),
        )
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi next round sot DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.post("/sportapi/odds/scan-sot-providers", response_model=None)
def sportapi_odds_scan_sot_providers(
    body: SportApiScanSotProvidersBody,
    db: Session = Depends(get_db),
):
    _require_sportapi()
    try:
        out = SportApiScanSotProvidersService().scan(
            db,
            sportapi_event_id=int(body.sportapi_event_id),
            country=body.country,
            max_providers=body.max_providers,
            provider_slug=body.provider_slug,
            save_snapshot=bool(body.save_snapshot),
            auto_sync_if_empty=bool(body.auto_sync_if_empty),
            channel=body.channel,
        )
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi scan sot providers DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.get("/providers", response_model=None)
def list_discovery_providers(db: Session = Depends(get_db)):
    """Fonti provider (API-Football + SportAPI) con stato configurazione."""
    try:
        out = BookmakerProvidersDiscoveryService().list_sources(db)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("list discovery providers DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.get("/providers/bookmakers", response_model=None)
def list_unified_bookmakers(db: Session = Depends(get_db)):
    """Tabella bookmaker aggregata da tutte le fonti."""
    try:
        out = BookmakerProvidersDiscoveryService().list_unified_bookmakers(db)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("list unified bookmakers DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.get("/markets", response_model=None)
def list_discovery_markets(
    provider_source: str | None = None,
    db: Session = Depends(get_db),
):
    """Catalogo mercati normalizzati (UNKNOWN evidenziato in payload)."""
    try:
        out = BookmakerMarketsDiscoveryService().list_markets(db, provider_source=provider_source)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("list discovery markets DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)
