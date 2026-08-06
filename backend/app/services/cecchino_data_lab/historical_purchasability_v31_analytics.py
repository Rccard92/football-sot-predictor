"""Analytics V3.1 read-only + positive signal health + decomposition + compare.

Si appoggia ai lean rows del replay persistito (stessa tabella V3).
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.services.cecchino.cecchino_historical_reliability import MIN_SAMPLE
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino_data_lab.historical_purchasability_replay_formula_registry import (
    ANALYTICS_SCHEMA_VERSION_V31,
    V31_MARKET_ORDER,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_go_no_go import (
    evaluate_purchasability_v31_go_no_go,
)

CLASS_LABELS: tuple[str, ...] = (
    "Molto Bassa",
    "Bassa",
    "Media",
    "Alta",
    "Molto Alta",
)
CLASS_ORDER = {c: i for i, c in enumerate(CLASS_LABELS)}
THRESHOLDS: tuple[int, ...] = (20, 40, 50, 60, 70, 80, 90)
BOOTSTRAP_SEED = 42
BOOTSTRAP_ITERS = 500


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        out = float(v)
        if out != out or out in (float("inf"), float("-inf")):
            return None
        return out
    except (TypeError, ValueError):
        return None


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.median(vals))


def _percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def _class_for_score(score: int | None) -> str | None:
    if score is None:
        return None
    if score < 20:
        return "Molto Bassa"
    if score < 40:
        return "Bassa"
    if score < 60:
        return "Media"
    if score < 80:
        return "Alta"
    return "Molto Alta"


def reconstruct_historical_factor(row: dict[str, Any]) -> tuple[float | None, str | None]:
    """historical_factor = raw / (value * quality / 100) se ricostruibile."""
    raw = _f(row.get("raw_score"))
    value = _f(row.get("value_score"))
    quality = _f(row.get("quality_score"))
    if raw is None or value is None or quality is None:
        return None, "missing_components"
    theoretical_raw = value * quality / 100.0
    if theoretical_raw <= 0:
        return None, "theoretical_raw_non_positive"
    return raw / theoretical_raw, None


def is_real_executable(row: dict[str, Any]) -> bool:
    return (
        str(row.get("quote_quality") or "") == "real"
        or bool(row.get("is_real_book_quote"))
    ) and not bool(row.get("is_derived_quote"))


def is_source_unavailable(row: dict[str, Any]) -> bool:
    status = str(row.get("calculation_status") or "")
    reasons = row.get("reason_codes_json") or row.get("reason_codes") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    codes = {str(x) for x in reasons}
    return (
        status in ("source_market_unavailable", "source_not_replayable")
        or "source_market_unavailable" in codes
        or (row.get("source_market_result_id") is None and status != "score")
    )


def score_production_rate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Denominatore: quota reale + input teorici completi; esclude mercati assenti."""
    eligible = []
    scored = 0
    for r in rows:
        if is_source_unavailable(r):
            continue
        if not is_real_executable(r):
            continue
        # input teorici: edge/vantaggio/rating presenti o comunque non missing_inputs
        status = str(r.get("calculation_status") or "")
        if status in ("unavailable", "source_not_replayable"):
            continue
        eligible.append(r)
        if r.get("score") is not None and status in ("score", "available", "partial") or (
            r.get("score") is not None
        ):
            if status not in ("gate_failed", "non_calculable", "error"):
                scored += 1
            elif r.get("score") is not None:
                scored += 1
    # recount scored properly
    scored = sum(
        1
        for r in eligible
        if r.get("score") is not None
        and str(r.get("calculation_status") or "") not in ("gate_failed", "non_calculable", "error")
    )
    n = len(eligible)
    return {
        "scored": scored,
        "eligible_real_complete": n,
        "score_production_rate": (scored / n) if n else None,
    }


