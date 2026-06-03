"""Service API dataset calibrazione v3.1."""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.services.backtest.v31_calibration_csv_export import dataset_to_csv_text
from app.services.backtest.v31_calibration_dataset_builder import build_v31_calibration_dataset
from app.services.backtest.v31_calibration_dataset_summary import build_v31_calibration_summary

logger = logging.getLogger(__name__)


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
        return build_v31_calibration_summary(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
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
    ) -> dict:
        logger.info(
            "V31_DATASET_EXPORT_START format=json competition_id=%s season_year=%s",
            competition_id,
            season_year,
        )
        t0 = time.perf_counter()
        payload = build_v31_calibration_dataset(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        rows = len(payload.get("rows") or [])
        logger.info(
            "V31_DATASET_EXPORT_DONE format=json rows=%s duration_ms=%s",
            rows,
            duration_ms,
        )
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
            "V31_DATASET_EXPORT_START format=csv competition_id=%s season_year=%s",
            competition_id,
            season_year,
        )
        t0 = time.perf_counter()
        payload = build_v31_calibration_dataset(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
        )
        csv_text = dataset_to_csv_text(payload)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "V31_DATASET_EXPORT_DONE format=csv rows=%s duration_ms=%s",
            len(payload.get("rows") or []),
            duration_ms,
        )
        return csv_text
