"""Job orchestrator per Pattern Insights (Run V2) — stesso schema (riga di
stato DB + thread daemon in-process) gia' usato per Pattern Grid, ma qui
i "target" da esplorare sono i 17 mercati con quota PIU' i bersagli
sintetici senza quota (tiri/corner/cartellini), eseguiti in sequenza
all'interno di un singolo run (niente concorrenza tra thread: e' stata
proprio l'esecuzione concorrente a causare lo stallo osservato nel
Pattern Grid originale)."""

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
from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.models.cecchino_run_v2_pattern_insight import (
    ACTIVE_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    TARGET_TYPE_MARKET,
    TARGET_TYPE_SYNTHETIC,
    CecchinoRunV2PatternInsightCandidate,
    CecchinoRunV2PatternInsightRun,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields
from app.services.cecchino_data_lab.run_v2_grid_dataset import (
    SYNTHETIC_TARGETS,
    load_run_v2_market_rows,
    load_run_v2_synthetic_rows,
)
from app.services.cecchino_data_lab.run_v2_grid_dataset import ODDS_MODE_CLOSING, ODDS_MODES
from app.services.cecchino_data_lab.run_v2_grid_engine import (
    ENGINE_VERSION_VECTORIZED,
    candidate_to_summary,
    discover_patterns_fast,
)
from app.services.cecchino_data_lab.run_v2_scope import is_lockbox_season
from app.services.cecchino_data_lab.run_v2_grid_labels import target_label

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}

MARKET_KEYS: tuple[str, ...] = (
    "HOME",
    "DRAW",
    "AWAY",
    "HOME_PT",
    "DRAW_PT",
    "AWAY_PT",
    "ONE_X",
    "X_TWO",
    "ONE_TWO",
    "OVER_0_5",
    "UNDER_0_5",
    "OVER_1_5",
    "UNDER_1_5",
    "OVER_2_5",
    "UNDER_2_5",
    "OVER_3_5",
    "UNDER_3_5",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _d(v: float | None) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def run_to_dict(run: CecchinoRunV2PatternInsightRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "run_v2_run_id": int(run.run_v2_run_id),
        "status": run.status,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "targets_total": int(run.targets_total or 0),
        "targets_processed": int(run.targets_processed or 0),
        "current_target_label": run.current_target_label,
        "progress_pct": float(run.progress_pct) if run.progress_pct is not None else None,
        "summary": run.summary_json,
        "error": run.error_json,
        "source_git_commit": run.source_git_commit,
        "odds_mode": run.odds_mode,
        "engine_version": run.engine_version,
    }


def candidate_row_to_dict(row: CecchinoRunV2PatternInsightCandidate) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "insight_run_id": int(row.insight_run_id),
        "target_type": row.target_type,
        "target_key": row.target_key,
        "target_label": row.target_label,
        "threshold": float(row.threshold) if row.threshold is not None else None,
        "filters_json": row.filters_json,
        "filters_text": row.filters_text,
        "filters_text_human": row.filters_text_human,
        "refined_from_text": row.refined_from_text,
        "n": row.n,
        "wins": row.wins,
        "losses": row.losses,
        "win_rate_pct": float(row.win_rate_pct) if row.win_rate_pct is not None else None,
        "roi_pct": float(row.roi_pct) if row.roi_pct is not None else None,
        "avg_quota": float(row.avg_quota) if row.avg_quota is not None else None,
        "baseline_win_rate_pct": (
            float(row.baseline_win_rate_pct) if row.baseline_win_rate_pct is not None else None
        ),
        "deviation_pct": float(row.deviation_pct) if row.deviation_pct is not None else None,
    }


