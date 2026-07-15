"""Helper matematici e configurazione per analisi statistica Credibilità X — Fase 1C.1."""

from __future__ import annotations

import math
import random
import statistics
from typing import Any

WILSON_Z = 1.959963984540054
TREND_TOLERANCE_PP = 2.0
PROB_CLAMP_LO = 1e-15
PROB_CLAMP_HI = 1.0 - 1e-15

FEATURE_FAMILIES: dict[str, dict[str, Any]] = {
    "under_family": {
        "members": ("prob_under_2_5_cecchino_pct", "under_minus_over_pp", "under_strength_pp"),
        "preferred_representative": "prob_under_2_5_cecchino_pct",
    },
    "x_probability_family": {
        "members": ("prob_x_norm", "quota_cecchino_x"),
        "preferred_representative": "prob_x_norm",
    },
    "dominance_family": {
        "members": ("dominance_pp", "dominance_normalized_pp", "conviction_index_candidate"),
        "preferred_representative": None,
        "directional_preferred": "x_directional_conviction_candidate",
    },
    "f36_gap_family": {
        "members": (
            "f36_abs",
            "f36_score_existing",
            "probability_gap_1_2_pp",
            "probability_balance_index",
            "gap_coherence_index_candidate",
        ),
        "preferred_representative": None,
        "note": "geometria F36, equilibrio 1/2 e coerenza restano concetti distinti",
    },
}

FEATURE_TO_FAMILY: dict[str, str] = {}
for _fam, _meta in FEATURE_FAMILIES.items():
    for _m in _meta["members"]:
        FEATURE_TO_FAMILY[_m] = _fam
FEATURE_TO_FAMILY["x_directional_conviction_candidate"] = "dominance_family"


def feature_family(name: str) -> str | None:
    return FEATURE_TO_FAMILY.get(name)


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


def rank_with_ties(values: list[float]) -> list[float]:
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
    ranks = rank_with_ties(scores)
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
    return pearson_r(rank_with_ties(xs), rank_with_ties(ys))


