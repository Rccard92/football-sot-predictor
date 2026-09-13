"""Esecuzione dei calcoli V3 in background (riga di stato su DB + thread),
con lo stesso schema dei job gia' usati da Pattern Insights.

Fase 1: solo specialista Forza.
Fase 2: Forza + specialista Gioco (tiri in porta, tiri) + orchestratore.
Fase 3: Fase 2 + specialista Forma (correzioni nell'orchestratore).
Fase 4: Fase 3 + specialista Calendario (riposo e fase della stagione).
Fase 5: Fase 4 + specialista Disciplina (falli, cartellini, arbitro).
"""

from __future__ import annotations

import logging
import math
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
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
    CALENDAR_ADJUSTMENTS,
    CONVERSION_PSEUDO_COUNT,
    DISCIPLINE_ADJUSTMENTS,
    DISCIPLINE_PRIOR_CARDS,
    DISCIPLINE_PRIOR_FOULS,
    DISCIPLINE_PSEUDO_MATCHES,
    COUNTRY_GROUPS,
    DEFAULT_HYPER,
    ENGINE_VERSION,
    ENGINE_VERSION_PHASE2,
    ENGINE_VERSION_PHASE3,
    ENGINE_VERSION_PHASE4,
    ENGINE_VERSION_PHASE5,
    EXAM_TOLERANCE_PCT,
    FINAL_PHASE_MATCHES,
    FORM_ADJUSTMENTS,
    FORM_MATCHES,
    FORM_PSEUDO_COUNT,
    GAME_STATS,
    HYPER_GRID,
    JUDGE_SEASONS,
    LOCKBOX,
    MARKET_KEYS,
    MIN_MATCHES_PLAYED,
    ORCHESTRATOR_DEFAULT_WEIGHTS,
    PHASES,
    PRIOR_GOALS_PER_STAT,
    REST_CAP_DAYS,
    REST_FLOOR_DAYS,
    REST_REFERENCE_DAYS,
    REFEREE_PSEUDO_GOALS,
    WARMUP_SEASON,
    Hyper,
)
from app.services.cecchino_v3.calendar_features import CalendarFeatures, compute_calendar
from app.services.cecchino_v3.data import MatchRecord, group_matches, load_matches
from app.services.cecchino_v3.discipline import DisciplineFeatures, compute_discipline
from app.services.cecchino_v3.form import Expectation, FormFeatures, compute_form
from app.services.cecchino_v3.markets import market_outcomes, market_probabilities, score_matrix
from app.services.cecchino_v3.orchestrator import Opinions, combine, default_weights, fit_weights
from app.services.cecchino_v3.walkforward import (
    GamePrediction,
    StrengthPrediction,
    run_game_group,
    run_group,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}

_INSERT_CHUNK = 2000
_CANCEL_CHECK_SECONDS = 5.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _d(value: float, places: int) -> Decimal:
    return Decimal(str(round(float(value), places)))


def run_phase(run: CecchinoV3Run) -> int:
    return int((run.config_json or {}).get("phase") or 1)


def run_to_dict(run: CecchinoV3Run) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "engine_version": run.engine_version,
        "phase": run_phase(run),
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


_ENGINE_BY_PHASE = {
    1: ENGINE_VERSION,
    2: ENGINE_VERSION_PHASE2,
    3: ENGINE_VERSION_PHASE3,
    4: ENGINE_VERSION_PHASE4,
    5: ENGINE_VERSION_PHASE5,
}


