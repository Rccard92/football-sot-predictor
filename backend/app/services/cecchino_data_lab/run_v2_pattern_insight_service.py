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

from sqlalchemy import func, select
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
from app.services.cecchino_data_lab.run_v2_grid_engine import candidate_to_summary, discover_patterns
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


def start_pattern_insight_run(db: Session, *, run_v2_run_id: int) -> dict[str, Any]:
    run_v2 = db.get(CecchinoRunV2Run, run_v2_run_id)
    if not run_v2:
        raise CecchinoLabImportError("run_v2_not_found", "Run V2 non trovata", status_code=404)
    if run_v2.status != "completed":
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
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    _spawn_worker(int(run.id))
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


def _latest_completed_run(db: Session) -> CecchinoRunV2PatternInsightRun | None:
    return db.scalars(
        select(CecchinoRunV2PatternInsightRun)
        .where(CecchinoRunV2PatternInsightRun.status == STATUS_COMPLETED)
        .order_by(CecchinoRunV2PatternInsightRun.completed_at.desc())
    ).first()


def get_summary(db: Session, *, min_n: int = 20) -> dict[str, Any]:
    """Aggregato leggero per la dashboard (conteggi/migliori per bersaglio),
    calcolato in SQL — mai l'intera lista di candidati (puo' superare le
    decine di migliaia di righe con un vocabolario cosi' ampio)."""
    run = _latest_completed_run(db)
    if not run:
        return {"run": None, "targets": [], "totals": {"market": 0, "synthetic": 0}}

    rows = db.execute(
        select(
            CecchinoRunV2PatternInsightCandidate.target_type,
            CecchinoRunV2PatternInsightCandidate.target_key,
            CecchinoRunV2PatternInsightCandidate.target_label,
            CecchinoRunV2PatternInsightCandidate.threshold,
            func.count().label("count"),
            func.max(CecchinoRunV2PatternInsightCandidate.roi_pct).label("best_roi_pct"),
            func.max(func.abs(CecchinoRunV2PatternInsightCandidate.deviation_pct)).label(
                "best_abs_deviation_pct"
            ),
        )
        .where(
            CecchinoRunV2PatternInsightCandidate.insight_run_id == run.id,
            CecchinoRunV2PatternInsightCandidate.n >= min_n,
        )
        .group_by(
            CecchinoRunV2PatternInsightCandidate.target_type,
            CecchinoRunV2PatternInsightCandidate.target_key,
            CecchinoRunV2PatternInsightCandidate.target_label,
            CecchinoRunV2PatternInsightCandidate.threshold,
        )
    ).all()

    targets = [
        {
            "target_type": r.target_type,
            "target_key": r.target_key,
            "target_label": r.target_label,
            "threshold": float(r.threshold) if r.threshold is not None else None,
            "count": int(r.count),
            "best_roi_pct": float(r.best_roi_pct) if r.best_roi_pct is not None else None,
            "best_abs_deviation_pct": (
                float(r.best_abs_deviation_pct) if r.best_abs_deviation_pct is not None else None
            ),
        }
        for r in rows
    ]
    totals = {
        "market": sum(t["count"] for t in targets if t["target_type"] == TARGET_TYPE_MARKET),
        "synthetic": sum(t["count"] for t in targets if t["target_type"] == TARGET_TYPE_SYNTHETIC),
    }
    return {"run": run_to_dict(run), "targets": targets, "totals": totals}


def get_analytics(db: Session, *, min_n: int = 50) -> dict[str, Any]:
    """Tutti gli aggregati della dashboard in una sola chiamata: ogni blocco
    risponde a una domanda diversa sugli stessi dati."""
    from app.services.cecchino_data_lab import run_v2_pattern_insight_analytics as an

    run = _latest_completed_run(db)
    if not run:
        return {"run": None}

    rid = int(run.id)
    return {
        "run": run_to_dict(run),
        "min_n": min_n,
        "by_market": an.by_market(db, insight_run_id=rid, min_n=min_n),
        "factor_frequency": an.factor_frequency(db, insight_run_id=rid, min_n=min_n),
        "by_complexity": an.by_complexity(db, insight_run_id=rid, min_n=min_n),
        "quality_scatter": an.quality_scatter(db, insight_run_id=rid, min_n=min_n),
        "synthetic_directions": an.synthetic_directions(db, insight_run_id=rid, min_n=min_n),
        "sample_buckets": an.sample_buckets(db, insight_run_id=rid, min_n=min_n),
        "source_coverage": an.source_coverage(db, run_v2_run_id=int(run.run_v2_run_id)),
    }


