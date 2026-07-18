"""Intensità Goal v5 — Fase 1D/1D.1: indici candidati research (ECDF train-only).

Riusa il dataset Fase 1B; non modifica statistics v1_2, eligibility, né v4.
Score 0–100 invariati; v1_1 corregge solo calibrazione e valutazione.
Nessuna formula produttiva.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from datetime import date, datetime, timedelta, timezone
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

VERSION = "cecchino_goal_intensity_v5_candidate_indices_v1_1"
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

LOO_IDS = (
    "GI_A_without_production",
    "GI_A_without_defence",
    "GI_A_without_tempo",
    "GI_A_without_volatility",
)

EXPANDING_CANDIDATE_IDS = (
    "GI_A_STRICT_CORE",
    "GI_B_RECENCY",
    "GI_C_SYMMETRIC_DIAGNOSTIC",
    "GI_D_WEAKEST_DEFENCE",
    "MT1_LONG_TERM",
    *LOO_IDS,
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
    "calibrated_predictions",
    "temporal_fold_metrics",
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


def _aligned_rows(
    scored_rows: list[dict[str, Any]],
    score_key: str,
    target_key: str,
) -> list[dict[str, Any]]:
    out = []
    for row in scored_rows:
        score = safe_float(row.get(score_key))
        target = safe_float(row.get(target_key))
        if score is None or target is None:
            continue
        out.append({
            "local_fixture_id": row.get("local_fixture_id"),
            "split": row.get("split"),
            "score": score,
            "target": target,
            "is_train": row.get("split") == "train",
            "kickoff": row.get("kickoff"),
            "scan_date": row.get("scan_date"),
        })
    return out


def _fit_linear_calibration(
    train_scores: list[float],
    train_targets: list[float],
) -> dict[str, Any] | None:
    if len(train_scores) < 3:
        return None
    x_arr = np.asarray(train_scores, float).reshape(-1, 1)
    y_arr = np.asarray(train_targets, float)
    try:
        from sklearn.linear_model import LinearRegression

        model = LinearRegression().fit(x_arr, y_arr)
        intercept = float(model.intercept_)
        coefficient = float(model.coef_[0])
    except Exception:
        if np.std(x_arr) < 1e-12:
            intercept = float(np.mean(y_arr))
            coefficient = 0.0
        else:
            coefficient, intercept = [float(v) for v in np.polyfit(x_arr.ravel(), y_arr, 1)]
    return {
        "calibration_method": "train_linear_regression",
        "intercept": _round(intercept),
        "coefficient": _round(coefficient),
        "train_n": len(train_scores),
        "_predict": lambda scores: intercept + coefficient * np.asarray(scores, float),
    }


def _fit_logistic_calibration(
    train_scores: list[float],
    train_targets: list[float],
) -> dict[str, Any] | None:
    y = np.asarray(train_targets, float)
    if len(train_scores) < 5 or len(np.unique(y)) < 2:
        return None
    x_arr = np.asarray(train_scores, float).reshape(-1, 1)
    try:
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(max_iter=1000, solver="lbfgs")
        model.fit(x_arr, y.astype(int))
        intercept = float(model.intercept_[0])
        coefficient = float(model.coef_[0][0])

        def predict_proba(scores: list[float] | np.ndarray) -> np.ndarray:
            probs = model.predict_proba(np.asarray(scores, float).reshape(-1, 1))[:, 1]
            return np.clip(probs, 1e-6, 1.0 - 1e-6)
    except Exception:
        return None
    return {
        "calibration_method": "train_logistic_regression",
        "intercept": _round(intercept),
        "coefficient": _round(coefficient),
        "train_n": len(train_scores),
        "train_positive_rate": _round(float(np.mean(y))),
        "_predict_proba": predict_proba,
    }


def _mae_rmse(preds: np.ndarray, actuals: np.ndarray) -> tuple[float | None, float | None]:
    if len(preds) == 0:
        return None, None
    err = preds - actuals
    return _round(float(np.mean(np.abs(err)))), _round(float(np.sqrt(np.mean(err ** 2))))


def _brier_logloss(probs: np.ndarray, actuals: np.ndarray) -> tuple[float | None, float | None, float | None]:
    if len(probs) == 0:
        return None, None, None
    y = actuals.astype(float)
    p = np.clip(probs.astype(float), 1e-6, 1.0 - 1e-6)
    brier = float(np.mean((p - y) ** 2))
    logloss = float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))
    calib_err = float(np.mean(np.abs(p - y)))
    return _round(brier), _round(logloss), _round(calib_err)


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


def _calibrate_and_evaluate(
    scored_rows: list[dict[str, Any]],
    score_key: str,
    *,
    bootstrap_iterations: int,
    random_seed: int,
    bootstrap_cache: dict[int, np.ndarray],
    collect_predictions: bool = False,
    fold_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Metriche con calibrazione train-only; Brier/logloss mai su score/100."""
    from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import auc_mann_whitney

    result: dict[str, Any] = {
        "score_key": score_key,
        "n": sum(1 for r in scored_rows if safe_float(r.get(score_key)) is not None),
    }
    predictions: list[dict[str, Any]] = []

    # --- continuous total_goals_ft ---
    aligned_tg = _aligned_rows(scored_rows, score_key, "total_goals_ft")
    if len(aligned_tg) >= 3:
        scores = [r["score"] for r in aligned_tg]
        targets = [r["target"] for r in aligned_tg]
        train_scores = [r["score"] for r in aligned_tg if r["is_train"]]
        train_targets = [r["target"] for r in aligned_tg if r["is_train"]]
        cal = _fit_linear_calibration(train_scores, train_targets)
        idx = bootstrap_cache.setdefault(
            len(scores), bootstrap_index_matrix(len(scores), bootstrap_iterations, random_seed)
        )
        spearman = bootstrap_spearman_ci(
            scores, targets, iterations=bootstrap_iterations, seed=random_seed, indices=idx
        )
        tg_block: dict[str, Any] = {
            "pearson": _round(pearson_r(scores, targets)),
            "spearman": spearman.get("spearman"),
            "spearman_bootstrap": spearman,
            **_decile_stats(scores, targets),
        }
        if cal is not None:
            preds = cal["_predict"](scores)
            mae, rmse = _mae_rmse(preds, np.asarray(targets, float))
            tg_block.update({
                "calibration_method": cal["calibration_method"],
                "intercept": cal["intercept"],
                "coefficient": cal["coefficient"],
                "train_n": cal["train_n"],
                "prediction_min": _round(float(np.min(preds))),
                "prediction_max": _round(float(np.max(preds))),
                "mae": mae,
                "rmse": rmse,
                "uses_score_over_100_as_probability": False,
            })
            if collect_predictions:
                for row, pred in zip(aligned_tg, preds):
                    actual = float(row["target"])
                    predictions.append({
                        "local_fixture_id": row["local_fixture_id"],
                        "split": row["split"],
                        "candidate": score_key,
                        "target": "total_goals_ft",
                        "raw_score": _round(row["score"]),
                        "calibrated_prediction": _round(float(pred)),
                        "actual_target": actual,
                        "absolute_error": _round(abs(float(pred) - actual)),
                        "squared_error": _round((float(pred) - actual) ** 2),
                        "probability": None,
                        "brier_component": None,
                        "fold_id": fold_id,
                    })
        else:
            tg_block.update({"mae": None, "rmse": None, "calibration_method": None})
        result["total_goals_ft"] = tg_block
        result["_linear_cal"] = cal
        result["_aligned_tg"] = aligned_tg

    # --- binary targets ---
    for target in BINARY_TARGETS:
        aligned = _aligned_rows(scored_rows, score_key, target)
        if len(aligned) < 5:
            continue
        scores = [r["score"] for r in aligned]
        targets = [r["target"] for r in aligned]
        train_scores = [r["score"] for r in aligned if r["is_train"]]
        train_targets = [r["target"] for r in aligned if r["is_train"]]
        cal = _fit_logistic_calibration(train_scores, train_targets)
        binary = np.asarray(targets, float)
        values = np.asarray(scores, float)
        idx = bootstrap_cache.setdefault(
            len(scores), bootstrap_index_matrix(len(scores), bootstrap_iterations, random_seed)
        )
        auc_ci = bootstrap_auc_ci(binary, values, idx)
        auc_raw = auc_mann_whitney(binary.astype(int).tolist(), scores)
        block: dict[str, Any] = {
            "auc": _round(auc_raw),
            "auc_bootstrap": auc_ci,
            "auc_on": "raw_score_rank_based",
            "uses_score_over_100_as_probability": False,
            **{k: v for k, v in _decile_stats(scores, targets).items() if k.startswith("monotonic")},
            "rate_per_decile": _decile_stats(scores, targets).get("decile_means"),
        }
        if cal is not None:
            probs = cal["_predict_proba"](scores)
            brier, logloss, calib_err = _brier_logloss(probs, binary)
            block.update({
                "calibration_method": cal["calibration_method"],
                "coefficient": cal["coefficient"],
                "intercept": cal["intercept"],
                "train_n": cal["train_n"],
                "train_positive_rate": cal["train_positive_rate"],
                "brier": brier,
                "log_loss": logloss,
                "calibration_error": calib_err,
            })
            if collect_predictions:
                for row, prob in zip(aligned, probs):
                    actual = float(row["target"])
                    p = float(prob)
                    predictions.append({
                        "local_fixture_id": row["local_fixture_id"],
                        "split": row["split"],
                        "candidate": score_key,
                        "target": target,
                        "raw_score": _round(row["score"]),
                        "calibrated_prediction": _round(p),
                        "actual_target": actual,
                        "absolute_error": None,
                        "squared_error": None,
                        "probability": _round(p),
                        "brier_component": _round((p - actual) ** 2),
                        "fold_id": fold_id,
                    })
        else:
            block.update({"brier": None, "log_loss": None, "calibration_method": None})
        result[target] = block
        result[f"_logistic_cal_{target}"] = cal
        result[f"_aligned_{target}"] = aligned

    return result, predictions