def _config(phase: int, baseline_run_id: int | None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "phase": phase,
        "engine_version": _ENGINE_BY_PHASE[phase],
        "warmup_season": WARMUP_SEASON,
        "judge_seasons": list(JUDGE_SEASONS),
        "lockbox_season": LOCKBOX,
        "min_matches_played": MIN_MATCHES_PLAYED,
        "final_phase_matches": FINAL_PHASE_MATCHES,
        "hyper_grid": [{"xi": h.xi, "sigma": h.sigma} for h in HYPER_GRID],
        "default_hyper": {"xi": DEFAULT_HYPER.xi, "sigma": DEFAULT_HYPER.sigma},
        "hyper_selection": "per stagione S: griglia con il miglior risultato sulla stagione S-1 (partite idonee)",
        "country_groups": {k: list(v) for k, v in COUNTRY_GROUPS.items()},
    }
    if phase >= 2:
        config.update(
            {
                "baseline_run_id": baseline_run_id,
                "game_stats": list(GAME_STATS),
                "prior_goals_per_stat": dict(PRIOR_GOALS_PER_STAT),
                "conversion_pseudo_count": dict(CONVERSION_PSEUDO_COUNT),
                "orchestrator_default_weights": dict(ORCHESTRATOR_DEFAULT_WEIGHTS),
                "orchestrator_fit": "pesi della stagione S stimati sulle previsioni della stagione S-1",
            }
        )
    if phase >= 3:
        config.update(
            {
                "form_matches": FORM_MATCHES,
                "form_pseudo_count": dict(FORM_PSEUDO_COUNT),
                "form_adjustments": list(FORM_ADJUSTMENTS),
                "exam_tolerance_pct": EXAM_TOLERANCE_PCT,
            }
        )
    if phase >= 4:
        config.update(
            {
                "calendar_adjustments": list(CALENDAR_ADJUSTMENTS),
                "rest_floor_days": REST_FLOOR_DAYS,
                "rest_cap_days": REST_CAP_DAYS,
                "rest_reference_days": REST_REFERENCE_DAYS,
                "calendar_limit": "solo partite di campionato: coppe e partite europee non accorciano il riposo",
            }
        )
    if phase >= 5:
        config.update(
            {
                "discipline_adjustments": list(DISCIPLINE_ADJUSTMENTS),
                "discipline_pseudo_matches": DISCIPLINE_PSEUDO_MATCHES,
                "discipline_prior_fouls": DISCIPLINE_PRIOR_FOULS,
                "discipline_prior_cards": DISCIPLINE_PRIOR_CARDS,
                "referee_pseudo_goals": REFEREE_PSEUDO_GOALS,
                "discipline_limit": "arbitro disponibile solo per i campionati inglesi",
            }
        )
    return config


def _latest_completed_phase(db: Session, phase: int) -> CecchinoV3Run | None:
    for run in db.scalars(
        select(CecchinoV3Run)
        .where(CecchinoV3Run.status == V3_STATUS_COMPLETED)
        .order_by(CecchinoV3Run.completed_at.desc())
    ):
        if run_phase(run) == phase:
            return run
    return None


def start_run(db: Session, *, phase: int = 2) -> dict[str, Any]:
    if phase not in PHASES:
        raise CecchinoLabImportError("invalid_phase", f"Fase non valida: {phase}", status_code=400)
    active = db.scalars(
        select(CecchinoV3Run).where(CecchinoV3Run.status.in_(V3_ACTIVE_STATUSES))
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste gia' un calcolo V3 in corso (id={active.id})",
            status_code=409,
        )
    baseline_run_id: int | None = None
    if phase >= 2:
        baseline = _latest_completed_phase(db, phase - 1)
        if baseline is None:
            raise CecchinoLabImportError(
                "baseline_missing",
                f"Serve un calcolo della Fase {phase - 1} completato: e' il termine di paragone dell'esame.",
                status_code=400,
            )
        baseline_run_id = int(baseline.id)
    config = _config(phase, baseline_run_id)
    run = CecchinoV3Run(
        engine_version=config["engine_version"],
        status=V3_STATUS_PENDING,
        requested_at=_utcnow(),
        config_json=config,
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


def list_completed_runs(db: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": int(r.id),
            "phase": run_phase(r),
            "engine_version": r.engine_version,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "exam_passed": ((r.summary_json or {}).get("evaluation") or {}).get("exam", {}).get("passed"),
            "user_decision": (r.config_json or {}).get("user_decision"),
            "reference_model": bool((r.config_json or {}).get("reference_model")),
        }
        for r in db.scalars(
            select(CecchinoV3Run)
            .where(CecchinoV3Run.status == V3_STATUS_COMPLETED)
            .order_by(CecchinoV3Run.id.desc())
        )
    ]


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


def _goals_log_loss(match: MatchRecord, pred: GamePrediction) -> float:
    """Poisson (senza costante) dei gol reali con i gol attesi dello specialista."""
    loss = 0.0
    for lam, goals in ((pred.lambda_home, match.ft_home), (pred.lambda_away, match.ft_away)):
        lam = max(lam, 1e-6)
        loss += lam - goals * math.log(lam)
    return loss


