"""Esecuzione della Fase 1 in background (riga di stato su DB + thread),
con lo stesso schema dei job gia' usati da Pattern Insights."""

from __future__ import annotations

import logging
import math
import threading
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_v3 import (
    V3_ACTIVE_STATUSES,
    V3_STATUS_CANCELLED,
    V3_STATUS_COMPLETED,
    V3_STATUS_FAILED,
    V3_STATUS_PENDING,
    V3_STATUS_RUNNING,
    CecchinoV3MarketPrediction,
    CecchinoV3MatchPrediction,
    CecchinoV3Run,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields
from app.services.cecchino_v3.constants import (
    COUNTRY_GROUPS,
    DEFAULT_HYPER,
    ENGINE_VERSION,
    FINAL_PHASE_MATCHES,
    HYPER_GRID,
    JUDGE_SEASONS,
    LOCKBOX,
    MARKET_KEYS,
    MIN_MATCHES_PLAYED,
    WARMUP_SEASON,
    Hyper,
)
from app.services.cecchino_v3.data import MatchRecord, group_matches, load_matches
from app.services.cecchino_v3.markets import market_outcomes, market_probabilities, score_matrix
from app.services.cecchino_v3.walkforward import StrengthPrediction, run_group

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}

_INSERT_CHUNK = 2000
_CANCEL_CHECK_SECONDS = 5.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _d(value: float, places: int) -> Decimal:
    return Decimal(str(round(float(value), places)))


def run_to_dict(run: CecchinoV3Run) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "engine_version": run.engine_version,
        "status": run.status,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "progress_pct": float(run.progress_pct) if run.progress_pct is not None else None,
        "current_step": run.current_step,
        "config": run.config_json,
        "summary": run.summary_json,
        "error": run.error_json,
        "source_git_commit": run.source_git_commit,
    }


def _config() -> dict[str, Any]:
    return {
        "engine_version": ENGINE_VERSION,
        "warmup_season": WARMUP_SEASON,
        "judge_seasons": list(JUDGE_SEASONS),
        "lockbox_season": LOCKBOX,
        "min_matches_played": MIN_MATCHES_PLAYED,
        "final_phase_matches": FINAL_PHASE_MATCHES,
        "hyper_grid": [{"xi": h.xi, "sigma": h.sigma} for h in HYPER_GRID],
        "default_hyper": {"xi": DEFAULT_HYPER.xi, "sigma": DEFAULT_HYPER.sigma},
        "hyper_selection": "per stagione S: griglia con log-loss 1X2 minima sulla stagione S-1 (partite idonee)",
        "country_groups": {k: list(v) for k, v in COUNTRY_GROUPS.items()},
    }


