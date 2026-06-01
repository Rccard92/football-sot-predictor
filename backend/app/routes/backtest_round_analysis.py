"""API analisi giornata persistente (Step I)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.backtest_round_analysis import RoundAnalysisAnalyzeRequest
from app.services.backtest.round_analysis_overview_service import RoundAnalysisOverviewService
from app.services.backtest.round_analysis_diagnostics_service import RoundAnalysisDiagnosticsService
from app.services.backtest.round_analysis_report_service import RoundAnalysisReportService
from app.services.backtest.round_analysis_service import RoundAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/round-analysis", tags=["backtest-round-analysis"])

_CONFIG_ERROR_DETAIL = {
    "status": "error",
    "error_code": "ROUND_ANALYSIS_CONFIG_ERROR",
    "error_message": "Configurazione analisi giornata non valida o incompleta.",
}


def _raise_config_error(exc: Exception) -> None:
    logger.exception("Round analysis: errore configurazione")
    raise HTTPException(status_code=500, detail=_CONFIG_ERROR_DETAIL) from exc


@router.post("/analyze")
def round_analysis_analyze(
    body: RoundAnalysisAnalyzeRequest,
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisService()
    try:
        payload = svc.analyze(db, body)
    except HTTPException:
        raise
    except (NameError, TypeError, AttributeError) as exc:
        _raise_config_error(exc)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST round-analysis/analyze: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder({"analysis": payload})


@router.get("")
def round_analysis_list(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="round_number"),
    sort_dir: str = Query(default="desc"),
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisService()
    try:
        payload = svc.list_analyses(
            db,
            competition_id=competition_id,
            season_year=season_year,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/overview")
def round_analysis_overview(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisOverviewService()
    try:
        payload = svc.get_overview(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis/overview: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/overview/report-json")
def round_analysis_overview_report_json(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisOverviewService()
    try:
        payload = svc.get_overview_report_json(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis/overview/report-json: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/overview/report-csv")
def round_analysis_overview_report_csv(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisOverviewService()
    try:
        csv_body = svc.get_overview_report_csv(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis/overview/report-csv: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    filename = f"round-analysis-calibration-{competition_id}-{season_year}.csv"
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/diagnostics")
def round_analysis_diagnostics(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisDiagnosticsService()
    try:
        payload = svc.get_diagnostics(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis/diagnostics: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/diagnostics/report-json")
def round_analysis_diagnostics_report_json(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisDiagnosticsService()
    try:
        payload = svc.get_diagnostics_report_json(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis/diagnostics/report-json: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.post("/{analysis_id}/recalculate")
def round_analysis_recalculate(
    analysis_id: int,
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisService()
    try:
        payload = svc.recalculate(db, analysis_id)
    except HTTPException:
        raise
    except (NameError, TypeError, AttributeError) as exc:
        _raise_config_error(exc)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST round-analysis recalculate: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder({"analysis": payload})


@router.delete("/{analysis_id}")
def round_analysis_delete(
    analysis_id: int,
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisService()
    try:
        payload = svc.delete_analysis(db, analysis_id)
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("DELETE round-analysis: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/{analysis_id}/report-json")
def round_analysis_report_json(
    analysis_id: int,
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisReportService()
    try:
        payload = svc.get_round_report_json(db, analysis_id)
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis report-json: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/{analysis_id}/fixtures/{fixture_id}/report-json")
def round_analysis_fixture_report_json(
    analysis_id: int,
    fixture_id: int,
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisReportService()
    try:
        payload = svc.get_fixture_report_json(db, analysis_id, fixture_id)
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis fixture report-json: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/{analysis_id}")
def round_analysis_detail(
    analysis_id: int,
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisService()
    try:
        payload = svc.get_detail(db, analysis_id)
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis detail: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)
