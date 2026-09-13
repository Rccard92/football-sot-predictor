"""Verifica fuori campione dei pattern Pattern Insights.

Prende tutti i pattern scoperti su una stagione Run V2 e li misura su una
stagione successiva, mai vista in fase di scoperta. Tre regole che rendono
la verifica onesta:

1. Stesse fasce: i quintili di tiri/corner/cartellini/arbitro sono quelli
   della stagione di SCOPERTA, applicati bloccati alla stagione di verifica.
2. Controllo di parita': prima di verificare, ogni pattern viene ricalcolato
   sulla stagione di scoperta e confrontato con quanto salvato allora. Se i
   numeri non coincidono, la verifica confronterebbe cose diverse — il
   conteggio delle discrepanze finisce nel riepilogo.
3. Riferimento casuale: per ogni pattern si stima quanto spesso un gruppo
   CASUALE di partite della stagione di verifica, della stessa dimensione,
   avrebbe passato lo stesso criterio. La somma di queste probabilita' e' il
   numero di conferme atteso per puro caso.

Criteri di conferma (almeno MIN_OOS_SAMPLE partite nella stagione di verifica):
- mercati con quota: ROI positivo.
- situazioni senza quota: scarto dalla media nella stessa direzione e di
  almeno SYNTHETIC_CONFIRM_DEVIATION_PCT punti; stessa direzione ma piu'
  debole = attenuato; direzione opposta = respinto.
"""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.models.cecchino_run_v2_pattern_insight import (
    ACTIVE_STATUSES,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    TARGET_TYPE_MARKET,
    TARGET_TYPE_SYNTHETIC,
    VERDICT_ATTENUATED,
    VERDICT_CONFIRMED,
    VERDICT_INSUFFICIENT,
    VERDICT_REJECTED,
    CecchinoRunV2PatternInsightCandidate,
    CecchinoRunV2PatternInsightRun,
    CecchinoRunV2PatternValidation,
    CecchinoRunV2PatternValidationRun,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields
from app.services.cecchino_data_lab.run_v2_grid_dataset import (
    SYNTHETIC_TARGETS,
    load_market_raw,
    load_season_binners,
    load_synthetic_raw,
    market_rows_from_raw,
    synthetic_rows_from_raw,
)
from app.services.cecchino_data_lab.run_v2_grid_labels import target_label
from app.services.cecchino_data_lab.run_v2_grid_matrix import NullModel, RowMatrix
from app.services.cecchino_data_lab.run_v2_grid_vocabulary import Atom
from app.services.cecchino_data_lab.run_v2_pattern_insight_service import MARKET_KEYS

logger = logging.getLogger(__name__)

MIN_OOS_SAMPLE = 20
SYNTHETIC_CONFIRM_DEVIATION_PCT = 5.0

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _d(v: float | None) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def validation_run_to_dict(run: CecchinoRunV2PatternValidationRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "insight_run_id": int(run.insight_run_id),
        "run_v2_run_id": int(run.run_v2_run_id),
        "season_label": run.season_label,
        "status": run.status,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "targets_total": int(run.targets_total or 0),
        "targets_processed": int(run.targets_processed or 0),
        "current_target_label": run.current_target_label,
        "progress_pct": _f(run.progress_pct),
        "summary": run.summary_json,
        "error": run.error_json,
    }


def _season(run: CecchinoRunV2Run) -> str | None:
    return (run.summary_json or {}).get("season_label")


def start_validation(db: Session, *, run_v2_run_id: int) -> dict[str, Any]:
    insight = db.scalars(
        select(CecchinoRunV2PatternInsightRun)
        .where(CecchinoRunV2PatternInsightRun.status == STATUS_COMPLETED)
        .order_by(CecchinoRunV2PatternInsightRun.completed_at.desc())
    ).first()
    if not insight:
        raise CecchinoLabImportError(
            "insight_not_found", "Nessuna analisi Pattern Insights completata", status_code=404
        )

    target = db.get(CecchinoRunV2Run, run_v2_run_id)
    discovery = db.get(CecchinoRunV2Run, int(insight.run_v2_run_id))
    if not target or target.status != "completed":
        raise CecchinoLabImportError(
            "run_v2_not_ready", "Run V2 di verifica non trovata o non completata", status_code=400
        )
    if not discovery:
        raise CecchinoLabImportError("run_v2_not_found", "Run V2 di scoperta non trovata", status_code=404)

    target_season, discovery_season = _season(target), _season(discovery)
    if int(target.id) == int(discovery.id) or (
        target_season and discovery_season and target_season <= discovery_season
    ):
        raise CecchinoLabImportError(
            "not_out_of_sample",
            f"La stagione di verifica ({target_season}) deve essere successiva a quella di "
            f"scoperta ({discovery_season}): altrimenti non e' una verifica fuori campione.",
            status_code=400,
        )

    active = db.scalars(
        select(CecchinoRunV2PatternValidationRun).where(
            CecchinoRunV2PatternValidationRun.status.in_(tuple(ACTIVE_STATUSES))
        )
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste gia' una verifica in corso (id={active.id})",
            status_code=409,
        )

    run = CecchinoRunV2PatternValidationRun(
        insight_run_id=int(insight.id),
        run_v2_run_id=int(target.id),
        season_label=target_season,
        status=STATUS_PENDING,
        requested_at=_utcnow(),
        source_git_commit=revision_as_source_fields().get("source_git_commit"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    _spawn_worker(int(run.id))
    return validation_run_to_dict(run)


def get_validation_run(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoRunV2PatternValidationRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Verifica non trovata", status_code=404)
    return validation_run_to_dict(run)


def _spawn_worker(run_id: int) -> None:
    with _lock:
        existing = _active_threads.get(run_id)
        if existing and existing.is_alive():
            return
        t = threading.Thread(
            target=_execute_validation,
            args=(run_id,),
            name=f"cecchino-run-v2-pattern-validation-{run_id}",
            daemon=True,
        )
        _active_threads[run_id] = t
        t.start()


def _candidates_for(
    db: Session, insight_run_id: int, target_type: str, target_key: str, threshold: float | None
) -> list[CecchinoRunV2PatternInsightCandidate]:
    q = select(CecchinoRunV2PatternInsightCandidate).where(
        CecchinoRunV2PatternInsightCandidate.insight_run_id == insight_run_id,
        CecchinoRunV2PatternInsightCandidate.target_type == target_type,
        CecchinoRunV2PatternInsightCandidate.target_key == target_key,
    )
    if threshold is not None:
        q = q.where(CecchinoRunV2PatternInsightCandidate.threshold == _d(threshold))
    return list(db.scalars(q).all())


def _combo(c: CecchinoRunV2PatternInsightCandidate) -> tuple[Atom, ...]:
    return tuple(Atom(column=str(f["column"]), value=str(f["value"])) for f in c.filters_json or [])


class _Tally:
    def __init__(self) -> None:
        self.by_type: dict[str, dict[str, float]] = {
            TARGET_TYPE_MARKET: {},
            TARGET_TYPE_SYNTHETIC: {},
        }
        self.parity_checked = 0
        self.parity_mismatches = 0

    def add(self, target_type: str, verdict: str, null_prob: float | None) -> None:
        t = self.by_type[target_type]
        t[verdict] = t.get(verdict, 0) + 1
        t["total"] = t.get("total", 0) + 1
        if verdict != VERDICT_INSUFFICIENT and null_prob is not None:
            t["tested"] = t.get("tested", 0) + 1
            t["expected_confirmed_by_chance"] = t.get("expected_confirmed_by_chance", 0.0) + null_prob

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "parity_checked": self.parity_checked,
            "parity_mismatches": self.parity_mismatches,
        }
        for kind, t in self.by_type.items():
            tested = int(t.get("tested", 0))
            confirmed = int(t.get(VERDICT_CONFIRMED, 0))
            expected = float(t.get("expected_confirmed_by_chance", 0.0))
            out[kind] = {
                "total": int(t.get("total", 0)),
                "tested": tested,
                "confirmed": confirmed,
                "attenuated": int(t.get(VERDICT_ATTENUATED, 0)),
                "rejected": int(t.get(VERDICT_REJECTED, 0)),
                "insufficient_sample": int(t.get(VERDICT_INSUFFICIENT, 0)),
                "confirmed_rate_pct": round(confirmed / tested * 100.0, 2) if tested else None,
                "expected_by_chance": round(expected, 1),
                "expected_rate_pct": round(expected / tested * 100.0, 2) if tested else None,
            }
        return out


def _verify_group(
    db: Session,
    *,
    validation_run_id: int,
    target_type: str,
    candidates: list[CecchinoRunV2PatternInsightCandidate],
    discovery_matrix: RowMatrix,
    oos_matrix: RowMatrix,
    tally: _Tally,
) -> None:
    if not candidates:
        return
    null = NullModel(oos_matrix, deviation_threshold_pct=SYNTHETIC_CONFIRM_DEVIATION_PCT)
    oos_baseline = oos_matrix.baseline_win_rate_pct()
    records: list[dict[str, Any]] = []

    for c in candidates:
        combo = _combo(c)

        disc = discovery_matrix.stats(discovery_matrix.combo_mask(combo))
        tally.parity_checked += 1
        if disc["n"] != c.n or disc["wins"] != c.wins:
            tally.parity_mismatches += 1

        s = oos_matrix.stats(oos_matrix.combo_mask(combo))
        deviation = (
            round(s["win_rate_pct"] - oos_baseline, 3)
            if s["win_rate_pct"] is not None and oos_baseline is not None
            else None
        )

        null_prob: float | None
        if s["n"] < MIN_OOS_SAMPLE:
            verdict, null_prob = VERDICT_INSUFFICIENT, None
        elif target_type == TARGET_TYPE_MARKET:
            verdict = VERDICT_CONFIRMED if (s["roi_pct"] or 0) > 0 else VERDICT_REJECTED
            null_prob = null.p_roi_positive(s["n"])
        else:
            direction = 1 if (c.deviation_pct or 0) >= 0 else -1
            dev = deviation or 0.0
            if dev * direction >= SYNTHETIC_CONFIRM_DEVIATION_PCT:
                verdict = VERDICT_CONFIRMED
            elif dev * direction > 0:
                verdict = VERDICT_ATTENUATED
            else:
                verdict = VERDICT_REJECTED
            null_prob = null.p_deviation(s["n"], direction=direction)

        tally.add(target_type, verdict, null_prob)
        records.append(
            {
                "validation_run_id": validation_run_id,
                "candidate_id": int(c.id),
                "n": s["n"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate_pct": _d(s["win_rate_pct"]),
                "roi_pct": _d(s["roi_pct"]),
                "profit_units": _d(s["profit_units"]),
                "avg_quota": _d(s["avg_quota"]),
                "baseline_win_rate_pct": _d(oos_baseline),
                "deviation_pct": _d(deviation),
                "verdict": verdict,
                "null_confirm_prob": _d(round(null_prob, 4) if null_prob is not None else None),
            }
        )

    db.execute(insert(CecchinoRunV2PatternValidation), records)
    db.commit()


def _execute_validation(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoRunV2PatternValidationRun, run_id)
        if not run:
            return
        run.status = STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()

        try:
            insight = db.get(CecchinoRunV2PatternInsightRun, int(run.insight_run_id))
            disc_id = int(insight.run_v2_run_id)
            oos_id = int(run.run_v2_run_id)
            insight_id = int(insight.id)

            groups = len(MARKET_KEYS) + len(SYNTHETIC_TARGETS)
            run.targets_total = groups
            db.commit()

            disc_binners = load_season_binners(db, run_id=disc_id)
            tally = _Tally()
            done = 0

            def progress(label: str) -> None:
                r = db.get(CecchinoRunV2PatternValidationRun, run_id)
                r.current_target_label = label
                r.targets_processed = done
                r.progress_pct = Decimal(str(round(done / groups * 100.0, 1)))
                db.commit()

            for mk in MARKET_KEYS:
                progress(target_label(mk))
                disc_rows = market_rows_from_raw(
                    load_market_raw(db, run_id=disc_id, market_key=mk), disc_binners
                )
                oos_rows = market_rows_from_raw(
                    load_market_raw(db, run_id=oos_id, market_key=mk), disc_binners
                )
                _verify_group(
                    db,
                    validation_run_id=run_id,
                    target_type=TARGET_TYPE_MARKET,
                    candidates=_candidates_for(db, insight_id, TARGET_TYPE_MARKET, mk, None),
                    discovery_matrix=RowMatrix(disc_rows),
                    oos_matrix=RowMatrix(oos_rows),
                    tally=tally,
                )
                done += 1

            for stat_key, _label, thresholds in SYNTHETIC_TARGETS:
                progress(target_label(stat_key, thresholds[0]).rsplit(" Over", 1)[0])
                disc_raw = load_synthetic_raw(db, run_id=disc_id, stat_key=stat_key)
                oos_raw = load_synthetic_raw(db, run_id=oos_id, stat_key=stat_key)
                for threshold in thresholds:
                    _verify_group(
                        db,
                        validation_run_id=run_id,
                        target_type=TARGET_TYPE_SYNTHETIC,
                        candidates=_candidates_for(
                            db, insight_id, TARGET_TYPE_SYNTHETIC, stat_key, threshold
                        ),
                        discovery_matrix=RowMatrix(
                            synthetic_rows_from_raw(disc_raw, disc_binners, threshold)
                        ),
                        oos_matrix=RowMatrix(
                            synthetic_rows_from_raw(oos_raw, disc_binners, threshold)
                        ),
                        tally=tally,
                    )
                done += 1

            run = db.get(CecchinoRunV2PatternValidationRun, run_id)
            run.targets_processed = groups
            run.progress_pct = Decimal("100.0")
            run.current_target_label = None
            run.summary_json = tally.summary()
            run.status = STATUS_COMPLETED
            run.completed_at = _utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoRunV2PatternValidationRun, run_id)
            if run:
                run.status = STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("run v2 pattern validation %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)
