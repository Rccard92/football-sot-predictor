"""Motore gol V4 come funzione pura: V3 Fase 4 (termine di paragone) piu' le
novita' pre-registrate, ognuna accendibile in `V4GoalsConfig`.

`predict_history(history, config)` restituisce, per ogni partita dello storico,
il payload "goals" di docs/v4/API.md. `predict_history_full` restituisce anche
le righe per l'esame e gli oggetti stimati sull'ultima stagione completa per il
live (`LiveArtifacts`). Nessuna quota del book entra qui.
"""

from __future__ import annotations

import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression

from app.services.cecchino_v3.constants import Hyper
from app.services.cecchino_v3.data import MatchRecord, group_matches
from app.services.cecchino_v3.markets import market_outcomes

from app.services.cecchino_v4.constants import CLASSIC_MARKETS
from app.services.cecchino_v4.engine_goals.additions import (
    HomeAdvState,
    HomeAdvantage,
    Uncertainty,
    apply_calibration_bounds_many,
    apply_calibration_many,
    apply_home_advantage,
    fit_calibration,
    fit_dispersion,
    team_home_advantage,
    uncertainty_cuts,
    uncertainty_level,
    uncertainty_score,
)
from app.services.cecchino_v4.engine_goals.baseline_v3 import V3Final, V3Phase4Result, run_v3_phase4_full
from app.services.cecchino_v4.engine_goals.cache import cached, matches_digest
from app.services.cecchino_v4.engine_goals.config import (
    ENGINE_VERSION,
    INTERVAL_SIGMA_BASE,
    INTERVAL_SIGMA_SLOPE,
    INTERVAL_Z90,
    LEVEL_MEDIUM,
    V4GoalsConfig,
)
from app.services.cecchino_v4.engine_goals.distributions import all_markets, market_intervals
from app.services.cecchino_v4.engine_goals.strength_params import DayParams, GroupIndex, prepare_group, walk_strength_params
from app.services.cecchino_v4.history.football_data import History

# --- parametri della Forza per giorno (ratings, rho per divisione) ----------------------------------


@dataclass
class GroupParams:
    index: GroupIndex
    by_hyper: dict[str, dict[int, DayParams]]  # hyper.key -> giorno -> parametri


def _params_job(matches: list[MatchRecord], hyper: Hyper, cache_name: str | None) -> dict[int, DayParams]:
    return cached(cache_name, lambda: walk_strength_params(matches, hyper), enabled=cache_name is not None)


def compute_strength_params(
    matches: list[MatchRecord],
    hypers: set[Hyper],
    *,
    cache_key: str | None = None,
    workers: int | None = None,
) -> dict[str, GroupParams]:
    groups = group_matches(matches)
    jobs: list[tuple[str, Hyper, str | None]] = []
    for group, ms in groups.items():
        digest = matches_digest(ms) if cache_key is not None else None
        for hyper in sorted(hypers, key=lambda h: h.key):
            name = f"v4params_{group}_{digest}_{hyper.key}" if cache_key is not None else None
            jobs.append((group, hyper, name))
    jobs.sort(key=lambda j: -len(groups[j[0]]))
    if workers is None:
        workers = max(1, min(8, (os.cpu_count() or 2) - 1))
    results: dict[tuple[str, str], dict[int, DayParams]] = {}
    if workers <= 1 or len(jobs) <= 1:
        for group, hyper, name in jobs:
            results[(group, hyper.key)] = _params_job(groups[group], hyper, name)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {(g, h.key): pool.submit(_params_job, groups[g], h, n) for g, h, n in jobs}
            results = {k: f.result() for k, f in futures.items()}
    out: dict[str, GroupParams] = {}
    for group, ms in groups.items():
        out[group] = GroupParams(
            index=prepare_group(ms), by_hyper={h.key: results[(group, h.key)] for h in hypers}
        )
    return out


# --- risultati -----------------------------------------------------------------------------------


