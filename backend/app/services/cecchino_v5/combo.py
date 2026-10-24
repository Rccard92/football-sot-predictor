"""Combo sulla stessa partita (docs/combo/COMBO_V1_PREREGISTRAZIONE.md).

Giocate coerenti dello stesso scenario (partita aperta / chiusa / dominio casa / dominio ospite). Probabilita' della combo
da una simulazione con copula gaussiana su gol, tiri in porta e angoli di casa e ospite; legami stimati sullo sviluppo.
Nessuna quota nel calcolo delle probabilita'.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import nbinom, norm, poisson

from app.services.cecchino_v5.constants import STAT_SPECIALIST_BY_KEY, VALID_LINES

COMBO_VERSION = "combo_v1_20261024"
N_SIMS = 2000
MIN_LEG_P = 0.65
MIN_P = 1 / 2.60
MAX_P = 1 / 1.90
VARS = ("gh", "ga", "sh", "sa", "ch", "ca")  # gol, tiri in porta, angoli; casa e ospite
KMAX = {"g": 16, "s": 40, "c": 30}
GOAL_OVER_LINES = (1.5, 2.5, 3.5)
GOAL_UNDER_LINES = (2.5, 3.5)


@dataclass(frozen=True)
class LegType:
    stat: str  # goals | sot | corners | res
    side: str  # total | home | away | 1X | X2
    direction: str  # over | under | res


SCENARIOS: dict[str, tuple[LegType, ...]] = {
    "aperta": (LegType("goals", "total", "over"), LegType("sot", "total", "over"), LegType("corners", "total", "over")),
    "chiusa": (LegType("goals", "total", "under"), LegType("sot", "total", "under"), LegType("corners", "total", "under")),
    "dominio_casa": (LegType("res", "1X", "res"), LegType("sot", "home", "over"), LegType("corners", "home", "over"), LegType("sot", "away", "under")),
    "dominio_ospite": (LegType("res", "X2", "res"), LegType("sot", "away", "over"), LegType("corners", "away", "over"), LegType("sot", "home", "under")),
}
SCENARIO_LABELS = {"aperta": "Partita aperta", "chiusa": "Partita chiusa", "dominio_casa": "Dominio casa", "dominio_ospite": "Dominio ospite"}


@dataclass(frozen=True)
class Leg:
    kind: LegType
    line: float | None

    @property
    def key(self) -> str:
        """Chiave di mercato V4 della giocata."""
        k = self.kind
        if k.stat == "res":
            return "ONE_X" if k.side == "1X" else "X_TWO"
        if k.stat == "goals":
            return f"{k.direction.upper()}_{str(self.line).replace('.', '_')}"
        return f"STAT:{k.stat}:{k.side}:{k.direction}:{self.line:.1f}"

    def label(self, home: str, away: str) -> str:
        k = self.kind
        if k.stat == "res":
            return k.side
        word = "Over" if k.direction == "over" else "Under"
        line = f"{self.line:.1f}".replace(".", ",")
        if k.stat == "goals":
            return f"{word} {line} gol"
        what = "tiri in porta" if k.stat == "sot" else "angoli"
        who = "totali" if k.side == "total" else (home if k.side == "home" else away)
        return f"{word} {line} {what} {who}"


def _values(sims: dict[str, np.ndarray], stat: str, side: str) -> np.ndarray:
    pre = {"goals": "g", "sot": "s", "corners": "c"}[stat]
    if side == "total":
        return sims[pre + "h"] + sims[pre + "a"]
    return sims[pre + ("h" if side == "home" else "a")]


def leg_hits(leg: Leg, sims: dict[str, np.ndarray]) -> np.ndarray:
    k = leg.kind
    if k.stat == "res":
        return sims["gh"] >= sims["ga"] if k.side == "1X" else sims["gh"] <= sims["ga"]
    v = _values(sims, k.stat, k.side)
    return v > leg.line if k.direction == "over" else v < leg.line


def actual_hit(leg: Leg, actual: dict[str, float | None]) -> bool | None:
    one = {name: np.array([actual[name]]) for name in VARS if actual.get(name) is not None}
    needed = {"res": ("gh", "ga"), "goals": ("gh", "ga"), "sot": ("sh", "sa"), "corners": ("ch", "ca")}[leg.kind.stat]
    if any(n not in one for n in needed):
        return None
    return bool(leg_hits(leg, one)[0])


def _lines(kind: LegType) -> tuple[float, ...]:
    if kind.stat == "goals":
        return GOAL_OVER_LINES if kind.direction == "over" else GOAL_UNDER_LINES
    lo, hi = VALID_LINES[(kind.stat, kind.side)]
    return tuple(lo + i for i in range(int(hi - lo) + 1))


def _cdf_tables(means: dict[str, float]) -> dict[str, np.ndarray]:
    r_sot = STAT_SPECIALIST_BY_KEY["tiri_porta"].r_team
    r_cor = STAT_SPECIALIST_BY_KEY["angoli"].r_team
    out = {}
    for name in VARS:
        m = max(1e-6, float(means[name]))
        ks = np.arange(KMAX[name[0]])
        if name[0] == "g":
            cdf = poisson.cdf(ks, m)
        else:
            r = r_sot if name[0] == "s" else r_cor
            cdf = nbinom.cdf(ks, r, r / (r + m))
        cdf[-1] = 1.0
        out[name] = cdf
    return out


def simulate(means: dict[str, float], chol: np.ndarray, seed: int, n: int = N_SIMS) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, len(VARS))) @ chol.T
    u = norm.cdf(z)
    tables = _cdf_tables(means)
    return {name: np.searchsorted(tables[name], u[:, i], side="right") for i, name in enumerate(VARS)}


def pit_z(means: dict[str, float], actual: dict[str, float], rng: np.random.Generator) -> np.ndarray:
    """Residuo di ogni variabile come posizione del valore reale nella distribuzione prevista (scala normale)."""
    tables = _cdf_tables(means)
    out = []
    for name in VARS:
        x = int(actual[name])
        cdf = tables[name]
        hi = cdf[min(x, len(cdf) - 1)]
        lo = cdf[x - 1] if 0 < x <= len(cdf) else (0.0 if x <= 0 else 1.0)
        u = lo + rng.random() * (hi - lo)
        out.append(norm.ppf(min(1 - 1e-6, max(1e-6, u))))
    return np.array(out)


def nearest_psd_corr(c: np.ndarray) -> np.ndarray:
    w, v = np.linalg.eigh((c + c.T) / 2)
    w = np.clip(w, 1e-4, None)
    m = v @ np.diag(w) @ v.T
    d = np.sqrt(np.diag(m))
    return m / np.outer(d, d)


@dataclass
class ComboCandidate:
    scenario: str
    legs: tuple[Leg, ...]
    p: float  # copula
    p_independent: float

    def label(self, home: str, away: str) -> str:
        return " + ".join(leg.label(home, away) for leg in self.legs)


def match_combos(sims: dict[str, np.ndarray], *, allow_goals: bool = True) -> list[ComboCandidate]:
    """Tutte le combo coerenti della partita (2-3 giocate per scenario, linee con probabilita' >= 65%)."""
    hits_cache: dict[str, np.ndarray] = {}
    out: list[ComboCandidate] = []
    for scenario, kinds in SCENARIOS.items():
        legs: list[Leg] = []
        for kind in kinds:
            if kind.stat in ("goals", "res") and not allow_goals:
                continue
            if kind.stat == "res":
                leg = Leg(kind, None)
                h = leg_hits(leg, sims)
                if h.mean() >= MIN_LEG_P:
                    hits_cache[leg.key] = h
                    legs.append(leg)
                continue
            lines = _lines(kind)
            ordered = sorted(lines, reverse=(kind.direction == "over"))  # dalla piu' impegnativa
            for line in ordered:
                leg = Leg(kind, line)
                h = leg_hits(leg, sims)
                if h.mean() >= MIN_LEG_P:
                    hits_cache[leg.key] = h
                    legs.append(leg)
                    break
        for size in (2, 3):
            for combo in itertools.combinations(legs, size):
                hits = np.logical_and.reduce([hits_cache[leg.key] for leg in combo])
                p_ind = math.prod(float(hits_cache[leg.key].mean()) for leg in combo)
                out.append(ComboCandidate(scenario, combo, float(hits.mean()), p_ind))
    return out


def pick(candidates: list[ComboCandidate]) -> ComboCandidate | None:
    """La combo con la probabilita' piu' alta tra quelle con quota equa tra 1,90 e 2,60."""
    inside = [c for c in candidates if MIN_P <= c.p <= MAX_P]
    return max(inside, key=lambda c: c.p) if inside else None


def combo_dict(c: ComboCandidate, home: str, away: str) -> dict[str, Any]:
    return {
        "scenario": c.scenario,
        "scenario_label": SCENARIO_LABELS[c.scenario],
        "label": c.label(home, away),
        "legs": [{"key": leg.key, "label": leg.label(home, away)} for leg in c.legs],
        "probability": round(c.p, 4),
        "probability_independent": round(c.p_independent, 4),
        "fair_quota": round(1 / c.p, 2),
        "min_quota": round(1.05 / c.p, 2),
    }
