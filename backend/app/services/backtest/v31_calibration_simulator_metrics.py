"""Metriche predittive numeriche per simulatore v3.1."""

from __future__ import annotations

import math
import statistics
from typing import Any

from app.services.backtest.v31_calibration_simulator_buckets import BUCKET_KEYS, bucket_label
from app.services.backtest.v31_calibration_simulator_error_reasons import probable_reason

STRATEGY_VERDICT_LABELS = {
    "weak": "Debole",
    "promising": "Promettente",
    "candidate": "Candidata",
    "solid": "Solida",
}


def _round1(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 1)


def _round4(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 4)


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return _round4(sum(vals) / len(vals))


def _ok_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("prediction_status") == "ok"]


def _scored_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in _ok_rows(rows)
        if r.get("predicted_total_sot") is not None and r.get("actual_total_sot") is not None
    ]


def regression_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _scored_rows(rows)
    errs: list[float] = []
    signed: list[float] = []
    for r in scored:
        e = float(r["predicted_total_sot"]) - float(r["actual_total_sot"])
        signed.append(e)
        errs.append(abs(e))
    if not errs:
        return {"mae": None, "bias": None, "rmse": None, "n": 0}
    mse = sum(e * e for e in signed) / len(signed)
    return {
        "mae": _round4(sum(errs) / len(errs)),
        "bias": _round4(sum(signed) / len(signed)),
        "rmse": _round4(math.sqrt(mse)),
        "n": len(errs),
    }


