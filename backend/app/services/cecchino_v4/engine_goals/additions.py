"""Le novita' del motore gol V4 (docs/v4/PREREGISTRAZIONE_FASE_1.md, sezione 3):
a. vantaggio casa per squadra, c. dispersione binomiale negativa per divisione,
d. incertezza, e. calibrazione isotonica per mercato. Funzioni pure.
(La b, rho per divisione, vive in `strength_params.fit_day`.)
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.isotonic import IsotonicRegression

from app.services.cecchino_v3.data import MatchRecord

from app.services.cecchino_v4.constants import CALIBRATION_MIN_ROWS, DISPERSION_MIN_ROWS, EVIDENCE_FULL_KNOWLEDGE
from app.services.cecchino_v4.engine_goals.config import (
    DISAGREEMENT_FULL,
    DISPERSION_POISSON_BELOW,
    HOME_ADV_DECAY_XI,
    HOME_ADV_MAX_LOG,
    HOME_ADV_PRIOR_MATCHES,
    LEVEL_HIGH,
    LEVEL_LOW,
    LEVEL_MEDIUM,
    UNCERTAINTY_QUANTILES,
    UNCERTAINTY_WARMUP_CUTS,
    UNCERTAINTY_WEIGHTS,
)

# --- a. vantaggio casa per squadra --------------------------------------------------------------


@dataclass
class HomeAdvState:
    """Somme pesate nel tempo dei residui di differenza reti di una squadra."""

    sum_home: float = 0.0
    n_home: float = 0.0
    sum_away: float = 0.0
    n_away: float = 0.0
    last_day: int | None = None

    def decayed(self, day: int) -> "HomeAdvState":
        if self.last_day is None or day <= self.last_day:
            return self
        f = math.exp(-HOME_ADV_DECAY_XI * (day - self.last_day))
        return HomeAdvState(self.sum_home * f, self.n_home * f, self.sum_away * f, self.n_away * f, day)

    def deviation(self, day: int) -> float:
        """hdev in gol di differenza reti, trattenuto verso zero (K/2 per lato)."""
        s = self.decayed(day)
        half = HOME_ADV_PRIOR_MATCHES / 2.0
        return 0.5 * (s.sum_home / (s.n_home + half) - s.sum_away / (s.n_away + half))

    def add(self, day: int, residual: float, *, at_home: bool) -> None:
        s = self.decayed(day)
        self.sum_home, self.n_home, self.sum_away, self.n_away = s.sum_home, s.n_home, s.sum_away, s.n_away
        if at_home:
            self.sum_home += residual
            self.n_home += 1.0
        else:
            self.sum_away += residual
            self.n_away += 1.0
        self.last_day = day


@dataclass(frozen=True)
class HomeAdvantage:
    kappa: float  # correzione in scala logaritmica (+casa, -ospite)
    hdev_home: float  # deviazione della squadra di casa (gol di differenza reti)
    hdev_away: float


def home_advantage_kappa(hdev_home: float, hdev_away: float, lam_home: float, lam_away: float) -> float:
    total = max(lam_home + lam_away, 1e-6)
    kappa = (hdev_home + hdev_away) / 2.0 / total
    return min(max(kappa, -HOME_ADV_MAX_LOG), HOME_ADV_MAX_LOG)


def team_home_advantage(
    matches: Sequence[MatchRecord],
    expected: dict[int, tuple[float, float]],
    *,
    states: dict[tuple[str, str], HomeAdvState] | None = None,
) -> dict[int, HomeAdvantage]:
    """Walk-forward: per ogni partita la correzione dai residui delle partite dei
    giorni precedenti (`expected` = gol attesi V3 casa/ospite di ogni partita).
    Le partite dello stesso giorno non si vedono tra loro. `states` puo' essere
    passato per continuare da uno stato gia' accumulato (live)."""
    if states is None:
        states = {}
    out: dict[int, HomeAdvantage] = {}

    def state(m: MatchRecord, team: str) -> HomeAdvState:
        key = (m.group, team)
        if key not in states:
            states[key] = HomeAdvState()
        return states[key]

    n = len(matches)
    i = 0
    while i < n:
        j = i
        while j < n and matches[j].day == matches[i].day:
            j += 1
        day = matches[i:j]
        for m in day:
            exp = expected.get(m.lab_match_id)
            if exp is None:
                continue
            hh = state(m, m.home_team).deviation(m.day)
            ha = state(m, m.away_team).deviation(m.day)
            out[m.lab_match_id] = HomeAdvantage(kappa=home_advantage_kappa(hh, ha, exp[0], exp[1]), hdev_home=hh, hdev_away=ha)
        for m in day:
            exp = expected.get(m.lab_match_id)
            if exp is None:
                continue
            resid_home = (m.ft_home - m.ft_away) - (exp[0] - exp[1])
            state(m, m.home_team).add(m.day, resid_home, at_home=True)
            state(m, m.away_team).add(m.day, -resid_home, at_home=False)
        i = j
    return out


