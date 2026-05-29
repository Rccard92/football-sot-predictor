from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.competition import IngestDryRunBody
from app.services.competition_ingestion_service import CompetitionIngestionService
from app.services.competition_service import CompetitionService
from app.services.league_season_api_helpers import SeasonNotAvailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/competitions", tags=["admin-competition-ingest"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(status_code=400, detail="API_FOOTBALL_KEY non configurata sul server")


def _ingest_body(body: IngestDryRunBody | None) -> bool:
    return bool(body.dry_run) if body else False


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


@router.post("/{competition_id}/refresh/next-round")
def refresh_competition_next_round(
    competition_id: int,
    body: IngestDryRunBody | None = None,
    db: Session = Depends(get_db),
):
    svc = CompetitionIngestionService()
    try:
        result = svc.refresh_next_round(db, competition_id, dry_run=_ingest_body(body))
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
