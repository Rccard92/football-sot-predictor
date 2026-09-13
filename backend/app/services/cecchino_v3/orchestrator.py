"""Orchestratore V3: combina le opinioni degli specialisti in gol attesi.

    log(gol attesi) = a + b_forza*log(Forza) + b_sot*log(Gioco tiri in porta)
                        + b_tiri*log(Gioco tiri)

Stessa formula per casa e ospite (il vantaggio casa e' gia' dentro ogni
specialista). I pesi della stagione S si stimano sulle previsioni della
stagione S-1 (verosimiglianza di Poisson dei gol reali, partite idonee),
trattenuti verso "solo Forza" in modo debole: se uno specialista non aggiunge
informazione il suo peso resta vicino a zero da solo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.services.cecchino_v3.constants import (
    ORCHESTRATOR_DEFAULT_WEIGHTS,
    ORCHESTRATOR_INPUTS,
    ORCHESTRATOR_PRIOR_PRECISION,
)

_KEYS: tuple[str, ...] = ("intercept", *ORCHESTRATOR_INPUTS)
_MAX_ITER = 50
_TOL = 1e-9


@dataclass(frozen=True)
class Opinions:
    """Gol attesi casa/ospite secondo ciascuno specialista."""

    home: dict[str, float]
    away: dict[str, float]


def default_weights() -> dict[str, float]:
    return dict(ORCHESTRATOR_DEFAULT_WEIGHTS)


def _features(values: dict[str, float]) -> list[float]:
    return [1.0] + [math.log(max(values[k], 1e-6)) for k in ORCHESTRATOR_INPUTS]


def fit_weights(samples: list[tuple[Opinions, int, int]]) -> dict[str, float]:
    """Pesi da (opinioni, gol casa, gol ospite) della stagione precedente."""
    if not samples:
        return default_weights()
    rows: list[list[float]] = []
    goals: list[float] = []
    for opinions, gh, ga in samples:
        rows.append(_features(opinions.home))
        goals.append(float(gh))
        rows.append(_features(opinions.away))
        goals.append(float(ga))
    x = np.array(rows)
    y = np.array(goals)
    prior = np.array([ORCHESTRATOR_DEFAULT_WEIGHTS[k] for k in _KEYS])
    precision = np.full(len(_KEYS), ORCHESTRATOR_PRIOR_PRECISION)

    beta = prior.copy()
    for _ in range(_MAX_ITER):
        lam = np.exp(np.clip(x @ beta, -10.0, 5.0))
        grad = x.T @ (lam - y) + precision * (beta - prior)
        hess = (x * lam[:, None]).T @ x + np.diag(precision)
        step = np.linalg.solve(hess, grad)
        beta -= step
        if np.max(np.abs(step)) < _TOL:
            break
    return {k: float(round(v, 6)) for k, v in zip(_KEYS, beta)}


def combine(opinions: Opinions, weights: dict[str, float]) -> tuple[float, float]:
    coef = np.array([weights[k] for k in _KEYS])
    home = math.exp(min(max(float(np.dot(coef, _features(opinions.home))), -10.0), 5.0))
    away = math.exp(min(max(float(np.dot(coef, _features(opinions.away))), -10.0), 5.0))
    return home, away