def apply_home_advantage(lam_home: float, lam_away: float, kappa: float) -> tuple[float, float]:
    return lam_home * math.exp(kappa), lam_away * math.exp(-kappa)


# --- c. dispersione binomiale negativa --------------------------------------------------------


def dispersion_alpha(lam: np.ndarray, y: np.ndarray) -> float | None:
    """Metodo dei momenti: alpha = sum[(y-lam)^2 - lam] / sum lam^2; Poisson se
    poche righe o alpha sotto la soglia."""
    if lam.size < DISPERSION_MIN_ROWS:
        return None
    denom = float(np.sum(lam * lam))
    if denom <= 0:
        return None
    alpha = float(np.sum((y - lam) ** 2 - lam)) / denom
    return alpha if alpha > DISPERSION_POISSON_BELOW else None


def fit_dispersion(
    rows: Iterable[tuple[str, float, float, int, int]],
) -> dict[str, tuple[float | None, float | None]]:
    """{divisione: (alpha casa, alpha ospite)} dalle righe (divisione, lam_h, lam_a, y_h, y_a)."""
    acc: dict[str, list[list[float]]] = {}
    for div, lh, la, yh, ya in rows:
        a = acc.setdefault(div, [[], [], [], []])
        a[0].append(lh)
        a[1].append(float(yh))
        a[2].append(la)
        a[3].append(float(ya))
    out: dict[str, tuple[float | None, float | None]] = {}
    for div, (lh, yh, la, ya) in acc.items():
        out[div] = (dispersion_alpha(np.array(lh), np.array(yh)), dispersion_alpha(np.array(la), np.array(ya)))
    return out


# --- d. incertezza -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Uncertainty:
    score: float
    knowledge: float
    disagreement: float
    new_team_home: bool
    new_team_away: bool


def specialist_disagreement(opinions: dict[str, tuple[float, float]]) -> float:
    """max |log(lambda_i / lambda_j)| tra gli specialisti, su entrambi i lati."""
    worst = 0.0
    names = list(opinions)
    for side in (0, 1):
        vals = [math.log(max(opinions[n][side], 1e-6)) for n in names]
        if vals:
            worst = max(worst, max(vals) - min(vals))
    return worst


def uncertainty_score(home_evidence: float, away_evidence: float, opinions: dict[str, tuple[float, float]]) -> Uncertainty:
    knowledge = 1.0 - min(1.0, min(home_evidence, away_evidence) / EVIDENCE_FULL_KNOWLEDGE)
    dis = specialist_disagreement(opinions)
    dnorm = min(1.0, dis / DISAGREEMENT_FULL)
    new_home = home_evidence <= 0.0
    new_away = away_evidence <= 0.0
    nt = 1.0 if (new_home or new_away) else 0.0
    w = UNCERTAINTY_WEIGHTS
    score = w["knowledge"] * knowledge + w["disagreement"] * dnorm + w["new_team"] * nt
    return Uncertainty(
        score=min(max(score, 0.0), 1.0),
        knowledge=knowledge,
        disagreement=dis,
        new_team_home=new_home,
        new_team_away=new_away,
    )


def uncertainty_cuts(previous_scores: Sequence[float] | None) -> tuple[float, float]:
    """Tagli (bassa|media, media|alta): percentili 30/70 della stagione precedente;
    fissi nel rodaggio o senza stagione precedente."""
    if not previous_scores:
        return UNCERTAINTY_WARMUP_CUTS
    lo, hi = np.quantile(np.asarray(previous_scores, dtype=float), UNCERTAINTY_QUANTILES)
    return float(lo), float(hi)


def uncertainty_level(score: float, cuts: tuple[float, float], *, new_team: bool = False) -> str:
    if new_team:
        return LEVEL_HIGH
    if score < cuts[0]:
        return LEVEL_LOW
    if score < cuts[1]:
        return LEVEL_MEDIUM
    return LEVEL_HIGH


# --- e. calibrazione isotonica per mercato --------------------------------------------------------

CALIBRATED_MARKETS: tuple[str, ...] = (
    "HOME",
    "DRAW",
    "AWAY",
    "OVER_0_5",
    "OVER_1_5",
    "OVER_2_5",
    "OVER_3_5",
    "HOME_PT",
    "DRAW_PT",
    "AWAY_PT",
)


