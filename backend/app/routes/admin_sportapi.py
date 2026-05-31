"""Admin/debug SportAPI RapidAPI — mapping e lineups (non usati nel modello)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings, sportapi_configured
from app.core.database import get_db
from app.schemas.sportapi import SportApiMappingConfirmBody
from app.services.sportapi.sportapi_client import SportApiDisabledError
from app.services.sportapi.sportapi_fixture_resolve import FIXTURE_NOT_FOUND_MSG
from app.services.sportapi.sportapi_lineup_impact_service import LineupImpactSimulationService
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService
from app.services.sportapi.sportapi_matching_service import SportApiMatchingService
from app.services.sportapi.sportapi_player_matching_service import SportApiPlayerMatchingService
from app.services.sportapi.lineup_refresh_impact_orchestrator import LineupRefreshImpactOrchestrator
from app.schemas.sportapi_unavailable_backfill import SportApiUnavailableBackfillRequest
from app.schemas.sportapi_fixture_mapping_backfill import SportApiFixtureMappingBackfillRequest
from app.services.sportapi.sportapi_unavailable_backfill_service import SportApiUnavailableBackfillService
from app.services.sportapi.sportapi_unavailable_debug_service import SportApiUnavailableDebugService
from app.services.sportapi.sportapi_fixture_mapping_backfill_service import SportApiFixtureMappingBackfillService
from app.services.sportapi.sportapi_fixture_mapping_debug_service import SportApiFixtureMappingDebugService
from app.services.sportapi.sportapi_round_refresh_service import SportApiRoundRefreshService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sportapi", tags=["admin-sportapi"])


def _fixture_not_found_message(payload: dict) -> str | None:
    msg = str(payload.get("message") or "")
    if payload.get("status") != "error":
        return None
    if msg == FIXTURE_NOT_FOUND_MSG or "non trovata" in msg.lower():
        return msg or FIXTURE_NOT_FOUND_MSG
    return None


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API-Football key mancante: imposta API_FOOTBALL_KEY per sincronizzare le rose",
        )


def _require_sportapi_enabled() -> None:
    if not sportapi_configured():
        raise HTTPException(
            status_code=400,
            detail="SportAPI disabilitata: imposta SPORTAPI_ENABLED=true e SPORTAPI_RAPIDAPI_KEY",
        )


def _refresh_next_round_lineups_handler(
    season: int,
    db: Session,
    *,
    force: bool,
    sync_squads: bool,
    regenerate_v20: bool,
    limit: int,
):
    _require_sportapi_enabled()
    try:
        return SportApiRoundRefreshService().refresh_next_round_lineups(
            db,
            int(season),
            force=force,
            sync_squads=sync_squads,
            regenerate_v20=regenerate_v20,
            limit=limit,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi refresh next round DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/debug/fixture/{fixture_id}/lineup-unavailable", response_model=None)
def sportapi_debug_fixture_lineup_unavailable(
    fixture_id: int,
    competition_id: int = Query(...),
    dry_run: bool = Query(default=True),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Debug indisponibili SportAPI per fixture target esatta (Step K.2)."""
    _require_sportapi_enabled()
    try:
        payload = SportApiUnavailableDebugService().debug_fixture(
            db,
            fixture_id=int(fixture_id),
            competition_id=int(competition_id),
            dry_run=bool(dry_run),
            force_refresh=bool(force_refresh),
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi debug lineup-unavailable DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.status == "error" and payload.mapping_status == "fixture_not_found":
        raise HTTPException(status_code=404, detail=payload.warnings[0] if payload.warnings else "Fixture not found")
    return jsonable_encoder(payload)


@router.get("/debug/fixture/{fixture_id}/mapping", response_model=None)
def sportapi_debug_fixture_mapping(
    fixture_id: int,
    competition_id: int = Query(...),
    dry_run: bool = Query(default=True),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Debug mapping fixture interna ↔ SportAPI (Step K.3)."""
    _require_sportapi_enabled()
    try:
        payload = SportApiFixtureMappingDebugService().debug_fixture(
            db,
            fixture_id=int(fixture_id),
            competition_id=int(competition_id),
            dry_run=bool(dry_run),
            force_refresh=bool(force_refresh),
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi debug fixture mapping DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.status == "error" and payload.warnings and "non trovata" in payload.warnings[0].lower():
        raise HTTPException(status_code=404, detail=payload.warnings[0])
    return jsonable_encoder(payload)


@router.post("/competitions/{competition_id}/backfill-fixture-mappings", response_model=None)
def sportapi_backfill_fixture_mappings(
    competition_id: int,
    body: SportApiFixtureMappingBackfillRequest,
    db: Session = Depends(get_db),
):
    """Backfill mapping fixture SportAPI per round/fixture finished (Step K.3)."""
    _require_sportapi_enabled()
    try:
        payload = SportApiFixtureMappingBackfillService().backfill(
            db,
            competition_id=int(competition_id),
            round_number=body.round_number,
            fixture_ids=body.fixture_ids,
            dry_run=body.dry_run,
            force_refresh=body.force_refresh,
            limit=body.limit,
            offset=body.offset,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi backfill fixture mappings DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(payload)


@router.post("/competitions/{competition_id}/backfill-unavailable", response_model=None)
def sportapi_backfill_unavailable(
    competition_id: int,
    body: SportApiUnavailableBackfillRequest,
    db: Session = Depends(get_db),
):
    """Backfill indisponibili storici SportAPI per round/fixture finished (Step K.2)."""
    _require_sportapi_enabled()
    try:
        payload = SportApiUnavailableBackfillService().backfill(
            db,
            competition_id=int(competition_id),
            round_number=body.round_number,
            fixture_ids=body.fixture_ids,
            dry_run=body.dry_run,
            force_refresh=body.force_refresh,
            limit=body.limit,
            offset=body.offset,
            auto_confirm_mapping=body.auto_confirm_mapping,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi backfill-unavailable DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(payload)


@router.post("/serie-a/{season}/refresh-next-round-lineups", response_model=None)
def sportapi_refresh_next_round_lineups(
    season: int,
    db: Session = Depends(get_db),
    force: bool = Query(False),
    sync_squads: bool = Query(False),
    regenerate_v20: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
):
    """Batch: mapping (se serve) + lineups SportAPI per il prossimo turno."""
    out = _refresh_next_round_lineups_handler(
        season,
        db,
        force=force,
        sync_squads=sync_squads,
        regenerate_v20=regenerate_v20,
        limit=limit,
    )
    return jsonable_encoder(out)


@router.post("/lineups/serie-a/{season}/next-round/refresh", response_model=None)
def sportapi_refresh_next_round_lineups_alias(
    season: int,
    db: Session = Depends(get_db),
    force: bool = Query(False),
    sync_squads: bool = Query(False),
    regenerate_v20: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
):
    """Alias batch refresh lineups prossimo turno."""
    out = _refresh_next_round_lineups_handler(
        season,
        db,
        force=force,
        sync_squads=sync_squads,
        regenerate_v20=regenerate_v20,
        limit=limit,
    )
    return jsonable_encoder(out)


@router.post("/serie-a/{season}/sync-api-squads-batch", response_model=None)
def sportapi_sync_api_squads_batch(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
):
    """Sync rose API-Sports per tutte le squadre del prossimo turno."""
    _require_api_football_key()
    try:
        out = SportApiRoundRefreshService().sync_next_round_api_squads(db, int(season), limit=limit)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi sync squads batch DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(out)


@router.get("/debug/fixture/{fixture_id}", response_model=None)
def sportapi_debug_fixture_match(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Match debug: una sola chiamata scheduled-events per la data della fixture."""
    try:
        svc = SportApiMatchingService()
        payload = svc.debug_match_fixture(db, int(fixture_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi debug DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        return jsonable_encoder(
            {
                "status": "disabled",
                "message": str(exc),
                "fixture_id": int(fixture_id),
                "sportapi_enabled": False,
            },
        )

    not_found = _fixture_not_found_message(payload)
    if not_found:
        raise HTTPException(status_code=404, detail=not_found)
    return jsonable_encoder(payload)


@router.post("/mappings/{fixture_id}/confirm", response_model=None)
def sportapi_confirm_mapping(
    fixture_id: int,
    body: SportApiMappingConfirmBody,
    db: Session = Depends(get_db),
):
    _require_sportapi_enabled()
    if body.confidence_score is not None and body.confidence_score < 90:
        logger.info(
            "sportapi mapping confirm fixture=%s score=%s (manual override)",
            fixture_id,
            body.confidence_score,
        )
    try:
        out = SportApiLineupService().confirm_mapping(
            db,
            int(fixture_id),
            provider_event_id=body.provider_event_id,
            confidence_score=body.confidence_score,
            matched_by=body.matched_by or "admin_manual",
            raw_payload=body.raw_payload,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi confirm mapping DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    not_found = _fixture_not_found_message(out)
    if not_found:
        raise HTTPException(status_code=404, detail=not_found)
    return jsonable_encoder(out)


@router.post("/lineups/{fixture_id}/fetch", response_model=None)
def sportapi_fetch_lineups(
    fixture_id: int,
    db: Session = Depends(get_db),
    track_impact: bool = Query(False),
    regenerate_v20: bool = Query(True),
):
    """Fetch lineups per event_id mappato (1 chiamata API). Con track_impact: snapshot pre/post e delta v2.0."""
    _require_sportapi_enabled()
    try:
        if track_impact:
            out = LineupRefreshImpactOrchestrator().refresh_fixture_with_impact(
                db,
                int(fixture_id),
                regenerate_v20=regenerate_v20,
            )
        else:
            out = SportApiLineupService().fetch_and_persist_lineups(db, int(fixture_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi fetch lineups DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    refresh_result = out.get("refresh_result") if track_impact else out
    status = str((refresh_result or out).get("status") or out.get("status") or "")
    if status == "error":
        msg = str((refresh_result or out).get("message") or out.get("message") or "")
        not_found = _fixture_not_found_message(refresh_result or out)
        if not_found:
            raise HTTPException(status_code=404, detail=not_found)
        if "non trovato" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=502, detail=msg)
    return jsonable_encoder(out)


@router.get("/lineups/{fixture_id}/last-refresh-impact", response_model=None)
def sportapi_last_refresh_impact(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Ultimo confronto pre/post refresh formazioni per la fixture."""
    latest = LineupRefreshImpactOrchestrator.load_latest_impact_by_fixture_ids(db, [int(fixture_id)])
    row = latest.get(int(fixture_id))
    if not row:
        return jsonable_encoder({"has_comparison": False, "fixture_id": int(fixture_id)})
    return jsonable_encoder({"has_comparison": True, "fixture_id": int(fixture_id), **row})


@router.get("/lineups/{fixture_id}", response_model=None)
def sportapi_get_lineups(
    fixture_id: int,
    include_raw: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        out = SportApiLineupService().get_stored_lineups(
            db,
            int(fixture_id),
            include_raw=include_raw,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi get lineups DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc

    not_found = _fixture_not_found_message(out)
    if not_found:
        raise HTTPException(status_code=404, detail=not_found)
    return jsonable_encoder(out)


@router.post("/fixture/{fixture_id}/sync-api-squads", response_model=None)
def sportapi_sync_api_squads_for_fixture(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Sync manuale rosa API-Sports per casa e trasferta della fixture."""
    from app.models import Season, Team
    from app.services.player_data.squads import sync_team_squads
    from app.services.sportapi.sportapi_fixture_resolve import resolve_fixture_or_error

    _require_api_football_key()
    try:
        fx, err = resolve_fixture_or_error(db, int(fixture_id))
        if fx is None:
            raise HTTPException(
                status_code=404,
                detail=(err or {}).get("message", FIXTURE_NOT_FOUND_MSG),
            )
        season = db.get(Season, int(fx.season_id))
        if season is None:
            raise HTTPException(status_code=400, detail="Stagione fixture non trovata")
        payload = sync_team_squads(
            db,
            int(season.year),
            [int(fx.home_team_id), int(fx.away_team_id)],
        )
        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        payload["fixture_id"] = int(fx.id)
        payload["teams"] = [
            {"team_id": int(fx.home_team_id), "name": home.name if home else None},
            {"team_id": int(fx.away_team_id), "name": away.name if away else None},
        ]
        return jsonable_encoder(payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi sync api squads DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc


@router.get("/fixture/{fixture_id}/player-matching", response_model=None)
def sportapi_player_matching_preview(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Preview matching giocatori SportAPI ↔ API-Sports (solo DB)."""
    from app.models import Team
    from app.services.sportapi.sportapi_fixture_resolve import resolve_fixture_or_error
    from app.services.sportapi.sportapi_lineup_present import build_sportapi_lineups_audit

    try:
        fx, err = resolve_fixture_or_error(db, int(fixture_id))
        if fx is None:
            raise HTTPException(
                status_code=404,
                detail=(err or {}).get("message", FIXTURE_NOT_FOUND_MSG),
            )
        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        lineups = build_sportapi_lineups_audit(
            db,
            int(fx.id),
            home_team_name=home.name if home else "Casa",
            away_team_name=away.name if away else "Trasferta",
        )
        svc = SportApiPlayerMatchingService()
        players = svc.collect_sportapi_players_from_lineups(lineups)
        matching = svc.match_players_for_fixture(db, int(fx.id), sportapi_players=players)
        impact = LineupImpactSimulationService().simulate_for_fixture(
            db,
            int(fx.id),
            home_team_name=home.name if home else None,
            away_team_name=away.name if away else None,
        )
        return jsonable_encoder(
            {
                "fixture_id": int(fx.id),
                "sportapi_lineups_available": lineups.get("available"),
                "player_matching": matching,
                "lineup_impact_simulation": impact,
            },
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi player matching DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