def bootstrap_auc(
    y_true: list[int],
    scores: list[float],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    """Bootstrap AUC con CI directional e discriminative esplicite."""
    original = auc_mann_whitney(y_true, scores)
    empty = {
        "original_directional_auc": round(original, 4) if original is not None else None,
        "bootstrap_mean_directional_auc": None,
        "directional_auc_ci_lower": None,
        "directional_auc_ci_upper": None,
        "original_discriminative_auc": round(max(original, 1 - original), 4) if original is not None else None,
        "discriminative_auc_ci_lower": None,
        "discriminative_auc_ci_upper": None,
        "valid_bootstrap_iterations": 0,
        # retrocompatibilità leggera
        "auc": None,
        "auc_ci_lower": None,
        "auc_ci_upper": None,
    }
    if original is None:
        return empty

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
        empty["valid_bootstrap_iterations"] = len(aucs)
        return empty

    aucs.sort()
    lo = aucs[int(0.025 * len(aucs))]
    hi = aucs[min(len(aucs) - 1, int(0.975 * len(aucs)))]
    mean_dir = statistics.mean(aucs)
    disc = max(original, 1.0 - original)

    if original >= 0.5:
        disc_lo, disc_hi = lo, hi
    else:
        disc_lo, disc_hi = 1.0 - hi, 1.0 - lo

    return {
        "original_directional_auc": round(original, 4),
        "bootstrap_mean_directional_auc": round(mean_dir, 4),
        "directional_auc_ci_lower": round(lo, 4),
        "directional_auc_ci_upper": round(hi, 4),
        "original_discriminative_auc": round(disc, 4),
        "discriminative_auc_ci_lower": round(disc_lo, 4),
        "discriminative_auc_ci_upper": round(disc_hi, 4),
        "valid_bootstrap_iterations": len(aucs),
        "auc": round(mean_dir, 4),
        "auc_ci_lower": round(lo, 4),
        "auc_ci_upper": round(hi, 4),
    }


def build_quantile_boundaries(primary_values: list[float], bin_count: int) -> list[float]:
    """Restituisce soglie interne (edge) da applicare con apply_quantile_boundaries."""
    if not primary_values:
        return []
    sorted_vals = sorted(primary_values)
    n = len(sorted_vals)
    actual_bins = min(bin_count, len(set(sorted_vals)))
    if actual_bins <= 1:
        return []
    edges: list[float] = []
    for i in range(1, actual_bins):
        q_idx = min(int(i * n / actual_bins), n - 1)
        edges.append(sorted_vals[q_idx])
    unique: list[float] = []
    for e in edges:
        if not unique or e != unique[-1]:
            unique.append(e)
    return unique


def apply_quantile_boundaries(values: list[float], boundaries: list[float]) -> list[int]:
    """Assegna indice bin 0..len(boundaries) a ciascun valore."""
    n_bins = len(boundaries) + 1
    labels: list[int] = []
    for v in values:
        assigned = n_bins - 1
        for i, edge in enumerate(boundaries):
            if v < edge or (i == 0 and v <= edge and False):
                # i==0: first bin is (-inf, edge0) exclusive on edge for subsequent
                pass
            if i == 0:
                if v < edge:
                    assigned = 0
                    break
            else:
                if v < edge:
                    assigned = i
                    break
        else:
            # last bin or value equals final edges
            if boundaries and v < boundaries[0]:
                assigned = 0
            else:
                assigned = n_bins - 1
                for i, edge in enumerate(boundaries):
                    if v < edge:
                        assigned = i
                        break
        labels.append(assigned)
    # Rewrite more carefully below
    return _assign_bins(values, boundaries)


def _assign_bins(values: list[float], boundaries: list[float]) -> list[int]:
    """Bin 0: (-inf, e0); bin i: [e{i-1}, e_i); last: [e_last, +inf]."""
    out: list[int] = []
    n_edges = len(boundaries)
    for v in values:
        placed = False
        for i, edge in enumerate(boundaries):
            if i == 0:
                if v < edge:
                    out.append(0)
                    placed = True
                    break
            else:
                if v < edge:
                    out.append(i)
                    placed = True
                    break
        if not placed:
            out.append(n_edges)
    return out


def bin_label_from_boundaries(index: int, boundaries: list[float]) -> str:
    n = len(boundaries) + 1
    if n <= 1:
        return "Q1"
    if index == 0:
        return f"<{boundaries[0]:.2f}" if boundaries else "Q1"
    if index >= len(boundaries):
        return f">={boundaries[-1]:.2f}"
    return f"{boundaries[index - 1]:.2f}–<{boundaries[index]:.2f}"


def bin_bounds_meta(bin_index_0: int, boundaries: list[float]) -> dict[str, Any]:
    """Metadati bound/inclusività per bin 0-based (convenzione apply_quantile_boundaries)."""
    n_bins = len(boundaries) + 1 if boundaries else 1
    if not boundaries or n_bins <= 1:
        return {
            "column_lower_bound": None,
            "column_upper_bound": None,
            "column_lower_inclusive": None,
            "column_upper_inclusive": None,
        }
    if bin_index_0 <= 0:
        return {
            "column_lower_bound": None,
            "column_upper_bound": round(boundaries[0], 4),
            "column_lower_inclusive": False,
            "column_upper_inclusive": False,
        }
    if bin_index_0 >= len(boundaries):
        return {
            "column_lower_bound": round(boundaries[-1], 4),
            "column_upper_bound": None,
            "column_lower_inclusive": True,
            "column_upper_inclusive": True,
        }
    return {
        "column_lower_bound": round(boundaries[bin_index_0 - 1], 4),
        "column_upper_bound": round(boundaries[bin_index_0], 4),
        "column_lower_inclusive": True,
        "column_upper_inclusive": False,
    }


def _num_safe(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _row_cat_canonical(row: dict[str, Any], dim: str) -> str:
    v = row.get(dim)
    return str(v) if v is not None else "null"


def matches_candidate_pattern(row: dict[str, Any], pattern: dict[str, Any]) -> bool:
    """Match strutturato: mai parsing di description."""
    row_dim = pattern.get("row_dimension")
    col_dim = pattern.get("column_dimension")
    col_type = pattern.get("column_type")
    row_cat = pattern.get("row_category")
    col_cat = pattern.get("column_category")
    if not row_dim or not col_dim or not col_type or row_cat is None or col_cat is None:
        return False
    if _row_cat_canonical(row, str(row_dim)) != str(row_cat):
        return False

    if col_type == "categorical":
        return _row_cat_canonical(row, str(col_dim)) == str(col_cat)

    if col_type == "quantile":
        boundaries = pattern.get("column_boundaries")
        bin_1 = pattern.get("column_bin_index")
        if not isinstance(boundaries, list) or bin_1 is None:
            return False
        try:
            bin_0 = int(bin_1) - 1
        except (TypeError, ValueError):
            return False
        if bin_0 < 0:
            return False
        val = _num_safe(row, str(col_dim))
        if val is None:
            return False
        assigned = apply_quantile_boundaries([val], [float(b) for b in boundaries])[0]
        return assigned == bin_0

    return False


def classify_trend_with_diagnostics(
    rates: list[float | None],
    *,
    tolerance_pp: float = TREND_TOLERANCE_PP,
) -> tuple[str, dict[str, Any]]:
    valid = [r for r in rates if r is not None]
    valid_idx = [i for i, r in enumerate(rates) if r is not None]
    diag: dict[str, Any] = {
        "valid_bins": len(valid),
        "rates": [round(r, 4) if r is not None else None for r in rates],
        "tolerance_pp": tolerance_pp,
        "edge_mean": None,
        "center_mean": None,
        "min_bin_index": None,
        "max_bin_index": None,
        "reason": None,
    }
    if len(valid) < 3:
        diag["reason"] = "fewer_than_3_valid_bins"
        return "insufficient_data", diag

    min_i = valid_idx[valid.index(min(valid))]
    max_i = valid_idx[valid.index(max(valid))]
    diag["min_bin_index"] = min_i + 1
    diag["max_bin_index"] = max_i + 1

    if max(valid) - min(valid) <= tolerance_pp:
        diag["reason"] = "range_within_tolerance"
        return "flat", diag

    diffs = [valid[i + 1] - valid[i] for i in range(len(valid) - 1)]
    inc = sum(1 for d in diffs if d > tolerance_pp)
    dec = sum(1 for d in diffs if d < -tolerance_pp)
    half = max(1, len(diffs) / 2)

    is_increasing = (
        dec == 0
        and inc >= half
        and valid[-1] > valid[0] + tolerance_pp
    )
    is_decreasing = (
        inc == 0
        and dec >= half
        and valid[0] > valid[-1] + tolerance_pp
    )
    if is_increasing:
        diag["reason"] = "monotonic_increase"
        return "increasing", diag
    if is_decreasing:
        diag["reason"] = "monotonic_decrease"
        return "decreasing", diag

    n = len(valid)
    edge_mean = (valid[0] + valid[-1]) / 2.0
    if n % 2 == 1:
        center_mean = valid[n // 2]
        center_indices = {valid_idx[n // 2]}
    else:
        center_mean = (valid[n // 2 - 1] + valid[n // 2]) / 2.0
        center_indices = {valid_idx[n // 2 - 1], valid_idx[n // 2]}
    diag["edge_mean"] = round(edge_mean, 4)
    diag["center_mean"] = round(center_mean, 4)

    # U-shaped requires >= 5 bins
    if n >= 5:
        min_in_center = min_i in center_indices or (
            min_i > valid_idx[0] and min_i < valid_idx[-1]
            and abs(min_i - (valid_idx[0] + valid_idx[-1]) / 2) <= (valid_idx[-1] - valid_idx[0]) / 3
        )
        u_ok = (
            valid[0] > center_mean + tolerance_pp
            and valid[-1] > center_mean + tolerance_pp
            and edge_mean > center_mean + tolerance_pp
            and min_in_center
            and not is_increasing
            and not is_decreasing
        )
        if u_ok:
            diag["reason"] = "edges_above_center_min_central"
            return "u_shaped", diag

        max_in_center = max_i in center_indices or (
            max_i > valid_idx[0] and max_i < valid_idx[-1]
            and abs(max_i - (valid_idx[0] + valid_idx[-1]) / 2) <= (valid_idx[-1] - valid_idx[0]) / 3
        )
        inv_ok = (
            center_mean > valid[0] + tolerance_pp
            and center_mean > valid[-1] + tolerance_pp
            and max_in_center
            and not is_increasing
            and not is_decreasing
        )
        if inv_ok:
            diag["reason"] = "center_above_edges_max_central"
            return "inverted_u", diag

    diag["reason"] = "no_clear_geometric_pattern"
    return "irregular", diag


def classify_trend(rates: list[float | None], *, tolerance_pp: float = TREND_TOLERANCE_PP) -> str:
    trend, _ = classify_trend_with_diagnostics(rates, tolerance_pp=tolerance_pp)
    return trend


def clamp_prob(p: float) -> float:
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
        pc = clamp_prob(p)
        total += -(y * math.log(pc) + (1 - y) * math.log(1 - pc))
    return total / len(probs)


def herfindahl(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    return sum((c / total) ** 2 for c in counts)


def hhi_concentration_status(hhi: float) -> str:
    if hhi < 0.05:
        return "highly_fragmented"
    if hhi < 0.10:
        return "fragmented"
    if hhi <= 0.18:
        return "moderate_concentration"
    return "concentrated"


def bootstrap_roi(
    profits: list[float],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any] | None:
    if len(profits) < 50:
        return None
    rng = random.Random(seed)
    rois: list[float] = []
    n = len(profits)
    for _ in range(iterations):
        sample = [profits[rng.randrange(n)] for _ in range(n)]
        rois.append(100.0 * sum(sample) / n)
    rois.sort()
    lo = rois[int(0.025 * len(rois))]
    hi = rois[min(len(rois) - 1, int(0.975 * len(rois)))]
    return {
        "lower_pct": round(lo, 2),
        "upper_pct": round(hi, 2),
        "crosses_zero": lo <= 0 <= hi,
    }
