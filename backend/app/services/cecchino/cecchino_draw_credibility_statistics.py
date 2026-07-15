"""Analisi statistica Credibilità X — Fase 1C.1 (stdlib only)."""

from __future__ import annotations

import math
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_draw_credibility_dataset import (
    build_draw_credibility_all_rows,
    rows_for_selected_cohort,
)
from app.services.cecchino.cecchino_draw_credibility_research_common import (
    COHORT_ALL_USABLE_SENSITIVITY,
    COHORT_ELIGIBLE_PRIMARY,
    COHORT_MARKET_SUBSET,
    _parse_iso_dt,
    normalize_outcome_side,
    pct,
)
from app.services.cecchino.cecchino_draw_credibility_statistics_helpers import (
    FEATURE_FAMILIES,
    TREND_TOLERANCE_PP,
    WILSON_Z,
    apply_quantile_boundaries,
    auc_mann_whitney,
    bin_label_from_boundaries,
    bootstrap_auc,
    bootstrap_roi,
    brier_score,
    build_quantile_boundaries,
    classify_trend,
    classify_trend_with_diagnostics,
    clamp_prob,
    feature_family,
    herfindahl,
    hhi_concentration_status,
    log_loss_score,
    pearson_r,
    spearman_rho,
    wilson_ci,
)

VERSION = "cecchino_draw_credibility_statistics_v1_1"

NUMERIC_FEATURES = (
    "prob_x_norm",
    "quota_cecchino_x",
    "x_vs_best_lateral_pp",
    "x_vs_second_probability_pp",
    "f36_abs",
    "f36_score_existing",
    "dominance_pp",
    "dominance_normalized_pp",
    "conviction_index_candidate",
    "x_directional_conviction_candidate",
    "probability_gap_1_2_pp",
    "probability_balance_index",
    "gap_coherence_index_candidate",
    "prob_under_2_5_cecchino_pct",
    "under_minus_over_pp",
    "under_strength_pp",
    "hours_to_kickoff",
)
CATEGORICAL_FEATURES = (
    "x_rank",
    "x_tied_for_top",
    "x_is_top",
    "x_is_last",
    "dominant_sign",
    "dominant_sign_normalized",
    "x_conviction_direction",
    "x_direction_bucket",
    "conviction_class_candidate",
    "f36_class_existing",
    "gap_coherence_class_candidate",
    "goal_probability_source",
    "hours_to_kickoff_class",
)
PVS_CATEGORICAL_FEATURES = (
    "x_rank",
    "dominant_sign_normalized",
    "x_conviction_direction",
    "conviction_class_candidate",
    "f36_class_existing",
    "gap_coherence_class_candidate",
    "hours_to_kickoff_class",
)
BOOK_NUMERIC = (
    "prob_book_x_norm",
    "quota_book_x",
    "deviation_x_pp",
    "market_deviation_mean_pp",
    "prob_book_under_2_5_norm",
    "book_1x2_overround",
    "book_goal_overround",
)
CORRELATION_FEATURES = NUMERIC_FEATURES
TEMPORAL_AUC_FEATURES = (
    "prob_x_norm",
    "prob_under_2_5_cecchino_pct",
    "f36_abs",
    "x_directional_conviction_candidate",
    "probability_gap_1_2_pp",
    "hours_to_kickoff",
)

CONVICTION_ORDER = ("Molto Debole", "Debole", "Moderata", "Forte", "Molto Forte")
F36_ORDER = ("Equilibrio forte", "Equilibrio", "Transizione", "Squilibrio")
GAP_COH_ORDER = ("Non Confermato", "Debole", "Parziale", "Confermato", "Fortemente Confermato")
HOURS_CLASS_ORDER = ("<=24h", ">24-72h", ">72-120h", ">120h")
X_DIRECTION_ORDER = (
    "draw_above_laterals",
    "draw_near_laterals",
    "draw_below_laterals",
    "unknown",
)
SIGN_ORDER = ("HOME", "DRAW", "AWAY", "null")

EXPECTED_REDUNDANCY_GROUPS = (
    ("quota_cecchino_x", "prob_x_norm"),
    ("dominance_pp", "conviction_index_candidate"),
    ("f36_abs", "probability_gap_1_2_pp"),
    ("probability_gap_1_2_pp", "probability_balance_index"),
    ("prob_under_2_5_cecchino_pct", "under_minus_over_pp"),
)

INTERACTION_SPECS: tuple[dict[str, Any], ...] = (
    {
        "interaction_key": "x_rank_x_under_q",
        "label": "x_rank × Under 2.5 quintile",
        "row_dimension": "x_rank",
        "column_dimension": "prob_under_2_5_cecchino_pct",
        "column_type": "quantile",
    },
    {
        "interaction_key": "dominant_sign_x_conviction_class",
        "label": "dominant_sign_normalized × conviction_class_candidate",
        "row_dimension": "dominant_sign_normalized",
        "column_dimension": "conviction_class_candidate",
        "column_type": "categorical",
    },
    {
        "interaction_key": "f36_class_x_rank",
        "label": "f36_class_existing × x_rank",
        "row_dimension": "f36_class_existing",
        "column_dimension": "x_rank",
        "column_type": "categorical",
    },
    {
        "interaction_key": "f36_class_x_under_q",
        "label": "f36_class_existing × Under 2.5 quintile",
        "row_dimension": "f36_class_existing",
        "column_dimension": "prob_under_2_5_cecchino_pct",
        "column_type": "quantile",
    },
    {
        "interaction_key": "x_direction_bucket_x_under_q",
        "label": "x_direction_bucket × Under 2.5 quintile",
        "row_dimension": "x_direction_bucket",
        "column_dimension": "prob_under_2_5_cecchino_pct",
        "column_type": "quantile",
    },
    {
        "interaction_key": "dominant_sign_x_f36_class",
        "label": "dominant_sign_normalized × f36_class_existing",
        "row_dimension": "dominant_sign_normalized",
        "column_dimension": "f36_class_existing",
        "column_type": "categorical",
    },
    {
        "interaction_key": "hours_class_x_prob_x_q",
        "label": "hours_to_kickoff_class × prob_x_norm quintile",
        "row_dimension": "hours_to_kickoff_class",
        "column_dimension": "prob_x_norm",
        "column_type": "quantile",
    },
)


def _round_out(obj: Any, ndigits: int = 4) -> Any:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return None
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_out(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_out(v, ndigits) for v in obj]
    return obj


