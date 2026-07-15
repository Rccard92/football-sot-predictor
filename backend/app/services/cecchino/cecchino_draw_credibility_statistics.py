"""Analisi statistica Credibilità X — Fase 1C (stdlib only)."""

from __future__ import annotations

import math
import random
import statistics
import time
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
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
    ELIGIBILITY_ELIGIBLE,
    _parse_iso_dt,
    pct,
)

VERSION = "cecchino_draw_credibility_statistics_v1"
WILSON_Z = 1.959963984540054
TREND_TOLERANCE_PP = 2.0
PROB_CLAMP_LO = 1e-15
PROB_CLAMP_HI = 1.0 - 1e-15

NUMERIC_FEATURES = (
    "prob_x_norm", "quota_cecchino_x", "x_vs_best_lateral_pp", "x_vs_second_probability_pp",
    "f36_abs", "f36_score_existing", "dominance_pp", "dominance_normalized_pp",
    "conviction_index_candidate", "x_directional_conviction_candidate",
    "probability_gap_1_2_pp", "probability_balance_index", "gap_coherence_index_candidate",
    "prob_under_2_5_cecchino_pct", "under_minus_over_pp", "under_strength_pp", "hours_to_kickoff",
)
CATEGORICAL_FEATURES = (
    "x_rank", "x_tied_for_top", "x_is_top", "x_is_last", "dominant_sign",
    "conviction_class_candidate", "f36_class_existing", "gap_coherence_class_candidate",
    "goal_probability_source", "hours_to_kickoff_class",
)
BOOK_NUMERIC = (
    "prob_book_x_norm", "quota_book_x", "deviation_x_pp", "market_deviation_mean_pp",
    "prob_book_under_2_5_norm", "book_1x2_overround", "book_goal_overround",
)
CORRELATION_FEATURES = NUMERIC_FEATURES

CONVICTION_ORDER = ("Molto Debole", "Debole", "Moderata", "Forte", "Molto Forte")
F36_ORDER = ("Equilibrio forte", "Equilibrio", "Transizione", "Squilibrio")
GAP_COH_ORDER = ("Non Confermato", "Debole", "Parziale", "Confermato", "Fortemente Confermato")
HOURS_CLASS_ORDER = ("<=24h", ">24-72h", ">72-120h", ">120h")

EXPECTED_REDUNDANCY_GROUPS = (
    ("quota_cecchino_x", "prob_x_norm"),
    ("dominance_pp", "conviction_index_candidate"),
    ("f36_abs", "probability_gap_1_2_pp"),
    ("probability_gap_1_2_pp", "probability_balance_index"),
    ("prob_under_2_5_cecchino_pct", "under_minus_over_pp"),
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


def wilson_ci(successes: int, n: int, z: float = WILSON_Z) -> dict[str, float | None]:
    if n <= 0:
        return {"lower_pct": None, "upper_pct": None}
    p_hat = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z2 / (4 * n)) / n) / denom
    return {
        "lower_pct": round(max(0.0, center - margin) * 100, 2),
        "upper_pct": round(min(1.0, center + margin) * 100, 2),
    }