@dataclass
class MatchRow:
    """Riga per l'esame: probabilita' finali e contesto (nessuna quota)."""

    lab_match_id: int
    season: str
    competition: str
    group: str
    eval_eligible: bool
    ft_home: int
    ft_away: int
    ht_home: int | None
    ht_away: int | None
    probs: dict[str, float]
    baseline_probs: dict[str, float]
    score: float
    level: str


@dataclass
class LiveArtifacts:
    """Oggetti stimati sull'ultima stagione completa, per la stagione successiva (live)."""

    config: V4GoalsConfig
    season: str  # stagione servita
    fitted_on: str  # ultima stagione completa
    hyper_forza: Hyper
    hyper_game: dict[str, Hyper]
    base_weights: dict[str, float]
    final_weights: dict[str, float]
    dispersion: dict[str, tuple[float | None, float | None]]  # competizione -> (alpha casa, alpha ospite)
    calibration: dict[str, IsotonicRegression | None]
    calibration_applied: bool
    uncertainty_cuts: tuple[float, float]
    # stato dei residui del vantaggio casa per (piramide, squadra) a fine stagione
    home_adv_states: dict[tuple[str, str], HomeAdvState] = field(default_factory=dict)
    # partite per squadra e stagione in ogni campionato (per la fase finale nel live)
    matches_per_team: dict[str, int] = field(default_factory=dict)


@dataclass
class V4Run:
    config: V4GoalsConfig
    payloads: dict[int, dict[str, Any]]
    rows: dict[int, MatchRow]
    baseline: V3Phase4Result
    artifacts: LiveArtifacts
    season_info: dict[str, dict[str, Any]] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)


# --- il motore -------------------------------------------------------------------------------------


def _ratings_block(
    gp: GroupParams,
    dp: DayParams,
    competition: str,
    team: str,
    peers: set[str],
    hdev: float,
) -> dict[str, Any]:
    idx = gp.index
    layout = idx.layout
    d = idx.div_index[competition]
    t = idx.team_index[team]
    attack = dp.attack(layout, t)
    defence = dp.defence(layout, t)
    peer_ids = [idx.team_index[p] for p in peers if p in idx.team_index]
    att_all = [dp.attack(layout, p) for p in peer_ids]
    def_all = [dp.defence(layout, p) for p in peer_ids]
    mu, home = dp.division_mu(layout, d), dp.division_home(layout, d)
    goals_scale = math.exp(mu + home / 2.0)
    return {
        "attack": round(attack, 4),
        "defence": round(defence, 4),
        "attack_rank": 1 + sum(1 for v in att_all if v > attack + 1e-12),
        "defence_rank": 1 + sum(1 for v in def_all if v > defence + 1e-12),
        "teams_in_division": len(peer_ids),
        "home_advantage": round(home + 0.5 * hdev / goals_scale, 4),
    }


def _season_before(seasons: list[str], season: str) -> str | None:
    i = seasons.index(season)
    return seasons[i - 1] if i > 0 else None