def _percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return _round4(s[0])
    idx = (len(s) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return _round4(s[lo] * (1 - frac) + s[hi] * frac)


def prediction_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = _ok_rows(rows)
    scored = _scored_rows(rows)
    preds = [float(r["predicted_total_sot"]) for r in ok if r.get("predicted_total_sot") is not None]
    actuals = [float(r["actual_total_sot"]) for r in scored]
    pred_std = _round4(statistics.pstdev(preds)) if len(preds) > 1 else None
    actual_std = _round4(statistics.pstdev(actuals)) if len(actuals) > 1 else None
    compression = None
    if pred_std is not None and actual_std and actual_std > 0:
        compression = _round4(pred_std / actual_std)

    dist_warnings: list[str] = []
    if compression is not None and compression < 0.55:
        dist_warnings.append("V31_MODEL_TOO_FLAT")

    pred_high = sum(1 for p in preds if p > 9)
    pred_very_high = sum(1 for p in preds if p > 10)
    pred_low = sum(1 for p in preds if p < 6)
    act_high = sum(1 for a in actuals if a > 9)
    act_very_high = sum(1 for a in actuals if a > 10)
    act_low = sum(1 for a in actuals if a < 6)

    if act_high > 0 and pred_high < act_high * 0.5:
        dist_warnings.append("V31_HIGH_TOTAL_UNDERDETECTED")
    if act_low > 0 and pred_low < act_low * 0.5:
        dist_warnings.append("V31_LOW_TOTAL_UNDERDETECTED")

    return {
        "predicted_std": pred_std,
        "actual_std": actual_std,
        "compression_ratio": compression,
        "predicted_p10": _percentile(preds, 0.10),
        "predicted_p25": _percentile(preds, 0.25),
        "predicted_p50": _percentile(preds, 0.50),
        "predicted_p75": _percentile(preds, 0.75),
        "predicted_p90": _percentile(preds, 0.90),
        "actual_p10": _percentile(actuals, 0.10),
        "actual_p25": _percentile(actuals, 0.25),
        "actual_p50": _percentile(actuals, 0.50),
        "actual_p75": _percentile(actuals, 0.75),
        "actual_p90": _percentile(actuals, 0.90),
        "predicted_low_count_under_6": pred_low,
        "predicted_high_count_over_9": pred_high,
        "predicted_very_high_count_over_10": pred_very_high,
        "actual_low_count_under_6": act_low,
        "actual_high_count_over_9": act_high,
        "actual_very_high_count_over_10": act_very_high,
        "distribution_warnings": dist_warnings,
        "model_too_flat": "V31_MODEL_TOO_FLAT" in dist_warnings,
    }


def bucket_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _scored_rows(rows)
    if not scored:
        return {
            "bucket_accuracy": None,
            "high_total_recall": None,
            "high_total_precision": None,
            "low_total_recall": None,
            "low_total_precision": None,
            "confusion_matrix": {},
        }

    correct = 0
    confusion: dict[str, dict[str, int]] = {b: {k: 0 for k in BUCKET_KEYS} for b in BUCKET_KEYS}

    high_actual = low_actual = 0
    high_pred_hit = low_pred_hit = 0
    high_pred_total = low_pred_total = 0

    for r in scored:
        pb = r.get("predicted_bucket") or bucket_label(r.get("predicted_total_sot"))
        ab = r.get("actual_bucket") or bucket_label(r.get("actual_total_sot"))
        if pb is None or ab is None:
            continue
        if pb == ab:
            correct += 1
        if pb in confusion and ab in confusion[pb]:
            confusion[pb][ab] += 1
        if ab in ("high_total", "very_high_total"):
            high_actual += 1
            if pb in ("high_total", "very_high_total"):
                high_pred_hit += 1
        if pb in ("high_total", "very_high_total"):
            high_pred_total += 1
        if ab == "low_total":
            low_actual += 1
            if pb == "low_total":
                low_pred_hit += 1
        if pb == "low_total":
            low_pred_total += 1

    n = len(scored)
    return {
        "bucket_accuracy": _round1(100.0 * correct / n) if n else None,
        "high_total_recall": _round1(100.0 * high_pred_hit / high_actual) if high_actual else None,
        "high_total_precision": _round1(100.0 * high_pred_hit / high_pred_total) if high_pred_total else None,
        "low_total_recall": _round1(100.0 * low_pred_hit / low_actual) if low_actual else None,
        "low_total_precision": _round1(100.0 * low_pred_hit / low_pred_total) if low_pred_total else None,
        "high_actual_count": high_actual,
        "high_predicted_count": high_pred_total,
        "low_actual_count": low_actual,
        "low_predicted_count": low_pred_total,
        "confusion_matrix": confusion,
    }


def prediction_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = _ok_rows(rows)
    preds = [float(r["predicted_total_sot"]) for r in ok if r.get("predicted_total_sot") is not None]
    scored = _scored_rows(rows)
    actuals = [float(r["actual_total_sot"]) for r in scored]
    warnings: list[str] = []
    pred_avg = _mean(preds)
    scale_warning = False
    if pred_avg is not None and (pred_avg < 5.5 or pred_avg > 10.5):
        scale_warning = True
        warnings.append("V31_PREDICTION_SCALE_OUT_OF_RANGE")
    dist = prediction_distribution(rows)
    warnings.extend(dist.get("distribution_warnings") or [])
    return {
        "actual_total_avg": _mean(actuals),
        "predicted_total_avg": pred_avg,
        "predicted_total_min": min(preds) if preds else None,
        "predicted_total_max": max(preds) if preds else None,
        "actual_total_min": min(actuals) if actuals else None,
        "actual_total_max": max(actuals) if actuals else None,
        "predicted_under_3_count": sum(1 for p in preds if p < 3),
        "predicted_over_12_count": sum(1 for p in preds if p > 12),
        "scale_warning": scale_warning,
        "warnings": warnings,
        "prediction_distribution": dist,
    }


def _within_band(scored: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    if not scored:
        return {"count": 0, "pct": None}
    n = sum(1 for r in scored if (r.get("abs_error") or 99) <= threshold)
    return {"count": n, "pct": _round1(100.0 * n / len(scored))}


def _possible_factors(row: dict[str, Any]) -> list[str]:
    factors: list[str] = []
    missing = row.get("missing_fields") or []
    if missing:
        factors.append(f"Campi mancanti: {', '.join(missing[:4])}")
    trace = row.get("trace") or {}
    if trace.get("bias_offset_applied"):
        factors.append(f"Bias offset {trace['bias_offset_applied']}")
    return factors[:5]


def error_distribution(rows: list[dict[str, Any]], *, top_n: int = 5) -> dict[str, Any]:
    scored = _scored_rows(rows)
    over: list[dict[str, Any]] = []
    under: list[dict[str, Any]] = []
    for r in scored:
        err = float(r.get("error") or 0)
        entry = {
            "fixture_id": r.get("fixture_id"),
            "match": r.get("match"),
            "round_number": r.get("round_number"),
            "predicted_total_sot": r.get("predicted_total_sot"),
            "actual_total_sot": r.get("actual_total_sot"),
            "predicted_bucket": r.get("predicted_bucket"),
            "actual_bucket": r.get("actual_bucket"),
            "error": r.get("error"),
            "abs_error": r.get("abs_error"),
            "possible_factors": _possible_factors(r),
            "probable_reason": probable_reason(r),
        }
        if err > 0:
            over.append(entry)
        elif err < 0:
            under.append(entry)

    over_errors = [float(x["error"]) for x in over]
    under_errors = [float(x["error"]) for x in under]
    exact_near = sum(1 for r in scored if (r.get("abs_error") or 99) <= 0.5)

    worst_over = sorted(over, key=lambda x: float(x.get("error") or 0), reverse=True)[:top_n]
    worst_under = sorted(under, key=lambda x: float(x.get("error") or 0))[:top_n]

    return {
        "overestimated_count": len(over),
        "underestimated_count": len(under),
        "exact_or_near_count": exact_near,
        "avg_error_when_overestimated": _mean(over_errors),
        "avg_error_when_underestimated": _mean(under_errors),
        "worst_overestimations": worst_over,
        "worst_underestimations": worst_under,
    }


def coverage_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _scored_rows(rows)
    wins = sum(1 for r in scored if r.get("coverage_outcome") == "win")
    losses = sum(1 for r in scored if r.get("coverage_outcome") == "loss")
    total = wins + losses
    rate = _round1(100.0 * wins / total) if total > 0 else None
    reg = regression_metrics(rows)
    bias = reg.get("bias")
    warning = None
    if rate is not None and bias is not None and rate >= 70.0 and bias < -0.5:
        warning = (
            "Coverage alta con bias negativo: possibile sottostima sistematica, "
            "non vera precisione predittiva."
        )
    return {
        "coverage_win_count": wins,
        "coverage_loss_count": losses,
        "coverage_win_rate": rate,
        "coverage_bias_warning": warning,
    }


def predictive_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fixtures_total = len(rows)
    ok = _ok_rows(rows)
    failed = fixtures_total - len(ok)
    scored = _scored_rows(rows)
    reg = regression_metrics(rows)
    cov = coverage_metrics(rows)
    err_dist = error_distribution(rows)

    abs_errors = [float(r["abs_error"]) for r in scored if r.get("abs_error") is not None]
    median_abs = _round4(statistics.median(abs_errors)) if abs_errors else None
    error_std = _round4(statistics.pstdev(abs_errors)) if len(abs_errors) > 1 else None

    preds = [float(r["predicted_total_sot"]) for r in ok if r.get("predicted_total_sot") is not None]
    actuals = [float(r["actual_total_sot"]) for r in scored]

    within: dict[str, Any] = {}
    for label, thr in (("within_0_5", 0.5), ("within_1_0", 1.0), ("within_1_5", 1.5), ("within_2_0", 2.0)):
        band = _within_band(scored, thr)
        within[f"{label}_count"] = band["count"]
        within[f"{label}_pct"] = band["pct"]

    return {
        "fixtures_total": fixtures_total,
        "predictions_ok": len(ok),
        "predictions_failed": failed,
        "predicted_avg": _mean(preds),
        "actual_avg": _mean(actuals),
        "mae": reg.get("mae"),
        "rmse": reg.get("rmse"),
        "bias": reg.get("bias"),
        "median_abs_error": median_abs,
        "error_std": error_std,
        **within,
        **cov,
        **err_dist,
    }


def walk_forward_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def _wf(train_lo: int, train_hi: int, test_lo: int, test_hi: int, name: str) -> dict[str, Any]:
        test_rows = [r for r in rows if test_lo <= int(r.get("round_number") or 0) <= test_hi]
        train_rows = [r for r in rows if train_lo <= int(r.get("round_number") or 0) <= train_hi]
        pm = predictive_metrics(test_rows)
        return {
            "name": name,
            "train_rounds": f"{train_lo}-{train_hi}",
            "test_rounds": f"{test_lo}-{test_hi}",
            "train_fixture_count": len(train_rows),
            "test_fixture_count": len(test_rows),
            "test_predictive": {
                "mae": pm.get("mae"),
                "rmse": pm.get("rmse"),
                "bias": pm.get("bias"),
                "within_1_5_pct": pm.get("within_1_5_pct"),
                "coverage_win_rate": pm.get("coverage_win_rate"),
                "predictions_ok": pm.get("predictions_ok"),
            },
        }

    return {
        "wf_5_15_to_16_26": _wf(5, 15, 16, 26, "wf_5_15_to_16_26"),
        "wf_5_26_to_27_37": _wf(5, 26, 27, 37, "wf_5_26_to_27_37"),
    }


def compute_strategy_verdict(
    *,
    mae: float | None,
    within_1_5_pct: float | None,
    bias: float | None,
    predictions_ok: int,
    fixtures_total: int,
) -> str:
    if predictions_ok < max(1, int(fixtures_total * 0.9)):
        return "weak"
    if mae is None:
        return "weak"
    abs_bias = abs(bias) if bias is not None else 99.0
    w15 = within_1_5_pct or 0.0
    if mae <= 2.2 and w15 >= 50.0 and abs_bias <= 0.5:
        return "solid"
    if mae <= 2.6 and w15 >= 42.0 and abs_bias <= 0.9:
        return "candidate"
    if mae <= 3.0 and w15 >= 35.0:
        return "promising"
    return "weak"


def _normalize_scores(values: list[tuple[str, float]], *, higher_better: bool) -> dict[str, float]:
    if not values:
        return {}
    nums = [v for _, v in values]
    lo, hi = min(nums), max(nums)
    out: dict[str, float] = {}
    for key, val in values:
        if hi == lo:
            out[key] = 100.0
        elif higher_better:
            out[key] = round(100.0 * (val - lo) / (hi - lo), 1)
        else:
            out[key] = round(100.0 * (hi - val) / (hi - lo), 1)
    return out


def balanced_prediction_score(block: dict[str, Any]) -> float | None:
    pm = block.get("predictive_metrics") or {}
    parts = block.get("score_components") or {}
    if not parts:
        return None
    return _round4(
        0.25 * (parts.get("mae") or 0)
        + 0.15 * (parts.get("rmse") or 0)
        + 0.15 * (parts.get("bias") or 0)
        + 0.20 * (parts.get("within_1_5") or 0)
        + 0.15 * (parts.get("high_recall") or 0)
        + 0.10 * (parts.get("compression") or 0),
    )


def _score_components_for_blocks(blocks: list[dict[str, Any]]) -> None:
    eligible = [b for b in blocks if int((b.get("predictive_metrics") or {}).get("predictions_ok") or 0) > 0]
    if not eligible:
        return

    def collect_pm(getter, higher_better: bool) -> dict[str, float]:
        pairs: list[tuple[str, float]] = []
        for b in eligible:
            pm = b.get("predictive_metrics") or {}
            v = getter(pm)
            if v is not None:
                pairs.append((b["key"], float(v)))
        return _normalize_scores(pairs, higher_better=higher_better)

    def collect_block(getter, higher_better: bool) -> dict[str, float]:
        pairs: list[tuple[str, float]] = []
        for b in eligible:
            v = getter(b)
            if v is not None:
                pairs.append((b["key"], float(v)))
        return _normalize_scores(pairs, higher_better=higher_better)

    mae_s = collect_pm(lambda pm: pm.get("mae"), higher_better=False)
    rmse_s = collect_pm(lambda pm: pm.get("rmse"), higher_better=False)
    bias_s = collect_pm(
        lambda pm: abs(pm.get("bias") or 0) if pm.get("bias") is not None else None,
        higher_better=False,
    )
    w15_s = collect_pm(lambda pm: pm.get("within_1_5_pct"), higher_better=True)
    hr_s = collect_block(
        lambda b: (b.get("bucket_metrics") or {}).get("high_total_recall"),
        higher_better=True,
    )

    def _compression_score(block: dict[str, Any]) -> float | None:
        dist = (block.get("prediction_diagnostics") or {}).get("prediction_distribution") or {}
        ratio = dist.get("compression_ratio")
        if ratio is None:
            return None
        r = float(ratio)
        if r < 0.55:
            return 0.0
        if 0.7 <= r <= 1.0:
            return 100.0
        if r < 0.7:
            return 100.0 * (r - 0.55) / 0.15
        return max(0.0, 100.0 - (r - 1.0) * 50.0)

    comp_pairs = [(b["key"], _compression_score(b)) for b in eligible]
    comp_pairs = [(k, v) for k, v in comp_pairs if v is not None]
    comp_s = _normalize_scores(comp_pairs, higher_better=True) if comp_pairs else {}

    for b in eligible:
        k = b["key"]
        bm = b.get("bucket_metrics") or {}
        b["score_components"] = {
            "mae": mae_s.get(k),
            "rmse": rmse_s.get(k),
            "bias": bias_s.get(k),
            "within_1_5": w15_s.get(k),
            "high_recall": hr_s.get(k),
            "compression": comp_s.get(k),
        }
        b["balanced_prediction_score"] = balanced_prediction_score(b)


def summarize_strategy(
    strategy_key: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    pm = predictive_metrics(rows)
    diag = prediction_diagnostics(rows)
    reg = regression_metrics(rows)
    err_dist = error_distribution(rows)
    cov = coverage_metrics(rows)
    bm = bucket_metrics(rows)
    dist = diag.get("prediction_distribution") or prediction_distribution(rows)
    verdict = compute_strategy_verdict(
        mae=pm.get("mae"),
        within_1_5_pct=pm.get("within_1_5_pct"),
        bias=pm.get("bias"),
        predictions_ok=int(pm.get("predictions_ok") or 0),
        fixtures_total=int(pm.get("fixtures_total") or 0),
    )
    coverage_samples = sorted(
        _scored_rows(rows),
        key=lambda r: float(r.get("abs_error") or 0),
    )[:30]

    return {
        "key": strategy_key,
        "prediction_diagnostics": diag,
        "predictive_metrics": pm,
        "regression_metrics": reg,
        "coverage_metrics": cov,
        "error_distribution": err_dist,
        "bucket_metrics": bm,
        "prediction_distribution": dist,
        "walk_forward_metrics": walk_forward_metrics(rows),
        "verdict": verdict,
        "verdict_label": STRATEGY_VERDICT_LABELS.get(verdict, verdict),
        "coverage_samples": coverage_samples,
        "metrics": {
            "fixtures_total": pm.get("fixtures_total"),
            "predictions_ok": pm.get("predictions_ok"),
            "predictions_failed": pm.get("predictions_failed"),
            "predicted_avg": pm.get("predicted_avg"),
            "actual_avg": pm.get("actual_avg"),
            "mae": pm.get("mae"),
            "rmse": pm.get("rmse"),
            "bias": pm.get("bias"),
            "within_1_0_pct": pm.get("within_1_0_pct"),
            "within_1_5_pct": pm.get("within_1_5_pct"),
            "coverage_win_count": pm.get("coverage_win_count"),
            "coverage_loss_count": pm.get("coverage_loss_count"),
            "coverage_win_rate": pm.get("coverage_win_rate"),
            "predicted_total_avg": diag.get("predicted_total_avg"),
            "actual_total_avg": diag.get("actual_total_avg"),
            "scale_warning": diag.get("scale_warning"),
            "predicted_std": dist.get("predicted_std"),
            "actual_std": dist.get("actual_std"),
            "compression_ratio": dist.get("compression_ratio"),
            "predicted_high_count_over_9": dist.get("predicted_high_count_over_9"),
            "actual_high_count_over_9": dist.get("actual_high_count_over_9"),
            "predicted_low_count_under_6": dist.get("predicted_low_count_under_6"),
            "actual_low_count_under_6": dist.get("actual_low_count_under_6"),
            "high_total_recall": bm.get("high_total_recall"),
            "low_total_recall": bm.get("low_total_recall"),
            "model_too_flat": dist.get("model_too_flat"),
        },
    }


def compute_best_by(strategy_blocks: list[dict[str, Any]], *, fixtures_total: int) -> dict[str, Any]:
    _score_components_for_blocks(strategy_blocks)
    for b in strategy_blocks:
        b["balanced_prediction_score"] = balanced_prediction_score(b)
        b["score_components"] = b.get("score_components") or {}

    min_ok = max(1, int(fixtures_total * 0.95))
    eligible = [
        b
        for b in strategy_blocks
        if int((b.get("predictive_metrics") or {}).get("predictions_ok") or 0) >= min_ok
    ]

    def _best(getter, lower_is_better: bool = True) -> dict[str, Any] | None:
        best_key = None
        best_val = None
        for b in strategy_blocks:
            pm = b.get("predictive_metrics") or {}
            v = getter(pm)
            if v is None:
                continue
            if best_val is None:
                best_val, best_key = v, b["key"]
            elif lower_is_better and v < best_val:
                best_val, best_key = v, b["key"]
            elif not lower_is_better and v > best_val:
                best_val, best_key = v, b["key"]
        return {"strategy": best_key, "value": best_val} if best_key else None

    def _best_abs_bias() -> dict[str, Any] | None:
        best_key = None
        best_val = None
        for b in strategy_blocks:
            pm = b.get("predictive_metrics") or {}
            bias = pm.get("bias")
            if bias is None:
                continue
            ab = abs(float(bias))
            if best_val is None or ab < best_val:
                best_val, best_key = ab, b["key"]
        return {"strategy": best_key, "value": _round4(best_val)} if best_key else None

    recommended = None
    best_score = None
    for b in eligible:
        dist = (b.get("prediction_distribution") or {})
        if dist.get("model_too_flat") and (b.get("balanced_prediction_score") or 0) < 50:
            continue
        sc = b.get("balanced_prediction_score")
        if sc is not None and (best_score is None or sc > best_score):
            best_score = sc
            recommended = b["key"]

    note = None
    if not eligible and strategy_blocks:
        note = "Nessuna strategia con copertura predittiva sufficiente (predictions_ok < 95% fixture)."

    def _best_block(getter, lower_is_better: bool = True) -> dict[str, Any] | None:
        best_key = None
        best_val = None
        for b in strategy_blocks:
            v = getter(b)
            if v is None:
                continue
            if best_val is None:
                best_val, best_key = v, b["key"]
            elif lower_is_better and v < best_val:
                best_val, best_key = v, b["key"]
            elif not lower_is_better and v > best_val:
                best_val, best_key = v, b["key"]
        return {"strategy": best_key, "value": best_val} if best_key else None

    from app.services.backtest.v31_calibration_simulator_predictor import STRATEGY_REGISTRY

    dynamic_families = {"dynamic", "aggressive"}
    strategy_family = {k: v.strategy_family for k, v in STRATEGY_REGISTRY.items()}

    best_dynamic = None
    best_dyn_score = None
    for b in strategy_blocks:
        fam = strategy_family.get(b["key"], "")
        if fam not in dynamic_families:
            continue
        sc = b.get("balanced_prediction_score")
        if sc is not None and (best_dyn_score is None or sc > best_dyn_score):
            best_dyn_score = sc
            best_dynamic = b["key"]

    return {
        "mae": _best(lambda pm: pm.get("mae"), lower_is_better=True),
        "rmse": _best(lambda pm: pm.get("rmse"), lower_is_better=True),
        "bias_near_zero": _best_abs_bias(),
        "within_1_5_pct": _best(lambda pm: pm.get("within_1_5_pct"), lower_is_better=False),
        "coverage_win_rate": _best(lambda pm: pm.get("coverage_win_rate"), lower_is_better=False),
        "best_high_total_detection": _best_block(
            lambda b: (b.get("bucket_metrics") or {}).get("high_total_recall"),
            lower_is_better=False,
        ),
        "best_dynamic_model": {"strategy": best_dynamic, "value": best_dyn_score},
        "balanced_prediction_score": {
            "strategy": recommended,
            "value": best_score,
        },
        "recommended_strategy": recommended,
        "recommendation_note": note,
    }
