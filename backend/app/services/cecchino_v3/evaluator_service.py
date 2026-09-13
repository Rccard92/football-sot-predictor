"""Calcolo e lettura del valutatore di mercato (Passo 3).

Sorgente: il calcolo V3 segnato come modello di riferimento, piu' le quote
della tabella partite. La stagione sotto chiave non viene mai caricata.
"""

from __future__ import annotations

import logging
import threading
import traceback
from dataclasses import replace
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
    CecchinoV3EvaluatorPlay,
    CecchinoV3EvaluatorRun,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields
from app.services.cecchino_data_lab.run_v2_scope import tier_of
from app.services.cecchino_v3.constants import (
    EVALUATOR_EDGE_GRID,
    EVALUATOR_ENGINE_VERSION,
    EVALUATOR_INFO_FAMILIES,
    EVALUATOR_L2,
    EVALUATOR_MAX_ODDS,
    EVALUATOR_MAX_PLAYS_PER_DAY,
    EVALUATOR_MIN_EDGE,
    EVALUATOR_MIN_ODDS,
    EVALUATOR_MIN_PLAYS,
    EVALUATOR_MIN_TRAIN_ROWS,
    EVALUATOR_ODDS_CLOSING,
    EVALUATOR_ODDS_OPENING,
    EVALUATOR_PRINCIPAL_MARKETS,
    JUDGE_SEASONS,
    LOCKBOX,
    MARKET_KEYS,
    STRATEGY_ALL,
    STRATEGY_MAIN,
    STRATEGY_V3_PURE,
)
from app.services.cecchino_v3.data import load_matches
from app.services.cecchino_v3.evaluator import (
    MarketRow,
    Play,
    book_probabilities,
    combine_walk_forward,
    final_phase_rules,
    information_exam,
    information_table,
    playability_exam,
    select_plays,
    strategy_report,
    summarize,
)
from app.services.cecchino_v3.index_service import _reference_run
from app.services.cecchino_v3.markets import market_outcomes

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}
_INSERT_CHUNK = 2000

# Gruppi per la tabella "informazione oltre il mercato": i primi due fanno l'esame.
INFORMATION_GROUPS: dict[str, tuple[str, ...]] = {
    **EVALUATOR_INFO_FAMILIES,
    "DOPPIA_CHANCE": ("ONE_X", "X_TWO", "ONE_TWO"),
    "OU_0_5": ("OVER_0_5",),
    "OU_1_5": ("OVER_1_5",),
    "OU_3_5": ("OVER_3_5",),
    "HT_1X2": ("HOME_PT", "DRAW_PT", "AWAY_PT"),
}