def compute_positive_signal_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    real_scored = [
        r
        for r in rows
        if is_real_executable(r)
        and r.get("score") is not None
        and str(r.get("calculation_status") or "") not in ("gate_failed", "non_calculable", "error")
    ]
    scores = [int(r["score"]) for r in real_scored]
    high = [s for s in scores if s >= 60]
    very_high = [s for s in scores if s >= 80]
    media_or_higher = [s for s in scores if s >= 40]

    markets_high = sorted(
        {
            str(r.get("market_key"))
            for r in real_scored
            if int(r["score"]) >= 60 and r.get("market_key")
        }
    )
    comps_high = sorted(
        {
            str(r.get("competition_name"))
            for r in real_scored
            if int(r["score"]) >= 60 and r.get("competition_name")
        }
    )
    dates_high = sorted(
        {
            str(r.get("kickoff_at"))[:10]
            for r in real_scored
            if int(r["score"]) >= 60 and r.get("kickoff_at")
        }
    )

    # consecutive windows without high: group by month
    by_month: dict[str, bool] = {}
    for r in real_scored:
        ko = str(r.get("kickoff_at") or "")[:7]
        if not ko:
            continue
        by_month.setdefault(ko, False)
        if int(r["score"]) >= 60:
            by_month[ko] = True
    months = sorted(by_month.keys())
    max_streak = 0
    cur = 0
    for m in months:
        if by_month[m]:
            cur = 0
        else:
            cur += 1
            max_streak = max(max_streak, cur)

    n = len(scores)
    lowish = sum(1 for s in scores if s < 40)
    all_collapse = False
    if n >= MIN_SAMPLE:
        if len(high) == 0:
            all_collapse = True
        elif lowish / n >= 0.95 and len(high) == 0:
            all_collapse = True

    positive_tail = len(high) > 0 and (max(scores) if scores else 0) >= 60
    positive_tail_sample_ok = len(high) >= MIN_SAMPLE

    reason_codes: list[str] = []
    if positive_tail:
        reason_codes.append("high_scores_observed")
    if len(very_high) > 0:
        reason_codes.append("very_high_scores_observed")
    if all_collapse:
        reason_codes.append("distribution_collapsed_low")
    if not positive_tail_sample_ok:
        reason_codes.append("high_sample_below_min_sample")

    return {
        "scored_real_count": n,
        "media_or_higher_count": len(media_or_higher),
        "high_count": len(high),
        "very_high_count": len(very_high),
        "high_share": (len(high) / n) if n else None,
        "very_high_share": (len(very_high) / n) if n else None,
        "max_score": max(scores) if scores else None,
        "p90_score": _percentile([float(s) for s in scores], 90),
        "p95_score": _percentile([float(s) for s in scores], 95),
        "markets_with_high_signals": markets_high,
        "competitions_with_high_signals": comps_high,
        "high_signal_dates": dates_high[:50],
        "consecutive_windows_without_high_signal": max_streak,
        "all_negative_collapse": all_collapse,
        "positive_tail_detected": positive_tail,
        "positive_tail_sample_sufficient": positive_tail_sample_ok,
        "positive_tail_reason_codes": reason_codes,
    }


