from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings, sportapi_configured
from app.core.database import get_db
from app.schemas.competition import IngestDryRunBody, SportApiLineupsIngestBody
from app.schemas.tracked_betting_picks import CreateTrackedPicksFromRoundBody
from app.services.competition_ingestion_service import CompetitionIngestionService
from app.services.competition_service import CompetitionService
from app.services.competition_sportapi_lineup_service import CompetitionSportApiLineupService
from app.services.league_season_api_helpers import SeasonNotAvailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/competitions", tags=["admin-competition-ingest"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(status_code=400, detail="API_FOOTBALL_KEY non configurata sul server")


def _ingest_body(body: IngestDryRunBody | None) -> bool:
    return bool(body.dry_run) if body else False


def _ingest_model_version(body: IngestDryRunBody | None) -> str | None:
    if body is None or body.model_version is None:
        return None
    mv = str(body.model_version).strip()
    return mv or None


@router.post("/{competition_id}/ingest/bootstrap")
def bootstrap_competition(
    competition_id: int,
    body: IngestDryRunBody | None = None,
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    CompetitionService().get_by_id_or_raise(db, competition_id)
    svc = CompetitionIngestionService()
    try:
        result = svc.bootstrap(db, competition_id, dry_run=_ingest_body(body))
    except SeasonNotAvailableError as exc:
        return JSONResponse(status_code=422, content=jsonable_encoder(exc.payload))
    return jsonable_encoder(result)


@router.post("/{competition_id}/ingest/standings")
def ingest_competition_standings(
    competition_id: int,
    body: IngestDryRunBody | None = None,
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    svc = CompetitionIngestionService()
    return jsonable_encoder(
        svc.ingest_standings(db, competition_id, dry_run=_ingest_body(body))
    )


@router.post("/{competition_id}/ingest/team-stats")
def ingest_competition_team_stats(
    competition_id: int,
    body: IngestDryRunBody | None = None,
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    svc = CompetitionIngestionService()
    return jsonable_encoder(
        svc.ingest_team_stats(db, competition_id, dry_run=_ingest_body(body))
    )


@router.post("/{competition_id}/ingest/player-match-stats")
def ingest_competition_player_match_stats(
    competition_id: int,
    body: IngestDryRunBody | None = None,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    svc = CompetitionIngestionService()
    return jsonable_encoder(
        svc.ingest_player_match_stats(
            db, competition_id, dry_run=_ingest_body(body), force=force
        )
    )


@router.post("/{competition_id}/features/player-season-profiles/build")
def build_competition_player_season_profiles(
    competition_id: int,
    body: IngestDryRunBody | None = None,
    db: Session = Depends(get_db),
):
    svc = CompetitionIngestionService()
    return jsonable_encoder(
        svc.build_player_season_profiles(db, competition_id, dry_run=_ingest_body(body))
    )


@router.post("/{competition_id}/ingest/lineups")
def ingest_competition_lineups(
    competition_id: int,
    body: IngestDryRunBody | None = None,
    fixture_id: int | None = Query(None),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    svc = CompetitionIngestionService()
    return jsonable_encoder(
        svc.ingest_lineups(
            db, competition_id, dry_run=_ingest_body(body), fixture_id=fixture_id, force=force
        )
    )


def _require_sportapi() -> None:
    if not sportapi_configured():
        raise HTTPException(status_code=400, detail="SportAPI non configurata sul server")


@router.post("/{competition_id}/ingest/sportapi-lineups")
def ingest_competition_sportapi_lineups(
    competition_id: int,
    body: SportApiLineupsIngestBody | None = None,
    db: Session = Depends(get_db),
):
    _require_sportapi()
    CompetitionService().get_by_id_or_raise(db, competition_id)
    opts = body or SportApiLineupsIngestBody()
    scope = str(opts.scope or "next_round")
    if scope not in ("next_round", "upcoming_limit", "fixture_ids"):
        raise HTTPException(status_code=422, detail=f"scope non supportato: {scope}")
    svc = CompetitionSportApiLineupService()
    result = svc.ingest(
        db,
        competition_id,
        scope=scope,  # type: ignore[arg-type]
        dry_run=bool(opts.dry_run),
        force=bool(opts.force),
        regenerate_v20=bool(opts.regenerate_v20),
        upcoming_limit=int(opts.upcoming_limit),
        fixture_ids=opts.fixture_ids,
    )
    if result.get("status") == "error" and result.get("code") in (
        "no_future_fixtures",
        "fixture_competition_mismatch",
        "fixture_ids_required",
        "sportapi_disabled",
    ):
        return JSONResponse(status_code=422, content=jsonable_encoder(result))
    return jsonable_encoder(result)


def _ingest_generate_mode(body: IngestDryRunBody | None) -> str:
    if body is None:
        return "default"
    return str(body.generate_mode or "default")


@router.post("/{competition_id}/refresh/next-round")
def refresh_competition_next_round(
    competition_id: int,
    body: IngestDryRunBody | None = None,
    db: Session = Depends(get_db),
):
    dry_run = _ingest_body(body)
    model_version = _ingest_model_version(body)
    generate_mode = _ingest_generate_mode(body)
    logger.info(
        "refresh next-round request competition_id=%s dry_run=%s model_version=%s generate_mode=%s",
        competition_id,
        dry_run,
        model_version,
        generate_mode,
    )
    svc = CompetitionIngestionService()
    try:
        result = svc.refresh_next_round(
            db,
            competition_id,
            dry_run=dry_run,
            model_version=model_version,
            generate_mode=generate_mode,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "refresh next-round competition_id=%s: errore inatteso",
            competition_id,
        )
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "unexpected_error",
                    "message": "Errore inatteso durante il refresh della prossima giornata.",
                    "competition_id": competition_id,
                    "step": "refresh_next_round",
                    "details": str(exc)[:500],
                },
            ),
        )

    if result.get("status") == "error":
        return JSONResponse(status_code=422, content=jsonable_encoder(result))
    return jsonable_encoder(result)
def create_competition_tracked_picks_from_round(
    competition_id: int,
    body: CreateTrackedPicksFromRoundBody,
    db: Session = Depends(get_db),
):
    from app.services.tracked_pick_round_backfill_service import TrackedPickRoundBackfillService

    try:
        out = TrackedPickRoundBackfillService().create_from_competition(
            db,
            int(competition_id),
            round_key=body.round,
            model_id=body.model_id,
            pick_type=body.pick_type,
            force=bool(body.force),
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("create tracked picks competition=%s DB error", competition_id)
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)
