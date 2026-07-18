"""Helpers Fase 2A — metriche OOF, bootstrap fixture-clustered, fold temporali."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np


def parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        s = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def sha256_hex(parts: list[str]) -> str:
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def safe_div(a: float, b: float) -> float | None:
    if b == 0:
        return None
    return a / b


def clip_prob(p: float, eps: float = 1e-6) -> float:
    return min(1.0 - eps, max(eps, float(p)))


def roc_auc(y: np.ndarray, score: np.ndarray) -> float | None:
    if len(y) < 2 or len(np.unique(y)) < 2:
        return None
    try:
        from sklearn.metrics import roc_auc_score

        return float(roc_auc_score(y, score))
    except Exception:  # noqa: BLE001
        return None


def brier(y: np.ndarray, p: np.ndarray) -> float | None:
    if len(y) == 0:
        return None
    return float(np.mean((p - y) ** 2))


def log_loss_score(y: np.ndarray, p: np.ndarray) -> float | None:
    if len(y) == 0:
        return None
    p = np.clip(p.astype(float), 1e-6, 1.0 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration_slope_intercept(y: np.ndarray, p: np.ndarray) -> dict[str, float | None]:
    if len(y) < 10 or len(np.unique(y)) < 2:
        return {"intercept": None, "slope": None}
    try:
        from sklearn.linear_model import LogisticRegression

        logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
        m = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500)
        m.fit(logit.reshape(-1, 1), y)
        return {
            "intercept": float(m.intercept_[0]),
            "slope": float(m.coef_[0][0]),
        }
    except Exception:  # noqa: BLE001
        return {"intercept": None, "slope": None}


def ece_score(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float | None:
    if len(y) < n_bins:
        return None
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (p >= bins[i]) & (p < bins[i + 1] if i < n_bins - 1 else p <= bins[i + 1])
        if not np.any(mask):
            continue
        ece += abs(float(np.mean(y[mask]) - np.mean(p[mask]))) * (np.sum(mask) / len(y))
    return float(ece)


def economic_metrics(
    profits: np.ndarray,
    won: np.ndarray,
    odds: np.ndarray,
    *,
    void_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """won: 1/0; void_mask True = void (excluded from WR)."""
    if void_mask is None:
        void_mask = np.zeros(len(profits), dtype=bool)
    settled_cls = ~void_mask
    n = int(len(profits))
    n_wr = int(np.sum(settled_cls))
    wins = int(np.sum(won[settled_cls] == 1)) if n_wr else 0
    wr = safe_div(wins, n_wr)
    total_profit = float(np.sum(profits)) if n else 0.0
    roi = safe_div(total_profit, float(n)) if n else None
    avg_odds = float(np.mean(odds[settled_cls])) if n_wr else None
    be = float(np.mean(1.0 / odds[settled_cls])) if n_wr and np.all(odds[settled_cls] > 0) else None
    # temporal drawdown on order given
    cum = np.cumsum(profits) if n else np.array([])
    dd = None
    if n:
        peak = np.maximum.accumulate(cum)
        dd = float(np.min(cum - peak))
    return {
        "n": n,
        "n_classification": n_wr,
        "wins": wins,
        "win_rate": wr,
        "avg_odds": avg_odds,
        "avg_break_even_prob": be,
        "total_unit_profit": total_profit,
        "roi": roi,
        "mean_unit_profit": float(np.mean(profits)) if n else None,
        "max_drawdown": dd,
        "coverage": 1.0,
    }


def quantile_roi(profits: np.ndarray, scores: np.ndarray, q: int = 5) -> list[dict[str, Any]]:
    if len(profits) < q * 2:
        return []
    order = np.argsort(scores)
    chunks = np.array_split(order, q)
    out = []
    for i, idx in enumerate(chunks):
        if len(idx) == 0:
            continue
        p = profits[idx]
        out.append(
            {
                "quantile": i + 1,
                "n": int(len(idx)),
                "roi": safe_div(float(np.sum(p)), float(len(idx))),
                "mean_profit": float(np.mean(p)),
            }
        )
    return out


def top_k_roi(profits: np.ndarray, scores: np.ndarray, frac: float) -> dict[str, Any]:
    n = len(profits)
    if n == 0:
        return {"n": 0, "roi": None}
    k = max(1, int(round(n * frac)))
    idx = np.argsort(scores)[-k:]
    p = profits[idx]
    return {"n": int(k), "roi": safe_div(float(np.sum(p)), float(k)), "mean_profit": float(np.mean(p))}


def fixture_cluster_bootstrap_ci(
    fixture_ids: np.ndarray,
    values_by_row: np.ndarray,
    *,
    iterations: int,
    seed: int,
    agg: str = "mean",
) -> dict[str, Any]:
    """Bootstrap resampling fixtures; keep all rows of sampled fixtures."""
    rng = np.random.default_rng(seed)
    groups: dict[Any, np.ndarray] = defaultdict(list)
    for i, fid in enumerate(fixture_ids):
        groups[fid].append(i)
    fids = list(groups.keys())
    if not fids:
        return {"mean": None, "ci_low": None, "ci_high": None, "iterations": 0}
    for k in list(groups.keys()):
        groups[k] = np.asarray(groups[k], dtype=int)
    stats = []
    for _ in range(max(1, iterations)):
        sample = rng.choice(fids, size=len(fids), replace=True)
        idx = np.concatenate([groups[f] for f in sample])
        vals = values_by_row[idx]
        if agg == "mean":
            stats.append(float(np.mean(vals)))
        elif agg == "sum":
            stats.append(float(np.sum(vals)))
        else:
            stats.append(float(np.mean(vals)))
    arr = np.asarray(stats, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "ci_low": float(np.percentile(arr, 2.5)),
        "ci_high": float(np.percentile(arr, 97.5)),
        "iterations": int(iterations),
    }


def expanding_fixture_folds(
    fixtures_ordered: list[Any],
    *,
    min_folds: int = 3,
    max_folds: int = 4,
) -> tuple[list[dict[str, Any]], list[str]]:
    """fixtures_ordered: list of fixture_id in time order (unique)."""
    limitations: list[str] = []
    n = len(fixtures_ordered)
    if n < 6:
        limitations.append("limited_temporal_span")
        # single holdout: first 2/3 train, last 1/3 test
        cut = max(1, n * 2 // 3)
        return (
            [
                {
                    "fold": 1,
                    "train_fixture_ids": fixtures_ordered[:cut],
                    "test_fixture_ids": fixtures_ordered[cut:],
                }
            ],
            limitations,
        )
    n_folds = max_folds if n >= 16 else min_folds
    # expanding: fold k uses first (k+1)/(n_folds+1) as train end, next slice as test
    folds = []
    for k in range(1, n_folds + 1):
        train_end = int(round(n * k / (n_folds + 1)))
        test_end = int(round(n * (k + 1) / (n_folds + 1)))
        if test_end <= train_end:
            continue
        train_ids = fixtures_ordered[:train_end]
        test_ids = fixtures_ordered[train_end:test_end]
        if not train_ids or not test_ids:
            continue
        folds.append(
            {
                "fold": len(folds) + 1,
                "train_fixture_ids": train_ids,
                "test_fixture_ids": test_ids,
            }
        )
    if len(folds) < min_folds:
        limitations.append("limited_temporal_span")
    return folds, limitations


def spearman_rho(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)

    def ranks(a: np.ndarray) -> np.ndarray:
        order = np.argsort(a)
        r = np.empty(len(a), dtype=float)
        i = 0
        while i < len(a):
            j = i
            while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    den = math.sqrt(float(np.sum(rx**2) * np.sum(ry**2)))
    if den == 0:
        return None
    return float(np.sum(rx * ry) / den)


def gap_from_payload(row: dict[str, Any], payload_key: str, own_value: float | None) -> float | None:
    payload = row.get(payload_key) or {}
    if not isinstance(payload, dict) or not payload or own_value is None:
        return None
    # first comparator / complement key
    for _k, v in payload.items():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        return float(own_value) - fv
    return None
