"""Service API dataset calibrazione v3.1."""

from __future__ import annotations

import logging
import time
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.backtest.v31_calibration_anti_leakage import build_anti_leakage_report_payload
from app.services.backtest.v31_calibration_csv_export import dataset_to_csv_text
from app.services.backtest.v31_calibration_dataset_builder import (
    DetailLevel,
    build_v31_calibration_dataset,
    build_v31_dataset_rows_standard,
)

logger = logging.getLogger(__name__)


class V31AntiLeakageFailedError(HTTPException):
    def __init__(self, anti: dict) -> None:
        super().__init__(
            status_code=422,
            detail={
                "error_code": "V31_ANTI_LEAKAGE_FAILED",
                "error_message": (
                    "Dataset non esportabile: campi vietati presenti nelle feature di training."
                ),
                "anti_leakage_check": anti,
            },
        )


class V31CalibrationDatasetService:
    def get_summary(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> dict:
        from app.services.backtest.v31_calibration_dataset_summary import (
            build_v31_calibration_summary,
        )

        return build_v31_calibration_summary(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )

    def get_anti_leakage_report(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> dict:
        rows, _excluded, _max_round = build_v31_dataset_rows_standard(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
        return build_anti_leakage_report_payload(
            rows,
            competition_id=competition_id,
            season_year=season_year,
        )

    def get_dataset(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
        max_fixtures: int | None = None,
        detail: DetailLevel = "standard",
    ) -> dict:
        payload = build_v31_calibration_dataset(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
            detail=detail,
        )
        anti = payload.get("anti_leakage_check") or {}
        if anti.get("status") != "ok":
            raise V31AntiLeakageFailedError(anti)
        return payload

    def get_dataset_csv(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
        max_fixtures: int | None = None,
    ) -> str:
        logger.info(
            "V31_DATASET_EXPORT_START format=csv detail=standard competition_id=%s season_year=%s",
            competition_id,
            season_year,
        )
        t0 = time.perf_counter()
        rows, _excluded, _max_round = build_v31_dataset_rows_standard(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
        )
        from app.services.backtest.v31_calibration_anti_leakage import validate_v31_rows

        anti = validate_v31_rows(rows)
        if anti.get("status") != "ok":
            raise V31AntiLeakageFailedError(anti)

        payload = {
            "report_type": "v31_calibration_dataset",
            "fixtures_count": len(rows),
            "detail": "standard",
            "rows": rows,
            "anti_leakage_check": anti,
        }
        csv_text = dataset_to_csv_text(payload)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "V31_DATASET_EXPORT_DONE format=csv detail=standard rows=%s duration_ms=%s",
            len(rows),
            duration_ms,
        )
        return csv_text