def _rank_with_ties(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def auc_mann_whitney(y_true: list[int], scores: list[float]) -> float | None:
    if len(y_true) != len(scores) or len(y_true) < 2:
        return None
    pos = [s for y, s in zip(y_true, scores) if y == 1]
    neg = [s for y, s in zip(y_true, scores) if y == 0]
    if not pos or not neg:
        return None
    ranks = _rank_with_ties(scores)
    rank_sum_pos = sum(r for y, r in zip(y_true, ranks) if y == 1)
    n_pos = len(pos)
    n_neg = len(neg)
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2
    return u / (n_pos * n_neg)


def pearson_r(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def spearman_rho(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return pearson_r(_rank_with_ties(xs), _rank_with_ties(ys))


def bootstrap_auc(
    y_true: list[int],
    scores: list[float],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    n = len(y_true)
    aucs: list[float] = []
    for _ in range(iterations):
        idx = [rng.randrange(n) for _ in range(n)]
        yt = [y_true[i] for i in idx]
        sc = [scores[i] for i in idx]
        a = auc_mann_whitney(yt, sc)
        if a is not None:
            aucs.append(a)
    if len(aucs) < 10:
        return {"auc": None, "auc_ci_lower": None, "auc_ci_upper": None, "valid_bootstrap_iterations": len(aucs)}
    aucs.sort()
    lo = aucs[int(0.025 * len(aucs))]
    hi = aucs[min(len(aucs) - 1, int(0.975 * len(aucs)))]
    return {
        "auc": round(statistics.mean(aucs), 4),
        "auc_ci_lower": round(lo, 4),
        "auc_ci_upper": round(hi, 4),
        "valid_bootstrap_iterations": len(aucs),
    }


def _quantile_bins(values: list[float], bin_count: int) -> list[dict[str, Any]]:
    if not values:
        return []
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    actual_bins = min(bin_count, len(set(sorted_vals)))
    if actual_bins <= 0:
        return []
    edges: list[float] = []
    for i in range(1, actual_bins):
        q_idx = int(i * n / actual_bins)
        q_idx = min(q_idx, n - 1)
        edges.append(sorted_vals[q_idx])
    unique_edges: list[float] = []
    for e in edges:
        if not unique_edges or e != unique_edges[-1]:
            unique_edges.append(e)
    bounds = [-math.inf] + unique_edges + [math.inf]
    bins: list[dict[str, Any]] = []
    for i in range(len(bounds) - 1):
        lo, hi = bounds[i], bounds[i + 1]
        lo_inc = i > 0
        hi_inc = i == len(bounds) - 2
        in_bin = []
        for v in values:
            if lo_inc:
                ok_lo = v >= lo
            else:
                ok_lo = v > lo
            if hi_inc:
                ok_hi = v <= hi
            else:
                ok_hi = v < hi
            if ok_lo and ok_hi:
                in_bin.append(v)
        if not in_bin and i < len(bounds) - 2:
            continue
        label = f"Q{i + 1}"
        if math.isfinite(lo) and math.isfinite(hi):
            label = f"{lo:.2f}–{hi:.2f}" if hi_inc else f"{lo:.2f}–<{hi:.2f}"
        bins.append({
            "index": len(bins) + 1,
            "label": label,
            "lower_bound": None if not math.isfinite(lo) else round(lo, 4),
            "upper_bound": None if not math.isfinite(hi) else round(hi, 4),
            "lower_inclusive": lo_inc,
            "upper_inclusive": hi_inc,
            "values": in_bin,
        })
    return bins


def classify_trend(rates: list[float | None], *, tolerance_pp: float = TREND_TOLERANCE_PP) -> str:
    valid = [r for r in rates if r is not None]
    if len(valid) < 3:
        return "insufficient_data"
    if max(valid) - min(valid) <= tolerance_pp:
        return "flat"
    diffs = [valid[i + 1] - valid[i] for i in range(len(valid) - 1)]
    inc = sum(1 for d in diffs if d > tolerance_pp)
    dec = sum(1 for d in diffs if d < -tolerance_pp)
    if inc >= len(diffs) - 1 and dec == 0:
        return "increasing"
    if dec >= len(diffs) - 1 and inc == 0:
        return "decreasing"
    mid = len(valid) // 2
    if valid[0] > valid[-1] and max(valid[mid:]) > valid[0] + tolerance_pp:
        return "u_shaped"
    if valid[0] < valid[-1] and min(valid[mid:]) < valid[0] - tolerance_pp:
        return "inverted_u"
    return "irregular"


def _clamp_prob(p: float) -> float:
    return max(PROB_CLAMP_LO, min(PROB_CLAMP_HI, p))


def brier_score(probs: list[float], y_true: list[int]) -> float | None:
    if not probs or len(probs) != len(y_true):
        return None
    return sum((p - y) ** 2 for p, y in zip(probs, y_true)) / len(probs)


def log_loss_score(probs: list[float], y_true: list[int]) -> float | None:
    if not probs or len(probs) != len(y_true):
        return None
    total = 0.0
    for p, y in zip(probs, y_true):
        pc = _clamp_prob(p)
        total += -(y * math.log(pc) + (1 - y) * math.log(1 - pc))
    return total / len(probs)


def expected_calibration_error(probs: list[float], y_true: list[float], weights: list[int] | None = None) -> float | None:
    if not probs:
        return None
    bins = _quantile_bins(probs, 5)
    if not bins:
        return None
    total_w = 0
    ece = 0.0
    for b in bins:
        idx_vals = b["values"]
        if not idx_vals:
            continue
        w = len(idx_vals)
        total_w += w
        actual = statistics.mean(
            [y_true[i] for i, p in enumerate(probs) if p in idx_vals]
        ) if any(p in idx_vals for p in probs) else 0
        pred = statistics.mean(idx_vals)
        ece += w * abs(pred - actual)
    return ece / total_w if total_w else None


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


def _enrich_research_features(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    feat_at = _parse_iso_dt(row.get("feature_snapshot_at"))
    kickoff = _parse_kickoff(row)
    hours = None
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
        out["dominance_normalized_pp"] = round(ordered[0] - ordered[1], 2)
    else:
        out["dominance_normalized_pp"] = None

    conv = _num(row, "conviction_index_candidate")
    dom = row.get("dominant_sign")
    if conv is not None and dom == "X":
        out["x_directional_conviction_candidate"] = conv
    elif conv is not None and dom in ("1", "2"):
        out["x_directional_conviction_candidate"] = -conv
    else:
        out["x_directional_conviction_candidate"] = None

    pu = _num(row, "prob_under_2_5_cecchino_pct")
    out["under_strength_pp"] = round(pu - 50, 2) if pu is not None else None
    xr = row.get("x_rank")
    out["x_is_top"] = 1 if xr == 1 else 0 if xr is not None else None
    out["x_is_last"] = 1 if xr == 3 else 0 if xr is not None else None
    return out


def _cohort_target_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    draws = sum(1 for r in rows if r.get("draw_ft") == 1)
    n = len(rows)
    kickoffs = [_parse_kickoff(r) for r in rows]
    kickoffs = [k for k in kickoffs if k is not None]
    days = {k.date().isoformat() for k in kickoffs}
    leagues = {r.get("league_name") for r in rows if r.get("league_name")}
    countries = {r.get("country_name") for r in rows if r.get("country_name")}
    ci = wilson_ci(draws, n)
    span = 0
    if kickoffs:
        span = (max(kickoffs) - min(kickoffs)).days
    return {
        "rows": n,
        "draws": draws,
        "non_draws": n - draws,
        "draw_rate_pct": pct(draws, n),
        "wilson_ci_95": ci,
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
        return {"feature": feature, "count": 0, "missing_count": missing, "missing_pct": pct(missing, n), "constant_feature": True}
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


def _analyze_numeric_feature(
    rows: list[dict],
    feature: str,
    *,
    baseline_rate: float,
    bin_count: int,
    min_group_size: int,
    bootstrap_iterations: int,
    random_seed: int,
) -> dict[str, Any]:
    pairs = [(r.get("draw_ft", 0), _num(r, feature)) for r in rows]
    valid_pairs = [(y, x) for y, x in pairs if x is not None and y in (0, 1)]
    desc = _descriptive_numeric(rows, feature)
    if len(valid_pairs) < 2:
        return {**desc, "auc": None, "directional_auc": None, "discriminative_auc": None, "bins": [], "trend": "insufficient_data"}

    y_true = [int(y) for y, _ in valid_pairs]
    scores = [x for _, x in valid_pairs]
    auc = auc_mann_whitney(y_true, scores)
    disc = max(auc, 1 - auc) if auc is not None else None
    boot = bootstrap_auc(y_true, scores, iterations=bootstrap_iterations, seed=random_seed)
    pear = pearson_r(scores, [float(y) for y in y_true])
    spear = spearman_rho(scores, [float(y) for y in y_true])

    raw_bins = _quantile_bins(scores, bin_count)
    bin_rows: list[dict] = []
    rates: list[float | None] = []
    for b in raw_bins:
        vals = set(b["values"])
        in_bin = [(y, x) for y, x in valid_pairs if x in vals]
        if not in_bin:
            continue
        d = sum(1 for y, _ in in_bin if y == 1)
        cnt = len(in_bin)
        dr = pct(d, cnt)
        rates.append(dr)
        ci = wilson_ci(d, cnt)
        bin_rows.append({
            "index": b["index"],
            "label": b["label"],
            "lower_bound": b["lower_bound"],
            "upper_bound": b["upper_bound"],
            "count": cnt,
            "draws": d,
            "non_draws": cnt - d,
            "draw_rate_pct": dr,
            "wilson_ci_95": ci,
            "lift_vs_baseline_pp": round(dr - baseline_rate, 2),
            "reliable": cnt >= min_group_size,
            "mean_feature_value": round(statistics.mean([x for _, x in in_bin]), 4),
        })

    trend = classify_trend(rates)
    best_dr = max((b["draw_rate_pct"] for b in bin_rows), default=None)
    worst_dr = min((b["draw_rate_pct"] for b in bin_rows), default=None)
    spread = round(best_dr - worst_dr, 2) if best_dr is not None and worst_dr is not None else None

    return {
        **desc,
        "directional_auc": round(auc, 4) if auc is not None else None,
        "discriminative_auc": round(disc, 4) if disc is not None else None,
        "pearson": round(pear, 4) if pear is not None else None,
        "spearman": round(spear, 4) if spear is not None else None,
        "bootstrap": boot,
        "bins": bin_rows,
        "actual_bin_count": len(bin_rows),
        "trend": trend,
        "best_bin_draw_rate": best_dr,
        "worst_bin_draw_rate": worst_dr,
        "spread_pp": spread,
        "reliability_status": _reliability_status(
            len(valid_pairs),
            sum(y_true),
            disc,
            boot.get("auc_ci_lower"),
            boot.get("auc_ci_upper"),
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
    ):
        if feature == order and s in seq:
            return (0, seq.index(s))
    return (1, s)


def _analyze_categorical(rows: list[dict], feature: str, *, baseline: float, min_group_size: int) -> dict[str, Any]:
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
        spread = round(max(c["draw_rate_pct"] for c in reliable) - min(c["draw_rate_pct"] for c in reliable), 2)
    return {"feature": feature, "categories": cats, "reliable_spread_pp": spread}


def _calibration_block(rows: list[dict], prob_key: str, label: str) -> dict[str, Any]:
    pairs = []
    for r in rows:
        p = _num(r, prob_key)
        if p is not None:
            pairs.append((_clamp_prob(p / 100.0 if p > 1 else p), int(r.get("draw_ft", 0))))
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
    ece = expected_calibration_error(probs, y)
    cal_bins = []
    for b in _quantile_bins(probs, 5):
        vals = b["values"]
        if not vals:
            continue
        in_y = [t for p, t in pairs if p in vals]
        cal_bins.append({
            "predicted_mean": round(statistics.mean(vals), 4),
            "actual_rate": round(statistics.mean(in_y), 4) if in_y else None,
            "count": len(in_y),
            "calibration_gap": round(abs(statistics.mean(vals) - statistics.mean(in_y)), 4) if in_y else None,
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
    for i, fa in enumerate(features):
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
                })
    groups = [{"features": list(g), "expected": True} for g in EXPECTED_REDUNDANCY_GROUPS]
    return {"pearson_matrix": matrix_p, "spearman_matrix": matrix_s, "pairs": pairs, "candidate_groups": groups}


def _roi_analysis(rows: list[dict], *, min_group_size: int, bootstrap_iterations: int, seed: int) -> dict[str, Any]:
    profits: list[float] = []
    for r in rows:
        odd = _num(r, "quota_book_x")
        if odd is None or odd <= 1:
            continue
        if r.get("draw_ft") == 1:
            profits.append(odd - 1)
        else:
            profits.append(-1.0)
    if not profits:
        return {"bets": 0, "roi_pct": None}
    wins = sum(1 for p in profits if p > 0)
    stake = len(profits)
    net = sum(profits)
    roi = pct(net, stake)
    boot_ci = None
    if stake >= 50:
        rng = random.Random(seed)
        rois = []
        for _ in range(bootstrap_iterations):
            sample = [profits[rng.randrange(len(profits))] for _ in range(len(profits))]
            rois.append(100 * sum(sample) / len(sample))
        rois.sort()
        boot_ci = {"lower_pct": round(rois[int(0.025 * len(rois))], 2), "upper_pct": round(rois[int(0.975 * len(rois))], 2)}
    return {
        "bets": stake,
        "wins": wins,
        "win_rate_pct": pct(wins, stake),
        "total_stake": stake,
        "net_profit": round(net, 2),
        "roi_pct": roi,
        "bootstrap_roi_ci_95": boot_ci,
        "warnings": ["theoretical_historical_roi", "no_transaction_costs", "short_sample"],
    }


def _research_conclusions(
    leaderboard: list[dict],
    redundancy: dict,
    maturity: dict,
) -> dict[str, list[str]]:
    useful = [x["feature"] for x in leaderboard if x.get("reliability_status") == "potentially_useful"]
    weak = [x["feature"] for x in leaderboard if x.get("reliability_status") in ("weak", "uncertain", "insufficient_sample")]
    redundant = [p["feature_a"] + "↔" + p["feature_b"] for p in redundancy.get("pairs", []) if p.get("redundancy_level") in ("high", "very_high")]
    nonlinear = [x["feature"] for x in leaderboard if x.get("trend") in ("u_shaped", "inverted_u", "irregular")]
    limits = maturity.get("warnings", [])
    next_feats = [f for f in useful if f not in redundant][:8]
    return {
        "potentially_useful": useful[:10],
        "weak_or_uncertain": weak[:10],
        "redundant": redundant[:10],
        "non_linear_candidates": nonlinear[:10],
        "requires_more_history": limits,
        "next_phase_features": next_feats,
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

    primary = cohorts[COHORT_ELIGIBLE_PRIMARY]
    sensitivity = cohorts[COHORT_ALL_USABLE_SENSITIVITY]
    market = cohorts[COHORT_MARKET_SUBSET]

    ds_summary = {k: _cohort_target_summary(v) for k, v in cohorts.items()}
    time_span = ds_summary[COHORT_ELIGIBLE_PRIMARY]["time_span_days"]
    maturity = _research_maturity(ds_summary[COHORT_ELIGIBLE_PRIMARY], time_span)

    baseline_p = ds_summary[COHORT_ELIGIBLE_PRIMARY]["draw_rate_pct"]
    numeric_analysis = {
        COHORT_ELIGIBLE_PRIMARY: [
            _analyze_numeric_feature(primary, f, baseline_rate=baseline_p, bin_count=bin_count,
                                     min_group_size=min_group_size, bootstrap_iterations=bootstrap_iterations,
                                     random_seed=random_seed)
            for f in NUMERIC_FEATURES
        ],
    }
    cat_analysis = {
        COHORT_ELIGIBLE_PRIMARY: [
            _analyze_categorical(primary, f, baseline=baseline_p, min_group_size=min_group_size)
            for f in CATEGORICAL_FEATURES
        ],
    }

    leaderboard = []
    for na in numeric_analysis[COHORT_ELIGIBLE_PRIMARY]:
        leaderboard.append({
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
            "best_bin_draw_rate": na.get("best_bin_draw_rate"),
            "worst_bin_draw_rate": na.get("worst_bin_draw_rate"),
            "spread_pp": na.get("spread_pp"),
            "reliability_status": na.get("reliability_status"),
            "interpretation": f"Trend {na.get('trend')}, discriminative AUC {na.get('discriminative_auc')}",
        })
    leaderboard.sort(key=lambda x: (-(x.get("discriminative_auc") or 0), x.get("missing_pct") or 0))

    redundancy = _redundancy_analysis(primary)
    cal_primary = _calibration_block(primary, "prob_x_norm", "Cecchino X Primary")
    cal_market_c = _calibration_block(market, "prob_x_norm", "Cecchino X Market")
    cal_market_b = _calibration_block(market, "prob_book_x_norm", "Book X Market")

    primary_ids = {r["provider_fixture_id"] for r in primary}
    sens_only = [r for r in sensitivity if r["provider_fixture_id"] not in primary_ids]

    pva = []
    pmap = {na["feature"]: na for na in numeric_analysis[COHORT_ELIGIBLE_PRIMARY]}
    for f in NUMERIC_FEATURES[:8]:
        sens_na = _analyze_numeric_feature(
            sensitivity, f, baseline_rate=ds_summary[COHORT_ALL_USABLE_SENSITIVITY]["draw_rate_pct"],
            bin_count=bin_count, min_group_size=min_group_size,
            bootstrap_iterations=bootstrap_iterations, random_seed=random_seed,
        )
        pa = pmap.get(f, {})
        auc_d = None
        if pa.get("directional_auc") is not None and sens_na.get("directional_auc") is not None:
            auc_d = round(sens_na["directional_auc"] - pa["directional_auc"], 4)
        pva.append({
            "feature": f,
            "primary_auc": pa.get("directional_auc"),
            "sensitivity_auc": sens_na.get("directional_auc"),
            "auc_delta": auc_d,
            "trend_consistent": pa.get("trend") == sens_na.get("trend"),
            "stability_status": "stable" if pa.get("trend") == sens_na.get("trend") else "mostly_stable",
        })

    warnings = list(maturity.get("warnings", []))
    warnings.extend(["theoretical_historical_roi", "no_slippage", "exploratory_not_production"])

    conclusions = _research_conclusions(leaderboard, redundancy, maturity)

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
            "sensitivity_draw_rate_pct": ds_summary[COHORT_ALL_USABLE_SENSITIVITY]["draw_rate_pct"],
            "market_draw_rate_pct": ds_summary[COHORT_MARKET_SUBSET]["draw_rate_pct"],
        },
        "descriptive_statistics": {
            "numeric": [_descriptive_numeric(primary, f) for f in NUMERIC_FEATURES],
        },
        "probability_calibration": {"primary_cecchino_x": cal_primary},
        "numeric_feature_analysis": numeric_analysis,
        "categorical_feature_analysis": cat_analysis,
        "feature_leaderboard": leaderboard,
        "redundancy_analysis": redundancy,
        "primary_vs_sensitivity": {
            "feature_comparisons": pva,
            "sensitivity_only_fixtures": {
                "count": len(sens_only),
                "draws": sum(1 for r in sens_only if r.get("draw_ft") == 1),
                "draw_rate_pct": pct(sum(1 for r in sens_only if r.get("draw_ft") == 1), len(sens_only)),
            },
        },
        "temporal_stability": {"short_observation_window": time_span < 90, "time_span_days": time_span},
        "league_stability": {"fragmented_leagues": maturity.get("fragmented_leagues", False)},
        "interaction_analysis": [],
        "candidate_patterns": [],
        "market_analysis": {
            "cecchino": cal_market_c,
            "book": cal_market_b,
            "comparison": {
                "delta_brier": round((cal_market_c.get("brier_score") or 0) - (cal_market_b.get("brier_score") or 0), 4)
                if cal_market_c.get("brier_score") is not None and cal_market_b.get("brier_score") is not None else None,
            },
            "roi": _roi_analysis(market, min_group_size=min_group_size, bootstrap_iterations=bootstrap_iterations, seed=random_seed),
        },
        "research_conclusions": conclusions,
        "warnings": warnings,
        "performance": {
            "dataset_build_ms": round((t_after_dataset - t_start) * 1000, 1),
            "statistics_compute_ms": round((t_end - t_after_dataset) * 1000, 1),
            "total_ms": round((t_end - t_start) * 1000, 1),
        },
    }
    return _round_out(payload, 4)
