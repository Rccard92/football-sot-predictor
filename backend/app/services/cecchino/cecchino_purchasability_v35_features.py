"""Feature builder e gate V3.5 — whitelist input, execution quote, gate EV-based."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
    clip_prob,
    parse_iso,
)
from app.services.cecchino.cecchino_purchasability_v35_config import (
    GATE_REASON_EXECUTION_QUOTE_NOT_REAL,
    GATE_REASON_INCOMPLETE_MARKET,
    GATE_REASON_INVALID_EXECUTION_QUOTE,
    GATE_REASON_INVALID_PRE_MATCH_SNAPSHOT,
    GATE_REASON_INVALID_PROBABILITY,
    GATE_REASON_MISSING_EXECUTION_QUOTE,
    GATE_REASON_MISSING_FAIR_BOOK_PROBABILITY,
    GATE_REASON_MISSING_MODEL_PROBABILITY,
    GATE_REASON_MODEL_NOT_ABOVE_FAIR,
    GATE_REASON_NON_POSITIVE_EV,
    GATE_REASON_RATING_BELOW_50,
    GATE_REASON_RATING_MISSING,
    RATING_MIN_GATE,
    SOURCE_DC_DERIVED,
    V35_ALLOWED_ROW_KEYS,
    V35_FORBIDDEN_INPUT_KEYS,
    _DERIVED_BOOK_SOURCE_MARKERS,
)


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


def sanitize_kpi_row(row: dict[str, Any]) -> dict[str, Any]:
    """Whitelist row fields; drop forbidden keys silently."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in V35_FORBIDDEN_INPUT_KEYS:
            continue
        if key in V35_ALLOWED_ROW_KEYS or key == "market_key":
            out[key] = value
    mk = out.get("market_key") or row.get("segno")
    if mk:
        out["market_key"] = str(mk)
    return out


def resolve_probability_cecchino(
    row: dict[str, Any],
    model_probs: dict[str, float | None] | None,
    market_key: str,
) -> float | None:
    if model_probs and market_key in model_probs:
        p = _safe_float(model_probs.get(market_key))
        if p is not None:
            return p
    return _safe_float(row.get("prob_cecchino"))


def is_valid_open_probability(p: float | None) -> bool:
    if p is None:
        return False
    return 0.0 < p < 1.0


