"""Helper statistici Intensità Goal v5 — Fase 1C (numpy + stdlib; sklearn solo nel service xG)."""

from __future__ import annotations

import math
import statistics
from typing import Any

import numpy as np

from app.services.cecchino.cecchino_draw_credibility_statistics_helpers import (
    apply_quantile_boundaries,
    auc_mann_whitney,
    bootstrap_auc,
    build_quantile_boundaries,
    pearson_r,
    rank_with_ties,
    spearman_rho,
)

PSI_STABLE = 0.10
PSI_MODERATE = 0.25
LOW_VARIANCE_EPS = 1e-12
CV_LOW_MEAN_EPS = 0.05


def safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def mad(values: list[float]) -> float | None:
    if not values:
        return None
    med = statistics.median(values)
    return float(statistics.median([abs(v - med) for v in values]))


def descriptive_feature_stats(values: list[float]) -> dict[str, Any]:
    n = len(values)
    if n == 0:
        return {
            "rows_available": 0,
            "missing": None,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "mad": None,
            "p5": None,
            "p10": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "skewness": None,
            "kurtosis": None,
            "zero_rate": None,
            "outlier_rate_iqr": None,
            "n_unique": 0,
            "low_variance": True,
        }
    arr = sorted(values)
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values) if n > 1 else 0.0
    med = statistics.median(values)

    def _pct(p: float) -> float:
        if n == 1:
            return arr[0]
        idx = (n - 1) * p / 100.0
        lo = int(math.floor(idx))
        hi = min(n - 1, int(math.ceil(idx)))
        if lo == hi:
            return arr[lo]
        w = idx - lo
        return arr[lo] * (1 - w) + arr[hi] * w

    p25, p75 = _pct(25), _pct(75)
    iqr = p75 - p25
    lo_fence, hi_fence = p25 - 1.5 * iqr, p75 + 1.5 * iqr
    outliers = sum(1 for v in values if v < lo_fence or v > hi_fence)
    zeros = sum(1 for v in values if abs(v) <= 1e-15)

    skew = None
    kurt = None
    if n >= 3 and stdev > 0:
        m3 = sum((v - mean) ** 3 for v in values) / n
        m4 = sum((v - mean) ** 4 for v in values) / n
        skew = m3 / (stdev**3)
        kurt = m4 / (stdev**4) - 3.0

    n_unique = len(set(round(v, 10) for v in values))
    return {
        "rows_available": n,
        "min": round(arr[0], 6),
        "max": round(arr[-1], 6),
        "mean": round(mean, 6),
        "median": round(med, 6),
        "standard_deviation": round(stdev, 6),
        "mad": round(mad(values) or 0.0, 6),
        "p5": round(_pct(5), 6),
        "p10": round(_pct(10), 6),
        "p25": round(p25, 6),
        "p50": round(_pct(50), 6),
        "p75": round(p75, 6),
        "p90": round(_pct(90), 6),
        "p95": round(_pct(95), 6),
        "skewness": round(skew, 6) if skew is not None else None,
        "kurtosis": round(kurt, 6) if kurt is not None else None,
        "zero_rate": round(zeros / n, 6),
        "outlier_rate_iqr": round(outliers / n, 6),
        "n_unique": n_unique,
        "low_variance": bool(stdev <= LOW_VARIANCE_EPS or n_unique <= 1),
    }


def point_biserial(binary: list[int], continuous: list[float]) -> float | None:
    if len(binary) != len(continuous) or len(binary) < 2:
        return None
    return pearson_r([float(b) for b in binary], continuous)


