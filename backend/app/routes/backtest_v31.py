"""API dataset calibrazione v3.1 SOT Calibrated Predictor."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.backtest.v31_calibration_dataset_service import V31CalibrationDatasetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/v31", tags=["backtest-v31"])


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


@router.get("/calibration-dataset")
def v31_calibration_dataset(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    use_latest_version_per_round: bool = Query(default=True),
    include_all_versions: bool = Query(default=False),
    max_fixtures: int | None = Query(default=None, ge=1, le=2000),
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
