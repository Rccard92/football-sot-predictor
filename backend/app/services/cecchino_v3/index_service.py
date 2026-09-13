"""Calcolo e lettura degli indici a 360 gradi (Passo 2).

Sorgente: il calcolo V3 segnato come modello di riferimento. Gli indici sono
salvati per partita con i controlli di coerenza C1-C4 nel riepilogo.
"""

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
    CecchinoV3MarketPrediction,
    CecchinoV3MatchIndex,
    CecchinoV3MatchPrediction,
    CecchinoV3Run,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields
from app.services.cecchino_data_lab.run_v2_grid_dataset import _CLOSING_QUOTE_SQL
from app.services.cecchino_data_lab.run_v2_market_scoreboard import _FAIR_PROB_SQL
from app.services.cecchino_v3.constants import (
    INDEX_CLASS_EDGES,
    INDEX_CLASSES,
    INDEX_ENGINE_VERSION,
    INDEX_MIN_HISTORY,
    JUDGE_SEASONS,
    MARKET_KEYS,
    RELIABILITY_COMPONENTS,
    RELIABILITY_FORM_NEUTRAL,
    RELIABILITY_HIGH,
    RELIABILITY_IRREGULARITY_MATCHES,
    RELIABILITY_IRREGULARITY_MIN_MATCHES,
    RELIABILITY_MEDIUM,
    RELIABILITY_MIN_CLASS_SHARE,
)
from app.services.cecchino_v3.data import MatchRecord, group_matches, load_matches
from app.services.cecchino_v3.discipline import compute_discipline
from app.services.cecchino_v3.form import Expectation
from app.services.cecchino_v3.indices import IndexInput, coherence_checks, compute_indices
from app.services.cecchino_v3.reliability import compute_reliability, reliability_exam, sign_support_table
from app.services.cecchino_v3.walkforward import divisions_for, mover_flags

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}
_INSERT_CHUNK = 2000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def index_run_to_dict(run: CecchinoV3IndexRun) -> dict[str, Any]:
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


def _reference_run(db: Session) -> CecchinoV3Run | None:
    for run in db.scalars(
        select(CecchinoV3Run)
        .where(CecchinoV3Run.status == V3_STATUS_COMPLETED)
        .order_by(CecchinoV3Run.completed_at.desc())
    ):
        if (run.config_json or {}).get("reference_model"):
            return run
    return None


def _config(source_run_id: int) -> dict[str, Any]:
    return {
        "engine_version": INDEX_ENGINE_VERSION,
        "source_run_id": source_run_id,
        "min_history": INDEX_MIN_HISTORY,
        "class_edges": list(INDEX_CLASS_EDGES),
        "classes": list(INDEX_CLASSES),
        "reliability": {
            "components": list(RELIABILITY_COMPONENTS),
            "target": "errore in eccesso 1X2 (Brier reale - Brier atteso dal modello)",
            "weights": "minimi quadrati con pesi >= 0, stagioni precedenti (walk-forward)",
            "irregularity_matches": RELIABILITY_IRREGULARITY_MATCHES,
            "irregularity_min_matches": RELIABILITY_IRREGULARITY_MIN_MATCHES,
            "high": RELIABILITY_HIGH,
            "medium": RELIABILITY_MEDIUM,
            "min_class_share": RELIABILITY_MIN_CLASS_SHARE,
            "form_neutral": RELIABILITY_FORM_NEUTRAL,
            "book_odds_used": False,
        },
        "judge_seasons": list(JUDGE_SEASONS),
    }


