"""V3 Fase 4 riprodotta come funzione pura: il termine di paragone dell'esame E1.

Riproduce `cecchino_v3.service._execute_run` per la fase 4 (Forza + Gioco tiri
in porta e tiri + orchestratore + Forma + Calendario; nessuna calibrazione,
nessuna disciplina, nessun parametro promozione) senza database.

Il motore V3 e' importato come libreria e non modificato. Gli helper privati di
`cecchino_v3.service` sono ricopiati alla lettera qui sotto (sezione "copie")
perche' quel modulo istanzia le impostazioni del database all'import.
"""

from __future__ import annotations

from app.services.cecchino_v4.settings import cap_workers

import math
import os
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.services.cecchino_v3.calendar_features import CalendarFeatures, compute_calendar
from app.services.cecchino_v3.constants import (
    CALENDAR_ADJUSTMENTS,
    DEFAULT_HYPER,
    FORM_ADJUSTMENTS,
    GAME_STATS,
    HYPER_GRID,
    MARKET_KEYS,
    Hyper,
)
from app.services.cecchino_v3.data import MatchRecord, group_matches
from app.services.cecchino_v3.form import Expectation, FormFeatures, compute_form
from app.services.cecchino_v3.markets import market_probabilities, score_matrix
from app.services.cecchino_v3.orchestrator import Opinions, combine, default_weights, fit_weights
from app.services.cecchino_v3.walkforward import (
    GamePrediction,
    StrengthPrediction,
    run_game_group,
    run_group,
)

from app.services.cecchino_v4.engine_goals.cache import cached, matches_digest

FORZA = "forza"


@dataclass(frozen=True)
class V3Final:
    """Previsione V3 Fase 4 di una partita (non calibrata)."""

    lab_match_id: int
    lambda_home: float
    lambda_away: float
    rho: float
    ht_share: float
    home_evidence: float
    away_evidence: float
    hyper: Hyper
    specialists: dict[str, Any]
    probabilities: dict[str, float]  # 17 mercati V3
    opinions: dict[str, tuple[float, float]]  # specialista -> (casa, ospite)


@dataclass
class V3Phase4Result:
    finals: dict[int, V3Final]
    chosen_forza: dict[str, Hyper]
    chosen_game: dict[str, dict[str, Hyper]]
    forza_table: dict[str, dict[str, Any]]
    game_tables: dict[str, dict[str, dict[str, Any]]]
    base_weights: dict[str, dict[str, float]]
    final_weights: dict[str, dict[str, float]]
    # oggetti per la stagione successiva all'ultima (live): scelti con la stessa
    # regola sull'ultima stagione completa presente nei dati
    next_season: str
    next_forza: Hyper
    next_game: dict[str, Hyper]
    next_base_weights: dict[str, float]
    next_final_weights: dict[str, float]
    timings: dict[str, float] = field(default_factory=dict)


# --- griglie walk-forward (parallele, con cache) -------------------------------------------


def _walk_job(matches: list[MatchRecord], hyper: Hyper, stat: str, cache_name: str | None) -> dict[int, Any]:
    def compute() -> dict[int, Any]:
        if stat == FORZA:
            return run_group(matches, hyper, movers=False)
        return run_game_group(matches, hyper, stat, movers=False)

    return cached(cache_name, compute, enabled=cache_name is not None)


def _grid_jobs(
    groups: dict[str, list[MatchRecord]], stats: tuple[str, ...], grid: tuple[Hyper, ...], cache_key: str | None
) -> list[tuple[str, str, Hyper, str | None]]:
    jobs: list[tuple[str, str, Hyper, str | None]] = []
    digests = {g: matches_digest(ms) for g, ms in groups.items()} if cache_key is not None else {}
    for stat in stats:
        for group, ms in groups.items():
            for hyper in grid:
                name = f"v3wf_{stat}_{group}_{digests[group]}_{hyper.key}" if cache_key is not None else None
                jobs.append((stat, group, hyper, name))
    # prima i lavori piu' lunghi (gruppi grandi)
    jobs.sort(key=lambda j: -len(groups[j[1]]))
    return jobs


