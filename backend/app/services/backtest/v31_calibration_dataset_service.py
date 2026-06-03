"""Service API dataset calibrazione v3.1."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.backtest.v31_calibration_csv_export import dataset_to_csv_text
from app.services.backtest.v31_calibration_dataset_builder import build_v31_calibration_dataset


class V31CalibrationDatasetService:
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
        return build_v31_calibration_dataset(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
        )

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
        payload = self.get_dataset(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
        )
        return dataset_to_csv_text(payload)