def _select_by_previous_season(
    matches: list[MatchRecord],
    predictions: dict[str, dict[int, Any]],
    loss: Callable[[MatchRecord, Any], float],
    metric_name: str,
) -> tuple[dict[str, Hyper], dict[str, dict[str, Any]]]:
    """Per ogni stagione, la griglia con la perdita media piu' bassa sulla
    stagione precedente; nel rodaggio il valore di partenza."""
    seasons = sorted({m.season_label for m in matches})
    table: dict[str, dict[str, Any]] = {}
    for hyper in HYPER_GRID:
        preds = predictions[hyper.key]
        per_season: dict[str, list[float]] = {}
        for m in matches:
            if not m.eval_eligible or m.lab_match_id not in preds:
                continue
            acc = per_season.setdefault(m.season_label, [0.0, 0])
            acc[0] += loss(m, preds[m.lab_match_id])
            acc[1] += 1
        table[hyper.key] = {
            "xi": hyper.xi,
            "sigma": hyper.sigma,
            metric_name: {s: round(v[0] / v[1], 5) for s, v in per_season.items() if v[1]},
        }

    chosen: dict[str, Hyper] = {}
    for idx, season in enumerate(seasons):
        if idx == 0:
            chosen[season] = DEFAULT_HYPER
            continue
        previous = seasons[idx - 1]
        chosen[season] = min(
            HYPER_GRID, key=lambda h: table[h.key][metric_name].get(previous, float("inf"))
        )
    return chosen, table


def select_hypers(
    matches: list[MatchRecord], predictions: dict[str, dict[int, StrengthPrediction]]
) -> tuple[dict[str, Hyper], dict[str, dict[str, Any]]]:
    return _select_by_previous_season(matches, predictions, _one_x_two_log_loss, "log_loss_1x2")


# --- previsione finale per partita ------------------------------------------------------


@dataclass(frozen=True)
class FinalPrediction:
    lambda_home: float
    lambda_away: float
    rho: float
    ht_share: float
    home_evidence: float
    away_evidence: float
    hyper: Hyper
    specialists: dict[str, Any] | None


@dataclass(frozen=True)
class Adjustments:
    """Correzioni in scala logaritmica per l'orchestratore, per partita e lato."""

    keys: tuple[str, ...]
    home: dict[int, dict[str, float]]
    away: dict[int, dict[str, float]]


def build_adjustments(
    form: dict[int, FormFeatures] | None,
    calendar: dict[int, CalendarFeatures] | None = None,
    discipline: dict[int, DisciplineFeatures] | None = None,
) -> Adjustments | None:
    """Unisce le correzioni degli specialisti attivi; una partita entra solo se
    ha tutte le correzioni richieste."""
    sources: list[dict[int, Any]] = [src for src in (form, calendar, discipline) if src is not None]
    if not sources:
        return None
    keys: tuple[str, ...] = ()
    if form is not None:
        keys += FORM_ADJUSTMENTS
    if calendar is not None:
        keys += CALENDAR_ADJUSTMENTS
    if discipline is not None:
        keys += DISCIPLINE_ADJUSTMENTS
    ids = set(sources[0])
    for src in sources[1:]:
        ids &= set(src)
    home: dict[int, dict[str, float]] = {}
    away: dict[int, dict[str, float]] = {}
    for mid in ids:
        h: dict[str, float] = {}
        a: dict[str, float] = {}
        if form is not None:
            fm = form[mid]
            h.update({"form_goals": fm.goals_home, "form_shots": fm.shots_home})
            a.update({"form_goals": fm.goals_away, "form_shots": fm.shots_away})
        if calendar is not None:
            h.update(calendar[mid].adjust_home)
            a.update(calendar[mid].adjust_away)
        if discipline is not None:
            h.update(discipline[mid].adjust_home)
            a.update(discipline[mid].adjust_away)
        home[mid] = h
        away[mid] = a
    return Adjustments(keys=keys, home=home, away=away)