def fit_isotonic(p: Sequence[float], y: Sequence[float]) -> IsotonicRegression | None:
    """Identita' (None) sotto CALIBRATION_MIN_ROWS righe."""
    if len(p) < CALIBRATION_MIN_ROWS:
        return None
    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0, increasing=True)
    model.fit(np.asarray(p, dtype=float), np.asarray(y, dtype=float))
    return model


def fit_calibration(rows: Iterable[tuple[dict[str, float], dict[str, bool | None]]]) -> dict[str, IsotonicRegression | None]:
    """Un modello per mercato dalle righe (probabilita' non calibrate, esiti)."""
    p: dict[str, list[float]] = {k: [] for k in CALIBRATED_MARKETS}
    y: dict[str, list[float]] = {k: [] for k in CALIBRATED_MARKETS}
    for probs, outcomes in rows:
        for k in CALIBRATED_MARKETS:
            won = outcomes.get(k)
            if won is None or k not in probs:
                continue
            p[k].append(probs[k])
            y[k].append(1.0 if won else 0.0)
    return {k: fit_isotonic(p[k], y[k]) for k in CALIBRATED_MARKETS}


def _cal_column(models: dict[str, IsotonicRegression | None], key: str, values: np.ndarray) -> np.ndarray:
    model = models.get(key)
    if model is None or values.size == 0:
        return values
    return np.clip(model.predict(values), 0.0, 1.0)


def _normalize_columns(cols: list[np.ndarray]) -> list[np.ndarray]:
    total = sum(cols)
    safe = np.where(total > 1e-12, total, 1.0)
    return [np.where(total > 1e-12, c / safe, 1.0 / len(cols)) for c in cols]


def apply_calibration_many(
    rows: Sequence[dict[str, float]], models: dict[str, IsotonicRegression | None]
) -> list[dict[str, float]]:
    """Calibra i mercati di CALIBRATED_MARKETS (in blocco) e ricostruisce gli
    altri in modo coerente: 1X2 e 1X2 primo tempo rinormalizzati, doppia chance
    dalle somme, under = 1 - over. I mercati handicap restano come sono."""
    if not rows:
        return []
    col = {k: np.array([r[k] for r in rows], dtype=float) for k in CALIBRATED_MARKETS if k in rows[0]}
    cal = {k: _cal_column(models, k, v) for k, v in col.items()}
    h, d, a = _normalize_columns([cal["HOME"], cal["DRAW"], cal["AWAY"]])
    has_ht = "HOME_PT" in cal
    if has_ht:
        hp, dp, ap = _normalize_columns([cal["HOME_PT"], cal["DRAW_PT"], cal["AWAY_PT"]])
    out: list[dict[str, float]] = []
    for i, r in enumerate(rows):
        o = dict(r)
        o.update(
            {
                "HOME": float(h[i]),
                "DRAW": float(d[i]),
                "AWAY": float(a[i]),
                "ONE_X": float(h[i] + d[i]),
                "X_TWO": float(d[i] + a[i]),
                "ONE_TWO": float(h[i] + a[i]),
            }
        )
        for suffix in ("0_5", "1_5", "2_5", "3_5"):
            over = float(cal[f"OVER_{suffix}"][i])
            o[f"OVER_{suffix}"] = over
            o[f"UNDER_{suffix}"] = 1.0 - over
        if has_ht:
            o.update({"HOME_PT": float(hp[i]), "DRAW_PT": float(dp[i]), "AWAY_PT": float(ap[i])})
        out.append(o)
    return out


def apply_calibration(probs: dict[str, float], models: dict[str, IsotonicRegression | None]) -> dict[str, float]:
    return apply_calibration_many([probs], models)[0]


def apply_calibration_bounds_many(
    lo: Sequence[dict[str, float]], hi: Sequence[dict[str, float]], models: dict[str, IsotonicRegression | None]
) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    """Gli estremi passano per la stessa mappa (monotona: l'ordine si conserva)."""
    clo, chi = apply_calibration_many(lo, models), apply_calibration_many(hi, models)
    return (
        [{k: min(a[k], b[k]) for k in a} for a, b in zip(clo, chi)],
        [{k: max(a[k], b[k]) for k in a} for a, b in zip(clo, chi)],
    )


__all__ = [
    "CALIBRATED_MARKETS",
    "HomeAdvState",
    "HomeAdvantage",
    "Uncertainty",
    "apply_calibration",
    "apply_calibration_bounds_many",
    "apply_calibration_many",
    "apply_home_advantage",
    "dispersion_alpha",
    "fit_calibration",
    "fit_dispersion",
    "fit_isotonic",
    "home_advantage_kappa",
    "specialist_disagreement",
    "team_home_advantage",
    "uncertainty_cuts",
    "uncertainty_level",
    "uncertainty_score",
]
