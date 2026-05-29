"""Macroarea 10 — qualità, confidence e warning (non impatta moltiplicatore SOT)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.predictions_v21.v21_constants import QUALITY_MACRO_KEY
from app.services.predictions_v21.v21_macro_aggregators import V21MacroResult
from app.services.predictions_v21.v21_normalization import V21MicroResult


@dataclass
class V21QualitySummary:
    quality_score: int
    confidence_score: int
    warnings: list[str]
    missing_variables_count: int
    fallback_variables_count: int
    not_tracked_count: int
    data_leakage_check: str
    source_coverage_score: int
    formula_quality_status: str
    sample_count_by_variable: dict[str, int | None]
    fallbacks_used: list[str]
    missing_data_flags: list[str]
    suspicious_value_warnings: list[str]

    def to_quality_json(self) -> dict[str, Any]:
        return {
            "quality_score": self.quality_score,
            "confidence_score": self.confidence_score,
            "missing_variables_count": self.missing_variables_count,
            "fallback_variables_count": self.fallback_variables_count,
            "not_tracked_count": self.not_tracked_count,
            "data_leakage_check": self.data_leakage_check,
            "source_coverage_score": self.source_coverage_score,
            "formula_quality_status": self.formula_quality_status,
            "sample_count_by_variable": self.sample_count_by_variable,
            "fallbacks_used": self.fallbacks_used,
            "missing_data_flags": self.missing_data_flags,
            "suspicious_value_warnings": self.suspicious_value_warnings,
        }

    def to_trace_quality_blob(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count_by_variable,
            "fallbacks_used": self.fallbacks_used,
            "missing_data": self.missing_data_flags,
            "no_data_leakage_check": self.data_leakage_check,
            "source_path_audit": "ok" if self.source_coverage_score >= 50 else "partial",
            "formula_quality_status": self.formula_quality_status,
            "suspicious_value_warnings": self.suspicious_value_warnings,
            "quality_score": self.quality_score,
            "confidence_score": self.confidence_score,
            "missing_variables_count": self.missing_variables_count,
            "fallback_variables_count": self.fallback_variables_count,
            "source_coverage_score": self.source_coverage_score,
        }


def build_v21_quality_summary(
    macro_results: list[V21MacroResult],
    *,
    side_warnings: list[str],
    prior_team_count: int,
    prior_opponent_count: int,
) -> V21QualitySummary:
    all_micros: list[V21MicroResult] = []
    for mr in macro_results:
        if mr.key == QUALITY_MACRO_KEY:
            continue
        all_micros.extend(mr.micros)

    total = len(all_micros)
    missing = sum(1 for m in all_micros if m.status in ("missing", "not_tracked_yet"))
    fallback = sum(1 for m in all_micros if m.fallback_used or m.status == "fallback_historical_profiles")
    not_tracked = sum(1 for m in all_micros if m.status == "not_tracked_yet")
    available = sum(1 for m in all_micros if m.status == "available")

    sample_map: dict[str, int | None] = {}
    fallbacks_used: list[str] = []
    missing_flags: list[str] = []
    suspicious: list[str] = []

    for m in all_micros:
        sample_map[m.key] = m.sample_count
        if m.fallback_used or m.status == "fallback_historical_profiles":
            fallbacks_used.append(m.key)
        if m.status in ("missing", "not_tracked_yet"):
            missing_flags.append(m.key)
        if m.normalized_value >= 1.29 or m.normalized_value <= 0.71:
            suspicious.append(f"{m.key}: normalized={m.normalized_value}")

    coverage_pct = (100.0 * available / total) if total else 0.0
    source_coverage_score = int(round(coverage_pct))

    if prior_team_count == 0 or prior_opponent_count == 0:
        leakage = "warning_insufficient_prior_sample"
    else:
        leakage = "ok"

    if coverage_pct >= 75 and missing == 0:
        fq_status = "ok"
    elif coverage_pct >= 40:
        fq_status = "partial"
    else:
        fq_status = "insufficient_data"

    quality_score = int(round(max(0.0, min(100.0, coverage_pct - 0.5 * missing - 0.3 * fallback))))
    confidence_base = quality_score
    if leakage != "ok":
        confidence_base -= 10
    confidence_score = int(max(0, min(100, confidence_base)))

    warnings = list(side_warnings)
    for mr in macro_results:
        warnings.extend(mr.warnings[:3])
    if missing > 0:
        warnings.append(f"{missing} micro-variabili missing/not_tracked_yet")
    if fallback > 0:
        warnings.append(f"{fallback} micro-variabili con fallback")

    return V21QualitySummary(
        quality_score=quality_score,
        confidence_score=confidence_score,
        warnings=warnings,
        missing_variables_count=missing,
        fallback_variables_count=fallback,
        not_tracked_count=not_tracked,
        data_leakage_check=leakage,
        source_coverage_score=source_coverage_score,
        formula_quality_status=fq_status,
        sample_count_by_variable=sample_map,
        fallbacks_used=fallbacks_used,
        missing_data_flags=missing_flags,
        suspicious_value_warnings=suspicious,
    )
