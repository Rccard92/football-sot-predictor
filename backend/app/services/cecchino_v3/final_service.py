"""Test finale sulla stagione sotto chiave 2025/26 (Passo 4).

Tutto e' gia' congelato prima di questo calcolo: modello (Fase 4 esteso),
pattern V3 e V2 gia' scoperti e verificati, regole dei valutatori. Qui si
misura soltanto, una volta, e si confronta V3 con V2.
"""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_v3 import (
    V3_ACTIVE_STATUSES,
    V3_STATUS_COMPLETED,
    V3_STATUS_FAILED,
    V3_STATUS_PENDING,
    V3_STATUS_RUNNING,
    CecchinoV3FinalRun,
    CecchinoV3Pattern,
    CecchinoV3PatternRun,
    CecchinoV3Run,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields
from app.services.cecchino_v3.constants import (
    EVALUATOR_INFO_FAMILIES,
    EVALUATOR_PRINCIPAL_MARKETS,
    FINAL_ENGINE_VERSION,
    FINAL_MAX_BOOK_GAP_PCT,
    FINAL_MAX_PROB_DIFF,
    FINAL_MIN_LIFT,
    JUDGE_SEASONS,
    LOCKBOX,
    MARKET_FAMILY,
    PATTERN_FROZEN_FROM,
    PATTERN_MIN_SAMPLE,
    PHASE_FEATURES,
    STRATEGY_MAIN,
    STRATEGY_V3_PURE,
    V2_INSIGHT_ODDS_MODE,
)
from app.services.cecchino_v3.evaluator import (
    MarketRow,
    combine_walk_forward,
    final_phase_rules,
    information_exam,
    information_table,
    select_plays,
    summarize,
)
from app.services.cecchino_v3.evaluator_service import (
    INFORMATION_GROUPS,
    load_market_rows,
    load_opening,
    opening_market_rows,
)
from app.services.cecchino_v3.pattern_service import _index_run_for, load_contexts
from app.services.cecchino_v3.pattern_service import load_opening as load_opening_quotes
from app.services.cecchino_v3.patterns import (
    PATTERN_COLUMNS,
    MarketMatrix,
    Pattern,
    build_matrices,
    frozen_test,
    market_move_analysis,
    validate,
    validation_tally,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}
FAMILIES: tuple[str, ...] = ("FT_1X2", "DOUBLE_CHANCE", "FT_OVER_UNDER", "HT_1X2")
_MISSING_CODE = -2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_to_dict(run: CecchinoV3FinalRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "status": run.status,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "current_step": run.current_step,
        "config": run.config_json,
        "summary": run.summary_json,
        "error": run.error_json,
    }


def _is_final(run: CecchinoV3Run) -> bool:
    phase = int((run.config_json or {}).get("phase") or 1)
    return bool(PHASE_FEATURES.get(phase) and PHASE_FEATURES[phase].lockbox)


def _final_model_run(db: Session) -> CecchinoV3Run | None:
    for run in db.scalars(
        select(CecchinoV3Run).where(CecchinoV3Run.status == V3_STATUS_COMPLETED).order_by(CecchinoV3Run.id.desc())
    ):
        if _is_final(run):
            return run
    return None


def _reference_model_run(db: Session) -> CecchinoV3Run | None:
    for run in db.scalars(
        select(CecchinoV3Run).where(CecchinoV3Run.status == V3_STATUS_COMPLETED).order_by(CecchinoV3Run.id.desc())
    ):
        if (run.config_json or {}).get("reference_model"):
            return run
    return None


def start_final_run(db: Session) -> dict[str, Any]:
    active = db.scalars(select(CecchinoV3FinalRun).where(CecchinoV3FinalRun.status.in_(V3_ACTIVE_STATUSES))).first()
    if active:
        raise CecchinoLabImportError("duplicate_active_run", f"Test finale gia' in corso (id={active.id})", status_code=409)
    final_model = _final_model_run(db)
    reference = _reference_model_run(db)
    if final_model is None or reference is None:
        raise CecchinoLabImportError("final_model_missing", "Serve il calcolo V3 finale completato", status_code=400)
    index_run = _index_run_for(db, int(final_model.id))
    if index_run is None:
        raise CecchinoLabImportError("indices_missing", "Servono gli indici del calcolo finale", status_code=400)
    pattern_run = db.scalars(
        select(CecchinoV3PatternRun)
        .where(CecchinoV3PatternRun.status == V3_STATUS_COMPLETED, CecchinoV3PatternRun.source_run_id == reference.id)
        .order_by(CecchinoV3PatternRun.completed_at.desc())
    ).first()
    if pattern_run is None:
        raise CecchinoLabImportError("patterns_missing", "Serve la ricerca pattern V3 completata", status_code=400)
    run = CecchinoV3FinalRun(
        engine_version=FINAL_ENGINE_VERSION,
        status=V3_STATUS_PENDING,
        requested_at=_utcnow(),
        config_json={
            "engine_version": FINAL_ENGINE_VERSION,
            "lockbox": LOCKBOX,
            "final_model_run_id": int(final_model.id),
            "reference_model_run_id": int(reference.id),
            "index_run_id": int(index_run.id),
            "pattern_run_id": int(pattern_run.id),
            "max_prob_diff": FINAL_MAX_PROB_DIFF,
            "max_book_gap_pct": FINAL_MAX_BOOK_GAP_PCT,
            "min_lift": FINAL_MIN_LIFT,
        },
        source_git_commit=revision_as_source_fields().get("source_git_commit"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    with _lock:
        t = threading.Thread(target=_execute, args=(int(run.id),), name=f"cecchino-v3-final-{run.id}", daemon=True)
        _active_threads[int(run.id)] = t
        t.start()
    return run_to_dict(run)


def latest_final_runs(db: Session) -> dict[str, Any]:
    latest = db.scalars(select(CecchinoV3FinalRun).order_by(CecchinoV3FinalRun.id.desc())).first()
    completed = db.scalars(
        select(CecchinoV3FinalRun)
        .where(CecchinoV3FinalRun.status == V3_STATUS_COMPLETED)
        .order_by(CecchinoV3FinalRun.completed_at.desc())
    ).first()
    return {"latest": run_to_dict(latest) if latest else None, "completed": run_to_dict(completed) if completed else None}


# --- misure --------------------------------------------------------------------------------


def integrity(db: Session, final_run_id: int, reference_run_id: int) -> dict[str, Any]:
    r = db.execute(
        text(
            """
            SELECT count(*) AS n,
                   max(abs(a.probability - b.probability)) AS max_diff
            FROM cecchino_v3_market_predictions a
            JOIN cecchino_v3_market_predictions b
              ON b.run_id = :ref AND b.lab_match_id = a.lab_match_id AND b.market_key = a.market_key
            WHERE a.run_id = :final
            """
        ),
        {"ref": reference_run_id, "final": final_run_id},
    ).first()
    reference_n = int(
        db.scalar(text("SELECT count(*) FROM cecchino_v3_market_predictions WHERE run_id = :ref"), {"ref": reference_run_id})
        or 0
    )
    lockbox_n = int(
        db.scalar(
            text(
                """
                SELECT count(*) FROM cecchino_v3_match_predictions
                WHERE run_id = :final AND season_label = :lockbox
                """
            ),
            {"final": final_run_id, "lockbox": LOCKBOX},
        )
        or 0
    )
    max_diff = float(r.max_diff) if r.max_diff is not None else None
    compared = int(r.n or 0)
    passed = compared == reference_n and compared > 0 and max_diff is not None and max_diff < FINAL_MAX_PROB_DIFF
    return {
        "compared_probabilities": compared,
        "reference_probabilities": reference_n,
        "max_diff": max_diff,
        "lockbox_matches": lockbox_n,
        "passed": bool(passed and lockbox_n > 0),
    }


def load_v2_probabilities(db: Session) -> dict[tuple[int, str], float]:
    out: dict[tuple[int, str], float] = {}
    for r in db.execute(
        text(
            """
            WITH v2_runs AS (
                SELECT DISTINCT ON (summary_json->>'season_label') id
                FROM cecchino_run_v2_runs
                WHERE status = 'completed' AND run_scope = 'full'
                  AND summary_json->>'season_label' <= :lockbox
                ORDER BY summary_json->>'season_label', completed_at DESC
            )
            SELECT s.lab_match_id, r.market_key, r.probability
            FROM cecchino_run_v2_market_results r
            JOIN v2_runs ON v2_runs.id = r.run_id
            JOIN cecchino_run_v2_match_snapshots s ON s.id = r.match_snapshot_id
            WHERE s.eligibility_status = 'eligible_core'
              AND r.observation_layer = 'core_strict'
              AND r.pre_match_input_safe IS TRUE
              AND r.probability IS NOT NULL
            """
        ),
        {"lockbox": LOCKBOX},
    ):
        out[(int(r.lab_match_id), r.market_key)] = float(r.probability)
    return out


def accuracy(rows: list[MarketRow], v2: dict[tuple[int, str], float], seasons: tuple[str, ...]) -> list[dict[str, Any]]:
    out = []
    for season in seasons:
        for family in FAMILIES:
            subset = [
                r for r in rows
                if r.eligible and r.season_label == season and MARKET_FAMILY[r.market_key] == family
                and (r.lab_match_id, r.market_key) in v2
            ]
            if not subset:
                out.append({"season": season, "family": family, "n": 0})
                continue
            y = np.array([float(r.won) for r in subset])
            b3 = float(np.mean((y - np.array([r.p_v3 for r in subset])) ** 2))
            b2 = float(np.mean((y - np.array([v2[(r.lab_match_id, r.market_key)] for r in subset])) ** 2))
            bb = float(np.mean((y - np.array([r.p_book for r in subset])) ** 2))
            out.append(
                {
                    "season": season,
                    "family": family,
                    "n": len(subset),
                    "brier_v3": round(b3, 6),
                    "brier_v2": round(b2, 6),
                    "brier_book": round(bb, 6),
                    "v3_vs_v2_pct": round((b3 / b2 - 1.0) * 100.0, 3),
                    "v3_vs_book_pct": round((b3 / bb - 1.0) * 100.0, 3),
                    "v2_vs_book_pct": round((b2 / bb - 1.0) * 100.0, 3),
                }
            )
    return out


def _stored_patterns(db: Session, pattern_run_id: int, matrices: dict[str, MarketMatrix]) -> list[tuple[Pattern, bool]]:
    out: list[tuple[Pattern, bool]] = []
    for rec in db.scalars(select(CecchinoV3Pattern).where(CecchinoV3Pattern.pattern_run_id == pattern_run_id)):
        matrix = matrices.get(rec.market_key)
        if matrix is None:
            continue
        combo = []
        for cond in rec.conditions_json:
            c = PATTERN_COLUMNS.index(cond["column"])
            values = matrix.values[c]
            combo.append((c, values.index(cond["value"]) if cond["value"] in values else _MISSING_CODE))
        pattern = Pattern(
            market_key=rec.market_key,
            combo=tuple(combo),
            conditions=list(rec.conditions_json),
            discovery={"n": rec.discovery_n, "roi": float(rec.discovery_roi)},
            seasons=dict(rec.seasons_json),
        )
        out.append((pattern, bool(rec.confirmed_all)))
    return out


def v3_patterns_on_lockbox(
    db: Session, rows: list[MarketRow], index_run_id: int, pattern_run: CecchinoV3PatternRun
) -> dict[str, Any]:
    contexts = load_contexts(db, index_run_id)
    edges = (pattern_run.summary_json or {})["edges"]
    matrices = build_matrices(rows, contexts, edges)
    stored = _stored_patterns(db, int(pattern_run.id), matrices)
    by_market: dict[str, list[Pattern]] = {}
    for pattern, _ in stored:
        by_market.setdefault(pattern.market_key, []).append(pattern)
    for market, patterns in by_market.items():
        validate(matrices[market], patterns, (LOCKBOX,))
    patterns = [p for p, _ in stored]
    tally = validation_tally(patterns, (LOCKBOX,))
    always = frozen_test(matrices, patterns, from_seasons=JUDGE_SEASONS, target_season=LOCKBOX)
    frozen = frozen_test(matrices, patterns, from_seasons=PATTERN_FROZEN_FROM, target_season=LOCKBOX)
    return {"tally": tally, "always_confirmed": always, "frozen_22_24": frozen}


def v2_patterns_on_lockbox(db: Session) -> dict[str, Any] | None:
    insight = db.execute(
        text(
            """
            SELECT id FROM cecchino_run_v2_pattern_insight_runs
            WHERE status = 'completed' AND odds_mode = :mode
            ORDER BY completed_at DESC LIMIT 1
            """
        ),
        {"mode": V2_INSIGHT_ODDS_MODE},
    ).first()
    if insight is None:
        return None
    ids = {
        r.season_label: int(r.id)
        for r in db.execute(
            text(
                """
                SELECT DISTINCT ON (season_label) id, season_label
                FROM cecchino_run_v2_pattern_validation_runs
                WHERE insight_run_id = :iid AND status = 'completed'
                ORDER BY season_label, completed_at DESC
                """
            ),
            {"iid": int(insight.id)},
        )
    }
    if LOCKBOX not in ids or any(s not in ids for s in JUDGE_SEASONS):
        return None
    t = db.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE v.verdict <> 'insufficient_sample') AS tested,
                   count(*) FILTER (WHERE v.verdict = 'confirmed') AS confirmed,
                   coalesce(sum(v.null_confirm_prob) FILTER (WHERE v.verdict <> 'insufficient_sample'), 0) AS expected
            FROM cecchino_run_v2_pattern_validations v
            JOIN cecchino_run_v2_pattern_insight_candidates c ON c.id = v.candidate_id
            WHERE v.validation_run_id = :vid AND c.target_type = 'market' AND c.n >= :min_n
            """
        ),
        {"vid": ids[LOCKBOX], "min_n": PATTERN_MIN_SAMPLE},
    ).first()
    tested, confirmed, expected = int(t.tested or 0), int(t.confirmed or 0), float(t.expected or 0.0)
    a = db.execute(
        text(
            """
            WITH per AS (
                SELECT c.id,
                       count(*) FILTER (WHERE v.validation_run_id = ANY(:judge) AND v.verdict = 'confirmed') AS ok,
                       max(v.n) FILTER (WHERE v.validation_run_id = :lock) AS n_l,
                       max(v.roi_pct) FILTER (WHERE v.validation_run_id = :lock) AS roi_l
                FROM cecchino_run_v2_pattern_validations v
                JOIN cecchino_run_v2_pattern_insight_candidates c ON c.id = v.candidate_id
                WHERE v.validation_run_id = ANY(:all_ids) AND c.target_type = 'market' AND c.n >= :min_n
                GROUP BY c.id
            )
            SELECT count(*) AS patterns,
                   coalesce(sum(n_l) FILTER (WHERE roi_l IS NOT NULL), 0) AS bets,
                   sum(n_l * roi_l) / NULLIF(sum(n_l) FILTER (WHERE roi_l IS NOT NULL), 0) AS pooled_roi
            FROM per WHERE ok = :k
            """
        ),
        {
            "judge": [ids[s] for s in JUDGE_SEASONS],
            "lock": ids[LOCKBOX],
            "all_ids": [ids[s] for s in (*JUDGE_SEASONS, LOCKBOX)],
            "min_n": PATTERN_MIN_SAMPLE,
            "k": len(JUDGE_SEASONS),
        },
    ).first()
    return {
        "tally": {
            "season": LOCKBOX,
            "tested": tested,
            "confirmed": confirmed,
            "expected": round(expected, 1),
            "confirmed_rate_pct": round(confirmed / tested * 100.0, 2) if tested else None,
            "expected_rate_pct": round(expected / tested * 100.0, 2) if tested else None,
            "lift": round(confirmed / expected, 3) if expected > 0 else None,
        },
        "always_confirmed": {
            "patterns": int(a.patterns or 0),
            "pooled_pattern_bets": int(a.bets or 0),
            "pooled_roi_pct": round(float(a.pooled_roi), 3) if a.pooled_roi is not None else None,
        },
    }


def evaluator_on_lockbox(rows: list[MarketRow]) -> dict[str, Any]:
    combined = combine_walk_forward(rows).probability
    v3 = {(r.lab_match_id, r.market_key): r.p_v3 for r in rows}
    groups = {k: v for k, v in INFORMATION_GROUPS.items() if all(key in {r.market_key for r in rows} for key in v)}
    table = information_table(rows, combined, groups, (LOCKBOX,))
    rules = final_phase_rules(rows, combined, (LOCKBOX,))
    main = select_plays(STRATEGY_MAIN, rows, combined, combined, EVALUATOR_PRINCIPAL_MARKETS, rules, (LOCKBOX,))
    pure = select_plays(STRATEGY_V3_PURE, rows, v3, combined, EVALUATOR_PRINCIPAL_MARKETS, rules, (LOCKBOX,))
    return {
        "information": table,
        "information_exam": information_exam(table, EVALUATOR_INFO_FAMILIES.keys(), (LOCKBOX,)),
        STRATEGY_MAIN: summarize(main),
        STRATEGY_V3_PURE: summarize(pure),
    }


def final_exam(
    integrity_block: dict[str, Any],
    accuracy_rows: list[dict[str, Any]],
    v3_patterns: dict[str, Any],
    v2_patterns: dict[str, Any] | None,
) -> dict[str, Any]:
    lock_rows = {r["family"]: r for r in accuracy_rows if r["season"] == LOCKBOX}
    f1_available = all(lock_rows.get(f, {}).get("n", 0) > 0 for f in FAMILIES)
    f1 = (
        f1_available
        and all(lock_rows[f]["brier_v3"] < lock_rows[f]["brier_v2"] for f in FAMILIES)
        and lock_rows["FT_1X2"]["v3_vs_book_pct"] <= FINAL_MAX_BOOK_GAP_PCT
    )
    tally = v3_patterns["tally"]["per_season"][0]
    always = v3_patterns["always_confirmed"]
    f2 = (
        tally["tested"] > 0
        and tally["confirmed"] > tally["expected"]
        and (tally["lift"] or 0.0) >= FINAL_MIN_LIFT
        and always["bets"] > 0
        and (always["roi_pct"] or 0.0) > 0
    )
    f3 = None
    if v2_patterns is not None:
        v2_lift = v2_patterns["tally"]["lift"] or 0.0
        v2_roi = v2_patterns["always_confirmed"]["pooled_roi_pct"]
        f3 = bool(
            (tally["lift"] or 0.0) > v2_lift
            and always["pooled_roi_pct"] is not None
            and v2_roi is not None
            and always["pooled_roi_pct"] > v2_roi
        )
    return {
        "F0": bool(integrity_block["passed"]),
        "F1": bool(f1),
        "F1_available": bool(f1_available),
        "F2": bool(f2),
        "F3": f3,
        "passed": bool(integrity_block["passed"] and f1 and f2 and f3),
    }


def _set_step(db: Session, run_id: int, step: str) -> None:
    run = db.get(CecchinoV3FinalRun, run_id)
    if run is not None:
        run.current_step = step[:128]
        db.commit()


def _execute(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoV3FinalRun, run_id)
        if run is None:
            return
        cfg = dict(run.config_json or {})
        run.status = V3_STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()
        try:
            final_id = int(cfg["final_model_run_id"])
            _set_step(db, run_id, "Integrita' del calcolo finale")
            integrity_block = integrity(db, final_id, int(cfg["reference_model_run_id"]))

            _set_step(db, run_id, "Caricamento previsioni 2021/22-2025/26 e quote")
            rows = load_market_rows(db, final_id, include_lockbox=True)
            v2 = load_v2_probabilities(db)
            accuracy_rows = accuracy(rows, v2, (*JUDGE_SEASONS, LOCKBOX))

            _set_step(db, run_id, "Pattern V3 e V2 sul 2025/26")
            pattern_run = db.get(CecchinoV3PatternRun, int(cfg["pattern_run_id"]))
            v3_patterns = v3_patterns_on_lockbox(db, rows, int(cfg["index_run_id"]), pattern_run)
            v2_patterns = v2_patterns_on_lockbox(db)

            _set_step(db, run_id, "Valutatori e movimento di mercato sul 2025/26")
            closing = evaluator_on_lockbox(rows)
            opening_rows = opening_market_rows(rows, load_opening(db, final_id))
            opening = evaluator_on_lockbox(opening_rows)
            move = market_move_analysis(rows, load_opening_quotes(db, final_id), seasons=(LOCKBOX,))

            summary = {
                "integrity": integrity_block,
                "accuracy": accuracy_rows,
                "v3_patterns": v3_patterns,
                "v2_patterns": v2_patterns,
                "v3_patterns_judge": (pattern_run.summary_json or {}).get("patterns"),
                "v2_patterns_judge": (pattern_run.summary_json or {}).get("v2"),
                "evaluator_closing": closing,
                "evaluator_opening": opening,
                "market_move": move,
                "exam": final_exam(integrity_block, accuracy_rows, v3_patterns, v2_patterns),
            }
            run = db.get(CecchinoV3FinalRun, run_id)
            run.summary_json = summary
            run.status = V3_STATUS_COMPLETED
            run.current_step = None
            run.completed_at = _utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoV3FinalRun, run_id)
            if run:
                run.status = V3_STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("cecchino v3 final run %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)
