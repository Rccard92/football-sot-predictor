"""Helper modeling Credibilità X — Fase 1D (split temporale, metriche, bootstrap, ROI OOF)."""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timezone
from typing import Any

import numpy as np

from app.services.cecchino.cecchino_draw_credibility_statistics_helpers import (
    PROB_CLAMP_HI,
    PROB_CLAMP_LO,
    auc_mann_whitney,
    brier_score,
    log_loss_score,
)

C_GRID: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0)
MAX_QUANTILE_BINS = 5
MIN_VAL_ROWS = 50
MIN_VAL_DRAWS = 10
BRIER_TOLERANCE_REDUCED = 0.002

FORBIDDEN_TRAIN_FEATURES: tuple[str, ...] = (
    "under_minus_over_pp",
    "under_strength_pp",
    "quota_cecchino_x",
    "dominance_pp",
    "dominance_normalized_pp",
    "conviction_index_candidate",
    "f36_abs",
    "f36_score_existing",
    "probability_gap_1_2_pp",
    "probability_balance_index",
    "quota_book_x",
    "prob_book_x_norm",
    "deviation_x_pp",
    "quota_book_1",
    "quota_book_2",
    "prob_book_1_norm",
    "prob_book_2_norm",
)

FEATURE_MANIFEST: dict[str, Any] = {
    "continuous": [
        "prob_under_2_5_cecchino_pct",
        "prob_x_norm",
        "x_directional_conviction_candidate",
    ],
    "categorical": ["x_rank", "f36_class_existing"],
    "nonlinear_binned": ["gap_coherence_index_candidate"],
    "interaction_only": ["x_direction_bucket", "dominant_sign_normalized"],
    "control_only": ["hours_to_kickoff", "hours_to_kickoff_class"],
    "excluded": list(FORBIDDEN_TRAIN_FEATURES),
    "notes": [
        "Book escluso dal training (solo benchmark).",
        "hours_to_kickoff solo in MODEL_CONTROL_TIMING.",
        "Nessuna feature binaria da pattern candidati 1C.",
    ],
}


def clamp_prob(p: float) -> float:
    return float(min(PROB_CLAMP_HI, max(PROB_CLAMP_LO, p)))


def parse_kickoff(row: dict[str, Any]) -> datetime | None:
    raw = row.get("kickoff")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        try:
            s = str(raw).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def kickoff_calendar_date(row: dict[str, Any]) -> date | None:
    ko = parse_kickoff(row)
    return ko.date() if ko else None


