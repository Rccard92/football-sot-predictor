"""Orchestratore V3: combina le opinioni degli specialisti in gol attesi.

    log(gol attesi) = a + b_forza*log(Forza) + b_sot*log(Gioco tiri in porta)
                        + b_tiri*log(Gioco tiri)
                        + somma_k c_k * correzione_k     (es. forma, dalla Fase 3)

Stessa formula per casa e ospite (il vantaggio casa e' gia' dentro ogni
specialista). I pesi della stagione S si stimano sulle previsioni della
stagione S-1 (verosimiglianza di Poisson dei gol reali, partite idonee),
trattenuti in modo debole verso "solo Forza, nessuna correzione": se uno
specialista non aggiunge informazione il suo peso resta vicino a zero da solo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.services.cecchino_v3.constants import (
    ORCHESTRATOR_DEFAULT_WEIGHTS,
    ORCHESTRATOR_INPUTS,
    ORCHESTRATOR_PRIOR_PRECISION,
)

_MAX_ITER = 50
_TOL = 1e-9


@dataclass(frozen=True)
class Opinions:
    """Gol attesi casa/ospite secondo ciascuno specialista, piu' eventuali
    correzioni gia' in scala logaritmica (0 = nessun effetto)."""

    home: dict[str, float]
    away: dict[str, float]
    adjust_home: dict[str, float] = field(default_factory=dict)
    adjust_away: dict[str, float] = field(default_factory=dict)


def weight_keys(adjustments: tuple[str, ...] = ()) -> tuple[str, ...]:
    return ("intercept", *ORCHESTRATOR_INPUTS, *adjustments)


def default_weights(adjustments: tuple[str, ...] = ()) -> dict[str, float]:
    weights = dict(ORCHESTRATOR_DEFAULT_WEIGHTS)
    weights.update({k: 0.0 for k in adjustments})
    return weights


def _features(values: dict[str, float], adjust: dict[str, float], adjustments: tuple[str, ...]) -> list[float]:
    return (
        [1.0]
        + [math.log(max(values[k], 1e-6)) for k in ORCHESTRATOR_INPUTS]
        + [float(adjust[k]) for k in adjustments]
    )


def _adjustments_of(weights: dict[str, float]) -> tuple[str, ...]:
    base = set(weight_keys())
    return tuple(k for k in weights if k not in base)


def fit_weights(
    samples: list[tuple[Opinions, int, int]], adjustments: tuple[str, ...] = ()
) -> dict[str, float]:
    """Pesi da (opinioni, gol casa, gol ospite) della stagione precedente."""
    if not samples:
        return default_weights(adjustments)
    keys = weight_keys(adjustments)
    rows: list[list[float]] = []
    goals: list[float] = []
    for opinions, gh, ga in samples:
        rows.append(_features(opinions.home, opinions.adjust_home, adjustments))
        goals.append(float(gh))
        rows.append(_features(opinions.away, opinions.adjust_away, adjustments))
        goals.append(float(ga))
    x = np.array(rows)
    y = np.array(goals)
    defaults = default_weights(adjustments)
    prior = np.array([defaults[k] for k in keys])
    precision = np.full(len(keys), ORCHESTRATOR_PRIOR_PRECISION)

    beta = prior.copy()
    for _ in range(_MAX_ITER):
        lam = np.exp(np.clip(x @ beta, -10.0, 5.0))
        grad = x.T @ (lam - y) + precision * (beta - prior)
        hess = (x * lam[:, None]).T @ x + np.diag(precision)
        step = np.linalg.solve(hess, grad)
        beta -= step
        if np.max(np.abs(step)) < _TOL:
            break
    return {k: float(round(v, 6)) for k, v in zip(keys, beta)}


def combine(opinions: Opinions, weights: dict[str, float]) -> tuple[float, float]:
    adjustments = _adjustments_of(weights)
    coef = np.array([weights[k] for k in weight_keys(adjustments)])
    eta_home = float(np.dot(coef, _features(opinions.home, opinions.adjust_home, adjustments)))
    eta_away = float(np.dot(coef, _features(opinions.away, opinions.adjust_away, adjustments)))
    return math.exp(min(max(eta_home, -10.0), 5.0)), math.exp(min(max(eta_away, -10.0), 5.0))
