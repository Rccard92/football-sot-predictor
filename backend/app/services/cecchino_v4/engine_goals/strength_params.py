"""Passo walk-forward della Forza rieseguito dalla V4 per leggere i parametri
del giorno (beta) che il walk-forward V3 non espone: attacco/difesa per squadra
(blocco `ratings`), vantaggio casa e livello della divisione, rho per divisione
(novita' b). Usa le stesse funzioni di `cecchino_v3.strength_model` e la stessa
finestra/peso di `cecchino_v3.walkforward`; il problema e' convesso, quindi i
parametri coincidono con quelli della V3 a meno della tolleranza di Newton.

Le stesse funzioni servono al live per stimare UNA finestra per (piramide,
giorno bersaglio) senza rifare tutto il walk-forward.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import numpy as np
from threadpoolctl import threadpool_limits

from app.services.cecchino_v3.constants import (
    CONVERSION_PSEUDO_COUNT,
    MIN_TIME_WEIGHT,
    PRIOR_GOALS_PER_STAT,
    PRIOR_HT_SHARE,
    PRIOR_LOG_GOALS,
    Hyper,
)
from app.services.cecchino_v3.data import MatchRecord
from app.services.cecchino_v3.strength_model import (
    ParamLayout,
    WindowData,
    expected_goals,
    fit_ht_share,
    fit_rho,
    fit_strength,
    team_divisions,
)
from app.services.cecchino_v3.walkforward import divisions_for

from app.services.cecchino_v4.engine_goals.config import DIVISION_RHO_MIN_WEIGHT


@dataclass
class GroupIndex:
    """Indici numerici di una piramide (copia V4 di `walkforward._GroupArrays`,
    con le squadre in piu' richieste dal live)."""

    matches: list[MatchRecord]
    divisions: tuple[str, ...]
    div_index: dict[str, int]
    teams: list[str]
    team_index: dict[str, int]
    layout: ParamLayout
    newcomer: np.ndarray
    day: np.ndarray
    home: np.ndarray
    away: np.ndarray
    division: np.ndarray
    home_goals: np.ndarray
    away_goals: np.ndarray
    ht_total: np.ndarray
    home_sot: np.ndarray
    away_sot: np.ndarray
    usable_sot: np.ndarray
    home_shots: np.ndarray
    away_shots: np.ndarray
    usable_shots: np.ndarray

    def stat_arrays(self, stat: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if stat == "sot":
            return self.home_sot, self.away_sot, self.usable_sot
        if stat == "shots":
            return self.home_shots, self.away_shots, self.usable_shots
        raise ValueError(f"statistica non supportata: {stat!r}")


def prepare_group(matches: list[MatchRecord], *, extra_teams: Iterable[str] = ()) -> GroupIndex:
    """Come `walkforward._prepare` (movers=False). `extra_teams`: squadre da
    prevedere che non compaiono nella storia (live), trattate come nuove."""
    if not matches:
        raise ValueError("gruppo vuoto")
    divisions = divisions_for(matches)
    div_index = {c: i for i, c in enumerate(divisions)}
    known = {m.home_team for m in matches} | {m.away_team for m in matches}
    extras = sorted(set(extra_teams) - known)
    teams = sorted(known) + extras
    team_index = {t: i for i, t in enumerate(teams)}

    first_season = min(m.season_label for m in matches)
    team_first_season: dict[str, str] = {}
    for m in matches:
        for t in (m.home_team, m.away_team):
            if t not in team_first_season or m.season_label < team_first_season[t]:
                team_first_season[t] = m.season_label
    newcomer = np.array(
        [1.0 if (t not in team_first_season or team_first_season[t] > first_season) else 0.0 for t in teams]
    )

    def pair_arrays(pairs: list[tuple[int | None, int | None]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        usable = np.array([h is not None and a is not None for h, a in pairs], dtype=bool)
        home = np.array([float(h) if h is not None else 0.0 for h, _ in pairs])
        away = np.array([float(a) if a is not None else 0.0 for _, a in pairs])
        return home, away, usable

    hs, as_, us = pair_arrays([(m.home_sot, m.away_sot) for m in matches])
    hsh, ash, ush = pair_arrays([(m.home_shots, m.away_shots) for m in matches])
    return GroupIndex(
        matches=matches,
        divisions=divisions,
        div_index=div_index,
        teams=teams,
        team_index=team_index,
        layout=ParamLayout(n_divisions=len(divisions), n_teams=len(teams), movers=False),
        newcomer=newcomer,
        day=np.array([m.day for m in matches], dtype=np.int64),
        home=np.array([team_index[m.home_team] for m in matches], dtype=np.int64),
        away=np.array([team_index[m.away_team] for m in matches], dtype=np.int64),
        division=np.array([div_index[m.competition] for m in matches], dtype=np.int64),
        home_goals=np.array([m.ft_home for m in matches], dtype=float),
        away_goals=np.array([m.ft_away for m in matches], dtype=float),
        ht_total=np.array(
            [
                float(m.ht_home + m.ht_away) if m.ht_home is not None and m.ht_away is not None else np.nan
                for m in matches
            ]
        ),
        home_sot=hs,
        away_sot=as_,
        usable_sot=us,
        home_shots=hsh,
        away_shots=ash,
        usable_shots=ush,
    )


def window_rows(g: GroupIndex, today: int, hyper: Hyper) -> tuple[np.ndarray, np.ndarray]:
    """Righe della finestra (giorni strettamente precedenti, entro l'eta' massima)
    e loro peso temporale."""
    max_age = math.log(1.0 / MIN_TIME_WEIGHT) / hyper.xi
    rows = np.nonzero((g.day < today) & (today - g.day <= max_age))[0]
    weight = np.exp(-hyper.xi * (today - g.day[rows]).astype(float))
    return rows, weight


def _fallback(g: GroupIndex, division_of_targets: dict[int, int]) -> np.ndarray:
    fallback = np.zeros(g.layout.n_teams, dtype=np.int64)
    for team, div in division_of_targets.items():
        fallback[team] = div
    return fallback


@dataclass
class DayParams:
    """Parametri della Forza stimati un giorno, dalla finestra dei giorni precedenti."""

    day: int
    beta: np.ndarray
    team_division: np.ndarray
    evidence: np.ndarray  # partite equivalenti per squadra
    rho_group: float
    rho_division: np.ndarray  # nan dove il peso della divisione e' insufficiente
    division_weight: np.ndarray
    ht_share: np.ndarray

    def attack(self, layout: ParamLayout, team: int) -> float:
        return float(self.beta[layout.team_att(np.array([team]))[0]])

    def defence(self, layout: ParamLayout, team: int) -> float:
        return float(self.beta[layout.team_def(np.array([team]))[0]])

    def division_home(self, layout: ParamLayout, division: int) -> float:
        return float(self.beta[layout.home[division]])

    def division_mu(self, layout: ParamLayout, division: int) -> float:
        return float(self.beta[layout.mu[division]])

    def rho_for(self, division: int) -> float:
        r = float(self.rho_division[division])
        return self.rho_group if math.isnan(r) else r


def fit_day(
    g: GroupIndex,
    today: int,
    hyper: Hyper,
    *,
    fallback: np.ndarray,
    beta_start: np.ndarray | None = None,
) -> DayParams:
    """Stima della Forza (gol) sulla finestra dei giorni precedenti a `today`."""
    rows, weight = window_rows(g, today, hyper)
    layout = g.layout
    window = WindowData(
        home=g.home[rows],
        away=g.away[rows],
        division=g.division[rows],
        home_goals=g.home_goals[rows],
        away_goals=g.away_goals[rows],
        weight=weight,
    )
    team_div = team_divisions(window, n_teams=layout.n_teams, n_divisions=layout.n_divisions, fallback=fallback)
    beta = fit_strength(layout, window, team_division=team_div, newcomer=g.newcomer, sigma=hyper.sigma, beta_start=beta_start)
    n_div = layout.n_divisions
    rho_division = np.full(n_div, np.nan)
    div_weight = np.zeros(n_div)
    if rows.size:
        lam_h, lam_a = expected_goals(
            layout, beta, division=window.division, home=window.home, away=window.away, team_division=team_div, newcomer=g.newcomer
        )
        rho_group = fit_rho(window.home_goals, window.away_goals, lam_h, lam_a, weight)
        div_weight = np.bincount(window.division, weights=weight, minlength=n_div)
        for d in range(n_div):
            if div_weight[d] >= DIVISION_RHO_MIN_WEIGHT:
                sel = window.division == d
                rho_division[d] = fit_rho(
                    window.home_goals[sel], window.away_goals[sel], lam_h[sel], lam_a[sel], weight[sel]
                )
        shares = fit_ht_share(window.division, window.home_goals + window.away_goals, g.ht_total[rows], weight, n_divisions=n_div)
        evidence = np.bincount(window.home, weights=weight, minlength=layout.n_teams) + np.bincount(
            window.away, weights=weight, minlength=layout.n_teams
        )
    else:
        rho_group = 0.0
        shares = np.full(n_div, PRIOR_HT_SHARE)
        evidence = np.zeros(layout.n_teams)
    return DayParams(
        day=today,
        beta=beta,
        team_division=team_div,
        evidence=evidence,
        rho_group=rho_group,
        rho_division=rho_division,
        division_weight=div_weight,
        ht_share=shares,
    )


@dataclass
class GameDayParams:
    """Parametri dello specialista Gioco (tiri in porta o tiri) stimati un giorno."""

    day: int
    stat: str
    beta: np.ndarray
    team_division: np.ndarray
    conversion: np.ndarray  # gol per unita' di volume, per divisione
    evidence: np.ndarray


def fit_game_day(
    g: GroupIndex,
    today: int,
    hyper: Hyper,
    stat: str,
    *,
    fallback: np.ndarray,
    beta_start: np.ndarray | None = None,
) -> GameDayParams:
    """Come `walkforward._run_game` per un solo giorno."""
    rows, _ = window_rows(g, today, hyper)
    stat_home, stat_away, usable = g.stat_arrays(stat)
    rows = rows[usable[rows]]  # solo partite con la statistica disponibile
    weight = np.exp(-hyper.xi * (today - g.day[rows]).astype(float))
    layout = g.layout
    prior_rate = PRIOR_GOALS_PER_STAT[stat]
    pseudo = CONVERSION_PSEUDO_COUNT[stat]
    window = WindowData(
        home=g.home[rows],
        away=g.away[rows],
        division=g.division[rows],
        home_goals=stat_home[rows],
        away_goals=stat_away[rows],
        weight=weight,
    )
    team_div = team_divisions(window, n_teams=layout.n_teams, n_divisions=layout.n_divisions, fallback=fallback)
    beta = fit_strength(
        layout,
        window,
        team_division=team_div,
        newcomer=g.newcomer,
        sigma=hyper.sigma,
        beta_start=beta_start,
        prior_log_level=math.log(1.3 / prior_rate),
    )
    goals = np.bincount(window.division, weights=weight * (g.home_goals[rows] + g.away_goals[rows]), minlength=layout.n_divisions)
    volume = np.bincount(window.division, weights=weight * (window.home_goals + window.away_goals), minlength=layout.n_divisions)
    conversion = (goals + prior_rate * pseudo) / (volume + pseudo)
    evidence = (
        np.bincount(window.home, weights=weight, minlength=layout.n_teams)
        + np.bincount(window.away, weights=weight, minlength=layout.n_teams)
        if rows.size
        else np.zeros(layout.n_teams)
    )
    return GameDayParams(day=today, stat=stat, beta=beta, team_division=team_div, conversion=conversion, evidence=evidence)


def predict_pairs(
    g: GroupIndex,
    beta: np.ndarray,
    team_division: np.ndarray,
    *,
    division: np.ndarray,
    home: np.ndarray,
    away: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Valori attesi (gol o volume) casa e ospite per le coppie indicate."""
    return expected_goals(
        g.layout, beta, division=division, home=home, away=away, team_division=team_division, newcomer=g.newcomer
    )


def _match_days(g: GroupIndex) -> Iterator[tuple[int, int, int]]:
    n = len(g.matches)
    i = 0
    while i < n:
        today = int(g.day[i])
        j = i
        while j < n and g.day[j] == today:
            j += 1
        yield today, i, j
        i = j


def walk_strength_params(
    matches: list[MatchRecord], hyper: Hyper, *, days: set[int] | None = None
) -> dict[int, DayParams]:
    """Parametri della Forza per ogni giorno di gara della piramide (o solo per
    i giorni in `days`), ognuno stimato sulla finestra dei giorni precedenti."""
    if not matches:
        return {}
    g = prepare_group(matches)
    out: dict[int, DayParams] = {}
    beta: np.ndarray | None = None
    with threadpool_limits(limits=1, user_api="blas"):
        for today, i, j in _match_days(g):
            if days is not None and today not in days:
                continue
            fallback = _fallback(g, {**dict(zip(g.home[i:j].tolist(), g.division[i:j].tolist())), **dict(zip(g.away[i:j].tolist(), g.division[i:j].tolist()))})
            params = fit_day(g, today, hyper, fallback=fallback, beta_start=beta)
            beta = params.beta
            out[today] = params
    return out


__all__ = [
    "DayParams",
    "GameDayParams",
    "GroupIndex",
    "fit_day",
    "fit_game_day",
    "predict_pairs",
    "prepare_group",
    "walk_strength_params",
    "window_rows",
]
