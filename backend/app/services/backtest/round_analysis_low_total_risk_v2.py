"""Indicatore diagnostico low_total_risk_v2 (solo simulatore, non modifica predizioni)."""

from __future__ import annotations

from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def compute_low_total_risk_v2_score(fx: dict[str, Any]) -> int:
    score = 0
    macros = fx.get("v21_macros") or {}
    v11_block = (fx.get("models") or {}).get(V11) or {}
    v21_block = (fx.get("models") or {}).get(V21) or {}
    warnings = list(v21_block.get("warnings") or [])
    warning_count = len(warnings)

    wmm = macros.get("weighted_macro_multiplier_avg")
    if wmm is not None and float(wmm) > 1.15:
        score += 2

    cq = macros.get("chance_quality_avg")
    pace = macros.get("pace_control_avg")
    if cq is not None and pace is not None and float(cq) > 1.15 and float(pace) > 1.10:
        score += 2

    off = macros.get("offensive_production_avg")
    v11_pt = v11_block.get("predicted_total_sot")
    if off is not None and v11_pt is not None and float(off) > 1.15 and float(v11_pt) < 7.60:
        score += 1

    v21_pt = v21_block.get("predicted_total_sot")
    if v21_pt is not None and v11_pt is not None and float(v21_pt) - float(v11_pt) > 1.25:
        score += 1

    if warning_count >= 4:
        score += 1

    if str(v21_block.get("confidence") or "").lower() == "low":
        score += 1

    unav = macros.get("injuries_unavailable_avg")
    if unav is not None and float(unav) < 0.88:
        score += 1

    lu = macros.get("lineups_avg")
    if lu is not None and float(lu) < 0.95:
        score += 1

    pl = macros.get("player_layer_avg")
    if pl is not None and float(pl) < 1.00:
        score += 1

    split_st = fx.get("split_status") or "missing"
    if split_st in ("missing", "partial_low_sample"):
        score += 1

    return score


def low_total_risk_v2_bucket(score: int) -> str:
    if score <= 1:
        return "low"
    if score <= 3:
        return "medium"
    return "high"
