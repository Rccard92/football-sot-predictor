"""Diagnostiche holdout Structural V2 — solo reporting, nessun retune."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
from typing import Any

import numpy as np

from app.models.cecchino_signal_activation import EVAL_LOST, EVAL_WON
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
    roc_auc,
    spearman_rho,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_analysis_export import (
    COHORT_PROSPECTIVE,
    COHORT_TECHNICAL_SMOKE,
    HOLDOUT_MARKET_FAMILIES,
    PRIMARY_DIAGNOSTIC_COHORT,
)

FIXED_V2_BANDS: tuple[tuple[str, float | None, float | None], ...] = (
    ("lt_40", None, 40.0),
    ("40_49", 40.0, 50.0),
    ("50_59", 50.0, 60.0),
    ("60_69", 60.0, 70.0),
    ("70_79", 70.0, 80.0),
    ("80_plus", 80.0, None),
)

ODDS_BUCKETS: tuple[tuple[str, float, float | None], ...] = (
    ("1.01_1.49", 1.01, 1.50),
    ("1.50_1.79", 1.50, 1.80),
    ("1.80_2.19", 1.80, 2.20),
    ("2.20_2.99", 2.20, 3.00),
    ("3.00_4.99", 3.00, 5.00),
    ("5.00_plus", 5.00, None),
)

MIN_N_FOR_TERTILES = 30
MIN_N_PER_SUBGROUP = 10
MIN_N_FOR_QUANTILES = 4


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _panel_index(market_key: str) -> int:
    try:
        return PANEL_MARKET_KEYS.index(market_key)
    except ValueError:
        return 10**9


def sort_key_raw_desc(row: dict[str, Any]) -> tuple:
    raw = _safe_float(row.get("v2_raw_score"))
    # Higher raw first → negate for ascending sort key used with reverse=True
    return (
        raw if raw is not None else float("-inf"),
        -_panel_index(str(row.get("market_key") or "")),
        -int(row.get("today_fixture_id") or 0),
    )


def sort_rows_by_raw_desc(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=sort_key_raw_desc, reverse=True)


def sort_rows_by_raw_asc(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ascending raw for quantile bins; tie-break panel ASC then fixture ASC."""
    return sorted(
        rows,
        key=lambda r: (
            _safe_float(r.get("v2_raw_score"))
            if _safe_float(r.get("v2_raw_score")) is not None
            else float("inf"),
            _panel_index(str(r.get("market_key") or "")),
            int(r.get("today_fixture_id") or 0),
        ),
    )


def _settled_binary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        outcome = r.get("outcome")
        if outcome not in {EVAL_WON, EVAL_LOST}:
            continue
        if _safe_float(r.get("v2_raw_score")) is None:
            continue
        out.append(r)
    return out


def _group_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    wins = sum(1 for r in rows if r.get("outcome") == EVAL_WON)
    losses = sum(1 for r in rows if r.get("outcome") == EVAL_LOST)
    quotes = [_safe_float(r.get("execution_quote")) for r in rows]
    quotes_ok = [q for q in quotes if q is not None and q > 0]
    profits = [_safe_float(r.get("profit_1u")) for r in rows]
    profits_ok = [p for p in profits if p is not None]
    profit_sum = sum(profits_ok) if profits_ok else 0.0
    stake = len(profits_ok)
    scores = [_safe_float(r.get("v2_score")) for r in rows]
    scores_ok = [s for s in scores if s is not None]
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "hit_rate": round(wins / (wins + losses), 6) if (wins + losses) else None,
        "avg_quote": round(sum(quotes_ok) / len(quotes_ok), 6) if quotes_ok else None,
        "median_quote": round(float(median(quotes_ok)), 6) if quotes_ok else None,
        "profit_1u": round(profit_sum, 4) if stake else 0.0,
        "ROI": round(profit_sum / stake, 6) if stake else None,
        "avg_v2_score": round(sum(scores_ok) / len(scores_ok), 4) if scores_ok else None,
    }


def _band_for_score(score: float) -> str:
    for label, lo, hi in FIXED_V2_BANDS:
        if lo is None and hi is not None and score < hi:
            return label
        if lo is not None and hi is None and score >= lo:
            return label
        if lo is not None and hi is not None and lo <= score < hi:
            return label
    return "lt_40"


def build_fixed_band_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = _settled_binary(rows)
    buckets: dict[str, list[dict[str, Any]]] = {label: [] for label, _, _ in FIXED_V2_BANDS}
    for r in settled:
        sc = _safe_float(r.get("v2_score"))
        if sc is None:
            continue
        buckets[_band_for_score(sc)].append(r)
    return {label: _group_stats(items) for label, items in buckets.items()}


