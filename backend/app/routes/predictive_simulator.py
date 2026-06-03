"""API laboratorio predittivo persistente v3.1."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.predictive_simulator import (
    PredictiveAiInsightsCreateBody,
    PredictiveFixtureNoteBody,
    PredictiveRunCreateBody,
)
from app.services.backtest.predictive_ai_insights_service import (
    OPENAI_NOT_CONFIGURED,
    PredictiveAiInsightsService,
    openai_configured,
)
from app.services.backtest.predictive_simulation_run_service import PredictiveSimulationRunService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictive-simulator", tags=["predictive-simulator"])


def _db_error(exc: Exception) -> HTTPException:
    logger.exception("Predictive simulator DB error")
    return HTTPException(
        status_code=503,
        detail={"error_code": "PREDICTIVE_DB_ERROR", "message": str(exc)},
    )


@router.get("/config")
def predictive_config():
    return {"openai_configured": openai_configured()}


@router.post("/run")
def create_predictive_run(
    body: PredictiveRunCreateBody,
    db: Session = Depends(get_db),
):
    svc = PredictiveSimulationRunService()
    try:
        result = svc.create_and_run(
            db,
            competition_id=body.competition_id,
            season_year=body.season_year,
            strategy=body.strategy,
            strategy_status=body.strategy_status,
            persist=body.persist,
            use_latest_version_per_round=body.use_latest_version_per_round,
            include_all_versions=body.include_all_versions,
        )
    except (OperationalError, ProgrammingError) as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        logger.exception("Predictive run failed")
        raise HTTPException(
            status_code=500,
            detail={"error_code": "PREDICTIVE_RUN_FAILED", "message": str(exc)},
        ) from exc
    return jsonable_encoder(result)


@router.get("/runs")
def list_predictive_runs(
    competition_id: int | None = Query(default=None),
    season_year: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    svc = PredictiveSimulationRunService()
    try:
        return jsonable_encoder(
            svc.list_runs(
                db,
                competition_id=competition_id,
                season_year=season_year,
                limit=limit,
            ),
        )
    except (OperationalError, ProgrammingError) as exc:
        raise _db_error(exc) from exc


@router.get("/runs/{run_id}")
def get_predictive_run(run_id: int, db: Session = Depends(get_db)):
    svc = PredictiveSimulationRunService()
    try:
        data = svc.get_run(db, run_id)
    except (OperationalError, ProgrammingError) as exc:
        raise _db_error(exc) from exc
    if data is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
    return jsonable_encoder(data)


@router.get("/runs/{run_id}/fixtures")
def get_predictive_fixtures(
    run_id: int,
    strategy_key: str | None = Query(default=None),
    round_number: int | None = Query(default=None),
    outcome_type: str | None = Query(default=None),
    predicted_bucket: str | None = Query(default=None),
    actual_bucket: str | None = Query(default=None),
    min_abs_error: float | None = Query(default=None),
    max_abs_error: float | None = Query(default=None),
    sort_by: str = Query(default="abs_error"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    svc = PredictiveSimulationRunService()
    try:
        return jsonable_encoder(
            svc.get_fixtures(
                db,
                run_id,
                strategy_key=strategy_key,
                round_number=round_number,
                outcome_type=outcome_type,
                predicted_bucket=predicted_bucket,
                actual_bucket=actual_bucket,
                min_abs_error=min_abs_error,
                max_abs_error=max_abs_error,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            ),
        )
    except (OperationalError, ProgrammingError) as exc:
        raise _db_error(exc) from exc


@router.post("/runs/{run_id}/fixtures/{fixture_id}/notes")
def upsert_fixture_note(
    run_id: int,
    fixture_id: int,
    body: PredictiveFixtureNoteBody,
    db: Session = Depends(get_db),
):
    run = PredictiveSimulationRunService().get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
    svc = PredictiveSimulationRunService()
    try:
        return jsonable_encoder(
            svc.upsert_note(
                db,
                run_id,
                fixture_id,
                body.strategy_key,
                body.note,
                tag=body.tag,
            ),
        )
    except (OperationalError, ProgrammingError) as exc:
        raise _db_error(exc) from exc


@router.post("/runs/{run_id}/ai-insights")
def generate_ai_insights(
    run_id: int,
    body: PredictiveAiInsightsCreateBody,
    db: Session = Depends(get_db),
):
    run = PredictiveSimulationRunService().get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
    if not openai_configured():
        raise HTTPException(
            status_code=503,
            detail={"error_code": OPENAI_NOT_CONFIGURED, "openai_configured": False},
        )
    svc = PredictiveAiInsightsService()
    try:
        result = svc.generate(
            db,
            run_id,
            analysis_type=body.analysis_type,
            fixture_id=body.fixture_id,
            strategy_key=body.strategy_key,
        )
    except (OperationalError, ProgrammingError) as exc:
        raise _db_error(exc) from exc
    if result.get("error_code") == "RUN_NOT_FOUND":
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
    if result.get("error_code") == "FIXTURE_NOT_FOUND":
        raise HTTPException(status_code=404, detail={"error_code": "FIXTURE_NOT_FOUND"})
    if result.get("error_code") == OPENAI_NOT_CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail={"error_code": OPENAI_NOT_CONFIGURED, "openai_configured": False},
        )
    return jsonable_encoder(result)


@router.get("/runs/{run_id}/ai-insights")
def list_ai_insights(
    run_id: int,
    analysis_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    run = PredictiveSimulationRunService().get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
    svc = PredictiveAiInsightsService()
    items = svc.list_history(db, run_id, analysis_type=analysis_type, limit=limit)
    return jsonable_encoder({"items": items})


@router.get("/runs/{run_id}/ai-insights/{insight_id}")
def get_ai_insight(run_id: int, insight_id: int, db: Session = Depends(get_db)):
    run = PredictiveSimulationRunService().get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
    svc = PredictiveAiInsightsService()
    data = svc.get_by_id(db, run_id, insight_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"error_code": "AI_INSIGHT_NOT_FOUND"})
    return jsonable_encoder(data)
