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
    V02ReadinessResponse,
)
from app.services.sot_line_evaluate import evaluate_match_sot_line, evaluate_sot_line
from app.services.sot_prediction_service import SotPredictionService
from app.services.sot_prediction_v02_service import SotPredictionV02Service
from app.services.predictions_v02.player_adjusted_service import SotPredictionV02PlayerAdjustedService
from app.services.predictions_v03.core_sot_service import SotPredictionV03CoreSotService
from app.services.predictions_v04.offensive_core_sot_service import SotPredictionV04OffensiveCoreSotService

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
    partial_result = {
        "upcoming_fixtures_found": 0,
        "predictions_created_or_updated": 0,
        "errors": [],
    }
    try:
        summary = svc.generate_v02_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v02_upcoming: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "database_operation",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST generate_v02_upcoming: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "generate_v02_upcoming",
                    "message": "Errore inatteso durante la generazione v0.2.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    if summary.get("status") == "error":
        return JSONResponse(
            status_code=502,
            content=jsonable_encoder(summary),
        )
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/v02-readiness", response_model=V02ReadinessResponse)
def get_serie_a_v02_readiness(
    season: int,
    db: Session = Depends(get_db),
) -> V02ReadinessResponse:
    svc = SotPredictionV02Service()
    try:
        data = svc.v02_readiness(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET v02-readiness: errore database")
        payload = {
            "season": season,
            "upcoming_fixtures": 0,
            "baseline_v01_upcoming_predictions": 0,
            "player_profiles_available": False,
            "standings_available": False,
            "adjustments_table_exists": False,
            "ready": False,
            "missing_requirements": ["database_unavailable"],
            "message": "Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        }
        return JSONResponse(status_code=503, content=jsonable_encoder(payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET v02-readiness: errore inatteso")
        payload = {
            "season": season,
            "upcoming_fixtures": 0,
            "baseline_v01_upcoming_predictions": 0,
            "player_profiles_available": False,
            "standings_available": False,
            "adjustments_table_exists": False,
            "ready": False,
            "missing_requirements": ["unexpected_error"],
            "message": "Errore inatteso durante il readiness check.",
        }
        return JSONResponse(status_code=500, content=jsonable_encoder(payload))
    return V02ReadinessResponse.model_validate(data)


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


@router.post("/serie-a/{season}/generate-v02-player-adjusted", response_model=None)
def generate_serie_a_predictions_v02_player_adjusted(
    season: int,
    db: Session = Depends(get_db),
):
    svc = SotPredictionV02PlayerAdjustedService()
    partial_result = {
        "upcoming_fixtures_found": 0,
        "predictions_created_or_updated": 0,
        "errors": [],
    }
    try:
        summary = svc.generate_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v02_player_adjusted: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "database_operation",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST generate_v02_player_adjusted: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "generate_v02_player_adjusted",
                    "message": "Errore inatteso durante la generazione v0.2 player adjusted.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    if summary.get("status") == "error":
        # Errore applicativo (es. baseline v0.1 mancante) → messaggio chiaro, senza 500 generico.
        return JSONResponse(status_code=409, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming-v02-player-adjusted", response_model=None)
def sot_predictions_serie_a_upcoming_v02_player_adjusted(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
):
    svc = SotPredictionV02PlayerAdjustedService()
    try:
        data = svc.upcoming_player_adjusted(db, season, limit=limit, only_next_round=only_next_round)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-v02-player-adjusted: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET upcoming-v02-player-adjusted: errore inatteso")
        raise HTTPException(status_code=500, detail="Errore inatteso") from exc
    return jsonable_encoder(data)


@router.post("/serie-a/{season}/generate-v03-core-sot", response_model=None)
def generate_serie_a_predictions_v03_core_sot(
    season: int,
    db: Session = Depends(get_db),
):
    svc = SotPredictionV03CoreSotService()
    partial_result = {
        "upcoming_fixtures_found": 0,
        "predictions_created_or_updated": 0,
        "errors": [],
    }
    try:
        summary = svc.generate_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v03_core_sot: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "database_operation",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST generate_v03_core_sot: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "generate_v03_core_sot",
                    "message": "Errore inatteso durante la generazione v0.3 core SOT.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    if summary.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming-v03-core-sot", response_model=None)
def sot_predictions_serie_a_upcoming_v03_core_sot(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
):
    svc = SotPredictionV03CoreSotService()
    try:
        data = svc.upcoming_v03(db, season, limit=limit, only_next_round=only_next_round)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-v03-core-sot: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET upcoming-v03-core-sot: errore inatteso")
        raise HTTPException(status_code=500, detail="Errore inatteso") from exc
    if isinstance(data, dict) and data.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(data))
    return jsonable_encoder(data)


@router.post("/serie-a/{season}/generate-v04-offensive-core-sot", response_model=None)
def generate_serie_a_predictions_v04_offensive_core_sot(
    season: int,
    db: Session = Depends(get_db),
):
    svc = SotPredictionV04OffensiveCoreSotService()
    partial_result = {
        "upcoming_fixtures_found": 0,
        "predictions_created_or_updated": 0,
        "errors": [],
    }
    try:
        summary = svc.generate_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v04_offensive_core_sot: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "database_operation",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST generate_v04_offensive_core_sot: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "generate_v04_offensive_core_sot",
                    "message": "Errore inatteso durante la generazione v0.4 offensive core SOT.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    if summary.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming-v04-offensive-core-sot", response_model=None)
def sot_predictions_serie_a_upcoming_v04_offensive_core_sot(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
):
    _ = only_next_round  # non ancora filtrato per round in v0.4
    svc = SotPredictionV04OffensiveCoreSotService()
    try:
        data = svc.upcoming_v04(db, season, limit=limit, only_next_round=only_next_round)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-v04-offensive-core-sot: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET upcoming-v04-offensive-core-sot: errore inatteso")
        raise HTTPException(status_code=500, detail="Errore inatteso") from exc
    if isinstance(data, dict) and data.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(data))
    return jsonable_encoder(data)


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
