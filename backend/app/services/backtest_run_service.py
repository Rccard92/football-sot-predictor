"""Service CRUD backtest_runs — Step C (nessun motore di calcolo)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.algorithms.registry import get_algorithm
from app.backtest.constants import (
    BACKTEST_FIXTURE_SCOPE_CUSTOM_RANGE,
    BACKTEST_FIXTURE_SCOPES,
    BACKTEST_MODES,
    BACKTEST_STATUS_PENDING,
)
from app.backtest.errors import raise_backtest_http
from app.backtest.git_info import resolve_git_commit_sha
from app.markets.registry import MarketSpec, get_market
from app.models import BacktestPick, BacktestPrediction, BacktestRun, BacktestRunMetric, Competition, Season
from app.schemas.backtest_runs import BacktestRunCreateRequest, BacktestRunFilters
from app.services.competition_service import CompetitionService


@dataclass(frozen=True)
class BacktestRunDetail:
    run: BacktestRun
    competition_name: str | None
    predictions_count: int
    picks_count: int
    metrics_count: int


class BacktestRunService:
    def validate_market_and_algorithm(self, market_key: str, algorithm_version: str) -> MarketSpec:
        market = get_market(market_key)
        if market is None:
            raise_backtest_http(
                422,
                "invalid_market_key",
                "Market non riconosciuto.",
                market_key=market_key,
            )
        if market.status != "active":
            raise_backtest_http(
                422,
                "market_not_active",
                "Market registrato ma non ancora attivo per backtest runtime.",
                market_key=market_key,
            )
        algo = get_algorithm(algorithm_version)
        if algo is None or algo.market_key != market_key:
            raise_backtest_http(
                422,
                "invalid_algorithm_for_market",
                "Algorithm non valido per il market selezionato.",
                market_key=market_key,
                algorithm_version=algorithm_version,
            )
        return market

    def compute_algorithm_config_hash(
        self,
        *,
        market: MarketSpec,
        market_key: str,
        algorithm_version: str,
        mode: str,
        fixture_scope: str,
        season_year: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
        config_json: dict[str, Any],
    ) -> str:
        default_lines = config_json.get("default_ou_lines")
        if default_lines is None:
            default_lines = list(market.default_lines)
        payload = {
            "market_key": market_key,
            "algorithm_version": algorithm_version,
            "mode": mode,
            "fixture_scope": fixture_scope,
            "season_year": season_year,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "config_json": config_json,
            "default_ou_lines": default_lines,
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _validate_create_fields(
        self,
        payload: BacktestRunCreateRequest,
        *,
        market: MarketSpec,
    ) -> None:
        if payload.mode not in BACKTEST_MODES:
            raise_backtest_http(
                422,
                "invalid_mode",
                "Mode non valido.",
                mode=payload.mode,
            )
        if payload.fixture_scope not in BACKTEST_FIXTURE_SCOPES:
            raise_backtest_http(
                422,
                "invalid_fixture_scope",
                "Fixture scope non valido.",
                fixture_scope=payload.fixture_scope,
            )
        if payload.fixture_scope == BACKTEST_FIXTURE_SCOPE_CUSTOM_RANGE:
            if payload.date_from is None or payload.date_to is None:
                raise_backtest_http(
                    422,
                    "missing_custom_range_dates",
                    "date_from e date_to sono obbligatori per fixture_scope custom_range.",
                    fixture_scope=payload.fixture_scope,
                )
        if payload.date_from is not None and payload.date_to is not None:
            if payload.date_from > payload.date_to:
                raise_backtest_http(
                    422,
                    "invalid_date_range",
                    "date_from non può essere successivo a date_to.",
                )

    def create_run(self, db: Session, payload: BacktestRunCreateRequest) -> BacktestRun:
        comp = CompetitionService().get_by_id(db, payload.competition_id)
        if comp is None:
            raise_backtest_http(
                404,
                "competition_not_found",
                "Competition non trovata.",
                competition_id=payload.competition_id,
            )

        market = self.validate_market_and_algorithm(payload.market_key, payload.algorithm_version)
        self._validate_create_fields(payload, market=market)

        season_year = payload.season_year if payload.season_year is not None else comp.season

        if payload.season_id is not None:
            season_row = db.get(Season, int(payload.season_id))
            if season_row is None:
                raise_backtest_http(
                    422,
                    "invalid_season_id",
                    "Season non trovata.",
                    season_id=payload.season_id,
                )

        config_json = dict(payload.config_json) if payload.config_json else {}
        algo_hash = self.compute_algorithm_config_hash(
            market=market,
            market_key=payload.market_key,
            algorithm_version=payload.algorithm_version,
            mode=payload.mode,
            fixture_scope=payload.fixture_scope,
            season_year=season_year,
            date_from=payload.date_from,
            date_to=payload.date_to,
            config_json=config_json,
        )

        run = BacktestRun(
            competition_id=int(comp.id),
            season_id=payload.season_id,
            season_year=season_year,
            market_key=payload.market_key,
            algorithm_version=payload.algorithm_version,
            mode=payload.mode,
            fixture_scope=payload.fixture_scope,
            date_from=payload.date_from,
            date_to=payload.date_to,
            status=BACKTEST_STATUS_PENDING,
            config_json=config_json,
            summary_json=None,
            error_json=None,
            algorithm_config_hash=algo_hash,
            model_manifest_version=payload.model_manifest_version,
            git_commit_sha=resolve_git_commit_sha(),
            completed_at=None,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _apply_filters(self, q, filters: BacktestRunFilters):
        if filters.competition_id is not None:
            q = q.where(BacktestRun.competition_id == int(filters.competition_id))
        if filters.season_year is not None:
            q = q.where(BacktestRun.season_year == int(filters.season_year))
        if filters.market_key is not None:
            q = q.where(BacktestRun.market_key == str(filters.market_key))
        if filters.algorithm_version is not None:
            q = q.where(BacktestRun.algorithm_version == str(filters.algorithm_version))
        if filters.mode is not None:
            q = q.where(BacktestRun.mode == str(filters.mode))
        if filters.status is not None:
            q = q.where(BacktestRun.status == str(filters.status))
        return q

    def list_runs(
        self,
        db: Session,
        filters: BacktestRunFilters,
    ) -> tuple[list[tuple[BacktestRun, str | None]], int]:
        count_q = self._apply_filters(select(func.count()).select_from(BacktestRun), filters)
        total = int(db.scalar(count_q) or 0)

        rows_q = (
            self._apply_filters(
                select(BacktestRun, Competition.name).outerjoin(
                    Competition,
                    Competition.id == BacktestRun.competition_id,
                ),
                filters,
            )
            .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )
        rows = list(db.execute(rows_q).all())
        return [(row[0], row[1]) for row in rows], total

    def get_run(self, db: Session, run_id: int) -> BacktestRunDetail | None:
        row = db.execute(
            select(BacktestRun, Competition.name)
            .outerjoin(Competition, Competition.id == BacktestRun.competition_id)
            .where(BacktestRun.id == int(run_id)),
        ).first()
        if row is None:
            return None
        run, competition_name = row[0], row[1]
        predictions_count = int(
            db.scalar(
                select(func.count())
                .select_from(BacktestPrediction)
                .where(BacktestPrediction.backtest_run_id == run.id),
            )
            or 0,
        )
        picks_count = int(
            db.scalar(
                select(func.count()).select_from(BacktestPick).where(BacktestPick.backtest_run_id == run.id),
            )
            or 0,
        )
        metrics_count = int(
            db.scalar(
                select(func.count())
                .select_from(BacktestRunMetric)
                .where(BacktestRunMetric.backtest_run_id == run.id),
            )
            or 0,
        )
        return BacktestRunDetail(
            run=run,
            competition_name=competition_name,
            predictions_count=predictions_count,
            picks_count=picks_count,
            metrics_count=metrics_count,
        )