def _opinions(
    m: MatchRecord,
    season: str,
    forza: dict[str, dict[int, StrengthPrediction]],
    game: dict[str, dict[str, dict[int, GamePrediction]]],
    chosen_forza: dict[str, Hyper],
    chosen_game: dict[str, dict[str, Hyper]],
    adjustments: Adjustments | None = None,
) -> Opinions | None:
    f = forza[chosen_forza[season].key].get(m.lab_match_id)
    if f is None:
        return None
    home = {"forza": f.lambda_home}
    away = {"forza": f.lambda_away}
    for stat in GAME_STATS:
        gp = game[stat][chosen_game[stat][season].key].get(m.lab_match_id)
        if gp is None:
            return None
        home[stat] = gp.lambda_home
        away[stat] = gp.lambda_away
    if adjustments is None:
        return Opinions(home=home, away=away)
    adjust_home = adjustments.home.get(m.lab_match_id)
    adjust_away = adjustments.away.get(m.lab_match_id)
    if adjust_home is None or adjust_away is None:
        return None
    return Opinions(home=home, away=away, adjust_home=adjust_home, adjust_away=adjust_away)


def _orchestrator_weights(
    matches: list[MatchRecord],
    forza: dict[str, dict[int, StrengthPrediction]],
    game: dict[str, dict[str, dict[int, GamePrediction]]],
    chosen_forza: dict[str, Hyper],
    chosen_game: dict[str, dict[str, Hyper]],
    adjustments: Adjustments | None = None,
) -> dict[str, dict[str, float]]:
    """Pesi per la stagione S dalle previsioni della stagione S-1, fatte con gli
    stessi specialisti (e parametri) che si useranno nella stagione S."""
    keys = adjustments.keys if adjustments is not None else ()
    seasons = sorted({m.season_label for m in matches})
    weights: dict[str, dict[str, float]] = {}
    for idx, season in enumerate(seasons):
        if idx == 0:
            weights[season] = default_weights(keys)
            continue
        previous = seasons[idx - 1]
        samples = []
        for m in matches:
            if m.season_label != previous or not m.eval_eligible:
                continue
            ops = _opinions(m, season, forza, game, chosen_forza, chosen_game, adjustments)
            if ops is not None:
                samples.append((ops, m.ft_home, m.ft_away))
        weights[season] = fit_weights(samples, keys)
    return weights


def _base_expectations(
    matches: list[MatchRecord],
    forza: dict[str, dict[int, StrengthPrediction]],
    game: dict[str, dict[str, dict[int, GamePrediction]]],
    chosen_forza: dict[str, Hyper],
    chosen_game: dict[str, dict[str, Hyper]],
    base_weights: dict[str, dict[str, float]],
) -> dict[int, Expectation]:
    """Attese pre-partita di Forza + Gioco (senza forma) per misurare la forma."""
    out: dict[int, Expectation] = {}
    for m in matches:
        ops = _opinions(m, m.season_label, forza, game, chosen_forza, chosen_game)
        if ops is None:
            continue
        goals_home, goals_away = combine(ops, base_weights[m.season_label])
        shots = game["shots"][chosen_game["shots"][m.season_label].key].get(m.lab_match_id)
        out[m.lab_match_id] = Expectation(
            goals_home=goals_home,
            goals_away=goals_away,
            shots_home=shots.stat_home if shots else None,
            shots_away=shots.stat_away if shots else None,
        )
    return out


def _specialists_payload(
    m: MatchRecord,
    season: str,
    f: StrengthPrediction,
    ops: Opinions,
    game: dict[str, dict[str, dict[int, GamePrediction]]],
    chosen_game: dict[str, dict[str, Hyper]],
    weights: dict[str, float],
    form: FormFeatures | None,
    calendar: CalendarFeatures | None = None,
    discipline: DisciplineFeatures | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "forza": {"home": round(f.lambda_home, 5), "away": round(f.lambda_away, 5)},
        "weights": weights,
    }
    for stat in GAME_STATS:
        gp = game[stat][chosen_game[stat][season].key][m.lab_match_id]
        payload[stat] = {
            "home": round(ops.home[stat], 5),
            "away": round(ops.away[stat], 5),
            "volume_home": round(gp.stat_home, 3),
            "volume_away": round(gp.stat_away, 3),
        }
    if form is not None:
        payload["form"] = {
            "goals_home": round(form.goals_home, 5),
            "goals_away": round(form.goals_away, 5),
            "shots_home": round(form.shots_home, 5),
            "shots_away": round(form.shots_away, 5),
            "matches_home": form.matches_home,
            "matches_away": form.matches_away,
            **form.detail,
        }
    if calendar is not None:
        payload["calendar"] = {
            "rest_days_home": calendar.rest_days_home,
            "rest_days_away": calendar.rest_days_away,
            "final_phase": calendar.final_phase,
        }
    if discipline is not None:
        payload["discipline"] = dict(discipline.detail)
    return payload


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
    final: dict[int, FinalPrediction],
) -> dict[str, int]:
    written = {"matches": 0, "markets": 0}
    for start in range(0, len(matches), _INSERT_CHUNK):
        chunk = matches[start : start + _INSERT_CHUNK]
        match_rows: list[dict[str, Any]] = []
        market_payload: dict[int, list[tuple[str, float, bool | None]]] = {}
        for m in chunk:
            pred = final.get(m.lab_match_id)
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
                    "hyper_xi": _d(pred.hyper.xi, 5),
                    "hyper_sigma": _d(pred.hyper.sigma, 3),
                    "ft_home_goals": m.ft_home,
                    "ft_away_goals": m.ft_away,
                    "specialists_json": pred.specialists,
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


