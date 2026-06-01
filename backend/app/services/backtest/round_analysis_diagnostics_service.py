"""Servizio diagnostica aggregata Round Analysis (solo lettura DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Competition
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.round_analysis_diagnostics_aggregator import build_diagnostics_payload
from app.services.backtest.round_analysis_diagnostics_loader import load_diagnostics_flat_rows


class RoundAnalysisDiagnosticsService:
    def get_diagnostics(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> dict[str, Any]:
        return self._build(db, competition_id, season_year, use_latest_version_per_round, include_all_versions)

    def get_diagnostics_report_json(
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
        flat_rows, model_keys, excluded = load_diagnostics_flat_rows(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
        fixture_ids = {int(r["fixture_id"]) for r in flat_rows}
        round_numbers = {int(r["round_number"]) for r in flat_rows}
        metadata = {
            "competition_id": int(competition_id),
            "competition_name": comp.name if comp else None,
            "season_year": int(season_year),
            "season_label": season_label_from_year(season_year),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analyzed_rounds": len(round_numbers),
            "analyzed_fixtures": len(fixture_ids),
            "analyzed_rows": len(flat_rows),
            "excluded_analysis_ids": excluded,
            "use_latest_version_per_round": use_latest_version_per_round and not include_all_versions,
            "filters_applied": {
                "completed_only": True,
                "completeness_ok": True,
                "fixture_status_ok": True,
                "actual_total_sot_required": True,
                "exclude_failed": True,
            },
        }
        return build_diagnostics_payload(flat_rows, model_keys, metadata=metadata)
