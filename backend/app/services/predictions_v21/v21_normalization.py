"""Normalizzazione micro-variabili v2.1 intorno a 1.0 con cap prudente."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.predictions_v21.v21_constants import MICRO_NORM_MAX, MICRO_NORM_MIN

V21MicroStatus = Literal[
    "available",
    "available_derived",
    "missing",
    "not_tracked_yet",
    "fallback",
    "fallback_partial",
    "fallback_historical_profiles",
    "partial",
]


def micro_status_counts_available(status: V21MicroStatus) -> bool:
    """True se la micro contribuisce alla copertura dati (non missing/not_tracked)."""
    return status in (
        "available",
        "available_derived",
        "partial",
        "fallback_historical_profiles",
        "fallback_partial",
    )


@dataclass
class V21MicroResult:
    key: str
    label: str
    micro_weight: int | None
    source_path: str
    raw_value: float | None
    normalized_value: float
    status: V21MicroStatus
    sample_count: int | None
    fallback_used: bool
    contribution: str
    warning: str | None = None

    def to_trace_input(self) -> dict:
        raw_r = round(float(self.raw_value), 2) if self.raw_value is not None else None
        norm_r = round(float(self.normalized_value), 2)
        return {
            "value": raw_r,
            "raw_value": raw_r,
            "normalized_value": norm_r,
            "micro_weight": self.micro_weight,
            "status": self.status,
            "source_path": self.source_path,
            "sample_count": self.sample_count,
            "fallback_used": self.fallback_used,
            "contribution": self.contribution,
            "warning": self.warning,
        }


def clamp_micro_norm(value: float) -> float:
    return max(MICRO_NORM_MIN, min(MICRO_NORM_MAX, float(value)))


def neutral_micro(
    *,
    key: str,
    label: str,
    micro_weight: int | None,
    source_path: str,
    status: V21MicroStatus = "missing",
    warning: str | None = None,
    fallback_used: bool = False,
) -> V21MicroResult:
    return V21MicroResult(
        key=key,
        label=label,
        micro_weight=micro_weight,
        source_path=source_path,
        raw_value=None,
        normalized_value=1.0,
        status=status,
        sample_count=None,
        fallback_used=fallback_used,
        contribution="neutra",
        warning=warning,
    )


def normalize_v21_micro_variable(
    *,
    key: str,
    label: str,
    micro_weight: int | None,
    source_path: str,
    raw_value: float | None,
    baseline: float | None,
    sample_count: int | None = None,
    status: V21MicroStatus = "available",
    fallback_used: bool = False,
    warning: str | None = None,
    invert: bool = False,
) -> V21MicroResult:
    if raw_value is None:
        return neutral_micro(
            key=key,
            label=label,
            micro_weight=micro_weight,
            source_path=source_path,
            status=status if status != "available" else "missing",
            warning=warning or f"Dato non disponibile per {label}",
            fallback_used=fallback_used,
        )
    if baseline is None or baseline <= 0:
        norm = 1.0
        eff_status: V21MicroStatus = "partial" if status == "available" else status
        eff_warning = warning or "Baseline assente: normalizzazione neutra"
    else:
        ratio = float(raw_value) / float(baseline)
        if invert:
            ratio = float(baseline) / float(raw_value) if float(raw_value) > 0 else 1.0
        norm = clamp_micro_norm(ratio)
        eff_status = status
        eff_warning = warning

    if norm > 1.02:
        contrib = "positiva"
    elif norm < 0.98:
        contrib = "negativa"
    else:
        contrib = "neutra"

    return V21MicroResult(
        key=key,
        label=label,
        micro_weight=micro_weight,
        source_path=source_path,
        raw_value=float(raw_value),
        normalized_value=round(norm, 4),
        status=eff_status,
        sample_count=sample_count,
        fallback_used=fallback_used,
        contribution=contrib,
        warning=eff_warning,
    )


def normalize_ratio_direct(
    *,
    key: str,
    label: str,
    micro_weight: int | None,
    source_path: str,
    ratio: float | None,
    sample_count: int | None = None,
    status: V21MicroStatus = "available",
    fallback_used: bool = False,
    warning: str | None = None,
) -> V21MicroResult:
    """Normalizza un rapporto già calcolato (es. trend recente vs stagione)."""
    if ratio is None:
        return neutral_micro(
            key=key,
            label=label,
            micro_weight=micro_weight,
            source_path=source_path,
            status=status if status != "available" else "missing",
            warning=warning,
            fallback_used=fallback_used,
        )
    norm = clamp_micro_norm(float(ratio))
    if norm > 1.02:
        contrib = "positiva"
    elif norm < 0.98:
        contrib = "negativa"
    else:
        contrib = "neutra"
    return V21MicroResult(
        key=key,
        label=label,
        micro_weight=micro_weight,
        source_path=source_path,
        raw_value=round(float(ratio), 4),
        normalized_value=round(norm, 4),
        status=status,
        sample_count=sample_count,
        fallback_used=fallback_used,
        contribution=contrib,
        warning=warning,
    )
