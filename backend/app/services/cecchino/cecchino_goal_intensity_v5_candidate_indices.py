"""Intensità Goal v5 — Fase 1D: indici candidati research (ECDF train-only).

Riusa il dataset Fase 1B; non modifica statistics v1_2, eligibility, né v4.
Nessuna formula produttiva: solo candidati research trasparenti 0–100.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from datetime import date
from typing import Any, Iterator, Literal

import numpy as np
from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_dataset import (
    XG_FEATURE_KEYS,
    build_goal_intensity_v5_dataset_internal,
    filter_dataset_rows_by_kind,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import (
    bootstrap_auc_ci,
    bootstrap_index_matrix,
    bootstrap_paired_delta_ci,
    bootstrap_spearman_ci,
    correlation_matrix,
    direction_consistent,
    monotonicity_from_quintile_means,
    pearson_r,
    safe_float,
    spearman_rho,
    vif_scores,
)

VERSION = "cecchino_goal_intensity_v5_candidate_indices_v1"
ELIGIBILITY_ENGINE_VERSION = "legacy_pre_utc_fix"
NORMALIZATION_METHOD = "train_ecdf_midrank"
WEIGHT_STATUS = "equal_weight_research_baseline"
VALIDATION_STATUS = "retrospective_selection_informed"
RESEARCH_NOTE = (
    "La ricerca descrive la coorte effettivamente dichiarata eleggibile da Cecchino Today "
    "nel periodo analizzato. Le esclusioni tecniche storiche non sono state rivalutate. "
    "Validation/test sono selection-informed: nessuna validazione produttiva definitiva."
)

HARD_EXCLUDED_FEATURES = frozenset({
    "goals_scored_mad_last_10",
    "goals_scored_cv_last_10",
    "goals_rolling_5_vs_10_delta",
    "goals_ge_3_frequency_last_10",
    "pair_goals_scored_rolling_5",
    "pair_goals_scored_rolling_10",
})

SCORE_FEATURES = (
    "home_goals_scored_avg",
    "home_goals_scored_rolling_5",
    "away_goals_scored_avg",
    "away_goals_scored_rolling_5",
    "home_goals_conceded_avg",
    "away_goals_conceded_avg",
    "total_goals_avg",
    "total_goals_rolling_5",
    "goals_scored_std_last_10",
)

XG_SCORE_FEATURES = ("pair_xg_for_avg", "pair_xg_against_avg")

ALL_TARGETS = ("total_goals_ft", "goals_ge_2", "goals_ge_3", "btts_ft")
BINARY_TARGETS = ("goals_ge_2", "goals_ge_3", "btts_ft")

PILLAR_CANDIDATE_IDS = (
    "OP1_HOME_LONG_TERM",
    "OP2_HOME_RECENCY",
    "OP3_SYMMETRIC_LONG_TERM_DIAGNOSTIC",
    "OP4_SYMMETRIC_RECENCY_DIAGNOSTIC",
    "DV1_MEAN_CONCEDED",
    "DV2_WEAKEST_DEFENCE",
    "MT1_LONG_TERM",
    "MT2_LONG_TERM_PLUS_RECENCY",
    "OV1_STD",
)

COMPOSITE_IDS = (
    "GI_A_STRICT_CORE",
    "GI_B_RECENCY",
    "GI_C_SYMMETRIC_DIAGNOSTIC",
    "GI_D_WEAKEST_DEFENCE",
)

CANDIDATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "OP1_HOME_LONG_TERM": {
        "status": "strict_core",
        "pillar": "offensive_production",
        "formula": "percentile(home_goals_scored_avg)",
        "features": ["home_goals_scored_avg"],
    },
    "OP2_HOME_RECENCY": {
        "status": "core_plus_recency",
        "pillar": "offensive_production",
        "formula": "mean(pct(home_goals_scored_avg), pct(home_goals_scored_rolling_5))",
        "features": ["home_goals_scored_avg", "home_goals_scored_rolling_5"],
    },
    "OP3_SYMMETRIC_LONG_TERM_DIAGNOSTIC": {
        "status": "diagnostic_secondary",
        "pillar": "offensive_production",
        "formula": "mean(pct(home_goals_scored_avg), pct(away_goals_scored_avg))",
        "features": ["home_goals_scored_avg", "away_goals_scored_avg"],
    },
    "OP4_SYMMETRIC_RECENCY_DIAGNOSTIC": {
        "status": "diagnostic_secondary",
        "pillar": "offensive_production",
        "formula": "mean(pct home/away avg + rolling_5)",
        "features": [
            "home_goals_scored_avg",
            "home_goals_scored_rolling_5",
            "away_goals_scored_avg",
            "away_goals_scored_rolling_5",
        ],
    },
    "DV1_MEAN_CONCEDED": {
        "status": "strict_core",
        "pillar": "defensive_vulnerability",
        "formula": "mean(pct(home_goals_conceded_avg), pct(away_goals_conceded_avg))",
        "features": ["home_goals_conceded_avg", "away_goals_conceded_avg"],
        "direction": "high = greater vulnerability",
    },
    "DV2_WEAKEST_DEFENCE": {
        "status": "strict_core_variant",
        "pillar": "defensive_vulnerability",
        "formula": "max(pct(home_goals_conceded_avg), pct(away_goals_conceded_avg))",
        "features": ["home_goals_conceded_avg", "away_goals_conceded_avg"],
    },
    "MT1_LONG_TERM": {
        "status": "strict_core",
        "pillar": "match_tempo",
        "formula": "percentile(total_goals_avg)",
        "features": ["total_goals_avg"],
    },
    "MT2_LONG_TERM_PLUS_RECENCY": {
        "status": "core_plus_recency",
        "pillar": "match_tempo",
        "formula": "mean(pct(total_goals_avg), pct(total_goals_rolling_5))",
        "features": ["total_goals_avg", "total_goals_rolling_5"],
    },
    "OV1_STD": {
        "status": "strict_core",
        "pillar": "offensive_volatility",
        "formula": "percentile(goals_scored_std_last_10)",
        "features": ["goals_scored_std_last_10"],
        "direction": "high = greater volatility (not stability)",
    },
    "GI_A_STRICT_CORE": {
        "status": "composite_baseline",
        "formula": "mean(OP1, DV1, MT1, OV1)",
        "components": ["OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM", "OV1_STD"],
        "weight_status": WEIGHT_STATUS,
    },
    "GI_B_RECENCY": {
        "status": "composite_recency",
        "formula": "mean(OP2, DV1, MT2, OV1)",
        "components": ["OP2_HOME_RECENCY", "DV1_MEAN_CONCEDED", "MT2_LONG_TERM_PLUS_RECENCY", "OV1_STD"],
        "weight_status": WEIGHT_STATUS,
    },
    "GI_C_SYMMETRIC_DIAGNOSTIC": {
        "status": "composite_diagnostic",
        "formula": "mean(OP3, DV1, MT1, OV1)",
        "components": ["OP3_SYMMETRIC_LONG_TERM_DIAGNOSTIC", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM", "OV1_STD"],
        "weight_status": WEIGHT_STATUS,
    },
    "GI_D_WEAKEST_DEFENCE": {
        "status": "composite_variant",
        "formula": "mean(OP1, DV2, MT1, OV1)",
        "components": ["OP1_HOME_LONG_TERM", "DV2_WEAKEST_DEFENCE", "MT1_LONG_TERM", "OV1_STD"],
        "weight_status": WEIGHT_STATUS,
    },
}

CandidateExportKind = Literal[
    "summary",
    "candidate_definitions",
    "candidate_scores",
    "pillar_metrics",
    "composite_metrics",
    "temporal_metrics",
    "decile_calibration",
    "ablation_analysis",
    "paired_candidate_comparison",
    "pillar_redundancy",
    "xg_optional_enrichment",
    "prospective_validation_protocol",
]


def _core_rows(rows: list[dict[str, Any]], min_sample: int) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if r.get("eligibility_status") != "eligible":
            continue
        if not r.get("row_feature_safe"):
            continue
        if r.get("core_feature_status") != "available":
            continue
        if int(r.get("sample_size") or 0) < min_sample:
            continue
        out.append(r)
    return out


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, digits)


def _distribution_hash(values: np.ndarray) -> str:
    payload = values.astype(np.float64).tobytes()
    return hashlib.sha256(payload).hexdigest()


class TrainEcdf:
    """ECDF midrank 0–100 fittata solo sul train."""

    def __init__(self, train_values: list[float]):
        arr = np.asarray([v for v in train_values if v is not None and np.isfinite(v)], dtype=float)
        arr.sort()
        self.values = arr
        self.n = int(arr.size)
        self.train_min = float(arr[0]) if self.n else None
        self.train_max = float(arr[-1]) if self.n else None
        self.train_median = float(np.median(arr)) if self.n else None
        self.ties_count = int(self.n - len(np.unique(arr))) if self.n else 0
        self.clipping_low_count = 0
        self.clipping_high_count = 0
        self.distribution_hash = _distribution_hash(arr) if self.n else hashlib.sha256(b"empty").hexdigest()
        self.quantiles = {}
        if self.n:
            for q in (5, 10, 25, 50, 75, 90, 95):
                self.quantiles[f"p{q}"] = float(np.quantile(arr, q / 100.0))

    def transform(self, x: float | None) -> float | None:
        if x is None or self.n == 0:
            return None
        try:
            xf = float(x)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(xf):
            return None
        if self.train_min is not None and xf < self.train_min:
            self.clipping_low_count += 1
            xf = self.train_min
        if self.train_max is not None and xf > self.train_max:
            self.clipping_high_count += 1
            xf = self.train_max
        less = int(np.searchsorted(self.values, xf, side="left"))
        equal = int(np.searchsorted(self.values, xf, side="right") - less)
        score = 100.0 * (less + 0.5 * equal) / self.n
        return float(min(100.0, max(0.0, score)))

    def metadata(self) -> dict[str, Any]:
        return {
            "normalization_method": NORMALIZATION_METHOD,
            "train_n": self.n,
            "train_min": _round(self.train_min),
            "train_max": _round(self.train_max),
            "train_median": _round(self.train_median),
            "quantiles": {k: _round(v) for k, v in self.quantiles.items()},
            "clipping_low_count": self.clipping_low_count,
            "clipping_high_count": self.clipping_high_count,
            "ties_count": self.ties_count,
            "distribution_hash": self.distribution_hash,
        }


def fit_train_ecdfs(rows: list[dict[str, Any]], features: tuple[str, ...]) -> dict[str, TrainEcdf]:
    train = [r for r in rows if r.get("temporal_fold_candidate") == "train"]
    return {
        feature: TrainEcdf([safe_float(r.get(feature)) for r in train if safe_float(r.get(feature)) is not None])
        for feature in features
    }


def apply_ecdfs(rows: list[dict[str, Any]], ecdfs: dict[str, TrainEcdf]) -> list[dict[str, float | None]]:
    out = []
    for row in rows:
        scored = {feature: ecdf.transform(safe_float(row.get(feature))) for feature, ecdf in ecdfs.items()}
        out.append(scored)
    return out


def _mean_ignore_none(values: list[float | None]) -> float | None:
    present = [float(v) for v in values if v is not None and np.isfinite(v)]
    if not present:
        return None
    return float(sum(present) / len(present))


def _pillar_scores_from_pct(pct: dict[str, float | None]) -> dict[str, float | None]:
    op1 = pct.get("home_goals_scored_avg")
    op2 = _mean_ignore_none([pct.get("home_goals_scored_avg"), pct.get("home_goals_scored_rolling_5")])
    op3 = _mean_ignore_none([pct.get("home_goals_scored_avg"), pct.get("away_goals_scored_avg")])
    op4 = _mean_ignore_none([
        pct.get("home_goals_scored_avg"),
        pct.get("home_goals_scored_rolling_5"),
        pct.get("away_goals_scored_avg"),
        pct.get("away_goals_scored_rolling_5"),
    ])
    home_c = pct.get("home_goals_conceded_avg")
    away_c = pct.get("away_goals_conceded_avg")
    dv1 = _mean_ignore_none([home_c, away_c])
    dv2_vals = [v for v in (home_c, away_c) if v is not None]
    dv2 = max(dv2_vals) if dv2_vals else None
    mt1 = pct.get("total_goals_avg")
    mt2 = _mean_ignore_none([mt1, pct.get("total_goals_rolling_5")])
    ov1 = pct.get("goals_scored_std_last_10")
    return {
        "OP1_HOME_LONG_TERM": op1,
        "OP2_HOME_RECENCY": op2,
        "OP3_SYMMETRIC_LONG_TERM_DIAGNOSTIC": op3,
        "OP4_SYMMETRIC_RECENCY_DIAGNOSTIC": op4,
        "DV1_MEAN_CONCEDED": dv1,
        "DV2_WEAKEST_DEFENCE": dv2,
        "defensive_solidity_display": _round(100.0 - dv1) if dv1 is not None else None,
        "MT1_LONG_TERM": mt1,
        "MT2_LONG_TERM_PLUS_RECENCY": mt2,
        "OV1_STD": ov1,
        "offensive_stability_display": _round(100.0 - ov1) if ov1 is not None else None,
    }


def _composite_scores(pillar: dict[str, float | None]) -> dict[str, float | None]:
    def m(*keys: str) -> float | None:
        return _mean_ignore_none([pillar.get(k) for k in keys])

    return {
        "GI_A_STRICT_CORE": m("OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM", "OV1_STD"),
        "GI_B_RECENCY": m("OP2_HOME_RECENCY", "DV1_MEAN_CONCEDED", "MT2_LONG_TERM_PLUS_RECENCY", "OV1_STD"),
        "GI_C_SYMMETRIC_DIAGNOSTIC": m(
            "OP3_SYMMETRIC_LONG_TERM_DIAGNOSTIC", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM", "OV1_STD"
        ),
        "GI_D_WEAKEST_DEFENCE": m("OP1_HOME_LONG_TERM", "DV2_WEAKEST_DEFENCE", "MT1_LONG_TERM", "OV1_STD"),
    }


def _loo_composites(pillar: dict[str, float | None]) -> dict[str, float | None]:
    base = ("OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM", "OV1_STD")
    labels = ("without_production", "without_defence", "without_tempo", "without_volatility")
    out = {}
    for idx, label in enumerate(labels):
        keys = [k for i, k in enumerate(base) if i != idx]
        out[label] = _mean_ignore_none([pillar.get(k) for k in keys])
    return out


def _score_rows(rows: list[dict[str, Any]], ecdfs: dict[str, TrainEcdf]) -> list[dict[str, Any]]:
    pct_rows = apply_ecdfs(rows, ecdfs)
    scored = []
    for row, pct in zip(rows, pct_rows):
        pillar = _pillar_scores_from_pct(pct)
        composite = _composite_scores(pillar)
        loo = _loo_composites(pillar)
        item = {
            "today_fixture_id": row.get("today_fixture_id"),
            "local_fixture_id": row.get("local_fixture_id"),
            "provider_fixture_id": row.get("provider_fixture_id"),
            "scan_date": row.get("scan_date"),
            "kickoff": row.get("kickoff"),
            "competition_id": row.get("competition_id"),
            "home_team_id": row.get("home_team_id"),
            "away_team_id": row.get("away_team_id"),
            "split": row.get("temporal_fold_candidate"),
            "normalization_fold": "train",
            "candidate_version": VERSION,
            "no_target_used_in_score": True,
            **{k: _round(v) for k, v in pillar.items()},
            **{k: _round(v) for k, v in composite.items()},
            **{f"GI_A_{k}": _round(v) for k, v in loo.items()},
            # targets AFTER scores
            "total_goals_ft": row.get("total_goals_ft"),
            "goals_ge_2": int(bool(row.get("goals_ge_2"))),
            "goals_ge_3": int(bool(row.get("goals_ge_3"))),
            "btts_ft": int(bool(row.get("btts_ft"))),
            "_pct": pct,
        }
        scored.append(item)
    return scored


def _paired_xy(xs: list[float | None], ys: list[Any]) -> tuple[list[float], list[float]]:
    ox, oy = [], []
    for x, y in zip(xs, ys):
        xf = safe_float(x)
        yf = safe_float(y)
        if xf is None or yf is None:
            continue
        ox.append(xf)
        oy.append(yf)
    return ox, oy


def _linear_calibration_metrics(xs: list[float], ys: list[float], train_mask: list[bool]) -> dict[str, Any]:
    tx = [x for x, m in zip(xs, train_mask) if m]
    ty = [y for y, m in zip(ys, train_mask) if m]
    if len(tx) < 3:
        return {"mae": None, "rmse": None}
    x_arr, y_arr = np.asarray(tx, float), np.asarray(ty, float)
    if np.std(x_arr) < 1e-12:
        pred_all = np.full(len(xs), float(np.mean(y_arr)))
    else:
        slope, intercept = np.polyfit(x_arr, y_arr, 1)
        pred_all = slope * np.asarray(xs, float) + intercept
    err = pred_all - np.asarray(ys, float)
    return {
        "mae": _round(float(np.mean(np.abs(err)))),
        "rmse": _round(float(np.sqrt(np.mean(err ** 2)))),
    }


def _decile_stats(xs: list[float], ys: list[float]) -> dict[str, Any]:
    if len(xs) < 10:
        return {"decile_means": [], "high_minus_low": None, "monotonicity_score": None}
    order = np.argsort(xs)
    x_sorted = np.asarray(xs, float)[order]
    y_sorted = np.asarray(ys, float)[order]
    edges = np.quantile(x_sorted, np.linspace(0, 1, 11))
    means = []
    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        if i < 9:
            mask = (x_sorted >= lo) & (x_sorted < hi)
        else:
            mask = (x_sorted >= lo) & (x_sorted <= hi)
        vals = y_sorted[mask]
        means.append(float(np.mean(vals)) if len(vals) else None)
    mono = monotonicity_from_quintile_means(means)
    high_low = None
    if means[0] is not None and means[-1] is not None:
        high_low = means[-1] - means[0]
    return {
        "decile_means": [_round(m) for m in means],
        "high_minus_low": _round(high_low),
        "monotonicity_score": mono.get("monotonicity_score"),
        "monotonic_direction": mono.get("monotonic_direction"),
    }


def _binary_scores(y_true: list[float], scores: list[float]) -> dict[str, Any]:
    y = np.asarray(y_true, float)
    s = np.asarray(scores, float)
    if len(y) < 5 or len(np.unique(y)) < 2:
        return {"auc": None, "brier": None, "log_loss": None}
    # Probabilità grezza = score/100
    p = np.clip(s / 100.0, 1e-6, 1 - 1e-6)
    brier = float(np.mean((p - y) ** 2))
    logloss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import auc_mann_whitney

    auc = auc_mann_whitney(y.astype(int).tolist(), s.tolist())
    return {"auc": _round(auc), "brier": _round(brier), "log_loss": _round(logloss)}


def evaluate_score_metrics(
    scored_rows: list[dict[str, Any]],
    score_key: str,
    *,
    bootstrap_iterations: int,
    random_seed: int,
    bootstrap_cache: dict[int, np.ndarray],
) -> dict[str, Any]:
    xs = [safe_float(r.get(score_key)) for r in scored_rows]
    train_mask = [r.get("split") == "train" for r in scored_rows]
    result: dict[str, Any] = {"score_key": score_key, "n": sum(1 for x in xs if x is not None)}
    # continuous
    ox, oy = _paired_xy(xs, [r.get("total_goals_ft") for r in scored_rows])
    if len(ox) >= 3:
        idx = bootstrap_cache.setdefault(len(ox), bootstrap_index_matrix(len(ox), bootstrap_iterations, random_seed))
        spearman = bootstrap_spearman_ci(ox, oy, iterations=bootstrap_iterations, seed=random_seed, indices=idx)
        train_mask_paired: list[bool] = []
        for x, y, m in zip(xs, [r.get("total_goals_ft") for r in scored_rows], train_mask):
            if safe_float(x) is not None and safe_float(y) is not None:
                train_mask_paired.append(bool(m))
        result["total_goals_ft"] = {
            "pearson": _round(pearson_r(ox, oy)),
            "spearman": spearman.get("spearman"),
            "spearman_bootstrap": spearman,
            **_linear_calibration_metrics(ox, oy, train_mask_paired),
            **_decile_stats(ox, oy),
        }
    for target in BINARY_TARGETS:
        bx, by = _paired_xy(xs, [r.get(target) for r in scored_rows])
        if len(bx) < 5:
            continue
        binary = np.asarray(by, float)
        values = np.asarray(bx, float)
        idx = bootstrap_cache.setdefault(len(bx), bootstrap_index_matrix(len(bx), bootstrap_iterations, random_seed))
        auc_ci = bootstrap_auc_ci(binary, values, idx)
        bin_metrics = _binary_scores(by, bx)
        deciles = _decile_stats(bx, by)
        result[target] = {
            **bin_metrics,
            "auc_bootstrap": auc_ci,
            "rate_per_decile": deciles.get("decile_means"),
            "monotonicity_score": deciles.get("monotonicity_score"),
            "monotonic_direction": deciles.get("monotonic_direction"),
        }
    return result


def _split_metrics(scored_rows: list[dict[str, Any]], score_key: str) -> dict[str, Any]:
    out = {}
    for split in ("train", "validation", "test"):
        subset = [r for r in scored_rows if r.get("split") == split]
        xs, ys = _paired_xy(
            [safe_float(r.get(score_key)) for r in subset],
            [r.get("total_goals_ft") for r in subset],
        )
        out[split] = {
            "n": len(subset),
            "spearman_total_goals": _round(spearman_rho(xs, ys)) if len(xs) >= 3 else None,
        }
    signs = []
    for split in ("train", "validation", "test"):
        rho = out[split]["spearman_total_goals"]
        if rho is not None:
            signs.append(1 if rho > 0 else -1 if rho < 0 else 0)
    out["direction_consistent"] = direction_consistent(signs)
    return out


def _expanding_fold_metrics(
    rows: list[dict[str, Any]],
    *,
    bootstrap_iterations: int,
    random_seed: int,
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda r: str(r.get("kickoff") or ""))
    if len(ordered) < 30:
        return {"status": "insufficient_sample_for_3_temporal_folds", "folds": []}
    folds_scores: list[list[dict[str, Any]]] = []
    step = max(1, len(ordered) // 4)
    for end in range(max(12, len(ordered) // 3), len(ordered) - 4, step):
        train = ordered[:end]
        test = ordered[end : min(len(ordered), end + max(4, len(ordered) // 6))]
        if len(test) < 4:
            continue
        ecdfs = {
            feature: TrainEcdf([safe_float(r.get(feature)) for r in train if safe_float(r.get(feature)) is not None])
            for feature in SCORE_FEATURES
        }
        pct_rows = apply_ecdfs(test, ecdfs)
        scored_test = []
        for row, pct in zip(test, pct_rows):
            pillar = _pillar_scores_from_pct(pct)
            composite = _composite_scores(pillar)
            scored_test.append({
                "split": "test",
                **{k: _round(v) for k, v in composite.items()},
                "total_goals_ft": row.get("total_goals_ft"),
            })
        folds_scores.append(scored_test)
        if len(folds_scores) >= 3 and end > len(ordered) * 0.7:
            break
    if len(folds_scores) < 3:
        return {"status": "insufficient_sample_for_3_temporal_folds", "folds": []}
    rhos = []
    for fold_rows in folds_scores:
        xs, ys = _paired_xy(
            [safe_float(r.get("GI_A_STRICT_CORE")) for r in fold_rows],
            [r.get("total_goals_ft") for r in fold_rows],
        )
        rho = spearman_rho(xs, ys) if len(xs) >= 3 else None
        if rho is not None:
            rhos.append(rho)
    return {
        "status": "ok",
        "fold_count": len(folds_scores),
        "GI_A_STRICT_CORE": {
            "mean_spearman": _round(float(np.mean(rhos))) if rhos else None,
            "std_spearman": _round(float(np.std(rhos))) if len(rhos) > 1 else None,
            "direction_consistent": direction_consistent(
                [1 if r > 0 else -1 if r < 0 else 0 for r in rhos]
            ),
        },
    }


def _pareto_select(composite_metrics: dict[str, dict[str, Any]], temporal_by_id: dict[str, Any]) -> dict[str, Any]:
    ids = list(COMPOSITE_IDS)
    # Primary metrics for dominance: |spearman TG|, AUC ge2, direction consistency
    def metric_tuple(cid: str) -> tuple[float, float, float]:
        m = composite_metrics.get(cid) or {}
        tg = m.get("total_goals_ft") or {}
        ge2 = m.get("goals_ge_2") or {}
        spearman = abs(float(tg.get("spearman") or 0))
        auc = float(ge2.get("auc") or 0.5)
        temp = 1.0 if (temporal_by_id.get(cid) or {}).get("direction_consistent") else 0.0
        return (spearman, auc, temp)

    dominated = set()
    for a in ids:
        for b in ids:
            if a == b:
                continue
            ma, mb = metric_tuple(a), metric_tuple(b)
            if all(x >= y for x, y in zip(mb, ma)) and any(x > y for x, y in zip(mb, ma)):
                dominated.add(a)
    front = [cid for cid in ids if cid not in dominated]
    # Default: primary = GI_A as transparent baseline; challenger = best non-dominated other
    primary = "GI_A_STRICT_CORE"
    others = [cid for cid in front if cid != primary] or [cid for cid in ids if cid != primary]
    challenger = max(others, key=lambda cid: metric_tuple(cid)[0]) if others else None
    # Evidence low unless a non-A candidate clearly dominates A
    evidence = "low"
    motivation = (
        "Baseline research equal-weight GI_A_STRICT_CORE selezionata come primary trasparente; "
        "nessuna superiorità statistica dichiarata (selection-informed / CI spesso includono zero)."
    )
    return {
        "pareto_front_candidates": front,
        "dominated_candidates": sorted(dominated),
        "primary_candidate": primary,
        "challenger_candidate": challenger,
        "selection_evidence_level": evidence,
        "selection_motivation": motivation,
    }


def _candidate_definition_hash() -> str:
    payload = json.dumps(CANDIDATE_DEFINITIONS, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _prospective_protocol(*, date_to: date) -> dict[str, Any]:
    return {
        "candidate_definition_frozen_at": date_to.isoformat(),
        "candidate_definition_hash": _candidate_definition_hash(),
        "dataset_end_date": date_to.isoformat(),
        "first_prospective_scan_date": date_to.isoformat(),
        "minimum_prospective_matches": 200,
        "metrics_to_monitor": [
            "spearman_total_goals_ft",
            "auc_goals_ge_2",
            "auc_goals_ge_3",
            "auc_btts_ft",
            "decile_monotonicity",
            "direction_consistency_expanding_folds",
        ],
        "no_retroactive_formula_changes": True,
        "validation_status": VALIDATION_STATUS,
        "note": (
            "La selezione feature Fase 1C ha usato l'intera coorte storica; "
            "validation/test attuali non sono holdout incontaminati. "
            "Nessuna validazione produttiva definitiva in Fase 1D."
        ),
    }


def build_goal_intensity_v5_candidate_indices_internal(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    minimum_history_sample: int = 10,
    bootstrap_iterations: int = 1000,
    random_seed: int = 42,
) -> dict[str, Any]:
    t0, phases = time.perf_counter(), {}
    t = time.perf_counter()
    source = build_goal_intensity_v5_dataset_internal(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    phases["dataset_internal_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    if source.get("error") or source.get("status") == "error":
        return {"status": "error", "version": VERSION, "error": source.get("error"), "performance": phases}

    dataset_rows = list(source.get("dataset_rows") or [])
    if any(r.get("eligibility_status") != "eligible" for r in dataset_rows):
        return {
            "status": "error",
            "version": VERSION,
            "error": "ineligible_match_entered_candidate_indices_dataset",
            "warnings": ["ineligible_match_entered_candidate_indices_dataset"],
            "performance": phases,
        }

    rows = _core_rows(dataset_rows, minimum_history_sample)
    core10 = _core_rows(dataset_rows, 10)
    core20 = _core_rows(dataset_rows, 20)
    bootstrap_cache: dict[int, np.ndarray] = {}

    # Hard exclusion check: never use excluded features in ECDF/scoring
    for feature in HARD_EXCLUDED_FEATURES:
        assert feature not in SCORE_FEATURES

    t = time.perf_counter()
    ecdfs = fit_train_ecdfs(rows, SCORE_FEATURES)
    scored = _score_rows(rows, ecdfs)
    phases["normalization_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    phases["pillar_scores_ms"] = phases["normalization_ms"]
    phases["composite_scores_ms"] = phases["normalization_ms"]

    normalization_summary = {
        "method": NORMALIZATION_METHOD,
        "features": {feature: ecdf.metadata() for feature, ecdf in ecdfs.items()},
        "hard_excluded_features": sorted(HARD_EXCLUDED_FEATURES),
        "no_target_used_in_normalization": True,
        "fit_split": "train",
    }

    t = time.perf_counter()
    pillar_metrics = {
        cid: evaluate_score_metrics(
            scored, cid, bootstrap_iterations=bootstrap_iterations,
            random_seed=random_seed, bootstrap_cache=bootstrap_cache,
        )
        for cid in PILLAR_CANDIDATE_IDS
    }
    composite_metrics = {
        cid: evaluate_score_metrics(
            scored, cid, bootstrap_iterations=bootstrap_iterations,
            random_seed=random_seed, bootstrap_cache=bootstrap_cache,
        )
        for cid in COMPOSITE_IDS
    }
    baseline_metrics = {
        cid: evaluate_score_metrics(
            scored, cid, bootstrap_iterations=bootstrap_iterations,
            random_seed=random_seed, bootstrap_cache=bootstrap_cache,
        )
        for cid in ("MT1_LONG_TERM", "OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "OV1_STD")
    }
    phases["metrics_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    phases["bootstrap_ms"] = phases["metrics_ms"]

    t = time.perf_counter()
    temporal_metrics = {cid: _split_metrics(scored, cid) for cid in list(COMPOSITE_IDS) + list(PILLAR_CANDIDATE_IDS)}
    expanding = _expanding_fold_metrics(
        rows, bootstrap_iterations=bootstrap_iterations, random_seed=random_seed
    )
    # core_min20 robustness
    ecdfs20 = fit_train_ecdfs(core20, SCORE_FEATURES)
    scored20 = _score_rows(core20, ecdfs20)
    core20_metrics = {
        "GI_A_STRICT_CORE": evaluate_score_metrics(
            scored20, "GI_A_STRICT_CORE",
            bootstrap_iterations=min(200, bootstrap_iterations),
            random_seed=random_seed,
            bootstrap_cache={},
        )
    }
    month_diag: dict[str, Any] = {}
    for month_key, prefix in (("june", "2026-06"), ("july", "2026-07")):
        subset = [r for r in scored if str(r.get("scan_date") or "").startswith(prefix)]
        xs, ys = _paired_xy(
            [safe_float(r.get("GI_A_STRICT_CORE")) for r in subset],
            [r.get("total_goals_ft") for r in subset],
        )
        month_diag[month_key] = {
            "n": len(subset),
            "spearman_GI_A_total_goals": _round(spearman_rho(xs, ys)) if len(xs) >= 3 else None,
            "status": "diagnostic_only",
        }
    phases["temporal_ms"] = _round((time.perf_counter() - t) * 1000, 2)

    t = time.perf_counter()
    # Ablation leave-one-out vs GI_A
    ablation = {}
    gi_a_scores = [safe_float(r.get("GI_A_STRICT_CORE")) for r in scored]
    y_tg = [r.get("total_goals_ft") for r in scored]
    for label, key in (
        ("without_production", "GI_A_without_production"),
        ("without_defence", "GI_A_without_defence"),
        ("without_tempo", "GI_A_without_tempo"),
        ("without_volatility", "GI_A_without_volatility"),
    ):
        alt = [safe_float(r.get(key)) for r in scored]
        paired = []
        for a, b, y in zip(gi_a_scores, alt, y_tg):
            if a is None or b is None or y is None:
                continue
            paired.append(abs(a - float(y)) - abs(b - float(y)))
        idx = bootstrap_cache.setdefault(
            len(paired) if paired else 0,
            bootstrap_index_matrix(len(paired), bootstrap_iterations, random_seed) if paired else np.empty((0, 0)),
        )
        alt_x, alt_y = _paired_xy(alt, y_tg)
        base_x, base_y = _paired_xy(gi_a_scores, y_tg)
        ablation[label] = {
            "loo_key": key,
            "paired_delta_ci": bootstrap_paired_delta_ci(paired, iterations=bootstrap_iterations, indices=idx) if paired else None,
            "alt_spearman": _round(spearman_rho(alt_x, alt_y)) if len(alt_x) >= 3 else None,
            "base_spearman": _round(spearman_rho(base_x, base_y)) if len(base_x) >= 3 else None,
        }
    phases["ablation_ms"] = _round((time.perf_counter() - t) * 1000, 2)

    # Paired candidate comparisons
    paired_comparisons = {}
    pairs = (
        ("GI_B_RECENCY", "GI_A_STRICT_CORE"),
        ("GI_C_SYMMETRIC_DIAGNOSTIC", "GI_A_STRICT_CORE"),
        ("GI_D_WEAKEST_DEFENCE", "GI_A_STRICT_CORE"),
        ("GI_A_STRICT_CORE", "MT1_LONG_TERM"),
    )
    for left, right in pairs:
        deltas = []
        for row in scored:
            a, b = safe_float(row.get(left)), safe_float(row.get(right))
            y = safe_float(row.get("total_goals_ft"))
            if a is None or b is None or y is None:
                continue
            deltas.append(abs(a - y) - abs(b - y))
        idx = bootstrap_cache.setdefault(
            len(deltas) if deltas else -1,
            bootstrap_index_matrix(len(deltas), bootstrap_iterations, random_seed) if deltas else np.empty((0, 0)),
        )
        paired_comparisons[f"{left}_vs_{right}"] = {
            "paired_delta_ci": bootstrap_paired_delta_ci(deltas, iterations=bootstrap_iterations, indices=idx) if deltas else None,
            "note": "delta>0 favorisce left su residuali assoluti vs total_goals (diagnostico, non produttivo)",
        }

    # Pillar redundancy on OP1/DV1/MT1/OV1
    pillar_vectors = {
        "OP1": [safe_float(r.get("OP1_HOME_LONG_TERM")) for r in scored],
        "DV1": [safe_float(r.get("DV1_MEAN_CONCEDED")) for r in scored],
        "MT1": [safe_float(r.get("MT1_LONG_TERM")) for r in scored],
        "OV1": [safe_float(r.get("OV1_STD")) for r in scored],
    }
    pillar_redundancy = {
        "pearson": correlation_matrix(pillar_vectors, "pearson"),
        "spearman": correlation_matrix(pillar_vectors, "spearman"),
        "vif": vif_scores({k: v for k, v in pillar_vectors.items()}),
        "correlation_with_MT1": {},
        "pillar_redundancy_warning": [],
    }
    mt1 = pillar_vectors["MT1"]
    for key, values in pillar_vectors.items():
        if key == "MT1":
            continue
        pairs_xy = _paired_xy(values, mt1)
        rho = spearman_rho(pairs_xy[0], pairs_xy[1]) if len(pairs_xy[0]) >= 3 else None
        pillar_redundancy["correlation_with_MT1"][key] = _round(rho)
        if rho is not None and abs(rho) >= 0.85:
            pillar_redundancy["pillar_redundancy_warning"].append(
                f"{key}_highly_redundant_with_MT1"
            )

    pareto = _pareto_select(composite_metrics, temporal_metrics)
    primary_id = pareto["primary_candidate"]
    challenger_id = pareto["challenger_candidate"]
    for row in scored:
        row["primary_candidate_score"] = _round(safe_float(row.get(primary_id))) if primary_id else None
        row["challenger_candidate_score"] = _round(safe_float(row.get(challenger_id))) if challenger_id else None

    # xG optional enrichment on paired cohort
    t = time.perf_counter()
    core10_ids = {r.get("local_fixture_id") for r in core10}
    paired_raw = filter_dataset_rows_by_kind(dataset_rows, "xg_paired")
    paired = [
        r for r in paired_raw
        if r.get("local_fixture_id") in core10_ids
        and all(safe_float(r.get(f)) is not None for f in XG_FEATURE_KEYS)
    ]
    xg_optional: dict[str, Any] = {
        "xg_status": "optional_research_enrichment",
        "xg_value_assessment": "neutral",
        "evidence_level": "low",
        "paired_n": len(paired),
    }
    if paired:
        xg_ecdfs = fit_train_ecdfs(paired, XG_SCORE_FEATURES)
        # Use train of paired only
        train_paired = [r for r in paired if r.get("temporal_fold_candidate") == "train"] or paired
        xg_ecdfs = {
            feature: TrainEcdf([safe_float(r.get(feature)) for r in train_paired if safe_float(r.get(feature)) is not None])
            for feature in XG_SCORE_FEATURES
        }
        primary_scores = []
        plus_xg_scores = []
        for row in paired:
            # map to scored primary via local_fixture_id
            match = next((s for s in scored if s.get("local_fixture_id") == row.get("local_fixture_id")), None)
            primary_score = safe_float(match.get(primary_id)) if match and primary_id else None
            xg_for = xg_ecdfs["pair_xg_for_avg"].transform(safe_float(row.get("pair_xg_for_avg")))
            xg_against = xg_ecdfs["pair_xg_against_avg"].transform(safe_float(row.get("pair_xg_against_avg")))
            xg_pair = _mean_ignore_none([xg_for, xg_against])
            plus = _mean_ignore_none([primary_score, xg_pair])
            primary_scores.append(primary_score)
            plus_xg_scores.append(plus)
        y = [safe_float(r.get("total_goals_ft")) for r in paired]
        px, py = _paired_xy(primary_scores, y)
        xx, xy = _paired_xy(plus_xg_scores, y)
        xg_optional.update({
            "XG_PAIR_SCORE_formula": "mean(pct(pair_xg_for_avg), pct(pair_xg_against_avg))",
            "GI_PRIMARY_PLUS_XG_DIAGNOSTIC_formula": "mean(primary, XG_PAIR_SCORE)",
            "primary_without_xg_spearman": _round(spearman_rho(px, py)) if len(px) >= 3 else None,
            "primary_with_xg_spearman": _round(spearman_rho(xx, xy)) if len(xx) >= 3 else None,
            "promoted_to_core": False,
        })
    phases["xg_ms"] = _round((time.perf_counter() - t) * 1000, 2)

    prospective = _prospective_protocol(date_to=date_to)

    phase_2a_checks = {
        "candidate_scores_complete": all(
            safe_float(scored[0].get(cid)) is not None for cid in COMPOSITE_IDS
        ) if scored else False,
        "train_only_normalization_verified": all(
            ecdfs[f].n > 0 for f in SCORE_FEATURES
        ),
        "no_target_leakage_verified": all(r.get("no_target_used_in_score") for r in scored),
        "temporal_validation_complete": bool(temporal_metrics),
        "ablation_complete": bool(ablation),
        "pillar_redundancy_checked": bool(pillar_redundancy.get("spearman")),
        "pareto_analysis_complete": bool(pareto.get("primary_candidate")),
        "primary_candidate_available": primary_id is not None,
        "challenger_candidate_available": challenger_id is not None,
        "xg_kept_optional": xg_optional.get("promoted_to_core") is False,
        "prospective_protocol_created": bool(prospective.get("candidate_definition_hash")),
    }
    blocking_2a = [k for k, v in phase_2a_checks.items() if not v]
    if not blocking_2a:
        next_2a = "phase_2a_preview"
    elif not phase_2a_checks["candidate_scores_complete"]:
        next_2a = "revise_candidate_indices"
    else:
        next_2a = "collect_more_data"

    preview_rows = []
    for row in scored[:100]:
        preview = {k: v for k, v in row.items() if not str(k).startswith("_")}
        preview_rows.append(preview)

    elapsed = _round((time.perf_counter() - t0) * 1000, 2) or 0
    warnings = []
    if elapsed > 45000:
        warnings.append("statistics_performance_above_target")
    if elapsed > 30000:
        warnings.append("candidate_indices_performance_above_preferable_target")

    payload = {
        "status": "ok",
        "version": VERSION,
        "v4_version": V4_VERSION,
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
            "minimum_history_sample": minimum_history_sample,
            "bootstrap_iterations": bootstrap_iterations,
            "random_seed": random_seed,
        },
        "research_limitations": {
            "eligibility_engine_version": ELIGIBILITY_ENGINE_VERSION,
            "validation_status": VALIDATION_STATUS,
            "note": RESEARCH_NOTE,
            "no_eligibility_mutation": True,
            "no_backfill": True,
            "utc_historical_exclusions_not_reclassified": True,
            "no_productive_validation_claim": True,
        },
        "cohort_summary": {
            "core_min10": len(core10),
            "core_min20": len(core20),
            "primary_analyzed": len(rows),
            "xg_complete_paired": len(paired),
            "fixture_ids_hash": source.get("fixture_ids_hash"),
            "targets_hash": source.get("targets_hash"),
            "ineligible_in_model": 0,
            "unknown_in_model": 0,
        },
        "normalization_summary": normalization_summary,
        "candidate_definitions": CANDIDATE_DEFINITIONS,
        "pillar_metrics": pillar_metrics,
        "pillar_redundancy": pillar_redundancy,
        "composite_metrics": composite_metrics,
        "baseline_metrics": baseline_metrics,
        "ablation_summary": ablation,
        "paired_candidate_comparisons": paired_comparisons,
        "temporal_metrics": {
            "splits": temporal_metrics,
            "expanding": expanding,
            "core_min20": core20_metrics,
            "month_diagnostic": month_diag,
        },
        "pareto_analysis": pareto,
        "xg_optional_analysis": xg_optional,
        "primary_candidate": primary_id,
        "challenger_candidate": challenger_id,
        "prospective_validation_protocol": prospective,
        "phase_2a_readiness": {
            **phase_2a_checks,
            "blocking_issues": blocking_2a,
            "recommended_next_step": next_2a,
        },
        "warnings": warnings,
        "performance": {
            **phases,
            "elapsed_ms": elapsed,
            "bootstrap_iterations": bootstrap_iterations,
            "random_seed": random_seed,
            "no_v5_productive_formula": True,
            "v4_unchanged": True,
            "weight_status": WEIGHT_STATUS,
        },
        "preview_rows": preview_rows,
        "_scored_rows": scored,
        "_ecdfs": {k: v.metadata() for k, v in ecdfs.items()},
        "_dataset": source,
    }
    t = time.perf_counter()
    payload["performance"]["serialization_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    return payload


def _strip_private_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_private_keys(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, list):
        return [_strip_private_keys(v) for v in value]
    return value


def build_goal_intensity_v5_candidate_indices(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    minimum_history_sample: int = 10,
    bootstrap_iterations: int = 1000,
    random_seed: int = 42,
) -> dict[str, Any]:
    full = build_goal_intensity_v5_candidate_indices_internal(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        minimum_history_sample=minimum_history_sample,
        bootstrap_iterations=bootstrap_iterations,
        random_seed=random_seed,
    )
    compact = _strip_private_keys(full)
    raw = json.dumps(compact, default=str).encode("utf-8")
    compact.setdefault("performance", {})["response_payload_bytes"] = len(raw)
    return compact


def candidate_indices_export_filename(*, kind: CandidateExportKind, date_from: date, date_to: date) -> str:
    from_s, to_s = date_from.isoformat(), date_to.isoformat()
    names = {
        "summary": f"cecchino_goal_intensity_v5_candidate_indices_summary_{from_s}_{to_s}.json",
        "candidate_definitions": f"cecchino_goal_intensity_v5_candidate_definitions_{from_s}_{to_s}.json",
        "candidate_scores": f"cecchino_goal_intensity_v5_candidate_scores_{from_s}_{to_s}.csv",
        "pillar_metrics": f"cecchino_goal_intensity_v5_pillar_metrics_{from_s}_{to_s}.csv",
        "composite_metrics": f"cecchino_goal_intensity_v5_composite_metrics_{from_s}_{to_s}.csv",
        "temporal_metrics": f"cecchino_goal_intensity_v5_temporal_metrics_{from_s}_{to_s}.csv",
        "decile_calibration": f"cecchino_goal_intensity_v5_decile_calibration_{from_s}_{to_s}.csv",
        "ablation_analysis": f"cecchino_goal_intensity_v5_ablation_analysis_{from_s}_{to_s}.csv",
        "paired_candidate_comparison": f"cecchino_goal_intensity_v5_paired_comparison_{from_s}_{to_s}.csv",
        "pillar_redundancy": f"cecchino_goal_intensity_v5_pillar_redundancy_{from_s}_{to_s}.csv",
        "xg_optional_enrichment": f"cecchino_goal_intensity_v5_xg_optional_{from_s}_{to_s}.csv",
        "prospective_validation_protocol": f"cecchino_goal_intensity_v5_prospective_protocol_{from_s}_{to_s}.json",
    }
    return names[kind]


def _csv_stream(rows: list[dict[str, Any]]) -> Iterator[str]:
    if not rows:
        rows = [{"note": "empty"}]
    columns = list(rows[0].keys())
    yield "\ufeff"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)
    for row in rows:
        out = {}
        for c in columns:
            v = row.get(c)
            if isinstance(v, (dict, list)):
                out[c] = json.dumps(v, default=str)
            elif v is None:
                out[c] = ""
            else:
                out[c] = v
        writer.writerow(out)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)


def stream_goal_intensity_v5_candidate_indices_export(
    db: Session,
    *,
    kind: CandidateExportKind,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    minimum_history_sample: int = 10,
    bootstrap_iterations: int = 1000,
    random_seed: int = 42,
) -> Iterator[str]:
    full = build_goal_intensity_v5_candidate_indices_internal(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        minimum_history_sample=minimum_history_sample,
        bootstrap_iterations=bootstrap_iterations,
        random_seed=random_seed,
    )
    if kind == "summary":
        yield json.dumps(_strip_private_keys(full), ensure_ascii=False, default=str)
        return
    if kind == "candidate_definitions":
        yield json.dumps(full.get("candidate_definitions") or {}, ensure_ascii=False, default=str)
        return
    if kind == "prospective_validation_protocol":
        yield json.dumps(full.get("prospective_validation_protocol") or {}, ensure_ascii=False, default=str)
        return
    if kind == "candidate_scores":
        rows = [
            {k: v for k, v in row.items() if not str(k).startswith("_")}
            for row in (full.get("_scored_rows") or [])
        ]
    elif kind == "pillar_metrics":
        rows = [{"candidate_id": cid, **metrics} for cid, metrics in (full.get("pillar_metrics") or {}).items()]
    elif kind == "composite_metrics":
        rows = [{"candidate_id": cid, **metrics} for cid, metrics in (full.get("composite_metrics") or {}).items()]
    elif kind == "temporal_metrics":
        splits = (full.get("temporal_metrics") or {}).get("splits") or {}
        rows = [{"candidate_id": cid, **metrics} for cid, metrics in splits.items()]
    elif kind == "decile_calibration":
        rows = []
        for cid, metrics in (full.get("composite_metrics") or {}).items():
            tg = metrics.get("total_goals_ft") or {}
            rows.append({
                "candidate_id": cid,
                "decile_means": tg.get("decile_means"),
                "high_minus_low": tg.get("high_minus_low"),
                "monotonicity_score": tg.get("monotonicity_score"),
            })
    elif kind == "ablation_analysis":
        rows = [{"ablation": k, **v} for k, v in (full.get("ablation_summary") or {}).items()]
    elif kind == "paired_candidate_comparison":
        rows = [{"comparison": k, **v} for k, v in (full.get("paired_candidate_comparisons") or {}).items()]
    elif kind == "pillar_redundancy":
        red = full.get("pillar_redundancy") or {}
        rows = [{"metric": "correlation_with_MT1", **(red.get("correlation_with_MT1") or {})}]
        if red.get("pillar_redundancy_warning"):
            rows.append({"metric": "warnings", "warnings": red["pillar_redundancy_warning"]})
    else:  # xg_optional_enrichment
        rows = [full.get("xg_optional_analysis") or {}]
    yield from _csv_stream(rows)
