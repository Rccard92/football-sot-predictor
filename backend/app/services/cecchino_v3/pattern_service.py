"""Calcolo e lettura dei pattern V3 (Passo 3c) e del movimento di mercato (3b),
con il confronto diretto con la ricerca pattern della V2."""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_v3 import (
    V3_ACTIVE_STATUSES,
    V3_STATUS_COMPLETED,
    V3_STATUS_FAILED,
    V3_STATUS_PENDING,
    V3_STATUS_RUNNING,
    CecchinoV3IndexRun,
    CecchinoV3Pattern,
    CecchinoV3PatternRun,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields
from app.services.cecchino_v3.constants import (
    JUDGE_SEASONS,
    PATTERN_DISCOVERY_SEASON,
    PATTERN_ENGINE_VERSION,
    PATTERN_FROZEN_FROM,
    PATTERN_FROZEN_SEASON,
    PATTERN_MIN_LIFT,
    PATTERN_MIN_PERSISTENCE_LIFT,
    PATTERN_MIN_SAMPLE,
    PATTERN_NULL_SAMPLES,
    PATTERN_QUANTILES,
    PATTERN_REFINEMENT_BASES,
    V2_INSIGHT_ODDS_MODE,
)
from app.services.cecchino_v3.evaluator import MarketRow, book_probabilities
from app.services.cecchino_v3.evaluator_service import load_market_rows
from app.services.cecchino_v3.index_service import _reference_run
from app.services.cecchino_v3.patterns import (
    VERDICT_CONFIRMED,
    MarketMatrix,
    MatchContext,
    OpeningQuote,
    Pattern,
    build_edges,
    build_matrices,
    discover,
    frozen_test,
    market_move_analysis,
    opening_plays_report,
    pattern_exam,
    validate,
    validation_tally,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}
_INSERT_CHUNK = 2000

# Riferimento del test congelato V2 con una giocata per partita per mercato,
# calcolato nell'analisi Pattern Insights del 2026-09-13 (le righe partita V2
# non sono salvate per pattern, quindi non si ricalcola qui).
V2_FROZEN_UNION_REFERENCE = {"patterns": 965, "bets": 39306, "roi_pct": -6.1, "source": "analisi Pattern Insights 2026-09-13"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_to_dict(run: CecchinoV3PatternRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "source_run_id": int(run.source_run_id),
        "index_run_id": int(run.index_run_id),
        "engine_version": run.engine_version,
        "status": run.status,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "current_step": run.current_step,
        "config": run.config_json,
        "summary": run.summary_json,
        "error": run.error_json,
    }


def _config(source_run_id: int, index_run_id: int) -> dict[str, Any]:
    return {
        "engine_version": PATTERN_ENGINE_VERSION,
        "source_run_id": source_run_id,
        "index_run_id": index_run_id,
        "discovery_season": PATTERN_DISCOVERY_SEASON,
        "validation_seasons": list(JUDGE_SEASONS),
        "min_sample": PATTERN_MIN_SAMPLE,
        "refinement_bases": PATTERN_REFINEMENT_BASES,
        "null_samples": PATTERN_NULL_SAMPLES,
        "quantiles": PATTERN_QUANTILES,
        "frozen_from": list(PATTERN_FROZEN_FROM),
        "frozen_season": PATTERN_FROZEN_SEASON,
        "min_lift": PATTERN_MIN_LIFT,
        "min_persistence_lift": PATTERN_MIN_PERSISTENCE_LIFT,
    }


def _index_run_for(db: Session, source_run_id: int) -> CecchinoV3IndexRun | None:
    return db.scalars(
        select(CecchinoV3IndexRun)
        .where(CecchinoV3IndexRun.status == V3_STATUS_COMPLETED, CecchinoV3IndexRun.source_run_id == source_run_id)
        .order_by(CecchinoV3IndexRun.completed_at.desc())
    ).first()


def start_pattern_run(db: Session) -> dict[str, Any]:
    active = db.scalars(select(CecchinoV3PatternRun).where(CecchinoV3PatternRun.status.in_(V3_ACTIVE_STATUSES))).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run", f"Esiste gia' una ricerca pattern in corso (id={active.id})", status_code=409
        )
    source = _reference_run(db)
    if source is None:
        raise CecchinoLabImportError("reference_missing", "Nessun modello V3 di riferimento", status_code=400)
    index_run = _index_run_for(db, int(source.id))
    if index_run is None:
        raise CecchinoLabImportError("indices_missing", "Indici V3 non calcolati", status_code=400)
    run = CecchinoV3PatternRun(
        source_run_id=int(source.id),
        index_run_id=int(index_run.id),
        engine_version=PATTERN_ENGINE_VERSION,
        status=V3_STATUS_PENDING,
        requested_at=_utcnow(),
        config_json=_config(int(source.id), int(index_run.id)),
        source_git_commit=revision_as_source_fields().get("source_git_commit"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    with _lock:
        t = threading.Thread(target=_execute, args=(int(run.id),), name=f"cecchino-v3-patterns-{run.id}", daemon=True)
        _active_threads[int(run.id)] = t
        t.start()
    return run_to_dict(run)


def _latest_completed(db: Session) -> CecchinoV3PatternRun | None:
    return db.scalars(
        select(CecchinoV3PatternRun)
        .where(CecchinoV3PatternRun.status == V3_STATUS_COMPLETED)
        .order_by(CecchinoV3PatternRun.completed_at.desc())
    ).first()


def latest_pattern_runs(db: Session) -> dict[str, Any]:
    latest = db.scalars(select(CecchinoV3PatternRun).order_by(CecchinoV3PatternRun.id.desc())).first()
    completed = _latest_completed(db)
    return {
        "latest": run_to_dict(latest) if latest else None,
        "completed": run_to_dict(completed) if completed else None,
    }


# --- caricamento --------------------------------------------------------------------------


def load_contexts(db: Session, index_run_id: int) -> dict[int, MatchContext]:
    out: dict[int, MatchContext] = {}
    for r in db.execute(
        text(
            """
            SELECT lab_match_id,
                   indices_json->'equilibrio'->>'class' AS equilibrio,
                   indices_json->'pareggio'->>'class' AS pareggio,
                   indices_json->'intensita_goal'->>'class' AS intensita,
                   (indices_json->'affidabilita'->'sign_support'->>'agents_agree')::int AS agree,
                   (indices_json->'forma'->'home'->>'gioco')::double precision AS form_home,
                   (indices_json->'forma'->'away'->>'gioco')::double precision AS form_away,
                   (indices_json->'calendario'->>'rest_diff')::int AS rest_diff
            FROM cecchino_v3_match_indices
            WHERE index_run_id = :rid
            """
        ),
        {"rid": index_run_id},
    ):
        form_diff = (
            float(r.form_home) - float(r.form_away) if r.form_home is not None and r.form_away is not None else None
        )
        out[int(r.lab_match_id)] = MatchContext(
            equilibrio=r.equilibrio,
            pareggio=r.pareggio,
            intensita_goal=r.intensita,
            agents_agree=r.agree,
            form_diff=form_diff,
            rest_diff=r.rest_diff,
        )
    return out


def load_opening(db: Session, source_run_id: int) -> dict[tuple[int, str], OpeningQuote]:
    out: dict[tuple[int, str], OpeningQuote] = {}
    for r in db.execute(
        text(
            """
            SELECT m.id, m.bet365_home AS home, m.bet365_draw AS draw, m.bet365_away AS away,
                   m.bet365_over_25 AS over_25, m.bet365_under_25 AS under_25
            FROM cecchino_lab_matches m
            JOIN cecchino_v3_match_predictions mp ON mp.lab_match_id = m.id AND mp.run_id = :run_id
            """
        ),
        {"run_id": source_run_id},
    ):
        odds = {k: (float(v) if v is not None else None) for k, v in dict(r._mapping).items() if k != "id"}
        for market, (quoted, p_book) in book_probabilities(odds).items():
            if market in ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5"):
                out[(int(r.id), market)] = OpeningQuote(odds=quoted, p_book=p_book)
    return out


# --- confronto con la V2 -----------------------------------------------------------------


def v2_comparison(db: Session) -> dict[str, Any] | None:
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
    validations = db.execute(
        text(
            """
            SELECT DISTINCT ON (season_label) id, season_label
            FROM cecchino_run_v2_pattern_validation_runs
            WHERE insight_run_id = :iid AND status = 'completed'
            ORDER BY season_label, completed_at DESC
            """
        ),
        {"iid": int(insight.id)},
    ).all()
    ids = {r.season_label: int(r.id) for r in validations}
    seasons = [s for s in JUDGE_SEASONS if s in ids]
    discovered = int(
        db.scalar(
            text(
                """
                SELECT count(*) FROM cecchino_run_v2_pattern_insight_candidates
                WHERE insight_run_id = :iid AND target_type = 'market' AND n >= :min_n
                """
            ),
            {"iid": int(insight.id), "min_n": PATTERN_MIN_SAMPLE},
        )
        or 0
    )
    per_season = []
    total_confirmed, total_expected = 0, 0.0
    for season in seasons:
        r = db.execute(
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
            {"vid": ids[season], "min_n": PATTERN_MIN_SAMPLE},
        ).first()
        tested, confirmed, expected = int(r.tested or 0), int(r.confirmed or 0), float(r.expected or 0.0)
        total_confirmed += confirmed
        total_expected += expected
        per_season.append(
            {
                "season": season,
                "tested": tested,
                "confirmed": confirmed,
                "expected": round(expected, 1),
                "confirmed_rate_pct": round(confirmed / tested * 100.0, 2) if tested else None,
                "expected_rate_pct": round(expected / tested * 100.0, 2) if tested else None,
                "lift": round(confirmed / expected, 3) if expected > 0 else None,
            }
        )

    persistence = None
    frozen = None
    if len(seasons) == len(JUDGE_SEASONS):
        k = len(seasons)
        r = db.execute(
            text(
                """
                WITH per AS (
                    SELECT c.id,
                           count(*) FILTER (WHERE v.verdict <> 'insufficient_sample') AS tested,
                           count(*) FILTER (WHERE v.verdict = 'confirmed') AS confirmed,
                           exp(sum(ln(greatest(coalesce(v.null_confirm_prob, 0), 1e-9)))) AS p_all
                    FROM cecchino_run_v2_pattern_validations v
                    JOIN cecchino_run_v2_pattern_insight_candidates c ON c.id = v.candidate_id
                    WHERE v.validation_run_id = ANY(:ids) AND c.target_type = 'market' AND c.n >= :min_n
                    GROUP BY c.id
                )
                SELECT count(*) FILTER (WHERE tested = :k) AS tested,
                       count(*) FILTER (WHERE tested = :k AND confirmed = :k) AS confirmed,
                       coalesce(sum(p_all) FILTER (WHERE tested = :k), 0) AS expected
                FROM per
                """
            ),
            {"ids": [ids[s] for s in seasons], "min_n": PATTERN_MIN_SAMPLE, "k": k},
        ).first()
        tested, confirmed, expected = int(r.tested or 0), int(r.confirmed or 0), float(r.expected or 0.0)
        persistence = {
            "season": "tutte",
            "tested": tested,
            "confirmed": confirmed,
            "expected": round(expected, 1),
            "confirmed_rate_pct": round(confirmed / tested * 100.0, 2) if tested else None,
            "expected_rate_pct": round(expected / tested * 100.0, 2) if tested else None,
            "lift": round(confirmed / expected, 3) if expected > 0 else None,
        }
        f = db.execute(
            text(
                """
                WITH per AS (
                    SELECT c.id,
                           count(*) FILTER (WHERE v.validation_run_id = ANY(:from_ids) AND v.verdict = 'confirmed') AS ok,
                           max(v.n) FILTER (WHERE v.validation_run_id = :target) AS n_t,
                           max(v.roi_pct) FILTER (WHERE v.validation_run_id = :target) AS roi_t
                    FROM cecchino_run_v2_pattern_validations v
                    JOIN cecchino_run_v2_pattern_insight_candidates c ON c.id = v.candidate_id
                    WHERE v.validation_run_id = ANY(:all_ids) AND c.target_type = 'market' AND c.n >= :min_n
                    GROUP BY c.id
                )
                SELECT count(*) AS patterns,
                       coalesce(sum(n_t), 0) AS bets,
                       sum(n_t * roi_t) / NULLIF(sum(n_t) FILTER (WHERE roi_t IS NOT NULL), 0) AS pooled_roi
                FROM per WHERE ok = :n_from
                """
            ),
            {
                "from_ids": [ids[s] for s in PATTERN_FROZEN_FROM],
                "target": ids[PATTERN_FROZEN_SEASON],
                "all_ids": [ids[s] for s in seasons],
                "min_n": PATTERN_MIN_SAMPLE,
                "n_from": len(PATTERN_FROZEN_FROM),
            },
        ).first()
        frozen = {
            "patterns": int(f.patterns or 0),
            "pooled_pattern_bets": int(f.bets or 0),
            "pooled_roi_pct": round(float(f.pooled_roi), 3) if f.pooled_roi is not None else None,
            "union_reference": V2_FROZEN_UNION_REFERENCE,
        }
    return {
        "insight_run_id": int(insight.id),
        "discovered": discovered,
        "per_season": per_season,
        "overall_lift": round(total_confirmed / total_expected, 3) if total_expected > 0 else None,
        "persistence": persistence,
        "frozen": frozen,
    }


# --- calcolo --------------------------------------------------------------------------------


def run_patterns(
    rows: list[MarketRow],
    contexts: dict[int, MatchContext],
    opening: dict[tuple[int, str], OpeningQuote],
) -> tuple[dict[str, Any], list[Pattern], dict[str, MarketMatrix]]:
    edges = build_edges(rows, contexts)
    matrices = build_matrices(rows, contexts, edges)
    patterns: list[Pattern] = []
    by_market = []
    for market, matrix in matrices.items():
        found = discover(matrix)
        validate(matrix, found, JUDGE_SEASONS)
        patterns.extend(found)
        tally = validation_tally(found, JUDGE_SEASONS)
        by_market.append({"market_key": market, **tally})
    tally = validation_tally(patterns, JUDGE_SEASONS)
    frozen = frozen_test(matrices, patterns)
    by_size = [
        {"size": size, **validation_tally([p for p in patterns if p.size == size], JUDGE_SEASONS)}
        for size in (1, 2, 3)
    ]
    summary = {
        "rows": len(rows),
        "edges": edges,
        "patterns": tally,
        "patterns_by_market": by_market,
        "patterns_by_size": by_size,
        "frozen": frozen,
        "exam": pattern_exam(tally, frozen),
        "market_move": market_move_analysis(rows, opening),
        "opening_plays": opening_plays_report(rows, opening),
    }
    return summary, patterns, matrices


def _pattern_record(run_id: int, p: Pattern) -> dict[str, Any]:
    confirmed_all = all(p.seasons.get(s, {}).get("verdict") == VERDICT_CONFIRMED for s in JUDGE_SEASONS)
    frozen = all(p.seasons.get(s, {}).get("verdict") == VERDICT_CONFIRMED for s in PATTERN_FROZEN_FROM)
    return {
        "pattern_run_id": run_id,
        "market_key": p.market_key,
        "size": p.size,
        "label": p.label[:512],
        "conditions_json": p.conditions,
        "discovery_n": int(p.discovery["n"]),
        "discovery_roi": Decimal(str(round(p.discovery["roi"], 5))),
        "seasons_json": {
            s: {k: (round(v, 6) if isinstance(v, float) else v) for k, v in stats.items()}
            for s, stats in p.seasons.items()
        },
        "confirmed_all": confirmed_all,
        "frozen": frozen,
    }


def _set_step(db: Session, run_id: int, step: str) -> None:
    run = db.get(CecchinoV3PatternRun, run_id)
    if run is not None:
        run.current_step = step[:128]
        db.commit()


def _execute(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoV3PatternRun, run_id)
        if run is None:
            return
        run.status = V3_STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()
        try:
            _set_step(db, run_id, "Caricamento previsioni, quote e indici")
            rows = load_market_rows(db, int(run.source_run_id))
            contexts = load_contexts(db, int(run.index_run_id))
            opening = load_opening(db, int(run.source_run_id))
            _set_step(db, run_id, "Scoperta e verifica dei pattern")
            summary, patterns, _ = run_patterns(rows, contexts, opening)
            _set_step(db, run_id, "Confronto con la V2")
            summary["v2"] = v2_comparison(db)

            _set_step(db, run_id, "Salvataggio pattern")
            records = [_pattern_record(run_id, p) for p in patterns]
            for start in range(0, len(records), _INSERT_CHUNK):
                db.execute(insert(CecchinoV3Pattern), records[start : start + _INSERT_CHUNK])
                db.commit()

            run = db.get(CecchinoV3PatternRun, run_id)
            run.summary_json = summary
            run.status = V3_STATUS_COMPLETED
            run.current_step = None
            run.completed_at = _utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoV3PatternRun, run_id)
            if run:
                run.status = V3_STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("cecchino v3 pattern run %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)


# --- lettura -------------------------------------------------------------------------------


def list_patterns(
    db: Session,
    *,
    market_key: str | None,
    only: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    run = _latest_completed(db)
    if run is None:
        return {"pattern_run_id": None, "total": 0, "items": []}
    p = CecchinoV3Pattern
    filters = [p.pattern_run_id == run.id]
    if market_key:
        filters.append(p.market_key == market_key)
    if only == "confirmed_all":
        filters.append(p.confirmed_all.is_(True))
    elif only == "frozen":
        filters.append(p.frozen.is_(True))
    total = int(db.scalar(select(func.count(p.id)).where(*filters)) or 0)
    rows = db.scalars(
        select(p).where(*filters).order_by(p.discovery_roi.desc(), p.id).limit(limit).offset(offset)
    ).all()
    return {
        "pattern_run_id": int(run.id),
        "total": total,
        "items": [
            {
                "id": int(r.id),
                "market_key": r.market_key,
                "size": r.size,
                "conditions": r.conditions_json,
                "discovery_n": r.discovery_n,
                "discovery_roi": float(r.discovery_roi),
                "seasons": r.seasons_json,
                "confirmed_all": r.confirmed_all,
                "frozen": r.frozen,
            }
            for r in rows
        ],
    }
