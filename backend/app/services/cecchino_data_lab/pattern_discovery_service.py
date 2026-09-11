"""Job orchestrator per la scoperta Pattern walk-forward Cecchino.

Stessa forma dei job già esistenti in Cecchino Lab (riga di stato DB + thread
daemon in-process, vedi historical_scan_service.py): nessuna infrastruttura
nuova, il carico di lavoro (fit di un albero poco profondo su decine di
migliaia di righe) è computazionalmente banale.
"""

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
from app.models.cecchino_discovered_pattern import CecchinoDiscoveredPattern
from app.models.cecchino_pattern_discovery_run import (
    ACTIVE_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    CecchinoPatternDiscoveryRun,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.pattern_discovery_dataset import (
    build_walk_forward_folds,
    load_market_rows_by_season,
)
from app.services.cecchino_data_lab.pattern_discovery_engine import (
    CandidatePattern,
    OosResult,
    discover_patterns_for_fold,
    validate_pattern_out_of_sample,
)
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}

KNOWN_MARKET_KEYS = (
    "HOME",
    "DRAW",
    "AWAY",
    "HOME_PT",
    "DRAW_PT",
    "AWAY_PT",
    "ONE_X",
    "X_TWO",
    "ONE_TWO",
    "OVER_1_5",
    "UNDER_1_5",
    "OVER_2_5",
    "UNDER_2_5",
    "OVER_3_5",
    "UNDER_3_5",
    "OVER_PT_0_5",
    "UNDER_PT_0_5",
    "OVER_PT_1_5",
    "UNDER_PT_1_5",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _d(v: float | None) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def run_to_dict(run: CecchinoPatternDiscoveryRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "market_key": run.market_key,
        "run_ids": run.run_ids_json,
        "status": run.status,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "folds_total": int(run.folds_total or 0),
        "folds_processed": int(run.folds_processed or 0),
        "progress_pct": float(run.progress_pct) if run.progress_pct is not None else None,
        "config": run.config_json,
        "summary": run.summary_json,
        "error": run.error_json,
        "source_git_commit": run.source_git_commit,
    }


def pattern_to_dict(p: CecchinoDiscoveredPattern) -> dict[str, Any]:
    return {
        "id": int(p.id),
        "discovery_run_id": int(p.discovery_run_id),
        "market_key": p.market_key,
        "fold_index": p.fold_index,
        "train_seasons": p.train_seasons_json,
        "validation_season": p.validation_season,
        "formula_slot": p.formula_slot,
        "rule": p.rule_json,
        "rule_text": p.rule_text,
        "train_n": p.train_n,
        "train_wins": p.train_wins,
        "train_win_rate_pct": float(p.train_win_rate_pct) if p.train_win_rate_pct is not None else None,
        "train_avg_profit_1u": float(p.train_avg_profit_1u) if p.train_avg_profit_1u is not None else None,
        "oos_n": p.oos_n,
        "oos_wins": p.oos_wins,
        "oos_win_rate_pct": float(p.oos_win_rate_pct) if p.oos_win_rate_pct is not None else None,
        "oos_win_rate_ci_low_pct": (
            float(p.oos_win_rate_ci_low_pct) if p.oos_win_rate_ci_low_pct is not None else None
        ),
        "oos_win_rate_ci_high_pct": (
            float(p.oos_win_rate_ci_high_pct) if p.oos_win_rate_ci_high_pct is not None else None
        ),
        "oos_avg_profit_1u": float(p.oos_avg_profit_1u) if p.oos_avg_profit_1u is not None else None,
        "oos_avg_profit_ci_low": float(p.oos_avg_profit_ci_low) if p.oos_avg_profit_ci_low is not None else None,
        "oos_avg_profit_ci_high": float(p.oos_avg_profit_ci_high) if p.oos_avg_profit_ci_high is not None else None,
        "oos_avg_quota_book": float(p.oos_avg_quota_book) if p.oos_avg_quota_book is not None else None,
        "breakeven_win_rate_pct": (
            float(p.breakeven_win_rate_pct) if p.breakeven_win_rate_pct is not None else None
        ),
        "promoted": bool(p.promoted),
        "promotion_reason": p.promotion_reason,
    }


def start_pattern_discovery(
    db: Session,
    *,
    market_key: str,
    run_ids: list[int],
) -> dict[str, Any]:
    normalized_key = (market_key or "").strip().upper()
    if normalized_key not in KNOWN_MARKET_KEYS:
        raise CecchinoLabImportError(
            "invalid_market_key",
            f"market_key non riconosciuto: {market_key!r}",
            status_code=400,
        )
    clean_run_ids = sorted({int(x) for x in (run_ids or [])})
    if len(clean_run_ids) < 2:
        raise CecchinoLabImportError(
            "insufficient_run_ids",
            "Servono almeno 2 run/stagioni per costruire un fold walk-forward",
            status_code=400,
        )

    active = db.scalars(
        select(CecchinoPatternDiscoveryRun).where(
            CecchinoPatternDiscoveryRun.market_key == normalized_key,
            CecchinoPatternDiscoveryRun.status.in_(tuple(ACTIVE_STATUSES)),
        )
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste già un run attivo (id={active.id}) per {normalized_key}",
            status_code=409,
            details={"active_run_id": int(active.id)},
        )

    revision = revision_as_source_fields()
    run = CecchinoPatternDiscoveryRun(
        market_key=normalized_key,
        run_ids_json=clean_run_ids,
        status=STATUS_PENDING,
        requested_at=_utcnow(),
        config_json={
            "engine_version": "cecchino_pattern_discovery_v1",
            "tree_max_depth": 3,
            "min_leaf_floor": 30,
            "max_formulas_per_fold": 4,
        },
        source_git_commit=revision.get("source_git_commit"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    _spawn_worker(int(run.id))
    return run_to_dict(run)


def get_pattern_discovery_run(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoPatternDiscoveryRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    return run_to_dict(run)


def list_discovered_patterns(db: Session, run_id: int) -> list[dict[str, Any]]:
    run = db.get(CecchinoPatternDiscoveryRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    rows = db.scalars(
        select(CecchinoDiscoveredPattern)
        .where(CecchinoDiscoveredPattern.discovery_run_id == run_id)
        .order_by(CecchinoDiscoveredPattern.fold_index, CecchinoDiscoveredPattern.formula_slot)
    ).all()
    return [pattern_to_dict(p) for p in rows]


def cancel_pattern_discovery(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoPatternDiscoveryRun, run_id)
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
            target=_execute_pattern_discovery_run,
            args=(run_id,),
            name=f"cecchino-pattern-discovery-{run_id}",
            daemon=True,
        )
        _active_threads[run_id] = t
        t.start()


def _persist_candidate(
    db: Session,
    run: CecchinoPatternDiscoveryRun,
    candidate: CandidatePattern,
    oos: OosResult,
) -> None:
    row = CecchinoDiscoveredPattern(
        discovery_run_id=run.id,
        market_key=run.market_key,
        fold_index=candidate.fold_index,
        train_seasons_json=candidate.train_seasons,
        validation_season=candidate.validation_season,
        formula_slot=candidate.formula_slot,
        rule_json=[c.as_dict() for c in candidate.conditions],
        rule_text=candidate.rule_text(),
        train_n=candidate.train_n,
        train_wins=candidate.train_wins,
        train_win_rate_pct=_d(candidate.train_win_rate_pct),
        train_avg_profit_1u=_d(candidate.train_avg_profit_1u),
        oos_n=oos.n,
        oos_wins=oos.wins,
        oos_win_rate_pct=_d(oos.win_rate_pct),
        oos_win_rate_ci_low_pct=_d(oos.win_rate_ci_low_pct),
        oos_win_rate_ci_high_pct=_d(oos.win_rate_ci_high_pct),
        oos_avg_profit_1u=_d(oos.avg_profit_1u),
        oos_avg_profit_ci_low=_d(oos.avg_profit_ci_low),
        oos_avg_profit_ci_high=_d(oos.avg_profit_ci_high),
        oos_avg_quota_book=_d(oos.avg_quota_book),
        breakeven_win_rate_pct=_d(oos.breakeven_win_rate_pct),
        promoted=oos.promoted,
        promotion_reason=oos.promotion_reason,
    )
    db.add(row)


def _execute_pattern_discovery_run(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoPatternDiscoveryRun, run_id)
        if not run:
            return
        run.status = STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()

        try:
            by_season = load_market_rows_by_season(
                db, run_ids=list(run.run_ids_json or []), market_key=run.market_key
            )
            seasons_sorted = sorted(by_season.keys())
            folds = build_walk_forward_folds(seasons_sorted)

            run.folds_total = len(folds)
            db.commit()

            fold_summaries: list[dict[str, Any]] = []
            for idx, (train_seasons, validation_season) in enumerate(folds):
                run = db.get(CecchinoPatternDiscoveryRun, run_id)
                if run is None or run.cancel_requested:
                    break

                train_rows = [row for s in train_seasons for row in by_season.get(s, [])]
                validation_rows = by_season.get(validation_season, [])

                candidates = discover_patterns_for_fold(
                    fold_index=idx,
                    train_seasons=train_seasons,
                    validation_season=validation_season,
                    train_rows=train_rows,
                )

                promoted_count = 0
                for candidate in candidates:
                    oos = validate_pattern_out_of_sample(candidate, validation_rows)
                    promoted_count += 1 if oos.promoted else 0
                    _persist_candidate(db, run, candidate, oos)

                fold_summaries.append(
                    {
                        "fold_index": idx,
                        "train_seasons": train_seasons,
                        "validation_season": validation_season,
                        "train_n": len(train_rows),
                        "validation_n": len(validation_rows),
                        "candidates_found": len(candidates),
                        "candidates_promoted": promoted_count,
                    }
                )
                run.folds_processed = idx + 1
                run.progress_pct = _d(round((idx + 1) / max(len(folds), 1) * 100.0, 1))
                db.commit()

            run = db.get(CecchinoPatternDiscoveryRun, run_id)
            if run is not None:
                run.summary_json = {
                    "seasons_available": seasons_sorted,
                    "folds": fold_summaries,
                }
                run.status = STATUS_CANCELLED if run.cancel_requested else STATUS_COMPLETED
                run.completed_at = _utcnow()
                db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoPatternDiscoveryRun, run_id)
            if run:
                run.status = STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("pattern discovery run %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)