def compute_score_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r.get("score") is not None]
    real_scored = [r for r in scored if is_real_executable(r)]
    scores = [int(r["score"]) for r in scored]
    by_class: dict[str, dict[str, Any]] = {}
    for label in CLASS_LABELS:
        subset = [r for r in scored if (r.get("score_class") or _class_for_score(int(r["score"]))) == label]
        vals = [int(r["score"]) for r in subset]
        real_n = sum(1 for r in subset if is_real_executable(r))
        factors = []
        for r in subset:
            hf, _ = reconstruct_historical_factor(r)
            if hf is not None:
                factors.append(hf)
        by_class[label] = {
            "count": len(subset),
            "share_of_scored": (len(subset) / len(scored)) if scored else None,
            "share_of_real_executable": (real_n / len(real_scored)) if real_scored else None,
            "mean_score": (sum(vals) / len(vals)) if vals else None,
            "median_score": _median([float(v) for v in vals]),
            "min_score": min(vals) if vals else None,
            "max_score": max(vals) if vals else None,
            "mean_value_score": _mean_field(subset, "value_score"),
            "mean_quality_score": _mean_field(subset, "quality_score"),
            "mean_historical_factor": (sum(factors) / len(factors)) if factors else None,
            "mean_total_penalty": _mean_field(subset, "total_penalty"),
            "mean_quota_book": _mean_field(subset, "quota_book"),
            "mean_edge_pct": _mean_field(subset, "edge_pct"),
            "mean_prob_cecchino": _mean_field(subset, "prob_cecchino"),
        }
    float_scores = [float(s) for s in scores]
    return {
        "scored_count": len(scored),
        "percentiles": {
            "p10": _percentile(float_scores, 10),
            "p25": _percentile(float_scores, 25),
            "p50": _percentile(float_scores, 50),
            "p75": _percentile(float_scores, 75),
            "p90": _percentile(float_scores, 90),
            "p95": _percentile(float_scores, 95),
        },
        "by_class": by_class,
        "mean_score": (sum(scores) / len(scores)) if scores else None,
        "median_score": _median(float_scores),
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
    }