def start_pattern_insight_run(
    db: Session, *, run_v2_run_id: int, odds_mode: str = ODDS_MODE_CLOSING, spawn: bool = True
) -> dict[str, Any]:
    """spawn=False: esecuzione nello stesso thread (pipeline RUN V2.5)."""
    if odds_mode not in ODDS_MODES:
        raise CecchinoLabImportError("invalid_odds_mode", f"odds_mode non valido: {odds_mode}", status_code=400)
    run_v2 = db.get(CecchinoRunV2Run, run_v2_run_id)
    if not run_v2:
        raise CecchinoLabImportError("run_v2_not_found", "Run V2 non trovata", status_code=404)
    if is_lockbox_season((run_v2.summary_json or {}).get("season_label")):
        raise CecchinoLabImportError(
            "lockbox_season",
            "La stagione 2025/26 e' sotto chiave: e' il test finale e non puo' essere usata per la scoperta.",
            status_code=403,
        )
    if run_v2.status not in ("completed", "completed_with_warnings"):
        raise CecchinoLabImportError(
            "run_v2_not_completed",
            f"Run V2 #{run_v2_run_id} non e' completata (stato: {run_v2.status})",
            status_code=400,
        )

    active = db.scalars(
        select(CecchinoRunV2PatternInsightRun).where(
            CecchinoRunV2PatternInsightRun.run_v2_run_id == run_v2_run_id,
            CecchinoRunV2PatternInsightRun.status.in_(tuple(ACTIVE_STATUSES)),
        )
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste gia' un'analisi attiva (id={active.id}) per questa Run V2",
            status_code=409,
            details={"active_run_id": int(active.id)},
        )

    revision = revision_as_source_fields()
    run = CecchinoRunV2PatternInsightRun(
        run_v2_run_id=run_v2_run_id,
        status=STATUS_PENDING,
        requested_at=_utcnow(),
        source_git_commit=revision.get("source_git_commit"),
        odds_mode=odds_mode,
        engine_version=ENGINE_VERSION_VECTORIZED,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if spawn:
        _spawn_worker(int(run.id))
    else:
        _execute_pattern_insight_run(int(run.id))
        db.refresh(run)
    return run_to_dict(run)


def get_pattern_insight_run(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoRunV2PatternInsightRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    return run_to_dict(run)


def cancel_pattern_insight_run(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoRunV2PatternInsightRun, run_id)
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
            target=_execute_pattern_insight_run,
            args=(run_id,),
            name=f"cecchino-run-v2-pattern-insight-{run_id}",
            daemon=True,
        )
        _active_threads[run_id] = t
        t.start()


def _execute_pattern_insight_run(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoRunV2PatternInsightRun, run_id)
        if not run:
            return
        run.status = STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()

        try:
            run_v2_run_id = int(run.run_v2_run_id)

            targets: list[tuple[str, str, str, float | None]] = [
                (TARGET_TYPE_MARKET, mk, mk, None) for mk in MARKET_KEYS
            ]
            for stat_key, label, thresholds in SYNTHETIC_TARGETS:
                for threshold in thresholds:
                    targets.append((TARGET_TYPE_SYNTHETIC, stat_key, label, threshold))

            run.targets_total = len(targets)
            db.commit()

            verdict_counts: dict[str, int] = {"market": 0, "synthetic": 0}
            total_candidates = 0

            for idx, (target_type, target_key, label, threshold) in enumerate(targets, start=1):
                run = db.get(CecchinoRunV2PatternInsightRun, run_id)
                if run is None:
                    return
                if run.cancel_requested:
                    run.status = STATUS_CANCELLED
                    run.completed_at = _utcnow()
                    db.commit()
                    return

                display_label = target_label(target_key, threshold)
                run.current_target_label = display_label
                run.targets_processed = idx - 1
                run.progress_pct = Decimal(str(round((idx - 1) / len(targets) * 100.0, 1)))
                db.commit()

                if target_type == TARGET_TYPE_MARKET:
                    rows = load_run_v2_market_rows(
                        db, run_id=run_v2_run_id, market_key=target_key, odds_mode=run.odds_mode
                    )
                    has_odds = True
                else:
                    rows = load_run_v2_synthetic_rows(
                        db, run_id=run_v2_run_id, stat_key=target_key, threshold=threshold
                    )
                    has_odds = False

                if rows:
                    baseline = round(sum(1 for r in rows if r.won) / len(rows) * 100.0, 3)
                    candidates = discover_patterns_fast(rows, has_odds=has_odds)
                    for c in candidates:
                        summary = candidate_to_summary(c, baseline_win_rate=baseline)
                        db.add(
                            CecchinoRunV2PatternInsightCandidate(
                                insight_run_id=run.id,
                                target_type=target_type,
                                target_key=target_key,
                                target_label=display_label,
                                threshold=_d(threshold),
                                filters_json=summary["filters_json"],
                                filters_text=summary["filters_text"],
                                filters_text_human=summary["filters_text_human"],
                                refined_from_text=summary["refined_from_text"],
                                n=summary["n"],
                                wins=summary["wins"],
                                losses=summary["losses"],
                                win_rate_pct=_d(summary["win_rate_pct"]),
                                roi_pct=_d(summary["roi_pct"]),
                                avg_quota=_d(summary["avg_quota"]),
                                baseline_win_rate_pct=_d(summary["baseline_win_rate_pct"]),
                                deviation_pct=_d(summary["deviation_pct"]),
                                profit_units=_d(c.stats.get("profit_units")),
                                n_priced=c.stats.get("n_priced"),
                            )
                        )
                    total_candidates += len(candidates)
                    verdict_counts[target_type] += len(candidates)
                    db.commit()

            run = db.get(CecchinoRunV2PatternInsightRun, run_id)
            if run is not None:
                run.targets_processed = len(targets)
                run.progress_pct = Decimal("100.0")
                run.current_target_label = None
                run.summary_json = {
                    "targets_total": len(targets),
                    "candidates_total": total_candidates,
                    "candidates_by_type": verdict_counts,
                }
                run.status = STATUS_CANCELLED if run.cancel_requested else STATUS_COMPLETED
                run.completed_at = _utcnow()
                db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoRunV2PatternInsightRun, run_id)
            if run:
                run.status = STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("run v2 pattern insight run %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)
