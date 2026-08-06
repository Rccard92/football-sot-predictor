"""Policy storica V3.1 — v1 (bloccante HR/100) vs v2 (multiplier neutrale).

Condivide solo la risoluzione del campione; le differenze restano isolate qui.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from app.services.cecchino.cecchino_historical_reliability import (
    HISTORICAL_RELIABILITY_VERSION,
    MIN_SAMPLE,
)
from app.services.cecchino.cecchino_purchasability_candidate import clamp

PolicyVariant = Literal["v1", "v2"]

# Status HR riconosciuti
HR_STATUS_OK = "ok"
HR_STATUS_PROVISIONAL = "provisional_insufficient_sample"
HR_STATUS_NO_HISTORY = "no_history"
HR_STATUS_INSUFFICIENT = "insufficient_data"  # legacy v1 / pre-v2


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _sample_n(item: dict[str, Any] | None) -> int:
    if not isinstance(item, dict):
        return 0
    sample = item.get("selected_sample_size")
    if sample is None:
        sample = item.get("sample_size")
    try:
        return max(0, int(sample) if sample is not None else 0)
    except (TypeError, ValueError):
        return 0


def historical_multiplier_from_score(hr_score: float) -> float:
    """v2: 1 + (HR - 50) / 100  ≡  0.5 + HR/100."""
    return 1.0 + (float(hr_score) - 50.0) / 100.0


def resolve_historical_v1(
    historical_reliability_item: dict[str, Any] | None,
) -> dict[str, Any]:
    """Policy v1: sample < MIN_SAMPLE → blocco non_calculable."""
    if not isinstance(historical_reliability_item, dict):
        return {
            "ok": False,
            "blocks_score": True,
            "reason_code": "historical_reliability_unavailable",
            "historical_reason_codes": ["historical_reliability_unavailable"],
            "reading": "Storico non disponibile",
            "item": None,
            "policy": "v1",
        }
    status = str(historical_reliability_item.get("status") or "")
    score = _safe_float(historical_reliability_item.get("score"))
    sample_n = _sample_n(historical_reliability_item)

    if status in (HR_STATUS_INSUFFICIENT, HR_STATUS_PROVISIONAL, HR_STATUS_NO_HISTORY) or (
        status == HR_STATUS_OK and sample_n < MIN_SAMPLE
    ):
        return {
            "ok": False,
            "blocks_score": True,
            "reason_code": "historical_sample_insufficient",
            "historical_reason_codes": ["historical_sample_insufficient"],
            "reading": (
                "Storico insufficiente per questo mercato e questa fascia Rating"
            ),
            "item": historical_reliability_item,
            "sample_size": sample_n,
            "policy": "v1",
        }
    if status != HR_STATUS_OK or score is None:
        return {
            "ok": False,
            "blocks_score": True,
            "reason_code": "historical_reliability_unavailable",
            "historical_reason_codes": ["historical_reliability_unavailable"],
            "reading": "Storico non disponibile",
            "item": historical_reliability_item,
            "sample_size": sample_n,
            "policy": "v1",
        }
    if sample_n < MIN_SAMPLE:
        return {
            "ok": False,
            "blocks_score": True,
            "reason_code": "historical_sample_insufficient",
            "historical_reason_codes": ["historical_sample_insufficient"],
            "reading": (
                "Storico insufficiente per questo mercato e questa fascia Rating"
            ),
            "item": historical_reliability_item,
            "sample_size": sample_n,
            "policy": "v1",
        }
    factor = float(score) / 100.0
    return {
        "ok": True,
        "blocks_score": False,
        "reason_code": None,
        "historical_reason_codes": [],
        "reading": None,
        "item": historical_reliability_item,
        "score": float(score),
        "factor": factor,
        "historical_factor_legacy": factor,
        "historical_multiplier": None,
        "sample_size": sample_n,
        "min_sample": MIN_SAMPLE,
        "historical_evidence_quality": "definitive",
        "item_status": "score",
        "calculation_quality": "full",
        "policy": "v1",
    }


def resolve_historical_v2(
    historical_reliability_item: dict[str, Any] | None,
) -> dict[str, Any]:
    """Policy v2: storico non bloccante; MIN_SAMPLE → definitive vs provisional."""
    sample_n = _sample_n(historical_reliability_item)
    item = historical_reliability_item if isinstance(historical_reliability_item, dict) else None
    status = str((item or {}).get("status") or "") if item else ""
    reason_codes: list[str] = []

    # Nessun item / campione zero → neutral fallback
    if item is None or sample_n <= 0 or status in (
        HR_STATUS_NO_HISTORY,
        "history_unavailable",
    ):
        if item is None:
            reason_codes.append("historical_reliability_unavailable")
        reason_codes.append("historical_no_sample")
        hr_score = 50.0
        multiplier = historical_multiplier_from_score(hr_score)
        return {
            "ok": True,
            "blocks_score": False,
            "reason_code": None,
            "historical_reason_codes": reason_codes,
            "reading": (
                "Nessuno storico disponibile: applicato moltiplicatore neutrale 1,00"
            ),
            "item": item,
            "score": hr_score,
            "score_is_neutral_fallback": True,
            "factor": None,
            "historical_multiplier": multiplier,
            "sample_size": 0,
            "min_sample": MIN_SAMPLE,
            "sample_confidence": 0.0,
            "raw_evidence": None,
            "historical_evidence_quality": "neutral_fallback",
            "item_status": "score_provisional",
            "calculation_quality": "provisional",
            "historical_reliability_status": HR_STATUS_NO_HISTORY,
            "policy": "v2",
        }

    score = _safe_float(item.get("score"))
    # Legacy insufficient_data senza score: tratta come provisional se n>=1
    # oppure recalcola non possibile → neutral se score assente e n < MIN_SAMPLE
    if score is None and sample_n >= 1:
        # Non inventare ROI: usa fallback neutrale ma marca provisional con sample
        reason_codes.append("historical_sample_below_minimum")
        if status == HR_STATUS_INSUFFICIENT:
            reason_codes.append("historical_legacy_insufficient_without_score")
        hr_score = 50.0
        multiplier = historical_multiplier_from_score(hr_score)
        return {
            "ok": True,
            "blocks_score": False,
            "reason_code": None,
            "historical_reason_codes": reason_codes,
            "reading": (
                f"Storico disponibile ma incompleto ({sample_n}/{MIN_SAMPLE}): "
                "moltiplicatore neutrale provvisorio"
            ),
            "item": item,
            "score": hr_score,
            "score_is_neutral_fallback": True,
            "factor": None,
            "historical_multiplier": multiplier,
            "sample_size": sample_n,
            "min_sample": MIN_SAMPLE,
            "sample_confidence": min(1.0, sample_n / 100.0),
            "raw_evidence": item.get("raw_evidence_score"),
            "historical_evidence_quality": "provisional",
            "item_status": "score_provisional",
            "calculation_quality": "provisional",
            "historical_reliability_status": HR_STATUS_PROVISIONAL,
            "policy": "v2",
        }

    if score is None:
        reason_codes.append("historical_no_sample")
        hr_score = 50.0
        multiplier = historical_multiplier_from_score(hr_score)
        return {
            "ok": True,
            "blocks_score": False,
            "reason_code": None,
            "historical_reason_codes": reason_codes,
            "reading": "Fallback neutrale: score storico assente",
            "item": item,
            "score": hr_score,
            "score_is_neutral_fallback": True,
            "factor": None,
            "historical_multiplier": multiplier,
            "sample_size": sample_n,
            "min_sample": MIN_SAMPLE,
            "sample_confidence": 0.0,
            "raw_evidence": None,
            "historical_evidence_quality": "neutral_fallback",
            "item_status": "score_provisional",
            "calculation_quality": "provisional",
            "historical_reliability_status": HR_STATUS_NO_HISTORY,
            "policy": "v2",
        }

    hr_score = float(score)
    multiplier = historical_multiplier_from_score(hr_score)
    confidence = item.get("sample_confidence")
    if confidence is None:
        confidence = min(1.0, sample_n / 100.0)

    if sample_n >= MIN_SAMPLE and status in (HR_STATUS_OK, ""):
        evidence = "definitive"
        item_status = "score"
        calc_q = "full"
        hr_status = HR_STATUS_OK
    else:
        evidence = "provisional"
        item_status = "score_provisional"
        calc_q = "provisional"
        hr_status = (
            HR_STATUS_PROVISIONAL
            if sample_n >= 1
            else HR_STATUS_NO_HISTORY
        )
        reason_codes.append("historical_sample_below_minimum")

    if item.get("fallback_used"):
        reason_codes.append("historical_global_fallback")
    stab = item.get("stability_ratio")
    if stab is None and sample_n >= 1:
        if item.get("stability_status") == "insufficient_periods" or (
            item.get("total_periods") is not None
            and int(item.get("total_periods") or 0) < 2
        ):
            reason_codes.append("historical_stability_insufficient_periods")

    return {
        "ok": True,
        "blocks_score": False,
        "reason_code": None,
        "historical_reason_codes": reason_codes,
        "reading": None,
        "item": item,
        "score": hr_score,
        "score_is_neutral_fallback": False,
        "factor": None,
        "historical_multiplier": multiplier,
        "sample_size": sample_n,
        "min_sample": MIN_SAMPLE,
        "sample_confidence": float(confidence) if confidence is not None else None,
        "raw_evidence": item.get("raw_evidence_score"),
        "historical_evidence_quality": evidence,
        "item_status": item_status,
        "calculation_quality": calc_q,
        "historical_reliability_status": hr_status
        if status not in (HR_STATUS_PROVISIONAL, HR_STATUS_OK)
        else (status or hr_status),
        "policy": "v2",
    }


def resolve_historical(
    historical_reliability_item: dict[str, Any] | None,
    *,
    policy: PolicyVariant = "v2",
) -> dict[str, Any]:
    if policy == "v1":
        return resolve_historical_v1(historical_reliability_item)
    return resolve_historical_v2(historical_reliability_item)


def build_historical_block(
    hr_resolved: dict[str, Any],
    *,
    policy: PolicyVariant = "v2",
) -> dict[str, Any]:
    item = hr_resolved.get("item") if isinstance(hr_resolved.get("item"), dict) else {}
    score = hr_resolved.get("score")
    sample_n = hr_resolved.get("sample_size")
    if sample_n is None:
        sample_n = _sample_n(item if item else None)

    block: dict[str, Any] = {
        "historical_reliability_version": (item or {}).get("version")
        or HISTORICAL_RELIABILITY_VERSION,
        "historical_reliability_status": hr_resolved.get(
            "historical_reliability_status"
        )
        or (item or {}).get("status"),
        "historical_reliability_score": score
        if score is not None
        else (item or {}).get("score"),
        "historical_reliability_class": (item or {}).get("class"),
        "cohort_scope": (item or {}).get("cohort_scope"),
        "rating_band": (item or {}).get("rating_band"),
        "local_sample_size": (item or {}).get("local_sample_size"),
        "global_sample_size": (item or {}).get("global_sample_size"),
        "selected_sample_size": (item or {}).get("selected_sample_size") or sample_n,
        "sample_size": sample_n,
        "min_sample": hr_resolved.get("min_sample") or MIN_SAMPLE,
        "wins": (item or {}).get("wins"),
        "losses": (item or {}).get("losses"),
        "voids": (item or {}).get("voids"),
        "roi": (item or {}).get("roi"),
        "realized_margin": (item or {}).get("realized_margin"),
        "average_odds": (item or {}).get("average_odds"),
        "win_rate": (item or {}).get("win_rate"),
        "total_profit": (item or {}).get("total_profit"),
        "stability_ratio": (item or {}).get("stability_ratio"),
        "stability_status": (item or {}).get("stability_status"),
        "stability_component": (item or {}).get("stability_component"),
        "roi_component": (item or {}).get("roi_component"),
        "margin_component": (item or {}).get("margin_component"),
        "raw_evidence_score": hr_resolved.get("raw_evidence")
        or (item or {}).get("raw_evidence_score"),
        "sample_confidence": hr_resolved.get("sample_confidence")
        if hr_resolved.get("sample_confidence") is not None
        else (item or {}).get("sample_confidence"),
        "historical_date_from": (item or {}).get("date_from")
        or (item or {}).get("historical_date_from"),
        "historical_date_to": (item or {}).get("date_to")
        or (item or {}).get("historical_date_to"),
        "positive_periods": (item or {}).get("positive_periods"),
        "total_periods": (item or {}).get("total_periods"),
        "fallback_used": (item or {}).get("fallback_used"),
        "fallback_reason": (item or {}).get("fallback_reason"),
        "historical_reason_codes": list(
            hr_resolved.get("historical_reason_codes") or []
        ),
        "historical_evidence_quality": hr_resolved.get(
            "historical_evidence_quality"
        ),
        "score_is_neutral_fallback": bool(
            hr_resolved.get("score_is_neutral_fallback")
        ),
        "policy": policy,
    }

    if policy == "v1":
        factor = hr_resolved.get("factor")
        block["historical_factor"] = factor
        block["historical_factor_legacy"] = factor
        block["historical_multiplier"] = None
    else:
        mult = hr_resolved.get("historical_multiplier")
        block["historical_multiplier"] = mult
        block["historical_factor"] = None  # non riusare semantica ambigua
        block["historical_factor_legacy"] = None

    return block


def apply_historical_to_theoretical(
    theoretical_raw_score: float,
    hr_resolved: dict[str, Any],
    *,
    policy: PolicyVariant = "v2",
) -> dict[str, Any]:
    """Applica factor (v1) o multiplier (v2) allo score teorico."""
    if policy == "v1":
        factor = float(hr_resolved["factor"])
        raw = theoretical_raw_score * factor
        return {
            "historical_factor": factor,
            "historical_factor_legacy": factor,
            "historical_multiplier": None,
            "historical_adjusted_raw_score": raw,
            "raw_score_v31": clamp(raw, 0.0, 100.0),
            "historical_adjustment_points": None,
            "historical_adjustment_pct": None,
        }

    multiplier = float(hr_resolved["historical_multiplier"])
    adjusted = theoretical_raw_score * multiplier
    raw_clamped = clamp(adjusted, 0.0, 100.0)
    return {
        "historical_factor": None,
        "historical_factor_legacy": None,
        "historical_multiplier": multiplier,
        "historical_adjusted_raw_score": adjusted,
        "raw_score_v31": raw_clamped,
        "historical_adjustment_points": raw_clamped - theoretical_raw_score,
        "historical_adjustment_pct": (multiplier - 1.0) * 100.0,
    }