_ODDS_COLUMNS: dict[str, str] = {
    "home": "bet365_closing_home",
    "draw": "bet365_closing_draw",
    "away": "bet365_closing_away",
    "over_25": "bet365_closing_over_25",
    "under_25": "bet365_closing_under_25",
    "over_05": "bet365_over_05",
    "under_05": "bet365_under_05",
    "over_15": "bet365_over_15",
    "under_15": "bet365_under_15",
    "over_35": "bet365_over_35",
    "under_35": "bet365_under_35",
    "ht_home": "bet365_ht_home",
    "ht_draw": "bet365_ht_draw",
    "ht_away": "bet365_ht_away",
    "dc_1x": "bet365_dc_1x",
    "dc_x2": "bet365_dc_x2",
    "dc_12": "bet365_dc_12",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_to_dict(run: CecchinoV3EvaluatorRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "source_run_id": int(run.source_run_id),
        "engine_version": run.engine_version,
        "status": run.status,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "current_step": run.current_step,
        "config": run.config_json,
        "summary": run.summary_json,
        "error": run.error_json,
    }


def _odds_mode(run: CecchinoV3EvaluatorRun) -> str:
    return (run.config_json or {}).get("odds_mode") or EVALUATOR_ODDS_CLOSING


def _config(source_run_id: int, odds_mode: str) -> dict[str, Any]:
    return {
        "engine_version": EVALUATOR_ENGINE_VERSION,
        "odds_mode": odds_mode,
        "source_run_id": source_run_id,
        "min_odds": EVALUATOR_MIN_ODDS,
        "max_odds": EVALUATOR_MAX_ODDS,
        "min_edge": EVALUATOR_MIN_EDGE,
        "max_plays_per_day": EVALUATOR_MAX_PLAYS_PER_DAY,
        "min_train_rows": EVALUATOR_MIN_TRAIN_ROWS,
        "l2": EVALUATOR_L2,
        "min_plays": EVALUATOR_MIN_PLAYS,
        "principal_markets": list(EVALUATOR_PRINCIPAL_MARKETS),
        "information_families": {k: list(v) for k, v in EVALUATOR_INFO_FAMILIES.items()},
        "judge_seasons": list(JUDGE_SEASONS),
        "lockbox": LOCKBOX,
    }


def start_evaluator_run(db: Session, odds_mode: str = EVALUATOR_ODDS_CLOSING) -> dict[str, Any]:
    if odds_mode not in (EVALUATOR_ODDS_CLOSING, EVALUATOR_ODDS_OPENING):
        raise CecchinoLabImportError("invalid_odds_mode", f"Quota non valida: {odds_mode}", status_code=400)
    active = db.scalars(
        select(CecchinoV3EvaluatorRun).where(CecchinoV3EvaluatorRun.status.in_(V3_ACTIVE_STATUSES))
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run", f"Esiste gia' un calcolo del valutatore in corso (id={active.id})", status_code=409
        )
    source = _reference_run(db)
    if source is None:
        raise CecchinoLabImportError(
            "reference_missing", "Nessun calcolo V3 segnato come modello di riferimento", status_code=400
        )
    run = CecchinoV3EvaluatorRun(
        source_run_id=int(source.id),
        engine_version=EVALUATOR_ENGINE_VERSION,
        status=V3_STATUS_PENDING,
        requested_at=_utcnow(),
        config_json=_config(int(source.id), odds_mode),
        source_git_commit=revision_as_source_fields().get("source_git_commit"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    with _lock:
        t = threading.Thread(target=_execute, args=(int(run.id),), name=f"cecchino-v3-evaluator-{run.id}", daemon=True)
        _active_threads[int(run.id)] = t
        t.start()
    return run_to_dict(run)


def _latest_completed(db: Session, odds_mode: str = EVALUATOR_ODDS_CLOSING) -> CecchinoV3EvaluatorRun | None:
    for run in db.scalars(
        select(CecchinoV3EvaluatorRun)
        .where(CecchinoV3EvaluatorRun.status == V3_STATUS_COMPLETED)
        .order_by(CecchinoV3EvaluatorRun.completed_at.desc())
    ):
        if _odds_mode(run) == odds_mode:
            return run
    return None


def latest_evaluator_runs(db: Session, odds_mode: str = EVALUATOR_ODDS_CLOSING) -> dict[str, Any]:
    latest = next(
        (
            r
            for r in db.scalars(select(CecchinoV3EvaluatorRun).order_by(CecchinoV3EvaluatorRun.id.desc()))
            if _odds_mode(r) == odds_mode
        ),
        None,
    )
    completed = _latest_completed(db, odds_mode)
    return {
        "latest": run_to_dict(latest) if latest else None,
        "completed": run_to_dict(completed) if completed else None,
    }


# --- calcolo ----------------------------------------------------------------------------


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def load_market_rows(db: Session, source_run_id: int, *, include_lockbox: bool = False) -> list[MarketRow]:
    matches = {m.lab_match_id: m for m in load_matches(db, include_lockbox=include_lockbox)}
    probabilities: dict[int, dict[str, float]] = {}
    for r in db.execute(
        text(
            """
            SELECT mk.lab_match_id, mk.market_key, mk.probability
            FROM cecchino_v3_market_predictions mk
            WHERE mk.run_id = :run_id
            """
        ),
        {"run_id": source_run_id},
    ):
        probabilities.setdefault(int(r.lab_match_id), {})[r.market_key] = float(r.probability)

    columns = ", ".join(f"m.{col} AS {key}" for key, col in _ODDS_COLUMNS.items())
    odds_by_match: dict[int, dict[str, float | None]] = {}
    for r in db.execute(
        text(
            f"""
            SELECT m.id, {columns}
            FROM cecchino_lab_matches m
            JOIN cecchino_v3_match_predictions mp ON mp.lab_match_id = m.id AND mp.run_id = :run_id
            """
        ),
        {"run_id": source_run_id},
    ):
        data = dict(r._mapping)
        odds_by_match[int(data.pop("id"))] = {k: _float(v) for k, v in data.items()}

    rows: list[MarketRow] = []
    for mid in sorted(probabilities):
        m = matches.get(mid)
        odds = odds_by_match.get(mid)
        if m is None or odds is None or m.season_label > LOCKBOX or (m.season_label == LOCKBOX and not include_lockbox):
            continue
        book = book_probabilities(odds)
        outcomes = market_outcomes(m.ft_home, m.ft_away, m.ht_home, m.ht_away)
        tier = tier_of(m.competition)
        for key in MARKET_KEYS:
            p_v3 = probabilities[mid].get(key)
            won = outcomes.get(key)
            if p_v3 is None or won is None or key not in book:
                continue
            quoted, p_book = book[key]
            rows.append(
                MarketRow(
                    lab_match_id=mid,
                    season_label=m.season_label,
                    competition=m.competition,
                    tier=tier,
                    match_date=m.match_date,
                    phase=m.phase,
                    eligible=m.eval_eligible,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    market_key=key,
                    p_v3=p_v3,
                    p_book=p_book,
                    odds=quoted,
                    won=bool(won),
                )
            )
    rows.sort(key=lambda r: (r.match_date, r.lab_match_id, r.market_key))
    return rows


_OPENING_COLUMNS: dict[str, str] = {
    "home": "bet365_home",
    "draw": "bet365_draw",
    "away": "bet365_away",
    "over_25": "bet365_over_25",
    "under_25": "bet365_under_25",
}


def load_opening(db: Session, source_run_id: int) -> dict[tuple[int, str], tuple[float, float]]:
    """(partita, mercato) -> (quota di apertura, probabilita' di apertura senza margine)."""
    columns = ", ".join(f"m.{col} AS {key}" for key, col in _OPENING_COLUMNS.items())
    out: dict[tuple[int, str], tuple[float, float]] = {}
    for r in db.execute(
        text(
            f"""
            SELECT m.id, {columns}
            FROM cecchino_lab_matches m
            JOIN cecchino_v3_match_predictions mp ON mp.lab_match_id = m.id AND mp.run_id = :run_id
            """
        ),
        {"run_id": source_run_id},
    ):
        data = dict(r._mapping)
        mid = int(data.pop("id"))
        for market, quote in book_probabilities({k: _float(v) for k, v in data.items()}).items():
            if market in EVALUATOR_PRINCIPAL_MARKETS:
                out[(mid, market)] = quote
    return out


def opening_market_rows(
    rows: list[MarketRow], opening: dict[tuple[int, str], tuple[float, float]]
) -> list[MarketRow]:
    """Stesse righe con quota e probabilita' del book di apertura (solo mercati che la hanno)."""
    out = []
    for r in rows:
        quote = opening.get((r.lab_match_id, r.market_key))
        if quote is not None:
            out.append(replace(r, odds=quote[0], p_book=quote[1]))
    return out


def _set_step(db: Session, run_id: int, step: str) -> None:
    run = db.get(CecchinoV3EvaluatorRun, run_id)
    if run is not None:
        run.current_step = step[:128]
        db.commit()


def _play_row(run_id: int, play: Play) -> dict[str, Any]:
    r = play.row
    return {
        "evaluator_run_id": run_id,
        "strategy": play.strategy,
        "lab_match_id": r.lab_match_id,
        "season_label": r.season_label,
        "match_date": r.match_date,
        "competition_name": r.competition,
        "home_team": r.home_team,
        "away_team": r.away_team,
        "phase": r.phase,
        "market_key": r.market_key,
        "odds": Decimal(str(round(r.odds, 3))),
        "p_v3": Decimal(str(round(r.p_v3, 7))),
        "p_book": Decimal(str(round(r.p_book, 7))),
        "p_eval": Decimal(str(round(play.p_eval, 7))) if play.p_eval is not None else None,
        "edge": Decimal(str(round(play.edge, 5))),
        "won": r.won,
        "profit": Decimal(str(round(play.profit, 3))),
    }


def run_evaluator(rows: list[MarketRow]) -> tuple[dict[str, Any], dict[str, list[Play]]]:
    """Tutto il Passo 3 su righe gia' caricate (usato dal job e dai test)."""
    combination = combine_walk_forward(rows)
    combined = combination.probability
    v3_probability = {(r.lab_match_id, r.market_key): r.p_v3 for r in rows}

    table = information_table(rows, combined, INFORMATION_GROUPS, JUDGE_SEASONS)
    info_exam = information_exam(table, EVALUATOR_INFO_FAMILIES.keys(), JUDGE_SEASONS)
    rules = final_phase_rules(rows, combined, JUDGE_SEASONS)

    strategies = {
        STRATEGY_MAIN: select_plays(
            STRATEGY_MAIN, rows, combined, combined, EVALUATOR_PRINCIPAL_MARKETS, rules, JUDGE_SEASONS
        ),
        STRATEGY_V3_PURE: select_plays(
            STRATEGY_V3_PURE, rows, v3_probability, combined, EVALUATOR_PRINCIPAL_MARKETS, rules, JUDGE_SEASONS
        ),
        STRATEGY_ALL: select_plays(STRATEGY_ALL, rows, combined, combined, MARKET_KEYS, rules, JUDGE_SEASONS),
    }
    edge_grid = []
    for edge in EVALUATOR_EDGE_GRID:
        plays = select_plays(
            STRATEGY_MAIN, rows, combined, combined, EVALUATOR_PRINCIPAL_MARKETS, rules, JUDGE_SEASONS, min_edge=edge
        )
        edge_grid.append(
            {
                "min_edge": edge,
                "total": summarize(plays),
                "by_season": [
                    {"season": s, **summarize([p for p in plays if p.row.season_label == s])} for s in JUDGE_SEASONS
                ],
            }
        )

    exam_g = playability_exam(strategies[STRATEGY_MAIN], JUDGE_SEASONS)
    summary = {
        "rows": len(rows),
        "matches": len({r.lab_match_id for r in rows}),
        "information": table,
        "information_exam": info_exam,
        "information_passed": all(e["passed"] for e in info_exam),
        "combination_models": combination.models,
        "final_phase_rules": [
            {"season": season, "family": family, **rule} for (season, family), rule in sorted(rules.items())
        ],
        "strategies": {code: strategy_report(plays) for code, plays in strategies.items()},
        "playability_exam": exam_g,
        "edge_grid": edge_grid,
    }
    return summary, strategies


def _execute(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoV3EvaluatorRun, run_id)
        if run is None:
            return
        run.status = V3_STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()
        source_run_id = int(run.source_run_id)
        try:
            _set_step(db, run_id, "Caricamento previsioni V3 e quote")
            rows = load_market_rows(db, source_run_id)
            if _odds_mode(run) == EVALUATOR_ODDS_OPENING:
                rows = opening_market_rows(rows, load_opening(db, source_run_id))
            _set_step(db, run_id, "Valutatore: informazione, fase finale, giocate")
            summary, strategies = run_evaluator(rows)

            _set_step(db, run_id, "Salvataggio giocate")
            records = [_play_row(run_id, p) for plays in strategies.values() for p in plays]
            for start in range(0, len(records), _INSERT_CHUNK):
                db.execute(insert(CecchinoV3EvaluatorPlay), records[start : start + _INSERT_CHUNK])
                db.commit()

            run = db.get(CecchinoV3EvaluatorRun, run_id)
            run.summary_json = summary
            run.status = V3_STATUS_COMPLETED
            run.current_step = None
            run.completed_at = _utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoV3EvaluatorRun, run_id)
            if run:
                run.status = V3_STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("cecchino v3 evaluator run %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)


# --- lettura ------------------------------------------------------------------------------


def list_plays(
    db: Session,
    *,
    strategy: str,
    odds_mode: str = EVALUATOR_ODDS_CLOSING,
    season_label: str | None,
    competition: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    run = _latest_completed(db, odds_mode)
    if run is None:
        return {"evaluator_run": None, "total": 0, "items": [], "competitions": []}
    p = CecchinoV3EvaluatorPlay
    filters = [p.evaluator_run_id == run.id, p.strategy == strategy]
    if season_label:
        filters.append(p.season_label == season_label)
    competitions = db.scalars(select(p.competition_name).where(*filters).distinct().order_by(p.competition_name)).all()
    if competition:
        filters.append(p.competition_name == competition)
    total = int(db.scalar(select(func.count(p.id)).where(*filters)) or 0)
    rows = db.scalars(
        select(p).where(*filters).order_by(p.match_date.desc(), p.edge.desc()).limit(limit).offset(offset)
    ).all()
    items = [
        {
            "lab_match_id": int(r.lab_match_id),
            "match_date": r.match_date.isoformat(),
            "season_label": r.season_label,
            "competition": r.competition_name,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "phase": r.phase,
            "market_key": r.market_key,
            "odds": float(r.odds),
            "p_v3": float(r.p_v3),
            "p_book": float(r.p_book),
            "p_eval": float(r.p_eval) if r.p_eval is not None else None,
            "edge": float(r.edge),
            "won": bool(r.won),
            "profit": float(r.profit),
        }
        for r in rows
    ]
    return {"evaluator_run_id": int(run.id), "total": total, "items": items, "competitions": list(competitions)}
