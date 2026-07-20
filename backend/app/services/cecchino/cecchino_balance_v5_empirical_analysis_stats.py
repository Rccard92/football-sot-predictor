"""Helper statistici Balance empirico Step 2B — numpy/sklearn, no SciPy nuovo.

Seed bootstrap: SHA-256 (analysis+policy+filtri+pillar+metric+group).
Nessun uso di hash() nativo Python.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Sequence

import numpy as np

from app.services.cecchino.cecchino_draw_credibility_statistics_helpers import (
    WILSON_Z,
    rank_with_ties,
    spearman_rho,
    wilson_ci,
)

PROB_CLAMP_LO = 1e-15
PROB_CLAMP_HI = 1.0 - 1e-15


def deterministic_seed_int(
    *,
    analysis_version: str,
    policy_version: str,
    filters: dict[str, Any],
    pillar: str,
    metric: str,
    group_key: str,
) -> int:
    payload = {
        "analysis_version": analysis_version,
        "policy_version": policy_version,
        "filters": filters,
        "pillar": pillar,
        "metric": metric,
        "group_key": group_key,
    }
    # sort recursively via json-like canonical string
    import json

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % (2**31 - 1)


def rate_pct(successes: int, n: int) -> float | None:
    if n <= 0:
        return None
    return round(100.0 * successes / n, 2)


def proportion_block(successes: int, n: int) -> dict[str, Any]:
    ci = wilson_ci(successes, n, z=WILSON_Z)
    return {
        "successes": successes,
        "n": n,
        "rate": (successes / n) if n else None,
        "rate_pct": rate_pct(successes, n),
        "ci95": {"lower_pct": ci["lower_pct"], "upper_pct": ci["upper_pct"]},
    }


def median(xs: Sequence[float]) -> float | None:
    if not xs:
        return None
    arr = np.asarray(list(xs), dtype=float)
    return float(np.median(arr))


def mean(xs: Sequence[float]) -> float | None:
    if not xs:
        return None
    return float(np.mean(np.asarray(list(xs), dtype=float)))


def bootstrap_ci(
    values: Sequence[float],
    *,
    seed: int,
    iterations: int = 2000,
    confidence: float = 0.95,
    statistic: str = "mean",
) -> dict[str, Any]:
    arr = np.asarray(list(values), dtype=float)
    n = len(arr)
    if n == 0:
        return {"point": None, "lower": None, "upper": None, "n": 0, "iterations": 0}
    rng = np.random.default_rng(seed)
    stats = np.empty(iterations, dtype=float)
    for i in range(iterations):
        sample = arr[rng.integers(0, n, size=n)]
        stats[i] = float(np.median(sample) if statistic == "median" else np.mean(sample))
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(stats, [alpha, 1.0 - alpha])
    point = float(np.median(arr) if statistic == "median" else np.mean(arr))
    return {
        "point": round(point, 4),
        "lower": round(float(lo), 4),
        "upper": round(float(hi), 4),
        "n": n,
        "iterations": iterations,
        "statistic": statistic,
    }


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    """BH FDR adjustment; None preservati."""
    indexed = [(i, p) for i, p in enumerate(p_values) if p is not None and math.isfinite(p)]
    m = len(indexed)
    out: list[float | None] = [None] * len(p_values)
    if m == 0:
        return out
    indexed.sort(key=lambda t: t[1])
    adj = [0.0] * m
    prev = 1.0
    for rank_from_end, (pos, (orig_i, p)) in enumerate(reversed(list(enumerate(indexed)))):
        # rank among sorted ascending: k = pos+1
        k = pos + 1
        val = min(prev, p * m / k)
        adj[pos] = val
        prev = val
    # recompute properly ascending
    adj_asc = [0.0] * m
    prev = 1.0
    for pos in range(m - 1, -1, -1):
        _, p = indexed[pos]
        k = pos + 1
        val = min(prev, p * m / k)
        adj_asc[pos] = val
        prev = val
    for pos, (orig_i, _) in enumerate(indexed):
        out[orig_i] = round(float(adj_asc[pos]), 6)
    return out


def chi_square_independence(
    table: list[list[int]],
) -> dict[str, Any]:
    """Pearson chi-square + Cramér's V su tabella contingenza."""
    a = np.asarray(table, dtype=float)
    if a.size == 0 or a.shape[0] < 2 or a.shape[1] < 2:
        return {
            "chi2": None,
            "dof": None,
            "p_value": None,
            "cramers_v": None,
            "status": "insufficient_data",
        }
    n = a.sum()
    if n <= 0:
        return {
            "chi2": None,
            "dof": None,
            "p_value": None,
            "cramers_v": None,
            "status": "insufficient_data",
        }
    row = a.sum(axis=1, keepdims=True)
    col = a.sum(axis=0, keepdims=True)
    expected = row @ col / n
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2 = float(np.nansum((a - expected) ** 2 / expected))
    dof = int((a.shape[0] - 1) * (a.shape[1] - 1))
    p = _chi2_sf(chi2, dof)
    r, k = a.shape
    v_den = n * max(1, min(r - 1, k - 1))
    cramers_v = math.sqrt(chi2 / v_den) if v_den > 0 else None
    return {
        "chi2": round(chi2, 4),
        "dof": dof,
        "p_value": p,
        "cramers_v": round(cramers_v, 4) if cramers_v is not None else None,
        "n": int(n),
        "status": "ok",
    }


