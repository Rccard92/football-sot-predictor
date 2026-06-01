"""Servizio overview aggregato Round Analysis (solo lettura DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import BacktestRoundAnalysis, BacktestRoundFixtureResult
from app.schemas.backtest_round_analysis import DEFAULT_ROUND_ANALYSIS_MODELS, season_label_from_year
from app.services.backtest.round_analysis_overview_aggregator import build_overview_payload
from app.services.backtest.round_analysis_calibration_export import (
    build_calibration_csv,
    build_calibration_report,
)

COMPLETED_STATUSES = frozenset({"completed", "completed_with_warnings"})


class RoundAnalysisOverviewService:
    def get_overview(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> dict[str, Any]:
        analyses = self._select_analyses(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
        fixtures_by_id = self._load_fixtures_by_analysis(db, [int(a.id) for a in analyses])
        model_keys = self._model_keys_from_analyses(analyses)
        return build_overview_payload(
            competition_id=competition_id,
            season_year=season_year,
            season_label=season_label_from_year(season_year),
            use_latest_version_per_round=use_latest_version_per_round and not include_all_versions,
            model_keys=model_keys,
            analyses=analyses,
            fixtures_by_analysis_id=fixtures_by_id,
        )

    def get_overview_report_json(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> dict[str, Any]:
        return build_calibration_report(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )

    def get_overview_report_csv(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> str:
        return build_calibration_csv(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )

    def _select_analyses(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool,
        include_all_versions: bool,
    ) -> list[BacktestRoundAnalysis]:
        rows = (
            db.query(BacktestRoundAnalysis)
            .filter(
                BacktestRoundAnalysis.competition_id == competition_id,
                BacktestRoundAnalysis.season_year == season_year,
                BacktestRoundAnalysis.status.in_(COMPLETED_STATUSES),
            )
            .all()
        )
        if include_all_versions or not use_latest_version_per_round:
            return sorted(rows, key=lambda r: (int(r.round_number), int(r.analysis_version)))
        by_round: dict[int, BacktestRoundAnalysis] = {}
        for row in rows:
            rn = int(row.round_number)
            prev = by_round.get(rn)
            if prev is None or int(row.analysis_version) > int(prev.analysis_version):
                by_round[rn] = row
        return sorted(by_round.values(), key=lambda r: int(r.round_number))

    def _load_fixtures_by_analysis(
        self,
        db: Session,
        analysis_ids: list[int],
    ) -> dict[int, list[BacktestRoundFixtureResult]]:
        if not analysis_ids:
            return {}
        rows = (
            db.query(BacktestRoundFixtureResult)
            .filter(BacktestRoundFixtureResult.analysis_id.in_(analysis_ids))
            .all()
        )
        out: dict[int, list[BacktestRoundFixtureResult]] = {}
        for row in rows:
            aid = int(row.analysis_id)
            out.setdefault(aid, []).append(row)
        return out

    def _model_keys_from_analyses(self, analyses: list[BacktestRoundAnalysis]) -> list[str]:
        keys: list[str] = []
        for analysis in analyses:
            cfg = dict(analysis.config_json or {})
            for k in cfg.get("models") or DEFAULT_ROUND_ANALYSIS_MODELS:
                if k not in keys:
                    keys.append(str(k))
        return keys or list(DEFAULT_ROUND_ANALYSIS_MODELS)
