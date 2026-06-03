"""Motivi probabili errori predittivi in italiano."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

FALLBACK_REASON = "Motivo non disponibile"


def _trace_str(trace: dict[str, Any], key: str, default: str = "") -> str:
    v = trace.get(key, default)
    return v if isinstance(v, str) else default


def _trace_float(trace: dict[str, Any], key: str, default: float = 0.0) -> float:
    v = trace.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _bucket_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def probable_reason(row: dict[str, Any]) -> str:
    reason_codes = row.get("reason_codes")
    if isinstance(reason_codes, list) and reason_codes:
        first = reason_codes[0]
        if isinstance(first, dict):
            label = first.get("label_it")
            evidence = first.get("evidence")
            if label and evidence:
                return f"{label}: {evidence}"
            if label:
                return str(label)

    pred = row.get("predicted_total_sot")
    actual = row.get("actual_total_sot")
    err = row.get("error")
    pb = _bucket_str(row.get("predicted_bucket"))
    ab = _bucket_str(row.get("actual_bucket"))
    trace = row.get("trace") if isinstance(row.get("trace"), dict) else {}

    if pred is None or actual is None:
        return "Predizione o actual non disponibile."

    pred_f = float(pred)
    act_f = float(actual)
    e = float(err) if err is not None else pred_f - act_f

    boost_reason = _trace_str(trace, "boost_reason")
    boost_applied = _trace_float(trace, "boost_applied")

    if e < -2.5:
        if ab in ("high_total", "very_high_total") and pb in ("normal_total", "low_total"):
            return (
                "Il modello ha sottostimato: profilo pre-match medio, "
                "ma la partita è esplosa oltre lo storico (bucket alto)."
            )
        if boost_applied < 0.3:
            return (
                "Possibile sottostima: boost dinamico insufficiente "
                "rispetto alla forza offensiva del match."
            )
        return "Possibile sottostima della forza offensiva o della fragilità difensiva avversaria."

    if e > 2.5:
        if boost_reason.startswith("chaos") or boost_applied > 0.8:
            return (
                "Il modello ha sovrastimato: dati pre-match indicavano volume alto, "
                "ma il match si è chiuso tatticamente."
            )
        return "Possibile sovrastima del volume offensivo atteso pre-match."

    if abs(e) <= 1.0:
        return "Errore contenuto: predizione vicina al reale."

    if e < 0:
        return "Leggera sottostima; il totale reale ha superato la stima numerica."

    return "Leggera sovrastima; il totale reale è rimasto sotto la stima."


def safe_probable_reason(row: dict[str, Any]) -> str:
    """Non propaga eccezioni: fallback se trace o tipi sono inconsistenti."""
    try:
        reason = probable_reason(row)
        return reason if isinstance(reason, str) and reason.strip() else FALLBACK_REASON
    except Exception:
        logger.warning(
            "V31 probable_reason fallback fixture_id=%s",
            row.get("fixture_id"),
            exc_info=True,
        )
        return FALLBACK_REASON