def evaluate_score_metrics(
    scored_rows: list[dict[str, Any]],
    score_key: str,
    *,
    bootstrap_iterations: int,
    random_seed: int,
    bootstrap_cache: dict[int, np.ndarray],
) -> dict[str, Any]:
    metrics, _ = _calibrate_and_evaluate(
        scored_rows,
        score_key,
        bootstrap_iterations=bootstrap_iterations,
        random_seed=random_seed,
        bootstrap_cache=bootstrap_cache,
        collect_predictions=False,
    )
    return {k: v for k, v in metrics.items() if not str(k).startswith("_")}


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


def _ci_includes_zero(ci: dict[str, Any] | None) -> bool:
    if not ci:
        return True
    lo, hi = ci.get("ci_lower"), ci.get("ci_upper")
    if lo is None or hi is None:
        return True
    return float(lo) <= 0.0 <= float(hi)


def _assessment_from_deltas(
    *,
    delta_mae_ci: dict[str, Any] | None,
    delta_spearman_ci: dict[str, Any] | None,
    delta_auc_ci: dict[str, Any] | None,
) -> tuple[str, str]:
    """Assessment left vs right: MAE delta<0 e AUC/Spearman delta>0 favoriscono left."""
    left_better = 0
    right_better = 0
    inconclusive = 0
    for ci, left_if_negative in (
        (delta_mae_ci, True),
        (delta_spearman_ci, False),
        (delta_auc_ci, False),
    ):
        if not ci or ci.get("mean") is None:
            continue
        if _ci_includes_zero(ci):
            inconclusive += 1
            continue
        mean = float(ci["mean"])
        if left_if_negative:
            if mean < 0:
                left_better += 1
            else:
                right_better += 1
        else:
            if mean > 0:
                left_better += 1
            else:
                right_better += 1
    total = left_better + right_better + inconclusive
    if total == 0:
        return "inconclusive", "low"
    if left_better > 0 and right_better == 0 and inconclusive == 0:
        return "positive", "strong" if left_better >= 2 else "moderate"
    if right_better > 0 and left_better == 0 and inconclusive == 0:
        return "negative", "strong" if right_better >= 2 else "moderate"
    if left_better > right_better:
        return "positive", "low"
    if right_better > left_better:
        return "negative", "low"
    if left_better == 0 and right_better == 0:
        return "neutral", "low"
    return "inconclusive", "low"