def sort_rows_by_kickoff(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(r: dict[str, Any]) -> tuple:
        ko = parse_kickoff(r)
        return (ko or datetime.min.replace(tzinfo=timezone.utc), r.get("provider_fixture_id") or 0)

    return sorted(rows, key=_key)


def group_rows_by_date(rows: list[dict[str, Any]]) -> list[tuple[date, list[dict[str, Any]]]]:
    ordered = sort_rows_by_kickoff(rows)
    groups: dict[date, list[dict[str, Any]]] = {}
    order: list[date] = []
    for r in ordered:
        d = kickoff_calendar_date(r)
        if d is None:
            continue
        if d not in groups:
            groups[d] = []
            order.append(d)
        groups[d].append(r)
    return [(d, groups[d]) for d in order]


def temporal_holdout_split(
    rows: list[dict[str, Any]],
    *,
    final_holdout_pct: float,
) -> dict[str, Any]:
    """Split cronologico: date più recenti ≈ holdout_pct; nessuna data spezzata."""
    groups = group_rows_by_date(rows)
    total = sum(len(g) for _, g in groups)
    if total == 0 or not groups:
        return {
            "development_rows": [],
            "holdout_rows": [],
            "development_dates": [],
            "holdout_dates": [],
            "actual_holdout_pct": 0.0,
        }

    target = max(1, int(round(total * final_holdout_pct)))
    holdout_dates: list[date] = []
    holdout_rows: list[dict[str, Any]] = []
    remaining = list(groups)
    while remaining and len(holdout_rows) < target:
        d, g = remaining.pop()  # più recente
        holdout_dates.insert(0, d)
        holdout_rows = g + holdout_rows

    # Se holdout troppo grande (>35%+buffer) e possiamo lasciare almeno 1 data in holdout
    # lasciamo così: prioritario non spezzare date e raggiungere ≈ pct.
    development_rows: list[dict[str, Any]] = []
    development_dates: list[date] = []
    for d, g in remaining:
        development_dates.append(d)
        development_rows.extend(g)

    actual = (len(holdout_rows) / total) if total else 0.0
    return {
        "development_rows": development_rows,
        "holdout_rows": holdout_rows,
        "development_dates": development_dates,
        "holdout_dates": holdout_dates,
        "actual_holdout_pct": round(actual, 4),
        "total_rows": total,
    }


def _fold_ok(rows: list[dict[str, Any]]) -> bool:
    if len(rows) < MIN_VAL_ROWS:
        return False
    draws = sum(1 for r in rows if int(r.get("draw_ft") or 0) == 1)
    if draws < MIN_VAL_DRAWS:
        return False
    non = len(rows) - draws
    return draws > 0 and non > 0


def expanding_window_folds(
    development_rows: list[dict[str, Any]],
    *,
    inner_splits: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Folds a finestra crescente su date development. Riduce split se criteri non soddisfatti."""
    warnings: list[str] = []
    groups = group_rows_by_date(development_rows)
    n_dates = len(groups)
    if n_dates < 2:
        warnings.append("insufficient_dates_for_expanding_cv")
        return [], warnings

    splits = min(inner_splits, max(2, n_dates - 1))
    folds: list[dict[str, Any]] = []

    while splits >= 2:
        folds = []
        # Partiziona le date in (splits+1) blocchi cronologici: train cresce, val = blocco successivo
        # Usa indici date: per fold k, train = dates[0 : cut_k], val = dates[cut_k : cut_{k+1}]
        cuts: list[int] = []
        for i in range(1, splits + 1):
            # cut dopo circa i/(splits+1) delle date, ma lascia almeno 1 data per val
            cut = max(1, int(round(n_dates * i / (splits + 1))))
            cut = min(cut, n_dates - 1)
            cuts.append(cut)
        # Unisci cut duplicati
        unique_cuts = sorted(set(cuts))
        if len(unique_cuts) < 2:
            splits -= 1
            continue

        ok = True
        for fi, cut in enumerate(unique_cuts):
            next_cut = unique_cuts[fi + 1] if fi + 1 < len(unique_cuts) else n_dates
            if next_cut <= cut:
                continue
            train_groups = groups[:cut]
            val_groups = groups[cut:next_cut]
            train_rows = [r for _, g in train_groups for r in g]
            val_rows = [r for _, g in val_groups for r in g]
            if not _fold_ok(val_rows) or len(train_rows) < MIN_VAL_ROWS:
                ok = False
                break
            train_dates = [d.isoformat() for d, _ in train_groups]
            val_dates = [d.isoformat() for d, _ in val_groups]
            folds.append(
                {
                    "fold_id": f"fold_{fi + 1}",
                    "train_rows": train_rows,
                    "validation_rows": val_rows,
                    "train_dates": train_dates,
                    "validation_dates": val_dates,
                    "train_draw_rate": (
                        sum(1 for r in train_rows if int(r.get("draw_ft") or 0) == 1) / len(train_rows)
                        if train_rows
                        else None
                    ),
                    "validation_draw_rate": (
                        sum(1 for r in val_rows if int(r.get("draw_ft") or 0) == 1) / len(val_rows)
                        if val_rows
                        else None
                    ),
                }
            )
        if ok and len(folds) >= 2:
            if splits < inner_splits:
                warnings.append(f"inner_splits_reduced_to_{splits}")
            return folds, warnings
        splits -= 1
        warnings.append("invalid_fold_criteria_reducing_splits")

    warnings.append("no_valid_expanding_folds")
    return [], warnings


def build_quantile_boundaries(values: list[float], n_bins: int = MAX_QUANTILE_BINS) -> list[float]:
    """Boundaries interne (n_bins-1) da quantili sul train. Nessun hardcode produttivo."""
    if not values or n_bins < 2:
        return []
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return []
    qs = np.linspace(0, 1, n_bins + 1)[1:-1]
    bounds = sorted({float(np.quantile(arr, q)) for q in qs})
    # rimuovi duplicati numerici
    cleaned: list[float] = []
    for b in bounds:
        if not cleaned or abs(b - cleaned[-1]) > 1e-9:
            cleaned.append(b)
    return cleaned


def assign_quantile_bin(value: float | None, boundaries: list[float]) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "missing"
    if not boundaries:
        return "bin_0"
    for i, b in enumerate(boundaries):
        if value <= b:
            return f"bin_{i}"
    return f"bin_{len(boundaries)}"


def ece_score(probs: list[float], y_true: list[int], n_bins: int = 10) -> float | None:
    if not probs or len(probs) != len(y_true):
        return None
    n = len(probs)
    if n == 0:
        return None
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        idx = [j for j, p in enumerate(probs) if (p >= lo if i == 0 else p > lo) and p <= hi]
        if not idx:
            continue
        conf = sum(probs[j] for j in idx) / len(idx)
        acc = sum(y_true[j] for j in idx) / len(idx)
        ece += (len(idx) / n) * abs(acc - conf)
    return float(ece)


def calibration_slope_intercept(
    probs: list[float], y_true: list[int]
) -> dict[str, float | None]:
    """Regressione lineare osservato~predetto su bin; fallback OLS su punti."""
    if len(probs) < 5 or len(set(y_true)) < 2:
        return {"slope": None, "intercept": None}
    try:
        from sklearn.linear_model import LinearRegression

        x = np.asarray(probs, dtype=float).reshape(-1, 1)
        y = np.asarray(y_true, dtype=float)
        lr = LinearRegression()
        lr.fit(x, y)
        return {"slope": float(lr.coef_[0]), "intercept": float(lr.intercept_)}
    except Exception:
        return {"slope": None, "intercept": None}


def quintile_lifts(
    probs: list[float], y_true: list[int]
) -> dict[str, float | None]:
    if len(probs) < 5:
        return {
            "top_quintile_draw_rate": None,
            "top_quintile_lift": None,
            "bottom_quintile_draw_rate": None,
            "bottom_quintile_lift": None,
        }
    base = sum(y_true) / len(y_true) if y_true else 0.0
    order = sorted(range(len(probs)), key=lambda i: probs[i])
    q = max(1, len(order) // 5)
    bottom = order[:q]
    top = order[-q:]
    bot_rate = sum(y_true[i] for i in bottom) / len(bottom)
    top_rate = sum(y_true[i] for i in top) / len(top)
    return {
        "top_quintile_draw_rate": round(top_rate, 4),
        "top_quintile_lift": round(top_rate / base, 4) if base > 0 else None,
        "bottom_quintile_draw_rate": round(bot_rate, 4),
        "bottom_quintile_lift": round(bot_rate / base, 4) if base > 0 else None,
    }


def prediction_metrics(
    probs: list[float],
    y_true: list[int],
    *,
    baseline_prob: float,
) -> dict[str, Any]:
    clamped = [clamp_prob(p) for p in probs]
    brier = brier_score(clamped, y_true)
    base_probs = [clamp_prob(baseline_prob)] * len(y_true)
    base_brier = brier_score(base_probs, y_true)
    bss = None
    if brier is not None and base_brier is not None and base_brier > 0:
        bss = 1.0 - (brier / base_brier)
    calib = calibration_slope_intercept(clamped, y_true)
    lifts = quintile_lifts(clamped, y_true)
    mean_p = float(np.mean(clamped)) if clamped else None
    std_p = float(np.std(clamped)) if len(clamped) > 1 else 0.0
    return {
        "brier_score": brier,
        "baseline_brier": base_brier,
        "brier_skill_score": bss,
        "log_loss": log_loss_score(clamped, y_true),
        "auc": auc_mann_whitney(y_true, clamped),
        "ece": ece_score(clamped, y_true),
        "calibration_intercept": calib["intercept"],
        "calibration_slope": calib["slope"],
        "prediction_mean": mean_p,
        "prediction_standard_deviation": std_p,
        **lifts,
    }


def build_quantile_boundaries_from_train_probs(
    train_probs: list[float], n_bins: int = 5
) -> list[float]:
    return build_quantile_boundaries(train_probs, n_bins=n_bins)


def apply_bin_index(value: float, boundaries: list[float]) -> int:
    if not boundaries:
        return 0
    for i, b in enumerate(boundaries):
        if value <= b:
            return i
    return len(boundaries)


def cluster_bootstrap_ci(
    dates: list[date],
    date_to_rows: dict[date, list[dict[str, Any]]],
    *,
    metric_fn,
    iterations: int,
    seed: int,
) -> dict[str, float | None]:
    """Bootstrap clusterizzato per calendar date."""
    if not dates:
        return {"lower": None, "upper": None, "mean": None}
    rng = random.Random(seed)
    scores: list[float] = []
    for _ in range(iterations):
        sampled = [dates[rng.randrange(len(dates))] for _ in dates]
        rows: list[dict[str, Any]] = []
        for d in sampled:
            rows.extend(date_to_rows.get(d, []))
        if not rows:
            continue
        val = metric_fn(rows)
        if val is not None and math.isfinite(val):
            scores.append(float(val))
    if len(scores) < 10:
        return {"lower": None, "upper": None, "mean": float(np.mean(scores)) if scores else None}
    lo, hi = np.percentile(scores, [2.5, 97.5])
    return {"lower": float(lo), "upper": float(hi), "mean": float(np.mean(scores))}


def roi_from_bets(bets: list[dict[str, Any]]) -> dict[str, Any]:
    """bets: [{odd, win: bool}]"""
    n = len(bets)
    if n == 0:
        return {
            "bets": 0,
            "wins": 0,
            "average_odd": None,
            "net_profit": 0.0,
            "roi": None,
            "profitable_status": "insufficient_sample",
        }
    wins = sum(1 for b in bets if b.get("win"))
    odds = [float(b["odd"]) for b in bets if b.get("odd") is not None]
    avg_odd = float(np.mean(odds)) if odds else None
    # unit stake 1
    profit = sum((float(b["odd"]) - 1.0) if b.get("win") else -1.0 for b in bets)
    roi = profit / n
    return {
        "bets": n,
        "wins": wins,
        "average_odd": avg_odd,
        "net_profit": round(profit, 4),
        "roi": round(roi, 4),
        "profitable_status": "inconclusive",  # CI set by caller
    }


def profitable_status_from_ci(ci: dict[str, float | None], *, min_bets: int, bets: int) -> str:
    if bets < min_bets:
        return "insufficient_sample"
    lo, hi = ci.get("lower"), ci.get("upper")
    if lo is None or hi is None:
        return "inconclusive"
    if lo > 0:
        return "positive_ci_above_zero"
    if hi < 0:
        return "negative_ci_below_zero"
    return "inconclusive"


def complexity_diagnostics(
    *,
    raw_feature_count: int,
    encoded_feature_count: int,
    interaction_count: int,
    nonzero_coef_count: int,
    train_rows: int,
) -> dict[str, Any]:
    trpc = (train_rows / nonzero_coef_count) if nonzero_coef_count else None
    warnings: list[str] = []
    if trpc is not None and trpc < 5:
        warnings.append("severe_low_train_rows_per_coefficient")
    elif trpc is not None and trpc < 10:
        warnings.append("low_train_rows_per_coefficient")
    return {
        "raw_feature_count": raw_feature_count,
        "encoded_feature_count": encoded_feature_count,
        "interaction_count": interaction_count,
        "non_zero_coefficient_count": nonzero_coef_count,
        "effective_complexity": nonzero_coef_count,
        "train_rows_per_coefficient": round(trpc, 2) if trpc is not None else None,
        "warnings": warnings,
    }


def coefficient_stability_status(
    coefs_per_fold: list[float],
    *,
    present_all_folds: bool,
) -> str:
    if not coefs_per_fold or not present_all_folds:
        return "unavailable"
    signs = [1 if c > 1e-8 else (-1 if c < -1e-8 else 0) for c in coefs_per_fold]
    nonzero_signs = [s for s in signs if s != 0]
    sign_changes = 0
    for i in range(1, len(nonzero_signs)):
        if nonzero_signs[i] != nonzero_signs[i - 1]:
            sign_changes += 1
    std = float(np.std(coefs_per_fold)) if len(coefs_per_fold) > 1 else 0.0
    mean_abs = float(np.mean(np.abs(coefs_per_fold))) + 1e-12
    cv = std / mean_abs
    if sign_changes >= 2 or cv > 1.5:
        return "unstable"
    if sign_changes == 1 or cv > 0.75:
        return "mostly_stable"
    return "stable"


def pick_best_c(
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """candidates: {C, mean_brier, mean_log_loss, simplicity_rank} — smaller C = more regularized."""
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda x: (
            x["mean_brier"] if x["mean_brier"] is not None else 999.0,
            x["mean_log_loss"] if x["mean_log_loss"] is not None else 999.0,
            x.get("simplicity_rank", 0),
            x["C"],
        ),
    )[0]


def eligibility_for_model(
    *,
    holdout_bss: float | None,
    holdout_brier: float | None,
    m1_holdout_brier: float | None,
    holdout_log_loss: float | None,
    baseline_log_loss: float | None,
    coherent_folds: int,
    leakage: bool,
    complexity_ok: bool,
    control_only: bool,
    unstable: bool,
    stable_improvement_cv: bool,
    brier_delta_ci_favorable: bool,
    main_coefs_stable: bool,
    reduced_not_worse: bool,
) -> str:
    if control_only:
        return "NOT_READY"
    if leakage or unstable or not complexity_ok:
        return "NOT_READY"
    if holdout_bss is None or holdout_bss <= 0:
        return "NOT_READY"
    if holdout_brier is None:
        return "NOT_READY"
    if m1_holdout_brier is not None and holdout_brier >= m1_holdout_brier:
        return "NOT_READY"
    if (
        holdout_log_loss is not None
        and baseline_log_loss is not None
        and holdout_log_loss > baseline_log_loss
    ):
        return "NOT_READY"
    if coherent_folds < 2:
        return "NOT_READY"
    base = "EXPLORATORY_CANDIDATE"
    if (
        stable_improvement_cv
        and brier_delta_ci_favorable
        and main_coefs_stable
        and reduced_not_worse
    ):
        return "LEADING_EXPLORATORY_CANDIDATE"
    return base
