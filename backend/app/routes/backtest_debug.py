"""Debug read-only Backtest Engine (Step C.1 + D + E + F + G2A + G2B + H)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.historical_lineup_audit_service import HistoricalLineupAuditService
from app.services.backtest.historical_unavailable_audit_service import HistoricalUnavailableAuditService
from app.services.backtest.point_in_time_context_service import PointInTimeContextService
from app.services.backtest.sot_pick_evaluation_preview_service import SotPickEvaluationPreviewService
from app.services.backtest.sot_v21_mini_run_preview_service import SotV21MiniRunPreviewService
from app.services.backtest.sot_v21_preview_service import SotV21PointInTimePreviewService
from app.services.backtest.round_analysis_model_registry import model_result_to_block
from app.services.backtest.round_analysis_model_registry import get_round_analysis_adapter
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig
from app.services.backtest_health_service import BacktestHealthService
from app.schemas.backtest_round_analysis import normalize_model_keys
from app.models import Competition, Fixture
from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
from app.services.backtest.sot_pick_evaluation_logic import DEFAULT_PICK_LINES
from app.schemas.backtest_sot_pick_evaluation import SotPickEvaluationRequest
from app.schemas.backtest_sot_v21_mini_run import SotV21MiniRunRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/debug", tags=["backtest-debug"])


@router.get("/health")
def backtest_debug_health(db: Session = Depends(get_db)):
    svc = BacktestHealthService()
    try:
        payload = svc.get_health(db)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest debug health: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/fixtures")
def backtest_debug_fixtures(
    competition_id: int = Query(...),
    season_year: int | None = Query(default=None),
    status: str = Query(default="finished"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    round_contains: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    svc = BacktestFixtureDebugService()
    try:
        payload = svc.list_candidate_fixtures(
            db,
            competition_id=competition_id,
            season_year=season_year,
            status=status,
            limit=limit,
            offset=offset,
            round_contains=round_contains,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest debug fixtures: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/point-in-time-context")
def backtest_debug_point_in_time_context(
    competition_id: int = Query(...),
    fixture_id: int = Query(...),
    market_key: str = Query(default="shots_on_target"),
    mode: str = Query(default="pre_lineup"),
    db: Session = Depends(get_db),
):
    svc = PointInTimeContextService()
    try:
        payload = svc.build_sot_context_with_historical(
            db,
            competition_id=competition_id,
            fixture_id=fixture_id,
            mode=mode,
            market_key=market_key,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest point-in-time context: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/sot-v21-preview")
def backtest_debug_sot_v21_preview(
    competition_id: int = Query(...),
    fixture_id: int = Query(...),
    mode: str = Query(default="pre_lineup"),
    db: Session = Depends(get_db),
):
    svc = SotV21PointInTimePreviewService()
    try:
        payload = svc.build_preview(
            db,
            competition_id=competition_id,
            fixture_id=fixture_id,
            mode=mode,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest sot-v21-preview: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.post("/sot-v21-mini-run")
def backtest_debug_sot_v21_mini_run(
    body: SotV21MiniRunRequest,
    db: Session = Depends(get_db),
):
    svc = SotV21MiniRunPreviewService()
    try:
        payload = svc.run_preview(
            db,
            competition_id=body.competition_id,
            mode=body.mode,
            limit=body.limit,
            offset=body.offset,
            round_number=body.round_number,
            round_contains=body.round_contains,
            fixture_ids=body.fixture_ids,
            include_trace=body.include_trace,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST backtest sot-v21-mini-run: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.post("/sot-pick-evaluation-preview")
def backtest_debug_sot_pick_evaluation_preview(
    body: SotPickEvaluationRequest,
    db: Session = Depends(get_db),
):
    svc = SotPickEvaluationPreviewService()
    try:
        payload = svc.run_pick_evaluation(
            db,
            competition_id=body.competition_id,
            mode=body.mode,
            limit=body.limit,
            offset=body.offset,
            round_number=body.round_number,
            round_contains=body.round_contains,
            fixture_ids=body.fixture_ids,
            lines=body.lines,
            cautious_drop_threshold=body.cautious_drop_threshold,
            include_no_pick=body.include_no_pick,
            play_advice_config=body.to_play_advice_config(),
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST backtest sot-pick-evaluation-preview: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/historical-lineup-audit/fixture")
def backtest_debug_historical_lineup_audit_fixture(
    competition_id: int = Query(...),
    fixture_id: int = Query(...),
    db: Session = Depends(get_db),
):
    svc = HistoricalLineupAuditService()
    try:
        payload = svc.audit_fixture(
            db,
            competition_id=competition_id,
            fixture_id=fixture_id,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET historical-lineup-audit/fixture: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/historical-lineup-audit/round")
def backtest_debug_historical_lineup_audit_round(
    competition_id: int = Query(...),
    round_number: int = Query(..., ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    svc = HistoricalLineupAuditService()
    try:
        payload = svc.audit_round(
            db,
            competition_id=competition_id,
            round_number=round_number,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET historical-lineup-audit/round: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/historical-unavailable-audit")
def backtest_debug_historical_unavailable_audit(
    competition_id: int = Query(...),
    round_number: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    svc = HistoricalUnavailableAuditService()
    try:
        payload = svc.audit(
            db,
            competition_id=competition_id,
            round_number=round_number,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET historical-unavailable-audit: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/round-analysis/fixture/{fixture_id}/model/{model_version}")
def backtest_debug_round_analysis_fixture_model(
    fixture_id: int,
    model_version: str,
    competition_id: int = Query(...),
    season_year: int | None = Query(default=None),
    mode: str = Query(default=BACKTEST_MODE_HISTORICAL_OFFICIAL_XI),
    db: Session = Depends(get_db),
):
    """Debug singola fixture × modello Round Analysis."""
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        raise HTTPException(status_code=404, detail="fixture_not_found")
    if fx.competition_id is None or int(fx.competition_id) != int(competition_id):
        raise HTTPException(status_code=422, detail="fixture_competition_mismatch")

    comp = db.get(Competition, int(competition_id))
    if comp is None:
        raise HTTPException(status_code=404, detail="competition_not_found")
    if season_year is not None and int(comp.season) != int(season_year):
        raise HTTPException(status_code=422, detail="season_year_mismatch")

    try:
        model_key = normalize_model_keys([model_version])[0]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    adapter = get_round_analysis_adapter(model_key)
    try:
        result = adapter.predict_fixture(
            db,
            fixture=fx,
            competition_id=int(competition_id),
            mode=mode,
            lines=list(DEFAULT_PICK_LINES),
            cautious_drop_threshold=0.75,
            play_config=PlayAdviceConfig(),
            data_quality={"lineup": "unknown", "mapping": "unknown"},
            actual_total=None,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis debug fixture/model: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc

    block = model_result_to_block(result)
    trace = result.trace_summary or block.get("trace_summary")
    if result.explanation:
        trace = {**(trace or {}), "explanation": result.explanation}

    return jsonable_encoder(
        {
            "status": result.status,
            "model_version_requested": result.model_version_requested,
            "model_version_used": result.model_version_used,
            "engine": result.model_engine_name,
            "prediction": result.prediction,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "trace": trace,
            "block": block,
        },
    )