def _paired_calibrated_comparison(
    scored_rows: list[dict[str, Any]],
    left_key: str,
    right_key: str,
    *,
    bootstrap_iterations: int,
    random_seed: int,
    bootstrap_cache: dict[int, np.ndarray],
) -> dict[str, Any]:
    """Confronta predizioni calibrate; mai score 0–100 vs goal 0–11."""
    from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import auc_mann_whitney

    left_m, _ = _calibrate_and_evaluate(
        scored_rows, left_key,
        bootstrap_iterations=bootstrap_iterations, random_seed=random_seed,
        bootstrap_cache=bootstrap_cache,
    )
    right_m, _ = _calibrate_and_evaluate(
        scored_rows, right_key,
        bootstrap_iterations=bootstrap_iterations, random_seed=random_seed,
        bootstrap_cache=bootstrap_cache,
    )
    out: dict[str, Any] = {
        "left": left_key,
        "right": right_key,
        "dimensionally_valid": True,
        "uses_raw_score_vs_goals": False,
        "direction_notes": {
            "delta_mae": "delta<0 favorisce left",
            "delta_rmse": "delta<0 favorisce left",
            "delta_spearman": "delta>0 favorisce left",
            "delta_auc": "delta>0 favorisce left",
            "delta_brier": "delta<0 favorisce left",
            "delta_log_loss": "delta<0 favorisce left",
        },
    }

    # total goals: per-row AE/SE from calibrated preds on shared fixtures
    left_aligned = left_m.get("_aligned_tg") or []
    right_aligned = right_m.get("_aligned_tg") or []
    left_cal = left_m.get("_linear_cal")
    right_cal = right_m.get("_linear_cal")
    left_by_id = {r["local_fixture_id"]: r for r in left_aligned}
    right_by_id = {r["local_fixture_id"]: r for r in right_aligned}
    shared_ids = [i for i in left_by_id if i in right_by_id]
    if left_cal and right_cal and shared_ids:
        ae_deltas, se_deltas = [], []
        left_scores, right_scores, targets = [], [], []
        for fid in shared_ids:
            lr, rr = left_by_id[fid], right_by_id[fid]
            lp = float(left_cal["_predict"]([lr["score"]])[0])
            rp = float(right_cal["_predict"]([rr["score"]])[0])
            y = float(lr["target"])
            ae_deltas.append(abs(lp - y) - abs(rp - y))
            se_deltas.append((lp - y) ** 2 - (rp - y) ** 2)
            left_scores.append(lr["score"])
            right_scores.append(rr["score"])
            targets.append(y)
        idx = bootstrap_cache.setdefault(
            len(ae_deltas),
            bootstrap_index_matrix(len(ae_deltas), bootstrap_iterations, random_seed),
        )
        mae_ci = bootstrap_paired_delta_ci(ae_deltas, iterations=bootstrap_iterations, indices=idx)
        # RMSE delta = sqrt(mean SE_left) - sqrt(mean SE_right) approximated via paired SE means
        rmse_left = float(np.sqrt(np.mean([(lp) for lp in [
            (float(left_cal["_predict"]([left_by_id[fid]["score"]])[0]) - float(left_by_id[fid]["target"])) ** 2
            for fid in shared_ids
        ]])))
        rmse_right = float(np.sqrt(np.mean([
            (float(right_cal["_predict"]([right_by_id[fid]["score"]])[0]) - float(right_by_id[fid]["target"])) ** 2
            for fid in shared_ids
        ])))
        se_ci = bootstrap_paired_delta_ci(se_deltas, iterations=bootstrap_iterations, indices=idx)
        rho_l = spearman_rho(left_scores, targets)
        rho_r = spearman_rho(right_scores, targets)
        delta_spearman = (rho_l - rho_r) if rho_l is not None and rho_r is not None else None
        spearman_deltas = []
        # bootstrap delta spearman on shared indices
        if len(shared_ids) >= 5:
            rng_idx = idx
            for row_idx in rng_idx:
                ls = [left_scores[i] for i in row_idx]
                rs = [right_scores[i] for i in row_idx]
                ys = [targets[i] for i in row_idx]
                rl, rr = spearman_rho(ls, ys), spearman_rho(rs, ys)
                if rl is not None and rr is not None:
                    spearman_deltas.append(rl - rr)
        spearman_ci = {
            "mean": _round(delta_spearman),
            "ci_lower": _round(float(np.quantile(spearman_deltas, 0.025))) if spearman_deltas else None,
            "ci_upper": _round(float(np.quantile(spearman_deltas, 0.975))) if spearman_deltas else None,
            "valid_bootstrap_iterations": len(spearman_deltas),
        }
        out["total_goals_ft"] = {
            "delta_mae": mae_ci.get("mean"),
            "delta_mae_ci": mae_ci,
            "delta_rmse": _round(rmse_left - rmse_right),
            "delta_rmse_ci": {
                "mean": _round(rmse_left - rmse_right),
                "ci_lower": _round(float(np.quantile(
                    [float(np.sqrt(np.mean([
                        (float(left_cal["_predict"]([left_by_id[shared_ids[i]]["score"]])[0])
                        - float(left_by_id[shared_ids[i]]["target"])) ** 2
                        for i in row_idx
                    ]))) - float(np.sqrt(np.mean([
                        (float(right_cal["_predict"]([right_by_id[shared_ids[i]]["score"]])[0])
                        - float(right_by_id[shared_ids[i]]["target"])) ** 2
                        for i in row_idx
                    ])))
                    for row_idx in idx
                ], 0.025))) if len(shared_ids) >= 5 else None,
                "ci_upper": _round(float(np.quantile(
                    [float(np.sqrt(np.mean([
                        (float(left_cal["_predict"]([left_by_id[shared_ids[i]]["score"]])[0])
                        - float(left_by_id[shared_ids[i]]["target"])) ** 2
                        for i in row_idx
                    ]))) - float(np.sqrt(np.mean([
                        (float(right_cal["_predict"]([right_by_id[shared_ids[i]]["score"]])[0])
                        - float(right_by_id[shared_ids[i]]["target"])) ** 2
                        for i in row_idx
                    ])))
                    for row_idx in idx
                ], 0.975))) if len(shared_ids) >= 5 else None,
                "note": "paired_bootstrap_on_rmse_difference",
                "se_delta_ci": se_ci,
            },
            "delta_spearman": _round(delta_spearman),
            "delta_spearman_ci": spearman_ci,
            "n_paired": len(shared_ids),
        }

    for target in BINARY_TARGETS:
        la = left_m.get(f"_aligned_{target}") or []
        ra = right_m.get(f"_aligned_{target}") or []
        lc = left_m.get(f"_logistic_cal_{target}")
        rc = right_m.get(f"_logistic_cal_{target}")
        lb = {r["local_fixture_id"]: r for r in la}
        rb = {r["local_fixture_id"]: r for r in ra}
        shared = [i for i in lb if i in rb]
        if not lc or not rc or len(shared) < 5:
            continue
        brier_deltas, logloss_deltas = [], []
        left_scores, right_scores, ys = [], [], []
        for fid in shared:
            lr, rr = lb[fid], rb[fid]
            lp = float(lc["_predict_proba"]([lr["score"]])[0])
            rp = float(rc["_predict_proba"]([rr["score"]])[0])
            y = float(lr["target"])
            brier_deltas.append((lp - y) ** 2 - (rp - y) ** 2)
            # per-row logloss contribution delta
            lp_c = min(max(lp, 1e-6), 1 - 1e-6)
            rp_c = min(max(rp, 1e-6), 1 - 1e-6)
            ll_l = -(y * np.log(lp_c) + (1 - y) * np.log(1 - lp_c))
            ll_r = -(y * np.log(rp_c) + (1 - y) * np.log(1 - rp_c))
            logloss_deltas.append(float(ll_l - ll_r))
            left_scores.append(lr["score"])
            right_scores.append(rr["score"])
            ys.append(y)
        idx = bootstrap_cache.setdefault(
            len(shared),
            bootstrap_index_matrix(len(shared), bootstrap_iterations, random_seed),
        )
        auc_l = auc_mann_whitney([int(v) for v in ys], left_scores)
        auc_r = auc_mann_whitney([int(v) for v in ys], right_scores)
        auc_deltas = []
        for row_idx in idx:
            ys_b = [ys[i] for i in row_idx]
            ls_b = [left_scores[i] for i in row_idx]
            rs_b = [right_scores[i] for i in row_idx]
            if len(set(int(v) for v in ys_b)) < 2:
                continue
            al = auc_mann_whitney([int(v) for v in ys_b], ls_b)
            ar = auc_mann_whitney([int(v) for v in ys_b], rs_b)
            if al is not None and ar is not None:
                auc_deltas.append(al - ar)
        out[target] = {
            "delta_auc": _round((auc_l or 0) - (auc_r or 0)) if auc_l is not None and auc_r is not None else None,
            "delta_auc_ci": {
                "mean": _round(float(np.mean(auc_deltas))) if auc_deltas else None,
                "ci_lower": _round(float(np.quantile(auc_deltas, 0.025))) if auc_deltas else None,
                "ci_upper": _round(float(np.quantile(auc_deltas, 0.975))) if auc_deltas else None,
                "valid_bootstrap_iterations": len(auc_deltas),
            },
            "delta_brier": _round(float(np.mean(brier_deltas))),
            "delta_brier_ci": bootstrap_paired_delta_ci(
                brier_deltas, iterations=bootstrap_iterations, indices=idx
            ),
            "delta_log_loss": _round(float(np.mean(logloss_deltas))),
            "delta_log_loss_ci": bootstrap_paired_delta_ci(
                logloss_deltas, iterations=bootstrap_iterations, indices=idx
            ),
            "n_paired": len(shared),
        }

    tg = out.get("total_goals_ft") or {}
    ge2 = out.get("goals_ge_2") or {}
    assessment, evidence = _assessment_from_deltas(
        delta_mae_ci=tg.get("delta_mae_ci"),
        delta_spearman_ci=tg.get("delta_spearman_ci"),
        delta_auc_ci=ge2.get("delta_auc_ci"),
    )
    out["comparison_assessment"] = assessment
    out["evidence_level"] = evidence
    return out


