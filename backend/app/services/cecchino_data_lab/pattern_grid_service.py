"""Job orchestrator per il motore Pattern Grid — stesso schema (riga di stato
DB + thread daemon in-process) già usato per il motore ad albero."""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_pattern_grid_candidate import CecchinoPatternGridCandidate
from app.models.cecchino_pattern_grid_run import (
    ACTIVE_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    CecchinoPatternGridRun,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.pattern_grid_dataset import load_grid_rows_by_season
from app.services.cecchino_data_lab.pattern_grid_engine import candidate_to_summary, run_pattern_grid
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}

KNOWN_MARKET_KEYS = (
    "HOME",
    "DRAW",
    "AWAY",
    "ONE_X",
    "X_TWO",
    "ONE_TWO",
    "OVER_2_5",
    "UNDER_2_5",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _d(v: float | None) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def run_to_dict(run: CecchinoPatternGridRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "market_key": run.market_key,
        "competition": run.competition,
        "run_ids": run.run_ids_json,
        "status": run.status,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "stages_total": int(run.stages_total or 0),
        "stages_processed": int(run.stages_processed or 0),
        "progress_pct": float(run.progress_pct) if run.progress_pct is not None else None,
        "summary": run.summary_json,
        "error": run.error_json,
        "source_git_commit": run.source_git_commit,
    }


def candidate_row_to_dict(row: CecchinoPatternGridCandidate) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "grid_run_id": int(row.grid_run_id),
        "market_key": row.market_key,
        "competition": row.competition,
        "filters_json": row.filters_json,
        "filters_text": row.filters_text,
        "born_stage": row.born_stage,
        "refined_from_text": row.refined_from_text,
        "per_stage": row.per_stage_json,
        "final_verdict": row.final_verdict,
    }


def start_pattern_grid(
    db: Session,
    *,
    market_key: str,
    run_ids: list[int],
    competition: str | None = None,
) -> dict[str, Any]:
    normalized_key = (market_key or "").strip().upper()
    if normalized_key not in KNOWN_MARKET_KEYS:
        raise CecchinoLabImportError(
            "invalid_market_key",
            f"market_key non riconosciuto o senza quote disponibili: {market_key!r}",
            status_code=400,
        )
    clean_run_ids = sorted({int(x) for x in (run_ids or [])})
    if len(clean_run_ids) < 2:
        raise CecchinoLabImportError(
            "insufficient_run_ids",
            "Servono almeno 2 stagioni per un ciclo sequenziale",
            status_code=400,
        )
    normalized_competition = (competition or "").strip() or None

    active = db.scalars(
        select(CecchinoPatternGridRun).where(
            CecchinoPatternGridRun.market_key == normalized_key,
            CecchinoPatternGridRun.competition == normalized_competition,
            CecchinoPatternGridRun.status.in_(tuple(ACTIVE_STATUSES)),
        )
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste già un run attivo (id={active.id}) per {normalized_key}"
            + (f" / {normalized_competition}" if normalized_competition else ""),
            status_code=409,
            details={"active_run_id": int(active.id)},
        )

    revision = revision_as_source_fields()
    run = CecchinoPatternGridRun(
        market_key=normalized_key,
        competition=normalized_competition,
        run_ids_json=clean_run_ids,
        status=STATUS_PENDING,
        requested_at=_utcnow(),
        source_git_commit=revision.get("source_git_commit"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    _spawn_worker(int(run.id))
    return run_to_dict(run)


def get_pattern_grid_run(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoPatternGridRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    return run_to_dict(run)


def list_pattern_grid_candidates(db: Session, run_id: int) -> list[dict[str, Any]]:
    run = db.get(CecchinoPatternGridRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    rows = db.scalars(
        select(CecchinoPatternGridCandidate)
        .where(CecchinoPatternGridCandidate.grid_run_id == run_id)
        .order_by(CecchinoPatternGridCandidate.born_stage, CecchinoPatternGridCandidate.id)
    ).all()
    return [candidate_row_to_dict(r) for r in rows]


def cancel_pattern_grid(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoPatternGridRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    run.cancel_requested = True
    db.commit()
    db.refresh(run)
    return run_to_dict(run)


def _spawn_worker(run_id: int) -> None:
    with _lock:
        existing = _active_threads.get(run_id)
        if existing and existing.is_alive():
            return
        t = threading.Thread(
            target=_execute_pattern_grid_run,
            args=(run_id,),
            name=f"cecchino-pattern-grid-{run_id}",
            daemon=True,
        )
        _active_threads[run_id] = t
        t.start()


def _execute_pattern_grid_run(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoPatternGridRun, run_id)
        if not run:
            return
        run.status = STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()

        try:
            by_season = load_grid_rows_by_season(
                db,
                run_ids=list(run.run_ids_json or []),
                market_key=run.market_key,
                competition=run.competition,
            )
            seasons_sorted = sorted(by_season.keys())
            rows_by_stage = [by_season[s] for s in seasons_sorted]

            run.stages_total = len(rows_by_stage)
            db.commit()

            candidates = run_pattern_grid(rows_by_stage)

            for c in candidates:
                summary = candidate_to_summary(c, total_stages=len(rows_by_stage))
                db.add(
                    CecchinoPatternGridCandidate(
                        grid_run_id=run.id,
                        market_key=run.market_key,
                        competition=run.competition,
                        filters_json=summary["filters_json"],
                        filters_text=summary["filters_text"],
                        born_stage=summary["born_stage"],
                        refined_from_text=summary["refined_from_text"],
                        per_stage_json=summary["per_stage"],
                        final_verdict=summary["final_verdict"],
                    )
                )

            run = db.get(CecchinoPatternGridRun, run_id)
            if run is not None:
                verdict_counts: dict[str, int] = {}
                for c in candidates:
                    v = candidate_to_summary(c, total_stages=len(rows_by_stage))["final_verdict"]
                    verdict_counts[v] = verdict_counts.get(v, 0) + 1
                run.summary_json = {
                    "seasons": seasons_sorted,
                    "candidates_total": len(candidates),
                    "verdict_counts": verdict_counts,
                }
                run.stages_processed = len(rows_by_stage)
                run.progress_pct = Decimal("100.0")
                run.status = STATUS_CANCELLED if run.cancel_requested else STATUS_COMPLETED
                run.completed_at = _utcnow()
                db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoPatternGridRun, run_id)
            if run:
                run.status = STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("pattern grid run %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)