def build_quantile_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = _settled_binary(rows)
    n = len(settled)
    if n < MIN_N_FOR_QUANTILES:
        return {"status": "insufficient_sample", "n": n}

    ordered = sort_rows_by_raw_asc(settled)
    # Mutually exclusive quartile index cuts
    cuts = [0, n // 4, n // 2, (3 * n) // 4, n]
    labels = ("Q1_bottom_25", "Q2_25_50", "Q3_50_75", "Q4_top_25")
    out: dict[str, Any] = {"status": "ok", "n": n, "ranking_key": "v2_raw_score"}
    for i, label in enumerate(labels):
        chunk = ordered[cuts[i] : cuts[i + 1]]
        out[label] = _group_stats(chunk)

    # Top 10% — exact n_selected, no expansion on integer ties
    desc = sort_rows_by_raw_desc(settled)
    requested_fraction = 0.10
    n_selected = max(1, int(math.floor(n * requested_fraction)))
    top = desc[:n_selected]
    cutoff = _safe_float(top[-1].get("v2_raw_score")) if top else None
    out["top_10_pct"] = {
        **_group_stats(top),
        "requested_fraction": requested_fraction,
        "n_selected": n_selected,
        "cutoff_raw_score": cutoff,
    }
    return out


def _odds_bucket_label(quote: float) -> str | None:
    for label, lo, hi in ODDS_BUCKETS:
        if hi is None:
            if quote >= lo:
                return label
        elif lo <= quote < hi:
            return label
    return None


def build_odds_controlled_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = _settled_binary(rows)
    by_bucket: dict[str, list[dict[str, Any]]] = {label: [] for label, _, _ in ODDS_BUCKETS}
    for r in settled:
        q = _safe_float(r.get("execution_quote"))
        if q is None:
            continue
        lab = _odds_bucket_label(q)
        if lab:
            by_bucket[lab].append(r)

    report: dict[str, Any] = {}
    for label, items in by_bucket.items():
        n = len(items)
        if n < MIN_N_FOR_TERTILES:
            report[label] = {"status": "insufficient_sample", "n": n}
            continue
        ordered = sort_rows_by_raw_asc(items)
        # Tertile cuts
        c1, c2 = n // 3, (2 * n) // 3
        groups = {
            "low": ordered[:c1],
            "mid": ordered[c1:c2],
            "high": ordered[c2:],
        }
        if any(len(g) < MIN_N_PER_SUBGROUP for g in groups.values()):
            report[label] = {
                "status": "insufficient_sample",
                "n": n,
                "reason": "subgroup_below_min",
                "min_subgroup_n": min(len(g) for g in groups.values()),
            }
            continue
        report[label] = {
            "status": "ok",
            "n": n,
            "low": _group_stats(groups["low"]),
            "mid": _group_stats(groups["mid"]),
            "high": _group_stats(groups["high"]),
        }
    return report


def build_market_family_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = _settled_binary(rows)
    by_fam: dict[str, list[dict[str, Any]]] = {f: [] for f in HOLDOUT_MARKET_FAMILIES}
    for r in settled:
        fam = r.get("holdout_market_family")
        if fam in by_fam:
            by_fam[str(fam)].append(r)

    report: dict[str, Any] = {}
    for fam, items in by_fam.items():
        n = len(items)
        if n < MIN_N_PER_SUBGROUP:
            report[fam] = {"status": "insufficient_sample", "n": n}
            continue
        base = _group_stats(items)
        qrep = build_quantile_report(items)
        report[fam] = {
            "status": "ok",
            **base,
            "score_quantiles": qrep,
        }
    return report


def build_correlation_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = _settled_binary(rows)
    v2 = [_safe_float(r.get("v2_raw_score")) for r in settled]
    pairs = {
        "execution_quote": [_safe_float(r.get("execution_quote")) for r in settled],
        "fair_book_probability": [
            _safe_float(r.get("fair_book_probability")) for r in settled
        ],
        "probability_cecchino": [
            _safe_float(r.get("probability_cecchino")) for r in settled
        ],
        "EV": [_safe_float(r.get("EV")) for r in settled],
        "V": [_safe_float(r.get("V")) for r in settled],
        "D": [_safe_float(r.get("D")) for r in settled],
        "R_base_rate_reliability": [_safe_float(r.get("R")) for r in settled],
        "S": [_safe_float(r.get("S")) for r in settled],
        "Q": [_safe_float(r.get("Q")) for r in settled],
    }
    out: dict[str, Any] = {
        "n": len(settled),
        "note": "diagnostic_only_no_retune",
        "R_terminology": "Base-rate Reliability",
    }
    for name, ys in pairs.items():
        xs_f: list[float] = []
        ys_f: list[float] = []
        for x, y in zip(v2, ys):
            if x is None or y is None:
                continue
            xs_f.append(x)
            ys_f.append(y)
        rho = spearman_rho(xs_f, ys_f) if len(xs_f) >= 3 else None
        out[f"spearman_v2_raw_vs_{name}"] = {
            "rho": round(rho, 6) if rho is not None else None,
            "n": len(xs_f),
        }
    return out


def _v1_auc_score(row: dict[str, Any]) -> float | None:
    raw = _safe_float(row.get("v1_raw_score_A"))
    if raw is not None:
        return raw
    return _safe_float(row.get("v1_score_A"))


def _strict_paired_settled(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if r.get("strict_paired") is not True:
            continue
        if r.get("outcome") not in {EVAL_WON, EVAL_LOST}:
            continue
        if _safe_float(r.get("v2_raw_score")) is None:
            continue
        if _v1_auc_score(r) is None:
            continue
        out.append(r)
    return out


def build_pair_alignment_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    paired_count = 0
    strict_paired_count = 0
    failures: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.get("paired") is True:
            paired_count += 1
            if r.get("strict_paired") is True:
                strict_paired_count += 1
            else:
                reason = str(r.get("pair_alignment_reason") or "unknown")
                failures[reason] += 1
    return {
        "paired_count": paired_count,
        "strict_paired_count": strict_paired_count,
        "pair_alignment_failures": dict(sorted(failures.items())),
    }


def build_ranking_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = _settled_binary(rows)
    y = np.array(
        [1.0 if r.get("outcome") == EVAL_WON else 0.0 for r in settled], dtype=float
    )
    s_v2 = np.array(
        [_safe_float(r.get("v2_raw_score")) or 0.0 for r in settled], dtype=float
    )
    auc_v2 = roc_auc(y, s_v2) if len(settled) >= 2 else None

    paired = [
        r
        for r in settled
        if r.get("paired") is True and _safe_float(r.get("v1_score_A")) is not None
    ]
    auc_v1 = None
    if len(paired) >= 2:
        y1 = np.array(
            [1.0 if r.get("outcome") == EVAL_WON else 0.0 for r in paired], dtype=float
        )
        s1 = np.array(
            [_safe_float(r.get("v1_score_A")) or 0.0 for r in paired], dtype=float
        )
        auc_v1 = roc_auc(y1, s1)

    strict = _strict_paired_settled(rows)
    auc_v2_strict = None
    auc_v1_strict = None
    delta_auc = None
    v1_score_source = "v1_raw_score_A"
    if strict:
        uses_raw = any(_safe_float(r.get("v1_raw_score_A")) is not None for r in strict)
        v1_score_source = "v1_raw_score_A" if uses_raw else "v1_score_A"
    if len(strict) >= 2:
        y_s = np.array(
            [1.0 if r.get("outcome") == EVAL_WON else 0.0 for r in strict], dtype=float
        )
        s_v2_s = np.array(
            [_safe_float(r.get("v2_raw_score")) or 0.0 for r in strict], dtype=float
        )
        s_v1_s = np.array([_v1_auc_score(r) or 0.0 for r in strict], dtype=float)
        auc_v2_strict = roc_auc(y_s, s_v2_s)
        auc_v1_strict = roc_auc(y_s, s_v1_s)
        if auc_v2_strict is not None and auc_v1_strict is not None:
            delta_auc = auc_v2_strict - auc_v1_strict

    auc_v2_rounded = round(auc_v2, 6) if auc_v2 is not None else None
    return {
        "roc_auc_v2_raw_score": auc_v2_rounded,
        "roc_auc_v2_all_settled": auc_v2_rounded,
        "roc_auc_v1_score_A_paired_only": round(auc_v1, 6) if auc_v1 is not None else None,
        "roc_auc_v2_strict_paired": round(auc_v2_strict, 6)
        if auc_v2_strict is not None
        else None,
        "roc_auc_v1_A_strict_paired": round(auc_v1_strict, 6)
        if auc_v1_strict is not None
        else None,
        "delta_auc_v2_minus_v1_strict_paired": round(delta_auc, 6)
        if delta_auc is not None
        else None,
        "n_settled_v2": len(settled),
        "n_paired_settled": len(paired),
        "n_strict_paired_settled": len(strict),
        "v1_score_source_strict_paired": v1_score_source,
        "strict_paired_pair_keys": [
            r.get("pair_key") for r in strict if r.get("pair_key") is not None
        ],
    }


def build_top_per_fixture_report(
    top_rows: list[dict[str, Any]],
    *,
    label: str,
) -> dict[str, Any]:
    """Aggregate pre-selected top-per-fixture rows (outcome already attached)."""
    settled = [r for r in top_rows if r.get("outcome") in {EVAL_WON, EVAL_LOST}]
    stats = _group_stats(settled)
    return {
        "label": label,
        "fixtures": len(top_rows),
        "settled": len(settled),
        "settled_fixtures": len(settled),
        "wins": stats["wins"],
        "losses": stats["losses"],
        "hit_rate": stats["hit_rate"],
        "avg_quote": stats["avg_quote"],
        "median_quote": stats["median_quote"],
        "profit_1u": stats["profit_1u"],
        "ROI": stats["ROI"],
        "n": stats["n"],
        "avg_v2_score": stats["avg_v2_score"],
    }


def build_paired_top_delta(
    top_v2: dict[str, Any],
    top_v1: dict[str, Any],
) -> dict[str, Any]:
    hr2 = top_v2.get("hit_rate")
    hr1 = top_v1.get("hit_rate")
    roi2 = top_v2.get("ROI")
    roi1 = top_v1.get("ROI")
    return {
        "delta_hit_rate": round(hr2 - hr1, 6)
        if hr2 is not None and hr1 is not None
        else None,
        "delta_ROI": round(roi2 - roi1, 6)
        if roi2 is not None and roi1 is not None
        else None,
    }


def filter_rows_by_cohort(
    rows: list[dict[str, Any]], cohort: str
) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("holdout_cohort") == cohort]


def build_holdout_diagnostics(
    csv_rows: list[dict[str, Any]],
    *,
    top_v2_all_markets_rows: list[dict[str, Any]] | None = None,
    top_v2_strict_paired_rows: list[dict[str, Any]] | None = None,
    top_v1_strict_paired_rows: list[dict[str, Any]] | None = None,
    # Back-compat aliases
    top_v2_fixture_rows: list[dict[str, Any]] | None = None,
    top_v1_fixture_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Full diagnostics block for manifest."""
    top_v2_all = top_v2_all_markets_rows or top_v2_fixture_rows or []
    top_v2_strict = top_v2_strict_paired_rows or []
    top_v1_strict = top_v1_strict_paired_rows or top_v1_fixture_rows or []

    def _filter_tops(rows: list[dict], cohort: str | None) -> list[dict]:
        if cohort is None:
            return rows
        return [t for t in rows if t.get("holdout_cohort") == cohort]

    def bundle(rows: list[dict[str, Any]], cohort: str | None) -> dict[str, Any]:
        tv2_all = _filter_tops(top_v2_all, cohort)
        tv2_strict = _filter_tops(top_v2_strict, cohort)
        tv1_strict = _filter_tops(top_v1_strict, cohort)
        top_v2_rep = build_top_per_fixture_report(
            tv2_strict, label="top_v2_strict_paired_per_fixture"
        )
        top_v1_rep = build_top_per_fixture_report(
            tv1_strict, label="top_v1_strict_paired_per_fixture"
        )
        return {
            "n_rows": len(rows),
            "n_settled": len(_settled_binary(rows)),
            **build_pair_alignment_report(rows),
            "fixed_score_bands": build_fixed_band_report(rows),
            "quantiles": build_quantile_report(rows),
            "odds_controlled": build_odds_controlled_report(rows),
            "market_family_control": build_market_family_report(rows),
            "correlation_diagnostics": build_correlation_diagnostics(rows),
            "ranking_quality": build_ranking_quality(rows),
            "top_v2_all_markets_per_fixture": build_top_per_fixture_report(
                tv2_all, label="top_v2_all_markets_per_fixture"
            ),
            "top_v2_strict_paired_per_fixture": top_v2_rep,
            "top_v1_strict_paired_per_fixture": top_v1_rep,
            "paired_top_delta": build_paired_top_delta(top_v2_rep, top_v1_rep),
            # Legacy aliases (operational / soft era)
            "top_v2_per_fixture": build_top_per_fixture_report(
                tv2_all, label="top_v2"
            ),
            "top_v1_per_fixture": top_v1_rep,
        }

    smoke = filter_rows_by_cohort(csv_rows, COHORT_TECHNICAL_SMOKE)
    prospective = filter_rows_by_cohort(csv_rows, COHORT_PROSPECTIVE)

    return {
        "PRIMARY_DIAGNOSTIC_COHORT": PRIMARY_DIAGNOSTIC_COHORT,
        "technical_smoke_cohort": bundle(smoke, COHORT_TECHNICAL_SMOKE),
        "prospective_holdout": bundle(prospective, COHORT_PROSPECTIVE),
        "all_cohorts": bundle(csv_rows, None),
        "primary": bundle(prospective, COHORT_PROSPECTIVE),
    }


__all__ = [
    "FIXED_V2_BANDS",
    "MIN_N_FOR_TERTILES",
    "MIN_N_PER_SUBGROUP",
    "ODDS_BUCKETS",
    "build_holdout_diagnostics",
    "build_pair_alignment_report",
    "build_quantile_report",
    "build_ranking_quality",
    "sort_rows_by_raw_desc",
]
