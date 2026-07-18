"""Helpers Fase 2A.1 — metriche OOF, paired comparison, bootstrap fixture-clustered."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np

# Descriptive thresholds for classify_marginal / fold stability (documented in research docs).
DELTA_AUC_STABLE = 0.01
DELTA_AUC_UNCERTAIN = 0.005
DELTA_AUC_NEGATIVE = -0.01
FOLD_NEUTRAL_ABS = 0.002
MARKET_NEUTRAL_ABS = 0.005


def stable_seed(base_seed: int, namespace: str) -> int:
    """Deterministic seed across Python processes (no builtin hash())."""
    digest = hashlib.sha256(f"{base_seed}:{namespace}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (2**31 - 1)


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
    # Full-coverage ROI is descriptive of the cohort, not model ranking.
    cohort_roi = safe_div(total_profit, float(n)) if n else None
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
        "cohort_full_coverage_roi": cohort_roi,
        "roi": cohort_roi,  # legacy alias — do not use for candidate deltas
        "mean_unit_profit": float(np.mean(profits)) if n else None,
        "max_drawdown": dd,
        "coverage": 1.0,
    }


def ranking_economic_from_scores(
    profits: np.ndarray,
    scores: np.ndarray,
) -> dict[str, Any]:
    """Model-discriminating economics from OOF score ranking only."""
    top10 = top_k_roi(profits, scores, 0.10)
    top20 = top_k_roi(profits, scores, 0.20)
    quints = quantile_roi(profits, scores, 5)
    top_q = next((q for q in quints if q.get("quantile") == 5), None)
    bot_q = next((q for q in quints if q.get("quantile") == 1), None)
    top_q_roi = top_q.get("roi") if top_q else None
    bot_q_roi = bot_q.get("roi") if bot_q else None
    spread = None
    if top_q_roi is not None and bot_q_roi is not None:
        spread = float(top_q_roi) - float(bot_q_roi)
    n = len(profits)
    return {
        "roi_top_10pct": top10.get("roi"),
        "roi_top_20pct": top20.get("roi"),
        "roi_top_quintile": top_q_roi,
        "roi_bottom_quintile": bot_q_roi,
        "top_bottom_roi_spread": spread,
        "profit_top_10pct": top10.get("mean_profit"),
        "profit_top_20pct": top20.get("mean_profit"),
        "coverage_top_10pct": safe_div(top10.get("n") or 0, n) if n else None,
        "coverage_top_20pct": safe_div(top20.get("n") or 0, n) if n else None,
        "roi_by_quintile": quints,
        "roi_top_10pct_detail": top10,
        "roi_top_20pct_detail": top20,
    }


def _ci_payload(
    values: list[float],
    *,
    estimate: float | None,
    iterations: int,
    skipped: int,
) -> dict[str, Any]:
    if not values:
        return {
            "estimate": estimate,
            "ci_low": None,
            "ci_high": None,
            "iterations": iterations,
            "valid_iterations": 0,
            "skipped_iterations": skipped,
        }
    arr = np.asarray(values, dtype=float)
    return {
        "estimate": estimate if estimate is not None else float(np.mean(arr)),
        "ci_low": float(np.percentile(arr, 2.5)),
        "ci_high": float(np.percentile(arr, 97.5)),
        "iterations": iterations,
        "valid_iterations": int(len(values)),
        "skipped_iterations": skipped,
    }


def _subset_cls_metrics(
    y: np.ndarray,
    p: np.ndarray,
) -> dict[str, float | None]:
    return {
        "auc": roc_auc(y, p),
        "brier": brier(y, p),
        "log_loss": log_loss_score(y, p),
        "ece": ece_score(y, p),
    }


def _subset_rank_roi(profits: np.ndarray, scores: np.ndarray) -> dict[str, float | None]:
    r = ranking_economic_from_scores(profits, scores)
    return {
        "roi_top_10pct": r["roi_top_10pct"],
        "roi_top_20pct": r["roi_top_20pct"],
        "roi_top_quintile": r["roi_top_quintile"],
        "top_bottom_roi_spread": r["top_bottom_roi_spread"],
    }


def paired_oof_comparison(
    rows: list[dict[str, Any]],
    predictions_candidate: np.ndarray,
    predictions_baseline: np.ndarray,
    *,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    """Paired OOF comparison on identical rows; positive delta = candidate better."""
    cand = np.asarray(predictions_candidate, dtype=float)
    base = np.asarray(predictions_baseline, dtype=float)
    n = len(rows)
    if len(cand) != n or len(base) != n:
        return {"status": "length_mismatch", "n_paired": 0}

    paired_idx = [
        i
        for i in range(n)
        if np.isfinite(cand[i]) and np.isfinite(base[i])
    ]
    if not paired_idx:
        return {"status": "no_paired_rows", "n_paired": 0}

    idx = np.asarray(paired_idx, dtype=int)
    y_all = np.array(
        [rows[i]["y_win"] if rows[i].get("y_win") is not None else np.nan for i in idx],
        dtype=float,
    )
    cls_mask = np.isfinite(y_all)
    profits = np.array([float(rows[i]["profit"]) for i in idx], dtype=float)
    fids = np.array([rows[i]["today_fixture_id"] for i in idx])
    pc = cand[idx]
    pb = base[idx]

    # Point estimates on full paired set
    cls_c = _subset_cls_metrics(y_all[cls_mask], pc[cls_mask]) if np.any(cls_mask) else {
        "auc": None, "brier": None, "log_loss": None, "ece": None
    }
    cls_b = _subset_cls_metrics(y_all[cls_mask], pb[cls_mask]) if np.any(cls_mask) else {
        "auc": None, "brier": None, "log_loss": None, "ece": None
    }
    eco_c = _subset_rank_roi(profits, pc)
    eco_b = _subset_rank_roi(profits, pb)

    def _d(a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return float(a) - float(b)

    # Positive = candidate better
    deltas = {
        "delta_auc": _d(cls_c["auc"], cls_b["auc"]),
        "delta_brier_improvement": _d(cls_b["brier"], cls_c["brier"]),
        "delta_log_loss_improvement": _d(cls_b["log_loss"], cls_c["log_loss"]),
        "delta_ece_improvement": _d(cls_b["ece"], cls_c["ece"]),
        "delta_roi_top_10pct": _d(eco_c["roi_top_10pct"], eco_b["roi_top_10pct"]),
        "delta_roi_top_20pct": _d(eco_c["roi_top_20pct"], eco_b["roi_top_20pct"]),
        "delta_roi_top_quintile": _d(eco_c["roi_top_quintile"], eco_b["roi_top_quintile"]),
        "delta_top_bottom_roi_spread": _d(
            eco_c["top_bottom_roi_spread"], eco_b["top_bottom_roi_spread"]
        ),
    }

    # Fixture-clustered paired bootstrap on differences
    groups: dict[Any, np.ndarray] = defaultdict(list)
    for local_i, fid in enumerate(fids):
        groups[fid].append(local_i)
    for k in list(groups.keys()):
        groups[k] = np.asarray(groups[k], dtype=int)
    unique_fids = list(groups.keys())
    rng = np.random.default_rng(seed)

    boot_keys = [
        "delta_auc",
        "delta_brier_improvement",
        "delta_log_loss_improvement",
        "delta_ece_improvement",
        "delta_roi_top_10pct",
        "delta_roi_top_20pct",
        "delta_roi_top_quintile",
    ]
    accum: dict[str, list[float]] = {k: [] for k in boot_keys}
    skipped = 0
    iterations = max(1, int(bootstrap_iterations))

    for _ in range(iterations):
        if not unique_fids:
            skipped += 1
            continue
        sample = rng.choice(unique_fids, size=len(unique_fids), replace=True)
        local = np.concatenate([groups[f] for f in sample])
        y_s = y_all[local]
        cls_s = np.isfinite(y_s)
        if not np.any(cls_s) or len(np.unique(y_s[cls_s])) < 2:
            skipped += 1
            continue
        mc = _subset_cls_metrics(y_s[cls_s], pc[local][cls_s])
        mb = _subset_cls_metrics(y_s[cls_s], pb[local][cls_s])
        if mc["auc"] is None or mb["auc"] is None:
            skipped += 1
            continue
        ec = _subset_rank_roi(profits[local], pc[local])
        eb = _subset_rank_roi(profits[local], pb[local])
        sample_deltas = {
            "delta_auc": float(mc["auc"] - mb["auc"]),
            "delta_brier_improvement": (
                float(mb["brier"] - mc["brier"])
                if mc["brier"] is not None and mb["brier"] is not None
                else None
            ),
            "delta_log_loss_improvement": (
                float(mb["log_loss"] - mc["log_loss"])
                if mc["log_loss"] is not None and mb["log_loss"] is not None
                else None
            ),
            "delta_ece_improvement": (
                float(mb["ece"] - mc["ece"])
                if mc["ece"] is not None and mb["ece"] is not None
                else None
            ),
            "delta_roi_top_10pct": _d(ec["roi_top_10pct"], eb["roi_top_10pct"]),
            "delta_roi_top_20pct": _d(ec["roi_top_20pct"], eb["roi_top_20pct"]),
            "delta_roi_top_quintile": _d(ec["roi_top_quintile"], eb["roi_top_quintile"]),
        }
        for k in boot_keys:
            v = sample_deltas.get(k)
            if v is not None and np.isfinite(v):
                accum[k].append(float(v))

    confidence = {
        k: _ci_payload(accum[k], estimate=deltas.get(k), iterations=iterations, skipped=skipped)
        for k in boot_keys
    }

    return {
        "status": "ok",
        "n_paired": int(len(idx)),
        "n_classification": int(np.sum(cls_mask)),
        "candidate_classification": cls_c,
        "baseline_classification": cls_b,
        "candidate_ranking_economic": eco_c,
        "baseline_ranking_economic": eco_b,
        **deltas,
        "confidence_intervals": confidence,
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