def start_run(db: Session) -> dict[str, Any]:
    active = db.scalars(
        select(CecchinoV3Run).where(CecchinoV3Run.status.in_(V3_ACTIVE_STATUSES))
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste gia' un calcolo V3 in corso (id={active.id})",
            status_code=409,
        )
    run = CecchinoV3Run(
        engine_version=ENGINE_VERSION,
        status=V3_STATUS_PENDING,
        requested_at=_utcnow(),
        config_json=_config(),
        source_git_commit=revision_as_source_fields().get("source_git_commit"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    _spawn_worker(int(run.id))
    return run_to_dict(run)


def get_run(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoV3Run, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Calcolo V3 non trovato", status_code=404)
    return run_to_dict(run)


def latest_run(db: Session) -> CecchinoV3Run | None:
    return db.scalars(select(CecchinoV3Run).order_by(CecchinoV3Run.id.desc())).first()


def latest_completed_run(db: Session) -> CecchinoV3Run | None:
    return db.scalars(
        select(CecchinoV3Run)
        .where(CecchinoV3Run.status == V3_STATUS_COMPLETED)
        .order_by(CecchinoV3Run.completed_at.desc())
    ).first()


def cancel_run(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoV3Run, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Calcolo V3 non trovato", status_code=404)
    if run.status in V3_ACTIVE_STATUSES:
        run.cancel_requested = True
        db.commit()
    return run_to_dict(run)


def _spawn_worker(run_id: int) -> None:
    with _lock:
        existing = _active_threads.get(run_id)
        if existing and existing.is_alive():
            return
        t = threading.Thread(
            target=_execute_run, args=(run_id,), name=f"cecchino-v3-run-{run_id}", daemon=True
        )
        _active_threads[run_id] = t
        t.start()


# --- scelta iperparametri -------------------------------------------------------


def _one_x_two_log_loss(match: MatchRecord, pred: StrengthPrediction) -> float:
    m = score_matrix(pred.lambda_home, pred.lambda_away, pred.rho)
    if match.ft_home > match.ft_away:
        p = float(np.tril(m, -1).sum())
    elif match.ft_home == match.ft_away:
        p = float(np.trace(m))
    else:
        p = float(np.triu(m, 1).sum())
    return -math.log(max(p, 1e-9))


def select_hypers(
    matches: list[MatchRecord],
    predictions: dict[str, dict[int, StrengthPrediction]],
) -> tuple[dict[str, Hyper], dict[str, dict[str, Any]]]:
    """Per ogni stagione, la griglia che ha previsto meglio la stagione
    precedente. Restituisce la scelta e la tabella dei log-loss."""
    seasons = sorted({m.season_label for m in matches})
    table: dict[str, dict[str, Any]] = {}
    for hyper in HYPER_GRID:
        preds = predictions[hyper.key]
        per_season: dict[str, dict[str, float]] = {}
        for m in matches:
            if not m.eval_eligible or m.lab_match_id not in preds:
                continue
            acc = per_season.setdefault(m.season_label, {"sum": 0.0, "n": 0})
            acc["sum"] += _one_x_two_log_loss(m, preds[m.lab_match_id])
            acc["n"] += 1
        table[hyper.key] = {
            "xi": hyper.xi,
            "sigma": hyper.sigma,
            "log_loss_1x2": {
                s: round(v["sum"] / v["n"], 5) for s, v in per_season.items() if v["n"]
            },
        }

    chosen: dict[str, Hyper] = {}
    for idx, season in enumerate(seasons):
        if idx == 0:
            chosen[season] = DEFAULT_HYPER
            continue
        previous = seasons[idx - 1]
        best = min(
            HYPER_GRID,
            key=lambda h: table[h.key]["log_loss_1x2"].get(previous, float("inf")),
        )
        chosen[season] = best
    return chosen, table


# --- esecuzione ---------------------------------------------------------------------


def _progress(db: Session, run_id: int, pct: float, step: str) -> None:
    run = db.get(CecchinoV3Run, run_id)
    if run is None:
        return
    run.progress_pct = Decimal(str(round(min(pct, 99.9), 1)))
    run.current_step = step[:128]
    db.commit()


def _cancel_checker(run_id: int) -> Callable[[], bool]:
    state = {"last": 0.0, "cancelled": False}

    def should_stop() -> bool:
        now = time.monotonic()
        if state["cancelled"] or now - state["last"] < _CANCEL_CHECK_SECONDS:
            return state["cancelled"]
        state["last"] = now
        with SessionLocal() as check_db:
            run = check_db.get(CecchinoV3Run, run_id)
            state["cancelled"] = bool(run is None or run.cancel_requested)
        return state["cancelled"]

    return should_stop


def _persist(
    db: Session,
    run_id: int,
    matches: list[MatchRecord],
    predictions: dict[str, dict[int, StrengthPrediction]],
    chosen: dict[str, Hyper],
) -> dict[str, int]:
    written = {"matches": 0, "markets": 0}
    for start in range(0, len(matches), _INSERT_CHUNK):
        chunk = matches[start : start + _INSERT_CHUNK]
        match_rows: list[dict[str, Any]] = []
        market_payload: dict[int, list[tuple[str, float, bool | None]]] = {}
        for m in chunk:
            hyper = chosen[m.season_label]
            pred = predictions[hyper.key].get(m.lab_match_id)
            if pred is None:
                continue
            probs = market_probabilities(pred.lambda_home, pred.lambda_away, pred.rho, pred.ht_share)
            outcomes = market_outcomes(m.ft_home, m.ft_away, m.ht_home, m.ht_away)
            market_payload[m.lab_match_id] = [(mk, probs[mk], outcomes[mk]) for mk in MARKET_KEYS]
            match_rows.append(
                {
                    "run_id": run_id,
                    "lab_match_id": m.lab_match_id,
                    "competition_name": m.competition,
                    "country_group": m.group,
                    "season_label": m.season_label,
                    "kickoff_at": m.kickoff_at,
                    "home_team": m.home_team,
                    "away_team": m.away_team,
                    "phase": m.phase,
                    "eval_eligible": m.eval_eligible,
                    "home_played": m.home_played,
                    "away_played": m.away_played,
                    "home_remaining": m.home_remaining,
                    "away_remaining": m.away_remaining,
                    "lambda_home": _d(pred.lambda_home, 5),
                    "lambda_away": _d(pred.lambda_away, 5),
                    "rho": _d(pred.rho, 4),
                    "ht_share": _d(pred.ht_share, 4),
                    "home_evidence": _d(pred.home_evidence, 3),
                    "away_evidence": _d(pred.away_evidence, 3),
                    "hyper_xi": _d(hyper.xi, 5),
                    "hyper_sigma": _d(hyper.sigma, 3),
                    "ft_home_goals": m.ft_home,
                    "ft_away_goals": m.ft_away,
                }
            )
        if not match_rows:
            continue
        inserted = db.execute(
            insert(CecchinoV3MatchPrediction).returning(
                CecchinoV3MatchPrediction.id, CecchinoV3MatchPrediction.lab_match_id
            ),
            match_rows,
        ).all()
        market_rows = [
            {
                "run_id": run_id,
                "match_prediction_id": int(row.id),
                "lab_match_id": int(row.lab_match_id),
                "market_key": mk,
                "probability": _d(min(max(p, 0.0), 1.0), 7),
                "won": won,
            }
            for row in inserted
            for mk, p, won in market_payload[int(row.lab_match_id)]
        ]
        db.execute(insert(CecchinoV3MarketPrediction), market_rows)
        db.commit()
        written["matches"] += len(match_rows)
        written["markets"] += len(market_rows)
    return written


def _execute_run(run_id: int) -> None:
    db = SessionLocal()
    t0 = time.monotonic()
    try:
        run = db.get(CecchinoV3Run, run_id)
        if not run:
            return
        run.status = V3_STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()

        try:
            _progress(db, run_id, 1.0, "Caricamento partite")
            matches = load_matches(db)
            groups = group_matches(matches)
            should_stop = _cancel_checker(run_id)

            total_work = len(HYPER_GRID) * len(matches)
            done = 0
            predictions: dict[str, dict[int, StrengthPrediction]] = {}
            timings: dict[str, float] = {}
            for hyper in HYPER_GRID:
                predictions[hyper.key] = {}
                for group, group_list in groups.items():
                    _progress(
                        db, run_id, 2.0 + 80.0 * done / max(total_work, 1), f"Forza · {group} · {hyper.key}"
                    )
                    g0 = time.monotonic()
                    predictions[hyper.key].update(run_group(group_list, hyper, should_stop=should_stop))
                    timings[f"{group}|{hyper.key}"] = round(time.monotonic() - g0, 2)
                    done += len(group_list)
                    if should_stop():
                        break
                if should_stop():
                    break

            run = db.get(CecchinoV3Run, run_id)
            if run is None:
                return
            if should_stop():
                run.status = V3_STATUS_CANCELLED
                run.completed_at = _utcnow()
                db.commit()
                return

            _progress(db, run_id, 83.0, "Scelta iperparametri sulla stagione precedente")
            chosen, hyper_table = select_hypers(matches, predictions)

            _progress(db, run_id, 86.0, "Salvataggio previsioni")
            written = _persist(db, run_id, matches, predictions, chosen)

            _progress(db, run_id, 95.0, "Valutazione contro V2 e bookmaker")
            from app.services.cecchino_v3.evaluation import build_evaluation

            evaluation = build_evaluation(db, run_id)

            seasons: dict[str, dict[str, int]] = {}
            for m in matches:
                s = seasons.setdefault(
                    m.season_label, {"matches": 0, "eligible": 0, "early": 0, "mid": 0, "final": 0}
                )
                s["matches"] += 1
                s["eligible"] += int(m.eval_eligible)
                s[m.phase] += 1

            run = db.get(CecchinoV3Run, run_id)
            run.summary_json = {
                "seasons": seasons,
                "chosen_hyper": {s: {"xi": h.xi, "sigma": h.sigma} for s, h in chosen.items()},
                "hyper_table": hyper_table,
                "written": written,
                "elapsed_seconds": round(time.monotonic() - t0, 1),
                "group_timings_seconds": timings,
                "evaluation": evaluation,
            }
            run.progress_pct = Decimal("100.0")
            run.current_step = None
            run.status = V3_STATUS_COMPLETED
            run.completed_at = _utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoV3Run, run_id)
            if run:
                run.status = V3_STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("cecchino v3 run %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)