def _mean_field(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [_f(r.get(key)) for r in rows]
    vals2 = [v for v in vals if v is not None]
    if not vals2:
        return None
    return sum(vals2) / len(vals2)


def _perf_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Performance solo su quote reali con outcome."""
    real = [
        r
        for r in rows
        if is_real_executable(r) and r.get("won") is not None and r.get("profit_1u_real") is not None
    ]
    n = len(real)
    if n == 0:
        return {
            "selections": 0,
            "wins": 0,
            "losses": 0,
            "voids": 0,
            "win_rate": None,
            "mean_odds": None,
            "break_even_rate": None,
            "realized_margin": None,
            "profit_1u": None,
            "roi": None,
            "profit_factor": None,
            "longest_losing_streak": 0,
            "max_drawdown": None,
            "profit_volatility": None,
            "insufficient_sample": True,
        }
    wins = sum(1 for r in real if r.get("won") is True)
    losses = sum(1 for r in real if r.get("won") is False)
    voids = 0
    profits = [float(r["profit_1u_real"]) for r in real]
    odds = [_f(r.get("quota_book")) for r in real]
    odds_ok = [o for o in odds if o is not None and o > 1]
    be = (sum(1.0 / o for o in odds_ok) / len(odds_ok)) if odds_ok else None
    win_rate = wins / (wins + losses) if (wins + losses) else None
    total_profit = sum(profits)
    roi = total_profit / n
    margin = (win_rate - be) if (win_rate is not None and be is not None) else None
    gross_win = sum(p for p in profits if p > 0)
    gross_loss = abs(sum(p for p in profits if p < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else None

    streak = max_streak = 0
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in sorted(real, key=lambda x: str(x.get("kickoff_at") or "")):
        p = float(r["profit_1u_real"])
        equity += p
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        if r.get("won") is False:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    vol = statistics.pstdev(profits) if len(profits) > 1 else 0.0
    ci = bootstrap_roi_ci(profits)
    return {
        "selections": n,
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "win_rate": win_rate,
        "mean_odds": (sum(odds_ok) / len(odds_ok)) if odds_ok else None,
        "break_even_rate": be,
        "realized_margin": margin,
        "profit_1u": total_profit,
        "roi": roi,
        "profit_factor": pf,
        "longest_losing_streak": max_streak,
        "max_drawdown": max_dd,
        "profit_volatility": vol,
        "insufficient_sample": n < MIN_SAMPLE,
        "confidence": ci,
    }


def bootstrap_roi_ci(
    profits: list[float],
    *,
    seed: int = BOOTSTRAP_SEED,
    iters: int = BOOTSTRAP_ITERS,
) -> dict[str, Any]:
    n = len(profits)
    if n == 0:
        return {
            "roi_point": None,
            "roi_ci_low": None,
            "roi_ci_high": None,
            "win_rate_point": None,
            "n": 0,
            "insufficient_sample": True,
        }
    point = sum(profits) / n
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(iters):
        draw = [profits[rng.randrange(n)] for _ in range(n)]
        samples.append(sum(draw) / n)
    samples.sort()
    lo = samples[int(0.025 * (iters - 1))]
    hi = samples[int(0.975 * (iters - 1))]
    # win-rate approx from sign
    return {
        "roi_point": point,
        "roi_ci_low": lo,
        "roi_ci_high": hi,
        "n": n,
        "insufficient_sample": n < MIN_SAMPLE,
        "seed": seed,
        "iters": iters,
    }


def compute_threshold_performance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    scored_real = [
        r
        for r in rows
        if is_real_executable(r) and r.get("score") is not None
    ]
    for thr in THRESHOLDS:
        subset = [r for r in scored_real if int(r["score"]) >= thr]
        block = _perf_block(subset)
        block["threshold"] = thr
        out[f"score_ge_{thr}"] = block
    # top percentiles
    if scored_real:
        ordered = sorted(scored_real, key=lambda r: int(r["score"]), reverse=True)
        n = len(ordered)
        for pct, key in ((5, "top_5pct"), (10, "top_10pct"), (20, "top_20pct")):
            k = max(1, int(math.ceil(n * pct / 100.0)))
            out[key] = _perf_block(ordered[:k])
            out[key]["n_selected"] = k
    return out


def compute_ordering_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, dict[str, Any]] = {}
    for label in CLASS_LABELS:
        subset = [
            r
            for r in rows
            if is_real_executable(r)
            and r.get("score") is not None
            and (r.get("score_class") or _class_for_score(int(r["score"]))) == label
        ]
        by_class[label] = _perf_block(subset)

    rois = []
    for label in CLASS_LABELS:
        b = by_class[label]
        if b.get("selections", 0) >= MIN_SAMPLE and b.get("roi") is not None:
            rois.append((CLASS_ORDER[label], float(b["roi"]), label))

    violations = 0
    severe = 0
    for i in range(len(rois) - 1):
        if rois[i][1] > rois[i + 1][1] + 1e-9:
            violations += 1
            # grave se Alta/Molto Alta peggio di basse
            if rois[i][2] in ("Molto Bassa", "Bassa") and rois[i + 1][2] in (
                "Alta",
                "Molto Alta",
            ):
                severe += 1

    # Spearman band index vs ROI
    spearman = None
    if len(rois) >= 3:
        xs = [r[0] for r in rois]
        ys = [r[1] for r in rois]
        spearman = _spearman(xs, ys)

    high_rows = [
        r
        for r in rows
        if is_real_executable(r) and r.get("score") is not None and int(r["score"]) >= 60
    ]
    all_scored = [r for r in rows if is_real_executable(r) and r.get("score") is not None]
    high_perf = _perf_block(high_rows)
    all_perf = _perf_block(all_scored)
    high_vs_all = None
    if high_perf.get("roi") is not None and all_perf.get("roi") is not None:
        high_vs_all = float(high_perf["roi"]) - float(all_perf["roi"])

    vh_rows = [r for r in high_rows if int(r["score"]) >= 80]
    vh_perf = _perf_block(vh_rows)
    vh_vs_all = None
    if vh_perf.get("roi") is not None and all_perf.get("roi") is not None:
        vh_vs_all = float(vh_perf["roi"]) - float(all_perf["roi"])

    low_rows = [
        r
        for r in all_scored
        if (r.get("score_class") or _class_for_score(int(r["score"])))
        in ("Molto Bassa", "Bassa")
    ]
    high_plus = [
        r
        for r in all_scored
        if (r.get("score_class") or _class_for_score(int(r["score"])))
        in ("Alta", "Molto Alta")
    ]
    low_p = _perf_block(low_rows)
    high_p = _perf_block(high_plus)
    high_vs_low = None
    if high_p.get("roi") is not None and low_p.get("roi") is not None:
        high_vs_low = float(high_p["roi"]) - float(low_p["roi"])

    return {
        "by_class": by_class,
        "monotonicity_violations": violations,
        "severe_monotonicity_violations": severe,
        "spearman_band_roi": spearman,
        "high_vs_all_uplift": high_vs_all,
        "very_high_vs_all_uplift": vh_vs_all,
        "high_plus_very_high_vs_low_roi_delta": high_vs_low,
        "baseline_scored_real": all_perf,
    }


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    rx = _ranks(xs)
    ry = _ranks(ys)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def _ranks(vals: list[float]) -> list[float]:
    ordered = sorted((v, i) for i, v in enumerate(vals))
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][0] == ordered[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[ordered[k][1]] = avg
        i = j + 1
    return ranks


def compute_decomposition(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Perdite per componente di severità."""
    scored = [r for r in rows if r.get("score") is not None]
    losses = {
        "score_loss_probability": [],
        "score_loss_opposite": [],
        "score_loss_divergence": [],
        "score_loss_family": [],
        "score_loss_historical": [],
    }
    blocked_alta = defaultdict(int)
    blocked_molto = defaultdict(int)
    theo_ge80_to_below60 = 0
    theo_ge80 = 0
    theo60_to_below40 = 0
    theo60 = 0
    suppressed_good = 0
    correctly_suppressed = 0

    for r in scored:
        value = _f(r.get("value_score")) or 0.0
        quality = _f(r.get("quality_score")) or 0.0
        theo_raw = value * quality / 100.0
        hf, _ = reconstruct_historical_factor(r)
        final = _f(r.get("score")) or 0.0
        p_prob = _f(r.get("probability_risk_penalty")) or 0.0
        p_opp = _f(r.get("opposite_market_pressure_penalty")) or 0.0
        p_div = _f(r.get("extreme_divergence_penalty")) or 0.0
        p_fam = _f(r.get("family_ambiguity_penalty")) or 0.0
        losses["score_loss_probability"].append(p_prob)
        losses["score_loss_opposite"].append(p_opp)
        losses["score_loss_divergence"].append(p_div)
        losses["score_loss_family"].append(p_fam)
        hist_loss = None
        if hf is not None:
            hist_loss = theo_raw * (1.0 - hf)
            losses["score_loss_historical"].append(hist_loss)

        if theo_raw >= 80:
            theo_ge80 += 1
            if final < 60:
                theo_ge80_to_below60 += 1
        if theo_raw >= 60:
            theo60 += 1
            if final < 40:
                theo60_to_below40 += 1

        # component that most blocks Alta/Molto Alta
        if theo_raw >= 60 and final < 60:
            comps = {
                "probability_risk": p_prob,
                "opposite_pressure": p_opp,
                "divergence": p_div,
                "family_ambiguity": p_fam,
                "historical_factor": hist_loss or 0.0,
            }
            top = max(comps, key=comps.get)
            blocked_alta[top] += 1
        if theo_raw >= 80 and final < 80:
            comps = {
                "probability_risk": p_prob,
                "opposite_pressure": p_opp,
                "divergence": p_div,
                "family_ambiguity": p_fam,
                "historical_factor": hist_loss or 0.0,
            }
            top = max(comps, key=comps.get)
            blocked_molto[top] += 1

        profit = _f(r.get("profit_1u_real"))
        if theo_raw >= 60 and hf is not None and hf < 0.7 and final < 40:
            if profit is not None and profit > 0:
                suppressed_good += 1
            elif profit is not None and profit < 0:
                correctly_suppressed += 1

    def _avg(xs: list[float]) -> float | None:
        return (sum(xs) / len(xs)) if xs else None

    return {
        "mean_losses": {k: _avg(v) for k, v in losses.items()},
        "component_blocking_alta_most_often": (
            max(blocked_alta, key=blocked_alta.get) if blocked_alta else None
        ),
        "component_blocking_molto_alta_most_often": (
            max(blocked_molto, key=blocked_molto.get) if blocked_molto else None
        ),
        "blocked_alta_counts": dict(blocked_alta),
        "blocked_molto_alta_counts": dict(blocked_molto),
        "pct_theo_ge80_dropped_below60": (
            theo_ge80_to_below60 / theo_ge80 if theo_ge80 else None
        ),
        "pct_theo_ge60_to_score_below40": (
            theo60_to_below40 / theo60 if theo60 else None
        ),
        "high_theo_positive_roi_suppressed": suppressed_good,
        "high_theo_negative_roi_correctly_suppressed": correctly_suppressed,
    }


def compute_matched_v3_v31_comparison(
    v31_rows: list[dict[str, Any]],
    v3_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Confronto solo righe confrontabili (fixture, mercato, quota reale, score)."""
    def key(r: dict[str, Any]) -> tuple:
        return (
            int(r.get("source_snapshot_id") or 0),
            str(r.get("market_key") or ""),
        )

    v3_map = {key(r): r for r in v3_rows if r.get("score") is not None and is_real_executable(r)}
    matched = []
    for r in v31_rows:
        if r.get("score") is None or not is_real_executable(r):
            continue
        k = key(r)
        if k in v3_map:
            matched.append((r, v3_map[k]))

    n = len(matched)
    if n == 0:
        return {"sample_matched": 0, "insufficient_sample": True}

    v31_only = [a for a, _ in matched]
    v3_only = [b for _, b in matched]
    p31 = _perf_block(v31_only)
    p3 = _perf_block(v3_only)

    # equal coverage: top N by score
    def top_n_perf(rows: list[dict[str, Any]], n_sel: int) -> dict[str, Any]:
        ordered = sorted(rows, key=lambda r: int(r["score"]), reverse=True)
        return _perf_block(ordered[:n_sel])

    equal = {}
    for pct, label in ((5, "top_5pct"), (10, "top_10pct"), (20, "top_20pct")):
        k = max(1, int(math.ceil(n * pct / 100.0)))
        a = top_n_perf(v31_only, k)
        b = top_n_perf(v3_only, k)
        equal[label] = {
            "n": k,
            "v31": a,
            "v3": b,
            "roi_delta": (
                (a.get("roi") - b.get("roi"))
                if a.get("roi") is not None and b.get("roi") is not None
                else None
            ),
        }

    n60 = sum(1 for r in v31_only if int(r["score"]) >= 60)
    n80 = sum(1 for r in v31_only if int(r["score"]) >= 80)
    if n60:
        equal["n_score_ge_60"] = {
            "n": n60,
            "v31": top_n_perf(v31_only, n60),
            "v3": top_n_perf(v3_only, n60),
        }
        equal["n_score_ge_60"]["roi_delta"] = (
            (equal["n_score_ge_60"]["v31"].get("roi") or 0)
            - (equal["n_score_ge_60"]["v3"].get("roi") or 0)
        )
    if n80:
        equal["n_score_ge_80"] = {
            "n": n80,
            "v31": top_n_perf(v31_only, n80),
            "v3": top_n_perf(v3_only, n80),
        }

    # overlap high picks
    set31 = {key(r) for r in v31_only if int(r["score"]) >= 60}
    set3 = {key(r) for r in v3_only if int(r["score"]) >= 60}
    overlap = len(set31 & set3)

    roi_delta = None
    if p31.get("roi") is not None and p3.get("roi") is not None:
        roi_delta = float(p31["roi"]) - float(p3["roi"])
    profit_delta = None
    if p31.get("profit_1u") is not None and p3.get("profit_1u") is not None:
        profit_delta = float(p31["profit_1u"]) - float(p3["profit_1u"])
    dd_delta = None
    if p31.get("max_drawdown") is not None and p3.get("max_drawdown") is not None:
        dd_delta = float(p31["max_drawdown"]) - float(p3["max_drawdown"])

    return {
        "sample_matched": n,
        "insufficient_sample": n < MIN_SAMPLE,
        "v31": {
            "mean_score": _mean_field(v31_only, "score"),
            "performance": p31,
            "score_ge_60": n60,
            "score_ge_80": n80,
        },
        "v3": {
            "mean_score": _mean_field(v3_only, "score"),
            "performance": p3,
            "score_ge_60": sum(1 for r in v3_only if int(r["score"]) >= 60),
            "score_ge_80": sum(1 for r in v3_only if int(r["score"]) >= 80),
        },
        "equal_coverage": equal,
        "incremental_profit_v31_vs_v3": profit_delta,
        "roi_delta": roi_delta,
        "drawdown_delta": dd_delta,
        "overlap_high": overlap,
        "picks_only_v31": len(set31 - set3),
        "picks_only_v3": len(set3 - set31),
        "equal_coverage_roi_delta": (equal.get("top_10pct") or {}).get("roi_delta"),
    }


def compute_coverage_analytics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    scored = sum(1 for r in rows if r.get("score") is not None)
    gate_failed = sum(
        1
        for r in rows
        if str(r.get("calculation_status") or "") == "gate_failed"
        or (str(r.get("gate_status") or "") not in ("", "passed", "None") and r.get("score") is None)
    )
    non_calc = sum(
        1 for r in rows if str(r.get("calculation_status") or "") == "non_calculable"
    )
    errors = sum(1 for r in rows if str(r.get("calculation_status") or "") == "error")
    source_unavail = sum(1 for r in rows if is_source_unavailable(r))
    real_q = sum(1 for r in rows if is_real_executable(r))
    derived_q = sum(1 for r in rows if bool(r.get("is_derived_quote")))
    spr = score_production_rate(rows)

    by_market = {}
    for mk in V31_MARKET_ORDER:
        subset = [r for r in rows if str(r.get("market_key")) == mk]
        by_market[mk] = {
            "rows": len(subset),
            "scored": sum(1 for r in subset if r.get("score") is not None),
            "source_unavailable": sum(1 for r in subset if is_source_unavailable(r)),
            "real": sum(1 for r in subset if is_real_executable(r)),
            "derived": sum(1 for r in subset if bool(r.get("is_derived_quote"))),
        }

    reason_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        for code in r.get("reason_codes_json") or r.get("reason_codes") or []:
            reason_counts[str(code)] += 1

    return {
        "evaluations_total": total,
        "scored": scored,
        "gate_failed": gate_failed,
        "non_calculable": non_calc,
        "errors": errors,
        "source_market_unavailable": source_unavail,
        "real_quotes": real_q,
        "derived_quotes": derived_q,
        "by_market": by_market,
        "markets_supported_count": len(PANEL_MARKET_KEYS),
        "reason_code_counts": dict(reason_counts),
        **spr,
    }


def assign_temporal_split(
    rows: list[dict[str, Any]],
    *,
    warm_pct: float = 0.60,
    mid_pct: float = 0.20,
) -> dict[str, Any]:
    """Split cronologico 60/20/20; stesso kickoff nello stesso blocco."""
    # unique kickoffs ordered
    kickoffs = sorted(
        {
            str(r.get("kickoff_at"))
            for r in rows
            if r.get("kickoff_at") is not None
        }
    )
    n = len(kickoffs)
    if n == 0:
        return {
            "split": "empty",
            "warm_up": [],
            "validation_mid": [],
            "pseudo_holdout": [],
            "has_independent_holdout": False,
        }
    i_warm = int(n * warm_pct)
    i_mid = int(n * (warm_pct + mid_pct))
    # adjust so we don't split same - already unique keys
    warm_set = set(kickoffs[:i_warm])
    mid_set = set(kickoffs[i_warm:i_mid])
    hold_set = set(kickoffs[i_mid:])

    def flag(r: dict[str, Any]) -> str:
        k = str(r.get("kickoff_at"))
        if k in warm_set:
            return "warm_up"
        if k in mid_set:
            return "validation_mid"
        return "pseudo_holdout"

    for r in rows:
        r["_temporal_split"] = flag(r)

    return {
        "split": "chronological_60_20_20",
        "kickoffs_total": n,
        "warm_up_kickoffs": len(warm_set),
        "validation_mid_kickoffs": len(mid_set),
        "pseudo_holdout_kickoffs": len(hold_set),
        "has_independent_holdout": False,
        "note": "Holdout indipendente assente: pseudo-holdout sulla stessa stagione.",
    }


def build_v31_analytics_payload(
    rows: list[dict[str, Any]],
    *,
    replay_meta: dict[str, Any] | None = None,
    v3_rows: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Payload analytics completo V3.1 + decisione GO/NO-GO."""
    meta = dict(replay_meta or {})
    ctx = dict(context or {})
    split_info = assign_temporal_split(rows)
    holdout_rows = [r for r in rows if r.get("_temporal_split") == "pseudo_holdout"]

    coverage = compute_coverage_analytics(rows)
    distribution = compute_score_distribution(rows)
    psh = compute_positive_signal_health(rows)
    psh_holdout = compute_positive_signal_health(holdout_rows)
    psh["holdout_high_count"] = psh_holdout.get("high_count")
    thresholds = compute_threshold_performance(rows)
    ordering = compute_ordering_diagnostics(rows)
    decomposition = compute_decomposition(rows)
    comparison = compute_matched_v3_v31_comparison(rows, v3_rows or [])

    derived_diag = [
        r
        for r in rows
        if bool(r.get("is_derived_quote"))
    ]
    derived_section = {
        "count": len(derived_diag),
        "note": "Solo diagnostica; esclusi da ROI reale e decisione GO/NO-GO",
        "non_calculable_derived": sum(
            1
            for r in derived_diag
            if str(r.get("calculation_status") or "") == "non_calculable"
        ),
    }

    analytics = {
        "schema_version": ANALYTICS_SCHEMA_VERSION_V31,
        "generated_at": _utcnow_iso(),
        "replay": meta,
        "temporal_split": split_info,
        "coverage": coverage,
        "score_distribution": distribution,
        "positive_signal_health": psh,
        "performance_real": thresholds,
        "thresholds": thresholds,
        "top_percentiles": {
            k: thresholds[k]
            for k in ("top_5pct", "top_10pct", "top_20pct")
            if k in thresholds
        },
        "ordering": ordering,
        "baseline_scored_real": ordering.get("baseline_scored_real"),
        "decomposition": decomposition,
        "v3_comparison": comparison,
        "derived_quotes_diagnostic": derived_section,
        "markets": coverage.get("by_market"),
    }

    ctx.setdefault("has_independent_holdout", False)
    ctx.setdefault("positive_signal_health", psh)
    ctx.setdefault("holdout_high_count", psh_holdout.get("high_count"))
    ctx.setdefault("score_production_rate", coverage.get("score_production_rate"))
    ctx.setdefault("scored_real_count", psh.get("scored_real_count"))
    ctx.setdefault("v3_comparison", comparison)
    ctx.setdefault("ordering", ordering)
    ctx.setdefault(
        "threshold_60",
        thresholds.get("score_ge_60"),
    )
    ctx.setdefault("threshold_80", thresholds.get("score_ge_80"))
    ctx.setdefault("top_percentiles", analytics["top_percentiles"])
    ctx.setdefault(
        "baseline_roi",
        (ordering.get("baseline_scored_real") or {}).get("roi"),
    )
    ctx.setdefault("high_vs_all_uplift", ordering.get("high_vs_all_uplift"))

    decision = evaluate_purchasability_v31_go_no_go(analytics, context=ctx)
    analytics["decision"] = decision
    return analytics
