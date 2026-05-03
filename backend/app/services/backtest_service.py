from __future__ import annotations

import math
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Fixture,
    FixtureTeamStat,
    League,
    PredictionBacktest,
    Season,
    TeamSotFeature,
    TeamSotPrediction,
)
from app.services.backtest_signals import actual_over_line, line_hit, line_signal
from app.services.ingestion_service import IngestionService

DEFAULT_BACKTEST_LINES = [2.5, 3.5, 4.5, 5.5, 6.5]


class BacktestService:
    def run_sot_backtest(
        self,
        db: Session,
        season_year: int,
        model_version: str,
        default_lines: list[float] | None = None,
    ) -> tuple[str, int]:
        lines = list(default_lines) if default_lines else list(DEFAULT_BACKTEST_LINES)
        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            raise ValueError("Lega Serie A non trovata")
        season = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season_year),
        )
        if season is None:
            raise ValueError(f"Stagione {season_year} non trovata")

        preds = db.scalars(
            select(TeamSotPrediction)
            .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
            .where(
                Fixture.season_id == season.id,
                TeamSotPrediction.model_version == model_version,
            ),
        ).all()

        if not preds:
            raise ValueError(
                "Nessuna TeamSotPrediction per questa stagione e model_version indicati",
            )

        fixture_ids = list({p.fixture_id for p in preds})

        feat_rows = db.scalars(
            select(TeamSotFeature).where(TeamSotFeature.fixture_id.in_(fixture_ids)),
        ).all()
        feat_actual: dict[tuple[int, int], int | float | None] = {}
        for fr in feat_rows:
            feats = fr.features or {}
            feat_actual[(fr.fixture_id, fr.team_id)] = feats.get("actual_sot")

        stat_rows = db.scalars(
            select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fixture_ids)),
        ).all()
        stat_sot: dict[tuple[int, int], int | None] = {
            (s.fixture_id, s.team_id): s.shots_on_target for s in stat_rows
        }

        fixtures_map = {f.id: f for f in db.scalars(select(Fixture).where(Fixture.id.in_(fixture_ids))).all()}

        batch_id = str(uuid.uuid4())
        n = 0
        try:
            for pred in preds:
                if pred.predicted_sot is None:
                    continue
                actual = feat_actual.get((pred.fixture_id, pred.team_id))
                if actual is None:
                    actual = stat_sot.get((pred.fixture_id, pred.team_id))
                if actual is None:
                    continue

                expected = float(pred.predicted_sot)
                act_f = float(actual)
                abs_err = abs(expected - act_f)
                sq_err = (expected - act_f) ** 2

                fx = fixtures_map.get(pred.fixture_id)
                if fx is None:
                    continue
                side = "home" if fx.home_team_id == pred.team_id else "away"

                line_details: dict[str, Any] = {}
                for lv in lines:
                    lk = str(lv)
                    sig = line_signal(expected, float(lv))
                    ao = actual_over_line(act_f, float(lv))
                    hit = line_hit(sig, ao)
                    line_details[lk] = {
                        "signal": sig,
                        "actual_over": ao,
                        "hit": hit,
                    }

                details: dict[str, Any] = {
                    "model_version": model_version,
                    "lines": line_details,
                    "side": side,
                }

                db.add(
                    PredictionBacktest(
                        batch_id=batch_id,
                        fixture_id=pred.fixture_id,
                        team_id=pred.team_id,
                        predicted_sot=expected,
                        actual_sot=act_f,
                        error=abs_err,
                        squared_error=sq_err,
                        details=details,
                        ingestion_run_id=None,
                    ),
                )
                n += 1
            if n == 0:
                raise ValueError(
                    "Nessun accoppiamento previsione–actual_sot valido "
                    "(verificare team_sot_features e fixture_team_stats).",
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return batch_id, n

    def resolve_batch_id(
        self,
        db: Session,
        season_id: int,
        batch_id: str | None,
    ) -> str | None:
        if batch_id:
            exists = db.scalar(
                select(PredictionBacktest.id)
                .join(Fixture, Fixture.id == PredictionBacktest.fixture_id)
                .where(
                    PredictionBacktest.batch_id == batch_id,
                    Fixture.season_id == season_id,
                )
                .limit(1),
            )
            return batch_id if exists is not None else None

        rows = db.execute(
            select(PredictionBacktest.batch_id, func.max(PredictionBacktest.created_at))
            .join(Fixture, Fixture.id == PredictionBacktest.fixture_id)
            .where(Fixture.season_id == season_id)
            .group_by(PredictionBacktest.batch_id),
        ).all()
        if not rows:
            return None
        return max(rows, key=lambda r: r[1])[0]

    def load_batch_rows(self, db: Session, season_id: int, batch_id: str) -> list[PredictionBacktest]:
        return list(
            db.scalars(
                select(PredictionBacktest)
                .join(Fixture, Fixture.id == PredictionBacktest.fixture_id)
                .where(
                    PredictionBacktest.batch_id == batch_id,
                    Fixture.season_id == season_id,
                ),
            ).all(),
        )

    def aggregate_summary(self, rows: list[PredictionBacktest]) -> dict[str, Any]:
        if not rows:
            return {
                "mae": None,
                "rmse": None,
                "hit_rate": None,
                "no_bet_rate": None,
                "total_predictions": 0,
                "total_line_evaluations": 0,
            }

        n = len(rows)
        mae = sum(r.error or 0.0 for r in rows) / n
        rmse = math.sqrt(sum(r.squared_error for r in rows) / n)

        total_cells = 0
        no_bet_cells = 0
        hit_vals: list[float] = []

        for r in rows:
            d = r.details or {}
            lines = d.get("lines") or {}
            for _lk, cell in lines.items():
                total_cells += 1
                sig = cell.get("signal")
                if sig == "no_bet":
                    no_bet_cells += 1
                    continue
                hit = cell.get("hit")
                if hit is True:
                    hit_vals.append(1.0)
                elif hit is False:
                    hit_vals.append(0.0)

        hit_rate = sum(hit_vals) / len(hit_vals) if hit_vals else None
        no_bet_rate = no_bet_cells / total_cells if total_cells else None

        return {
            "mae": round(mae, 6),
            "rmse": round(rmse, 6),
            "hit_rate": round(hit_rate, 6) if hit_rate is not None else None,
            "no_bet_rate": round(no_bet_rate, 6) if no_bet_rate is not None else None,
            "total_predictions": n,
            "total_line_evaluations": total_cells,
        }

    def aggregate_by_team(self, rows: list[PredictionBacktest]) -> dict[str, dict[str, Any]]:
        by_tid: dict[int, list[PredictionBacktest]] = defaultdict(list)
        for r in rows:
            by_tid[r.team_id].append(r)

        out: dict[str, dict[str, Any]] = {}
        for tid, rs in by_tid.items():
            n = len(rs)
            mae = sum(r.error or 0.0 for r in rs) / n
            rmse = math.sqrt(sum(r.squared_error for r in rs) / n)
            out[str(tid)] = {
                "team_id": tid,
                "n": n,
                "mae": round(mae, 6),
                "rmse": round(rmse, 6),
            }
        return out

    def aggregate_by_side(self, rows: list[PredictionBacktest]) -> dict[str, dict[str, Any]]:
        by_side: dict[str, list[PredictionBacktest]] = defaultdict(list)
        for r in rows:
            side = (r.details or {}).get("side") or "unknown"
            by_side[str(side)].append(r)

        out: dict[str, Any] = {}
        for side, rs in by_side.items():
            n = len(rs)
            mae = sum(r.error or 0.0 for r in rs) / n
            rmse = math.sqrt(sum(r.squared_error for r in rs) / n)
            out[side] = {"n": n, "mae": round(mae, 6), "rmse": round(rmse, 6)}
        return out

    def aggregate_by_line(self, rows: list[PredictionBacktest]) -> dict[str, dict[str, Any]]:
        by_line: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "line": 0.0,
                "total_evaluations": 0,
                "no_bet_count": 0,
                "decision_count": 0,
                "hits": 0,
                "misses": 0,
            },
        )

        for r in rows:
            d = r.details or {}
            lines = d.get("lines") or {}
            for lk, cell in lines.items():
                bucket = by_line[lk]
                bucket["line"] = float(lk)
                bucket["total_evaluations"] += 1
                sig = cell.get("signal")
                if sig == "no_bet":
                    bucket["no_bet_count"] += 1
                    continue
                bucket["decision_count"] += 1
                hit = cell.get("hit")
                if hit is True:
                    bucket["hits"] += 1
                elif hit is False:
                    bucket["misses"] += 1

        out: dict[str, dict[str, Any]] = {}
        for lk, b in by_line.items():
            dec = b["decision_count"]
            tot = b["total_evaluations"]
            out[lk] = {
                "line": b["line"],
                "total_evaluations": tot,
                "no_bet_count": b["no_bet_count"],
                "no_bet_rate": round(b["no_bet_count"] / tot, 6) if tot else None,
                "decision_count": dec,
                "hit_rate": round(b["hits"] / dec, 6) if dec else None,
                "hits": b["hits"],
                "misses": b["misses"],
            }
        return out
