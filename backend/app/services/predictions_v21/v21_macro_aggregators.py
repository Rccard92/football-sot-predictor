"""Aggregazione macroaree 1-9 e moltiplicatore finale v2.1."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.predictions_v21.v21_constants import (
    FINAL_MULTIPLIER_MAX,
    FINAL_MULTIPLIER_MIN,
    MACRO_INDEX_MAX,
    MACRO_INDEX_MIN,
    PREDICTIVE_MACRO_KEYS,
)
from app.services.predictions_v21.v21_manifest_definitions import V21MacroAreaSpec
from app.services.predictions_v21.v21_normalization import V21MicroResult, micro_status_counts_available


@dataclass
class V21MacroResult:
    key: str
    label: str
    macro_weight: int
    macro_index: float
    macro_contribution_to_multiplier: float
    coverage_pct: float
    status: str
    warnings: list[str]
    micros: list[V21MicroResult]
    is_quality_only: bool = False

    def to_components_blob(self) -> dict:
        available = sum(1 for m in self.micros if micro_status_counts_available(m.status))
        total = len(self.micros)
        return {
            "value": round(self.macro_index, 4),
            "macro_index": round(self.macro_index, 4),
            "macro_weight": self.macro_weight,
            "macro_contribution_to_multiplier": round(self.macro_contribution_to_multiplier, 4),
            "coverage_pct": round(self.coverage_pct, 1),
            "status": self.status,
            "warnings": self.warnings,
            "micro_available_count": available,
            "micro_total_count": total,
            "inputs": {m.key: m.to_trace_input() for m in self.micros},
        }


def aggregate_v21_macro_score(
    macro_spec: V21MacroAreaSpec,
    micro_results: list[V21MicroResult],
) -> V21MacroResult:
    weight_sum = sum(int(m.micro_weight or 0) for m in macro_spec.micros)
    if weight_sum <= 0:
        return V21MacroResult(
            key=macro_spec.key,
            label=macro_spec.label,
            macro_weight=macro_spec.macro_weight,
            macro_index=1.0,
            macro_contribution_to_multiplier=0.0,
            coverage_pct=0.0,
            status="missing",
            warnings=["Nessun peso micro nel manifest"],
            micros=micro_results,
            is_quality_only=macro_spec.is_quality_only,
        )

    weighted = sum(
        float(mr.normalized_value) * float(mr.micro_weight or 0)
        for mr in micro_results
    )
    macro_index = weighted / float(weight_sum)
    macro_index = max(MACRO_INDEX_MIN, min(MACRO_INDEX_MAX, macro_index))

    available_n = sum(1 for mr in micro_results if micro_status_counts_available(mr.status))
    coverage_pct = 100.0 * available_n / max(len(micro_results), 1)

    warnings: list[str] = []
    for mr in micro_results:
        if mr.warning:
            warnings.append(mr.warning)

    if available_n == 0:
        status = "missing"
    elif available_n < len(micro_results):
        status = "partial"
    else:
        status = "available"

    contrib = macro_index * float(macro_spec.macro_weight)

    return V21MacroResult(
        key=macro_spec.key,
        label=macro_spec.label,
        macro_weight=macro_spec.macro_weight,
        macro_index=round(macro_index, 4),
        macro_contribution_to_multiplier=round(contrib, 4),
        coverage_pct=round(coverage_pct, 1),
        status=status,
        warnings=warnings,
        micros=micro_results,
        is_quality_only=macro_spec.is_quality_only,
    )


def calculate_v21_weighted_macro_multiplier(
    macro_results: list[V21MacroResult],
) -> tuple[float, float]:
    """Ritorna (multiplier, weight_sum) usando solo macro predittive 1-9."""
    predictive = [m for m in macro_results if m.key in PREDICTIVE_MACRO_KEYS and not m.is_quality_only]
    weight_sum = sum(float(m.macro_weight) for m in predictive)
    if weight_sum <= 0:
        return 1.0, 0.0
    weighted = sum(float(m.macro_index) * float(m.macro_weight) for m in predictive)
    multiplier = weighted / weight_sum
    multiplier = max(FINAL_MULTIPLIER_MIN, min(FINAL_MULTIPLIER_MAX, multiplier))
    return round(multiplier, 4), weight_sum


def calculate_v21_base_anchor_sot(
    *,
    team_sot_for: float | None,
    opponent_sot_conceded: float | None,
) -> tuple[float | None, list[str]]:
    from app.services.predictions_v21.v21_constants import (
        ANCHOR_OPP_SOT_CONCEDED_WEIGHT,
        ANCHOR_TEAM_SOT_WEIGHT,
    )

    warnings: list[str] = []
    if team_sot_for is None and opponent_sot_conceded is None:
        return None, ["Anchor SOT: nessuna media squadra o avversario disponibile"]
    if team_sot_for is None:
        warnings.append("Anchor SOT: media SOT fatti squadra mancante, uso solo avversario")
        anchor = float(opponent_sot_conceded or 0.0)
    elif opponent_sot_conceded is None:
        warnings.append("Anchor SOT: media SOT concessi avversario mancante, uso solo squadra")
        anchor = float(team_sot_for)
    else:
        anchor = (
            ANCHOR_TEAM_SOT_WEIGHT * float(team_sot_for)
            + ANCHOR_OPP_SOT_CONCEDED_WEIGHT * float(opponent_sot_conceded)
        )
    return max(0.0, round(anchor, 4)), warnings


def calculate_v21_expected_sot(
    *,
    base_anchor_sot: float | None,
    weighted_macro_multiplier: float,
) -> float | None:
    if base_anchor_sot is None:
        return None
    return max(0.0, round(float(base_anchor_sot) * float(weighted_macro_multiplier), 4))
