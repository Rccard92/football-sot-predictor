"""Normalizzazione trace predittivo v3.1 (default coerenti, no None su campi stringa)."""

from __future__ import annotations

from typing import Any

DEFAULT_TRACE: dict[str, Any] = {
    "boost_reason": "",
    "boost_applied": 0.0,
    "league_blend_applied": 0.0,
    "interaction_scores": {},
    "missing_fields": [],
    "warnings": [],
}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if x is not None]


def normalize_prediction_trace(trace: dict[str, Any] | None) -> dict[str, Any]:
    """Merge trace con default; campi opzionali non calcolabili restano null dove già null."""
    raw = dict(trace or {})
    out: dict[str, Any] = {**DEFAULT_TRACE, **raw}

    out["boost_reason"] = _coerce_str(raw.get("boost_reason"), "")
    out["boost_applied"] = round(
        _coerce_float(raw.get("boost_applied", raw.get("total_boost_applied")), 0.0),
        4,
    )
    out["league_blend_applied"] = round(_coerce_float(raw.get("league_blend_applied"), 0.0), 4)
    out["interaction_scores"] = _coerce_dict(raw.get("interaction_scores"))
    out["missing_fields"] = _coerce_str_list(raw.get("missing_fields"))
    out["warnings"] = _coerce_str_list(raw.get("warnings"))

    return out