def start_index_run(db: Session) -> dict[str, Any]:
    active = db.scalars(
        select(CecchinoV3IndexRun).where(CecchinoV3IndexRun.status.in_(V3_ACTIVE_STATUSES))
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run", f"Esiste gia' un calcolo indici in corso (id={active.id})", status_code=409
        )
    source = _reference_run(db)
    if source is None:
        raise CecchinoLabImportError(
            "reference_missing", "Nessun calcolo V3 segnato come modello di riferimento", status_code=400
        )
    run = CecchinoV3IndexRun(
        source_run_id=int(source.id),
        engine_version=INDEX_ENGINE_VERSION,
        status=V3_STATUS_PENDING,
        requested_at=_utcnow(),
        config_json=_config(int(source.id)),
        source_git_commit=revision_as_source_fields().get("source_git_commit"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    with _lock:
        t = threading.Thread(target=_execute, args=(int(run.id),), name=f"cecchino-v3-indices-{run.id}", daemon=True)
        _active_threads[int(run.id)] = t
        t.start()
    return index_run_to_dict(run)


def latest_index_runs(db: Session) -> dict[str, Any]:
    latest = db.scalars(select(CecchinoV3IndexRun).order_by(CecchinoV3IndexRun.id.desc())).first()
    completed = _latest_completed_index_run(db)
    return {
        "latest": index_run_to_dict(latest) if latest else None,
        "completed": index_run_to_dict(completed) if completed else None,
    }


def _latest_completed_index_run(db: Session) -> CecchinoV3IndexRun | None:
    return db.scalars(
        select(CecchinoV3IndexRun)
        .where(CecchinoV3IndexRun.status == V3_STATUS_COMPLETED)
        .order_by(CecchinoV3IndexRun.completed_at.desc())
    ).first()


# --- calcolo ----------------------------------------------------------------------------


def _new_team_flags(matches: list[MatchRecord]) -> dict[int, tuple[bool, bool]]:
    """Per ogni partita: squadra di casa/ospite neopromossa (rispetto alla stagione
    precedente) o nuova nel dataset, nella sua prima stagione."""
    out: dict[int, tuple[bool, bool]] = {}
    for group_list in group_matches(matches).values():
        div_index = {c: i for i, c in enumerate(divisions_for(group_list))}
        home_move, away_move = mover_flags(group_list, div_index)
        first_season = min(m.season_label for m in group_list)
        team_first: dict[str, str] = {}
        for m in group_list:
            for team in (m.home_team, m.away_team):
                if team not in team_first or m.season_label < team_first[team]:
                    team_first[team] = m.season_label
        for k, m in enumerate(group_list):
            late_entry = m.season_label > first_season
            out[m.lab_match_id] = (
                bool(home_move[k, 0]) or (late_entry and team_first[m.home_team] == m.season_label),
                bool(away_move[k, 0]) or (late_entry and team_first[m.away_team] == m.season_label),
            )
    return out


def _load_source(db: Session, source_run_id: int) -> dict[int, dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT mp.lab_match_id, mp.lambda_home, mp.lambda_away, mp.rho, mp.home_evidence, mp.away_evidence,
                   mp.specialists_json,
                   max(mk.probability) FILTER (WHERE mk.market_key = 'HOME') AS p_home,
                   max(mk.probability) FILTER (WHERE mk.market_key = 'DRAW') AS p_draw,
                   max(mk.probability) FILTER (WHERE mk.market_key = 'AWAY') AS p_away,
                   max(mk.probability) FILTER (WHERE mk.market_key = 'OVER_2_5') AS p_over_2_5
            FROM cecchino_v3_match_predictions mp
            JOIN cecchino_v3_market_predictions mk ON mk.match_prediction_id = mp.id
            WHERE mp.run_id = :run_id
            GROUP BY mp.id
            """
        ),
        {"run_id": source_run_id},
    )
    return {int(r.lab_match_id): dict(r._mapping) for r in rows}


def _set_step(db: Session, run_id: int, step: str) -> None:
    run = db.get(CecchinoV3IndexRun, run_id)
    if run is not None:
        run.current_step = step[:128]
        db.commit()


def _execute(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoV3IndexRun, run_id)
        if run is None:
            return
        run.status = V3_STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()
        source_run_id = int(run.source_run_id)
        try:
            _set_step(db, run_id, "Caricamento partite e previsioni del modello di riferimento")
            matches = load_matches(db)
            source = _load_source(db, source_run_id)
            matches = [m for m in matches if m.lab_match_id in source]

            _set_step(db, run_id, "Disciplina e squadre nuove")
            expectations = {
                mid: Expectation(float(s["lambda_home"]), float(s["lambda_away"]), None, None)
                for mid, s in source.items()
            }
            discipline = compute_discipline(matches, expectations)
            new_teams = _new_team_flags(matches)

            inputs = []
            for m in matches:
                s = source[m.lab_match_id]
                if None in (s["p_home"], s["p_draw"], s["p_away"], s["p_over_2_5"]):
                    continue
                new_home, new_away = new_teams.get(m.lab_match_id, (False, False))
                inputs.append(
                    IndexInput(
                        match=m,
                        prob_home=float(s["p_home"]),
                        prob_draw=float(s["p_draw"]),
                        prob_away=float(s["p_away"]),
                        prob_over_2_5=float(s["p_over_2_5"]),
                        lambda_home=float(s["lambda_home"]),
                        lambda_away=float(s["lambda_away"]),
                        home_evidence=float(s["home_evidence"]),
                        away_evidence=float(s["away_evidence"]),
                        specialists=s["specialists_json"] or {},
                        rho=float(s["rho"]),
                        new_team_home=new_home,
                        new_team_away=new_away,
                        discipline=discipline.get(m.lab_match_id),
                    )
                )

            _set_step(db, run_id, "Indici a 360 gradi")
            reliability = compute_reliability(inputs)
            indices = compute_indices(inputs, reliability.per_match)
            checks = coherence_checks(inputs, indices, JUDGE_SEASONS)
            reliability_checks = reliability_exam(
                inputs, reliability.per_match, JUDGE_SEASONS, RELIABILITY_MIN_CLASS_SHARE
            )

            _set_step(db, run_id, "Salvataggio")
            rows = []
            for item in inputs:
                idx = indices[item.match.lab_match_id]
                m = item.match
                rows.append(
                    {
                        "index_run_id": run_id,
                        "lab_match_id": m.lab_match_id,
                        "competition_name": m.competition,
                        "season_label": m.season_label,
                        "kickoff_at": m.kickoff_at,
                        "home_team": m.home_team,
                        "away_team": m.away_team,
                        "reliability": (
                            Decimal(str(idx["affidabilita"]["value"]))
                            if idx["affidabilita"]["value"] is not None
                            else None
                        ),
                        "reliability_class": idx["affidabilita"]["class"],
                        "equilibrio_class": idx["equilibrio"]["class"],
                        "pareggio_class": idx["pareggio"]["class"],
                        "intensita_class": idx["intensita_goal"]["class"],
                        "indices_json": idx,
                    }
                )
            for start in range(0, len(rows), _INSERT_CHUNK):
                db.execute(insert(CecchinoV3MatchIndex), rows[start : start + _INSERT_CHUNK])
                db.commit()

            distribution: dict[str, dict[str, int]] = {}
            for idx in indices.values():
                for name in ("equilibrio", "pareggio", "intensita_goal", "affidabilita"):
                    klass = idx[name]["class"] or "n.d."
                    distribution.setdefault(name, {}).setdefault(klass, 0)
                    distribution[name][klass] += 1

            run = db.get(CecchinoV3IndexRun, run_id)
            run.summary_json = {
                "matches": len(rows),
                "coherence_checks": checks,
                "reliability_checks": reliability_checks,
                "reliability_passed": all(c["passed"] for c in reliability_checks),
                "reliability_models": [model.summary() for model in reliability.models],
                "sign_support": sign_support_table(inputs, reliability.per_match, JUDGE_SEASONS),
                "all_checks_passed": all(c["passed"] for c in checks + reliability_checks),
                "class_distribution": distribution,
            }
            run.status = V3_STATUS_COMPLETED
            run.current_step = None
            run.completed_at = _utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.get(CecchinoV3IndexRun, run_id)
            if run:
                run.status = V3_STATUS_FAILED
                run.completed_at = _utcnow()
                run.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("cecchino v3 index run %s failed", run_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(run_id, None)


# --- lettura per la pagina "Partita per partita" --------------------------------------


def match_filters(db: Session) -> dict[str, Any]:
    run = _latest_completed_index_run(db)
    if run is None:
        return {"index_run": None, "competitions": [], "seasons": []}
    competitions = db.scalars(
        select(CecchinoV3MatchIndex.competition_name)
        .where(CecchinoV3MatchIndex.index_run_id == run.id)
        .distinct()
        .order_by(CecchinoV3MatchIndex.competition_name)
    ).all()
    seasons = db.scalars(
        select(CecchinoV3MatchIndex.season_label)
        .where(CecchinoV3MatchIndex.index_run_id == run.id)
        .distinct()
        .order_by(CecchinoV3MatchIndex.season_label.desc())
    ).all()
    return {"index_run": index_run_to_dict(run), "competitions": list(competitions), "seasons": list(seasons)}


def list_matches(
    db: Session,
    *,
    competition: str | None,
    season_label: str | None,
    team: str | None,
    reliability_class: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    run = _latest_completed_index_run(db)
    if run is None:
        return {"index_run": None, "total": 0, "items": []}
    mi = CecchinoV3MatchIndex
    filters = [mi.index_run_id == run.id]
    if competition:
        filters.append(mi.competition_name == competition)
    if season_label:
        filters.append(mi.season_label == season_label)
    if team:
        pattern = f"%{team.strip()}%"
        filters.append(mi.home_team.ilike(pattern) | mi.away_team.ilike(pattern))
    if reliability_class:
        filters.append(mi.reliability_class == reliability_class)
    total = int(db.scalar(select(func.count(mi.id)).where(*filters)) or 0)
    rows = db.scalars(
        select(mi).where(*filters).order_by(mi.kickoff_at.desc(), mi.lab_match_id.desc()).limit(limit).offset(offset)
    ).all()
    predictions = {
        int(p.lab_match_id): p
        for p in db.scalars(
            select(CecchinoV3MatchPrediction).where(
                CecchinoV3MatchPrediction.run_id == run.source_run_id,
                CecchinoV3MatchPrediction.lab_match_id.in_([int(r.lab_match_id) for r in rows] or [-1]),
            )
        ).all()
    }
    probabilities: dict[int, dict[str, float]] = {}
    if predictions:
        by_prediction = {int(p.id): mid for mid, p in predictions.items()}
        for mk in db.scalars(
            select(CecchinoV3MarketPrediction).where(
                CecchinoV3MarketPrediction.match_prediction_id.in_(list(by_prediction)),
                CecchinoV3MarketPrediction.market_key.in_(("HOME", "DRAW", "AWAY", "OVER_2_5")),
            )
        ).all():
            probabilities.setdefault(by_prediction[int(mk.match_prediction_id)], {})[mk.market_key] = float(
                mk.probability
            )
    items = []
    for r in rows:
        idx = r.indices_json
        pred = predictions.get(int(r.lab_match_id))
        probs = probabilities.get(int(r.lab_match_id), {})
        items.append(
            {
                "lab_match_id": int(r.lab_match_id),
                "kickoff_at": r.kickoff_at.isoformat() if r.kickoff_at else None,
                "competition": r.competition_name,
                "season_label": r.season_label,
                "home_team": r.home_team,
                "away_team": r.away_team,
                "score": f"{pred.ft_home_goals}-{pred.ft_away_goals}" if pred else None,
                "eval_eligible": bool(pred.eval_eligible) if pred else None,
                "phase": pred.phase if pred else None,
                "prob_home": probs.get("HOME"),
                "prob_draw": probs.get("DRAW"),
                "prob_away": probs.get("AWAY"),
                "prob_over_2_5": probs.get("OVER_2_5"),
                "reliability": float(r.reliability) if r.reliability is not None else None,
                "reliability_class": r.reliability_class,
                "equilibrio": idx["equilibrio"],
                "pareggio": idx["pareggio"],
                "intensita_goal": idx["intensita_goal"],
            }
        )
    return {"index_run": index_run_to_dict(run), "total": total, "items": items}


def _book_odds(db: Session, lab_match_id: int) -> dict[str, dict[str, float | None]]:
    columns = []
    for mk in MARKET_KEYS:
        if mk in _CLOSING_QUOTE_SQL:
            columns.append(f'({_CLOSING_QUOTE_SQL[mk]})::double precision AS "q_{mk}"')
        if mk in _FAIR_PROB_SQL:
            columns.append(f'({_FAIR_PROB_SQL[mk]})::double precision AS "f_{mk}"')
    row = db.execute(
        text(f"SELECT {', '.join(columns)} FROM cecchino_lab_matches m WHERE m.id = :id"), {"id": lab_match_id}
    ).first()
    if row is None:
        return {}
    data = dict(row._mapping)
    return {
        mk: {
            "closing_odds": round(data[f"q_{mk}"], 3) if data.get(f"q_{mk}") else None,
            "fair_probability": round(data[f"f_{mk}"], 4) if data.get(f"f_{mk}") is not None else None,
        }
        for mk in MARKET_KEYS
    }


def match_detail(db: Session, lab_match_id: int) -> dict[str, Any]:
    run = _latest_completed_index_run(db)
    if run is None:
        raise CecchinoLabImportError("indices_missing", "Indici non ancora calcolati", status_code=404)
    index_row = db.scalars(
        select(CecchinoV3MatchIndex).where(
            CecchinoV3MatchIndex.index_run_id == run.id, CecchinoV3MatchIndex.lab_match_id == lab_match_id
        )
    ).first()
    pred = db.scalars(
        select(CecchinoV3MatchPrediction).where(
            CecchinoV3MatchPrediction.run_id == run.source_run_id,
            CecchinoV3MatchPrediction.lab_match_id == lab_match_id,
        )
    ).first()
    if index_row is None or pred is None:
        raise CecchinoLabImportError("match_not_found", "Partita non trovata", status_code=404)
    markets = {
        mk.market_key: {"probability": float(mk.probability), "won": mk.won}
        for mk in db.scalars(
            select(CecchinoV3MarketPrediction).where(CecchinoV3MarketPrediction.match_prediction_id == pred.id)
        ).all()
    }
    book = _book_odds(db, lab_match_id)
    return {
        "index_run_id": int(run.id),
        "source_run_id": int(run.source_run_id),
        "match": {
            "lab_match_id": lab_match_id,
            "kickoff_at": pred.kickoff_at.isoformat() if pred.kickoff_at else None,
            "competition": pred.competition_name,
            "season_label": pred.season_label,
            "home_team": pred.home_team,
            "away_team": pred.away_team,
            "phase": pred.phase,
            "eval_eligible": pred.eval_eligible,
            "home_played": pred.home_played,
            "away_played": pred.away_played,
            "home_remaining": pred.home_remaining,
            "away_remaining": pred.away_remaining,
        },
        "model": {
            "lambda_home": float(pred.lambda_home),
            "lambda_away": float(pred.lambda_away),
            "rho": float(pred.rho),
            "ht_share": float(pred.ht_share),
            "home_evidence": float(pred.home_evidence),
            "away_evidence": float(pred.away_evidence),
            "specialists": pred.specialists_json,
        },
        "markets": [
            {
                "market_key": mk,
                "probability": markets.get(mk, {}).get("probability"),
                "model_odds": (
                    round(1.0 / markets[mk]["probability"], 3)
                    if markets.get(mk, {}).get("probability")
                    else None
                ),
                "closing_odds": book.get(mk, {}).get("closing_odds"),
                "fair_probability": book.get(mk, {}).get("fair_probability"),
                "won": markets.get(mk, {}).get("won"),
            }
            for mk in MARKET_KEYS
        ],
        "indices": index_row.indices_json,
        "result": {"ft": f"{pred.ft_home_goals}-{pred.ft_away_goals}"},
    }
