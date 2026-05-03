import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.features import (
    SotFeatureSeasonSummaryResponse,
    SotFixtureFeaturesResponse,
    TeamSotFeatureRead,
)
from app.services.sot_feature_service import SotFeatureService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/features/sot", tags=["features"])


@router.post("/serie-a/{season}/build", response_model=None)
def build_serie_a_sot_features(season: int, db: Session = Depends(get_db)):
    svc = SotFeatureService()
    try:
        summary = svc.build_features_for_season_admin(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST build_sot_features: errore database")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        ) from exc

    if summary.get("status") == "error" and summary.get("rows_upserted", 0) == 0:
        return JSONResponse(
            status_code=502,
            content=jsonable_encoder(summary),
        )
    return jsonable_encoder(summary)


@router.post("/serie-a/{season}/build-upcoming", response_model=None)
def build_serie_a_sot_features_upcoming(season: int, db: Session = Depends(get_db)):
    svc = SotFeatureService()
    try:
        summary = svc.build_upcoming_features_for_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST build_sot_features_upcoming: errore database")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        ) from exc

    if summary.get("status") == "error" and summary.get("feature_rows_created_or_updated", 0) == 0:
        return JSONResponse(
            status_code=502,
            content=jsonable_encoder(summary),
        )
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/summary", response_model=SotFeatureSeasonSummaryResponse)
def sot_features_season_summary(season: int, db: Session = Depends(get_db)) -> SotFeatureSeasonSummaryResponse:
    svc = SotFeatureService()
    try:
        data = svc.get_season_summary(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET sot summary: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return SotFeatureSeasonSummaryResponse.model_validate(data)


@router.get("/fixture/{fixture_id}", response_model=SotFixtureFeaturesResponse)
def get_fixture_sot_features(fixture_id: int, db: Session = Depends(get_db)) -> SotFixtureFeaturesResponse:
    try:
        rows = SotFeatureService().get_fixture_feature_rows(db, fixture_id)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET fixture sot features: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return SotFixtureFeaturesResponse(
        fixture_id=fixture_id,
        rows=[TeamSotFeatureRead.model_validate(r) for r in rows],
    )