def _num(row: dict, key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _parse_kickoff(row: dict) -> datetime | None:
    return _parse_iso_dt(row.get("kickoff"))


def _mean_or_none(vals: list[float]) -> float | None:
    return round(statistics.mean(vals), 4) if vals else None


def _quantile_bins(values: list[float], bin_count: int) -> list[dict[str, Any]]:
    """Compatibilità test: costruisce bin da boundaries Primary-style."""
    boundaries = build_quantile_boundaries(values, bin_count)
    if not values:
        return []
    if not boundaries:
        return [{
            "index": 1,
            "label": "Q1",
            "lower_bound": None,
            "upper_bound": None,
            "lower_inclusive": False,
            "upper_inclusive": True,
            "values": list(values),
        }]
    labels = apply_quantile_boundaries(values, boundaries)
    n_bins = len(boundaries) + 1
    bins: list[dict[str, Any]] = []
    for i in range(n_bins):
        in_bin = [v for v, lab in zip(values, labels) if lab == i]
        if i == 0:
            lo, hi = None, boundaries[0]
            lo_inc, hi_inc = False, False
        elif i == n_bins - 1:
            lo, hi = boundaries[-1], None
            lo_inc, hi_inc = True, True
        else:
            lo, hi = boundaries[i - 1], boundaries[i]
            lo_inc, hi_inc = True, False
        bins.append({
            "index": i + 1,
            "label": bin_label_from_boundaries(i, boundaries),
            "lower_bound": round(lo, 4) if lo is not None else None,
            "upper_bound": round(hi, 4) if hi is not None else None,
            "lower_inclusive": lo_inc,
            "upper_inclusive": hi_inc,
            "values": in_bin,
        })
    return bins


def _enrich_research_features(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    feat_at = _parse_iso_dt(row.get("feature_snapshot_at"))
    kickoff = _parse_kickoff(row)
    if feat_at and kickoff and kickoff >= feat_at:
        hours = round((kickoff - feat_at).total_seconds() / 3600.0, 2)
        out["hours_to_kickoff"] = hours
        if hours <= 24:
            out["hours_to_kickoff_class"] = "<=24h"
        elif hours <= 72:
            out["hours_to_kickoff_class"] = ">24-72h"
        elif hours <= 120:
            out["hours_to_kickoff_class"] = ">72-120h"
        else:
            out["hours_to_kickoff_class"] = ">120h"
    else:
        out["hours_to_kickoff"] = None
        out["hours_to_kickoff_class"] = None

    probs = [_num(row, "prob_1_norm"), _num(row, "prob_x_norm"), _num(row, "prob_2_norm")]
    valid_probs = [p for p in probs if p is not None]
    if len(valid_probs) >= 2:
        ordered = sorted(valid_probs, reverse=True)
        out["dominance_normalized_pp"] = round(max(0.0, ordered[0] - ordered[1]), 2)
    else:
        out["dominance_normalized_pp"] = None

    conv = _num(row, "conviction_index_candidate")
    dom_norm = normalize_outcome_side(row.get("dominant_sign"))
    out["dominant_sign_normalized"] = dom_norm
    if conv is not None and dom_norm == "DRAW":
        out["x_directional_conviction_candidate"] = conv
        out["x_conviction_direction"] = "toward_draw"
    elif conv is not None and dom_norm in ("HOME", "AWAY"):
        out["x_directional_conviction_candidate"] = -conv
        out["x_conviction_direction"] = "against_draw"
    else:
        out["x_directional_conviction_candidate"] = None
        out["x_conviction_direction"] = "unknown"

    pu = _num(row, "prob_under_2_5_cecchino_pct")
    out["under_strength_pp"] = round(pu - 50, 2) if pu is not None else None
    xr = row.get("x_rank")
    out["x_is_top"] = 1 if xr == 1 else 0 if xr is not None else None
    out["x_is_last"] = 1 if xr == 3 else 0 if xr is not None else None

    x_vs = _num(row, "x_vs_best_lateral_pp")
    if x_vs is None:
        out["x_direction_bucket"] = "unknown"
    elif x_vs > 0:
        out["x_direction_bucket"] = "draw_above_laterals"
    elif -3 <= x_vs <= 0:
        out["x_direction_bucket"] = "draw_near_laterals"
    elif x_vs < -3:
        out["x_direction_bucket"] = "draw_below_laterals"
    else:
        out["x_direction_bucket"] = "unknown"
    return out


def _cohort_target_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    draws = sum(1 for r in rows if r.get("draw_ft") == 1)
    n = len(rows)
    kickoffs = [_parse_kickoff(r) for r in rows]
    kickoffs = [k for k in kickoffs if k is not None]
    days = {k.date().isoformat() for k in kickoffs}
    leagues = {r.get("league_name") for r in rows if r.get("league_name")}
    countries = {r.get("country_name") for r in rows if r.get("country_name")}
    span = 0
    if kickoffs:
        span = (max(kickoffs) - min(kickoffs)).days
    return {
        "rows": n,
        "draws": draws,
        "non_draws": n - draws,
        "draw_rate_pct": pct(draws, n),
        "wilson_ci_95": wilson_ci(draws, n),
        "first_kickoff": min(kickoffs).isoformat() if kickoffs else None,
        "last_kickoff": max(kickoffs).isoformat() if kickoffs else None,
        "time_span_days": span,
        "distinct_match_days": len(days),
        "league_count": len(leagues),
        "country_count": len(countries),
    }


def _research_maturity(primary: dict[str, Any], time_span: int) -> dict[str, Any]:
    n = primary["rows"]
    draws = primary["draws"]
    short = time_span < 90
    if n < 300:
        status = "weak_sample"
    elif n < 700:
        status = "exploratory"
    elif n < 1500:
        status = "exploratory_with_reasonable_volume"
    else:
        status = "broader_validation_possible"
    warnings: list[str] = []
    if short:
        warnings.append("short_time_span: periodo osservato inferiore a 90 giorni")
    if n < 300:
        warnings.append("weak_sample: campione inferiore a 300 righe")
    warnings.append("multiple_comparisons_exploratory_analysis")
    return {
        "status": status,
        "sample_size": n,
        "positive_events": draws,
        "time_span_days": time_span,
        "short_time_span": short,
        "fragmented_leagues": primary.get("league_count", 0) > 15,
        "warnings": warnings,
    }


def _descriptive_numeric(rows: list[dict], feature: str) -> dict[str, Any]:
    vals = [_num(r, feature) for r in rows]
    valid = [v for v in vals if v is not None]
    n = len(rows)
    missing = n - len(valid)
    if not valid:
        return {
            "feature": feature,
            "count": 0,
            "missing_count": missing,
            "missing_pct": pct(missing, n),
            "constant_feature": True,
            "feature_family": feature_family(feature),
        }
    unique = len(set(valid))
    q = statistics.quantiles(valid, n=4, method="inclusive") if len(valid) >= 4 else [valid[0], valid[0], valid[-1]]
    return {
        "feature": feature,
        "count": len(valid),
        "missing_count": missing,
        "missing_pct": pct(missing, n),
        "min": round(min(valid), 4),
        "max": round(max(valid), 4),
        "mean": round(statistics.mean(valid), 4),
        "median": round(statistics.median(valid), 4),
        "standard_deviation": round(statistics.pstdev(valid), 4) if len(valid) > 1 else 0.0,
        "q1": round(q[0], 4) if len(q) >= 1 else None,
        "q3": round(q[2], 4) if len(q) >= 3 else None,
        "iqr": round(q[2] - q[0], 4) if len(q) >= 3 else None,
        "unique_values": unique,
        "constant_feature": unique <= 1,
        "feature_family": feature_family(feature),
    }


def _reliability_status(
    count: int,
    draws: int,
    disc_auc: float | None,
    ci_lo: float | None,
    ci_hi: float | None,
) -> str:
    if count < 100 or draws < 20:
        return "insufficient_sample"
    if ci_lo is not None and ci_hi is not None and ci_lo <= 0.5 <= ci_hi:
        return "uncertain"
    if ci_lo is not None and ci_hi is not None and (ci_hi - ci_lo) > 0.25:
        return "uncertain"
    if disc_auc is None:
        return "insufficient_sample"
    if disc_auc < 0.54:
        return "weak"
    if disc_auc < 0.58:
        return "modest"
    return "potentially_useful"


def _build_bins_from_boundaries(
    valid_pairs: list[tuple[int, float]],
    boundaries: list[float],
    *,
    baseline_rate: float,
    min_group_size: int,
) -> tuple[list[dict[str, Any]], list[float | None]]:
    scores = [x for _, x in valid_pairs]
    labels = apply_quantile_boundaries(scores, boundaries)
    n_bins = len(boundaries) + 1 if boundaries else 1
    bin_rows: list[dict[str, Any]] = []
    rates: list[float | None] = []
    for i in range(n_bins):
        in_bin = [(y, x) for (y, x), lab in zip(valid_pairs, labels) if lab == i]
        if not in_bin:
            rates.append(None)
            continue
        d = sum(1 for y, _ in in_bin if y == 1)
        cnt = len(in_bin)
        dr = pct(d, cnt)
        rates.append(dr)
        lo = boundaries[i - 1] if i > 0 and boundaries else None
        hi = boundaries[i] if i < len(boundaries) else None
        bin_rows.append({
            "index": i + 1,
            "label": bin_label_from_boundaries(i, boundaries),
            "lower_bound": round(lo, 4) if lo is not None else None,
            "upper_bound": round(hi, 4) if hi is not None else None,
            "count": cnt,
            "draws": d,
            "non_draws": cnt - d,
            "draw_rate_pct": dr,
            "wilson_ci_95": wilson_ci(d, cnt),
            "lift_vs_baseline_pp": round(dr - baseline_rate, 2),
            "reliable": cnt >= min_group_size,
            "mean_feature_value": round(statistics.mean([x for _, x in in_bin]), 4),
        })
    return bin_rows, rates


def _analyze_numeric_feature(
    rows: list[dict],
    feature: str,
    *,
    baseline_rate: float,
    bin_count: int,
    min_group_size: int,
    bootstrap_iterations: int,
    random_seed: int,
    boundaries: list[float] | None = None,
    boundary_source: str = "cohort",
    timing_acc: dict[str, float] | None = None,
) -> dict[str, Any]:
    pairs = [(r.get("draw_ft", 0), _num(r, feature)) for r in rows]
    valid_pairs = [(int(y), x) for y, x in pairs if x is not None and y in (0, 1)]
    desc = _descriptive_numeric(rows, feature)
    if len(valid_pairs) < 2:
        return {
            **desc,
            "auc": None,
            "directional_auc": None,
            "discriminative_auc": None,
            "bins": [],
            "trend": "insufficient_data",
            "trend_diagnostics": {"reason": "too_few_valid_pairs"},
            "boundaries": boundaries or [],
            "boundary_source": boundary_source,
        }

    y_true = [y for y, _ in valid_pairs]
    scores = [x for _, x in valid_pairs]
    if boundaries is None:
        boundaries = build_quantile_boundaries(scores, bin_count)
        boundary_source = "cohort" if boundary_source == "cohort" else boundary_source

    auc = auc_mann_whitney(y_true, scores)
    disc = max(auc, 1 - auc) if auc is not None else None
    t_boot0 = time.perf_counter()
    boot = bootstrap_auc(y_true, scores, iterations=bootstrap_iterations, seed=random_seed)
    if timing_acc is not None:
        timing_acc["bootstrap_ms"] = timing_acc.get("bootstrap_ms", 0.0) + (time.perf_counter() - t_boot0) * 1000
    pear = pearson_r(scores, [float(y) for y in y_true])
    spear = spearman_rho(scores, [float(y) for y in y_true])

    bin_rows, rates = _build_bins_from_boundaries(
        valid_pairs, boundaries, baseline_rate=baseline_rate, min_group_size=min_group_size,
    )
    trend, trend_diag = classify_trend_with_diagnostics(rates)
    best_dr = max((b["draw_rate_pct"] for b in bin_rows), default=None)
    worst_dr = min((b["draw_rate_pct"] for b in bin_rows), default=None)
    spread = round(best_dr - worst_dr, 2) if best_dr is not None and worst_dr is not None else None
    best_bin = max(bin_rows, key=lambda b: b["draw_rate_pct"], default=None)
    worst_bin = min(bin_rows, key=lambda b: b["draw_rate_pct"], default=None)

    return {
        **desc,
        "directional_auc": round(auc, 4) if auc is not None else None,
        "discriminative_auc": round(disc, 4) if disc is not None else None,
        "pearson": round(pear, 4) if pear is not None else None,
        "spearman": round(spear, 4) if spear is not None else None,
        "bootstrap": boot,
        "bins": bin_rows,
        "actual_bin_count": len(bin_rows),
        "boundaries": [round(b, 4) for b in boundaries],
        "boundary_source": boundary_source,
        "trend": trend,
        "trend_diagnostics": trend_diag,
        "best_bin_draw_rate": best_dr,
        "worst_bin_draw_rate": worst_dr,
        "best_bin_index": best_bin["index"] if best_bin else None,
        "worst_bin_index": worst_bin["index"] if worst_bin else None,
        "spread_pp": spread,
        "reliability_status": _reliability_status(
            len(valid_pairs),
            sum(y_true),
            disc,
            boot.get("discriminative_auc_ci_lower"),
            boot.get("discriminative_auc_ci_upper"),
        ),
    }


def _cat_sort_key(feature: str, val: Any) -> tuple:
    s = str(val) if val is not None else ""
    if feature == "x_rank":
        try:
            return (0, int(val))
        except (TypeError, ValueError):
            return (1, s)
    for order, seq in (
        ("conviction_class_candidate", CONVICTION_ORDER),
        ("f36_class_existing", F36_ORDER),
        ("gap_coherence_class_candidate", GAP_COH_ORDER),
        ("hours_to_kickoff_class", HOURS_CLASS_ORDER),
        ("x_direction_bucket", X_DIRECTION_ORDER),
        ("dominant_sign_normalized", SIGN_ORDER),
        ("x_conviction_direction", ("toward_draw", "against_draw", "unknown")),
    ):
        if feature == order and s in seq:
            return (0, seq.index(s))
    return (1, s)


def _analyze_categorical(
    rows: list[dict],
    feature: str,
    *,
    baseline: float,
    min_group_size: int,
) -> dict[str, Any]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        v = r.get(feature)
        key = str(v) if v is not None else "null"
        groups[key].append(r)
    cats = []
    for cat, grp in sorted(groups.items(), key=lambda x: _cat_sort_key(feature, x[0])):
        d = sum(1 for r in grp if r.get("draw_ft") == 1)
        n = len(grp)
        dr = pct(d, n)
        cats.append({
            "category": cat,
            "count": n,
            "percentage": pct(n, len(rows)),
            "draws": d,
            "draw_rate_pct": dr,
            "wilson_ci_95": wilson_ci(d, n),
            "lift_vs_baseline_pp": round(dr - baseline, 2),
            "reliable": n >= min_group_size,
        })
    reliable = [c for c in cats if c["reliable"]]
    spread = None
    if len(reliable) >= 2:
        spread = round(
            max(c["draw_rate_pct"] for c in reliable) - min(c["draw_rate_pct"] for c in reliable),
            2,
        )
    return {"feature": feature, "categories": cats, "reliable_spread_pp": spread}


def _expected_calibration_error(probs: list[float], y_true: list[int], bin_count: int = 5) -> float | None:
    if len(probs) < 2:
        return None
    boundaries = build_quantile_boundaries(probs, bin_count)
    labels = apply_quantile_boundaries(probs, boundaries)
    n_bins = len(boundaries) + 1 if boundaries else 1
    total = 0
    ece = 0.0
    for i in range(n_bins):
        idx = [j for j, lab in enumerate(labels) if lab == i]
        if not idx:
            continue
        w = len(idx)
        total += w
        pred = statistics.mean([probs[j] for j in idx])
        actual = statistics.mean([y_true[j] for j in idx])
        ece += w * abs(pred - actual)
    return ece / total if total else None


def _calibration_block(rows: list[dict], prob_key: str, label: str) -> dict[str, Any]:
    pairs: list[tuple[float, int]] = []
    for r in rows:
        p = _num(r, prob_key)
        if p is not None:
            pairs.append((clamp_prob(p / 100.0 if p > 1 else p), int(r.get("draw_ft", 0))))
    if not pairs:
        return {"label": label, "rows": 0}
    probs = [p for p, _ in pairs]
    y = [t for _, t in pairs]
    base_rate = statistics.mean(y)
    brier = brier_score(probs, y)
    brier_base = base_rate * (1 - base_rate)
    bss = 1 - (brier / brier_base) if brier is not None and brier_base > 0 else None
    ll = log_loss_score(probs, y)
    auc = auc_mann_whitney(y, probs)
    ece = _expected_calibration_error(probs, y)
    cal_bins = []
    boundaries = build_quantile_boundaries(probs, 5)
    labels = apply_quantile_boundaries(probs, boundaries)
    n_bins = len(boundaries) + 1 if boundaries else 1
    for i in range(n_bins):
        idx = [j for j, lab in enumerate(labels) if lab == i]
        if not idx:
            continue
        pred = statistics.mean([probs[j] for j in idx])
        actual = statistics.mean([y[j] for j in idx])
        cal_bins.append({
            "predicted_mean": round(pred, 4),
            "actual_rate": round(actual, 4),
            "count": len(idx),
            "calibration_gap": round(abs(pred - actual), 4),
        })
    return {
        "label": label,
        "rows": len(pairs),
        "brier_score": round(brier, 4) if brier is not None else None,
        "brier_baseline": round(brier_base, 4),
        "brier_skill_score": round(bss, 4) if bss is not None else None,
        "log_loss": round(ll, 4) if ll is not None else None,
        "auc": round(auc, 4) if auc is not None else None,
        "ece": round(ece, 4) if ece is not None else None,
        "calibration_bins": cal_bins,
    }


def _redundancy_analysis(rows: list[dict]) -> dict[str, Any]:
    features = list(CORRELATION_FEATURES)
    matrix_p: dict[str, dict[str, float | None]] = {}
    matrix_s: dict[str, dict[str, float | None]] = {}
    pairs: list[dict] = []
    for fa in features:
        matrix_p[fa] = {}
        matrix_s[fa] = {}
        for fb in features:
            xs = [_num(r, fa) for r in rows]
            ys = [_num(r, fb) for r in rows]
            common = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
            if len(common) < 3:
                matrix_p[fa][fb] = None
                matrix_s[fa][fb] = None
                continue
            cx = [x for x, _ in common]
            cy = [y for _, y in common]
            pr = pearson_r(cx, cy)
            sr = spearman_rho(cx, cy)
            matrix_p[fa][fb] = round(pr, 4) if pr is not None else None
            matrix_s[fa][fb] = round(sr, 4) if sr is not None else None
            if fa < fb and pr is not None:
                absp = abs(pr)
                abss = abs(sr) if sr is not None else 0
                if absp >= 0.85 or abss >= 0.85:
                    level = "very_high" if max(absp, abss) >= 0.90 else "high"
                elif max(absp, abss) >= 0.80:
                    level = "high"
                elif max(absp, abss) >= 0.60:
                    level = "moderate"
                else:
                    level = "low"
                rec = "keep_one_candidate" if max(absp, abss) >= 0.85 else "no_clear_redundancy"
                pairs.append({
                    "feature_a": fa,
                    "feature_b": fb,
                    "pearson": round(pr, 4),
                    "spearman": round(sr, 4) if sr is not None else None,
                    "common_rows": len(common),
                    "redundancy_level": level,
                    "recommendation": rec,
                    "feature_a_family": feature_family(fa),
                    "feature_b_family": feature_family(fb),
                })
    groups = [{"features": list(g), "expected": True} for g in EXPECTED_REDUNDANCY_GROUPS]
    return {
        "pearson_matrix": matrix_p,
        "spearman_matrix": matrix_s,
        "pairs": pairs,
        "candidate_groups": groups,
        "feature_families": FEATURE_FAMILIES,
    }


def _row_cat_value(row: dict, dim: str) -> str:
    v = row.get(dim)
    return str(v) if v is not None else "null"


def _column_category_for_row(
    row: dict,
    *,
    column_dimension: str,
    column_type: str,
    boundaries: list[float],
) -> str | None:
    if column_type == "categorical":
        return _row_cat_value(row, column_dimension)
    val = _num(row, column_dimension)
    if val is None:
        return None
    lab = apply_quantile_boundaries([val], boundaries)[0]
    return bin_label_from_boundaries(lab, boundaries)


def _build_interaction_cells(
    rows: list[dict],
    *,
    row_dimension: str,
    column_dimension: str,
    column_type: str,
    boundaries: list[float],
    baseline: float,
    min_group_size: int,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        row_cat = _row_cat_value(r, row_dimension)
        col_cat = _column_category_for_row(
            r,
            column_dimension=column_dimension,
            column_type=column_type,
            boundaries=boundaries,
        )
        if col_cat is None:
            continue
        buckets[(row_cat, col_cat)].append(r)

    cells: list[dict[str, Any]] = []
    for (row_cat, col_cat), grp in sorted(
        buckets.items(),
        key=lambda x: (_cat_sort_key(row_dimension, x[0][0]), x[0][1]),
    ):
        n = len(grp)
        d = sum(1 for r in grp if r.get("draw_ft") == 1)
        reliable = n >= min_group_size and d >= 5
        suppressed = not reliable
        reason = None
        if suppressed:
            if n < min_group_size:
                reason = "count_below_min_group_size"
            elif d < 5:
                reason = "draws_below_5"
        dr = pct(d, n)
        cell: dict[str, Any] = {
            "row_category": row_cat,
            "column_category": col_cat,
            "count": n,
            "draws": d,
            "non_draws": n - d,
            "reliable": reliable,
            "suppressed": suppressed,
            "suppression_reason": reason,
        }
        if not suppressed:
            cell.update({
                "draw_rate_pct": dr,
                "wilson_ci_95": wilson_ci(d, n),
                "lift_vs_baseline_pp": round(dr - baseline, 2),
            })
        else:
            cell.update({
                "draw_rate_pct": dr if n > 0 else None,
                "wilson_ci_95": wilson_ci(d, n) if n > 0 else None,
                "lift_vs_baseline_pp": round(dr - baseline, 2) if n > 0 else None,
            })
        cells.append(cell)
    return cells


def _interaction_analysis(
    primary: list[dict],
    sensitivity: list[dict],
    *,
    primary_boundaries: dict[str, list[float]],
    baseline_primary: float,
    baseline_sensitivity: float,
    min_group_size: int,
    bin_count: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in INTERACTION_SPECS:
        col = spec["column_dimension"]
        if spec["column_type"] == "quantile":
            boundaries = primary_boundaries.get(col)
            if boundaries is None:
                vals = [v for v in (_num(r, col) for r in primary) if v is not None]
                boundaries = build_quantile_boundaries(vals, bin_count)
            boundary_source = "primary"
        else:
            boundaries = []
            boundary_source = "categorical"

        p_cells = _build_interaction_cells(
            primary,
            row_dimension=spec["row_dimension"],
            column_dimension=col,
            column_type=spec["column_type"],
            boundaries=boundaries,
            baseline=baseline_primary,
            min_group_size=min_group_size,
        )
        s_cells = _build_interaction_cells(
            sensitivity,
            row_dimension=spec["row_dimension"],
            column_dimension=col,
            column_type=spec["column_type"],
            boundaries=boundaries,
            baseline=baseline_sensitivity,
            min_group_size=min_group_size,
        )
        reliable_p = sum(1 for c in p_cells if c["reliable"])
        suppressed_p = sum(1 for c in p_cells if c["suppressed"])
        out.append({
            "interaction_key": spec["interaction_key"],
            "label": spec["label"],
            "row_dimension": spec["row_dimension"],
            "column_dimension": col,
            "boundary_source": boundary_source,
            "column_boundaries": [round(b, 4) for b in boundaries],
            "primary_cells": p_cells,
            "sensitivity_cells": s_cells,
            "summary": {
                "primary_cell_count": len(p_cells),
                "sensitivity_cell_count": len(s_cells),
                "primary_reliable_cells": reliable_p,
                "primary_suppressed_cells": suppressed_p,
            },
        })
    return out


def _candidate_patterns(
    interactions: list[dict[str, Any]],
    *,
    baseline_primary: float,
    min_group_size: int,
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for ix in interactions:
        sens_map = {
            (c["row_category"], c["column_category"]): c
            for c in ix.get("sensitivity_cells", [])
        }
        for cell in ix.get("primary_cells", []):
            if cell.get("suppressed"):
                continue
            n = cell["count"]
            d = cell["draws"]
            lift = cell.get("lift_vs_baseline_pp")
            ci = cell.get("wilson_ci_95") or {}
            if n < min_group_size or d < 10 or lift is None or abs(lift) < 5:
                continue
            if ci.get("lower_pct") is None or ci.get("upper_pct") is None:
                continue

            sc = sens_map.get((cell["row_category"], cell["column_category"]))
            warnings: list[str] = []
            direction_consistent = False
            rate_delta = None
            sens_count = 0
            sens_dr = None
            sens_lift = None

            if sc is None:
                warnings.append("missing_sensitivity_cell")
                stability = "insufficient"
            else:
                sens_count = sc["count"]
                sens_dr = sc.get("draw_rate_pct")
                sens_lift = sc.get("lift_vs_baseline_pp")
                primary_dr = cell.get("draw_rate_pct")
                if primary_dr is not None and sens_dr is not None:
                    rate_delta = round(primary_dr - sens_dr, 2)
                same_dir = (
                    sens_lift is not None
                    and ((lift > 0 and sens_lift > 0) or (lift < 0 and sens_lift < 0))
                )
                direction_consistent = bool(same_dir)
                count_ok = sens_count >= min_group_size or (n > 0 and sens_count >= 0.8 * n)
                if not direction_consistent:
                    stability = "unstable"
                    warnings.append("sensitivity_lift_direction_mismatch")
                elif rate_delta is not None and abs(rate_delta) > 7:
                    stability = "unstable"
                    warnings.append("rate_delta_above_7pp")
                elif not count_ok:
                    stability = "insufficient"
                    warnings.append("sensitivity_count_insufficient")
                else:
                    lo = ci.get("lower_pct")
                    hi = ci.get("upper_pct")
                    baseline_outside = (
                        lo is not None and hi is not None and not (lo <= baseline_primary <= hi)
                    )
                    if baseline_outside:
                        stability = "stronger_candidate"
                    else:
                        stability = "exploratory_candidate"

            lo = ci.get("lower_pct")
            hi = ci.get("upper_pct")
            evidence = (
                "baseline_outside_ci"
                if lo is not None and hi is not None and not (lo <= baseline_primary <= hi)
                else "overlapping_ci"
            )
            patterns.append({
                "pattern_key": (
                    f"{ix['interaction_key']}__{cell['row_category']}__{cell['column_category']}"
                ),
                "interaction_key": ix["interaction_key"],
                "description": (
                    f"{ix['row_dimension']}={cell['row_category']} × "
                    f"{ix['column_dimension']}={cell['column_category']}"
                ),
                "primary_count": n,
                "primary_draws": d,
                "primary_draw_rate_pct": cell.get("draw_rate_pct"),
                "primary_lift_pp": lift,
                "primary_ci": ci,
                "sensitivity_count": sens_count,
                "sensitivity_draw_rate_pct": sens_dr,
                "sensitivity_lift_pp": sens_lift,
                "direction_consistent": direction_consistent,
                "rate_delta_pp": rate_delta,
                "evidence_status": evidence,
                "stability_status": stability,
                "warnings": warnings,
            })
    return patterns


def _auc_direction(auc: float | None) -> str | None:
    if auc is None:
        return None
    if auc > 0.5:
        return "positive"
    if auc < 0.5:
        return "negative"
    return "neutral"


def _pvs_stability(
    *,
    primary_auc: float | None,
    sens_auc: float | None,
    primary_trend: str | None,
    sens_trend: str | None,
) -> str:
    if primary_auc is None or sens_auc is None:
        return "insufficient"
    delta = abs(sens_auc - primary_auc)
    same_dir = _auc_direction(primary_auc) == _auc_direction(sens_auc)
    nonlinear = {"u_shaped", "inverted_u", "irregular"}
    trend_ok = (
        primary_trend == sens_trend
        or (primary_trend in nonlinear and sens_trend in nonlinear)
    )
    if not same_dir or delta > 0.04 or (
        primary_trend and sens_trend and primary_trend != sens_trend
        and not (primary_trend in nonlinear and sens_trend in nonlinear)
        and delta > 0.02
    ):
        if not same_dir or delta > 0.04:
            return "unstable"
    if delta <= 0.02 and same_dir and trend_ok:
        return "stable"
    if delta <= 0.04 and same_dir:
        return "mostly_stable"
    if not same_dir or delta > 0.04:
        return "unstable"
    return "mostly_stable"


def _primary_vs_sensitivity(
    primary_numeric: list[dict],
    sens_numeric: list[dict],
    primary_cat: list[dict],
    sens_cat: list[dict],
    sens_only: list[dict],
    primary: list[dict],
) -> dict[str, Any]:
    pmap = {x["feature"]: x for x in primary_numeric}
    smap = {x["feature"]: x for x in sens_numeric}
    comparisons: list[dict[str, Any]] = []
    for f in NUMERIC_FEATURES:
        pa = pmap.get(f, {})
        sa = smap.get(f, {})
        p_auc = pa.get("directional_auc")
        s_auc = sa.get("directional_auc")
        auc_delta = round(s_auc - p_auc, 4) if p_auc is not None and s_auc is not None else None
        p_dir = _auc_direction(p_auc)
        s_dir = _auc_direction(s_auc)
        best_dir_ok = None
        if pa.get("best_bin_index") is not None and sa.get("best_bin_index") is not None:
            best_dir_ok = pa.get("best_bin_index") == sa.get("best_bin_index")
        spread_delta = None
        if pa.get("spread_pp") is not None and sa.get("spread_pp") is not None:
            spread_delta = round(sa["spread_pp"] - pa["spread_pp"], 2)
        status = _pvs_stability(
            primary_auc=p_auc,
            sens_auc=s_auc,
            primary_trend=pa.get("trend"),
            sens_trend=sa.get("trend"),
        )
        comparisons.append({
            "feature": f,
            "type": "numeric",
            "primary_count": pa.get("count"),
            "sensitivity_count": sa.get("count"),
            "primary_missing_pct": pa.get("missing_pct"),
            "sensitivity_missing_pct": sa.get("missing_pct"),
            "primary_directional_auc": p_auc,
            "sensitivity_directional_auc": s_auc,
            "primary_discriminative_auc": pa.get("discriminative_auc"),
            "sensitivity_discriminative_auc": sa.get("discriminative_auc"),
            "auc_delta": auc_delta,
            "primary_auc": p_auc,
            "sensitivity_auc": s_auc,
            "primary_trend": pa.get("trend"),
            "sensitivity_trend": sa.get("trend"),
            "direction_consistent": p_dir == s_dir if p_dir and s_dir else None,
            "trend_consistent": pa.get("trend") == sa.get("trend"),
            "spread_delta": spread_delta,
            "best_bin_direction_consistent": best_dir_ok,
            "stability_status": status,
            "boundary_source": "primary",
            "feature_family": feature_family(f),
            "notes": [],
        })

    pcmap = {x["feature"]: x for x in primary_cat}
    scmap = {x["feature"]: x for x in sens_cat}
    for f in PVS_CATEGORICAL_FEATURES:
        pa = pcmap.get(f, {})
        sa = scmap.get(f, {})
        p_spread = pa.get("reliable_spread_pp")
        s_spread = sa.get("reliable_spread_pp")
        comparisons.append({
            "feature": f,
            "type": "categorical",
            "primary_reliable_spread_pp": p_spread,
            "sensitivity_reliable_spread_pp": s_spread,
            "spread_delta": round(s_spread - p_spread, 2) if p_spread is not None and s_spread is not None else None,
            "stability_status": (
                "stable"
                if p_spread is not None and s_spread is not None and abs(s_spread - p_spread) <= 3
                else "mostly_stable"
                if p_spread is not None and s_spread is not None and abs(s_spread - p_spread) <= 7
                else "insufficient"
                if p_spread is None or s_spread is None
                else "unstable"
            ),
            "notes": [],
        })

    so_draws = sum(1 for r in sens_only if r.get("draw_ft") == 1)
    so_n = len(sens_only)
    elig = Counter(str(r.get("eligibility_status_feature") or r.get("eligibility_status") or "null") for r in sens_only)
    elig_reason = Counter(
        str(r.get("eligibility_reason") or r.get("eligibility_reason_feature") or "null")
        for r in sens_only
        if r.get("eligibility_reason") is not None or r.get("eligibility_reason_feature") is not None
    )
    p_means = {
        "mean_prob_x_norm": _mean_or_none([v for v in (_num(r, "prob_x_norm") for r in primary) if v is not None]),
        "mean_under": _mean_or_none(
            [v for v in (_num(r, "prob_under_2_5_cecchino_pct") for r in primary) if v is not None]
        ),
        "mean_f36_abs": _mean_or_none([v for v in (_num(r, "f36_abs") for r in primary) if v is not None]),
        "mean_directional_conviction": _mean_or_none(
            [v for v in (_num(r, "x_directional_conviction_candidate") for r in primary) if v is not None]
        ),
    }
    so_means = {
        "mean_prob_x_norm": _mean_or_none(
            [v for v in (_num(r, "prob_x_norm") for r in sens_only) if v is not None]
        ),
        "mean_under": _mean_or_none(
            [v for v in (_num(r, "prob_under_2_5_cecchino_pct") for r in sens_only) if v is not None]
        ),
        "mean_f36_abs": _mean_or_none([v for v in (_num(r, "f36_abs") for r in sens_only) if v is not None]),
        "mean_directional_conviction": _mean_or_none(
            [v for v in (_num(r, "x_directional_conviction_candidate") for r in sens_only) if v is not None]
        ),
    }
    return {
        "feature_comparisons": comparisons,
        "sensitivity_only_fixtures": {
            "count": so_n,
            "draws": so_draws,
            "non_draws": so_n - so_draws,
            "draw_rate_pct": pct(so_draws, so_n),
            "wilson_ci_95": wilson_ci(so_draws, so_n),
            "eligibility_status_distribution": dict(elig),
            "eligibility_reason_distribution": dict(elig_reason) if elig_reason else None,
            "means": so_means,
            "primary_means_for_comparison": p_means,
        },
    }


def _feature_means(rows: list[dict]) -> dict[str, float | None]:
    keys = (
        "prob_x_norm",
        "prob_under_2_5_cecchino_pct",
        "f36_abs",
        "x_directional_conviction_candidate",
    )
    return {
        f"mean_{k}": _mean_or_none([v for v in (_num(r, k) for r in rows) if v is not None])
        for k in keys
    }


def _block_aucs(rows: list[dict]) -> dict[str, float | None]:
    n = len(rows)
    draws = sum(1 for r in rows if r.get("draw_ft") == 1)
    if n < 50 or draws < 10 or draws == n:
        return {f: None for f in TEMPORAL_AUC_FEATURES}
    out: dict[str, float | None] = {}
    for f in TEMPORAL_AUC_FEATURES:
        pairs = [(int(r.get("draw_ft", 0)), _num(r, f)) for r in rows]
        valid = [(y, x) for y, x in pairs if x is not None and y in (0, 1)]
        if len(valid) < 2:
            out[f] = None
            continue
        y = [a for a, _ in valid]
        s = [b for _, b in valid]
        if len(set(y)) < 2:
            out[f] = None
            continue
        a = auc_mann_whitney(y, s)
        out[f] = round(a, 4) if a is not None else None
    return out


def _temporal_stability(primary: list[dict], time_span: int) -> dict[str, Any]:
    dated = [(r, _parse_kickoff(r)) for r in primary]
    dated = [(r, k) for r, k in dated if k is not None]
    dated.sort(key=lambda x: x[1])

    weeks: dict[str, list[dict]] = defaultdict(list)
    for r, k in dated:
        iso = k.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        weeks[week_key].append(r)

    week_rows = []
    for week_key in sorted(weeks.keys()):
        grp = weeks[week_key]
        kicks = [_parse_kickoff(r) for r in grp]
        kicks = [k for k in kicks if k is not None]
        d = sum(1 for r in grp if r.get("draw_ft") == 1)
        n = len(grp)
        week_rows.append({
            "week_key": week_key,
            "first_date": min(kicks).date().isoformat() if kicks else None,
            "last_date": max(kicks).date().isoformat() if kicks else None,
            "rows": n,
            "draws": d,
            "draw_rate_pct": pct(d, n),
            "wilson_ci_95": wilson_ci(d, n),
            **_feature_means(grp),
        })

    blocks: list[dict[str, Any]] = []
    n = len(dated)
    if n:
        cuts = [0, n // 3, (2 * n) // 3, n]
        names = ("early", "middle", "late")
        for i, name in enumerate(names):
            chunk = [r for r, _ in dated[cuts[i]:cuts[i + 1]]]
            if not chunk:
                continue
            kicks = [_parse_kickoff(r) for r in chunk]
            kicks = [k for k in kicks if k is not None]
            d = sum(1 for r in chunk if r.get("draw_ft") == 1)
            cn = len(chunk)
            aucs = _block_aucs(chunk)
            blocks.append({
                "block": name,
                "rows": cn,
                "date_from": min(kicks).date().isoformat() if kicks else None,
                "date_to": max(kicks).date().isoformat() if kicks else None,
                "draws": d,
                "draw_rate_pct": pct(d, cn),
                "wilson_ci_95": wilson_ci(d, cn),
                **_feature_means(chunk),
                "feature_aucs": aucs,
            })

    consistency: dict[str, Any] = {}
    for f in TEMPORAL_AUC_FEATURES:
        vals = [b["feature_aucs"].get(f) for b in blocks if b["feature_aucs"].get(f) is not None]
        if len(vals) < 2:
            consistency[f] = {
                "temporal_direction_consistency": None,
                "temporal_auc_range": None,
                "interpretation": "insufficient_block_auc",
            }
            continue
        dirs = [_auc_direction(v) for v in vals]
        consistency[f] = {
            "temporal_direction_consistency": len(set(dirs)) == 1,
            "temporal_auc_range": round(max(vals) - min(vals), 4),
            "interpretation": "consistent_direction" if len(set(dirs)) == 1 else "direction_varies",
        }

    return {
        "short_observation_window": time_span < 90,
        "time_span_days": time_span,
        "iso_weeks": week_rows,
        "chronological_blocks": blocks,
        "feature_temporal_consistency": consistency,
        "note": "analisi descrittiva within-sample, non out-of-sample",
    }


def _league_stability(primary: list[dict], *, min_group_size: int) -> dict[str, Any]:
    by_league: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in primary:
        league = str(r.get("league_name") or "unknown")
        country = str(r.get("country_name") or "unknown")
        by_league[(country, league)].append(r)

    ranked = sorted(by_league.items(), key=lambda x: (-len(x[1]), x[0][1]))
    total = len(primary)
    counts = [len(v) for _, v in ranked]
    hhi = herfindahl(counts) if counts else 0.0
    top5 = pct(sum(counts[:5]), total) if counts else 0.0
    top10 = pct(sum(counts[:10]), total) if counts else 0.0

    top15 = ranked[:15]
    others_rows: list[dict] = []
    for _, rows in ranked[15:]:
        others_rows.extend(rows)

    league_rows = []
    for (country, league), rows in top15:
        d = sum(1 for r in rows if r.get("draw_ft") == 1)
        n = len(rows)
        league_rows.append({
            "country_name": country,
            "league_name": league,
            "rows": n,
            "percentage_dataset": pct(n, total),
            "draws": d,
            "draw_rate_pct": pct(d, n),
            "wilson_ci_95": wilson_ci(d, n),
            **_feature_means(rows),
            "is_others": False,
        })
    if others_rows:
        d = sum(1 for r in others_rows if r.get("draw_ft") == 1)
        n = len(others_rows)
        league_rows.append({
            "country_name": "Altri",
            "league_name": "Altri",
            "rows": n,
            "percentage_dataset": pct(n, total),
            "draws": d,
            "draw_rate_pct": pct(d, n),
            "wilson_ci_95": wilson_ci(d, n),
            **_feature_means(others_rows),
            "is_others": True,
        })

    reliable = sum(1 for _, rows in ranked if len(rows) >= min_group_size)
    return {
        "leagues": league_rows,
        "top_5_share_pct": top5,
        "top_10_share_pct": top10,
        "hhi": round(hhi, 6),
        "concentration_status": hhi_concentration_status(hhi),
        "fragmented_leagues": len(ranked) > 15,
        "reliable_league_count": reliable,
        "league_count": len(ranked),
        "note": "campionato non usato come feature predittiva",
    }


def _bet_profits(rows: list[dict]) -> list[tuple[dict, float, float]]:
    out: list[tuple[dict, float, float]] = []
    for r in rows:
        odd = _num(r, "quota_book_x")
        if odd is None or odd <= 1:
            continue
        profit = (odd - 1.0) if r.get("draw_ft") == 1 else -1.0
        out.append((r, odd, profit))
    return out


def _roi_from_bets(
    bets: list[tuple[dict, float, float]],
    *,
    group_key: str,
    label: str,
    boundary_source: str,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    if not bets:
        return {
            "group_key": group_key,
            "label": label,
            "boundary_source": boundary_source,
            "count": 0,
            "roi_pct": None,
            "reliable": False,
            "warnings": ["no_bets"],
        }
    profits = [p for _, _, p in bets]
    odds = [o for _, o, _ in bets]
    wins = sum(1 for p in profits if p > 0)
    losses = sum(1 for p in profits if p <= 0)
    stake = len(profits)
    net = sum(profits)
    gross = sum(o if p > 0 else 0.0 for (_, o, p) in bets)
    roi = pct(net, stake)
    boot = bootstrap_roi(profits, iterations=bootstrap_iterations, seed=seed) if stake >= 50 else None
    crosses = bool(boot["crosses_zero"]) if boot else None
    reliable = stake >= 50 and boot is not None and not boot["crosses_zero"]
    warnings = ["theoretical_historical_roi", "multiple_comparisons_risk"]
    if stake < 50:
        warnings.append("sample_below_50")
    if crosses:
        warnings.append("ci_crosses_zero")
    return {
        "group_key": group_key,
        "label": label,
        "boundary_source": boundary_source,
        "count": stake,
        "bets": stake,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": pct(wins, stake),
        "average_book_odd": round(statistics.mean(odds), 4),
        "median_book_odd": round(statistics.median(odds), 4),
        "minimum_book_odd": round(min(odds), 4),
        "maximum_book_odd": round(max(odds), 4),
        "total_stake": stake,
        "gross_return": round(gross, 4),
        "net_profit": round(net, 4),
        "roi_pct": roi,
        "bootstrap_roi_ci_95": boot,
        "ci_crosses_zero": crosses,
        "reliable": reliable,
        "warnings": warnings,
    }


def _roi_global(
    market: list[dict],
    *,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    bets = _bet_profits(market)
    base = _roi_from_bets(
        bets,
        group_key="market_global",
        label="Market ROI globale (quota_book_x)",
        boundary_source="market_subset",
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    base["warnings"] = list(dict.fromkeys(
        base.get("warnings", []) + ["theoretical_historical_roi", "no_transaction_costs", "short_sample"]
    ))
    return base


def _roi_breakdown(
    market: list[dict],
    patterns: list[dict[str, Any]],
    *,
    bin_count: int,
    bootstrap_iterations: int,
    seed: int,
) -> list[dict[str, Any]]:
    bets = _bet_profits(market)
    if not bets:
        return []

    dimensions: list[dict[str, Any]] = []

    def add_quantile_dim(feature: str, dim_key: str) -> None:
        vals = [v for v in (_num(r, feature) for r, _, _ in bets) if v is not None]
        boundaries = build_quantile_boundaries(vals, bin_count)
        groups: dict[int, list[tuple[dict, float, float]]] = defaultdict(list)
        for r, odd, profit in bets:
            v = _num(r, feature)
            if v is None:
                continue
            lab = apply_quantile_boundaries([v], boundaries)[0]
            groups[lab].append((r, odd, profit))
        n_bins = len(boundaries) + 1 if boundaries else 1
        for i in range(n_bins):
            label = bin_label_from_boundaries(i, boundaries)
            dimensions.append(
                _roi_from_bets(
                    groups.get(i, []),
                    group_key=f"{dim_key}__q{i + 1}",
                    label=f"{feature} {label}",
                    boundary_source="market_subset",
                    bootstrap_iterations=bootstrap_iterations,
                    seed=seed + i + (sum(ord(c) for c in dim_key) % 1000),
                )
            )

    add_quantile_dim("prob_x_norm", "prob_x_norm")
    add_quantile_dim("prob_under_2_5_cecchino_pct", "prob_under")
    add_quantile_dim("deviation_x_pp", "deviation_x")

    for cat_feature, order in (
        ("x_rank", None),
        ("dominant_sign_normalized", SIGN_ORDER),
        ("conviction_class_candidate", CONVICTION_ORDER),
        ("f36_class_existing", F36_ORDER),
        ("hours_to_kickoff_class", HOURS_CLASS_ORDER),
    ):
        groups: dict[str, list[tuple[dict, float, float]]] = defaultdict(list)
        for r, odd, profit in bets:
            groups[_row_cat_value(r, cat_feature)].append((r, odd, profit))
        keys = list(groups.keys())
        if order:
            keys = sorted(keys, key=lambda k: _cat_sort_key(cat_feature, k))
        else:
            keys = sorted(keys, key=lambda k: _cat_sort_key(cat_feature, k))
        for j, key in enumerate(keys):
            dimensions.append(
                _roi_from_bets(
                    groups[key],
                    group_key=f"{cat_feature}__{key}",
                    label=f"{cat_feature}={key}",
                    boundary_source="categorical",
                    bootstrap_iterations=bootstrap_iterations,
                    seed=seed + 200 + j,
                )
            )

    # Pattern ROI su Market: match cella via dimensioni note dove possibile
    for pi, pat in enumerate(patterns):
        ix_key = pat["interaction_key"]
        spec = next((s for s in INTERACTION_SPECS if s["interaction_key"] == ix_key), None)
        if not spec:
            continue
        # description contains row=… × col=…
        row_cat = pat["description"].split(" × ")[0].split("=", 1)[-1]
        col_cat = pat["description"].split(" × ")[1].split("=", 1)[-1] if " × " in pat["description"] else ""
        matched: list[tuple[dict, float, float]] = []
        if spec["column_type"] == "quantile":
            vals = [v for v in (_num(r, spec["column_dimension"]) for r, _, _ in bets) if v is not None]
            boundaries = build_quantile_boundaries(vals, bin_count)
            for r, odd, profit in bets:
                if _row_cat_value(r, spec["row_dimension"]) != row_cat:
                    continue
                col = _column_category_for_row(
                    r,
                    column_dimension=spec["column_dimension"],
                    column_type="quantile",
                    boundaries=boundaries,
                )
                if col == col_cat:
                    matched.append((r, odd, profit))
        else:
            for r, odd, profit in bets:
                if (
                    _row_cat_value(r, spec["row_dimension"]) == row_cat
                    and _row_cat_value(r, spec["column_dimension"]) == col_cat
                ):
                    matched.append((r, odd, profit))
        dimensions.append(
            _roi_from_bets(
                matched,
                group_key=f"pattern__{pat['pattern_key']}",
                label=f"pattern: {pat['description']}",
                boundary_source="market_subset",
                bootstrap_iterations=bootstrap_iterations,
                seed=seed + 500 + pi,
            )
        )

    return dimensions


def _market_analysis(
    market: list[dict],
    patterns: list[dict[str, Any]],
    *,
    bin_count: int,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    cal_c = _calibration_block(market, "prob_x_norm", "Cecchino X Market")
    cal_b = _calibration_block(market, "prob_book_x_norm", "Book X Market")

    signed: list[float] = []
    abs_dev: list[float] = []
    gt = lt = eq = 0
    compared = 0
    for r in market:
        cx = _num(r, "prob_x_norm")
        bx = _num(r, "prob_book_x_norm")
        if cx is None or bx is None:
            continue
        compared += 1
        diff = cx - bx
        signed.append(diff)
        abs_dev.append(abs(diff))
        if abs(diff) <= 0.5:
            eq += 1
        elif diff > 0:
            gt += 1
        else:
            lt += 1

    def _delta(a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return round(a - b, 4)

    comparison = {
        "rows_compared": compared,
        "delta_brier": _delta(cal_c.get("brier_score"), cal_b.get("brier_score")),
        "delta_brier_skill_score": _delta(cal_c.get("brier_skill_score"), cal_b.get("brier_skill_score")),
        "delta_log_loss": _delta(cal_c.get("log_loss"), cal_b.get("log_loss")),
        "delta_auc": _delta(cal_c.get("auc"), cal_b.get("auc")),
        "delta_ece": _delta(cal_c.get("ece"), cal_b.get("ece")),
        "pct_cecchino_gt_book": pct(gt, compared),
        "pct_cecchino_lt_book": pct(lt, compared),
        "pct_approximately_equal_0_5pp": pct(eq, compared),
        "mean_signed_deviation_x": _mean_or_none(signed),
        "median_signed_deviation_x": round(statistics.median(signed), 4) if signed else None,
        "mean_absolute_deviation_x": _mean_or_none(abs_dev),
        "median_absolute_deviation_x": round(statistics.median(abs_dev), 4) if abs_dev else None,
    }

    roi = _roi_global(market, bootstrap_iterations=bootstrap_iterations, seed=seed)
    roi_breakdown = _roi_breakdown(
        market,
        patterns,
        bin_count=bin_count,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed + 17,
    )
    return {
        "cecchino": cal_c,
        "book": cal_b,
        "comparison": comparison,
        "roi": roi,
        "roi_breakdown": roi_breakdown,
        "warnings": [
            "theoretical_historical_roi",
            "no_transaction_costs",
            "no_slippage",
            "multiple_comparisons_risk",
            "exploratory_not_production",
        ],
    }


def _leaderboard_row(na: dict[str, Any], stability: str | None = None) -> dict[str, Any]:
    return {
        "feature": na["feature"],
        "type": "numeric",
        "count": na.get("count"),
        "missing_pct": na.get("missing_pct"),
        "directional_auc": na.get("directional_auc"),
        "discriminative_auc": na.get("discriminative_auc"),
        "bootstrap": na.get("bootstrap"),
        "pearson": na.get("pearson"),
        "spearman": na.get("spearman"),
        "trend": na.get("trend"),
        "trend_diagnostics": na.get("trend_diagnostics"),
        "best_bin_draw_rate": na.get("best_bin_draw_rate"),
        "worst_bin_draw_rate": na.get("worst_bin_draw_rate"),
        "spread_pp": na.get("spread_pp"),
        "reliability_status": na.get("reliability_status"),
        "stability_status": stability,
        "feature_family": feature_family(na["feature"]),
        "interpretation": (
            f"Trend {na.get('trend')}, discriminative AUC {na.get('discriminative_auc')}"
        ),
    }


def _research_conclusions(
    leaderboard: list[dict],
    redundancy: dict,
    maturity: dict,
    pvs: dict,
    patterns: list[dict],
) -> dict[str, Any]:
    useful = [x["feature"] for x in leaderboard if x.get("reliability_status") == "potentially_useful"]
    modest = [x["feature"] for x in leaderboard if x.get("reliability_status") == "modest"]
    weak = [
        x["feature"]
        for x in leaderboard
        if x.get("reliability_status") in ("weak", "uncertain", "insufficient_sample")
    ]
    nonlinear = [
        x["feature"]
        for x in leaderboard
        if x.get("trend") in ("u_shaped", "inverted_u", "irregular")
    ]
    unstable = [
        c["feature"]
        for c in pvs.get("feature_comparisons", [])
        if c.get("stability_status") == "unstable"
    ]
    redundant_groups: list[dict[str, Any]] = []
    for p in redundancy.get("pairs", []):
        if p.get("redundancy_level") in ("high", "very_high"):
            redundant_groups.append({
                "features": [p["feature_a"], p["feature_b"]],
                "pearson": p.get("pearson"),
                "spearman": p.get("spearman"),
                "level": p.get("redundancy_level"),
            })

    recommended: list[dict[str, Any]] = []
    for fam, meta in FEATURE_FAMILIES.items():
        pref = meta.get("preferred_representative")
        if fam == "dominance_family":
            pref = meta.get("directional_preferred") or "x_directional_conviction_candidate"
        if pref:
            recommended.append({
                "family": fam,
                "representative": pref,
                "members": list(meta.get("members", ())),
                "note": meta.get("note"),
            })

    candidate_interactions = [
        p["pattern_key"]
        for p in patterns
        if p.get("stability_status") in ("stronger_candidate", "exploratory_candidate")
    ][:15]

    next_recs: list[dict[str, Any]] = []
    seen: set[str] = set()
    unstable_set = set(unstable)

    def _add(feature: str, reason: str, preferred_form: str, representation: str) -> None:
        if feature in seen or feature in unstable_set or len(next_recs) >= 10:
            return
        fam = feature_family(feature)
        if fam:
            for rec in recommended:
                if rec["family"] == fam and rec["representative"] != feature:
                    # prefer family representative if listed
                    if rec["representative"] not in seen and rec["representative"] not in unstable_set:
                        feature = rec["representative"]
                        reason = f"{reason}; rappresentante famiglia {fam}"
                    break
        seen.add(feature)
        next_recs.append({
            "feature": feature,
            "representation": representation,
            "family": fam,
            "reason": reason,
            "preferred_form": preferred_form,
        })

    for f in useful:
        form = "continuous"
        if f in ("x_rank",) or f.endswith("_class") or f.endswith("_class_existing") or f.endswith("_class_candidate"):
            form = "categorical"
        elif f in nonlinear:
            form = "spline_or_bins"
        _add(f, "potentially_useful on Primary", form, "univariate")
    for f in modest:
        form = "spline_or_bins" if f in nonlinear else "continuous"
        _add(f, "modest reliability — keep for 1D", form, "univariate")
    _add(
        "x_directional_conviction_candidate",
        "directional conviction corrected for HOME/DRAW/AWAY",
        "continuous",
        "directional",
    )
    for f in nonlinear:
        _add(f, "non-linear trend — test categorical/binned form", "spline_or_bins", "binned")
    _add("x_rank", "categorical position of X", "categorical", "categorical")
    _add("f36_class_existing", "F36 class for interaction tests", "categorical", "categorical")

    return {
        "potentially_useful": useful[:10],
        "modest_candidates": modest[:10],
        "weak_or_uncertain": weak[:15],
        "redundant_groups": redundant_groups[:15],
        "recommended_representatives": recommended,
        "non_linear_candidates": nonlinear[:10],
        "candidate_interactions": candidate_interactions,
        "unstable_features": unstable[:15],
        "requires_more_history": list(maturity.get("warnings", [])),
        "next_phase_features": [x["feature"] for x in next_recs],
        "next_phase_feature_recommendations": next_recs,
    }


def build_draw_credibility_statistical_analysis(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    bin_count: int = 5,
    min_group_size: int = 20,
    bootstrap_iterations: int = 500,
    random_seed: int = 42,
) -> dict[str, Any]:
    t_start = time.perf_counter()
    all_rows, _meta = build_draw_credibility_all_rows(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id,
    )
    t_after_dataset = time.perf_counter()

    cohorts_raw = {
        COHORT_ELIGIBLE_PRIMARY: rows_for_selected_cohort(all_rows, COHORT_ELIGIBLE_PRIMARY),
        COHORT_ALL_USABLE_SENSITIVITY: rows_for_selected_cohort(all_rows, COHORT_ALL_USABLE_SENSITIVITY),
        COHORT_MARKET_SUBSET: rows_for_selected_cohort(all_rows, COHORT_MARKET_SUBSET),
    }
    cohorts = {k: [_enrich_research_features(r) for r in v] for k, v in cohorts_raw.items()}
    t_after_enrich = time.perf_counter()

    primary = cohorts[COHORT_ELIGIBLE_PRIMARY]
    sensitivity = cohorts[COHORT_ALL_USABLE_SENSITIVITY]
    market = cohorts[COHORT_MARKET_SUBSET]

    ds_summary = {k: _cohort_target_summary(v) for k, v in cohorts.items()}
    time_span = ds_summary[COHORT_ELIGIBLE_PRIMARY]["time_span_days"]
    maturity = _research_maturity(ds_summary[COHORT_ELIGIBLE_PRIMARY], time_span)

    baseline_p = ds_summary[COHORT_ELIGIBLE_PRIMARY]["draw_rate_pct"]
    baseline_s = ds_summary[COHORT_ALL_USABLE_SENSITIVITY]["draw_rate_pct"]

    timing_acc: dict[str, float] = {"bootstrap_ms": 0.0}
    t_univ0 = time.perf_counter()

    primary_boundaries: dict[str, list[float]] = {}
    primary_numeric: list[dict[str, Any]] = []
    for i, f in enumerate(NUMERIC_FEATURES):
        vals = [v for v in (_num(r, f) for r in primary) if v is not None]
        boundaries = build_quantile_boundaries(vals, bin_count)
        primary_boundaries[f] = boundaries
        primary_numeric.append(
            _analyze_numeric_feature(
                primary,
                f,
                baseline_rate=baseline_p,
                bin_count=bin_count,
                min_group_size=min_group_size,
                bootstrap_iterations=bootstrap_iterations,
                random_seed=random_seed + i,
                boundaries=boundaries,
                boundary_source="primary",
                timing_acc=timing_acc,
            )
        )

    sens_numeric: list[dict[str, Any]] = []
    for i, f in enumerate(NUMERIC_FEATURES):
        sens_numeric.append(
            _analyze_numeric_feature(
                sensitivity,
                f,
                baseline_rate=baseline_s,
                bin_count=bin_count,
                min_group_size=min_group_size,
                bootstrap_iterations=bootstrap_iterations,
                random_seed=random_seed + 100 + i,
                boundaries=primary_boundaries[f],
                boundary_source="primary",
                timing_acc=timing_acc,
            )
        )

    primary_cat = [
        _analyze_categorical(primary, f, baseline=baseline_p, min_group_size=min_group_size)
        for f in CATEGORICAL_FEATURES
    ]
    sens_cat = [
        _analyze_categorical(sensitivity, f, baseline=baseline_s, min_group_size=min_group_size)
        for f in CATEGORICAL_FEATURES
    ]
    t_after_univ = time.perf_counter()

    primary_ids = {r["provider_fixture_id"] for r in primary}
    sens_only = [r for r in sensitivity if r["provider_fixture_id"] not in primary_ids]
    pvs = _primary_vs_sensitivity(
        primary_numeric, sens_numeric, primary_cat, sens_cat, sens_only, primary,
    )
    stab_map = {
        c["feature"]: c.get("stability_status")
        for c in pvs["feature_comparisons"]
        if c.get("type") == "numeric"
    }

    leaderboard = [_leaderboard_row(na, stab_map.get(na["feature"])) for na in primary_numeric]
    leaderboard.sort(key=lambda x: (-(x.get("discriminative_auc") or 0), x.get("missing_pct") or 0))

    redundancy = _redundancy_analysis(primary)
    cal_primary = _calibration_block(primary, "prob_x_norm", "Cecchino X Primary")

    t_ix0 = time.perf_counter()
    interactions = _interaction_analysis(
        primary,
        sensitivity,
        primary_boundaries=primary_boundaries,
        baseline_primary=baseline_p,
        baseline_sensitivity=baseline_s,
        min_group_size=min_group_size,
        bin_count=bin_count,
    )
    patterns = _candidate_patterns(
        interactions, baseline_primary=baseline_p, min_group_size=min_group_size,
    )
    t_after_ix = time.perf_counter()

    t_temp0 = time.perf_counter()
    temporal = _temporal_stability(primary, time_span)
    t_after_temp = time.perf_counter()

    t_league0 = time.perf_counter()
    league = _league_stability(primary, min_group_size=min_group_size)
    t_after_league = time.perf_counter()

    t_mkt0 = time.perf_counter()
    market_block = _market_analysis(
        market,
        patterns,
        bin_count=bin_count,
        bootstrap_iterations=bootstrap_iterations,
        seed=random_seed,
    )
    t_after_mkt = time.perf_counter()

    t_conc0 = time.perf_counter()
    conclusions = _research_conclusions(leaderboard, redundancy, maturity, pvs, patterns)
    t_after_conc = time.perf_counter()

    warnings = list(maturity.get("warnings", []))
    warnings.extend([
        "theoretical_historical_roi",
        "no_slippage",
        "exploratory_not_production",
        "multiple_comparisons_risk",
    ])

    t_end = time.perf_counter()
    payload = {
        "status": "ok",
        "version": VERSION,
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
            "bin_count": bin_count,
            "min_group_size": min_group_size,
            "bootstrap_iterations": bootstrap_iterations,
            "random_seed": random_seed,
        },
        "dataset_summary": {
            "primary": ds_summary[COHORT_ELIGIBLE_PRIMARY],
            "sensitivity": ds_summary[COHORT_ALL_USABLE_SENSITIVITY],
            "market": ds_summary[COHORT_MARKET_SUBSET],
        },
        "research_maturity": maturity,
        "target_baseline": {
            "primary_draw_rate_pct": baseline_p,
            "sensitivity_draw_rate_pct": baseline_s,
            "market_draw_rate_pct": ds_summary[COHORT_MARKET_SUBSET]["draw_rate_pct"],
        },
        "descriptive_statistics": {
            "numeric": [_descriptive_numeric(primary, f) for f in NUMERIC_FEATURES],
        },
        "probability_calibration": {"primary_cecchino_x": cal_primary},
        "numeric_feature_analysis": {
            COHORT_ELIGIBLE_PRIMARY: primary_numeric,
            COHORT_ALL_USABLE_SENSITIVITY: sens_numeric,
        },
        "categorical_feature_analysis": {
            COHORT_ELIGIBLE_PRIMARY: primary_cat,
            COHORT_ALL_USABLE_SENSITIVITY: sens_cat,
        },
        "feature_leaderboard": leaderboard,
        "feature_families": FEATURE_FAMILIES,
        "redundancy_analysis": redundancy,
        "primary_vs_sensitivity": pvs,
        "temporal_stability": temporal,
        "league_stability": league,
        "interaction_analysis": interactions,
        "candidate_patterns": patterns,
        "market_analysis": market_block,
        "research_conclusions": conclusions,
        "warnings": warnings,
        "performance": {
            "dataset_build_ms": round((t_after_dataset - t_start) * 1000, 1),
            "enrichment_ms": round((t_after_enrich - t_after_dataset) * 1000, 1),
            "univariate_ms": round((t_after_univ - t_univ0) * 1000, 1),
            "bootstrap_ms": round(timing_acc.get("bootstrap_ms", 0.0), 1),
            "interactions_ms": round((t_after_ix - t_ix0) * 1000, 1),
            "temporal_ms": round((t_after_temp - t_temp0) * 1000, 1),
            "league_ms": round((t_after_league - t_league0) * 1000, 1),
            "market_ms": round((t_after_mkt - t_mkt0) * 1000, 1),
            "conclusions_ms": round((t_after_conc - t_conc0) * 1000, 1),
            "statistics_compute_ms": round((t_end - t_after_dataset) * 1000, 1),
            "total_ms": round((t_end - t_start) * 1000, 1),
        },
    }
    return _round_out(payload, 4)
