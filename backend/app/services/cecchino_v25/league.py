"""Riferimento di campionato V2.5: frequenze e medie gol dalle sole partite gia' giocate.

Corregge due difetti della V2:
- la frequenza di campionato dell'Under 0.5 primo tempo era sempre 0 (mai conteggiata);
- a inizio stagione il riferimento era vuoto: ora entra la stagione precedente dello
  stesso campionato (con peso limitato) e, se serve, il riferimento globale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.services.cecchino_v25.constants import (
    LEAGUE_MIN_SAMPLE,
    LEAGUE_PREVIOUS_SEASON_WEIGHT,
)

FT_LINES = (0.5, 1.5, 2.5, 3.5)
HT_LINES = (0.5, 1.5)

# Valori di partenza quando non esiste alcuna partita (solo le primissime giornate
# della prima stagione): medie tipiche del calcio europeo.
_DEFAULT = {
    "ft_n": 1.0,
    "ft_home_goals": 1.48,
    "ft_away_goals": 1.16,
    "ft_home_win": 0.44,
    "ft_draw": 0.27,
    "ft_away_win": 0.29,
    "ft_over": {0.5: 0.92, 1.5: 0.75, 2.5: 0.50, 3.5: 0.28},
    "ht_n": 1.0,
    "ht_home_goals": 0.66,
    "ht_away_goals": 0.51,
    "ht_home_win": 0.33,
    "ht_draw": 0.42,
    "ht_away_win": 0.25,
    "ht_over": {0.5: 0.70, 1.5: 0.34},
}


def halftime_score(proxy: Any) -> tuple[int, int] | None:
    raw = getattr(proxy, "raw_json", None) or {}
    ht = ((raw.get("score") or {}).get("halftime")) or {}
    h, a = ht.get("home"), ht.get("away")
    if h is None or a is None:
        return None
    try:
        return int(h), int(a)
    except (TypeError, ValueError):
        return None


@dataclass
class LeagueCounts:
    """Somme pesate: tutte le frequenze sono somme / n."""

    ft_n: float = 0.0
    ft_home_goals: float = 0.0
    ft_away_goals: float = 0.0
    ft_home_win: float = 0.0
    ft_draw: float = 0.0
    ft_away_win: float = 0.0
    ft_over: dict[float, float] = field(default_factory=lambda: {line: 0.0 for line in FT_LINES})
    ht_n: float = 0.0
    ht_home_goals: float = 0.0
    ht_away_goals: float = 0.0
    ht_home_win: float = 0.0
    ht_draw: float = 0.0
    ht_away_win: float = 0.0
    ht_over: dict[float, float] = field(default_factory=lambda: {line: 0.0 for line in HT_LINES})

    def add_match(self, proxy: Any, weight: float = 1.0) -> None:
        gh, ga = getattr(proxy, "goals_home", None), getattr(proxy, "goals_away", None)
        if gh is None or ga is None:
            return
        gh, ga = int(gh), int(ga)
        self.ft_n += weight
        self.ft_home_goals += weight * gh
        self.ft_away_goals += weight * ga
        if gh > ga:
            self.ft_home_win += weight
        elif gh == ga:
            self.ft_draw += weight
        else:
            self.ft_away_win += weight
        for line in FT_LINES:
            if gh + ga > line:
                self.ft_over[line] += weight
        ht = halftime_score(proxy)
        if ht is None:
            return
        hh, ha = ht
        self.ht_n += weight
        self.ht_home_goals += weight * hh
        self.ht_away_goals += weight * ha
        if hh > ha:
            self.ht_home_win += weight
        elif hh == ha:
            self.ht_draw += weight
        else:
            self.ht_away_win += weight
        for line in HT_LINES:
            if hh + ha > line:
                self.ht_over[line] += weight

    def add_counts(self, other: LeagueCounts, weight: float = 1.0, *, ht_weight: float | None = None) -> None:
        hw = weight if ht_weight is None else ht_weight
        for name in ("ft_n", "ft_home_goals", "ft_away_goals", "ft_home_win", "ft_draw", "ft_away_win"):
            setattr(self, name, getattr(self, name) + weight * getattr(other, name))
        for name in ("ht_n", "ht_home_goals", "ht_away_goals", "ht_home_win", "ht_draw", "ht_away_win"):
            setattr(self, name, getattr(self, name) + hw * getattr(other, name))
        for line in FT_LINES:
            self.ft_over[line] += weight * other.ft_over[line]
        for line in HT_LINES:
            self.ht_over[line] += hw * other.ht_over[line]

    def scaled(self, weight: float) -> LeagueCounts:
        out = LeagueCounts()
        out.add_counts(self, weight)
        return out


def counts_from_matches(proxies: Iterable[Any]) -> LeagueCounts:
    out = LeagueCounts()
    for p in proxies:
        out.add_match(p)
    return out


@dataclass(frozen=True)
class LeagueReference:
    """Frequenze di campionato pronte all'uso (mai None, mai 0 per costruzione)."""

    ft_n: float
    ht_n: float
    home_goals: float
    away_goals: float
    ht_home_goals: float
    ht_away_goals: float
    p_home: float
    p_draw: float
    p_away: float
    ht_p_home: float
    ht_p_draw: float
    ht_p_away: float
    ft_over: dict[float, float]
    ht_over: dict[float, float]
    source: str

    @property
    def team_goals(self) -> float:
        return (self.home_goals + self.away_goals) / 2.0

    @property
    def ht_team_goals(self) -> float:
        return (self.ht_home_goals + self.ht_away_goals) / 2.0

    @property
    def total_goals(self) -> float:
        return self.home_goals + self.away_goals

    def over(self, line: float, *, ht: bool) -> float:
        return (self.ht_over if ht else self.ft_over)[line]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ft_n": round(self.ft_n, 1),
            "ht_n": round(self.ht_n, 1),
            "home_goals": round(self.home_goals, 4),
            "away_goals": round(self.away_goals, 4),
            "p_home": round(self.p_home, 4),
            "p_draw": round(self.p_draw, 4),
            "p_away": round(self.p_away, 4),
            "ft_over": {str(k): round(v, 4) for k, v in self.ft_over.items()},
            "ht_over": {str(k): round(v, 4) for k, v in self.ht_over.items()},
            "ht_p_draw": round(self.ht_p_draw, 4),
        }


