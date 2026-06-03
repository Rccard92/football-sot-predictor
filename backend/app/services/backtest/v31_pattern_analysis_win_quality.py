"""Classificazione win_quality e pesi diagnostici (solo post-match)."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_pattern_analysis_buckets import (
    actual_bucket_dynamic,
    actual_bucket_static,
)

WIN_QUALITY_KEYS = (
    "HEALTHY_WIN",
    "ACCEPTABLE_WIN",
    "UNDERSTATED_WIN",
    "EXTREME_WIN_OUTLIER",
    "BAD_LOSS_OVERESTIMATION",
    "CLOSE_LOSS",
    "NORMAL_LOSS",
)

DIAGNOSTIC_WEIGHTS: dict[str, float] = {
    "HEALTHY_WIN": 1.0,
    "ACCEPTABLE_WIN": 0.6,
    "UNDERSTATED_WIN": 0.9,
    "EXTREME_WIN_OUTLIER": 0.25,
    "BAD_LOSS_OVERESTIMATION": 0.9,
    "CLOSE_LOSS": 0.2,
    "NORMAL_LOSS": 0.5,
}


def diagnostic_weight_for(win_quality: str | None) -> float:
    if not win_quality:
        return 0.0
    return DIAGNOSTIC_WEIGHTS.get(win_quality, 0.0)


def classify_win_quality(
    *,
    predicted: float | None,
    actual: float | None,
    abs_error: float | None,
    actual_bucket_dynamic: str | None,
) -> tuple[str | None, bool, bool]:
    """Ritorna win_quality, coverage_win, coverage_loss."""
    if predicted is None or actual is None or abs_error is None:
        return None, False, False

    pred_f = float(predicted)
    act_f = float(actual)
    ae = float(abs_error)
    coverage_win = act_f > pred_f
    coverage_loss = not coverage_win

    if coverage_win:
        if actual_bucket_dynamic == "extreme_total":
            return "EXTREME_WIN_OUTLIER", coverage_win, coverage_loss
        if ae <= 1.5:
            return "HEALTHY_WIN", coverage_win, coverage_loss
        if ae <= 2.5:
            return "ACCEPTABLE_WIN", coverage_win, coverage_loss
        if (act_f - pred_f) > 2.5:
            return "UNDERSTATED_WIN", coverage_win, coverage_loss
        return "ACCEPTABLE_WIN", coverage_win, coverage_loss

    if (pred_f - act_f) > 2.5:
        return "BAD_LOSS_OVERESTIMATION", coverage_win, coverage_loss
    if ae <= 1.5:
        return "CLOSE_LOSS", coverage_win, coverage_loss
    return "NORMAL_LOSS", coverage_win, coverage_loss


def enrich_row_with_pattern_fields(
    row: dict[str, Any],
    *,
    p25: float | None,
    p75: float | None,
    p90: float | None,
    p95: float | None,
) -> dict[str, Any]:
    """Arricchisce riga post-predizione; non modifica il trace predittivo."""
    out = dict(row)
    actual = out.get("actual_total_sot")
    dyn = actual_bucket_dynamic(actual, p25=p25, p75=p75, p90=p90, p95=p95)
    stat = actual_bucket_static(actual)
    out["actual_bucket_dynamic"] = dyn
    out["actual_bucket_static"] = stat
    out["is_extreme_outlier"] = dyn == "extreme_total"

    wq, cov_win, cov_loss = classify_win_quality(
        predicted=out.get("predicted_total_sot"),
        actual=actual,
        abs_error=out.get("abs_error"),
        actual_bucket_dynamic=dyn,
    )
    out["win_quality"] = wq
    out["coverage_win"] = cov_win
    out["coverage_loss"] = cov_loss
    out["diagnostic_weight"] = diagnostic_weight_for(wq)
    return out