def run_grids(
    groups: dict[str, list[MatchRecord]],
    *,
    stats: tuple[str, ...] = (FORZA, *GAME_STATS),
    grid: tuple[Hyper, ...] = HYPER_GRID,
    cache_key: str | None = None,
    workers: int | None = None,
    timings: dict[str, float] | None = None,
) -> dict[str, dict[str, dict[int, Any]]]:
    """{specialista: {hyper.key: {lab_match_id: previsione}}} su tutta la griglia."""
    jobs = _grid_jobs(groups, stats, grid, cache_key)
    out: dict[str, dict[str, dict[int, Any]]] = {s: {h.key: {} for h in grid} for s in stats}
    if workers is None:
        workers = max(1, min(8, (os.cpu_count() or 2) - 1))
    workers = cap_workers(workers)
    t0 = time.monotonic()
    if workers <= 1 or len(jobs) <= 1:
        for stat, group, hyper, name in jobs:
            g0 = time.monotonic()
            out[stat][hyper.key].update(_walk_job(groups[group], hyper, stat, name))
            if timings is not None:
                timings[f"{stat}|{group}|{hyper.key}"] = round(time.monotonic() - g0, 2)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [
                (stat, hyper, pool.submit(_walk_job, groups[group], hyper, stat, name))
                for stat, group, hyper, name in jobs
            ]
            for stat, hyper, fut in futures:
                out[stat][hyper.key].update(fut.result())
    if timings is not None:
        timings["grids_total"] = round(time.monotonic() - t0, 1)
    return out


# --- copie alla lettera degli helper privati di cecchino_v3.service ----------------------------


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
    grid: tuple[Hyper, ...] = HYPER_GRID,
) -> tuple[dict[str, Hyper], dict[str, dict[str, Any]]]:
    """Per ogni stagione, la griglia con la perdita media piu' bassa sulla
    stagione precedente; nel rodaggio il valore di partenza."""
    seasons = sorted({m.season_label for m in matches})
    table: dict[str, dict[str, Any]] = {}
    for hyper in grid:
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
            chosen[season] = DEFAULT_HYPER if DEFAULT_HYPER in grid else grid[0]
            continue
        previous = seasons[idx - 1]
        chosen[season] = min(grid, key=lambda h: table[h.key][metric_name].get(previous, float("inf")))
    return chosen, table


def _next_hyper(table: dict[str, dict[str, Any]], metric_name: str, last_season: str, grid: tuple[Hyper, ...]) -> Hyper:
    """Stessa regola di scelta applicata alla stagione successiva all'ultima."""
    return min(grid, key=lambda h: table[h.key][metric_name].get(last_season, float("inf")))


@dataclass(frozen=True)
class Adjustments:
    """Correzioni in scala logaritmica per l'orchestratore, per partita e lato."""

    keys: tuple[str, ...]
    home: dict[int, dict[str, float]]
    away: dict[int, dict[str, float]]


def build_adjustments(
    form: dict[int, FormFeatures] | None,
    calendar: dict[int, CalendarFeatures] | None = None,
) -> Adjustments | None:
    """Unisce le correzioni degli specialisti attivi; una partita entra solo se
    ha tutte le correzioni richieste (copia di service.build_adjustments, senza disciplina)."""
    sources: list[dict[int, Any]] = [src for src in (form, calendar) if src is not None]
    if not sources:
        return None
    keys: tuple[str, ...] = ()
    if form is not None:
        keys += FORM_ADJUSTMENTS
    if calendar is not None:
        keys += CALENDAR_ADJUSTMENTS
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


def _fit_season_weights(
    matches: list[MatchRecord],
    previous: str,
    season: str,
    forza: dict[str, dict[int, StrengthPrediction]],
    game: dict[str, dict[str, dict[int, GamePrediction]]],
    chosen_forza: dict[str, Hyper],
    chosen_game: dict[str, dict[str, Hyper]],
    adjustments: Adjustments | None,
) -> dict[str, float]:
    keys = adjustments.keys if adjustments is not None else ()
    samples = []
    for m in matches:
        if m.season_label != previous or not m.eval_eligible:
            continue
        ops = _opinions(m, season, forza, game, chosen_forza, chosen_game, adjustments)
        if ops is not None:
            samples.append((ops, m.ft_home, m.ft_away))
    return fit_weights(samples, keys)


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
        weights[season] = _fit_season_weights(
            matches, seasons[idx - 1], season, forza, game, chosen_forza, chosen_game, adjustments
        )
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
    return payload


# --- la Fase 4 come funzione pura ----------------------------------------------------------------


