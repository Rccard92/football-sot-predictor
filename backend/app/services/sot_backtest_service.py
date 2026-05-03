from __future__ import annotations

import logging
import math
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import BASELINE_SOT_MODEL_VERSION
from app.models import Fixture, League, PredictionBacktest, Season, Team, TeamSotPrediction

logger = logging.getLogger(__name__)

NOT_EVALUATED = "not_evaluated"


class SotBacktestService:
    """Backtest numerico expected_sot vs actual_sot (nessuna linea bookmaker)."""

    def _season_row(self, db: Session, season_year: int) -> tuple[League, Season]:
        settings = get_settings()
        league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError(f"Lega con api_league_id={settings.default_league_id} non trovata")
        season = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season_year),
        )
        if season is None:
            raise ValueError(f"Stagione non trovata per year={season_year}")
        return league, season

    def count_predictions_with_actual(
        self,
        db: Session,
        season_id: int,
        model_version: str,
    ) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
                .where(
                    Fixture.season_id == season_id,
                    TeamSotPrediction.model_version == model_version,
                    TeamSotPrediction.actual_sot.isnot(None),
                    TeamSotPrediction.predicted_sot.isnot(None),
                ),
            )
            or 0,
        )

    def run_numeric_backtest_admin(
        self,
        db: Session,
        season_year: int,
        model_version: str = BASELINE_SOT_MODEL_VERSION,
    ) -> dict[str, Any]:
        from app.services.ingestion_service import IngestionService

        summary: dict[str, Any] = {
            "status": "pending",
            "season": season_year,
            "model_version": model_version,
            "predictions_total": 0,
            "backtests_created_or_updated": 0,
            "mae": 0.0,
            "rmse": 0.0,
            "avg_expected_sot": 0.0,
            "avg_actual_sot": 0.0,
            "errors": [],
        }

        ing = IngestionService()
        run = ing._begin_run(
            db,
            "run_sot_backtest",
            meta={"season": season_year, "model_version": model_version},
        )

        try:
            _league, season = self._season_row(db, season_year)
        except ValueError as exc:
            logger.warning("run_sot_backtest: %s", exc)
            summary["status"] = "error"
            summary["message"] = str(exc)
            ing._finish_run(
                db,
                run,
                success=False,
                records_processed=0,
                error=str(exc),
                meta_merge={"summary": summary},
            )
            summary["ingestion_run_id"] = run.id
            return summary

        preds = db.scalars(
            select(TeamSotPrediction)
            .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
            .where(
                Fixture.season_id == season.id,
                TeamSotPrediction.model_version == model_version,
                TeamSotPrediction.actual_sot.isnot(None),
                TeamSotPrediction.predicted_sot.isnot(None),
            ),
        ).all()

        summary["predictions_total"] = len(preds)
        if not preds:
            summary["status"] = "success"
            ing._finish_run(db, run, success=True, records_processed=0, meta_merge={"summary": summary})
            summary["ingestion_run_id"] = run.id
            return summary

        fixture_ids = {p.fixture_id for p in preds}
        fixtures_map = {
            f.id: f
            for f in db.scalars(select(Fixture).where(Fixture.id.in_(fixture_ids))).all()
        }

        n_ok = 0
        sum_abs = 0.0
        sum_sq = 0.0
        sum_exp = 0.0
        sum_act = 0.0

        for pred in preds:
            try:
                expected = float(pred.predicted_sot)
                act_f = float(pred.actual_sot)
                abs_err = abs(expected - act_f)
                sq_err = (expected - act_f) ** 2

                fx = fixtures_map.get(pred.fixture_id)
                if fx is None:
                    raise ValueError("fixture non trovata")
                side = "home" if fx.home_team_id == pred.team_id else "away"

                existing = db.scalar(
                    select(PredictionBacktest).where(
                        PredictionBacktest.fixture_id == pred.fixture_id,
                        PredictionBacktest.team_id == pred.team_id,
                        PredictionBacktest.model_version == model_version,
                    ),
                )

                details = {
                    "confidence_score": pred.confidence_score,
                }

                if existing is None:
                    row = PredictionBacktest(
                        batch_id=None,
                        fixture_id=pred.fixture_id,
                        team_id=pred.team_id,
                        model_version=model_version,
                        prediction_id=pred.id,
                        side=side,
                        line_value=None,
                        predicted_side=NOT_EVALUATED,
                        actual_side=NOT_EVALUATED,
                        is_correct=None,
                        predicted_sot=expected,
                        actual_sot=act_f,
                        error=abs_err,
                        squared_error=sq_err,
                        details=details,
                        ingestion_run_id=run.id,
                    )
                    db.add(row)
                else:
                    existing.batch_id = None
                    existing.prediction_id = pred.id
                    existing.side = side
                    existing.line_value = None
                    existing.predicted_side = NOT_EVALUATED
                    existing.actual_side = NOT_EVALUATED
                    existing.is_correct = None
                    existing.predicted_sot = expected
                    existing.actual_sot = act_f
                    existing.error = abs_err
                    existing.squared_error = sq_err
                    existing.details = details
                    existing.ingestion_run_id = run.id

                db.flush()
                n_ok += 1
                sum_abs += abs_err
                sum_sq += sq_err
                sum_exp += expected
                sum_act += act_f
            except Exception as exc:
                logger.exception(
                    "run_sot_backtest: errore prediction_id=%s fixture_id=%s team_id=%s",
                    pred.id,
                    pred.fixture_id,
                    pred.team_id,
                )
                summary["errors"].append(
                    {
                        "prediction_id": pred.id,
                        "fixture_id": pred.fixture_id,
                        "team_id": pred.team_id,
                        "message": str(exc),
                    },
                )

        try:
            db.commit()
            if n_ok:
                summary["mae"] = round(sum_abs / n_ok, 6)
                summary["rmse"] = round(math.sqrt(sum_sq / n_ok), 6)
                summary["avg_expected_sot"] = round(sum_exp / n_ok, 6)
                summary["avg_actual_sot"] = round(sum_act / n_ok, 6)
            summary["status"] = "success"
            summary["backtests_created_or_updated"] = n_ok
            ing._finish_run(
                db,
                run,
                success=True,
                records_processed=n_ok,
                meta_merge={"summary": {k: v for k, v in summary.items() if k != "status"}},
            )
        except Exception as exc:
            logger.exception("run_sot_backtest: commit fallito")
            db.rollback()
            summary["status"] = "error"
            summary["message"] = str(exc)
            try:
                ing._finish_run(
                    db,
                    run,
                    success=False,
                    records_processed=n_ok,
                    error=str(exc),
                    meta_merge={"summary": {k: v for k, v in summary.items() if k != "status"}},
                )
            except Exception:
                logger.exception("run_sot_backtest: impossibile finalizzare ingestion_run")

        summary["ingestion_run_id"] = run.id
        return summary

    def get_season_summary(
        self,
        db: Session,
        season_year: int,
        model_version: str = BASELINE_SOT_MODEL_VERSION,
    ) -> dict[str, Any]:
        try:
            _league, season = self._season_row(db, season_year)
        except ValueError:
            return {
                "season": season_year,
                "model_version": model_version,
                "predictions_total": 0,
                "backtests_total": 0,
                "coverage_pct": 0.0,
                "mae": 0.0,
                "rmse": 0.0,
                "avg_expected_sot": 0.0,
                "avg_actual_sot": 0.0,
                "avg_absolute_error": 0.0,
                "max_absolute_error": 0.0,
            }

        predictions_total = self.count_predictions_with_actual(db, season.id, model_version)

        stats = db.execute(
            select(
                func.count(PredictionBacktest.id),
                func.avg(PredictionBacktest.error),
                func.max(PredictionBacktest.error),
                func.avg(PredictionBacktest.squared_error),
                func.avg(PredictionBacktest.predicted_sot),
                func.avg(PredictionBacktest.actual_sot),
            )
            .join(Fixture, Fixture.id == PredictionBacktest.fixture_id)
            .where(
                Fixture.season_id == season.id,
                PredictionBacktest.model_version == model_version,
            ),
        ).one()

        backtests_total = int(stats[0] or 0)
        avg_abs = float(stats[1] or 0.0)
        max_abs = float(stats[2] or 0.0)
        avg_sq = float(stats[3] or 0.0)
        avg_exp = float(stats[4] or 0.0)
        avg_act = float(stats[5] or 0.0)

        rmse = math.sqrt(avg_sq) if avg_sq > 0 else 0.0
        coverage = (
            round(100.0 * backtests_total / predictions_total, 2) if predictions_total else 0.0
        )

        return {
            "season": season_year,
            "model_version": model_version,
            "predictions_total": predictions_total,
            "backtests_total": backtests_total,
            "coverage_pct": coverage,
            "mae": round(avg_abs, 6),
            "rmse": round(rmse, 6),
            "avg_expected_sot": round(avg_exp, 6),
            "avg_actual_sot": round(avg_act, 6),
            "avg_absolute_error": round(avg_abs, 6),
            "max_absolute_error": round(max_abs, 6),
        }

    def get_by_team(
        self,
        db: Session,
        season_year: int,
        model_version: str = BASELINE_SOT_MODEL_VERSION,
    ) -> list[dict[str, Any]]:
        try:
            _league, season = self._season_row(db, season_year)
        except ValueError:
            return []

        rows = db.execute(
            select(
                PredictionBacktest.team_id,
                func.count(PredictionBacktest.id),
                func.avg(PredictionBacktest.predicted_sot),
                func.avg(PredictionBacktest.actual_sot),
                func.avg(PredictionBacktest.error),
                func.max(PredictionBacktest.error),
                func.avg(PredictionBacktest.squared_error),
            )
            .join(Fixture, Fixture.id == PredictionBacktest.fixture_id)
            .where(
                Fixture.season_id == season.id,
                PredictionBacktest.model_version == model_version,
            )
            .group_by(PredictionBacktest.team_id),
        ).all()

        team_ids = [r[0] for r in rows]
        names = {}
        if team_ids:
            for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all():
                names[t.id] = t.name

        out: list[dict[str, Any]] = []
        for r in rows:
            tid, n, avg_e, avg_a, mae, max_abs, avg_sq = r
            n_int = int(n or 0)
            rmse = math.sqrt(float(avg_sq or 0.0))
            out.append(
                {
                    "team_id": int(tid),
                    "team_name": names.get(int(tid), ""),
                    "predictions_count": n_int,
                    "avg_expected_sot": round(float(avg_e or 0.0), 6),
                    "avg_actual_sot": round(float(avg_a or 0.0), 6),
                    "mae": round(float(mae or 0.0), 6),
                    "rmse": round(rmse, 6),
                    "max_absolute_error": round(float(max_abs or 0.0), 6),
                },
            )

        out.sort(key=lambda x: x["mae"], reverse=True)
        return out

    def get_by_side(
        self,
        db: Session,
        season_year: int,
        model_version: str = BASELINE_SOT_MODEL_VERSION,
    ) -> list[dict[str, Any]]:
        try:
            _league, season = self._season_row(db, season_year)
        except ValueError:
            return []

        rows = db.execute(
            select(
                PredictionBacktest.side,
                func.count(PredictionBacktest.id),
                func.avg(PredictionBacktest.predicted_sot),
                func.avg(PredictionBacktest.actual_sot),
                func.avg(PredictionBacktest.error),
                func.avg(PredictionBacktest.squared_error),
            )
            .join(Fixture, Fixture.id == PredictionBacktest.fixture_id)
            .where(
                Fixture.season_id == season.id,
                PredictionBacktest.model_version == model_version,
                PredictionBacktest.side.isnot(None),
            )
            .group_by(PredictionBacktest.side),
        ).all()

        by_side: dict[str, dict[str, Any]] = {}
        for r in rows:
            side_key = str(r[0] or "unknown")
            n = int(r[1] or 0)
            avg_sq = float(r[5] or 0.0)
            by_side[side_key] = {
                "side": side_key,
                "predictions_count": n,
                "avg_expected_sot": round(float(r[2] or 0.0), 6),
                "avg_actual_sot": round(float(r[3] or 0.0), 6),
                "mae": round(float(r[4] or 0.0), 6),
                "rmse": round(math.sqrt(avg_sq), 6) if avg_sq > 0 else 0.0,
            }

        order = ["home", "away", "unknown"]
        return [by_side[k] for k in order if k in by_side] + [
            by_side[k] for k in sorted(by_side.keys()) if k not in order
        ]

    def get_fixture_comparison(
        self,
        db: Session,
        fixture_id: int,
        model_version: str = BASELINE_SOT_MODEL_VERSION,
    ) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(PredictionBacktest)
            .where(
                PredictionBacktest.fixture_id == fixture_id,
                PredictionBacktest.model_version == model_version,
            )
            .order_by(PredictionBacktest.side.desc().nulls_last(), PredictionBacktest.team_id.asc()),
        ).all()

        out: list[dict[str, Any]] = []
        for r in rows:
            team = db.get(Team, r.team_id)
            conf = r.details.get("confidence_score") if isinstance(r.details, dict) else None
            if conf is None and r.prediction_id:
                p = db.get(TeamSotPrediction, r.prediction_id)
                if p:
                    conf = p.confidence_score
            out.append(
                {
                    "team_name": team.name if team else "",
                    "side": r.side or "",
                    "expected_sot": r.predicted_sot,
                    "actual_sot": r.actual_sot,
                    "absolute_error": r.error,
                    "confidence_score": conf,
                },
            )
        return out

    def get_dashboard_backtest_block(
        self,
        db: Session,
        season_year: int,
        model_version: str = BASELINE_SOT_MODEL_VERSION,
    ) -> dict[str, Any]:
        sm = self.get_season_summary(db, season_year, model_version)
        return {
            "sot_backtests_total": sm["backtests_total"],
            "sot_backtests_expected": sm["predictions_total"],
            "sot_backtest_coverage_pct": float(sm["coverage_pct"]),
            "sot_backtest_mae": float(sm["mae"]),
            "sot_backtest_rmse": float(sm["rmse"]),
            "sot_backtest_avg_expected_sot": float(sm["avg_expected_sot"]),
            "sot_backtest_avg_actual_sot": float(sm["avg_actual_sot"]),
        }
