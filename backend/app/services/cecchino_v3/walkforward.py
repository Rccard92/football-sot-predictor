"""Previsione partita per partita usando solo il passato.

Per ogni giorno di gara di una piramide nazionale: finestra = tutte le partite
dei giorni PRECEDENTI (pesate per eta'), stima del modello, previsione delle
partite di quel giorno. Le partite dello stesso giorno non si vedono tra loro.

Specialisti:
- Forza: attacco/difesa sui gol (+ correzione pareggi e quota primo tempo).
- Gioco: stesso modello sui tiri in porta o sui tiri; il volume previsto e'
  tradotto in gol attesi con il tasso di conversione della divisione.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np
from threadpoolctl import threadpool_limits

from app.services.cecchino_v3.constants import (
    CONVERSION_PSEUDO_COUNT,
    COUNTRY_GROUPS,
    MIN_TIME_WEIGHT,
    PRIOR_GOALS_PER_STAT,
    PRIOR_HT_SHARE,
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


@dataclass(frozen=True)
class StrengthPrediction:
    lab_match_id: int
    lambda_home: float
    lambda_away: float
    rho: float
    ht_share: float
    home_evidence: float  # partite "equivalenti" della squadra nella finestra
    away_evidence: float
    # parametri promozione/retrocessione stimati quel giorno (solo movers)
    movers: dict[str, float] | None = None


@dataclass(frozen=True)
class GamePrediction:
    lab_match_id: int
    lambda_home: float  # gol attesi tradotti dal volume di gioco
    lambda_away: float
    stat_home: float  # volume atteso (tiri in porta o tiri)
    stat_away: float
    conversion: float  # gol per unita' di volume nella divisione
    home_evidence: float
    away_evidence: float
    movers: dict[str, float] | None = None


@dataclass
class _GroupArrays:
    matches: list[MatchRecord]
    layout: ParamLayout
    newcomer: np.ndarray
    day: np.ndarray
    home: np.ndarray
    away: np.ndarray
    division: np.ndarray
    home_goals: np.ndarray
    away_goals: np.ndarray
    ht_total: np.ndarray
    # (n, 2): [promossa, retrocessa] rispetto alla stagione precedente
    home_move: np.ndarray
    away_move: np.ndarray


def divisions_for(matches: list[MatchRecord]) -> tuple[str, ...]:
    group = matches[0].group
    if group in COUNTRY_GROUPS:
        return COUNTRY_GROUPS[group]
    return tuple(sorted({m.competition for m in matches}))


def mover_flags(
    matches: list[MatchRecord], div_index: dict[str, int]
) -> tuple[np.ndarray, np.ndarray]:
    """Per ogni partita e squadra: promossa (sale di divisione) o retrocessa
    (scende) rispetto alla stagione precedente del dataset. Dipende solo da
    dove la squadra gioca, noto prima della stagione."""
    seasons = sorted({m.season_label for m in matches})
    previous = {s: seasons[i - 1] for i, s in enumerate(seasons) if i > 0}
    division_of: dict[tuple[str, str], int] = {}
    for m in matches:
        d = div_index[m.competition]
        division_of[(m.season_label, m.home_team)] = d
        division_of[(m.season_label, m.away_team)] = d

    def flags(m: MatchRecord, team: str) -> tuple[float, float]:
        prev_season = previous.get(m.season_label)
        if prev_season is None:
            return 0.0, 0.0
        before = division_of.get((prev_season, team))
        if before is None:
            return 0.0, 0.0
        now = div_index[m.competition]
        return (1.0 if now < before else 0.0), (1.0 if now > before else 0.0)

    home = np.array([flags(m, m.home_team) for m in matches], dtype=float).reshape(-1, 2)
    away = np.array([flags(m, m.away_team) for m in matches], dtype=float).reshape(-1, 2)
    return home, away


def _prepare(matches: list[MatchRecord], *, movers: bool = False) -> _GroupArrays:
    divisions = divisions_for(matches)
    div_index = {c: i for i, c in enumerate(divisions)}
    home_move, away_move = mover_flags(matches, div_index)
    teams = sorted({m.home_team for m in matches} | {m.away_team for m in matches})
    team_index = {t: i for i, t in enumerate(teams)}

    first_season = min(m.season_label for m in matches)
    team_first_season: dict[str, str] = {}
    for m in matches:
        for t in (m.home_team, m.away_team):
            if t not in team_first_season or m.season_label < team_first_season[t]:
                team_first_season[t] = m.season_label

    return _GroupArrays(
        matches=matches,
        layout=ParamLayout(n_divisions=len(divisions), n_teams=len(teams), movers=movers),
        newcomer=np.array(
            [1.0 if team_first_season[t] > first_season else 0.0 for t in teams], dtype=float
        ),
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
        home_move=home_move,
        away_move=away_move,
    )


def _mover_values(layout: ParamLayout, beta: np.ndarray) -> dict[str, float] | None:
    indices = layout.mover_indices()
    if not indices:
        return None
    return {name: float(beta[idx]) for name, idx in indices.items()}


def _match_days(
    g: _GroupArrays, hyper: Hyper, should_stop: Callable[[], bool] | None
) -> Iterator[tuple[int, int, slice, np.ndarray]]:
    """Per ogni giorno di gara: (inizio, fine) delle partite del giorno,
    finestra delle partite precedenti e loro peso temporale."""
    max_age = math.log(1.0 / MIN_TIME_WEIGHT) / hyper.xi
    n = len(g.matches)
    start = 0
    i = 0
    while i < n:
        if should_stop is not None and should_stop():
            return
        today = g.day[i]
        j = i
        while j < n and g.day[j] == today:
            j += 1
        while start < i and today - g.day[start] > max_age:
            start += 1
        past = slice(start, i)
        yield i, j, past, np.exp(-hyper.xi * (today - g.day[past]).astype(float))
        i = j


def _fallback_divisions(g: _GroupArrays, i: int, j: int) -> np.ndarray:
    fallback = np.zeros(g.layout.n_teams, dtype=np.int64)
    fallback[g.home[i:j]] = g.division[i:j]
    fallback[g.away[i:j]] = g.division[i:j]
    return fallback


def _evidence(window: WindowData, n_teams: int) -> np.ndarray:
    return np.bincount(window.home, weights=window.weight, minlength=n_teams) + np.bincount(
        window.away, weights=window.weight, minlength=n_teams
    )


# --- Specialista Forza ---------------------------------------------------------------


def run_group(
    matches: list[MatchRecord],
    hyper: Hyper,
    *,
    should_stop: Callable[[], bool] | None = None,
    movers: bool = False,
) -> dict[int, StrengthPrediction]:
    """Previsioni walk-forward dello specialista Forza per una piramide."""
    if not matches:
        return {}
    # Migliaia di sistemi lineari piccoli (~200x200): con i thread BLAS di un
    # server a molti core il costo di coordinamento li rende ~200 volte piu'
    # lenti. Un solo thread per tutta la durata del calcolo.
    with threadpool_limits(limits=1, user_api="blas"):
        return _run_strength(_prepare(matches, movers=movers), hyper, should_stop)


def _run_strength(
    g: _GroupArrays, hyper: Hyper, should_stop: Callable[[], bool] | None
) -> dict[int, StrengthPrediction]:
    layout = g.layout
    beta: np.ndarray | None = None
    out: dict[int, StrengthPrediction] = {}
    for i, j, past, weight in _match_days(g, hyper, should_stop):
        window = WindowData(
            home=g.home[past],
            away=g.away[past],
            division=g.division[past],
            home_goals=g.home_goals[past],
            away_goals=g.away_goals[past],
            weight=weight,
            home_move=g.home_move[past] if layout.movers else None,
            away_move=g.away_move[past] if layout.movers else None,
        )
        team_div = team_divisions(
            window,
            n_teams=layout.n_teams,
            n_divisions=layout.n_divisions,
            fallback=_fallback_divisions(g, i, j),
        )
        beta = fit_strength(
            layout, window, team_division=team_div, newcomer=g.newcomer, sigma=hyper.sigma, beta_start=beta
        )

        if window.home.size:
            lam_h_w, lam_a_w = expected_goals(
                layout,
                beta,
                division=window.division,
                home=window.home,
                away=window.away,
                team_division=team_div,
                newcomer=g.newcomer,
                home_move=window.home_move,
                away_move=window.away_move,
            )
            rho = fit_rho(window.home_goals, window.away_goals, lam_h_w, lam_a_w, weight)
            shares = fit_ht_share(
                window.division,
                window.home_goals + window.away_goals,
                g.ht_total[past],
                weight,
                n_divisions=layout.n_divisions,
            )
            evidence = _evidence(window, layout.n_teams)
        else:
            rho = 0.0
            shares = np.full(layout.n_divisions, PRIOR_HT_SHARE)
            evidence = np.zeros(layout.n_teams)

        lam_h, lam_a = expected_goals(
            layout,
            beta,
            division=g.division[i:j],
            home=g.home[i:j],
            away=g.away[i:j],
            team_division=team_div,
            newcomer=g.newcomer,
            home_move=g.home_move[i:j] if layout.movers else None,
            away_move=g.away_move[i:j] if layout.movers else None,
        )
        movers_today = _mover_values(layout, beta)
        for k in range(j - i):
            idx = i + k
            mid = g.matches[idx].lab_match_id
            out[mid] = StrengthPrediction(
                lab_match_id=mid,
                lambda_home=float(lam_h[k]),
                lambda_away=float(lam_a[k]),
                rho=rho,
                ht_share=float(shares[g.division[idx]]),
                home_evidence=float(evidence[g.home[idx]]),
                away_evidence=float(evidence[g.away[idx]]),
                movers=movers_today,
            )
    return out


# --- Specialista Gioco ---------------------------------------------------------------


def _stat_arrays(matches: list[MatchRecord], stat: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if stat == "sot":
        pairs = [(m.home_sot, m.away_sot) for m in matches]
    elif stat == "shots":
        pairs = [(m.home_shots, m.away_shots) for m in matches]
    else:
        raise ValueError(f"statistica di gioco non supportata: {stat!r}")
    usable = np.array([h is not None and a is not None for h, a in pairs], dtype=bool)
    home = np.array([float(h) if h is not None else 0.0 for h, _ in pairs])
    away = np.array([float(a) if a is not None else 0.0 for _, a in pairs])
    return home, away, usable


def run_game_group(
    matches: list[MatchRecord],
    hyper: Hyper,
    stat: str,
    *,
    should_stop: Callable[[], bool] | None = None,
    movers: bool = False,
) -> dict[int, GamePrediction]:
    """Previsioni walk-forward dello specialista Gioco (tiri in porta o tiri)."""
    if not matches:
        return {}
    with threadpool_limits(limits=1, user_api="blas"):
        return _run_game(_prepare(matches, movers=movers), hyper, stat, should_stop)


def _run_game(
    g: _GroupArrays, hyper: Hyper, stat: str, should_stop: Callable[[], bool] | None
) -> dict[int, GamePrediction]:
    layout = g.layout
    stat_home, stat_away, usable = _stat_arrays(g.matches, stat)
    prior_rate = PRIOR_GOALS_PER_STAT[stat]
    pseudo = CONVERSION_PSEUDO_COUNT[stat]
    beta: np.ndarray | None = None
    out: dict[int, GamePrediction] = {}

    for i, j, past, weight in _match_days(g, hyper, should_stop):
        rows = np.arange(past.start, past.stop)[usable[past]]
        w = weight[usable[past]]
        window = WindowData(
            home=g.home[rows],
            away=g.away[rows],
            division=g.division[rows],
            home_goals=stat_home[rows],
            away_goals=stat_away[rows],
            weight=w,
            home_move=g.home_move[rows] if layout.movers else None,
            away_move=g.away_move[rows] if layout.movers else None,
        )
        team_div = team_divisions(
            window,
            n_teams=layout.n_teams,
            n_divisions=layout.n_divisions,
            fallback=_fallback_divisions(g, i, j),
        )
        # a priori il volume parte dalla media dei gol divisa per la conversione
        beta = fit_strength(
            layout,
            window,
            team_division=team_div,
            newcomer=g.newcomer,
            sigma=hyper.sigma,
            beta_start=beta,
            prior_log_level=math.log(1.3 / prior_rate),
        )
        goals = np.bincount(
            window.division,
            weights=w * (g.home_goals[rows] + g.away_goals[rows]),
            minlength=layout.n_divisions,
        )
        volume = np.bincount(
            window.division, weights=w * (window.home_goals + window.away_goals), minlength=layout.n_divisions
        )
        conversion = (goals + prior_rate * pseudo) / (volume + pseudo)
        evidence = _evidence(window, layout.n_teams) if window.home.size else np.zeros(layout.n_teams)

        vol_h, vol_a = expected_goals(
            layout,
            beta,
            division=g.division[i:j],
            home=g.home[i:j],
            away=g.away[i:j],
            team_division=team_div,
            newcomer=g.newcomer,
            home_move=g.home_move[i:j] if layout.movers else None,
            away_move=g.away_move[i:j] if layout.movers else None,
        )
        movers_today = _mover_values(layout, beta)
        for k in range(j - i):
            idx = i + k
            mid = g.matches[idx].lab_match_id
            conv = float(conversion[g.division[idx]])
            out[mid] = GamePrediction(
                lab_match_id=mid,
                lambda_home=float(vol_h[k]) * conv,
                lambda_away=float(vol_a[k]) * conv,
                stat_home=float(vol_h[k]),
                stat_away=float(vol_a[k]),
                conversion=conv,
                home_evidence=float(evidence[g.home[idx]]),
                away_evidence=float(evidence[g.away[idx]]),
                movers=movers_today,
            )
    return out