def resolve_execution_quote_v35(
    fair_info: dict[str, Any] | None,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Quota realmente eseguibile vs derivata — reimplementazione locale V3.5."""
    quota_book = _safe_float(row.get("quota_book"))
    book_source = str(
        row.get("book_source")
        or row.get("odds_source")
        or row.get("quote_source")
        or ""
    )
    fair_source = None
    if isinstance(fair_info, dict):
        fair_source = fair_info.get("fair_book_probability_source")

    if quota_book is None or quota_book <= 1.0:
        return {
            "execution_quote": None,
            "execution_quote_source": book_source or None,
            "execution_quote_real": False,
            "performance_type": "unavailable",
            "reason_code": GATE_REASON_MISSING_EXECUTION_QUOTE
            if quota_book is None
            else GATE_REASON_INVALID_EXECUTION_QUOTE,
            "fair_probability_may_be_derived": fair_source == SOURCE_DC_DERIVED,
        }

    is_derived = bool(
        row.get("derived_quote")
        or row.get("not_real_book_quote")
        or row.get("force_derived_quote")
    )
    src_l = book_source.lower()
    if any(m in src_l for m in _DERIVED_BOOK_SOURCE_MARKERS):
        is_derived = True
    if fair_source == SOURCE_DC_DERIVED and (
        "derived" in src_l or row.get("force_derived_quote") is True
    ):
        is_derived = True

    if is_derived:
        return {
            "execution_quote": quota_book,
            "execution_quote_source": book_source or str(fair_source or "derived"),
            "execution_quote_real": False,
            "performance_type": "derived",
            "reason_code": GATE_REASON_EXECUTION_QUOTE_NOT_REAL,
            "fair_probability_may_be_derived": True,
        }

    return {
        "execution_quote": quota_book,
        "execution_quote_source": book_source or "betfair_panel",
        "execution_quote_real": True,
        "performance_type": "real",
        "reason_code": None,
        "fair_probability_may_be_derived": fair_source == SOURCE_DC_DERIVED,
    }


def compute_expected_value(probability_cecchino: float, execution_quote: float) -> float:
    return probability_cecchino * execution_quote - 1.0


def compute_hours_to_kickoff(
    fixture_meta: dict[str, Any] | None,
) -> float | None:
    if not isinstance(fixture_meta, dict):
        return None
    kickoff = parse_iso(fixture_meta.get("kickoff"))
    snapshot_at = parse_iso(fixture_meta.get("snapshot_at"))
    if kickoff is None or snapshot_at is None:
        return None
    delta = kickoff - snapshot_at
    return delta.total_seconds() / 3600.0


def evaluate_v35_gate(
    *,
    row: dict[str, Any],
    fair_info: dict[str, Any] | None,
    exec_info: dict[str, Any],
    probability_cecchino: float | None,
    fair_book_probability: float | None,
    fixture_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gate V3.5 — machine-readable reason codes."""
    reason_codes: list[str] = []

    # Execution quote
    if not exec_info.get("execution_quote_real"):
        rc = exec_info.get("reason_code")
        if rc:
            reason_codes.append(str(rc))
        else:
            reason_codes.append(GATE_REASON_MISSING_EXECUTION_QUOTE)
        return _gate_result(
            gate_status="unavailable_inputs",
            item_status="not_calculable",
            reason_codes=reason_codes,
        )

    execution_quote = _safe_float(exec_info.get("execution_quote"))
    if execution_quote is None or execution_quote <= 1.0:
        reason_codes.append(GATE_REASON_INVALID_EXECUTION_QUOTE)
        return _gate_result(
            gate_status="unavailable_inputs",
            item_status="not_calculable",
            reason_codes=reason_codes,
        )

    # Model probability
    if probability_cecchino is None:
        reason_codes.append(GATE_REASON_MISSING_MODEL_PROBABILITY)
        return _gate_result(
            gate_status="unavailable_inputs",
            item_status="not_calculable",
            reason_codes=reason_codes,
        )
    if not is_valid_open_probability(probability_cecchino):
        reason_codes.append(GATE_REASON_INVALID_PROBABILITY)
        return _gate_result(
            gate_status="unavailable_inputs",
            item_status="not_calculable",
            reason_codes=reason_codes,
        )

    # Fair book probability
    fair_verified = bool(
        isinstance(fair_info, dict)
        and fair_info.get("fair_book_probability_verified")
    )
    if fair_book_probability is None or not fair_verified:
        if fair_book_probability is None:
            reason_codes.append(GATE_REASON_MISSING_FAIR_BOOK_PROBABILITY)
        else:
            reason_codes.append(GATE_REASON_INCOMPLETE_MARKET)
        return _gate_result(
            gate_status="unavailable_inputs",
            item_status="not_calculable",
            reason_codes=reason_codes,
        )
    if not is_valid_open_probability(fair_book_probability):
        reason_codes.append(GATE_REASON_INVALID_PROBABILITY)
        return _gate_result(
            gate_status="unavailable_inputs",
            item_status="not_calculable",
            reason_codes=reason_codes,
        )

    # Rating
    rating = _safe_float(row.get("rating"))
    if rating is None:
        reason_codes.append(GATE_REASON_RATING_MISSING)
        return _gate_result(
            gate_status="unavailable_inputs",
            item_status="not_calculable",
            reason_codes=reason_codes,
        )

    # Economic direction
    ev = compute_expected_value(probability_cecchino, execution_quote)
    if ev <= 0:
        reason_codes.append(GATE_REASON_NON_POSITIVE_EV)
        return _gate_result(
            gate_status="gate_failed",
            item_status="gate_failed",
            reason_codes=reason_codes,
            ev=ev,
            rating=rating,
        )

    if probability_cecchino <= fair_book_probability:
        reason_codes.append(GATE_REASON_MODEL_NOT_ABOVE_FAIR)
        return _gate_result(
            gate_status="gate_failed",
            item_status="gate_failed",
            reason_codes=reason_codes,
            ev=ev,
            rating=rating,
        )

    if rating < RATING_MIN_GATE:
        reason_codes.append(GATE_REASON_RATING_BELOW_50)
        return _gate_result(
            gate_status="gate_failed",
            item_status="gate_failed",
            reason_codes=reason_codes,
            ev=ev,
            rating=rating,
        )

    return {
        "gate_status": "passed",
        "item_status": "score",
        "gate_reason_codes": [],
        "expected_value": ev,
        "execution_quote": execution_quote,
        "probability_cecchino": probability_cecchino,
        "fair_book_probability": fair_book_probability,
        "rating": rating,
        "rating_threshold": RATING_MIN_GATE,
    }


def _gate_result(
    *,
    gate_status: str,
    item_status: str,
    reason_codes: list[str],
    ev: float | None = None,
    rating: float | None = None,
) -> dict[str, Any]:
    return {
        "gate_status": gate_status,
        "item_status": item_status,
        "gate_reason_codes": reason_codes,
        "expected_value": ev,
        "rating": rating,
        "rating_threshold": RATING_MIN_GATE,
    }


def resolve_fair_book_probability(fair_info: dict[str, Any] | None) -> float | None:
    if not isinstance(fair_info, dict):
        return None
    if not fair_info.get("fair_book_probability_verified"):
        return None
    return _safe_float(fair_info.get("fair_book_probability"))


def resolve_overround(fair_info: dict[str, Any] | None) -> float | None:
    if not isinstance(fair_info, dict):
        return None
    ov = _safe_float(fair_info.get("market_overround"))
    if ov is not None:
        return ov
    norm = fair_info.get("normalization_payload")
    if isinstance(norm, dict):
        ov = _safe_float(norm.get("overround"))
        if ov is not None:
            return ov
        return _safe_float(norm.get("overround_1x2"))
    return None


def build_market_input_context(
    *,
    row: dict[str, Any],
    fair_info: dict[str, Any] | None,
    model_probs: dict[str, float | None] | None,
    market_key: str,
    fixture_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble pre-match context for one market (whitelist-safe)."""
    clean_row = sanitize_kpi_row(row)
    exec_info = resolve_execution_quote_v35(fair_info, clean_row)
    p_cec = resolve_probability_cecchino(clean_row, model_probs, market_key)
    p_fair = resolve_fair_book_probability(fair_info)
    overround = resolve_overround(fair_info)
    book_fallback = bool(clean_row.get("book_fallback_used") is True)
    fair_may_be_derived = bool(
        exec_info.get("fair_probability_may_be_derived")
        or (
            isinstance(fair_info, dict)
            and fair_info.get("fair_book_probability_source") == SOURCE_DC_DERIVED
        )
    )
    hours_to_kickoff = compute_hours_to_kickoff(fixture_meta)

    return {
        "row": clean_row,
        "execution": exec_info,
        "probability_cecchino": p_cec,
        "fair_book_probability": p_fair,
        "overround": overround,
        "book_fallback_used": book_fallback,
        "fair_probability_may_be_derived": fair_may_be_derived,
        "hours_to_kickoff": hours_to_kickoff,
        "edge_pct_diagnostic": _safe_float(clean_row.get("edge_pct")),
        "vantaggio_prob_diagnostic": _safe_float(clean_row.get("vantaggio_prob")),
    }


def assert_no_forbidden_keys_in_row(row: dict[str, Any]) -> list[str]:
    """Return forbidden keys present (for tests)."""
    return [k for k in row if k in V35_FORBIDDEN_INPUT_KEYS]