def run_v3_phase4_full(
    matches: list[MatchRecord],
    *,
    cache_key: str | None = None,
    grid: tuple[Hyper, ...] = HYPER_GRID,
    workers: int | None = None,
) -> V3Phase4Result:
    """Tutta la pipeline della Fase 4 V3 (senza database) con gli oggetti stimati."""
    if not matches:
        raise ValueError("nessuna partita")
    timings: dict[str, float] = {}
    groups = group_matches(matches)
    grids = run_grids(groups, grid=grid, cache_key=cache_key, workers=workers, timings=timings)
    forza = grids[FORZA]
    game = {stat: grids[stat] for stat in GAME_STATS}

    t0 = time.monotonic()
    chosen_forza, forza_table = _select_by_previous_season(matches, forza, _one_x_two_log_loss, "log_loss_1x2", grid)
    chosen_game: dict[str, dict[str, Hyper]] = {}
    game_tables: dict[str, dict[str, dict[str, Any]]] = {}
    for stat in GAME_STATS:
        chosen_game[stat], game_tables[stat] = _select_by_previous_season(
            matches, game[stat], _goals_log_loss, "goals_log_loss", grid
        )
    base_weights = _orchestrator_weights(matches, forza, game, chosen_forza, chosen_game)
    expectations = _base_expectations(matches, forza, game, chosen_forza, chosen_game, base_weights)
    form = compute_form(matches, expectations)
    calendar = compute_calendar(matches)
    adjustments = build_adjustments(form, calendar)
    assert adjustments is not None
    final_weights = _orchestrator_weights(matches, forza, game, chosen_forza, chosen_game, adjustments)

    finals: dict[int, V3Final] = {}
    for m in matches:
        season = m.season_label
        f = forza[chosen_forza[season].key].get(m.lab_match_id)
        if f is None:
            continue
        ops = _opinions(m, season, forza, game, chosen_forza, chosen_game, adjustments)
        if ops is None:
            continue
        weights = final_weights[season]
        lam_h, lam_a = combine(ops, weights)
        specialists = _specialists_payload(
            m, season, f, ops, game, chosen_game, weights, form.get(m.lab_match_id), calendar.get(m.lab_match_id)
        )
        finals[m.lab_match_id] = V3Final(
            lab_match_id=m.lab_match_id,
            lambda_home=lam_h,
            lambda_away=lam_a,
            rho=f.rho,
            ht_share=f.ht_share,
            home_evidence=f.home_evidence,
            away_evidence=f.away_evidence,
            hyper=chosen_forza[season],
            specialists=specialists,
            probabilities=market_probabilities(lam_h, lam_a, f.rho, f.ht_share),
            opinions={k: (ops.home[k], ops.away[k]) for k in ops.home},
        )
    timings["phase4_assembly"] = round(time.monotonic() - t0, 1)

    # oggetti per la stagione successiva (live), con la stessa regola sull'ultima stagione
    seasons = sorted({m.season_label for m in matches})
    last = seasons[-1]
    next_forza = _next_hyper(forza_table, "log_loss_1x2", last, grid)
    next_game = {stat: _next_hyper(game_tables[stat], "goals_log_loss", last, grid) for stat in GAME_STATS}
    virtual = "__next__"
    cf = {**chosen_forza, virtual: next_forza}
    cg = {stat: {**chosen_game[stat], virtual: next_game[stat]} for stat in GAME_STATS}
    next_base = _fit_season_weights(matches, last, virtual, forza, game, cf, cg, None)
    next_final = _fit_season_weights(matches, last, virtual, forza, game, cf, cg, adjustments)

    return V3Phase4Result(
        finals=finals,
        chosen_forza=chosen_forza,
        chosen_game=chosen_game,
        forza_table=forza_table,
        game_tables=game_tables,
        base_weights=base_weights,
        final_weights=final_weights,
        next_season=_season_after(last),
        next_forza=next_forza,
        next_game=next_game,
        next_base_weights=next_base,
        next_final_weights=next_final,
        timings=timings,
    )


def _season_after(label: str) -> str:
    try:
        a, b = label.split("/")
        return f"{int(a) + 1}/{int(b) + 1}"
    except ValueError:
        return f"{label}+1"


def run_v3_phase4(
    matches: list[MatchRecord],
    *,
    cache_key: str | None = None,
    grid: tuple[Hyper, ...] = HYPER_GRID,
    workers: int | None = None,
) -> dict[int, V3Final]:
    """V3 Fase 4 esatta per ogni partita: gol attesi, rho, quota primo tempo,
    evidenza, specialisti e le 17 probabilita' (`MARKET_KEYS`)."""
    return run_v3_phase4_full(matches, cache_key=cache_key, grid=grid, workers=workers).finals


__all__ = [
    "Adjustments",
    "MARKET_KEYS",
    "V3Final",
    "V3Phase4Result",
    "build_adjustments",
    "run_grids",
    "run_v3_phase4",
    "run_v3_phase4_full",
]
