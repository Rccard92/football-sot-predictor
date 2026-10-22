"""Modello statistico degli specialisti V5: stesse formule dell'esame (docs/v5/esami/STATISTICI_V1_PREREGISTRAZIONE.md).

Per una statistica X (tiri in porta, angoli, cartellini = gialli + 2 x rossi):
- medie del campionato nella stagione fino al giorno prima, per lato (casa/ospite); sotto 30 partite si usa la
  media di tutta la divisione nello storico caricato;
- forza di ogni squadra = media dei rapporti X fatto / media del lato e X concesso / media del lato avversario sulle
  ultime 30 partite (qualsiasi campionato), ristretta verso 1 con peso k;
- attese: casa = media casa x attacco casa x difesa ospite (e simmetrico), con l'ingrediente specifico;
- distribuzione binomiale negativa con la dispersione stimata sullo sviluppo.
Nessuna quota entra qui.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_v5.constants import (
    LEAGUE_FALLBACK_BELOW,
    LEAGUE_MIN_MATCHES,
    REFEREE_SHRINK,
    TEAM_WINDOW,
    StatSpecialist,
)

STATS = ("sot", "corners", "cards")


def season_of(d: date) -> int:
    return d.year if d.month >= 7 else d.year - 1


def referee_key(name: str | None) -> str | None:
    """"Michael Oliver, England" e "M Oliver" -> "m oliver" (iniziale del nome + cognome)."""
    if not name:
        return None
    base = str(name).split(",")[0].strip().replace(".", " ")
    parts = [p for p in base.split() if p]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0][0]} {parts[-1]}".lower()


@dataclass
class HistMatch:
    division: str
    season: int
    day: date
    home: str
    away: str
    referee: str | None
    values: dict[str, tuple[float, float]]  # statistica -> (casa, ospite)
    goals: tuple[float, float] | None


@dataclass
class StatIndex:
    """Medie di campionato e rapporti delle squadre per una statistica, precalcolati sullo storico."""

    stat: str
    # (divisione, stagione) -> giorni ordinati e somme cumulative (casa, ospite, partite) prima di ciascun giorno
    league_days: dict[tuple[str, int], list[date]] = field(default_factory=dict)
    league_cum: dict[tuple[str, int], list[tuple[float, float, int]]] = field(default_factory=dict)
    division_mean: dict[str, tuple[float, float]] = field(default_factory=dict)
    # squadra -> lista ordinata di (giorno, rapporto fatto, rapporto concesso)
    team_entries: dict[str, list[tuple[date, float, float]]] = field(default_factory=dict)
    # arbitro -> lista ordinata di (giorno, rapporto cartellini totali / media)
    referee_entries: dict[str, list[tuple[date, float]]] = field(default_factory=dict)

    def league_means(self, division: str, season: int, day: date) -> tuple[float, float, int] | None:
        """(media casa, media ospite, partite precedenti) prima di `day`; media di divisione sotto la soglia."""
        days = self.league_days.get((division, season)) or []
        idx = bisect_left(days, day)  # partite con giorno < day
        cum = self.league_cum.get((division, season)) or []
        sum_h, sum_a, n = cum[idx] if cum else (0.0, 0.0, 0)
        fallback = self.division_mean.get(division)
        if n >= LEAGUE_FALLBACK_BELOW:
            return sum_h / n, sum_a / n, n
        if fallback is None:
            return None
        return fallback[0], fallback[1], n


def _build_index(matches: list[HistMatch], stat: str) -> StatIndex:
    idx = StatIndex(stat=stat)
    per_league: dict[tuple[str, int], dict[date, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    div_sum: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for m in matches:
        v = m.values.get(stat)
        if v is None:
            continue
        per_league[(m.division, m.season)][m.day].append(v)
        acc = div_sum[m.division]
        acc[0] += v[0]
        acc[1] += v[1]
        acc[2] += 1
    for div, (sh, sa, n) in div_sum.items():
        if n > 0:
            idx.division_mean[div] = (sh / n, sa / n)
    for key, by_day in per_league.items():
        days = sorted(by_day)
        cum: list[tuple[float, float, int]] = []
        sh = sa = 0.0
        n = 0
        for d in days:
            cum.append((sh, sa, n))  # prima del giorno d
            for h, a in by_day[d]:
                sh += h
                sa += a
                n += 1
        cum.append((sh, sa, n))  # dopo l'ultimo giorno
        idx.league_days[key] = days
        idx.league_cum[key] = cum
    team: dict[str, list[tuple[date, float, float]]] = defaultdict(list)
    referee: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for m in matches:
        v = m.values.get(stat)
        if v is None:
            continue
        means = idx.league_means(m.division, m.season, m.day)
        if means is None or means[0] <= 0 or means[1] <= 0:
            continue
        mh, ma, _ = means
        team[m.home].append((m.day, v[0] / mh, v[1] / ma))
        team[m.away].append((m.day, v[1] / ma, v[0] / mh))
        ref = referee_key(m.referee)
        if ref:
            referee[ref].append((m.day, (v[0] + v[1]) / (mh + ma)))
    idx.team_entries = {k: sorted(v, key=lambda e: e[0]) for k, v in team.items()}
    idx.referee_entries = {k: sorted(v, key=lambda e: e[0]) for k, v in referee.items()}
    return idx


@dataclass
class History:
    matches: list[HistMatch]
    indexes: dict[str, StatIndex]
    goals_index: StatIndex


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def load_history(db: Session, *, since: date = date(2023, 7, 1)) -> History:
    """Storico football-data del Lab (16 campionati) da `since`: basta per la finestra di 30 partite."""
    rows = db.execute(
        text(
            """
            SELECT division_code, match_date, home_team, away_team, referee,
                   home_shots_on_target, away_shots_on_target, home_corners, away_corners,
                   home_yellow_cards, away_yellow_cards, home_red_cards, away_red_cards,
                   ft_home_goals, ft_away_goals
            FROM cecchino_lab_matches
            WHERE match_date >= :since
            ORDER BY match_date, id
            """
        ),
        {"since": since},
    ).all()
    matches: list[HistMatch] = []
    for r in rows:
        values: dict[str, tuple[float, float]] = {}
        sh, sa = _f(r.home_shots_on_target), _f(r.away_shots_on_target)
        if sh is not None and sa is not None:
            values["sot"] = (sh, sa)
        ch, ca = _f(r.home_corners), _f(r.away_corners)
        if ch is not None and ca is not None:
            values["corners"] = (ch, ca)
        yh, ya = _f(r.home_yellow_cards), _f(r.away_yellow_cards)
        if yh is not None and ya is not None:
            values["cards"] = (yh + 2 * (_f(r.home_red_cards) or 0.0), ya + 2 * (_f(r.away_red_cards) or 0.0))
        gh, ga = _f(r.ft_home_goals), _f(r.ft_away_goals)
        goals = (gh, ga) if gh is not None and ga is not None else None
        if goals is not None:
            values["goals"] = goals
        matches.append(
            HistMatch(
                division=str(r.division_code),
                season=season_of(r.match_date),
                day=r.match_date,
                home=str(r.home_team),
                away=str(r.away_team),
                referee=r.referee,
                values=values,
                goals=goals,
            )
        )
    return History(
        matches=matches,
        indexes={s: _build_index(matches, s) for s in STATS},
        goals_index=_build_index(matches, "goals"),
    )


def _strength(entries: list[tuple[date, float, float]], day: date, k: float) -> tuple[float, float, int]:
    pos = bisect_left([e[0] for e in entries], day)
    window = entries[max(0, pos - TEAM_WINDOW) : pos]
    n = len(window)
    att = (sum(e[1] for e in window) + k) / (n + k)
    dfn = (sum(e[2] for e in window) + k) / (n + k)
    return att, dfn, n


def _referee_factor(idx: StatIndex, referee: str | None, day: date) -> float:
    key = referee_key(referee)
    entries = idx.referee_entries.get(key) if key else None
    if not entries:
        return 1.0
    pos = bisect_left([e[0] for e in entries], day)
    prior = entries[:pos]
    return (sum(e[1] for e in prior) + REFEREE_SHRINK) / (len(prior) + REFEREE_SHRINK)


@dataclass
class StatExpectation:
    home: float
    away: float
    league_matches: int

    @property
    def total(self) -> float:
        return self.home + self.away


def expected_counts(
    history: History,
    spec: StatSpecialist,
    *,
    division: str,
    day: date,
    home: str,
    away: str,
    lambda_home: float | None,
    lambda_away: float | None,
    referee: str | None = None,
) -> StatExpectation | None:
    """Attese di casa e ospite per lo specialista, None se mancano dati sufficienti."""
    idx = history.indexes[spec.stat]
    season = season_of(day)
    means = idx.league_means(division, season, day)
    if means is None:
        return None
    mh, ma, n_league = means
    if n_league < LEAGUE_MIN_MATCHES or mh <= 0 or ma <= 0:
        return None
    att_h, def_h, _ = _strength(idx.team_entries.get(home, []), day, spec.k)
    att_a, def_a, _ = _strength(idx.team_entries.get(away, []), day, spec.k)
    lh = mh * att_h * def_a
    la = ma * att_a * def_h
    if spec.gamma and lambda_home and lambda_away and lambda_home > 0 and lambda_away > 0:
        if spec.stat == "corners":
            lh *= (lambda_home / lambda_away) ** spec.gamma
            la *= (lambda_away / lambda_home) ** spec.gamma
        else:  # tiri in porta: gol attesi rispetto alla media gol del campionato
            g = history.goals_index.league_means(division, season, day)
            if g is not None and g[0] > 0 and g[1] > 0:
                lh *= (lambda_home / g[0]) ** spec.gamma
                la *= (lambda_away / g[1]) ** spec.gamma
    if spec.delta:
        factor = _referee_factor(idx, referee, day)
        lh *= factor**spec.delta
        la *= factor**spec.delta
    return StatExpectation(home=lh, away=la, league_matches=n_league)


def nb_prob_over(mean: float, r: float, line: float) -> float:
    """P(X > line) con X binomiale negativa di media `mean` e dispersione `r` (line con mezzo punto)."""
    if mean <= 0:
        return 0.0
    k_max = int(math.floor(line))
    log_p = r * math.log(r / (r + mean))
    log_q = math.log(mean / (r + mean))
    cdf = math.exp(log_p)
    for x in range(1, k_max + 1):
        log_p += math.log((x - 1 + r) / x) + log_q
        cdf += math.exp(log_p)
    return min(1.0, max(0.0, 1.0 - cdf))
