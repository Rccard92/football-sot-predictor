"""API dataset calibrazione v3.1 SOT Calibrated Predictor."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.backtest.v31_calibration_dataset_service import V31CalibrationDatasetService
from app.services.backtest.v31_calibration_simulator_service import V31CalibrationSimulatorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/v31", tags=["backtest-v31"])


@router.post("/calibration-dataset/full/build-job")
def v31_full_export_build_job(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    round_from: int | None = Query(default=None, ge=1, le=38),
    round_to: int | None = Query(default=None, ge=1, le=38),
    chunk_part: int | None = Query(default=None, ge=1, le=10),
    chunk_total_parts: int | None = Query(default=None, ge=1, le=10),
    body: dict | None = Body(default=None),
):
    if body:
        competition_id = int(body.get("competition_id", competition_id))
        season_year = int(body.get("season_year", season_year))
        use_latest_version_per_round = bool(
            body.get("use_latest_version_per_round", use_latest_version_per_round),
        )
        include_all_versions = bool(body.get("include_all_versions", include_all_versions))
        if body.get("round_from") is not None:
            round_from = int(body["round_from"])
        if body.get("round_to") is not None:
            round_to = int(body["round_to"])
        if body.get("chunk_part") is not None:
            chunk_part = int(body["chunk_part"])
        if body.get("chunk_total_parts") is not None:
            chunk_total_parts = int(body["chunk_total_parts"])
    svc = V31CalibrationDatasetService()
    return jsonable_encoder(
        svc.start_full_export_job(
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            round_from=round_from,
            round_to=round_to,
            chunk_part=chunk_part,
            chunk_total_parts=chunk_total_parts,
        ),
    )


@router.get("/calibration-dataset/full/build-job/{job_id}")
def v31_full_export_job_status(job_id: str):
    svc = V31CalibrationDatasetService()
    status = svc.get_full_export_job(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail={"error_code": "V31_JOB_NOT_FOUND"})
    return jsonable_encoder(status)


@router.post("/calibration-dataset/full/build-job/{job_id}/cancel")
def v31_full_export_job_cancel(job_id: str):
    svc = V31CalibrationDatasetService()
    return jsonable_encoder(svc.cancel_full_export_job(job_id))


@router.get("/calibration-dataset/full/build-job/{job_id}/download")
def v31_full_export_job_download(job_id: str):
    svc = V31CalibrationDatasetService()
    payload = svc.get_full_export_job_download_payload(job_id)
    job = svc.get_full_export_job(job_id) or {}
    part = job.get("chunk_part")
    rf = job.get("round_from")
    rt = job.get("round_to")
    if part is not None and rf is not None and rt is not None:
        filename = f"v31-calibration-dataset-full-part-{part}-rounds-{rf}-{rt}.json"
    else:
        cid = job.get("competition_id", "x")
        sy = job.get("season_year", "x")
        filename = f"v31-calibration-dataset-full-{cid}-{sy}.json"
    return JSONResponse(
        content=jsonable_encoder(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/calibration-simulator")
def v31_calibration_simulator(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    strategy: str = Query(default="all"),
    include_rows: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    svc = V31CalibrationSimulatorService()
    try:
        payload = svc.run_simulator(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            strategy=strategy,
            include_rows=include_rows,
        )
    except (OperationalError, ProgrammingError):
        logger.exception("GET v31/calibration-simulator database error")
        raise
    return jsonable_encoder(payload)


@router.get("/calibration-simulator/report-json")
def v31_calibration_simulator_report_json(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    strategy: str = Query(default="all"),
    db: Session = Depends(get_db),
):
    svc = V31CalibrationSimulatorService()
    try:
        payload = svc.run_simulator(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            strategy=strategy,
            include_rows=True,
        )
    except (OperationalError, ProgrammingError):
        logger.exception("GET v31/calibration-simulator/report-json database error")
        raise
    filename = f"v31-predictive-simulator-{competition_id}-{season_year}.json"
    return JSONResponse(
        content=jsonable_encoder(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/calibration-dataset/summary")
def v31_calibration_dataset_summary(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    svc = V31CalibrationDatasetService()
    try:
        payload = svc.get_summary(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
    except (OperationalError, ProgrammingError):
        logger.exception("GET v31/calibration-dataset/summary database error")
        raise
    return jsonable_encoder(payload)


@router.get("/calibration-dataset/anti-leakage-report")
def v31_calibration_anti_leakage_report(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    svc = V31CalibrationDatasetService()
    try:
        payload = svc.get_anti_leakage_report(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
    except (OperationalError, ProgrammingError):
        logger.exception("GET v31/calibration-dataset/anti-leakage-report database error")
        raise
    return jsonable_encoder(payload)


@router.get("/calibration-dataset")
def v31_calibration_dataset(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    max_fixtures: int | None = Query(default=None, ge=1, le=2000),
    detail: Literal["standard", "full"] = Query(default="standard"),
    round_from: int | None = Query(default=None, ge=1, le=38),
    round_to: int | None = Query(default=None, ge=1, le=38),
    chunk_part: int | None = Query(default=None, ge=1, le=10),
    chunk_total_parts: int | None = Query(default=None, ge=1, le=10),
    db: Session = Depends(get_db),
):
    svc = V31CalibrationDatasetService()
    try:
        payload = svc.get_dataset(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
            detail=detail,
            round_from=round_from,
            round_to=round_to,
            chunk_part=chunk_part,
            chunk_total_parts=chunk_total_parts,
        )
    except (OperationalError, ProgrammingError):
        logger.exception("GET v31/calibration-dataset database error")
        raise
    return jsonable_encoder(payload)


@router.get("/calibration-dataset.csv")
def v31_calibration_dataset_csv(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    max_fixtures: int | None = Query(default=None, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    svc = V31CalibrationDatasetService()
    try:
        csv_text = svc.get_dataset_csv(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
        )
    except (OperationalError, ProgrammingError):
        logger.exception("GET v31/calibration-dataset.csv database error")
        raise
    filename = f"v31-calibration-dataset-{competition_id}-{season_year}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