def predict_history_full(
    history: History,
    config: V4GoalsConfig,
    *,
    baseline: V3Phase4Result | None = None,
    params: dict[str, GroupParams] | None = None,
    cache_key: str | None = None,
    workers: int | None = None,
    compute_intervals: bool | None = None,
) -> V4Run:
    t0 = time.monotonic()
    timings: dict[str, float] = {}
    matches = history.matches
    if baseline is None:
        baseline = run_v3_phase4_full(matches, cache_key=cache_key, workers=workers)
        timings["baseline"] = round(time.monotonic() - t0, 1)
    finals = baseline.finals
    seasons = sorted({m.season_label for m in matches})
    need_params = config.division_rho or config.ratings
    if need_params and params is None:
        t1 = time.monotonic()
        hypers = set(baseline.chosen_forza.values()) | {baseline.next_forza}
        params = compute_strength_params(matches, hypers, cache_key=cache_key, workers=workers)
        timings["strength_params"] = round(time.monotonic() - t1, 1)
    if compute_intervals is None:
        compute_intervals = config.uncertainty

    t2 = time.monotonic()
    # --- passo A: gol attesi dopo (a) e rho dopo (b) ---------------------------------------------
    home_adv: dict[int, HomeAdvantage] = {}
    ha_states: dict[tuple[str, str], HomeAdvState] = {}
    if config.team_home_advantage:
        home_adv = team_home_advantage(
            matches, {mid: (f.lambda_home, f.lambda_away) for mid, f in finals.items()}, states=ha_states
        )
    lam: dict[int, tuple[float, float]] = {}
    rho: dict[int, float] = {}
    for m in matches:
        f = finals.get(m.lab_match_id)
        if f is None:
            continue
        lh, la = f.lambda_home, f.lambda_away
        if config.team_home_advantage:
            ha = home_adv.get(m.lab_match_id)
            if ha is not None:
                lh, la = apply_home_advantage(lh, la, ha.kappa)
        lam[m.lab_match_id] = (lh, la)
        r = f.rho
        if config.division_rho and params is not None:
            gp = params[m.group]
            dp = gp.by_hyper[baseline.chosen_forza[m.season_label].key].get(m.day)
            if dp is not None:
                r = dp.rho_for(gp.index.div_index[m.competition])
        rho[m.lab_match_id] = r

    # --- (c) dispersione per stagione dalla stagione precedente -----------------------------------
    dispersion: dict[str, dict[str, tuple[float | None, float | None]]] = {}

    def _dispersion_rows(season: str):
        return (
            (m.competition, lam[m.lab_match_id][0], lam[m.lab_match_id][1], m.ft_home, m.ft_away)
            for m in matches
            if m.season_label == season and m.eval_eligible and m.lab_match_id in lam
        )

    if config.division_dispersion:
        for s in seasons:
            prev = _season_before(seasons, s)
            dispersion[s] = fit_dispersion(_dispersion_rows(prev)) if prev else {}
        next_dispersion = fit_dispersion(_dispersion_rows(seasons[-1]))
    else:
        for s in seasons:
            dispersion[s] = {}
        next_dispersion = {}

    # --- passo B: probabilita' non calibrate e punteggio di incertezza ------------------------------
    raw: dict[int, dict[str, float]] = {}
    unc: dict[int, Uncertainty] = {}
    alphas: dict[int, tuple[float | None, float | None]] = {}
    for m in matches:
        mid = m.lab_match_id
        if mid not in lam:
            continue
        f = finals[mid]
        a_h, a_a = dispersion[m.season_label].get(m.competition, (None, None))
        alphas[mid] = (a_h, a_a)
        lh, la = lam[mid]
        raw[mid] = all_markets(lh, la, rho[mid], f.ht_share, alpha_home=a_h, alpha_away=a_a, with_ah=config.asian_handicap)
        unc[mid] = uncertainty_score(f.home_evidence, f.away_evidence, f.opinions)

    # --- (e) calibrazione e (d) tagli per stagione dalla stagione precedente -----------------------
    calibration: dict[str, dict[str, IsotonicRegression | None]] = {}
    cuts: dict[str, tuple[float, float]] = {}
    season_info: dict[str, dict[str, Any]] = {}

    def _cal_rows(season: str):
        return (
            (raw[m.lab_match_id], market_outcomes(m.ft_home, m.ft_away, m.ht_home, m.ht_away))
            for m in matches
            if m.season_label == season and m.eval_eligible and m.lab_match_id in raw
        )

    def _scores(season: str) -> list[float]:
        return [unc[m.lab_match_id].score for m in matches if m.season_label == season and m.eval_eligible and m.lab_match_id in unc]

    for s in seasons:
        prev = _season_before(seasons, s)
        models: dict[str, IsotonicRegression | None] = {}
        if config.isotonic_calibration and prev is not None:
            models = fit_calibration(_cal_rows(prev))
        calibration[s] = models
        cuts[s] = uncertainty_cuts(_scores(prev) if prev is not None else None)
        season_info[s] = {
            "previous_season": prev,
            "calibration_applied": any(v is not None for v in models.values()),
            "uncertainty_cuts": [round(cuts[s][0], 4), round(cuts[s][1], 4)],
            "dispersion": {k: [v[0], v[1]] for k, v in sorted(dispersion[s].items())},
            "hyper_forza": baseline.chosen_forza[s].key,
        }
    last = seasons[-1]
    next_models = fit_calibration(_cal_rows(last)) if config.isotonic_calibration else {}
    next_cuts = uncertainty_cuts(_scores(last))

    # --- probabilita' finali (in blocco per stagione) e intervalli ----------------------------------
    final: dict[int, dict[str, float]] = {}
    lo_hi: dict[int, tuple[dict[str, float], dict[str, float]]] = {}
    for s in seasons:
        ids = [m.lab_match_id for m in matches if m.season_label == s and m.lab_match_id in raw]
        models = calibration[s]
        applied = config.isotonic_calibration and any(v is not None for v in models.values())
        centers = [raw[mid] for mid in ids]
        cal_centers = apply_calibration_many(centers, models) if applied else centers
        for mid, p in zip(ids, cal_centers):
            final[mid] = p
        if compute_intervals:
            los: list[dict[str, float]] = []
            his: list[dict[str, float]] = []
            for mid in ids:
                f = finals[mid]
                lh, la = lam[mid]
                sigma = INTERVAL_SIGMA_BASE + INTERVAL_SIGMA_SLOPE * unc[mid].score
                iv = market_intervals(
                    lh, la, rho[mid], f.ht_share, sigma, INTERVAL_Z90, raw[mid],
                    alpha_home=alphas[mid][0], alpha_away=alphas[mid][1], with_ah=config.asian_handicap,
                )
                los.append({k: v[0] for k, v in iv.items()})
                his.append({k: v[1] for k, v in iv.items()})
            if applied:
                los, his = apply_calibration_bounds_many(los, his, models)
            for mid, lo, hi in zip(ids, los, his):
                lo_hi[mid] = (lo, hi)

    # --- payload e righe ---------------------------------------------------------------------------
    payloads: dict[int, dict[str, Any]] = {}
    rows: dict[int, MatchRow] = {}
    seen: dict[tuple[str, str], set[str]] = {}
    n = len(matches)
    i = 0
    while i < n:
        j = i
        while j < n and matches[j].day == matches[i].day:
            j += 1
        for m in matches[i:j]:
            mid = m.lab_match_id
            if mid not in final:
                continue
            f = finals[mid]
            u = unc[mid]
            level = (
                uncertainty_level(u.score, cuts[m.season_label], new_team=u.new_team_home or u.new_team_away)
                if config.uncertainty
                else LEVEL_MEDIUM
            )
            probs = final[mid]
            lo, hi = lo_hi.get(mid, (probs, probs))
            ha = home_adv.get(mid)
            ratings: dict[str, Any] | None = None
            if config.ratings and params is not None:
                gp = params[m.group]
                dp = gp.by_hyper[baseline.chosen_forza[m.season_label].key].get(m.day)
                if dp is not None:
                    peers = set(seen.get((m.competition, m.season_label), set())) | {m.home_team, m.away_team}
                    ratings = {
                        "home": _ratings_block(gp, dp, m.competition, m.home_team, peers, ha.hdev_home if ha else 0.0),
                        "away": _ratings_block(gp, dp, m.competition, m.away_team, peers, ha.hdev_away if ha else 0.0),
                    }
            payloads[mid] = build_payload(
                lam=lam[mid],
                rho=rho[mid],
                ht_share=f.ht_share,
                alphas=alphas[mid],
                uncertainty=u,
                level=level,
                home_evidence=f.home_evidence,
                away_evidence=f.away_evidence,
                probs=probs,
                lo=lo,
                hi=hi,
                ratings=ratings,
                specialists=f.specialists,
                calibration_applied=season_info[m.season_label]["calibration_applied"],
                calibration_season=season_info[m.season_label]["previous_season"],
                home_advantage=ha,
            )
            rows[mid] = MatchRow(
                lab_match_id=mid,
                season=m.season_label,
                competition=m.competition,
                group=m.group,
                eval_eligible=m.eval_eligible,
                ft_home=m.ft_home,
                ft_away=m.ft_away,
                ht_home=m.ht_home,
                ht_away=m.ht_away,
                probs=probs,
                baseline_probs=f.probabilities,
                score=u.score,
                level=level,
            )
        for m in matches[i:j]:
            seen.setdefault((m.competition, m.season_label), set()).update((m.home_team, m.away_team))
        i = j
    timings["v4_additions"] = round(time.monotonic() - t2, 1)
    timings["total"] = round(time.monotonic() - t0, 1)

    artifacts = LiveArtifacts(
        config=config,
        season=baseline.next_season,
        fitted_on=last,
        hyper_forza=baseline.next_forza,
        hyper_game=dict(baseline.next_game),
        base_weights=dict(baseline.next_base_weights),
        final_weights=dict(baseline.next_final_weights),
        dispersion=next_dispersion,
        calibration=next_models,
        calibration_applied=any(v is not None for v in next_models.values()),
        uncertainty_cuts=next_cuts,
        home_adv_states=ha_states,
        matches_per_team={
            comp: max(m.home_played + m.home_remaining for m in matches if m.competition == comp and m.season_label == last)
            for comp in sorted({m.competition for m in matches if m.season_label == last})
        },
    )
    return V4Run(
        config=config,
        payloads=payloads,
        rows=rows,
        baseline=baseline,
        artifacts=artifacts,
        season_info=season_info,
        timings=timings,
    )


