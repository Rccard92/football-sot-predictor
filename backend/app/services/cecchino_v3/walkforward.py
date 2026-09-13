"""Previsione partita per partita usando solo il passato.

Per ogni giorno di gara di una piramide nazionale: finestra = tutte le partite
dei giorni PRECEDENTI (pesate per eta'), stima del modello, previsione delle
partite di quel giorno. Le partite dello stesso giorno non si vedono tra loro.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.services.cecchino_v3.constants import (
    COUNTRY_GROUPS,
    MIN_TIME_WEIGHT,
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


def _divisions_for(matches: list[MatchRecord]) -> tuple[str, ...]:
    group = matches[0].group
    if group in COUNTRY_GROUPS:
        return COUNTRY_GROUPS[group]
    return tuple(sorted({m.competition for m in matches}))


def run_group(
    matches: list[MatchRecord],
    hyper: Hyper,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> dict[int, StrengthPrediction]:
    """Previsioni walk-forward per tutte le partite (gia' ordinate) di una piramide."""
    if not matches:
        return {}
    divisions = _divisions_for(matches)
    div_index = {c: i for i, c in enumerate(divisions)}
    teams = sorted({m.home_team for m in matches} | {m.away_team for m in matches})
    team_index = {t: i for i, t in enumerate(teams)}

    first_season = min(m.season_label for m in matches)
    team_first_season: dict[str, str] = {}
    for m in matches:
        for t in (m.home_team, m.away_team):
            if t not in team_first_season or m.season_label < team_first_season[t]:
                team_first_season[t] = m.season_label
    newcomer = np.array(
        [1.0 if team_first_season[t] > first_season else 0.0 for t in teams], dtype=float
    )

    day = np.array([m.day for m in matches], dtype=np.int64)
    home = np.array([team_index[m.home_team] for m in matches], dtype=np.int64)
    away = np.array([team_index[m.away_team] for m in matches], dtype=np.int64)
    division = np.array([div_index[m.competition] for m in matches], dtype=np.int64)
    home_goals = np.array([m.ft_home for m in matches], dtype=float)
    away_goals = np.array([m.ft_away for m in matches], dtype=float)
    ht_total = np.array(
        [
            float(m.ht_home + m.ht_away) if m.ht_home is not None and m.ht_away is not None else np.nan
            for m in matches
        ]
    )

    layout = ParamLayout(n_divisions=len(divisions), n_teams=len(teams))
    max_age = math.log(1.0 / MIN_TIME_WEIGHT) / hyper.xi
    beta: np.ndarray | None = None
    out: dict[int, StrengthPrediction] = {}

    n = len(matches)
    start = 0
    i = 0
    while i < n:
        if should_stop is not None and should_stop():
            break
        today = day[i]
        j = i
        while j < n and day[j] == today:
            j += 1
        while start < i and today - day[start] > max_age:
            start += 1

        past = slice(start, i)
        weight = np.exp(-hyper.xi * (today - day[past]).astype(float))
        window = WindowData(
            home=home[past],
            away=away[past],
            division=division[past],
            home_goals=home_goals[past],
            away_goals=away_goals[past],
            weight=weight,
        )

        fallback = np.zeros(layout.n_teams, dtype=np.int64)
        fallback[home[i:j]] = division[i:j]
        fallback[away[i:j]] = division[i:j]
        team_div = team_divisions(
            window, n_teams=layout.n_teams, n_divisions=layout.n_divisions, fallback=fallback
        )
        beta = fit_strength(
            layout,
            window,
            team_division=team_div,
            newcomer=newcomer,
            sigma=hyper.sigma,
            beta_start=beta,
        )

        if window.home.size:
            lam_h_w, lam_a_w = expected_goals(
                layout,
                beta,
                division=window.division,
                home=window.home,
                away=window.away,
                team_division=team_div,
                newcomer=newcomer,
            )
            rho = fit_rho(window.home_goals, window.away_goals, lam_h_w, lam_a_w, weight)
            shares = fit_ht_share(
                window.division,
                window.home_goals + window.away_goals,
                ht_total[past],
                weight,
                n_divisions=layout.n_divisions,
            )
            evidence = np.bincount(window.home, weights=weight, minlength=layout.n_teams) + np.bincount(
                window.away, weights=weight, minlength=layout.n_teams
            )
        else:
            rho = 0.0
            shares = np.full(layout.n_divisions, PRIOR_HT_SHARE)
            evidence = np.zeros(layout.n_teams)

        lam_h, lam_a = expected_goals(
            layout,
            beta,
            division=division[i:j],
            home=home[i:j],
            away=away[i:j],
            team_division=team_div,
            newcomer=newcomer,
        )
        for k in range(j - i):
            idx = i + k
            out[matches[idx].lab_match_id] = StrengthPrediction(
                lab_match_id=matches[idx].lab_match_id,
                lambda_home=float(lam_h[k]),
                lambda_away=float(lam_a[k]),
                rho=rho,
                ht_share=float(shares[division[idx]]),
                home_evidence=float(evidence[home[idx]]),
                away_evidence=float(evidence[away[idx]]),
            )
        i = j
    return out
