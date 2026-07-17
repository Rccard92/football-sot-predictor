"""Analisi statistica Intensità Goal v5 — Fase 1C (riusa dataset 1B)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
import time
from collections import Counter, defaultdict
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
    CV_LOW_MEAN_EPS,
    PSI_MODERATE,
    PSI_STABLE,
    apply_quantile_boundaries,
    auc_mann_whitney,
    bootstrap_auc,
    bootstrap_paired_delta_ci,
    bootstrap_spearman_ci,
    build_quantile_boundaries,
    classify_psi,
    cluster_by_abs_rho,
    correlation_matrix,
    descriptive_feature_stats,
    direction_consistent,
    ks_statistic,
    mann_whitney_u,
    monotonicity_from_quintile_means,
    pearson_r,
    point_biserial,
    population_stability_index,
    safe_float,
    spearman_rho,
    standardized_mean_difference,
    vif_scores,
)
from app.services.cecchino.cecchino_goal_intensity_v5_today_cohort import (
    COHORT_BASIS,
    MIN_GOAL_INTENSITY_TODAY_SCAN_DATE,
)

VERSION = "cecchino_goal_intensity_v5_statistics_v1"
ELIGIBILITY_ENGINE_VERSION = "legacy_pre_utc_fix"
RESEARCH_NOTE = (
    "La ricerca descrive la coorte effettivamente dichiarata eleggibile da Cecchino Today "
    "nel periodo analizzato. Le esclusioni tecniche storiche non sono state rivalutate."
)

TARGETS_CONTINUOUS = ("total_goals_ft",)
TARGETS_BINARY = ("goals_ge_2", "goals_ge_3", "btts_ft")
ALL_TARGETS = TARGETS_CONTINUOUS + TARGETS_BINARY

PILLAR_FEATURES: dict[str, tuple[str, ...]] = {
    "offensive_production": (
        "home_goals_scored_avg",
        "away_goals_scored_avg",
        "home_goals_scored_rolling_5",
        "away_goals_scored_rolling_5",
        "home_goals_scored_rolling_10",
        "away_goals_scored_rolling_10",
    ),
    "defensive_solidity": (
        "home_goals_conceded_avg",
        "away_goals_conceded_avg",
        "home_clean_sheet_freq",
        "away_clean_sheet_freq",
    ),
    "match_tempo": (
        "over_2_5_frequency_last_10",
        "gg_frequency_last_10",
        "total_goals_avg",
        "total_goals_rolling_5",
        "total_goals_rolling_10",
        "goals_ge_2_frequency_last_10",
        "goals_ge_3_frequency_last_10",
    ),
    "offensive_stability": (
        "pair_goals_scored_rolling_5",
        "pair_goals_scored_rolling_10",
        "goals_scored_std_last_10",
        "goals_scored_mad_last_10",
        "goals_scored_cv_last_10",
        "goals_rolling_5_vs_10_delta",
    ),
}

CORE_FEATURES = tuple(k for keys in PILLAR_FEATURES.values() for k in keys)
FEATURE_TO_PILLAR = {f: p for p, keys in PILLAR_FEATURES.items() for f in keys}

REDUNDANCY_FAMILIES: dict[str, tuple[str, ...]] = {
    "goals_scored_level": (
        "home_goals_scored_avg",
        "away_goals_scored_avg",
        "home_goals_scored_rolling_5",
        "away_goals_scored_rolling_5",
        "home_goals_scored_rolling_10",
        "away_goals_scored_rolling_10",
    ),
    "goals_conceded_level": (
        "home_goals_conceded_avg",
        "away_goals_conceded_avg",
        "home_clean_sheet_freq",
        "away_clean_sheet_freq",
    ),
    "match_goal_level": (
        "total_goals_avg",
        "total_goals_rolling_5",
        "total_goals_rolling_10",
        "over_2_5_frequency_last_10",
        "goals_ge_2_frequency_last_10",
        "goals_ge_3_frequency_last_10",
        "gg_frequency_last_10",
    ),
    "offensive_stability": (
        "goals_scored_std_last_10",
        "goals_scored_mad_last_10",
        "goals_scored_cv_last_10",
        "goals_rolling_5_vs_10_delta",
    ),
    "xg_for": ("home_xg_for_avg", "away_xg_for_avg", "pair_xg_for_avg"),
    "xg_against": ("home_xg_against_avg", "away_xg_against_avg", "pair_xg_against_avg"),
}

StatsExportKind = Literal[
    "summary",
    "feature_signal",
    "redundancy_matrix",
    "redundancy_clusters",
    "temporal_stability",
    "rolling_comparison",
    "stability_metrics",
    "xg_value",
    "feature_recommendations",
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


def _col(rows: list[dict[str, Any]], key: str) -> list[float | None]:
    return [safe_float(r.get(key)) for r in rows]


def _paired_xy(xs: list[float | None], ys: list[Any]) -> tuple[list[float], list[float]]:
    ox: list[float] = []
    oy: list[float] = []
    for x, y in zip(xs, ys):
        xf = safe_float(x)
        yf = safe_float(y)
        if xf is None or yf is None:
            continue
        ox.append(xf)
        oy.append(yf)
    return ox, oy


def _target_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    tg = [float(r["total_goals_ft"]) for r in rows if r.get("total_goals_ft") is not None]
    return {
        "n": len(rows),
        "total_goals_ft": {
            "mean": round(statistics.mean(tg), 4) if tg else None,
            "median": round(statistics.median(tg), 4) if tg else None,
            "std": round(statistics.pstdev(tg), 4) if len(tg) > 1 else None,
        },
        "goals_ge_2_rate": round(sum(1 for r in rows if r.get("goals_ge_2")) / len(rows), 4),
        "goals_ge_3_rate": round(sum(1 for r in rows if r.get("goals_ge_3")) / len(rows), 4),
        "btts_ft_rate": round(sum(1 for r in rows if r.get("btts_ft")) / len(rows), 4),
    }


def _bootstrap_pearson(
    xs: list[float], ys: list[float], *, iterations: int, seed: int
) -> dict[str, Any]:
    original = pearson_r(xs, ys)
    if original is None or len(xs) < 3:
        return {"pearson": None, "ci_lower": None, "ci_upper": None, "valid_bootstrap_iterations": 0}
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(iterations):
        idx = rng.integers(0, len(xs), len(xs))
        value = pearson_r([xs[i] for i in idx], [ys[i] for i in idx])
        if value is not None:
            values.append(value)
    if len(values) < 10:
        return {"pearson": round(original, 6), "ci_lower": None, "ci_upper": None, "valid_bootstrap_iterations": len(values)}
    return {
        "pearson": round(original, 6),
        "ci_lower": round(float(np.quantile(values, 0.025)), 6),
        "ci_upper": round(float(np.quantile(values, 0.975)), 6),
        "valid_bootstrap_iterations": len(values),
    }


def _quintile_signal(xs: list[float], ys: list[float]) -> dict[str, Any]:
    boundaries = build_quantile_boundaries(xs, 5)
    labels = apply_quantile_boundaries(xs, boundaries)
    bins = []
    means: list[float | None] = []
    for index in range(len(boundaries) + 1):
        target_values = [y for y, label in zip(ys, labels) if label == index]
        feature_values = [x for x, label in zip(xs, labels) if label == index]
        mean = statistics.mean(target_values) if target_values else None
        means.append(mean)
        bins.append({
            "quintile": index + 1,
            "count": len(target_values),
            "feature_mean": round(statistics.mean(feature_values), 6) if feature_values else None,
            "target_mean": round(mean, 6) if mean is not None else None,
        })
    return {
        "boundaries": [round(x, 6) for x in boundaries],
        "bins": bins,
        "monotonicity": monotonicity_from_quintile_means(means),
    }


def _analyze_feature_signal(
    rows: list[dict[str, Any]], *, bootstrap_iterations: int, random_seed: int
) -> list[dict[str, Any]]:
    analysis: list[dict[str, Any]] = []
    for feature_index, feature in enumerate(CORE_FEATURES):
        raw = _col(rows, feature)
        values = [value for value in raw if value is not None]
        item: dict[str, Any] = {
            "feature": feature,
            "pillar": FEATURE_TO_PILLAR.get(feature),
            "distribution": {
                **descriptive_feature_stats(values),
                "missing": len(rows) - len(values),
                "missing_rate": round((len(rows) - len(values)) / len(rows), 6) if rows else None,
            },
            "targets": {},
        }
        for target_index, target in enumerate(ALL_TARGETS):
            xs, ys = _paired_xy(raw, [r.get(target) for r in rows])
            target_result: dict[str, Any] = {"n": len(xs)}
            if target in TARGETS_CONTINUOUS:
                target_result.update({
                    "pearson_bootstrap": _bootstrap_pearson(
                        xs, ys, iterations=bootstrap_iterations,
                        seed=random_seed + feature_index * 100 + target_index,
                    ),
                    "spearman_bootstrap": bootstrap_spearman_ci(
                        xs, ys, iterations=bootstrap_iterations,
                        seed=random_seed + feature_index * 100 + target_index + 10_000,
                    ),
                    "quintiles": _quintile_signal(xs, ys) if xs else {"bins": [], "monotonicity": {}},
                })
            else:
                binary = [int(y) for y in ys]
                auc = auc_mann_whitney(binary, xs)
                pos = [x for x, y in zip(xs, binary) if y == 1]
                neg = [x for x, y in zip(xs, binary) if y == 0]
                target_result.update({
                    "point_biserial": round(point_biserial(binary, xs), 6) if point_biserial(binary, xs) is not None else None,
                    "auc": round(auc, 6) if auc is not None else None,
                    "auc_bootstrap": bootstrap_auc(
                        binary, xs, iterations=bootstrap_iterations,
                        seed=random_seed + feature_index * 100 + target_index + 20_000,
                    ),
                    "standardized_mean_difference": round(standardized_mean_difference(pos, neg), 6)
                    if standardized_mean_difference(pos, neg) is not None else None,
                    "mann_whitney_u": round(mann_whitney_u(pos, neg), 4) if mann_whitney_u(pos, neg) is not None else None,
                    "quintiles": _quintile_signal(xs, [float(y) for y in binary]) if xs else {"bins": [], "monotonicity": {}},
                })
            item["targets"][target] = target_result
        analysis.append(item)
    return analysis


def _redundancy_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    vectors: dict[str, list[float | None]] = {key: _col(rows, key) for key in CORE_FEATURES}
    pearson = correlation_matrix({key: [x for x in vectors[key]] for key in CORE_FEATURES}, "pearson")
    spearman = correlation_matrix({key: [x for x in vectors[key]] for key in CORE_FEATURES}, "spearman")
    vif = vif_scores({key: [x for x in vectors[key]] for key in CORE_FEATURES})  # type: ignore[arg-type]
    clusters = {
        str(threshold): cluster_by_abs_rho(pearson["matrix"], threshold)
        for threshold in (0.80, 0.85, 0.90)
    }
    families = []
    for family, members in REDUNDANCY_FAMILIES.items():
        present = [key for key in members if key in vectors]
        high_pairs = [
            (a, b) for i, a in enumerate(present) for b in present[i + 1:]
            if (pearson["matrix"][a].get(b) is not None and abs(pearson["matrix"][a][b]) >= 0.85)
            or (spearman["matrix"][a].get(b) is not None and abs(spearman["matrix"][a][b]) >= 0.85)
        ]
        families.append({
            "family": family,
            "features": present,
            "high_correlation_pairs": [{"feature_a": a, "feature_b": b} for a, b in high_pairs],
            "decision_status": "reduce_to_representative" if high_pairs else "retain_for_signal_review",
        })
    return {
        "pearson": pearson,
        "spearman": spearman,
        "clusters": clusters,
        "vif": vif,
        "families": families,
    }


def _rolling_comparison(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparisons = []
    for base in ("home_goals_scored", "away_goals_scored", "total_goals"):
        f5, f10 = f"{base}_rolling_5", f"{base}_rolling_10"
        if f5 not in CORE_FEATURES or f10 not in CORE_FEATURES:
            continue
        xs, ys = _paired_xy(_col(rows, f5), _col(rows, f10))
        deltas = [x - y for x, y in zip(xs, ys)]
        comparisons.append({
            "rolling_5_feature": f5,
            "rolling_10_feature": f10,
            "n": len(xs),
            "pearson": round(pearson_r(xs, ys), 6) if pearson_r(xs, ys) is not None else None,
            "spearman": round(spearman_rho(xs, ys), 6) if spearman_rho(xs, ys) is not None else None,
            "mean_delta_5_minus_10": round(statistics.mean(deltas), 6) if deltas else None,
            "mean_absolute_delta": round(statistics.mean(abs(x) for x in deltas), 6) if deltas else None,
        })
    return comparisons


def _stability_metric_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    features = (
        "goals_scored_std_last_10", "goals_scored_mad_last_10", "goals_scored_cv_last_10",
        "goals_rolling_5_vs_10_delta",
    )
    vectors = {key: _col(rows, key) for key in features}
    return {
        "features": list(features),
        "distributions": {
            key: descriptive_feature_stats([x for x in values if x is not None])
            for key, values in vectors.items()
        },
        "pearson": correlation_matrix({key: [x for x in values] for key, values in vectors.items()}, "pearson"),
        "cv_low_mean_epsilon": CV_LOW_MEAN_EPS,
    }


def _temporal_stability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: str(row.get("kickoff") or ""))
    split_rows = {
        "train": [r for r in ordered if r.get("temporal_fold_candidate") == "train"],
        "validation": [r for r in ordered if r.get("temporal_fold_candidate") == "validation"],
        "test": [r for r in ordered if r.get("temporal_fold_candidate") == "test"],
        "2026-06": [r for r in ordered if str(r.get("kickoff_month") or r.get("kickoff") or "")[:7] == "2026-06"],
        "2026-07": [r for r in ordered if str(r.get("kickoff_month") or r.get("kickoff") or "")[:7] == "2026-07"],
    }
    blocks = {name: _target_summary(group) for name, group in split_rows.items()}
    features: dict[str, Any] = {}
    reference = split_rows["train"]
    for feature in CORE_FEATURES:
        ref = [x for x in _col(reference, feature) if x is not None]
        comparisons = {}
        signs = []
        for name, group in split_rows.items():
            vals = [x for x in _col(group, feature) if x is not None]
            corr_x, corr_y = _paired_xy(_col(group, feature), [r.get("total_goals_ft") for r in group])
            rho = spearman_rho(corr_x, corr_y)
            if rho is not None:
                signs.append(1 if rho > 0 else -1 if rho < 0 else 0)
            psi = population_stability_index(ref, vals)
            comparisons[name] = {
                "n": len(vals),
                "mean": round(statistics.mean(vals), 6) if vals else None,
                "psi_vs_train": psi,
                "psi_status": classify_psi(psi),
                "ks_vs_train": ks_statistic(ref, vals),
                "spearman_total_goals": round(rho, 6) if rho is not None else None,
            }
        features[feature] = {
            "blocks": comparisons,
            "direction_consistent": direction_consistent(signs),
        }
    return {"blocks": blocks, "features": features, "reference_block": "train"}


def _xg_value_and_bias(
    rows: list[dict[str, Any]], *, bootstrap_iterations: int, random_seed: int
) -> dict[str, Any]:
    """Confronto out-of-sample con xG; ogni conclusione resta esplorativa."""
    core = [r for r in rows if all(r.get(k) is not None for k in CORE_FEATURES)]
    paired = [r for r in core if r.get("xg_status") == "available" and all(r.get(k) is not None for k in XG_FEATURE_KEYS)]
    report: dict[str, Any] = {
        "core_min10_rows": len(core),
        "xg_paired_rows": len(paired),
        "evidence_level": "exploratory",
        "note": "L'evidence_level non viene mai promosso automaticamente a strong.",
    }
    if len(paired) < 20:
        return {**report, "status": "insufficient_paired_rows", "models": {}, "bias_report": {}}
    try:
        from sklearn.linear_model import LinearRegression, LogisticRegression
        from sklearn.metrics import mean_absolute_error, roc_auc_score
    except ImportError:
        return {**report, "status": "sklearn_unavailable", "models": {}, "bias_report": {}}

    paired = sorted(paired, key=lambda row: str(row.get("kickoff") or ""))
    split = max(1, int(len(paired) * 0.70))
    train, test = paired[:split], paired[split:]
    if len(test) < 5:
        return {**report, "status": "insufficient_temporal_test_rows", "models": {}, "bias_report": {}}

    def matrix(items: list[dict[str, Any]], keys: tuple[str, ...]) -> np.ndarray:
        return np.asarray([[float(r[k]) for k in keys] for r in items], dtype=float)

    y_goals_train = np.asarray([float(r["total_goals_ft"]) for r in train])
    y_goals_test = np.asarray([float(r["total_goals_ft"]) for r in test])
    core_keys = CORE_FEATURES
    augmented_keys = CORE_FEATURES + XG_FEATURE_KEYS
    base = LinearRegression().fit(matrix(train, core_keys), y_goals_train)
    augmented = LinearRegression().fit(matrix(train, augmented_keys), y_goals_train)
    base_pred, aug_pred = base.predict(matrix(test, core_keys)), augmented.predict(matrix(test, augmented_keys))
    deltas = [abs(a - y) - abs(b - y) for a, b, y in zip(base_pred, aug_pred, y_goals_test)]
    models: dict[str, Any] = {
        "total_goals_ft": {
            "baseline_mae": round(float(mean_absolute_error(y_goals_test, base_pred)), 6),
            "xg_augmented_mae": round(float(mean_absolute_error(y_goals_test, aug_pred)), 6),
            "mae_delta_baseline_minus_xg": round(float(mean_absolute_error(y_goals_test, base_pred) - mean_absolute_error(y_goals_test, aug_pred)), 6),
            "paired_mae_delta_bootstrap": bootstrap_paired_delta_ci(
                deltas, iterations=bootstrap_iterations, seed=random_seed,
            ),
        }
    }
    for target in TARGETS_BINARY:
        yt, yv = [int(r[target]) for r in train], [int(r[target]) for r in test]
        if len(set(yt)) < 2 or len(set(yv)) < 2:
            models[target] = {"status": "single_class_in_temporal_fold"}
            continue
        bmodel = LogisticRegression(max_iter=1000).fit(matrix(train, core_keys), yt)
        xmodel = LogisticRegression(max_iter=1000).fit(matrix(train, augmented_keys), yt)
        bp, xp = bmodel.predict_proba(matrix(test, core_keys))[:, 1], xmodel.predict_proba(matrix(test, augmented_keys))[:, 1]
        models[target] = {
            "baseline_auc": round(float(roc_auc_score(yv, bp)), 6),
            "xg_augmented_auc": round(float(roc_auc_score(yv, xp)), 6),
            "auc_delta_xg_minus_baseline": round(float(roc_auc_score(yv, xp) - roc_auc_score(yv, bp)), 6),
        }
    report.update({
        "status": "ok",
        "temporal_cv": {"train_rows": len(train), "test_rows": len(test), "split": "chronological_70_30"},
        "models": models,
        "bias_report": {
            "core_min10": _target_summary(core),
            "xg_paired": _target_summary(paired),
            "total_goals_mean_delta": (
                round((_target_summary(paired).get("total_goals_ft", {}).get("mean") or 0)
                      - (_target_summary(core).get("total_goals_ft", {}).get("mean") or 0), 6)
            ),
        },
    })
    return report


def _rank_and_recommend(
    signals: list[dict[str, Any]], redundancy: dict[str, Any], temporal: dict[str, Any]
) -> dict[str, Any]:
    high_redundancy = {
        feature for group in redundancy.get("clusters", {}).get("0.85", []) for feature in group
    }
    ranked = []
    for item in signals:
        feature = item["feature"]
        target = item.get("targets", {}).get("total_goals_ft", {})
        spearman = target.get("spearman_bootstrap", {}).get("spearman")
        mono = target.get("quintiles", {}).get("monotonicity", {}).get("monotonicity_score")
        temporal_ok = temporal.get("features", {}).get(feature, {}).get("direction_consistent")
        components = {
            "signal": abs(spearman) if spearman is not None else 0.0,
            "monotonicity": float(mono or 0.0),
            "temporal_stability": 1.0 if temporal_ok else 0.0,
            "non_redundancy": 0.0 if feature in high_redundancy else 1.0,
        }
        score = statistics.mean(components.values())
        ranked.append({
            "feature": feature, "pillar": item.get("pillar"),
            "component_scores": components, "equal_weight_score": round(score, 6),
            "recommendation": (
                "candidate_core" if score >= 0.55 and feature not in high_redundancy
                else "candidate_secondary" if score >= 0.35
                else "insufficient_evidence"
            ),
            "evidence_level": "moderate" if score >= 0.55 else "low",
        })
    ranked.sort(key=lambda row: (-row["equal_weight_score"], row["feature"]))
    for f in XG_FEATURE_KEYS:
        ranked.append({
            "feature": f,
            "pillar": "offensive_production" if "for" in f else "defensive_solidity",
            "component_scores": {},
            "equal_weight_score": None,
            "recommendation": "candidate_optional_xg",
            "evidence_level": "low",
        })
    return {"ranking": ranked, "weighting": "equal_component_weights"}


def build_goal_intensity_v5_statistics_internal(
    db: Session, *, date_from: date, date_to: date, competition_id: int | None = None,
    minimum_history_sample: int = 10, bootstrap_iterations: int = 1000, random_seed: int = 42,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    warnings: list[str] = []
    if minimum_history_sample not in (10, 20):
        raise ValueError("minimum_history_sample deve essere 10 o 20")
    source = build_goal_intensity_v5_dataset_internal(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id,
    )
    if source.get("status") == "error" or (source.get("status") and source.get("status") != "ok" and source.get("error")):
        # dataset internal may omit status=ok; treat error key
        if source.get("error") or source.get("status") == "error":
            return {"status": "error", "version": VERSION, "error": source.get("error"), "warnings": warnings}
    dataset_rows = list(source.get("dataset_rows") or [])
    if any(row.get("eligibility_status") != "eligible" for row in dataset_rows):
        return {
            "status": "error",
            "version": VERSION,
            "error": "ineligible_match_entered_statistics_dataset",
            "warnings": ["ineligible_match_entered_statistics_dataset"],
        }
    if any(str(row.get("scan_date") or "") < MIN_GOAL_INTENSITY_TODAY_SCAN_DATE.isoformat() for row in dataset_rows):
        warnings.append("scan_date_before_min_detected")

    core10 = _core_rows(dataset_rows, 10)
    core20 = _core_rows(dataset_rows, 20)
    rows = _core_rows(dataset_rows, minimum_history_sample)
    paired = filter_dataset_rows_by_kind(dataset_rows, "xg_paired")

    signals = _analyze_feature_signal(rows, bootstrap_iterations=bootstrap_iterations, random_seed=random_seed)
    redundancy = _redundancy_analysis(rows)
    temporal = _temporal_stability(rows)
    rolling = _rolling_comparison(rows)
    stability_metrics = _stability_metric_comparison(rows)
    xg = _xg_value_and_bias(core10, bootstrap_iterations=bootstrap_iterations, random_seed=random_seed)
    recs = _rank_and_recommend(signals, redundancy, temporal)

    # Mark redundant/unstable in recommendations
    unstable_feats = {
        f for f, meta in (temporal.get("features") or {}).items()
        if not meta.get("direction_consistent")
    }
    high_red = {f for g in redundancy.get("clusters", {}).get("0.85", []) for f in g}
    for item in recs.get("ranking") or []:
        feat = item["feature"]
        if feat in unstable_feats and item["recommendation"] not in ("candidate_optional_xg",):
            item["recommendation"] = "unstable_candidate"
        elif feat in high_red and item["recommendation"] == "candidate_secondary":
            item["recommendation"] = "redundant_candidate"

    feature_recs = []
    for item in recs.get("ranking") or []:
        sig = next((s for s in signals if s.get("feature") == item["feature"]), {})
        tg = (sig.get("targets") or {}).get("total_goals_ft") or {}
        feature_recs.append({
            "feature_key": item["feature"],
            "pillar": item.get("pillar"),
            "coverage": (sig.get("distribution") or {}).get("rows_available"),
            "signal_summary": {
                "spearman_total_goals": (tg.get("spearman_bootstrap") or {}).get("spearman"),
            },
            "redundancy_summary": "high" if item["feature"] in high_red else "low",
            "temporal_stability": (
                "stable" if (temporal.get("features") or {}).get(item["feature"], {}).get("direction_consistent")
                else "unstable"
            ),
            "target_specific_strengths": {},
            "weaknesses": [],
            "recommendation": item["recommendation"],
            "evidence_level": item.get("evidence_level") or "low",
            "research_evidence_components": item.get("component_scores"),
            "research_evidence_mean": item.get("equal_weight_score"),
        })

    pillar_recs: dict[str, Any] = {}
    for pillar, keys in PILLAR_FEATURES.items():
        subset = [r for r in feature_recs if r["feature_key"] in keys]
        pillar_recs[pillar] = {
            "candidate_core": [r["feature_key"] for r in subset if r["recommendation"] == "candidate_core"],
            "candidate_secondary": [r["feature_key"] for r in subset if r["recommendation"] == "candidate_secondary"],
            "note": (
                "Feature difensive disponibili; nessuna feature primaria ancora selezionata statisticamente."
                if pillar == "defensive_solidity"
                else None
            ),
        }

    fold_train = sum(1 for r in rows if r.get("temporal_fold_candidate") == "train" or r.get("train_candidate"))
    fold_test = sum(1 for r in rows if r.get("temporal_fold_candidate") == "test" or r.get("test_candidate"))
    blocking = []
    if len(rows) < 100:
        blocking.append("core_sample_too_small")
    readiness = {
        "core_sample_sufficient": len(rows) >= 200,
        "temporal_validation_available": fold_train > 0 and fold_test > 0,
        "redundancy_analysis_complete": bool(redundancy.get("families")),
        "rolling_window_decision_available": bool(rolling),
        "stability_metric_decision_available": bool(stability_metrics),
        "xg_assessment_available": xg.get("status") == "ok",
        "blocking_issues": blocking,
        "recommended_next_step": "collect_more_data" if blocking else "phase_1d_candidate_indices",
    }

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
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
            "note": RESEARCH_NOTE,
            "utc_historical_exclusions_not_reclassified": True,
            "no_backfill": True,
            "no_eligibility_mutation": True,
        },
        "cohort_summary": {
            "cohort_basis": source.get("cohort_basis") or COHORT_BASIS,
            "rows_feature_safe": len(dataset_rows),
            "core_min10": len(core10),
            "core_min20": len(core20),
            "primary_analyzed": len(rows),
            "xg_complete_paired": len(paired),
            "identity_excluded": len(source.get("identity_excluded") or []),
            "fixture_ids_hash": source.get("fixture_ids_hash"),
            "targets_hash": source.get("targets_hash"),
            "ineligible_in_model": 0,
            "unknown_in_model": 0,
        },
        "target_summary": {
            "primary": _target_summary(rows),
            "core_min10": _target_summary(core10),
            "xg_paired": _target_summary(paired),
        },
        "feature_signal_summary": [
            {
                "feature_key": s["feature"],
                "pillar": s.get("pillar"),
                "coverage": (s.get("distribution") or {}).get("rows_available"),
                "spearman_total_goals": ((s.get("targets") or {}).get("total_goals_ft") or {})
                .get("spearman_bootstrap", {})
                .get("spearman"),
                "auc_goals_ge_2": ((s.get("targets") or {}).get("goals_ge_2") or {}).get("auc"),
                "monotonic_direction": ((s.get("targets") or {}).get("total_goals_ft") or {})
                .get("quintiles", {})
                .get("monotonicity", {})
                .get("monotonic_direction"),
                "monotonicity_score": ((s.get("targets") or {}).get("total_goals_ft") or {})
                .get("quintiles", {})
                .get("monotonicity", {})
                .get("monotonicity_score"),
                "low_variance": (s.get("distribution") or {}).get("low_variance"),
            }
            for s in signals
        ],
        "redundancy_summary": {
            "thresholds": {"rho_0_80": 0.80, "rho_0_85": 0.85, "rho_0_90": 0.90},
            "cluster_counts": {k: len(v) for k, v in (redundancy.get("clusters") or {}).items()},
            "clusters": redundancy.get("clusters"),
            "vif": redundancy.get("vif"),
            "families": redundancy.get("families"),
        },
        "rolling_window_comparison": {"groups": rolling},
        "stability_metric_comparison": stability_metrics,
        "temporal_stability_summary": {
            "reference_block": temporal.get("reference_block"),
            "block_sizes": {k: (v or {}).get("n") for k, v in (temporal.get("blocks") or {}).items()},
            "direction_consistent_features": [
                f for f, m in (temporal.get("features") or {}).items() if m.get("direction_consistent")
            ],
            "unstable_features": [
                f for f, m in (temporal.get("features") or {}).items() if not m.get("direction_consistent")
            ],
            "psi_thresholds": {"stable_lt": PSI_STABLE, "moderate_le": PSI_MODERATE},
        },
        "xg_value_summary": {
            "paired_n": xg.get("xg_paired_rows"),
            "status": xg.get("status"),
            "xg_value_assessment": (
                "positive"
                if ((xg.get("models") or {}).get("total_goals_ft") or {}).get("mae_delta_baseline_minus_xg", 0) > 0.02
                else "neutral"
                if xg.get("status") == "ok"
                else "inconclusive"
            ),
            "evidence_level": "low" if xg.get("evidence_level") == "exploratory" else xg.get("evidence_level"),
            "models": xg.get("models"),
            "temporal_cv": xg.get("temporal_cv"),
            "note": xg.get("note"),
        },
        "xg_availability_bias_report": xg.get("bias_report") or {},
        "pillar_recommendations": pillar_recs,
        "feature_recommendations": feature_recs,
        "phase_1d_readiness": readiness,
        "warnings": warnings,
        "performance": {
            "elapsed_ms": elapsed_ms,
            "bootstrap_iterations": bootstrap_iterations,
            "random_seed": random_seed,
            "no_v5_formula": True,
            "v4_unchanged": True,
        },
        # full sections for export
        "_feature_signal": signals,
        "_redundancy_analysis": redundancy,
        "_temporal_stability": temporal,
        "_rolling_comparison": rolling,
        "_stability_metric_comparison": stability_metrics,
        "_xg_value_and_bias": xg,
        "_feature_recommendations_raw": recs,
        "_dataset": source,
    }


def _strip_private_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_private_keys(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, list):
        return [_strip_private_keys(item) for item in value]
    return value


def build_goal_intensity_v5_statistics(
    db: Session, *, date_from: date, date_to: date, competition_id: int | None = None,
    minimum_history_sample: int = 10, bootstrap_iterations: int = 1000, random_seed: int = 42,
) -> dict[str, Any]:
    full = build_goal_intensity_v5_statistics_internal(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id,
        minimum_history_sample=minimum_history_sample, bootstrap_iterations=bootstrap_iterations,
        random_seed=random_seed,
    )
    compact = _strip_private_keys(full)
    raw = json.dumps(compact, default=str).encode("utf-8")
    compact.setdefault("performance", {})["response_payload_bytes"] = len(raw)
    return compact


def statistics_export_filename(*, kind: StatsExportKind, date_from: date, date_to: date) -> str:
    from_s, to_s = date_from.isoformat(), date_to.isoformat()
    names = {
        "summary": f"cecchino_goal_intensity_v5_statistics_summary_{from_s}_{to_s}.json",
        "feature_signal": f"cecchino_goal_intensity_v5_feature_signal_{from_s}_{to_s}.csv",
        "redundancy_matrix": f"cecchino_goal_intensity_v5_redundancy_matrix_{from_s}_{to_s}.csv",
        "redundancy_clusters": f"cecchino_goal_intensity_v5_redundancy_clusters_{from_s}_{to_s}.csv",
        "temporal_stability": f"cecchino_goal_intensity_v5_temporal_stability_{from_s}_{to_s}.csv",
        "rolling_comparison": f"cecchino_goal_intensity_v5_rolling_comparison_{from_s}_{to_s}.csv",
        "stability_metrics": f"cecchino_goal_intensity_v5_stability_metrics_{from_s}_{to_s}.csv",
        "xg_value": f"cecchino_goal_intensity_v5_xg_value_{from_s}_{to_s}.csv",
        "feature_recommendations": f"cecchino_goal_intensity_v5_feature_recommendations_{from_s}_{to_s}.csv",
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


def stream_goal_intensity_v5_statistics_export(
    db: Session, *, kind: StatsExportKind, date_from: date, date_to: date,
    competition_id: int | None = None, minimum_history_sample: int = 10,
    bootstrap_iterations: int = 1000, random_seed: int = 42,
) -> Iterator[str]:
    full = build_goal_intensity_v5_statistics_internal(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id,
        minimum_history_sample=minimum_history_sample, bootstrap_iterations=bootstrap_iterations,
        random_seed=random_seed,
    )
    if kind == "summary":
        yield json.dumps(_strip_private_keys(full), ensure_ascii=False, default=str)
        return

    rows_out: list[dict[str, Any]] = []
    if kind == "feature_signal":
        for s in full.get("_feature_signal") or []:
            tg = (s.get("targets") or {}).get("total_goals_ft") or {}
            rows_out.append({
                "feature_key": s.get("feature"),
                "pillar": s.get("pillar"),
                "rows_available": (s.get("distribution") or {}).get("rows_available"),
                "mean": (s.get("distribution") or {}).get("mean"),
                "std": (s.get("distribution") or {}).get("standard_deviation"),
                "spearman_total_goals": (tg.get("spearman_bootstrap") or {}).get("spearman"),
                "auc_goals_ge_2": ((s.get("targets") or {}).get("goals_ge_2") or {}).get("auc"),
                "monotonic_direction": (tg.get("quintiles") or {}).get("monotonicity", {}).get("monotonic_direction"),
                "monotonicity_score": (tg.get("quintiles") or {}).get("monotonicity", {}).get("monotonicity_score"),
            })
    elif kind == "redundancy_matrix":
        mat = ((full.get("_redundancy_analysis") or {}).get("spearman") or {}).get("matrix") or {}
        for a, row in mat.items():
            for b, val in (row or {}).items():
                rows_out.append({"feature_a": a, "feature_b": b, "spearman": val})
    elif kind == "redundancy_clusters":
        for thr, clusters in ((full.get("redundancy_summary") or {}).get("clusters") or {}).items():
            for i, cl in enumerate(clusters):
                rows_out.append({"threshold": thr, "cluster_id": i, "features": "|".join(cl), "size": len(cl)})
    elif kind == "temporal_stability":
        for f, meta in ((full.get("_temporal_stability") or {}).get("features") or {}).items():
            rows_out.append({
                "feature_key": f,
                "direction_consistent": meta.get("direction_consistent"),
                "blocks_json": json.dumps(meta.get("blocks") or {}, default=str),
            })
    elif kind == "rolling_comparison":
        for g in full.get("_rolling_comparison") or []:
            rows_out.append(g)
    elif kind == "stability_metrics":
        sm = full.get("_stability_metric_comparison") or {}
        if isinstance(sm, dict):
            rows_out.append(sm)
    elif kind == "xg_value":
        xv = full.get("xg_value_summary") or {}
        rows_out.append({
            "paired_n": xv.get("paired_n"),
            "xg_value_assessment": xv.get("xg_value_assessment"),
            "evidence_level": xv.get("evidence_level"),
            "models_json": json.dumps(xv.get("models") or {}, default=str),
        })
    elif kind == "feature_recommendations":
        rows_out = list(full.get("feature_recommendations") or [])

    yield from _csv_stream(rows_out)