def list_candidates(
    db: Session,
    *,
    target_type: str | None = None,
    target_key: str | None = None,
    threshold: float | None = None,
    min_n: int = 20,
    verdict: str | None = None,
    sort: str = "best",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Candidati paginati/filtrati per la tabella della dashboard, con i
    numeri della stagione di verifica (se esiste una verifica completata)
    affiancati a quelli della stagione di scoperta."""
    from app.models.cecchino_run_v2_pattern_insight import (
        CecchinoRunV2PatternValidation as V,
        CecchinoRunV2PatternValidationRun as VR,
    )

    C = CecchinoRunV2PatternInsightCandidate
    run = _latest_completed_run(db)
    if not run:
        return {"run": None, "validation": None, "total": 0, "items": []}

    vrun = db.scalars(
        select(VR)
        .where(VR.insight_run_id == run.id, VR.status == STATUS_COMPLETED)
        .order_by(VR.completed_at.desc())
    ).first()

    filters = [C.insight_run_id == run.id, C.n >= min_n]
    if target_type:
        filters.append(C.target_type == target_type)
    if target_key:
        filters.append(C.target_key == target_key)
    if threshold is not None:
        filters.append(C.threshold == _d(threshold))

    join_on = (
        (V.candidate_id == C.id) & (V.validation_run_id == vrun.id) if vrun is not None else V.id == -1
    )
    if vrun is not None and verdict:
        filters.append(V.verdict == verdict)

    query = select(C, V).select_from(C).outerjoin(V, join_on).where(*filters)
    total = int(
        db.scalar(select(func.count(C.id)).select_from(C).outerjoin(V, join_on).where(*filters))
        or 0
    )

    if sort == "roi_desc":
        query = query.order_by(C.roi_pct.desc().nulls_last())
    elif sort == "deviation_desc":
        query = query.order_by(func.abs(C.deviation_pct).desc().nulls_last())
    elif sort == "oos_roi_desc":
        query = query.order_by(V.roi_pct.desc().nulls_last())
    elif sort == "oos_deviation_desc":
        query = query.order_by(func.abs(V.deviation_pct).desc().nulls_last())
    elif sort == "oos_n_desc":
        query = query.order_by(V.n.desc().nulls_last())
    else:
        query = query.order_by(
            C.roi_pct.desc().nulls_last(), func.abs(C.deviation_pct).desc().nulls_last()
        )
    rows = db.execute(query.limit(limit).offset(offset)).all()

    items = []
    for cand, val in rows:
        item = candidate_row_to_dict(cand)
        item["oos"] = (
            {
                "n": val.n,
                "wins": val.wins,
                "losses": val.losses,
                "win_rate_pct": float(val.win_rate_pct) if val.win_rate_pct is not None else None,
                "roi_pct": float(val.roi_pct) if val.roi_pct is not None else None,
                "profit_units": float(val.profit_units) if val.profit_units is not None else None,
                "avg_quota": float(val.avg_quota) if val.avg_quota is not None else None,
                "baseline_win_rate_pct": (
                    float(val.baseline_win_rate_pct) if val.baseline_win_rate_pct is not None else None
                ),
                "deviation_pct": float(val.deviation_pct) if val.deviation_pct is not None else None,
                "verdict": val.verdict,
                "null_confirm_prob": (
                    float(val.null_confirm_prob) if val.null_confirm_prob is not None else None
                ),
            }
            if val is not None
            else None
        )
        items.append(item)

    return {
        "run": run_to_dict(run),
        "validation": (
            {"id": int(vrun.id), "season_label": vrun.season_label} if vrun is not None else None
        ),
        "total": total,
        "items": items,
    }


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
                    rows = load_run_v2_market_rows(db, run_id=run_v2_run_id, market_key=target_key)
                    has_odds = True
                else:
                    rows = load_run_v2_synthetic_rows(
                        db, run_id=run_v2_run_id, stat_key=target_key, threshold=threshold
                    )
                    has_odds = False

                if rows:
                    baseline = round(sum(1 for r in rows if r.won) / len(rows) * 100.0, 3)
                    candidates = discover_patterns(rows, has_odds=has_odds)
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
