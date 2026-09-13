"""Calibrazione finale dei gol attesi (dalla Fase 7).

Le previsioni con rumore portano l'orchestratore a "schiacciare" la differenza
di forza tra le squadre (le favorite risultano sottostimate). La correzione
agisce sui gol attesi, prima di calcolare i mercati, cosi' i 17 mercati restano
coerenti tra loro:

    s = log(casa) - log(ospite)           differenza di forza
    m = (log(casa) + log(ospite)) / 2     livello dei gol
    s' = alpha * s + beta                 alpha > 1 allarga le differenze
    m' = m + gamma
    casa' = exp(m' + s'/2),  ospite' = exp(m' - s'/2)

Variante a gol totali invariati (Fase 7b, preserve_total=True): la differenza
di forza si calibra come sopra, ma i gol totali della partita restano quelli
dell'orchestratore, riscalati solo da un fattore globale:

    T = casa + ospite
    casa' = T * exp(gamma) * sigmoide(s'),  ospite' = T * exp(gamma) * sigmoide(-s')

cosi' allargare le differenze non aumenta i gol totali nelle partite sbilanciate.

I tre numeri della stagione S si stimano sui risultati esatti della stagione
S-1 (verosimiglianza Dixon-Coles), usando le previsioni NON calibrate che quella
stagione aveva davvero: sono fuori campione. Nel rodaggio nessuna calibrazione.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from app.services.cecchino_v3.constants import CALIBRATION_ALPHA_BOUNDS, CALIBRATION_SHIFT_BOUNDS


@dataclass(frozen=True)
class Calibration:
    alpha: float = 1.0
    beta: float = 0.0
    gamma: float = 0.0
    preserve_total: bool = False

    def as_dict(self) -> dict[str, float | bool]:
        return {
            "alpha": round(self.alpha, 6),
            "beta": round(self.beta, 6),
            "gamma": round(self.gamma, 6),
            "preserve_total": self.preserve_total,
        }


IDENTITY = Calibration()


@dataclass(frozen=True)
class CalibrationSample:
    lambda_home: float
    lambda_away: float
    rho: float
    goals_home: int
    goals_away: int


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def apply_calibration(lambda_home: float, lambda_away: float, cal: Calibration) -> tuple[float, float]:
    lam_h = max(lambda_home, 1e-9)
    lam_a = max(lambda_away, 1e-9)
    log_h = math.log(lam_h)
    log_a = math.log(lam_a)
    s = cal.alpha * (log_h - log_a) + cal.beta
    if cal.preserve_total:
        total = (lam_h + lam_a) * math.exp(cal.gamma)
        share = _sigmoid(s)
        return total * share, total * (1.0 - share)
    m = (log_h + log_a) / 2.0 + cal.gamma
    return math.exp(m + s / 2.0), math.exp(m - s / 2.0)


def _calibrated_arrays(
    params: np.ndarray, data: dict[str, np.ndarray], preserve_total: bool
) -> tuple[np.ndarray, np.ndarray]:
    alpha, beta, gamma = (float(v) for v in params)
    s = alpha * data["s"] + beta
    if preserve_total:
        total = data["total"] * math.exp(gamma)
        share = 1.0 / (1.0 + np.exp(-s))
        return total * share, total * (1.0 - share)
    m = data["m"] + gamma
    return np.exp(m + s / 2.0), np.exp(m - s / 2.0)


def _negative_log_likelihood(params: np.ndarray, data: dict[str, np.ndarray], preserve_total: bool) -> float:
    lam_h, lam_a = _calibrated_arrays(params, data, preserve_total)
    lam_h = np.maximum(lam_h, 1e-9)
    lam_a = np.maximum(lam_a, 1e-9)
    gh, ga, rho = data["gh"], data["ga"], data["rho"]

    tau = np.ones_like(lam_h)
    m00 = (gh == 0) & (ga == 0)
    m01 = (gh == 0) & (ga == 1)
    m10 = (gh == 1) & (ga == 0)
    m11 = (gh == 1) & (ga == 1)
    tau[m00] = 1.0 - lam_h[m00] * lam_a[m00] * rho[m00]
    tau[m01] = 1.0 + lam_h[m01] * rho[m01]
    tau[m10] = 1.0 + lam_a[m10] * rho[m10]
    tau[m11] = 1.0 - rho[m11]
    tau = np.maximum(tau, 1e-9)

    log_lik = (
        np.log(tau)
        + gh * np.log(lam_h)
        - lam_h
        - data["lg_h"]
        + ga * np.log(lam_a)
        - lam_a
        - data["lg_a"]
    )
    return float(-np.mean(log_lik))


def fit_calibration(samples: list[CalibrationSample], *, preserve_total: bool = False) -> Calibration:
    """Massima verosimiglianza dei risultati esatti entro i limiti ammessi."""
    identity = Calibration(preserve_total=preserve_total)
    if not samples:
        return identity
    lam_h = np.array([max(x.lambda_home, 1e-9) for x in samples])
    lam_a = np.array([max(x.lambda_away, 1e-9) for x in samples])
    gh = np.array([x.goals_home for x in samples], dtype=float)
    ga = np.array([x.goals_away for x in samples], dtype=float)
    data = {
        "s": np.log(lam_h) - np.log(lam_a),
        "m": (np.log(lam_h) + np.log(lam_a)) / 2.0,
        "total": lam_h + lam_a,
        "gh": gh,
        "ga": ga,
        "rho": np.array([x.rho for x in samples]),
        "lg_h": gammaln(gh + 1.0),
        "lg_a": gammaln(ga + 1.0),
    }
    result = minimize(
        _negative_log_likelihood,
        x0=np.array([1.0, 0.0, 0.0]),
        args=(data, preserve_total),
        method="L-BFGS-B",
        bounds=[CALIBRATION_ALPHA_BOUNDS, CALIBRATION_SHIFT_BOUNDS, CALIBRATION_SHIFT_BOUNDS],
        options={"maxiter": 500, "ftol": 1e-12, "gtol": 1e-9},
    )
    alpha, beta, gamma = (float(v) for v in result.x)
    # se l'ottimizzazione non migliora il punto di partenza si resta all'identita'
    if not result.success and _negative_log_likelihood(result.x, data, preserve_total) > _negative_log_likelihood(
        np.array([1.0, 0.0, 0.0]), data, preserve_total
    ):
        return identity
    return Calibration(alpha=alpha, beta=beta, gamma=gamma, preserve_total=preserve_total)
