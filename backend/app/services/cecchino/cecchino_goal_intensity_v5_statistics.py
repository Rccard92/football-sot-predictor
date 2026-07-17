"""Analisi statistica Intensità Goal v5 — Fase 1C (riusa dataset 1B)."""

from __future__ import annotations

import csv
import io
import json
import statistics
import time
from collections import defaultdict
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
    apply_quantile_boundaries,
    bootstrap_paired_delta_ci,
    bootstrap_spearman_ci,
    build_quantile_boundaries,
    cluster_by_abs_rho,
    correlation_matrix,
    descriptive_feature_stats,
    direction_consistent,
    mann_whitney_u,
    monotonicity_from_quintile_means,
    pearson_r,
    point_biserial,
    safe_float,
    spearman_rho,
    standardized_mean_difference,
    vif_scores,
)

VERSION = "cecchino_goal_intensity_v5_statistics_v1_1"
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


def _round(value: float | None, digits: int = 6) -> float | None:
    return round(float(value), digits) if value is not None and np.isfinite(value) else None


def _arrays(rows: list[dict[str, Any]], features: tuple[str, ...]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    feature_arrays = {
        feature: np.asarray([safe_float(row.get(feature)) if safe_float(row.get(feature)) is not None else np.nan for row in rows], dtype=float)
        for feature in features
    }
    targets = {
        target: np.asarray([safe_float(row.get(target)) if safe_float(row.get(target)) is not None else np.nan for row in rows], dtype=float)
        for target in ALL_TARGETS
    }
    return feature_arrays, targets


def _ci_precision(ci: dict[str, Any]) -> float:
    lo, hi = ci.get("ci_lower"), ci.get("ci_upper")
    if lo is None or hi is None:
        return 0.0
    return round(max(0.0, 1.0 - min(1.0, abs(float(hi) - float(lo)))), 6)


def _signal_one(
    x: np.ndarray, y: np.ndarray, target: str, bootstrap_cache: dict[int, np.ndarray],
    iterations: int, seed: int,
) -> dict[str, Any]:
    from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import bootstrap_auc_ci, bootstrap_index_matrix

    mask = np.isfinite(x) & np.isfinite(y)
    xs, ys = x[mask], y[mask]
    n = len(xs)
    result: dict[str, Any] = {"n": n}
    if n < 3:
        return result
    indices = bootstrap_cache.setdefault(n, bootstrap_index_matrix(n, iterations, seed))
    quintiles = _quintile_signal(xs.tolist(), ys.tolist())
    mono = quintiles["monotonicity"]
    if target == "total_goals_ft":
        pearson = pearson_r(xs.tolist(), ys.tolist())
        spearman = bootstrap_spearman_ci(xs.tolist(), ys.tolist(), iterations=iterations, seed=seed, indices=indices)
        result.update({
            "pearson": _round(pearson),
            "spearman": spearman.get("spearman"),
            "spearman_bootstrap": spearman,
            "effect_direction": "positive" if (spearman.get("spearman") or 0) > 0 else "negative" if (spearman.get("spearman") or 0) < 0 else "flat",
            "quintile_high_minus_low": mono.get("high_minus_low"),
            "monotonicity_score": mono.get("monotonicity_score"),
            "quintiles": quintiles,
        })
    else:
        binary = ys.astype(int)
        pos, neg = xs[binary == 1], xs[binary == 0]
        auc_ci = bootstrap_auc_ci(binary, xs, indices)
        rho = spearman_rho(xs.tolist(), binary.astype(float).tolist())
        pb = point_biserial(binary.tolist(), xs.tolist())
        result.update({
            "point_biserial": _round(pb),
            "spearman": _round(rho),
            "auc": auc_ci["auc"],
            "auc_bootstrap": auc_ci,
            "mean_pos": _round(float(np.mean(pos))) if len(pos) else None,
            "mean_neg": _round(float(np.mean(neg))) if len(neg) else None,
            "smd": _round(standardized_mean_difference(pos.tolist(), neg.tolist())),
            "mann_whitney_u": _round(mann_whitney_u(pos.tolist(), neg.tolist()), 4),
            "effect_direction": "positive" if (pb or 0) > 0 else "negative" if (pb or 0) < 0 else "flat",
            "quintile_high_minus_low": mono.get("high_minus_low"),
            "monotonicity_score": mono.get("monotonicity_score"),
            "quintiles": quintiles,
        })
    return result


def _signal_table(
    arrays: dict[str, np.ndarray], targets: dict[str, np.ndarray], features: tuple[str, ...],
    bootstrap_cache: dict[int, np.ndarray], iterations: int, seed: int, *, xg: bool = False,
) -> list[dict[str, Any]]:
    rows = []
    for feature in features:
        values = arrays[feature]
        present = values[np.isfinite(values)]
        distribution = descriptive_feature_stats(present.tolist())
        distribution["missing"] = int(len(values) - len(present))
        distribution["missing_rate"] = _round((len(values) - len(present)) / len(values)) if len(values) else None
        item = {
            "feature": feature, "pillar": FEATURE_TO_PILLAR.get(feature, "xg"),
            "distribution": distribution, "targets": {},
        }
        for target, target_values in targets.items():
            item["targets"][target] = _signal_one(values, target_values, target, bootstrap_cache, iterations, seed)
        rows.append(item)
    return rows


def _flat_signal(item: dict[str, Any], *, coverage_paired: float | None = None, coverage_global: float | None = None) -> dict[str, Any]:
    flat: dict[str, Any] = {
        "feature_key": item["feature"], "pillar": item["pillar"],
        "coverage": item["distribution"].get("rows_available"),
        "coverage_paired": coverage_paired, "coverage_global": coverage_global,
        "low_variance": item["distribution"].get("low_variance"),
        "outlier_rate_iqr": item["distribution"].get("outlier_rate_iqr"),
        "n_unique": item["distribution"].get("n_unique"),
    }
    for target, metric in item["targets"].items():
        prefix = target
        for key in ("n", "pearson", "spearman", "point_biserial", "auc", "mean_pos", "mean_neg", "smd", "mann_whitney_u", "effect_direction", "quintile_high_minus_low", "monotonicity_score"):
            flat[f"{prefix}_{key}"] = metric.get(key)
        ci = metric.get("spearman_bootstrap") or metric.get("auc_bootstrap") or {}
        flat[f"{prefix}_ci_lower"] = ci.get("ci_lower")
        flat[f"{prefix}_ci_upper"] = ci.get("ci_upper")
        mono = (metric.get("quintiles") or {}).get("monotonicity") or {}
        flat[f"{prefix}_monotonic_direction"] = mono.get("monotonic_direction")
    # Alias compatibilità FE / export leggibili
    flat["spearman_total_goals"] = flat.get("total_goals_ft_spearman")
    flat["auc_goals_ge_2"] = flat.get("goals_ge_2_auc")
    flat["auc_goals_ge_3"] = flat.get("goals_ge_3_auc")
    flat["auc_btts_ft"] = flat.get("btts_ft_auc")
    flat["monotonic_direction"] = flat.get("total_goals_ft_monotonic_direction")
    return flat


def _dependency_map(arrays: dict[str, np.ndarray]) -> dict[str, dict[str, Any]]:
    result = {feature: {"dependency_type": "independent", "source_features": [], "exact_or_approximate": None, "keep_as_interpretable_summary": False, "eligible_for_same_formula_with_sources": True} for feature in arrays}
    pairs = (
        ("goals_ge_3_frequency_last_10", "over_2_5_frequency_last_10"),
        ("pair_goals_scored_rolling_5", "home_goals_scored_rolling_5", "away_goals_scored_rolling_5"),
        ("pair_goals_scored_rolling_10", "home_goals_scored_rolling_10", "away_goals_scored_rolling_10"),
        ("goals_rolling_5_vs_10_delta", "pair_goals_scored_rolling_5", "pair_goals_scored_rolling_10"),
    )
    for spec in pairs:
        target, *sources = spec
        if target not in arrays or any(source not in arrays for source in sources):
            continue
        mask = np.isfinite(arrays[target])
        for source in sources:
            mask &= np.isfinite(arrays[source])
        if mask.sum() < 3:
            continue
        expected = arrays[sources[0]][mask] if len(sources) == 1 else (
            arrays[sources[0]][mask] + arrays[sources[1]][mask] if target.startswith("pair_")
            else arrays[sources[0]][mask] - arrays[sources[1]][mask]
        )
        if np.allclose(arrays[target][mask], expected, rtol=0, atol=1e-10):
            kind = "exact_duplicate" if len(sources) == 1 else "derived_linear"
            result[target] = {
                "dependency_type": kind, "source_features": sources, "exact_or_approximate": "exact",
                "keep_as_interpretable_summary": kind == "derived_linear",
                "eligible_for_same_formula_with_sources": False,
            }
    return result


def _redundancy_v11(arrays: dict[str, np.ndarray], signals: list[dict[str, Any]]) -> dict[str, Any]:
    deps = _dependency_map(arrays)
    pearson = correlation_matrix({k: v.tolist() for k, v in arrays.items()}, "pearson")
    spearman = correlation_matrix({k: v.tolist() for k, v in arrays.items()}, "spearman")
    clusters = {str(t): cluster_by_abs_rho(spearman["matrix"], t) for t in (0.80, 0.85, 0.90)}
    removed = [key for key, dep in deps.items() if dep["dependency_type"] in ("exact_duplicate", "derived_linear")]
    independent = {key: value.tolist() for key, value in arrays.items() if key not in removed}
    vif = vif_scores(independent)
    vif["removed_exact_dependencies"] = removed
    vif["full_matrix_rank"] = vif.get("full_matrix_rank")
    vif["independent_feature_count"] = len(independent)
    vif["representative_vif"] = vif.get("vif", {})
    cluster_meta: dict[str, dict[str, Any]] = {}
    for i, group in enumerate(clusters["0.8"], start=1):
        candidates = [s for s in signals if s["feature"] in group]
        if not candidates:
            continue
        representative = max(
            candidates,
            key=lambda s: abs((s["targets"]["total_goals_ft"].get("spearman") or 0)),
        ).get("feature")
        for feature in group:
            cluster_meta[feature] = {
                "redundancy_cluster_id": f"rho80_{i}",
                "representative_of_cluster": feature == representative,
                "redundant_with": [x for x in group if x != feature],
            }
    return {"pearson": pearson, "spearman": spearman, "clusters": clusters, "vif": vif, "dependencies": deps, "cluster_meta": cluster_meta}


def _temporal_v11(rows: list[dict[str, Any]], arrays: dict[str, np.ndarray], targets: dict[str, np.ndarray]) -> dict[str, Any]:
    labels = np.asarray([str(r.get("temporal_fold_candidate") or "") for r in rows])
    months = np.asarray([str(r.get("kickoff_month") or r.get("kickoff") or "")[:7] for r in rows])
    blocks = {"train": labels == "train", "validation": labels == "validation", "test": labels == "test", "2026-06": months == "2026-06", "2026-07": months == "2026-07"}
    features: dict[str, Any] = {}
    for feature, values in arrays.items():
        by_target, signs = {}, []
        for target, y in targets.items():
            results = {}
            for name, mask in blocks.items():
                valid = mask & np.isfinite(values) & np.isfinite(y)
                rho = spearman_rho(values[valid].tolist(), y[valid].tolist()) if valid.sum() >= 3 else None
                results[name] = {"n": int(valid.sum()), "spearman": _round(rho)}
                if rho is not None and name in ("train", "validation", "test"):
                    signs.append(1 if rho > 0 else -1 if rho < 0 else 0)
            by_target[target] = results
        features[feature] = {"targets": by_target, "direction_consistent": direction_consistent(signs)}
    return {"features": features, "block_sizes": {k: int(v.sum()) for k, v in blocks.items()}}


def _rank_v11(signals: list[dict[str, Any]], redundancy: dict[str, Any], temporal: dict[str, Any], *, xg: bool = False) -> list[dict[str, Any]]:
    output = []
    for item in signals:
        feature = item["feature"]
        strengths, rankings = {}, {}
        for target, metric in item["targets"].items():
            effect = abs(metric.get("spearman") or metric.get("point_biserial") or 0)
            ci = metric.get("spearman_bootstrap") or metric.get("auc_bootstrap") or {}
            strengths[target] = {
                "effect_size": _round(effect),
                "ci_precision": _ci_precision(ci),
                "monotonicity": metric.get("monotonicity_score"),
                "temporal": temporal["features"].get(feature, {}).get("direction_consistent"),
                "auc": metric.get("auc"),
                "smd": metric.get("smd"),
            }
            rankings[target] = effect + 0.15 * strengths[target]["ci_precision"] + 0.05 * float(metric.get("monotonicity_score") or 0)
        dep = redundancy.get("dependencies", {}).get(feature, {})
        cluster = redundancy.get("cluster_meta", {}).get(feature, {})
        high_red = bool(cluster.get("redundant_with"))
        components = {
            "signal_component": _round(float(np.mean(list(rankings.values()))) if rankings else 0.0),
            "CI_precision_component": _round(float(np.mean([v["ci_precision"] for v in strengths.values()])) if strengths else 0.0),
            "monotonicity_component": _round(float(np.mean([v.get("monotonicity") or 0 for v in strengths.values()])) if strengths else 0.0),
            "temporal_component": 1.0 if temporal["features"].get(feature, {}).get("direction_consistent") else 0.0,
            "redundancy_component": 0.0 if high_red or dep.get("dependency_type") != "independent" else 1.0,
            "coverage_component": item["distribution"].get("rows_available", 0),
        }
        meaningful = (components["signal_component"] or 0) >= 0.10 and (components["CI_precision_component"] or 0) >= 0.20
        if xg and meaningful:
            recommendation = "candidate_optional_xg"
        elif meaningful and not high_red and dep.get("dependency_type") == "independent":
            recommendation = "candidate_core"
        elif meaningful:
            recommendation = "candidate_secondary"
        else:
            recommendation = "insufficient_evidence"
        redundancy_summary = "high" if high_red or dep.get("dependency_type") != "independent" else "low"
        if high_red and redundancy_summary == "low":
            redundancy_summary = "high"
        output.append({
            "feature_key": feature,
            "pillar": item["pillar"],
            "target_specific_strengths": strengths,
            "ranking_total_goals_ft": _round(rankings.get("total_goals_ft", 0)),
            "ranking_goals_ge_2": _round(rankings.get("goals_ge_2", 0)),
            "ranking_goals_ge_3": _round(rankings.get("goals_ge_3", 0)),
            "ranking_btts_ft": _round(rankings.get("btts_ft", 0)),
            "ranking_per_pillar": _round(float(np.mean(list(rankings.values()))) if rankings else 0),
            "research_evidence_components": components,
            "recommendation": recommendation,
            "evidence_level": "moderate" if meaningful and not xg else "low",
            "redundancy_summary": redundancy_summary,
            **cluster,
            **dep,
        })
    return output


def _decision_for_group(
    name: str, features: tuple[str, ...], recommendations: list[dict[str, Any]],
    signals_by_key: dict[str, dict[str, Any]], redundancy: dict[str, Any], temporal: dict[str, Any],
) -> dict[str, Any]:
    present = [f for f in features if f in signals_by_key]
    if not present:
        return {
            "group": name, "recommendation": "insufficient_evidence", "selected_feature": None,
            "secondary_feature": None, "excluded_redundant_features": [],
            "motivation": "feature non disponibili", "evidence_level": "insufficient_evidence",
        }
    by_key = {r["feature_key"]: r for r in recommendations}
    ordered = sorted(present, key=lambda f: by_key.get(f, {}).get("ranking_per_pillar") or -1, reverse=True)
    selected = ordered[0]
    secondary = ordered[1] if len(ordered) > 1 else None
    excluded = [
        f for f in present
        if redundancy["dependencies"].get(f, {}).get("dependency_type") != "independent"
        or (
            redundancy["cluster_meta"].get(f, {}).get("redundant_with")
            and not redundancy["cluster_meta"][f].get("representative_of_cluster")
        )
    ]
    selected_rec = by_key.get(selected, {})
    all_targets = selected_rec.get("target_specific_strengths", {})
    temporal_ok = temporal["features"].get(selected, {}).get("direction_consistent")
    enough = len(all_targets) == 4 and selected_rec.get("recommendation") not in (None, "insufficient_evidence")
    rank_gap = None
    if len(ordered) > 1:
        rank_gap = abs((by_key.get(ordered[0], {}).get("ranking_per_pillar") or 0) - (by_key.get(ordered[1], {}).get("ranking_per_pillar") or 0))
    if not enough:
        decision = "insufficient_evidence"
    elif rank_gap is not None and rank_gap < 0.02:
        decision = "keep_both"
    elif selected.endswith("rolling_5"):
        decision = "prefer_rolling_5"
    elif selected.endswith("rolling_10"):
        decision = "prefer_rolling_10"
    elif selected.endswith("_avg") or selected == "total_goals_avg":
        decision = "prefer_long_term_average"
    else:
        decision = "keep_both"
    return {
        "group": name,
        "recommendation": decision,
        "selected_feature": selected,
        "secondary_feature": secondary,
        "excluded_redundant_features": excluded,
        "motivation": (
            "Confronto su quattro target, monotonicità, IC bootstrap, blocchi train/validation/test "
            "e mesi giugno/luglio; la scelta usa il segnale osservato e non regole fisse."
            + ("" if temporal_ok else " Stabilità temporale debole sul selezionato.")
        ),
        "evidence_level": "moderate" if enough and temporal_ok else "low" if enough else "insufficient_evidence",
    }


def _rolling_decisions(signals: list[dict[str, Any]], recs: list[dict[str, Any]], redundancy: dict[str, Any], temporal: dict[str, Any]) -> dict[str, Any]:
    by_key = {s["feature"]: s for s in signals}
    groups = [
        ("home_attack", ("home_goals_scored_avg", "home_goals_scored_rolling_5", "home_goals_scored_rolling_10")),
        ("away_attack", ("away_goals_scored_avg", "away_goals_scored_rolling_5", "away_goals_scored_rolling_10")),
        ("match_tempo", ("total_goals_avg", "total_goals_rolling_5", "total_goals_rolling_10")),
    ]
    return {"groups": [_decision_for_group(name, features, recs, by_key, redundancy, temporal) for name, features in groups]}


def _stability_decision(signals: list[dict[str, Any]], recs: list[dict[str, Any]], temporal: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "goals_scored_std_last_10",
        "goals_scored_mad_last_10",
        "goals_scored_cv_last_10",
        "goals_rolling_5_vs_10_delta",
    )
    # pair rolling sono livello offensivo, non misure di dispersione: escluse dalla decisione.
    signal = {x["feature"]: x for x in signals}
    rec = {x["feature_key"]: x for x in recs}
    motivations: list[str] = []
    usable: list[str] = []
    excluded: list[str] = []
    for feature in keys:
        dist = signal.get(feature, {}).get("distribution", {})
        tg = signal.get(feature, {}).get("targets", {}).get("total_goals_ft", {})
        spearman = tg.get("spearman")
        n_unique = int(dist.get("n_unique") or 0)
        temp_ok = temporal["features"].get(feature, {}).get("direction_consistent")
        if feature.endswith("_mad_last_10") and n_unique <= 5:
            excluded.append(feature)
            motivations.append("MAD: pochi valori distinti / distribuzione fortemente discreta")
            continue
        if feature.endswith("_cv_last_10") and (spearman is None or spearman <= 0 or not temp_ok):
            excluded.append(feature)
            motivations.append("CV: segnale negativo o instabilità temporale")
            continue
        if feature.endswith("_delta") and (abs(spearman or 0) < 0.05 or not temp_ok):
            excluded.append(feature)
            motivations.append("delta: segnale debole e/o instabilità temporale")
            continue
        if feature not in rec or rec[feature]["recommendation"] == "insufficient_evidence":
            # STD può restare usable se ha copertura e unicità anche con evidenza limitata.
            if feature.endswith("_std_last_10") and n_unique >= 10:
                usable.append(feature)
                motivations.append("STD: elevata unicità e stabilità temporale relativa")
                continue
            excluded.append(feature)
            motivations.append(f"{feature}: evidenza insufficiente")
            continue
        usable.append(feature)
        if feature.endswith("_std_last_10"):
            motivations.append("STD: elevata unicità e stabilità temporale relativa")
    ordered = sorted(usable, key=lambda f: abs((signal.get(f, {}).get("targets", {}).get("total_goals_ft", {}).get("spearman") or 0)), reverse=True)
    preferred = ordered[0] if ordered else None
    secondary = ordered[1] if len(ordered) > 1 else None
    for feature in keys:
        if feature not in usable and feature not in excluded:
            excluded.append(feature)
    if preferred is None:
        return {
            "preferred_stability_metric": None,
            "secondary_stability_metric": None,
            "excluded_or_unstable_metrics": excluded,
            "recommendation": "insufficient_evidence",
            "motivation": "; ".join(dict.fromkeys(motivations)) or "Nessuna metrica di stabilità con evidenza sufficiente.",
            "evidence_level": "insufficient_evidence",
        }
    return {
        "preferred_stability_metric": preferred,
        "secondary_stability_metric": secondary,
        "excluded_or_unstable_metrics": excluded,
        "recommendation": f"prefer_{preferred}",
        "motivation": "; ".join(dict.fromkeys(motivations)),
        "evidence_level": "moderate" if temporal["features"].get(preferred, {}).get("direction_consistent") else "low",
    }


def _xg_models_v11(rows: list[dict[str, Any]], bootstrap_cache: dict[int, np.ndarray], iterations: int) -> dict[str, Any]:
    """CV temporale expanding; nessuna conclusione forte è automatica."""
    if len(rows) < 20:
        return {"status": "insufficient_sample_for_3_temporal_folds", "paired_n": len(rows), "models": {}}
    try:
        from sklearn.linear_model import LinearRegression, LogisticRegression
        from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error, mean_squared_error, roc_auc_score
    except ImportError:
        return {"status": "sklearn_unavailable", "paired_n": len(rows), "models": {}}
    ordered = sorted(rows, key=lambda r: str(r.get("kickoff") or ""))
    folds = []
    for end in range(max(12, len(ordered) // 3), len(ordered) - 4, max(1, len(ordered) // 4)):
        folds.append((ordered[:end], ordered[end:min(len(ordered), end + max(4, len(ordered) // 6))]))
    if len(folds) < 3:
        return {"status": "insufficient_sample_for_3_temporal_folds", "paired_n": len(rows), "models": {}}
    keys_base, keys_xg = CORE_FEATURES, CORE_FEATURES + XG_FEATURE_KEYS
    aggregate: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for train, test in folds:
        matrix = lambda group, keys: np.asarray([[float(row[k]) for k in keys] for row in group], dtype=float)
        y_train = np.asarray([float(row["total_goals_ft"]) for row in train])
        y_test = np.asarray([float(row["total_goals_ft"]) for row in test])
        base, plus = LinearRegression().fit(matrix(train, keys_base), y_train), LinearRegression().fit(matrix(train, keys_xg), y_train)
        bp, xp = base.predict(matrix(test, keys_base)), plus.predict(matrix(test, keys_xg))
        for name, pred in (("baseline", bp), ("xg", xp)):
            aggregate["total_goals_ft"][f"{name}_mae"].append(float(mean_absolute_error(y_test, pred)))
            aggregate["total_goals_ft"][f"{name}_rmse"].append(float(mean_squared_error(y_test, pred) ** .5))
            aggregate["total_goals_ft"][f"{name}_poisson_deviance"].append(float(np.mean(2 * (np.maximum(pred, 1e-6) - y_test * np.log(np.maximum(pred, 1e-6))))))
        aggregate["total_goals_ft"]["delta"].extend((np.abs(bp - y_test) - np.abs(xp - y_test)).tolist())
        for target in TARGETS_BINARY:
            yt, yv = np.asarray([int(r[target]) for r in train]), np.asarray([int(r[target]) for r in test])
            if len(np.unique(yt)) < 2 or len(np.unique(yv)) < 2:
                continue
            base_l = LogisticRegression(max_iter=1000).fit(matrix(train, keys_base), yt)
            plus_l = LogisticRegression(max_iter=1000).fit(matrix(train, keys_xg), yt)
            bp, xp = base_l.predict_proba(matrix(test, keys_base))[:, 1], plus_l.predict_proba(matrix(test, keys_xg))[:, 1]
            for name, pred in (("baseline", bp), ("xg", xp)):
                aggregate[target][f"{name}_auc"].append(float(roc_auc_score(yv, pred)))
                aggregate[target][f"{name}_logloss"].append(float(log_loss(yv, pred)))
                aggregate[target][f"{name}_brier"].append(float(brier_score_loss(yv, pred)))
                aggregate[target][f"{name}_calibration_error"].append(float(abs(np.mean(pred) - np.mean(yv))))
            aggregate[target]["delta"].extend((xp - bp).tolist())
    models = {}
    for target, metrics in aggregate.items():
        delta = metrics.pop("delta", [])
        index = bootstrap_cache.setdefault(len(delta), np.random.default_rng(42).integers(0, len(delta), size=(iterations, len(delta)))) if delta else np.empty((0, 0), dtype=int)
        models[target] = {key: _round(float(np.mean(value))) for key, value in metrics.items()}
        models[target]["paired_delta_ci"] = bootstrap_paired_delta_ci(delta, iterations=iterations, indices=index) if delta else {"mean": None, "ci_lower": None, "ci_upper": None, "valid_bootstrap_iterations": 0}
    return {
        "status": "ok",
        "paired_n": len(rows),
        "temporal_cv": {"method": "expanding", "fold_count": len(folds)},
        "models": models,
        "evidence_level": "low",
        "assessment": "neutral",
        "xg_value_assessment": "neutral",
    }


def build_goal_intensity_v5_statistics_internal(
    db: Session, *, date_from: date, date_to: date, competition_id: int | None = None,
    minimum_history_sample: int = 10, bootstrap_iterations: int = 1000, random_seed: int = 42,
) -> dict[str, Any]:
    """Statistiche 1C v1.1, esclusivamente sul dataset 1B già eleggibile."""
    t0, phases = time.perf_counter(), {}
    t = time.perf_counter()
    source = build_goal_intensity_v5_dataset_internal(db, date_from=date_from, date_to=date_to, competition_id=competition_id)
    phases["dataset_internal_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    if source.get("error") or source.get("status") == "error":
        return {"status": "error", "version": VERSION, "error": source.get("error"), "performance": phases}
    dataset_rows = list(source.get("dataset_rows") or [])
    if any(r.get("eligibility_status") != "eligible" for r in dataset_rows):
        return {
            "status": "error",
            "version": VERSION,
            "error": "ineligible_match_entered_statistics_dataset",
            "warnings": ["ineligible_match_entered_statistics_dataset"],
            "performance": phases,
        }
    rows = _core_rows(dataset_rows, minimum_history_sample)
    core10 = _core_rows(dataset_rows, 10)
    core20 = _core_rows(dataset_rows, 20)
    core10_ids = {r.get("local_fixture_id") for r in core10}
    paired_raw = filter_dataset_rows_by_kind(dataset_rows, "xg_paired")
    paired = [
        r for r in paired_raw
        if r.get("local_fixture_id") in core10_ids
        and all(safe_float(r.get(f)) is not None for f in XG_FEATURE_KEYS)
    ]
    bootstrap_cache: dict[int, np.ndarray] = {}
    t = time.perf_counter()
    arrays, targets = _arrays(rows, CORE_FEATURES)
    phases["descriptive_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    t = time.perf_counter()
    signals = _signal_table(arrays, targets, CORE_FEATURES, bootstrap_cache, bootstrap_iterations, random_seed)
    phases["univariate_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    phases["bootstrap_ms"] = phases["univariate_ms"]
    t = time.perf_counter()
    redundancy = _redundancy_v11(arrays, signals)
    phases["redundancy_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    t = time.perf_counter()
    temporal = _temporal_v11(rows, arrays, targets)
    phases["temporal_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    recs = _rank_v11(signals, redundancy, temporal)
    rolling = _rolling_decisions(signals, recs, redundancy, temporal)
    stability = _stability_decision(signals, recs, temporal)
    t = time.perf_counter()
    xg_arrays, xg_targets = _arrays(paired, XG_FEATURE_KEYS)
    paired_core_arrays, _ = _arrays(paired, CORE_FEATURES)
    xg_signals = _signal_table(xg_arrays, xg_targets, XG_FEATURE_KEYS, bootstrap_cache, bootstrap_iterations, random_seed, xg=True)
    xg_temporal = _temporal_v11(paired, xg_arrays, xg_targets)
    xg_recs = _rank_v11(
        xg_signals,
        {"dependencies": _dependency_map(xg_arrays), "cluster_meta": {}},
        xg_temporal,
        xg=True,
    )
    xg_models = _xg_models_v11(paired, bootstrap_cache, bootstrap_iterations)
    phases["xg_models_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    t = time.perf_counter()
    core_n = len(core10)
    paired_n = len(paired)
    xg_flat = []
    for s in xg_signals:
        flat = _flat_signal(
            s,
            coverage_paired=float(s["distribution"].get("rows_available") or 0),
            coverage_global=_round((s["distribution"].get("rows_available") or 0) / core_n) if core_n else 0.0,
        )
        correlations = {
            core: spearman_rho(xg_arrays[s["feature"]].tolist(), values.tolist())
            for core, values in paired_core_arrays.items()
        }
        valid = {key: value for key, value in correlations.items() if value is not None}
        flat["max_abs_redundancy_vs_core"] = _round(max((abs(value) for value in valid.values()), default=0.0))
        flat["most_redundant_core_feature"] = max(valid, key=lambda key: abs(valid[key])) if valid else None
        flat["temporal_status"] = (
            "stable"
            if xg_temporal["features"].get(s["feature"], {}).get("direction_consistent")
            else "insufficient_sample_or_unstable"
        )
        xg_flat.append(flat)
    feature_flat = [_flat_signal(s) for s in signals]
    signal_by_key = {s["feature"]: s for s in signals}
    xg_signal_by_key = {s["feature"]: s for s in xg_signals}
    for r in recs + xg_recs:
        s = signal_by_key.get(r["feature_key"]) or xg_signal_by_key.get(r["feature_key"])
        if s:
            r["coverage"] = s["distribution"]["rows_available"]
        r["strengths"] = r["target_specific_strengths"]
    phases["recommendation_ms"] = _round((time.perf_counter() - t) * 1000, 2)

    cluster_features: set[str] = set()
    for groups in (redundancy.get("clusters") or {}).values():
        for group in groups:
            cluster_features.update(group)
    cluster_meta = redundancy.get("cluster_meta") or {}
    reps_ok = all(feature in cluster_meta and "representative_of_cluster" in cluster_meta[feature] for feature in cluster_features)
    deps = redundancy.get("dependencies") or {}
    deps_ok = bool(deps) and all("dependency_type" in meta for meta in deps.values())

    readiness_checks = {
        "rolling_window_decision_available": all(
            bool(g.get("recommendation")) for g in rolling["groups"]
        ),
        "stability_metric_decision_available": bool(stability.get("preferred_stability_metric"))
        or stability.get("recommendation") == "insufficient_evidence"
        or stability.get("evidence_level") == "insufficient_evidence",
        "target_specific_analysis_complete": all(
            len(r.get("target_specific_strengths") or {}) == 4 for r in recs
        ),
        "xg_univariate_analysis_complete": (
            paired_n > 0
            and len(xg_signals) == len(XG_FEATURE_KEYS)
            and all(len(x.get("targets") or {}) == 4 for x in xg_signals)
            and all(f.get("coverage_paired") is not None for f in xg_flat)
            and all(f.get("total_goals_ft_spearman") is not None or f.get("coverage_paired") == 0 for f in xg_flat)
        ),
        "redundancy_representatives_selected": deps_ok and reps_ok,
    }
    blocking = [key for key, value in readiness_checks.items() if not value]
    elapsed = _round((time.perf_counter() - t0) * 1000, 2) or 0
    warnings = ["statistics_performance_above_target"] if elapsed > 45000 else []
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
            "note": RESEARCH_NOTE,
            "no_eligibility_mutation": True,
            "no_backfill": True,
            "utc_historical_exclusions_not_reclassified": True,
        },
        "cohort_summary": {
            "core_min10": len(core10),
            "core_min20": len(core20),
            "primary_analyzed": len(rows),
            "xg_complete_paired": paired_n,
            "fixture_ids_hash": source.get("fixture_ids_hash"),
            "targets_hash": source.get("targets_hash"),
            "ineligible_in_model": 0,
            "unknown_in_model": 0,
            "identity_excluded": len(source.get("identity_excluded") or []),
        },
        "target_summary": {
            "primary": _target_summary(rows),
            "core_min10": _target_summary(core10),
            "xg_paired": _target_summary(paired),
        },
        "feature_signal_summary": feature_flat,
        "xg_univariate_summary": xg_flat,
        "redundancy_summary": {
            "clusters": redundancy["clusters"],
            "cluster_counts": {k: len(v) for k, v in redundancy["clusters"].items()},
            "vif": redundancy["vif"],
            "dependencies": redundancy["dependencies"],
            "cluster_meta": redundancy["cluster_meta"],
        },
        "rolling_window_comparison": rolling,
        "stability_metric_comparison": stability,
        "temporal_stability_summary": temporal,
        "xg_value_summary": xg_models,
        "xg_availability_bias_report": {
            "core_min10": _target_summary(core10),
            "xg_paired": _target_summary(paired),
        },
        "pillar_recommendations": {
            pillar: {
                "candidate_core": [r["feature_key"] for r in recs if r["pillar"] == pillar and r["recommendation"] == "candidate_core"],
                "candidate_secondary": [r["feature_key"] for r in recs if r["pillar"] == pillar and r["recommendation"] == "candidate_secondary"],
            }
            for pillar in PILLAR_FEATURES
        },
        "feature_recommendations": recs + xg_recs,
        "phase_1d_readiness": {
            **readiness_checks,
            "blocking_issues": blocking,
            "recommended_next_step": "phase_1d_candidate_indices" if not blocking else "complete_phase_1c_analysis",
        },
        "warnings": warnings,
        "performance": {
            **phases,
            "elapsed_ms": elapsed,
            "bootstrap_iterations": bootstrap_iterations,
            "random_seed": random_seed,
            "bootstrap_index_matrices": {str(k): list(v.shape) for k, v in bootstrap_cache.items()},
            "no_v5_formula": True,
            "v4_unchanged": True,
        },
        "_feature_signal": signals,
        "_xg_feature_signal": xg_signals,
        "_feature_recommendations_raw": recs + xg_recs,
        "_redundancy": redundancy,
        "_dataset": source,
    }
    t = time.perf_counter()
    payload["performance"]["serialization_ms"] = _round((time.perf_counter() - t) * 1000, 2)
    return payload


def stream_goal_intensity_v5_statistics_export(
    db: Session, *, kind: StatsExportKind, date_from: date, date_to: date, competition_id: int | None = None,
    minimum_history_sample: int = 10, bootstrap_iterations: int = 1000, random_seed: int = 42,
) -> Iterator[str]:
    full = build_goal_intensity_v5_statistics_internal(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id,
        minimum_history_sample=minimum_history_sample, bootstrap_iterations=bootstrap_iterations,
        random_seed=random_seed,
    )
    if kind == "summary":
        yield json.dumps(_strip_private_keys(full), ensure_ascii=False, default=str)
        return
    if kind == "feature_signal":
        rows = list(full.get("feature_signal_summary") or []) + list(full.get("xg_univariate_summary") or [])
    elif kind == "rolling_comparison":
        rows = list((full.get("rolling_window_comparison") or {}).get("groups") or [])
    elif kind == "stability_metrics":
        rows = [full.get("stability_metric_comparison") or {}]
    elif kind == "feature_recommendations":
        rows = list(full.get("feature_recommendations") or [])
    elif kind == "xg_value":
        models = (full.get("xg_value_summary") or {}).get("models") or {}
        rows = [{"target": target, **metrics} for target, metrics in models.items()] or [full.get("xg_value_summary") or {}]
    elif kind == "redundancy_clusters":
        red = full.get("redundancy_summary") or {}
        deps = red.get("dependencies") or {}
        meta = red.get("cluster_meta") or {}
        keys = sorted(set(deps) | set(meta))
        rows = [{"feature_key": key, **(deps.get(key) or {}), **(meta.get(key) or {})} for key in keys]
    elif kind == "redundancy_matrix":
        matrix = (((full.get("_redundancy") or {}).get("spearman") or {}).get("matrix") or {})
        rows = []
        for a, row in matrix.items():
            for b, value in (row or {}).items():
                if a <= b:
                    continue
                rows.append({"feature_a": a, "feature_b": b, "spearman": value})
        if not rows:
            rows = [{"note": "matrice vuota"}]
    else:
        rows = [
            {"feature_key": key, **value}
            for key, value in ((full.get("temporal_stability_summary") or {}).get("features") or {}).items()
        ]
    yield from _csv_stream(rows)
