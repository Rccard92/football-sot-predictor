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
    EvaluateMatchSotLineBody,
    EvaluateMatchSotLineResponse,
    EvaluateSotLineBody,
    EvaluateSotLineResponse,
    FixturePredictionsEnrichedResponse,
    FixtureSotPredictionItem,
    GeneratePredictionsBody,
    SotPredictionsSeasonSummaryResponse,
    TeamPredictionsResponse,
    TeamSotPredictionRead,
    UpcomingMatchesResponse,
    UpcomingV02Response,
)
from app.services.sot_line_evaluate import evaluate_match_sot_line, evaluate_sot_line
from app.services.sot_prediction_service import SotPredictionService
from app.services.sot_prediction_v02_service import SotPredictionV02Service

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


@router.post("/serie-a/{season}/generate-upcoming", response_model=None)
def generate_serie_a_predictions_upcoming(
    season: int,
    db: Session = Depends(get_db),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
):
    svc = SotPredictionService()
    try:
        summary = svc.generate_upcoming_predictions_for_season(db, season, model_version=model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_sot_predictions_upcoming: errore database")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        ) from exc

    if summary.get("status") == "error" and summary.get("predictions_created_or_updated", 0) == 0:
        return JSONResponse(status_code=502, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming", response_model=UpcomingMatchesResponse)
def sot_predictions_serie_a_upcoming(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    match_round: str | None = Query(default=None, alias="round"),
    only_next_round: bool = Query(default=True),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
) -> UpcomingMatchesResponse:
    svc = SotPredictionService()
    try:
        data = svc.get_serie_a_upcoming_matches(
            db,
            season,
            limit=limit,
            round_filter=match_round,
            only_next_round=only_next_round,
            model_version=model_version,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return UpcomingMatchesResponse.model_validate(data)


@router.post("/evaluate-line", response_model=EvaluateSotLineResponse)
def evaluate_sot_line_endpoint(body: EvaluateSotLineBody) -> EvaluateSotLineResponse:
    return EvaluateSotLineResponse.model_validate(evaluate_sot_line(body.expected_sot, body.line_value))


@router.post("/evaluate-match-line", response_model=EvaluateMatchSotLineResponse)
def evaluate_match_sot_line_endpoint(body: EvaluateMatchSotLineBody) -> EvaluateMatchSotLineResponse:
    return EvaluateMatchSotLineResponse.model_validate(
        evaluate_match_sot_line(
            body.home_expected_sot,
            body.away_expected_sot,
            body.line_value,
            home_adjusted_expected_sot=body.home_adjusted_expected_sot,
            away_adjusted_expected_sot=body.away_adjusted_expected_sot,
            use_adjusted=body.use_adjusted,
            odds=body.odds,
            bookmaker=body.bookmaker,
            market_type=body.market_type,
        ),
    )


@router.post("/serie-a/{season}/generate-v02-upcoming", response_model=None)
def generate_serie_a_predictions_v02_upcoming(
    season: int,
    db: Session = Depends(get_db),
):
    svc = SotPredictionV02Service()
    try:
        summary = svc.generate_v02_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v02_upcoming: errore database")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        ) from exc
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming-v02", response_model=UpcomingV02Response)
def sot_predictions_serie_a_upcoming_v02(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
) -> UpcomingV02Response:
    svc = SotPredictionV02Service()
    try:
        data = svc.upcoming_v02(
            db,
            season,
            limit=limit,
            only_next_round=only_next_round,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-v02: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return UpcomingV02Response.model_validate(data)


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
