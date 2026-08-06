"""Valutatore GO/NO-GO versionato per Acquistabilità V3.1.

purchasability_v31_go_no_go_v1 — nessuna taratura, nessun giudizio nascosto.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.cecchino.cecchino_historical_reliability import MIN_SAMPLE

GO_NO_GO_VERSION = "purchasability_v31_go_no_go_v1"

DECISION_GO_FINAL = "GO_FINAL"
DECISION_GO_PROVISIONAL = "GO_PROVISIONAL"
DECISION_NO_GO_OVER_SEVERE = "NO_GO_OVER_SEVERE"
DECISION_NO_GO_PERFORMANCE = "NO_GO_PERFORMANCE"
DECISION_NO_GO_DATA = "NO_GO_DATA"
DECISION_NO_GO_TECHNICAL = "NO_GO_TECHNICAL"

ALLOWED_DECISIONS = frozenset(
    {
        DECISION_GO_FINAL,
        DECISION_GO_PROVISIONAL,
        DECISION_NO_GO_OVER_SEVERE,
        DECISION_NO_GO_PERFORMANCE,
        DECISION_NO_GO_DATA,
        DECISION_NO_GO_TECHNICAL,
    }
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def evaluate_purchasability_v31_go_no_go(
    analytics: dict[str, Any] | None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Valuta decisione GO/NO-GO da analytics + contesto anti-leakage."""
    analytics = analytics or {}
    ctx = dict(context or {})

    passed: list[str] = []
    failed: list[str] = []
    insufficient: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: dict[str, Any] = {}

    # --- A. Gate tecnici ---
    leakage = bool(ctx.get("leakage_detected"))
    future_data = bool(ctx.get("future_data_used"))
    integrity_invalid = bool(ctx.get("integrity_invalid"))
    unclassified = int(ctx.get("unclassified_count") or 0)
    recon_ok = ctx.get("reconciliation_ok")
    if recon_ok is None:
        recon = analytics.get("reconciliation") or {}
        recon_ok = bool(recon.get("ok", recon.get("delta", 1) == 0))
    ambiguous_join = int(ctx.get("ambiguous_join_count") or 0)
    duplicate_results = int(ctx.get("duplicate_results_count") or 0)
    formula_mismatch = bool(ctx.get("formula_version_mismatch"))
    v3_modified = bool(ctx.get("v3_modified"))
    mixed_quotes = bool(ctx.get("real_synthetic_mixed"))

    technical_fail = False
    if leakage:
        failed.append("no_leakage")
        blockers.append("leakage_detected")
        technical_fail = True
    else:
        passed.append("no_leakage")
    if future_data:
        failed.append("no_future_data")
        blockers.append("future_data_used")
        technical_fail = True
    else:
        passed.append("no_future_data")
    if integrity_invalid:
        failed.append("integrity_valid")
        blockers.append("hash_freeze_invalid")
        technical_fail = True
    else:
        passed.append("integrity_valid")
    if unclassified != 0:
        failed.append("unclassified_zero")
        blockers.append(f"unclassified={unclassified}")
        technical_fail = True
    else:
        passed.append("unclassified_zero")
    if not recon_ok:
        failed.append("reconciliation_ok")
        blockers.append("reconciliation_delta")
        technical_fail = True
    else:
        passed.append("reconciliation_ok")
    if ambiguous_join != 0:
        failed.append("no_ambiguous_join")
        blockers.append("ambiguous_join")
        technical_fail = True
    else:
        passed.append("no_ambiguous_join")
    if duplicate_results != 0:
        failed.append("no_duplicate_results")
        blockers.append("duplicate_results")
        technical_fail = True
    else:
        passed.append("no_duplicate_results")
    if formula_mismatch:
        failed.append("formula_version_match")
        blockers.append("formula_version_mismatch")
        technical_fail = True
    else:
        passed.append("formula_version_match")
    if v3_modified:
        failed.append("v3_unmodified")
        blockers.append("v3_modified")
        technical_fail = True
    else:
        passed.append("v3_unmodified")
    if mixed_quotes:
        failed.append("real_synthetic_separated")
        blockers.append("real_synthetic_mixed")
        technical_fail = True
    else:
        passed.append("real_synthetic_separated")

    if technical_fail:
        return _pack(
            DECISION_NO_GO_TECHNICAL,
            passed,
            failed,
            insufficient,
            evidence,
            blockers,
            warnings,
            "Correggere leakage/integrità/riconciliazione prima di rivalutare.",
            ctx,
        )

    # --- B. Copertura / dati ---
    psh = analytics.get("positive_signal_health") or ctx.get("positive_signal_health") or {}
    coverage = analytics.get("coverage") or {}
    score_prod = _f(coverage.get("score_production_rate"), ctx.get("score_production_rate"))
    scored_real = int(
        psh.get("scored_real_count")
        or coverage.get("scored_real_count")
        or ctx.get("scored_real_count")
        or 0
    )
    evidence["scored_real_count"] = scored_real
    evidence["score_production_rate"] = score_prod

    majority_non_calc_bug = bool(ctx.get("majority_non_calculable_bug"))
    no_market_sample = bool(ctx.get("no_market_sufficient_sample"))
    if no_market_sample is False and scored_real < MIN_SAMPLE:
        no_market_sample = True

    positive_tail_sample_ok = bool(psh.get("positive_tail_sample_sufficient"))
    if "positive_tail_sample_sufficient" not in psh and "positive_tail_sample_sufficient" not in ctx:
        high_count = int(psh.get("high_count") or 0)
        positive_tail_sample_ok = high_count >= MIN_SAMPLE

    data_fail = False
    if majority_non_calc_bug:
        failed.append("score_production_healthy")
        blockers.append("majority_non_calculable_bug")
        data_fail = True
    elif score_prod is not None and score_prod < 0.05 and not ctx.get("low_production_data_reason"):
        failed.append("score_production_healthy")
        blockers.append("score_production_rate_insufficient")
        data_fail = True
    else:
        passed.append("score_production_healthy")

    if no_market_sample:
        failed.append("sufficient_market_sample")
        blockers.append("no_market_sufficient_sample")
        data_fail = True
    else:
        passed.append("sufficient_market_sample")

    if not positive_tail_sample_ok:
        # Non è sempre NO_GO_DATA: può diventare OVER_SEVERE o PROVISIONAL
        insufficient.append("positive_tail_sample_sufficient")
    else:
        passed.append("positive_tail_sample_sufficient")

    if data_fail and scored_real < MIN_SAMPLE:
        return _pack(
            DECISION_NO_GO_DATA,
            passed,
            failed,
            insufficient,
            evidence,
            blockers,
            warnings,
            "Ampliare copertura storica o completare mercati mancanti.",
            ctx,
        )

    # --- C. Coda positiva ---
    all_collapse = bool(psh.get("all_negative_collapse"))
    positive_tail = bool(psh.get("positive_tail_detected"))
    high_count = int(psh.get("high_count") or 0)
    very_high_count = int(psh.get("very_high_count") or 0)
    max_score = _f(psh.get("max_score"))
    evidence.update(
        {
            "high_count": high_count,
            "very_high_count": very_high_count,
            "max_score": max_score,
            "all_negative_collapse": all_collapse,
            "positive_tail_detected": positive_tail,
        }
    )

    if all_collapse or (not positive_tail and scored_real >= MIN_SAMPLE):
        failed.append("positive_tail_present")
        blockers.append("all_negative_collapse" if all_collapse else "positive_tail_absent")
        return _pack(
            DECISION_NO_GO_OVER_SEVERE,
            passed,
            failed,
            insufficient,
            evidence,
            blockers,
            warnings,
            "Formula troppo severa: analizzare decomposition (HR/penalità/gate) in Step successivo.",
            ctx,
        )
    if positive_tail:
        passed.append("positive_tail_present")
    else:
        insufficient.append("positive_tail_present")

    holdout_high = int(ctx.get("holdout_high_count") or psh.get("holdout_high_count") or high_count)
    if holdout_high < MIN_SAMPLE:
        insufficient.append("holdout_high_min_sample")
    else:
        passed.append("holdout_high_min_sample")

    has_very_high = very_high_count >= 1 and (max_score is not None and max_score >= 80)
    if has_very_high:
        passed.append("very_high_present")
    else:
        insufficient.append("very_high_present")
        warnings.append("Classe Molto Alta assente o max_score < 80")

    molto_alta_min = very_high_count >= MIN_SAMPLE
    if molto_alta_min:
        passed.append("molto_alta_min_sample")
    else:
        insufficient.append("molto_alta_min_sample")

    # --- D. Performance ---
    perf = analytics.get("performance_real") or analytics.get("thresholds") or {}
    thr60 = _threshold_block(perf, 60) or ctx.get("threshold_60") or {}
    thr80 = _threshold_block(perf, 80) or ctx.get("threshold_80") or {}
    roi60 = _f(thr60.get("roi"))
    margin60 = _f(thr60.get("realized_margin"))
    top10 = analytics.get("top_percentiles") or ctx.get("top_percentiles") or {}
    top10_roi = _f((top10.get("top_10pct") or {}).get("roi") if isinstance(top10.get("top_10pct"), dict) else top10.get("top_10_roi"))
    baseline_roi = _f(
        (analytics.get("baseline_scored_real") or {}).get("roi")
        or ctx.get("baseline_roi")
    )
    high_vs_all = _f(
        (analytics.get("ordering") or {}).get("high_vs_all_uplift")
        or ctx.get("high_vs_all_uplift")
    )
    equal_cov = analytics.get("v3_comparison") or ctx.get("v3_comparison") or {}
    equal_roi_delta = _f(equal_cov.get("roi_delta") or equal_cov.get("equal_coverage_roi_delta"))
    drawdown_delta = _f(equal_cov.get("drawdown_delta"))

    perf_fail = False
    if roi60 is not None and roi60 <= 0 and int(thr60.get("selections") or 0) >= MIN_SAMPLE:
        failed.append("roi_ge60_positive")
        perf_fail = True
    elif roi60 is None or int(thr60.get("selections") or 0) < MIN_SAMPLE:
        insufficient.append("roi_ge60_positive")
    else:
        passed.append("roi_ge60_positive")

    if margin60 is not None and margin60 <= 0 and int(thr60.get("selections") or 0) >= MIN_SAMPLE:
        failed.append("margin_ge60_positive")
        perf_fail = True
    elif margin60 is None or int(thr60.get("selections") or 0) < MIN_SAMPLE:
        insufficient.append("margin_ge60_positive")
    else:
        passed.append("margin_ge60_positive")

    if top10_roi is not None and baseline_roi is not None:
        if top10_roi > baseline_roi:
            passed.append("top10_above_baseline")
        else:
            failed.append("top10_above_baseline")
            perf_fail = True
    else:
        insufficient.append("top10_above_baseline")

    if high_vs_all is not None:
        if high_vs_all > 0:
            passed.append("high_vs_all_uplift_positive")
        else:
            failed.append("high_vs_all_uplift_positive")
            perf_fail = True
    else:
        insufficient.append("high_vs_all_uplift_positive")

    if equal_roi_delta is not None:
        if equal_roi_delta >= 0:
            passed.append("equal_coverage_roi_not_worse_than_v3")
        else:
            failed.append("equal_coverage_roi_not_worse_than_v3")
            perf_fail = True
    else:
        insufficient.append("equal_coverage_roi_not_worse_than_v3")

    if drawdown_delta is not None and drawdown_delta < -0.15 and (
        equal_roi_delta is None or equal_roi_delta < 0.05
    ):
        failed.append("drawdown_not_materially_worse")
        perf_fail = True
    elif drawdown_delta is None:
        insufficient.append("drawdown_not_materially_worse")
    else:
        passed.append("drawdown_not_materially_worse")

    evidence["roi60"] = roi60
    evidence["margin60"] = margin60
    evidence["top10_roi"] = top10_roi
    evidence["baseline_roi"] = baseline_roi
    evidence["equal_roi_delta"] = equal_roi_delta

    # --- E. Ordinamento ---
    ordering = analytics.get("ordering") or ctx.get("ordering") or {}
    high_vs_low = _f(ordering.get("high_plus_very_high_vs_low_roi_delta"))
    severe_violations = int(ordering.get("severe_monotonicity_violations") or 0)
    if high_vs_low is not None:
        if high_vs_low > 0:
            passed.append("high_classes_beat_low")
        else:
            failed.append("high_classes_beat_low")
            perf_fail = True
    else:
        insufficient.append("high_classes_beat_low")
    if severe_violations > 0 and scored_real >= MIN_SAMPLE:
        failed.append("no_severe_monotonicity_violations")
        perf_fail = True
    else:
        passed.append("no_severe_monotonicity_violations")

    if perf_fail:
        return _pack(
            DECISION_NO_GO_PERFORMANCE,
            passed,
            failed,
            insufficient,
            evidence,
            blockers,
            warnings,
            "Non promuovere: performance/ordinamento insufficienti vs baseline o V3.",
            ctx,
        )

    # --- F/G. Holdout e robustezza ---
    has_independent_holdout = bool(ctx.get("has_independent_holdout"))
    evidence["has_independent_holdout"] = has_independent_holdout
    temporal_ok = bool(ctx.get("temporal_robustness_ok", True))
    single_month_dominated = bool(ctx.get("single_month_dominated"))
    single_comp_dominated = bool(ctx.get("single_competition_dominated"))
    single_market_dominated = bool(ctx.get("single_market_dominated"))

    if single_month_dominated or single_comp_dominated:
        warnings.append("ROI concentrato su mese/campionato unico")
        insufficient.append("temporal_diversification")
    else:
        passed.append("temporal_diversification")

    if single_market_dominated:
        warnings.append("Quasi tutto il profitto da un solo mercato")
        insufficient.append("market_diversification")
    else:
        passed.append("market_diversification")

    if not temporal_ok:
        insufficient.append("multi_window_positive")
    else:
        passed.append("multi_window_positive")

    # Decisione finale
    core_positive = (
        positive_tail
        and not all_collapse
        and "roi_ge60_positive" in passed
        and "high_classes_beat_low" in passed
    ) or (
        positive_tail
        and not all_collapse
        and "roi_ge60_positive" not in failed
        and "high_classes_beat_low" not in failed
    )

    if not has_independent_holdout:
        if core_positive or (positive_tail and not all_collapse and not perf_fail):
            insufficient.append("independent_holdout")
            warnings.append(
                "Holdout indipendente assente: decisione massima GO_PROVISIONAL; V3.1 resta shadow."
            )
            return _pack(
                DECISION_GO_PROVISIONAL,
                passed,
                failed,
                insufficient,
                evidence,
                blockers,
                warnings,
                "Eseguire Historical Scan su stagione successiva congelata, poi rivalutare GO_FINAL.",
                ctx,
            )
        return _pack(
            DECISION_NO_GO_DATA,
            passed,
            failed,
            insufficient,
            evidence,
            blockers,
            warnings,
            "Dati/coda positiva insufficienti anche in modalità provvisoria.",
            ctx,
        )

    if not molto_alta_min:
        warnings.append(
            "Molto Alta con campione < MIN_SAMPLE: niente messaggio operativo forte."
        )
        return _pack(
            DECISION_GO_PROVISIONAL,
            passed,
            failed,
            insufficient,
            evidence,
            blockers,
            warnings,
            "Attendere campione Molto Alta sufficiente prima di GO_FINAL.",
            ctx,
        )

    # GO_FINAL richiede criteri performance passati e holdout
    required_for_final = {
        "positive_tail_present",
        "holdout_high_min_sample",
        "very_high_present",
        "molto_alta_min_sample",
        "roi_ge60_positive",
        "margin_ge60_positive",
        "top10_above_baseline",
        "high_vs_all_uplift_positive",
        "equal_coverage_roi_not_worse_than_v3",
        "high_classes_beat_low",
    }
    missing_required = [c for c in required_for_final if c not in passed]
    if missing_required:
        for c in missing_required:
            if c not in insufficient and c not in failed:
                insufficient.append(c)
        return _pack(
            DECISION_GO_PROVISIONAL,
            passed,
            failed,
            insufficient,
            evidence,
            blockers,
            warnings,
            "Holdout presente ma criteri statistici incompleti: restare in shadow.",
            ctx,
        )

    return _pack(
        DECISION_GO_FINAL,
        passed,
        failed,
        insufficient,
        evidence,
        blockers,
        warnings,
        "Promozione V3.1 consentita con confirm token e audit.",
        ctx,
    )


