from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION
from app.core.database import get_db
from app.models import Fixture, TeamSotPrediction
from app.schemas.predictions import (
    FixturePredictionsResponse,
    GeneratePredictionsBody,
    GeneratePredictionsResponse,
    TeamPredictionsResponse,
    TeamSotPredictionRead,
)
from app.services.sot_prediction_service import SotPredictionService

router = APIRouter(prefix="/predictions/sot", tags=["predictions"])


@router.post("/serie-a/{season}/generate", response_model=GeneratePredictionsResponse)
def generate_serie_a_predictions(
    season: int,
    db: Session = Depends(get_db),
    body: GeneratePredictionsBody = Body(default_factory=GeneratePredictionsBody),
) -> GeneratePredictionsResponse:
    svc = SotPredictionService()
    try:
        league_id = svc.resolve_serie_a_league_id(db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    line_value = body.line_value
    try:
        n = svc.generate_for_season(db, league_id, season, line_value=line_value)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return GeneratePredictionsResponse(
        league_id=league_id,
        season=season,
        model_version=BASELINE_SOT_MODEL_VERSION,
        rows_upserted=n,
    )


@router.get("/fixture/{fixture_id}", response_model=FixturePredictionsResponse)
def get_fixture_predictions(
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
) -> FixturePredictionsResponse:
    rows = db.scalars(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id == fixture_id,
            TeamSotPrediction.model_version == model_version,
        ),
    ).all()
    return FixturePredictionsResponse(
        fixture_id=fixture_id,
        predictions=[TeamSotPredictionRead.model_validate(r) for r in rows],
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