def standardized_mean_difference(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    mp, mn = statistics.mean(pos), statistics.mean(neg)
    sp = statistics.pstdev(pos) if len(pos) > 1 else 0.0
    sn = statistics.pstdev(neg) if len(neg) > 1 else 0.0
    pooled = math.sqrt((sp**2 + sn**2) / 2.0)
    if pooled <= LOW_VARIANCE_EPS:
        return None
    return (mp - mn) / pooled


def mann_whitney_u(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    combined = pos + neg
    ranks = rank_with_ties(combined)
    n1 = len(pos)
    rank_sum = sum(ranks[:n1])
    return rank_sum - n1 * (n1 + 1) / 2.0


def _average_rank_rows(matrix: np.ndarray) -> np.ndarray:
    """Ranghi medi per riga (gestione tie), shape (B, n)."""
    order = np.argsort(matrix, axis=1, kind="mergesort")
    ranks = np.empty_like(matrix, dtype=float)
    b_count, n = matrix.shape
    for i in range(b_count):
        sorted_vals = matrix[i, order[i]]
        row_ranks = np.empty(n, dtype=float)
        j = 0
        while j < n:
            k = j
            while k + 1 < n and sorted_vals[k + 1] == sorted_vals[j]:
                k += 1
            avg = 0.5 * (j + k) + 1.0
            row_ranks[j : k + 1] = avg
            j = k + 1
        ranks[i, order[i]] = row_ranks
    return ranks


def _spearman_from_arrays(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 3:
        return None
    rx = _average_rank_rows(x.reshape(1, -1))[0]
    ry = _average_rank_rows(y.reshape(1, -1))[0]
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    den = math.sqrt(float(np.dot(rx, rx) * np.dot(ry, ry)))
    if den <= 1e-15:
        return None
    return float(np.dot(rx, ry) / den)


def bootstrap_spearman_ci(
    xs: list[float],
    ys: list[float],
    *,
    iterations: int,
    seed: int = 42,
    indices: np.ndarray | None = None,
) -> dict[str, Any]:
    x_arr, y_arr = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    original = _spearman_from_arrays(x_arr, y_arr)
    empty = {
        "spearman": round(original, 6) if original is not None else None,
        "ci_lower": None,
        "ci_upper": None,
        "valid_bootstrap_iterations": 0,
    }
    if original is None or len(xs) < 3:
        return empty
    index_matrix = indices if indices is not None else bootstrap_index_matrix(len(xs), iterations, seed)
    sampled_x = x_arr[index_matrix]
    sampled_y = y_arr[index_matrix]
    rx = _average_rank_rows(sampled_x)
    ry = _average_rank_rows(sampled_y)
    rx = rx - rx.mean(axis=1, keepdims=True)
    ry = ry - ry.mean(axis=1, keepdims=True)
    num = np.sum(rx * ry, axis=1)
    den = np.sqrt(np.sum(rx * rx, axis=1) * np.sum(ry * ry, axis=1))
    valid = den > 1e-15
    samples = (num[valid] / den[valid]).tolist()
    if len(samples) < 10:
        empty["valid_bootstrap_iterations"] = len(samples)
        return empty
    samples.sort()
    lo = samples[int(0.025 * len(samples))]
    hi = samples[min(len(samples) - 1, int(0.975 * len(samples)))]
    return {
        "spearman": round(original, 6),
        "ci_lower": round(lo, 6),
        "ci_upper": round(hi, 6),
        "valid_bootstrap_iterations": len(samples),
    }


def bootstrap_paired_delta_ci(
    deltas: list[float],
    *,
    iterations: int,
    seed: int = 42,
    indices: np.ndarray | None = None,
) -> dict[str, Any]:
    if not deltas:
        return {"mean": None, "ci_lower": None, "ci_upper": None, "valid_bootstrap_iterations": 0}
    values = np.asarray(deltas, dtype=float)
    index_matrix = indices if indices is not None else bootstrap_index_matrix(len(values), iterations, seed)
    means = np.mean(values[index_matrix], axis=1)
    return {
        "mean": round(float(np.mean(values)), 6),
        "ci_lower": round(float(np.quantile(means, 0.025)), 6),
        "ci_upper": round(float(np.quantile(means, 0.975)), 6),
        "valid_bootstrap_iterations": len(means),
    }


def bootstrap_index_matrix(n: int, iterations: int = 1000, seed: int = 42) -> np.ndarray:
    """Matrice condivisibile di indici bootstrap, deterministica per dimensione."""
    if n <= 0 or iterations <= 0:
        return np.empty((0, 0), dtype=np.intp)
    return np.random.default_rng(seed).integers(0, n, size=(iterations, n), dtype=np.intp)


def bootstrap_auc_ci(
    binary: np.ndarray, values: np.ndarray, indices: np.ndarray
) -> dict[str, Any]:
    """AUC e IC bootstrap riutilizzando la matrice di indici condivisa."""
    original = auc_mann_whitney(binary.tolist(), values.tolist())
    if original is None or len(binary) < 3:
        return {"auc": None, "ci_lower": None, "ci_upper": None, "valid_bootstrap_iterations": 0}
    sampled_y = binary[indices].astype(float)
    sampled_x = values[indices]
    positive = sampled_y.sum(axis=1)
    negative = sampled_y.shape[1] - positive
    valid = (positive > 0) & (negative > 0)
    ranks = _average_rank_rows(sampled_x)
    rank_sum_pos = np.sum(ranks * sampled_y, axis=1)
    u = rank_sum_pos - positive * (positive + 1.0) / 2.0
    denom = positive * negative
    auc_rows = np.full(len(positive), np.nan, dtype=float)
    ok = valid & (denom > 0)
    auc_rows[ok] = u[ok] / denom[ok]
    samples = [float(v) for v in auc_rows[ok] if np.isfinite(v)]
    return {
        "auc": round(float(original), 6),
        "ci_lower": round(float(np.quantile(samples, 0.025)), 6) if len(samples) >= 10 else None,
        "ci_upper": round(float(np.quantile(samples, 0.975)), 6) if len(samples) >= 10 else None,
        "valid_bootstrap_iterations": len(samples),
    }


def monotonicity_from_quintile_means(means: list[float | None]) -> dict[str, Any]:
    vals = [m for m in means if m is not None]
    if len(vals) < 2:
        return {
            "monotonic_direction": "flat",
            "monotonicity_score": 0.0,
            "n_inversions": 0,
            "high_minus_low": None,
        }
    diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    ups = sum(1 for d in diffs if d > 1e-9)
    downs = sum(1 for d in diffs if d < -1e-9)
    high_low = vals[-1] - vals[0]
    if ups == len(diffs):
        direction, score, inv = "increasing", 1.0, 0
    elif downs == len(diffs):
        direction, score, inv = "decreasing", 1.0, 0
    elif ups == 0 and downs == 0:
        direction, score, inv = "flat", 0.0, 0
    else:
        direction = "non_monotonic"
        if abs(high_low) <= 1e-12:
            score, inv = 0.0, len(diffs)
        else:
            agree = ups if high_low > 0 else downs
            score = round(agree / len(diffs), 4)
            inv = len(diffs) - agree
    return {
        "monotonic_direction": direction,
        "monotonicity_score": round(float(score), 4),
        "n_inversions": int(inv),
        "high_minus_low": round(high_low, 6),
    }


def correlation_matrix(
    feature_vectors: dict[str, list[float | None]], method: str = "pearson"
) -> dict[str, Any]:
    keys = list(feature_vectors.keys())
    matrix: dict[str, dict[str, float | None]] = {k: {} for k in keys}
    for i, a in enumerate(keys):
        for j, b in enumerate(keys):
            if j < i:
                matrix[a][b] = matrix[b][a]
                continue
            xa, xb = feature_vectors[a], feature_vectors[b]
            pairs = [
                (xf, yf)
                for x, y in zip(xa, xb)
                if (xf := safe_float(x)) is not None and (yf := safe_float(y)) is not None
            ]
            if len(pairs) < 3:
                r = None
            else:
                xs = [p[0] for p in pairs]
                ys = [p[1] for p in pairs]
                r = pearson_r(xs, ys) if method == "pearson" else spearman_rho(xs, ys)
            matrix[a][b] = round(r, 6) if r is not None else None
    return {"features": keys, "matrix": matrix}


def cluster_by_abs_rho(matrix: dict[str, dict[str, float | None]], threshold: float) -> list[list[str]]:
    keys = list(matrix.keys())
    parent = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a in keys:
        for b in keys:
            if a >= b:
                continue
            r = matrix[a].get(b)
            if r is not None and abs(r) >= threshold:
                union(a, b)
    groups: dict[str, list[str]] = {}
    for k in keys:
        groups.setdefault(find(k), []).append(k)
    return [sorted(g) for g in groups.values() if len(g) >= 2]


def vif_scores(feature_vectors: dict[str, list[float | None]]) -> dict[str, Any]:
    keys = [k for k, v in feature_vectors.items() if len(v) >= 5]
    if len(keys) < 2:
        return {"status": "insufficient_features", "vif": {}, "note": "VIF non calcolabile"}
    n = min(len(feature_vectors[k]) for k in keys)
    cols = []
    used = []
    for k in keys:
        col = [safe_float(feature_vectors[k][i]) for i in range(n)]
        if sum(1 for x in col if x is not None) < 5:
            continue
        present = [x for x in col if x is not None]
        mu = statistics.mean(present)
        cols.append([mu if x is None else x for x in col])
        used.append(k)
    if len(used) < 2:
        return {"status": "insufficient_features", "vif": {}, "note": "VIF non calcolabile"}
    X = np.asarray(cols, dtype=float).T
    try:
        X = X - X.mean(axis=0, keepdims=True)
        std = X.std(axis=0, keepdims=True)
        if np.any(std < 1e-12) or not np.isfinite(std).all():
            return {
                "status": "insufficient_variance",
                "vif": {},
                "note": "VIF non calcolabile: colonne costanti o non finite",
            }
        X = X / std
        corr = np.corrcoef(X, rowvar=False)
        if not np.isfinite(corr).all():
            return {
                "status": "insufficient_variance",
                "vif": {},
                "note": "VIF non calcolabile: colonne costanti o non finite",
            }
        rank = int(np.linalg.matrix_rank(X))
        if rank < X.shape[1]:
            return {
                "status": "singular_design",
                "vif": {},
                "full_matrix_rank": rank,
                "independent_feature_count": X.shape[1],
                "note": "VIF non calcolato: disegno singolare",
            }
        inv = np.linalg.inv(corr)
        vif = {used[i]: round(float(inv[i, i]), 4) for i in range(len(used))}
        return {
            "status": "ok", "vif": vif, "full_matrix_rank": rank,
            "independent_feature_count": len(used), "note": "VIF su disegno a rango pieno",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "vif": {}, "note": f"VIF fail-safe: {type(exc).__name__}"}


def population_stability_index(expected: list[float], actual: list[float], n_bins: int = 10) -> float | None:
    if len(expected) < 5 or len(actual) < 5:
        return None
    edges = np.quantile(expected, np.linspace(0, 1, n_bins + 1))
    edges = np.unique(edges)
    if len(edges) < 3:
        return None
    e_counts, _ = np.histogram(expected, bins=edges)
    a_counts, _ = np.histogram(actual, bins=edges)
    e_pct = e_counts / max(e_counts.sum(), 1)
    a_pct = a_counts / max(a_counts.sum(), 1)
    psi = 0.0
    for pe, pa in zip(e_pct, a_pct):
        pe = max(float(pe), 1e-6)
        pa = max(float(pa), 1e-6)
        psi += (pa - pe) * math.log(pa / pe)
    return round(psi, 6)


def classify_psi(psi: float | None) -> str:
    if psi is None:
        return "insufficient_sample"
    if psi < PSI_STABLE:
        return "stable"
    if psi <= PSI_MODERATE:
        return "moderately_shifted"
    return "unstable"


def ks_statistic(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    sa, sb = sorted(a), sorted(b)
    all_v = sorted(set(sa + sb))
    i = j = 0
    na, nb = len(sa), len(sb)
    d = 0.0
    for v in all_v:
        while i < na and sa[i] <= v:
            i += 1
        while j < nb and sb[j] <= v:
            j += 1
        d = max(d, abs(i / na - j / nb))
    return round(d, 6)


def direction_consistent(signs: list[int]) -> bool:
    nz = [s for s in signs if s != 0]
    if not nz:
        return True
    return all(s == nz[0] for s in nz)