def _default_counts() -> LeagueCounts:
    out = LeagueCounts(
        ft_n=_DEFAULT["ft_n"],
        ft_home_goals=_DEFAULT["ft_home_goals"],
        ft_away_goals=_DEFAULT["ft_away_goals"],
        ft_home_win=_DEFAULT["ft_home_win"],
        ft_draw=_DEFAULT["ft_draw"],
        ft_away_win=_DEFAULT["ft_away_win"],
        ht_n=_DEFAULT["ht_n"],
        ht_home_goals=_DEFAULT["ht_home_goals"],
        ht_away_goals=_DEFAULT["ht_away_goals"],
        ht_home_win=_DEFAULT["ht_home_win"],
        ht_draw=_DEFAULT["ht_draw"],
        ht_away_win=_DEFAULT["ht_away_win"],
    )
    out.ft_over = dict(_DEFAULT["ft_over"])
    out.ht_over = dict(_DEFAULT["ht_over"])
    return out


def _fill_to(counts: LeagueCounts, base: LeagueCounts, target: float) -> LeagueCounts:
    """Aggiunge `base` (in proporzione) finche' i campioni FT e primo tempo arrivano a `target`."""
    ft_missing = max(0.0, target - counts.ft_n)
    ht_missing = max(0.0, target - counts.ht_n)
    out = LeagueCounts()
    out.add_counts(counts)
    out.add_counts(
        base,
        ft_missing / base.ft_n if base.ft_n > 0 else 0.0,
        ht_weight=ht_missing / base.ht_n if base.ht_n > 0 else 0.0,
    )
    return out


def build_reference(
    *,
    current: LeagueCounts,
    previous: LeagueCounts | None,
    global_pool: LeagueCounts | None,
) -> LeagueReference:
    """Stagione in corso + stagione precedente (peso limitato) + globale se il campione e' corto."""
    combined = LeagueCounts()
    combined.add_counts(current)
    sources = ["stagione"]
    if previous is not None and previous.ft_n > 0:
        weight = min(1.0, LEAGUE_PREVIOUS_SEASON_WEIGHT / previous.ft_n)
        combined.add_counts(previous, weight)
        sources.append("stagione_precedente")
    if combined.ft_n < LEAGUE_MIN_SAMPLE or combined.ht_n < LEAGUE_MIN_SAMPLE:
        base = global_pool if global_pool is not None and global_pool.ft_n >= LEAGUE_MIN_SAMPLE else None
        combined = _fill_to(combined, base or _default_counts().scaled(LEAGUE_MIN_SAMPLE), LEAGUE_MIN_SAMPLE)
        sources.append("globale" if base is not None else "valori_tipici")
    ft_n = max(combined.ft_n, 1e-9)
    ht_n = max(combined.ht_n, 1e-9)
    return LeagueReference(
        ft_n=combined.ft_n,
        ht_n=combined.ht_n,
        home_goals=combined.ft_home_goals / ft_n,
        away_goals=combined.ft_away_goals / ft_n,
        ht_home_goals=combined.ht_home_goals / ht_n,
        ht_away_goals=combined.ht_away_goals / ht_n,
        p_home=combined.ft_home_win / ft_n,
        p_draw=combined.ft_draw / ft_n,
        p_away=combined.ft_away_win / ft_n,
        ht_p_home=combined.ht_home_win / ht_n,
        ht_p_draw=combined.ht_draw / ht_n,
        ht_p_away=combined.ht_away_win / ht_n,
        ft_over={line: combined.ft_over[line] / ft_n for line in FT_LINES},
        ht_over={line: combined.ht_over[line] / ht_n for line in HT_LINES},
        source="+".join(sources),
    )
