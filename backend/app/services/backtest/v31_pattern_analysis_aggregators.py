"""Aggregati pattern vincenti, persi, alte e outlier."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.backtest.v31_calibration_simulator_error_reasons import safe_probable_reason
from app.services.backtest.v31_pattern_analysis_buckets import is_high_or_above_dynamic, is_non_extreme_high_dynamic
from app.services.backtest.v31_pattern_analysis_win_quality import WIN_QUALITY_KEYS

WIN_CATEGORIES = ("HEALTHY_WIN", "ACCEPTABLE_WIN", "UNDERSTATED_WIN", "EXTREME_WIN_OUTLIER")
LOSS_CATEGORIES = ("CLOSE_LOSS", "NORMAL_LOSS", "BAD_LOSS_OVERESTIMATION")

EXAMPLE_LIMIT = 5


def _ok_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("prediction_status") == "ok" and r.get("actual_total_sot") is not None]


def _fixture_example(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": row.get("fixture_id"),
        "match": row.get("match"),
        "predicted_total_sot": row.get("predicted_total_sot"),
        "actual_total_sot": row.get("actual_total_sot"),
        "abs_error": row.get("abs_error"),
        "actual_bucket_dynamic": row.get("actual_bucket_dynamic"),
        "actual_bucket_static": row.get("actual_bucket_static"),
        "win_quality": row.get("win_quality"),
        "probable_reason": safe_probable_reason(row),
    }


def _category_block(rows: list[dict[str, Any]], category: str, total: int) -> dict[str, Any]:
    subset = [r for r in rows if r.get("win_quality") == category]
    count = len(subset)
    mae = None
    if subset:
        mae = round(sum(float(r.get("abs_error") or 0) for r in subset) / count, 4)
    bucket_dist = Counter(r.get("actual_bucket_dynamic") for r in subset if r.get("actual_bucket_dynamic"))
    tags = Counter()
    for r in subset:
        reason = safe_probable_reason(r)
        if reason:
            tags[reason[:80]] += 1
    top_tags = [{"tag": k, "count": v} for k, v in tags.most_common(5)]
    examples = sorted(subset, key=lambda r: float(r.get("abs_error") or 0), reverse=True)[:EXAMPLE_LIMIT]
    return {
        "count": count,
        "pct_of_total": round(100.0 * count / total, 1) if total else 0.0,
        "avg_abs_error": mae,
        "actual_bucket_dynamic_distribution": dict(bucket_dist),
        "pattern_tags": top_tags,
        "examples": [_fixture_example(r) for r in examples],
    }


def winning_patterns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _ok_rows(rows)
    total = len(scored)
    wins = [r for r in scored if r.get("coverage_win")]
    win_total = len(wins) or 1
    categories = {cat: _category_block(scored, cat, total) for cat in WIN_CATEGORIES}
    understated_pct = round(100.0 * categories["UNDERSTATED_WIN"]["count"] / win_total, 1)
    interpretation = (
        "Il modello vince spesso, ma molte vittorie sono sottostime: "
        "questo conferma che il modello è troppo prudente."
        if understated_pct >= 30
        else "Le vittorie sono prevalentemente vicine al reale."
    )
    return {
        "total_fixtures": total,
        "total_wins": len(wins),
        "categories": categories,
        "interpretation": interpretation,
    }


def _is_false_high_prediction(row: dict[str, Any]) -> bool:
    pb = row.get("predicted_bucket") or ""
    ab = row.get("actual_bucket_static") or row.get("actual_bucket") or ""
    return pb in ("high_total", "very_high_total") and ab in ("normal", "low")


def _is_low_block_not_detected(row: dict[str, Any]) -> bool:
    if row.get("win_quality") != "BAD_LOSS_OVERESTIMATION":
        return False
    trace = row.get("trace") if isinstance(row.get("trace"), dict) else {}
    boost_reason = str(trace.get("boost_reason") or "")
    return "chaos" in boost_reason or "low_block" in boost_reason or float(trace.get("boost_applied") or 0) > 0.5


def losing_patterns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _ok_rows(rows)
    total = len(scored)
    categories = {cat: _category_block(scored, cat, total) for cat in LOSS_CATEGORIES}
    false_high = [r for r in scored if _is_false_high_prediction(r)]
    low_block = [r for r in scored if _is_low_block_not_detected(r)]
    special = {
        "false_high_prediction": {
            "count": len(false_high),
            "pct_of_total": round(100.0 * len(false_high) / total, 1) if total else 0.0,
            "examples": [_fixture_example(r) for r in false_high[:EXAMPLE_LIMIT]],
        },
        "low_block_not_detected": {
            "count": len(low_block),
            "pct_of_total": round(100.0 * len(low_block) / total, 1) if total else 0.0,
            "examples": [_fixture_example(r) for r in low_block[:EXAMPLE_LIMIT]],
        },
    }
    bad = categories["BAD_LOSS_OVERESTIMATION"]["count"]
    interpretation = (
        "Il modello perde spesso per sovrastima: spinge troppo su profili medi."
        if bad >= total * 0.15
        else "Le perdite sono distribuite senza sovrastima sistemica grave."
    )
    return {
        "total_fixtures": total,
        "total_losses": sum(1 for r in scored if r.get("coverage_loss")),
        "categories": categories,
        "special_categories": special,
        "interpretation": interpretation,
    }


def win_quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _ok_rows(rows)
    total = len(scored)
    counts = {k: sum(1 for r in scored if r.get("win_quality") == k) for k in WIN_QUALITY_KEYS}
    return {
        "total_fixtures": total,
        "counts": counts,
        "pct": {k: round(100.0 * v / total, 1) if total else 0.0 for k, v in counts.items()},
    }


def loss_quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _ok_rows(rows)
    total = len(scored)
    counts = {k: sum(1 for r in scored if r.get("win_quality") == k) for k in LOSS_CATEGORIES}
    return {
        "total_fixtures": total,
        "counts": counts,
        "pct": {k: round(100.0 * v / total, 1) if total else 0.0 for k, v in counts.items()},
    }


def high_and_outlier_summary(
    rows: list[dict[str, Any]],
    *,
    p75: float | None,
    p90: float | None,
    p95: float | None,
) -> dict[str, Any]:
    scored = _ok_rows(rows)
    actual_high = actual_p90 = actual_p95 = actual_static_extreme = 0
    pred_high = pred_very_high = pred_extreme = 0
    missed_high = missed_extreme = understated_extreme = 0

    for r in scored:
        act = float(r.get("actual_total_sot") or 0)
        pred = float(r.get("predicted_total_sot") or 0)
        dyn = r.get("actual_bucket_dynamic")
        if p75 is not None and act > p75:
            actual_high += 1
        if p90 is not None and act > p90:
            actual_p90 += 1
        if p95 is not None and act > p95:
            actual_p95 += 1
        if r.get("actual_bucket_static") == "extreme" or act >= 15:
            actual_static_extreme += 1

        pb = r.get("predicted_bucket") or ""
        if pb == "high_total":
            pred_high += 1
        elif pb == "very_high_total":
            pred_very_high += 1
        if r.get("actual_bucket_static") == "extreme" and pred >= 12:
            pred_extreme += 1

        if is_high_or_above_dynamic(dyn) and pred < (p75 or 8):
            missed_high += 1
        if dyn == "extreme_total" and (pred < act - 2.5):
            missed_extreme += 1
            if r.get("win_quality") == "EXTREME_WIN_OUTLIER":
                understated_extreme += 1

    return {
        "actual_above_p75": actual_high,
        "actual_above_p90": actual_p90,
        "actual_above_p95": actual_p95,
        "actual_static_extreme_gte_15": actual_static_extreme,
        "predicted_high": pred_high,
        "predicted_very_high": pred_very_high,
        "predicted_extreme_static": pred_extreme,
        "missed_high": missed_high,
        "missed_extreme": missed_extreme,
        "understated_extreme_wins": understated_extreme,
        "calibration_weight_reduced_count": understated_extreme,
        "interpretation": (
            "Il modello non riconosce quasi mai partite alte. "
            "Tuttavia, una parte delle partite molto alte è estrema e va trattata come outlier."
            if missed_high > actual_high * 0.5
            else "Il modello intercetta parte delle partite alte del campionato."
        ),
    }


def high_total_non_extreme_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _ok_rows(rows)
    subset = [
        r
        for r in scored
        if is_non_extreme_high_dynamic(r.get("actual_bucket_dynamic"))
    ]
    understated = [r for r in subset if r.get("win_quality") == "UNDERSTATED_WIN"]
    return {
        "count_high_non_extreme": len(subset),
        "understated_count": len(understated),
        "understated_pct": round(100.0 * len(understated) / len(subset), 1) if subset else 0.0,
        "avg_abs_error": round(sum(float(r.get("abs_error") or 0) for r in subset) / len(subset), 4)
        if subset
        else None,
    }


def extreme_outlier_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _ok_rows(rows)
    extreme = [r for r in scored if r.get("actual_bucket_dynamic") == "extreme_total"]
    ext_wins = [r for r in extreme if r.get("win_quality") == "EXTREME_WIN_OUTLIER"]
    return {
        "extreme_actual_count": len(extreme),
        "extreme_win_outlier_count": len(ext_wins),
        "extreme_avg_abs_error": round(sum(float(r.get("abs_error") or 0) for r in extreme) / len(extreme), 4)
        if extreme
        else None,
    }