class _Cancelled(Exception):
    pass


def _grid(
    db: Session,
    run_id: int,
    groups: dict[str, list[MatchRecord]],
    label: str,
    compute: Callable[[list[MatchRecord], Hyper], dict[int, Any]],
    *,
    progress_from: float,
    progress_span: float,
    should_stop: Callable[[], bool],
    timings: dict[str, float],
) -> dict[str, dict[int, Any]]:
    total = len(HYPER_GRID) * sum(len(v) for v in groups.values())
    done = 0
    out: dict[str, dict[int, Any]] = {}
    for hyper in HYPER_GRID:
        out[hyper.key] = {}
        for group, group_list in groups.items():
            _progress(db, run_id, progress_from + progress_span * done / max(total, 1), f"{label} · {group} · {hyper.key}")
            g0 = time.monotonic()
            out[hyper.key].update(compute(group_list, hyper))
            timings[f"{label}|{group}|{hyper.key}"] = round(time.monotonic() - g0, 2)
            done += len(group_list)
            if should_stop():
                raise _Cancelled()
    return out


def _execute_run(run_id: int) -> None:
    db = SessionLocal()
    t0 = time.monotonic()
    try:
        run = db.get(CecchinoV3Run, run_id)
        if not run:
            return
        phase = run_phase(run)
        baseline_run_id = (run.config_json or {}).get("baseline_run_id")
        run.status = V3_STATUS_RUNNING
        run.started_at = _utcnow()
        db.commit()

        try:
            _progress(db, run_id, 1.0, "Caricamento partite")
            matches = load_matches(db)
            groups = group_matches(matches)
            should_stop = _cancel_checker(run_id)
            timings: dict[str, float] = {}
            span = 80.0 if phase == 1 else 80.0 / (1 + len(GAME_STATS))

            forza = _grid(
                db,
                run_id,
                groups,
                "Forza",
                lambda ms, h: run_group(ms, h, should_stop=should_stop),
                progress_from=2.0,
                progress_span=span,
                should_stop=should_stop,
                timings=timings,
            )
            game: dict[str, dict[str, dict[int, GamePrediction]]] = {}
            if phase >= 2:
                for k, stat in enumerate(GAME_STATS, start=1):
                    game[stat] = _grid(
                        db,
                        run_id,
                        groups,
                        f"Gioco {stat}",
                        lambda ms, h, s=stat: run_game_group(ms, h, s, should_stop=should_stop),
                        progress_from=2.0 + span * k,
                        progress_span=span,
                        should_stop=should_stop,
                        timings=timings,
                    )

            _progress(db, run_id, 83.0, "Scelta parametri sulla stagione precedente")
            chosen_forza, forza_table = select_hypers(matches, forza)
            chosen_game: dict[str, dict[str, Hyper]] = {}
            game_tables: dict[str, Any] = {}
            base_weights: dict[str, dict[str, float]] = {}
            form: dict[int, FormFeatures] | None = None
            calendar: dict[int, CalendarFeatures] | None = None
            discipline: dict[int, DisciplineFeatures] | None = None
            expectations: dict[int, Expectation] = {}
            adjustments: Adjustments | None = None
            final_weights: dict[str, dict[str, float]] = {}
            if phase >= 2:
                for stat in GAME_STATS:
                    chosen_game[stat], game_tables[stat] = _select_by_previous_season(
                        matches, game[stat], _goals_log_loss, "goals_log_loss"
                    )
                _progress(db, run_id, 84.0, "Pesi dell'orchestratore")
                base_weights = _orchestrator_weights(matches, forza, game, chosen_forza, chosen_game)
            if phase >= 3:
                _progress(db, run_id, 85.0, "Forma: rendimento recente rispetto alle attese")
                expectations = _base_expectations(matches, forza, game, chosen_forza, chosen_game, base_weights)
                form = compute_form(matches, expectations)
            if phase >= 4:
                _progress(db, run_id, 85.5, "Calendario: riposo e fase della stagione")
                calendar = compute_calendar(matches)
            if phase >= 5:
                _progress(db, run_id, 85.7, "Disciplina: falli, cartellini e arbitro")
                discipline = compute_discipline(matches, expectations)
            if phase >= 3:
                adjustments = build_adjustments(form, calendar, discipline)
                final_weights = _orchestrator_weights(
                    matches, forza, game, chosen_forza, chosen_game, adjustments
                )

            final: dict[int, FinalPrediction] = {}
            for m in matches:
                season = m.season_label
                f = forza[chosen_forza[season].key].get(m.lab_match_id)
                if f is None:
                    continue
                lam_h, lam_a = f.lambda_home, f.lambda_away
                specialists: dict[str, Any] | None = None
                if phase >= 2:
                    ops = _opinions(m, season, forza, game, chosen_forza, chosen_game, adjustments)
                    if ops is None:
                        continue
                    weights = final_weights[season] if phase >= 3 else base_weights[season]
                    lam_h, lam_a = combine(ops, weights)
                    specialists = _specialists_payload(
                        m,
                        season,
                        f,
                        ops,
                        game,
                        chosen_game,
                        weights,
                        form.get(m.lab_match_id) if form is not None else None,
                        calendar.get(m.lab_match_id) if calendar is not None else None,
                        discipline.get(m.lab_match_id) if discipline is not None else None,
                    )
                final[m.lab_match_id] = FinalPrediction(
                    lambda_home=lam_h,
                    lambda_away=lam_a,
                    rho=f.rho,
                    ht_share=f.ht_share,
                    home_evidence=f.home_evidence,
                    away_evidence=f.away_evidence,
                    hyper=chosen_forza[season],
                    specialists=specialists,
                )

            _progress(db, run_id, 86.0, "Salvataggio previsioni")
            written = _persist(db, run_id, matches, final)

            _progress(db, run_id, 95.0, "Valutazione")
            from app.services.cecchino_v3.evaluation import build_evaluation

            evaluation = build_evaluation(
                db,
                run_id,
                baseline_run_id=baseline_run_id,
                tolerance_pct=EXAM_TOLERANCE_PCT if phase >= 3 else None,
            )

            seasons: dict[str, dict[str, int]] = {}
            for m in matches:
                s = seasons.setdefault(
                    m.season_label, {"matches": 0, "eligible": 0, "early": 0, "mid": 0, "final": 0}
                )
                s["matches"] += 1
                s["eligible"] += int(m.eval_eligible)
                s[m.phase] += 1

            summary: dict[str, Any] = {
                "seasons": seasons,
                "chosen_hyper": {s: {"xi": h.xi, "sigma": h.sigma} for s, h in chosen_forza.items()},
                "hyper_table": forza_table,
                "written": written,
                "elapsed_seconds": round(time.monotonic() - t0, 1),
                "group_timings_seconds": timings,
                "evaluation": evaluation,
            }
            if phase >= 2:
                summary["game_chosen_hyper"] = {
                    stat: {s: {"xi": h.xi, "sigma": h.sigma} for s, h in chosen.items()}
                    for stat, chosen in chosen_game.items()
                }
                summary["game_hyper_table"] = game_tables
                summary["orchestrator_weights"] = final_weights if phase >= 3 else base_weights
            if phase >= 3:
                summary["base_orchestrator_weights"] = base_weights

            run = db.get(CecchinoV3Run, run_id)
            run.summary_json = summary
            run.progress_pct = Decimal("100.0")
            run.current_step = None
            run.status = V3_STATUS_COMPLETED
            run.completed_at = _utcnow()
            db.commit()
        except _Cancelled:
            db.rollback()
            run = db.get(CecchinoV3Run, run_id)
            if run:
                run.status = V3_STATUS_CANCELLED
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
