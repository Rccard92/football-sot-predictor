from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import League, TeamSotFeature
from app.schemas.features import SotFeatureBuildResponse, SotFixtureFeaturesResponse, TeamSotFeatureRead
from app.services.ingestion_service import IngestionService
from app.services.sot_feature_service import SotFeatureService

router = APIRouter(prefix="/features/sot", tags=["features"])


@router.post("/serie-a/{season}/build", response_model=SotFeatureBuildResponse)
def build_serie_a_sot_features(season: int, db: Session = Depends(get_db)) -> SotFeatureBuildResponse:
    league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
    if league is None:
        raise HTTPException(status_code=404, detail="Lega Serie A non trovata")
    try:
        n = SotFeatureService().build_features_for_season(db, league.id, season)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SotFeatureBuildResponse(league_id=league.id, season=season, rows_upserted=n)


@router.get("/fixture/{fixture_id}", response_model=SotFixtureFeaturesResponse)
def get_fixture_sot_features(fixture_id: int, db: Session = Depends(get_db)) -> SotFixtureFeaturesResponse:
    rows = db.scalars(
        select(TeamSotFeature).where(TeamSotFeature.fixture_id == fixture_id),
    ).all()
    return SotFixtureFeaturesResponse(
        fixture_id=fixture_id,
        rows=[TeamSotFeatureRead.model_validate(r) for r in rows],
    )
