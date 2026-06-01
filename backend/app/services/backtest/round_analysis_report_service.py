"""Servizio export report JSON Round Analysis."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BacktestRoundAnalysis, BacktestRoundFixtureResult, Competition, Fixture
from app.services.backtest.round_analysis_report_builder import (
    build_fixture_report_payload,
    build_round_report,
)
from app.services.backtest.round_analysis_service import raise_backtest_http


class RoundAnalysisReportService:
    def get_round_report_json(self, db: Session, analysis_id: int) -> dict[str, Any]:
        analysis, fixtures, competition_name, kickoff_map = self._load_analysis_context(
            db,
            analysis_id,
        )
        return build_round_report(
            analysis,
            fixtures,
            competition_name=competition_name,
            kickoff_by_fixture_id=kickoff_map,
        )

    def get_fixture_report_json(
        self,
        db: Session,
        analysis_id: int,
        fixture_id: int,
    ) -> dict[str, Any]:
        analysis, fixtures, competition_name, kickoff_map = self._load_analysis_context(
            db,
            analysis_id,
        )
        row = next((f for f in fixtures if int(f.fixture_id) == int(fixture_id)), None)
        if row is None:
            raise_backtest_http(404, "fixture_not_in_analysis", "Fixture non presente in questa analisi.")
        return build_fixture_report_payload(
            analysis,
            row,
            competition_name=competition_name,
            kickoff_at=kickoff_map.get(int(fixture_id)),
        )

    def _load_analysis_context(
        self,
        db: Session,
        analysis_id: int,
    ) -> tuple[
        BacktestRoundAnalysis,
        list[BacktestRoundFixtureResult],
        str | None,
        dict[int, Any],
    ]:
        analysis = db.get(BacktestRoundAnalysis, int(analysis_id))
        if analysis is None:
            raise_backtest_http(404, "analysis_not_found", "Analisi non trovata.")

        fixtures = list(
            db.scalars(
                select(BacktestRoundFixtureResult)
                .where(BacktestRoundFixtureResult.analysis_id == int(analysis.id))
                .order_by(BacktestRoundFixtureResult.id.asc()),
            ).all(),
        )

        comp = db.get(Competition, int(analysis.competition_id))
        competition_name = comp.name if comp is not None else None

        fixture_ids = [int(f.fixture_id) for f in fixtures]
        kickoff_map: dict[int, Any] = {}
        if fixture_ids:
            for fx in db.scalars(select(Fixture).where(Fixture.id.in_(fixture_ids))).all():
                kickoff_map[int(fx.id)] = fx.kickoff_at

        return analysis, fixtures, competition_name, kickoff_map