def _expanding_fold_metrics(
    rows: list[dict[str, Any]],
    *,
    bootstrap_iterations: int,
    random_seed: int,
) -> dict[str, Any]:
    """Expanding CV: ECDF+score+calibrazione rifittati per fold su tutti i candidati richiesti."""
    from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import auc_mann_whitney

    ordered = sorted(rows, key=lambda r: str(r.get("kickoff") or ""))
    if len(ordered) < 30:
        return {
            "status": "insufficient_sample_for_3_temporal_folds",
            "folds": [],
            "candidates": {},
            "fold_rows": [],
        }

    fold_defs: list[tuple[list[dict[str, Any]], list[dict[str, Any]], str, str, str, str]] = []
    step = max(1, len(ordered) // 4)
    for end in range(max(12, len(ordered) // 3), len(ordered) - 4, step):
        train = ordered[:end]
        val = ordered[end : min(len(ordered), end + max(4, len(ordered) // 6))]
        if len(val) < 4:
            continue
        train_start = str(train[0].get("kickoff") or "")
        train_end = str(train[-1].get("kickoff") or "")
        val_start = str(val[0].get("kickoff") or "")
        val_end = str(val[-1].get("kickoff") or "")
        fold_defs.append((train, val, train_start, train_end, val_start, val_end))
        if len(fold_defs) >= 3 and end > len(ordered) * 0.7:
            break
    if len(fold_defs) < 3:
        return {
            "status": "insufficient_sample_for_3_temporal_folds",
            "folds": [],
            "candidates": {},
            "fold_rows": [],
        }

    fold_rows_export: list[dict[str, Any]] = []
    per_candidate_folds: dict[str, list[dict[str, Any]]] = {cid: [] for cid in EXPANDING_CANDIDATE_IDS}

    for fold_i, (train, val, train_start, train_end, val_start, val_end) in enumerate(fold_defs):
        fold_id = f"expanding_{fold_i}"
        ecdfs = {
            feature: TrainEcdf(
                [safe_float(r.get(feature)) for r in train if safe_float(r.get(feature)) is not None]
            )
            for feature in SCORE_FEATURES
        }
        scored_train = []
        for row, pct in zip(train, apply_ecdfs(train, ecdfs)):
            pillar = _pillar_scores_from_pct(pct)
            composite = _composite_scores(pillar)
            loo = _loo_composites(pillar)
            scored_train.append({
                "local_fixture_id": row.get("local_fixture_id"),
                "split": "train",
                "kickoff": row.get("kickoff"),
                **{k: _round(v) for k, v in pillar.items()},
                **{k: _round(v) for k, v in composite.items()},
                **{f"GI_A_{k}": _round(v) for k, v in loo.items()},
                "total_goals_ft": row.get("total_goals_ft"),
                "goals_ge_2": int(bool(row.get("goals_ge_2"))),
                "goals_ge_3": int(bool(row.get("goals_ge_3"))),
                "btts_ft": int(bool(row.get("btts_ft"))),
            })
        scored_val = []
        for row, pct in zip(val, apply_ecdfs(val, ecdfs)):
            pillar = _pillar_scores_from_pct(pct)
            composite = _composite_scores(pillar)
            loo = _loo_composites(pillar)
            scored_val.append({
                "local_fixture_id": row.get("local_fixture_id"),
                "split": "validation",
                "kickoff": row.get("kickoff"),
                **{k: _round(v) for k, v in pillar.items()},
                **{k: _round(v) for k, v in composite.items()},
                **{f"GI_A_{k}": _round(v) for k, v in loo.items()},
                "total_goals_ft": row.get("total_goals_ft"),
                "goals_ge_2": int(bool(row.get("goals_ge_2"))),
                "goals_ge_3": int(bool(row.get("goals_ge_3"))),
                "btts_ft": int(bool(row.get("btts_ft"))),
            })
        combined = scored_train + scored_val

        for cid in EXPANDING_CANDIDATE_IDS:
            train_scores = [safe_float(r.get(cid)) for r in scored_train]
            train_tg = [safe_float(r.get("total_goals_ft")) for r in scored_train]
            pairs_train = [(s, y) for s, y in zip(train_scores, train_tg) if s is not None and y is not None]
            lin = _fit_linear_calibration(
                [p[0] for p in pairs_train], [p[1] for p in pairs_train]
            ) if pairs_train else None

            val_scores = [safe_float(r.get(cid)) for r in scored_val]
            val_tg = [safe_float(r.get("total_goals_ft")) for r in scored_val]
            pairs_val = [(s, y) for s, y in zip(val_scores, val_tg) if s is not None and y is not None]
            spearman = spearman_rho([p[0] for p in pairs_val], [p[1] for p in pairs_val]) if len(pairs_val) >= 3 else None
            mae = rmse = None
            if lin is not None and pairs_val:
                preds = lin["_predict"]([p[0] for p in pairs_val])
                mae, rmse = _mae_rmse(preds, np.asarray([p[1] for p in pairs_val], float))

            fold_metrics: dict[str, Any] = {
                "fold_id": fold_id,
                "candidate": cid,
                "train_start": train_start,
                "train_end": train_end,
                "validation_start": val_start,
                "validation_end": val_end,
                "train_n": len(scored_train),
                "validation_n": len(scored_val),
                "spearman_total_goals": _round(spearman),
                "mae": mae,
                "rmse": rmse,
            }

            for target in BINARY_TARGETS:
                t_train = [
                    (safe_float(r.get(cid)), safe_float(r.get(target)))
                    for r in scored_train
                ]
                t_train = [(s, y) for s, y in t_train if s is not None and y is not None]
                log = _fit_logistic_calibration(
                    [p[0] for p in t_train], [p[1] for p in t_train]
                ) if t_train else None
                t_val = [
                    (safe_float(r.get(cid)), safe_float(r.get(target)))
                    for r in scored_val
                ]
                t_val = [(s, y) for s, y in t_val if s is not None and y is not None]
                auc = brier = None
                if len(t_val) >= 5 and len({int(p[1]) for p in t_val}) >= 2:
                    auc = auc_mann_whitney(
                        [int(p[1]) for p in t_val], [p[0] for p in t_val]
                    )
                if log is not None and t_val:
                    probs = log["_predict_proba"]([p[0] for p in t_val])
                    brier, _, _ = _brier_logloss(probs, np.asarray([p[1] for p in t_val], float))
                fold_metrics[f"auc_{target}"] = _round(auc)
                fold_metrics[f"brier_{target}"] = brier
                fold_rows_export.append({
                    "candidate": cid,
                    "fold_id": fold_id,
                    "target": target,
                    "train_start": train_start,
                    "train_end": train_end,
                    "validation_start": val_start,
                    "validation_end": val_end,
                    "train_n": len(scored_train),
                    "validation_n": len(scored_val),
                    "auc": _round(auc),
                    "brier": brier,
                    "spearman": None,
                    "mae": None,
                    "rmse": None,
                })

            fold_rows_export.append({
                "candidate": cid,
                "fold_id": fold_id,
                "target": "total_goals_ft",
                "train_start": train_start,
                "train_end": train_end,
                "validation_start": val_start,
                "validation_end": val_end,
                "train_n": len(scored_train),
                "validation_n": len(scored_val),
                "auc": None,
                "brier": None,
                "spearman": _round(spearman),
                "mae": mae,
                "rmse": rmse,
            })
            per_candidate_folds[cid].append(fold_metrics)

    # Aggregates + rank stability on spearman
    candidates_out: dict[str, Any] = {}
    for cid, folds in per_candidate_folds.items():
        if not folds:
            continue
        def _agg(key: str) -> dict[str, Any]:
            vals = [f[key] for f in folds if f.get(key) is not None]
            if not vals:
                return {"mean": None, "std": None, "min": None, "max": None}
            arr = np.asarray(vals, float)
            return {
                "mean": _round(float(np.mean(arr))),
                "std": _round(float(np.std(arr))) if len(arr) > 1 else 0.0,
                "min": _round(float(np.min(arr))),
                "max": _round(float(np.max(arr))),
            }

        rhos = [f["spearman_total_goals"] for f in folds if f.get("spearman_total_goals") is not None]
        signs = [1 if r > 0 else -1 if r < 0 else 0 for r in rhos]
        candidates_out[cid] = {
            "folds": folds,
            "spearman_total_goals": _agg("spearman_total_goals"),
            "mae": _agg("mae"),
            "rmse": _agg("rmse"),
            "auc_goals_ge_2": _agg("auc_goals_ge_2"),
            "brier_goals_ge_2": _agg("brier_goals_ge_2"),
            "auc_goals_ge_3": _agg("auc_goals_ge_3"),
            "brier_goals_ge_3": _agg("brier_goals_ge_3"),
            "auc_btts_ft": _agg("auc_btts_ft"),
            "brier_btts_ft": _agg("brier_btts_ft"),
            "direction_consistent": direction_consistent(signs) if signs else False,
        }

    # Rank per fold by spearman (higher better)
    fold_count = len(fold_defs)
    for fold_i in range(fold_count):
        ranking = []
        for cid, folds in per_candidate_folds.items():
            if fold_i < len(folds) and folds[fold_i].get("spearman_total_goals") is not None:
                ranking.append((cid, folds[fold_i]["spearman_total_goals"]))
        ranking.sort(key=lambda x: x[1], reverse=True)
        for rank, (cid, _) in enumerate(ranking, start=1):
            per_candidate_folds[cid][fold_i]["rank_spearman"] = rank
            candidates_out[cid]["folds"][fold_i]["rank_spearman"] = rank

    for cid, folds in per_candidate_folds.items():
        ranks = [f.get("rank_spearman") for f in folds if f.get("rank_spearman") is not None]
        if ranks:
            candidates_out[cid]["rank_stability"] = {
                "mean_rank": _round(float(np.mean(ranks))),
                "std_rank": _round(float(np.std(ranks))) if len(ranks) > 1 else 0.0,
                "ranks": ranks,
            }
        else:
            candidates_out[cid]["rank_stability"] = {"mean_rank": None, "std_rank": None, "ranks": []}

    all_candidates_ok = all(cid in candidates_out for cid in EXPANDING_CANDIDATE_IDS)
    all_targets_ok = all(
        candidates_out.get(cid, {}).get("auc_goals_ge_2", {}).get("mean") is not None
        or candidates_out.get(cid, {}).get("spearman_total_goals", {}).get("mean") is not None
        for cid in EXPANDING_CANDIDATE_IDS
    ) and all(
        any(fr.get("target") == t for fr in fold_rows_export)
        for t in ALL_TARGETS
    )

    return {
        "status": "ok",
        "fold_count": fold_count,
        "candidates": candidates_out,
        "fold_rows": fold_rows_export,
        "all_candidates_present": all_candidates_ok,
        "all_targets_present": all_targets_ok,
        "ecdf_refit_per_fold": True,
        "calibration_refit_per_fold": True,
    }


def _pareto_select(
    composite_metrics: dict[str, dict[str, Any]],
    temporal_by_id: dict[str, Any],
    expanding: dict[str, Any],
    paired_comparisons: dict[str, Any],
) -> dict[str, Any]:
    ids = list(COMPOSITE_IDS)
    complexity = {
        "GI_A_STRICT_CORE": 1.0,
        "GI_B_RECENCY": 1.2,
        "GI_C_SYMMETRIC_DIAGNOSTIC": 1.3,
        "GI_D_WEAKEST_DEFENCE": 1.1,
    }

    def metric_tuple(cid: str) -> tuple[float, float, float, float, float, float]:
        m = composite_metrics.get(cid) or {}
        tg = m.get("total_goals_ft") or {}
        ge2 = m.get("goals_ge_2") or {}
        spearman = abs(float(tg.get("spearman") or 0))
        mae = float(tg.get("mae") or 99.0)
        rmse = float(tg.get("rmse") or 99.0)
        auc = float(ge2.get("auc") or 0.5)
        brier = float(ge2.get("brier") or 1.0)
        exp = (expanding.get("candidates") or {}).get(cid) or {}
        stab = 1.0 if exp.get("direction_consistent") else 0.0
        # higher better for spearman/auc/stab; lower better for mae/rmse/brier/complexity → invert errors
        return (spearman, -mae, -rmse, auc, -brier, stab - 0.05 * complexity.get(cid, 1.0))

    dominated = set()
    for a in ids:
        for b in ids:
            if a == b:
                continue
            ma, mb = metric_tuple(a), metric_tuple(b)
            if all(x >= y for x, y in zip(mb, ma)) and any(x > y for x, y in zip(mb, ma)):
                dominated.add(a)
    nominal_front = [cid for cid in ids if cid not in dominated]

    # Statistically supported: require paired CI vs GI_A not including zero in favor of challenger
    supported: list[str] = ["GI_A_STRICT_CORE"]
    for cid in nominal_front:
        if cid == "GI_A_STRICT_CORE":
            continue
        key = f"{cid}_vs_GI_A_STRICT_CORE"
        comp = paired_comparisons.get(key) or {}
        tg = comp.get("total_goals_ft") or {}
        mae_ci = tg.get("delta_mae_ci")
        # delta_mae < 0 favors left (cid); support only if CI entirely < 0
        if mae_ci and mae_ci.get("ci_upper") is not None and float(mae_ci["ci_upper"]) < 0:
            supported.append(cid)

    primary = "GI_A_STRICT_CORE"
    challenger = "GI_B_RECENCY" if "GI_B_RECENCY" in ids else (nominal_front[1] if len(nominal_front) > 1 else None)
    if challenger is None:
        others = [c for c in nominal_front if c != primary] or [c for c in ids if c != primary]
        challenger = max(others, key=lambda c: metric_tuple(c)[0]) if others else None

    # Evidence: low if GI_B vs A CI includes zero
    gb = paired_comparisons.get("GI_B_RECENCY_vs_GI_A_STRICT_CORE") or {}
    mae_ci = (gb.get("total_goals_ft") or {}).get("delta_mae_ci")
    evidence = "low"
    if mae_ci and not _ci_includes_zero(mae_ci) and float(mae_ci.get("mean") or 0) < 0:
        evidence = "moderate"

    return {
        "nominal_pareto_front": nominal_front,
        "statistically_supported_pareto_front": supported,
        "pareto_front_candidates": nominal_front,
        "dominated_candidates": sorted(dominated),
        "primary_candidate": primary,
        "challenger_candidate": challenger,
        "selection_evidence_level": evidence,
        "selection_motivation": (
            "GI_A_STRICT_CORE resta baseline trasparente equal-weight; "
            "nessuna superiorità statistica dichiarata se gli intervalli paired includono zero."
        ),
        "uses_calibrated_metrics": True,
    }


def _candidate_definition_hash() -> str:
    payload = json.dumps(CANDIDATE_DEFINITIONS, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _prospective_protocol(*, date_to: date) -> dict[str, Any]:
    freeze_at = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
    first_scan = date_to + timedelta(days=1)
    window_start = datetime(first_scan.year, first_scan.month, first_scan.day, 0, 0, 0, tzinfo=timezone.utc)
    return {
        "candidate_definition_frozen_at": freeze_at.isoformat().replace("+00:00", "Z"),
        "candidate_definition_hash": _candidate_definition_hash(),
        "dataset_end_date": date_to.isoformat(),
        "retrospective_dataset_end_at": freeze_at.isoformat().replace("+00:00", "Z"),
        "first_prospective_scan_date": first_scan.isoformat(),
        "prospective_window_started_at": window_start.isoformat().replace("+00:00", "Z"),
        "prospective_matches_collected": 0,
        "minimum_prospective_matches": 200,
        "protocol_status": "waiting_for_prospective_data",
        "metrics_to_monitor": [
            "spearman_total_goals_ft",
            "mae_calibrated",
            "rmse_calibrated",
            "auc_goals_ge_2",
            "brier_goals_ge_2_calibrated",
            "auc_goals_ge_3",
            "brier_goals_ge_3_calibrated",
            "auc_btts_ft",
            "brier_btts_ft_calibrated",
            "direction_consistency_expanding_folds",
        ],
        "no_retroactive_formula_changes": True,
        "no_historical_1c_1d_matches_in_prospective": True,
        "validation_status": VALIDATION_STATUS,
        "note": (
            "Il periodo prospettico inizia strettamente dopo il freeze della definizione. "
            "Nessuna partita già usata in Fase 1C/1D entra nella coorte prospettica."
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
    # Ablation leave-one-out calibrata vs GI_A
    ablation: dict[str, Any] = {}
    all_predictions: list[dict[str, Any]] = []
    # Collect calibrated predictions for main composites + MT1 + LOO
    for cid in list(COMPOSITE_IDS) + ["MT1_LONG_TERM"] + list(LOO_IDS):
        _, preds = _calibrate_and_evaluate(
            scored, cid,
            bootstrap_iterations=min(200, bootstrap_iterations),
            random_seed=random_seed,
            bootstrap_cache={},
            collect_predictions=True,
            fold_id=None,
        )
        all_predictions.extend(preds)

    for label, key in (
        ("without_production", "GI_A_without_production"),
        ("without_defence", "GI_A_without_defence"),
        ("without_tempo", "GI_A_without_tempo"),
        ("without_volatility", "GI_A_without_volatility"),
    ):
        # Ablation: full GI_A vs LOO — positive assessment means full model better than LOO
        # so left=GI_A, right=LOO: delta_mae<0 means GI_A better → pillar contributes positively
        comp = _paired_calibrated_comparison(
            scored, "GI_A_STRICT_CORE", key,
            bootstrap_iterations=bootstrap_iterations,
            random_seed=random_seed,
            bootstrap_cache=bootstrap_cache,
        )
        tg = comp.get("total_goals_ft") or {}
        ge2 = comp.get("goals_ge_2") or {}
        assessment, evidence = _assessment_from_deltas(
            delta_mae_ci=tg.get("delta_mae_ci"),
            delta_spearman_ci=tg.get("delta_spearman_ci"),
            delta_auc_ci=ge2.get("delta_auc_ci"),
        )
        ablation[label] = {
            "loo_key": key,
            "calibrated": True,
            "uses_raw_score_vs_goals": False,
            "total_goals_ft": {
                "delta_spearman": tg.get("delta_spearman"),
                "delta_spearman_ci": tg.get("delta_spearman_ci"),
                "delta_mae": tg.get("delta_mae"),
                "delta_mae_ci": tg.get("delta_mae_ci"),
                "delta_rmse": tg.get("delta_rmse"),
                "delta_rmse_ci": tg.get("delta_rmse_ci"),
            },
            "goals_ge_2": {
                "delta_auc": ge2.get("delta_auc"),
                "delta_auc_ci": ge2.get("delta_auc_ci"),
                "delta_brier": ge2.get("delta_brier"),
                "delta_brier_ci": ge2.get("delta_brier_ci"),
                "delta_log_loss": ge2.get("delta_log_loss"),
                "delta_log_loss_ci": ge2.get("delta_log_loss_ci"),
            },
            "goals_ge_3": {
                k: (comp.get("goals_ge_3") or {}).get(k)
                for k in (
                    "delta_auc", "delta_auc_ci", "delta_brier", "delta_brier_ci",
                    "delta_log_loss", "delta_log_loss_ci",
                )
            },
            "btts_ft": {
                k: (comp.get("btts_ft") or {}).get(k)
                for k in (
                    "delta_auc", "delta_auc_ci", "delta_brier", "delta_brier_ci",
                    "delta_log_loss", "delta_log_loss_ci",
                )
            },
            "pillar_incremental_assessment": assessment,
            "evidence_level": evidence,
            "direction_notes": comp.get("direction_notes"),
        }
    phases["ablation_ms"] = _round((time.perf_counter() - t) * 1000, 2)

    # Paired candidate comparisons (calibrated)
    paired_comparisons = {}
    pairs = (
        ("GI_B_RECENCY", "GI_A_STRICT_CORE"),
        ("GI_C_SYMMETRIC_DIAGNOSTIC", "GI_A_STRICT_CORE"),
        ("GI_D_WEAKEST_DEFENCE", "GI_A_STRICT_CORE"),
        ("GI_A_STRICT_CORE", "MT1_LONG_TERM"),
        ("GI_B_RECENCY", "MT1_LONG_TERM"),
    )
    for left, right in pairs:
        paired_comparisons[f"{left}_vs_{right}"] = _paired_calibrated_comparison(
            scored, left, right,
            bootstrap_iterations=bootstrap_iterations,
            random_seed=random_seed,
            bootstrap_cache=bootstrap_cache,
        )

    # LOO vs MT1 diagnostic
    for loo in LOO_IDS:
        paired_comparisons[f"{loo}_vs_MT1_LONG_TERM"] = _paired_calibrated_comparison(
            scored, loo, "MT1_LONG_TERM",
            bootstrap_iterations=min(200, bootstrap_iterations),
            random_seed=random_seed,
            bootstrap_cache=bootstrap_cache,
        )

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

    pareto = _pareto_select(composite_metrics, temporal_metrics, expanding, paired_comparisons)
    primary_id = pareto["primary_candidate"]
    challenger_id = pareto["challenger_candidate"]
    for row in scored:
        row["primary_candidate_score"] = _round(safe_float(row.get(primary_id))) if primary_id else None
        row["challenger_candidate_score"] = _round(safe_float(row.get(challenger_id))) if challenger_id else None

    # MT1 vs composites assessment
    a_vs_mt1 = paired_comparisons.get("GI_A_STRICT_CORE_vs_MT1_LONG_TERM") or {}
    b_vs_mt1 = paired_comparisons.get("GI_B_RECENCY_vs_MT1_LONG_TERM") or {}
    a_assess = a_vs_mt1.get("comparison_assessment") or "inconclusive"
    b_assess = b_vs_mt1.get("comparison_assessment") or "inconclusive"
    # positive = composite (left) better than MT1
    if a_assess == "positive" or b_assess == "positive":
        composite_value = "positive"
        tempo_competitive = False
    elif a_assess in {"negative", "neutral"} and b_assess in {"negative", "neutral", "inconclusive"}:
        composite_value = "negative" if a_assess == "negative" else "neutral"
        tempo_competitive = True
    else:
        composite_value = "inconclusive"
        tempo_competitive = True
    mt1_tg = (baseline_metrics.get("MT1_LONG_TERM") or {}).get("total_goals_ft") or {}
    gi_a_tg = (composite_metrics.get("GI_A_STRICT_CORE") or {}).get("total_goals_ft") or {}
    if mt1_tg.get("spearman") is not None and gi_a_tg.get("spearman") is not None:
        if abs(float(mt1_tg["spearman"])) >= abs(float(gi_a_tg["spearman"])) - 0.02:
            tempo_competitive = True
    tempo_baseline_comparison = {
        "composite_value_over_tempo": composite_value,
        "tempo_only_baseline_competitive": tempo_competitive,
        "GI_A_vs_MT1": a_vs_mt1.get("comparison_assessment"),
        "GI_B_vs_MT1": b_vs_mt1.get("comparison_assessment"),
        "note": (
            "MT1 può risultare competitivo o superiore ai compositi; "
            "i compositi non sono promossi automaticamente."
        ),
    }
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
    first_prospective = prospective.get("first_prospective_scan_date")
    prospective_after_freeze = bool(
        first_prospective and date_to.isoformat() < str(first_prospective)
    )

    binary_cal_ok = all(
        (composite_metrics.get(cid) or {}).get(t, {}).get("calibration_method") == "train_logistic_regression"
        for cid in COMPOSITE_IDS
        for t in BINARY_TARGETS
        if (composite_metrics.get(cid) or {}).get(t)
    )
    linear_cal_ok = all(
        (composite_metrics.get(cid) or {}).get("total_goals_ft", {}).get("calibration_method")
        == "train_linear_regression"
        for cid in COMPOSITE_IDS
        if (composite_metrics.get(cid) or {}).get("total_goals_ft")
    )
    paired_dim_ok = all(
        (paired_comparisons.get(k) or {}).get("dimensionally_valid") is True
        and (paired_comparisons.get(k) or {}).get("uses_raw_score_vs_goals") is False
        for k in (
            "GI_B_RECENCY_vs_GI_A_STRICT_CORE",
            "GI_A_STRICT_CORE_vs_MT1_LONG_TERM",
            "GI_B_RECENCY_vs_MT1_LONG_TERM",
        )
    )
    paired_dir_ok = all(
        bool((paired_comparisons.get(k) or {}).get("direction_notes"))
        for k in ("GI_B_RECENCY_vs_GI_A_STRICT_CORE", "GI_A_STRICT_CORE_vs_MT1_LONG_TERM")
    )
    ablation_cal_ok = all(
        (ablation.get(lab) or {}).get("calibrated") is True
        and (ablation.get(lab) or {}).get("uses_raw_score_vs_goals") is False
        for lab in ("without_production", "without_defence", "without_tempo", "without_volatility")
    )
    expanding_ok = expanding.get("status") == "ok"
    expanding_all_cand = bool(expanding.get("all_candidates_present"))
    expanding_all_tgt = bool(expanding.get("all_targets_present"))
    temporal_complete = expanding_ok and expanding_all_cand and expanding_all_tgt

    phase_2a_checks = {
        "candidate_scores_complete": all(
            safe_float(scored[0].get(cid)) is not None for cid in COMPOSITE_IDS
        ) if scored else False,
        "train_only_normalization_verified": all(
            ecdfs[f].n > 0 for f in SCORE_FEATURES
        ),
        "no_target_leakage_verified": all(r.get("no_target_used_in_score") for r in scored),
        "binary_calibration_verified": binary_cal_ok and linear_cal_ok,
        "paired_comparison_dimensionally_valid": paired_dim_ok,
        "paired_delta_direction_verified": paired_dir_ok,
        "ablation_calibrated": ablation_cal_ok,
        "expanding_validation_all_candidates": expanding_all_cand and expanding_ok,
        "expanding_validation_all_targets": expanding_all_tgt and expanding_ok,
        "tempo_baseline_comparison_complete": bool(tempo_baseline_comparison.get("composite_value_over_tempo")),
        "prospective_start_strictly_after_freeze": prospective_after_freeze,
        "temporal_validation_complete": temporal_complete,
        "ablation_complete": ablation_cal_ok,
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
    else:
        next_2a = "complete_phase_1d_evaluation"

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
        "tempo_baseline_comparison": tempo_baseline_comparison,
        "temporal_metrics": {
            "splits": temporal_metrics,
            "expanding": {k: v for k, v in expanding.items() if k != "fold_rows"},
            "core_min20": core20_metrics,
            "month_diagnostic": month_diag,
        },
        "pareto_analysis": {
            **pareto,
            "tempo_only_baseline_competitive": tempo_competitive,
        },
        "xg_optional_analysis": xg_optional,
        "primary_candidate": primary_id,
        "challenger_candidate": challenger_id,
        "prospective_validation_protocol": prospective,
        "phase_2a_readiness": {
            **phase_2a_checks,
            "blocking_issues": blocking_2a,
            "recommended_next_step": next_2a,
            "ready_for_phase_2a": not blocking_2a,
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
            "evaluation_version": "v1_1_calibrated",
        },
        "preview_rows": preview_rows,
        "_scored_rows": scored,
        "_calibrated_predictions": all_predictions,
        "_temporal_fold_rows": expanding.get("fold_rows") or [],
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
        "calibrated_predictions": f"cecchino_goal_intensity_v5_calibrated_predictions_{from_s}_{to_s}.csv",
        "temporal_fold_metrics": f"cecchino_goal_intensity_v5_temporal_fold_metrics_{from_s}_{to_s}.csv",
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
    elif kind == "calibrated_predictions":
        rows = list(full.get("_calibrated_predictions") or [])
    elif kind == "temporal_fold_metrics":
        rows = list(full.get("_temporal_fold_rows") or [])
    else:  # xg_optional_enrichment
        rows = [full.get("xg_optional_analysis") or {}]
    yield from _csv_stream(rows)
