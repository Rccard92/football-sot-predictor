"""Servizio simulatore calibrazione v3.0 (solo lettura DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Competition
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.round_analysis_calibration_simulator import build_simulator_payload
from app.services.backtest.round_analysis_calibration_simulator_loader import load_simulator_fixtures


class RoundAnalysisCalibrationSimulatorService:
    def get_simulator(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> dict[str, Any]:
        return self._build(db, competition_id, season_year, use_latest_version_per_round, include_all_versions)

    def get_simulator_report_json(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> dict[str, Any]:
        return self._build(db, competition_id, season_year, use_latest_version_per_round, include_all_versions)

    def _build(
        self,
        db: Session,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool,
        include_all_versions: bool,
    ) -> dict[str, Any]:
        comp = db.get(Competition, int(competition_id))
        fixtures, _model_keys, excluded = load_simulator_fixtures(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
        round_numbers = {int(f["round_number"]) for f in fixtures}
        metadata = {
            "competition_id": int(competition_id),
            "competition_name": comp.name if comp else None,
            "season_year": int(season_year),
            "season_label": season_label_from_year(season_year),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analyzed_rounds": len(round_numbers),
            "analyzed_fixtures": len(fixtures),
            "excluded_analysis_ids": excluded,
            "use_latest_version_per_round": use_latest_version_per_round and not include_all_versions,
            "filters_applied": {
                "completed_only": True,
                "completeness_ok": True,
                "fixture_status_ok": True,
                "actual_total_sot_required": True,
                "simulation_only": True,
                "no_model_recalculation": True,
            },
        }
        return build_simulator_payload(fixtures, metadata=metadata)
