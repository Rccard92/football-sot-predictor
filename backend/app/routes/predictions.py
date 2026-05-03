import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION
from app.core.database import get_db
from app.models import Fixture, TeamSotPrediction
from app.schemas.predictions import (
    FixturePredictionsEnrichedResponse,
    FixtureSotPredictionItem,
    GeneratePredictionsBody,
    SotPredictionsSeasonSummaryResponse,
    TeamPredictionsResponse,
    TeamSotPredictionRead,
)
from app.services.sot_prediction_service import SotPredictionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions/sot", tags=["predictions"])


@router.post("/serie-a/{season}/generate", response_model=None)
def generate_serie_a_predictions(
    season: int,
    db: Session = Depends(get_db),
    body: GeneratePredictionsBody = Body(default_factory=GeneratePredictionsBody),
):
    _ = body  # line_value non usato nello Step 5
    svc = SotPredictionService()
    try:
        summary = svc.generate_for_season_admin(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_sot_predictions: errore database")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        ) from exc

    if summary.get("status") == "error" and summary.get("predictions_created_or_updated", 0) == 0:
        return JSONResponse(status_code=502, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/summary", response_model=SotPredictionsSeasonSummaryResponse)
def sot_predictions_season_summary(
    season: int,
    db: Session = Depends(get_db),
) -> SotPredictionsSeasonSummaryResponse:
    svc = SotPredictionService()
    try:
        data = svc.get_season_predictions_summary(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET predictions summary: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return SotPredictionsSeasonSummaryResponse.model_validate(data)


@router.get("/fixture/{fixture_id}", response_model=FixturePredictionsEnrichedResponse)
def get_fixture_predictions(
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
) -> FixturePredictionsEnrichedResponse:
    svc = SotPredictionService()
    try:
        items = svc.get_fixture_predictions_enriched(db, fixture_id, model_version=model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET fixture predictions: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc

    return FixturePredictionsEnrichedResponse(
        fixture_id=fixture_id,
        predictions=[FixtureSotPredictionItem.model_validate(x) for x in items],
    )


@router.get("/team/{team_id}", response_model=TeamPredictionsResponse)
def get_team_predictions(
    team_id: int,
    db: Session = Depends(get_db),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
    limit: int = Query(default=100, ge=1, le=500),
) -> TeamPredictionsResponse:
    rows = db.scalars(
        select(TeamSotPrediction)
        .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
        .where(
            TeamSotPrediction.team_id == team_id,
            TeamSotPrediction.model_version == model_version,
        )
        .order_by(Fixture.kickoff_at.desc(), Fixture.id.desc())
        .limit(limit),
    ).all()
    return TeamPredictionsResponse(
        team_id=team_id,
        predictions=[TeamSotPredictionRead.model_validate(r) for r in rows],
    )
