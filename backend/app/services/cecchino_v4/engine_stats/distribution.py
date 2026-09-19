"""Distribuzioni di conteggio (Poisson / binomiale negativa), probabilita' per linea, CRPS.

Parametrizzazione: media m, dispersione alpha con Var = m + alpha·m². alpha = 0 (o NaN) = Poisson.
Binomiale negativa di scipy: n = 1/alpha, p = 1/(1 + alpha·m).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import nbinom, poisson

_MIN_MEAN = 1e-6
_MIN_ALPHA = 1e-9


def _prep(mean, alpha) -> tuple[np.ndarray, np.ndarray]:
    m = np.maximum(np.asarray(mean, dtype=float), _MIN_MEAN)
    a = np.asarray(alpha, dtype=float)
    a = np.where(np.isnan(a), 0.0, a)
    a = np.broadcast_to(np.maximum(a, 0.0), m.shape)
    return m, a


def cdf(k, mean, alpha) -> np.ndarray:
    """F(k) = P(X ≤ k), per ogni elemento (k, mean, alpha trasmessi insieme)."""
    m, a = _prep(mean, alpha)
    k = np.asarray(k, dtype=float)
    k, m, a = np.broadcast_arrays(k, m, a)
    out = poisson.cdf(k, m)
    nb = a > _MIN_ALPHA
    if np.any(nb):
        n = 1.0 / a[nb]
        p = 1.0 / (1.0 + a[nb] * m[nb])
        out = out.copy()
        out[nb] = nbinom.cdf(k[nb], n, p)
    return out


def prob_over(line, mean, alpha) -> np.ndarray:
    """P(X > linea) con linea a mezzo: 1 − F(⌊linea⌋)."""
    return 1.0 - cdf(np.floor(np.asarray(line, dtype=float)), mean, alpha)


def prob_under(line, mean, alpha) -> np.ndarray:
    return cdf(np.floor(np.asarray(line, dtype=float)), mean, alpha)


def variance(mean, alpha) -> np.ndarray:
    m, a = _prep(mean, alpha)
    return m + a * m * m


def total_dispersion(mean_home, alpha_home, mean_away, alpha_away) -> np.ndarray:
    """Somma di due conteggi indipendenti: aggancio dei momenti (PREREGISTRAZIONE §2.3)."""
    mh, ah = _prep(mean_home, alpha_home)
    ma, aa = _prep(mean_away, alpha_away)
    mt = mh + ma
    var = mh + ah * mh * mh + ma + aa * ma * ma
    alpha_t = (var - mt) / (mt * mt)
    return np.maximum(alpha_t, 0.0)


def crps(y, mean, alpha) -> np.ndarray:
    """CRPS numerico: Σ_k [F(k) − 1(y ≤ k)]² per k = 0 … K, K = max(y, m + 12·sd) + 5."""
    y = np.asarray(y, dtype=float)
    m, a = _prep(mean, alpha)
    y, m, a = np.broadcast_arrays(y, m, a)
    sd = np.sqrt(m + a * m * m)
    kmax = int(math.ceil(float(np.max(np.maximum(y, m + 12.0 * sd))))) + 5
    ks = np.arange(kmax + 1, dtype=float)
    out = np.empty(y.shape[0], dtype=float)
    # a blocchi per non allocare matrici enormi
    step = max(1, 200_000 // (kmax + 1))
    for start in range(0, y.shape[0], step):
        sl = slice(start, start + step)
        f = cdf(ks[None, :], m[sl, None], a[sl, None])
        ind = (y[sl, None] <= ks[None, :]).astype(float)
        out[sl] = np.sum((f - ind) ** 2, axis=1)
    return out


def poisson_loglik(y, mean) -> np.ndarray:
    """log p(y | m) di Poisson (quasi-verosimiglianza per conteggi non interi)."""
    y = np.asarray(y, dtype=float)
    m = np.maximum(np.asarray(mean, dtype=float), _MIN_MEAN)
    from scipy.special import gammaln

    return y * np.log(m) - m - gammaln(y + 1.0)