def _threshold_block(perf: dict[str, Any], threshold: int) -> dict[str, Any] | None:
    if not isinstance(perf, dict):
        return None
    key = f"score_ge_{threshold}"
    if key in perf and isinstance(perf[key], dict):
        return perf[key]
    by_thr = perf.get("by_threshold") or perf.get("thresholds") or {}
    if isinstance(by_thr, dict):
        block = by_thr.get(str(threshold)) or by_thr.get(threshold) or by_thr.get(key)
        if isinstance(block, dict):
            return block
    return None


def _pack(
    decision: str,
    passed: list[str],
    failed: list[str],
    insufficient: list[str],
    evidence: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
    next_action: str,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    assert decision in ALLOWED_DECISIONS
    return {
        "version": GO_NO_GO_VERSION,
        "decision_version": GO_NO_GO_VERSION,
        "decision": decision,
        "criteria_passed": list(passed),
        "criteria_failed": list(failed),
        "criteria_insufficient": list(insufficient),
        "evidence": evidence,
        "blockers": list(blockers),
        "warnings": list(warnings),
        "recommended_next_action": next_action,
        "generated_at": _utcnow_iso(),
        "formula_version": ctx.get("formula_version"),
        "replay_id": ctx.get("replay_id"),
        "source_run_id": ctx.get("source_run_id"),
        "promotion_allowed": decision == DECISION_GO_FINAL,
        "strong_buy_message_allowed": decision == DECISION_GO_FINAL,
    }