def _chi2_sf(x: float, k: int) -> float | None:
    """Sopravvivenza chi2 approssimata (Wilson–Hilferty); nessun SciPy."""
    if k <= 0 or x < 0 or not math.isfinite(x):
        return None
    # rough: use incomplete gamma via series for small k
    try:
        from math import gamma

        # upper incomplete gamma / gamma(k/2)
        a = k / 2.0
        # regularized gamma Q via continued fraction / series
        return round(_gammaincc(a, x / 2.0), 6)
    except Exception:
        return None


def _gammaincc(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a,x)."""
    if x <= 0:
        return 1.0
    if x < a + 1:
        # Q = 1 - P
        return 1.0 - _gammainc_series(a, x)
    return _gammainc_cf(a, x)


def _gammainc_series(a: float, x: float) -> float:
    term = 1.0 / a
    s = term
    for n in range(1, 200):
        term *= x / (a + n)
        s += term
        if abs(term) < 1e-12 * abs(s):
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gammainc_cf(a: float, x: float) -> float:
    # Lentz continued fraction for Q
    tiny = 1e-30
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 200):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def kruskal_wallis(groups: list[list[float]]) -> dict[str, Any]:
    """Kruskal–Wallis H + epsilon squared."""
    clean = [list(g) for g in groups if g]
    if len(clean) < 2:
        return {"H": None, "p_value": None, "epsilon_squared": None, "status": "insufficient_data"}
    all_vals: list[float] = []
    labels: list[int] = []
    for i, g in enumerate(clean):
        all_vals.extend(g)
        labels.extend([i] * len(g))
    n = len(all_vals)
    if n < 3:
        return {"H": None, "p_value": None, "epsilon_squared": None, "status": "insufficient_data"}
    ranks = rank_with_ties(all_vals)
    rank_sums = [0.0] * len(clean)
    sizes = [0] * len(clean)
    for r, lab in zip(ranks, labels):
        rank_sums[lab] += r
        sizes[lab] += 1
    h = (12.0 / (n * (n + 1))) * sum(
        (rs**2) / sz for rs, sz in zip(rank_sums, sizes) if sz > 0
    ) - 3.0 * (n + 1)
    dof = len(clean) - 1
    p = _chi2_sf(h, dof)
    eps2 = (h - dof) / (n - 1) if n > 1 else None
    return {
        "H": round(h, 4),
        "dof": dof,
        "p_value": p,
        "epsilon_squared": round(eps2, 4) if eps2 is not None else None,
        "n": n,
        "groups": len(clean),
        "status": "ok",
    }


def odds_ratio(a: int, b: int, c: int, d: int) -> dict[str, Any]:
    """OR su tabella 2x2 con Haldane–Anscombe +0.5 se zeri."""
    aa, bb, cc, dd = a, b, c, d
    if 0 in (a, b, c, d):
        aa, bb, cc, dd = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    if bb * cc == 0:
        return {"odds_ratio": None, "log_or": None}
    or_v = (aa * dd) / (bb * cc)
    return {"odds_ratio": round(float(or_v), 4), "log_or": round(math.log(or_v), 4)}


def clamp_prob(p: float) -> float:
    return min(PROB_CLAMP_HI, max(PROB_CLAMP_LO, float(p)))


def brier_score(y_true: Sequence[int], p_pred: Sequence[float]) -> float | None:
    if not y_true or len(y_true) != len(p_pred):
        return None
    err = [(float(y) - clamp_prob(p)) ** 2 for y, p in zip(y_true, p_pred)]
    return round(float(np.mean(err)), 6)


def log_loss(y_true: Sequence[int], p_pred: Sequence[float]) -> float | None:
    if not y_true or len(y_true) != len(p_pred):
        return None
    losses = []
    for y, p in zip(y_true, p_pred):
        pc = clamp_prob(p)
        losses.append(-(y * math.log(pc) + (1 - y) * math.log(1 - pc)))
    return round(float(np.mean(losses)), 6)


def expected_calibration_error(
    y_true: Sequence[int],
    p_pred: Sequence[float],
    *,
    n_bins: int = 10,
) -> dict[str, Any]:
    if not y_true or len(y_true) != len(p_pred) or n_bins < 2:
        return {"ece": None, "bins": [], "status": "insufficient_data"}
    ys = np.asarray(list(y_true), dtype=float)
    ps = np.asarray([clamp_prob(p) for p in p_pred], dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins_out: list[dict[str, Any]] = []
    ece = 0.0
    n = len(ys)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            mask = (ps >= lo) & (ps <= hi)
        else:
            mask = (ps >= lo) & (ps < hi)
        cnt = int(mask.sum())
        if cnt == 0:
            bins_out.append(
                {
                    "bin": i,
                    "lo": float(lo),
                    "hi": float(hi),
                    "count": 0,
                    "predicted_mean": None,
                    "observed_rate": None,
                    "gap": None,
                }
            )
            continue
        pred_m = float(ps[mask].mean())
        obs = float(ys[mask].mean())
        gap = obs - pred_m
        ece += (cnt / n) * abs(gap)
        bins_out.append(
            {
                "bin": i,
                "lo": round(float(lo), 4),
                "hi": round(float(hi), 4),
                "count": cnt,
                "predicted_mean": round(pred_m, 4),
                "observed_rate": round(obs, 4),
                "gap": round(gap, 4),
                "ci95": wilson_ci(int(ys[mask].sum()), cnt),
            }
        )
    return {"ece": round(ece, 6), "bins": bins_out, "status": "ok", "n": n}


def roc_pr_auc(y_true: Sequence[int], scores: Sequence[float]) -> dict[str, Any]:
    if len(y_true) < 2 or len(set(y_true)) < 2:
        return {
            "roc_auc": None,
            "pr_auc": None,
            "label": "diagnostic",
            "status": "insufficient_data",
        }
    try:
        from sklearn.metrics import average_precision_score, roc_auc_score

        roc = float(roc_auc_score(list(y_true), list(scores)))
        pr = float(average_precision_score(list(y_true), list(scores)))
        return {
            "roc_auc": round(roc, 4),
            "pr_auc": round(pr, 4),
            "label": "diagnostic",
            "status": "ok",
        }
    except Exception as exc:
        return {
            "roc_auc": None,
            "pr_auc": None,
            "label": "diagnostic",
            "status": "error",
            "error": type(exc).__name__,
        }


def population_stability_index(
    expected_counts: Sequence[float],
    actual_counts: Sequence[float],
) -> float | None:
    e = np.asarray(list(expected_counts), dtype=float)
    a = np.asarray(list(actual_counts), dtype=float)
    if e.size == 0 or a.size != e.size:
        return None
    e = e + 1e-6
    a = a + 1e-6
    e = e / e.sum()
    a = a / a.sum()
    psi = float(np.sum((a - e) * np.log(a / e)))
    return round(psi, 6)


def jensen_shannon(p: Sequence[float], q: Sequence[float]) -> float | None:
    pp = np.asarray(list(p), dtype=float)
    qq = np.asarray(list(q), dtype=float)
    if pp.size == 0 or qq.size != pp.size:
        return None
    pp = pp + 1e-12
    qq = qq + 1e-12
    pp = pp / pp.sum()
    qq = qq / qq.sum()
    m = 0.5 * (pp + qq)

    def _kl(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.sum(a * np.log(a / b)))

    return round(0.5 * _kl(pp, m) + 0.5 * _kl(qq, m), 6)


def classify_drift(psi: float | None) -> str:
    if psi is None:
        return "insufficient_data"
    if psi < 0.1:
        return "stable"
    if psi < 0.25:
        return "mild_drift"
    return "material_drift"


def spearman_safe(xs: Sequence[float], ys: Sequence[float]) -> dict[str, Any]:
    if len(xs) < 5 or len(xs) != len(ys):
        return {"rho": None, "n": len(xs), "status": "insufficient_data"}
    rho = spearman_rho(list(xs), list(ys))
    return {"rho": round(rho, 4) if rho is not None else None, "n": len(xs), "status": "ok"}