def build_payload(
    *,
    lam: tuple[float, float],
    rho: float,
    ht_share: float,
    alphas: tuple[float | None, float | None],
    uncertainty: Uncertainty,
    level: str,
    home_evidence: float,
    away_evidence: float,
    probs: dict[str, float],
    lo: dict[str, float],
    hi: dict[str, float],
    ratings: dict[str, Any] | None,
    specialists: dict[str, Any],
    calibration_applied: bool,
    calibration_season: str | None,
    home_advantage: HomeAdvantage | None,
) -> dict[str, Any]:
    """Il payload "goals" di docs/v4/API.md."""
    markets = {
        k: {
            "p": round(float(probs[k]), 6),
            "lo": round(min(float(lo.get(k, probs[k])), float(probs[k])), 6),
            "hi": round(max(float(hi.get(k, probs[k])), float(probs[k])), 6),
        }
        for k in probs
    }
    payload: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "lambda_home": round(lam[0], 5),
        "lambda_away": round(lam[1], 5),
        "rho": round(float(rho), 4),
        "ht_share": round(float(ht_share), 4),
        "dispersion": {
            "home": round(alphas[0], 5) if alphas[0] is not None else None,
            "away": round(alphas[1], 5) if alphas[1] is not None else None,
        },
        "uncertainty": {
            "score": round(uncertainty.score, 4),
            "level": level,
            "home_evidence": round(home_evidence, 3),
            "away_evidence": round(away_evidence, 3),
            "disagreement": round(uncertainty.disagreement, 4),
            "new_team_home": bool(uncertainty.new_team_home),
            "new_team_away": bool(uncertainty.new_team_away),
        },
        "markets": markets,
        "ratings": ratings,
        "specialists": specialists,
        "calibration": {"applied": bool(calibration_applied), "season": calibration_season if calibration_applied else None},
    }
    if home_advantage is not None:
        payload["home_advantage"] = {
            "kappa": round(home_advantage.kappa, 5),
            "hdev_home": round(home_advantage.hdev_home, 4),
            "hdev_away": round(home_advantage.hdev_away, 4),
        }
    return payload


def predict_history(history: History, config: V4GoalsConfig, **kwargs: Any) -> dict[int, dict[str, Any]]:
    """Payload "goals" (docs/v4/API.md) per ogni partita dello storico."""
    return predict_history_full(history, config, **kwargs).payloads


__all__ = [
    "CLASSIC_MARKETS",
    "GroupParams",
    "LiveArtifacts",
    "MatchRow",
    "V3Final",
    "V4Run",
    "build_payload",
    "compute_strength_params",
    "predict_history",
    "predict_history_full",
]
