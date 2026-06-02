"""Logica v3.0 SOT Value Selector (solo pre-match, anti-leakage)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Decision = Literal["GIOCA", "NO_BET", "BORDERLINE"]
ConfidenceTier = Literal["strong", "medium", "weak", "no_bet"]
Profile = Literal["safe_6_5", "premium_7_5", "no_bet"]


FORBIDDEN_INPUT_FIELDS = frozenset(
    {
        "actual_total_sot",
        "actual_home_sot",
        "actual_away_sot",
        "outcome",
        "win",
        "loss",
        "actual_bucket",
        "final_score",
        "score",
    },
)


@dataclass(frozen=True)
class V30Selection:
    decision: Decision
    side: Literal["OVER"] = "OVER"
    line: float | None = None
    profile: Profile = "no_bet"
    confidence_tier: ConfidenceTier = "no_bet"
    reason_codes: list[str] = None  # type: ignore[assignment]
    no_bet_reasons: list[str] = None  # type: ignore[assignment]

    def as_json(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "side": self.side,
            "line": self.line,
            "profile": self.profile,
            "confidence_tier": self.confidence_tier,
            "reason_codes": list(self.reason_codes or []),
            "no_bet_reasons": list(self.no_bet_reasons or []),
        }


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return None


def _is_low_confidence(conf: Any) -> bool:
    return str(conf or "").strip().lower() == "low"


def _warning_count(warnings: Any) -> int:
    if not warnings:
        return 0
    if isinstance(warnings, list):
        return len(warnings)
    return 1


def _macro(macros: dict[str, Any], key: str) -> float | None:
    return _num((macros or {}).get(key))


def guard_no_leakage(pre_match_context: dict[str, Any]) -> None:
    present = sorted(set(pre_match_context.keys()) & set(FORBIDDEN_INPUT_FIELDS))
    if present:
        raise ValueError(f"v30_leakage_forbidden_fields_present:{','.join(present)}")


def select_value_pick(pre_match_context: dict[str, Any]) -> tuple[V30Selection, dict[str, Any]]:
    """
    Seleziona una giocata Over SOT (6.5/7.5) o NO_BET/BORDERLINE usando solo input pre-match.

    Ritorna (selection, debug_trace).
    """
    guard_no_leakage(pre_match_context)

    v21 = pre_match_context.get("v2_1") or {}
    v11 = pre_match_context.get("v1_1") or {}
    macros = dict(pre_match_context.get("macros") or {})

    v21_pt = _num(v21.get("predicted_total_sot"))
    v11_pt = _num(v11.get("predicted_total_sot"))
    v21_line = _num(v21.get("cautious_line"))
    v21_adv = str(v21.get("cautious_advice") or "")
    v11_adv = str(v11.get("cautious_advice") or "")

    warnings = list(v21.get("warnings") or [])
    warning_count = _warning_count(warnings)
    confidence = v21.get("confidence")
    sample_bucket = v21.get("sample_bucket")
    fallback_count = int(pre_match_context.get("fallback_count") or 0)
    data_quality = dict(pre_match_context.get("data_quality") or {})

    reason_codes: list[str] = []
    no_bet: list[str] = []

    trace = {
        "inputs": {
            "v21_predicted_total": v21_pt,
            "v11_predicted_total": v11_pt,
            "v21_cautious_line": v21_line,
            "v21_cautious_advice": v21_adv,
            "v11_cautious_advice": v11_adv,
            "warning_count": warning_count,
            "confidence": str(confidence) if confidence is not None else None,
            "sample_bucket": sample_bucket,
            "fallback_count": fallback_count,
            "data_quality": data_quality,
        },
        "macro_snapshot": {
            k: macros.get(k)
            for k in (
                "weighted_macro_multiplier_avg",
                "offensive_production_avg",
                "opponent_defensive_resistance_avg",
                "split_avg",
                "recent_form_avg",
                "chance_quality_avg",
                "player_layer_avg",
                "lineups_avg",
                "injuries_unavailable_avg",
                "pace_control_avg",
            )
        },
    }

    # --- Guard rail (availability) ---
    if v21_pt is None or v21_line is None or not str(v21_adv):
        return (
            V30Selection(
                decision="NO_BET",
                line=None,
                profile="no_bet",
                confidence_tier="no_bet",
                reason_codes=[],
                no_bet_reasons=["V21_NOT_AVAILABLE"],
            ),
            {**trace, "decision_path": ["V21_NOT_AVAILABLE"]},
        )

    # line exclusions
    if v21_line >= 8.5:
        return (
            V30Selection(
                decision="NO_BET",
                line=None,
                profile="no_bet",
                confidence_tier="no_bet",
                reason_codes=[],
                no_bet_reasons=["LINE_TOO_HIGH"],
            ),
            {**trace, "decision_path": ["LINE_TOO_HIGH"]},
        )
    if v21_line == 5.5:
        return (
            V30Selection(
                decision="NO_BET",
                line=None,
                profile="no_bet",
                confidence_tier="no_bet",
                reason_codes=[],
                no_bet_reasons=["LINE_5_5_EXCLUDED"],
            ),
            {**trace, "decision_path": ["LINE_5_5_EXCLUDED"]},
        )

    # quality / fallback / warnings
    if warning_count >= 5:
        no_bet.append("TOO_MANY_WARNINGS")
    if fallback_count >= 6:
        no_bet.append("FALLBACK_TOO_HIGH")
    if str(data_quality.get("mapping") or "").lower() == "missing":
        no_bet.append("DATA_QUALITY_LOW")

    # macro overheat
    wmm = _macro(macros, "weighted_macro_multiplier_avg")
    cq = _macro(macros, "chance_quality_avg")
    pace = _macro(macros, "pace_control_avg")
    if wmm is not None and wmm > 1.15:
        no_bet.append("MACRO_OVERHEAT")
    if cq is not None and pace is not None and cq > 1.15 and pace > 1.12:
        no_bet.append("MACRO_OVERHEAT")

    # v21 vs v11 gap
    if v11_pt is not None and (v21_pt - v11_pt) > 1.30:
        no_bet.append("V21_V11_GAP_TOO_HIGH")

    if no_bet:
        return (
            V30Selection(
                decision="NO_BET",
                line=None,
                profile="no_bet",
                confidence_tier="no_bet",
                reason_codes=[],
                no_bet_reasons=sorted(list(dict.fromkeys(no_bet))),
            ),
            {**trace, "decision_path": sorted(list(dict.fromkeys(no_bet)))},
        )

    # --- Line 6.5 (balanced) ---
    if v21_line == 6.5:
        reason_codes.append("V21_LINE_6_5")
        reason_codes.append("SAFE_LINE")

        if v21_pt < 7.40:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["V21_PRED_TOO_LOW"],
                ),
                {**trace, "decision_path": ["V21_PRED_TOO_LOW"]},
            )
        if v21_pt > 8.40:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["V21_PRED_TOO_HIGH"],
                ),
                {**trace, "decision_path": ["V21_PRED_TOO_HIGH"]},
            )

        lineup = _macro(macros, "lineups_avg")
        if lineup is not None and lineup < 0.95:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["LINEUP_WEAK"],
                ),
                {**trace, "decision_path": ["LINEUP_WEAK"]},
            )
        reason_codes.append("LINEUP_OK")

        injuries = _macro(macros, "injuries_unavailable_avg")
        player_layer = _macro(macros, "player_layer_avg")
        if injuries is not None and injuries < 0.85 and (player_layer is None or player_layer < 1.00):
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["INJURY_PLAYER_LAYER_WEAK"],
                ),
                {**trace, "decision_path": ["INJURY_PLAYER_LAYER_WEAK"]},
            )
        reason_codes.append("INJURY_INDEX_OK")

        if _is_low_confidence(confidence):
            reason_codes.append("MEDIUM_CONFIDENCE")
            tier: ConfidenceTier = "weak"
            decision: Decision = "BORDERLINE"
        else:
            tier = "weak"
            decision = "GIOCA"

        # tier upgrade on consensus
        if str(v21_adv).upper() == "GIOCA" and str(v11_adv).upper() == "GIOCA":
            reason_codes.append("V11_V21_CONSENSUS")
            tier = "strong" if decision == "GIOCA" else "medium"
        else:
            tier = "medium" if decision == "GIOCA" else "weak"

        reason_codes.append("MACRO_NOT_OVERHEATED")

        return (
            V30Selection(
                decision=decision,
                line=6.5,
                profile="safe_6_5",
                confidence_tier=tier,
                reason_codes=reason_codes,
                no_bet_reasons=[],
            ),
            {**trace, "decision_path": ["SAFE_6_5"], "reason_codes": reason_codes, "confidence_tier": tier},
        )

    # --- Line 7.5 (premium) ---
    if v21_line == 7.5:
        if str(v21_adv).upper() != "GIOCA":
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["V21_NOT_GIOCA"],
                ),
                {**trace, "decision_path": ["V21_NOT_GIOCA"]},
            )
        if str(v11_adv).upper() != "GIOCA":
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["V11_REQUIRED_FOR_7_5"],
                ),
                {**trace, "decision_path": ["V11_REQUIRED_FOR_7_5"]},
            )
        if v21_pt < 8.50:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["V21_PRED_TOO_LOW_FOR_7_5"],
                ),
                {**trace, "decision_path": ["V21_PRED_TOO_LOW_FOR_7_5"]},
            )
        if v11_pt is None or v11_pt < 7.80:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["V11_PRED_TOO_LOW_FOR_7_5"],
                ),
                {**trace, "decision_path": ["V11_PRED_TOO_LOW_FOR_7_5"]},
            )
        if _is_low_confidence(confidence):
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["CONFIDENCE_LOW"],
                ),
                {**trace, "decision_path": ["CONFIDENCE_LOW"]},
            )
        if v11_pt is not None and abs(v21_pt - v11_pt) > 1.25:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["V21_V11_GAP_TOO_HIGH"],
                ),
                {**trace, "decision_path": ["V21_V11_GAP_TOO_HIGH"]},
            )

        wmm = _macro(macros, "weighted_macro_multiplier_avg")
        if wmm is None or wmm < 0.95 or wmm > 1.08:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["MACRO_CONTROLLED_FAIL"],
                ),
                {**trace, "decision_path": ["MACRO_CONTROLLED_FAIL"]},
            )
        if cq is not None and cq > 1.12:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["NO_OVERHEAT_FAIL"],
                ),
                {**trace, "decision_path": ["NO_OVERHEAT_FAIL"]},
            )
        if pace is not None and pace > 1.10:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["NO_OVERHEAT_FAIL"],
                ),
                {**trace, "decision_path": ["NO_OVERHEAT_FAIL"]},
            )
        off = _macro(macros, "offensive_production_avg")
        if off is not None and off > 1.15:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["OFFENSE_TOO_HIGH"],
                ),
                {**trace, "decision_path": ["OFFENSE_TOO_HIGH"]},
            )
        lineup = _macro(macros, "lineups_avg")
        if lineup is not None and lineup < 0.98:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["LINEUP_WEAK"],
                ),
                {**trace, "decision_path": ["LINEUP_WEAK"]},
            )
        injuries = _macro(macros, "injuries_unavailable_avg")
        if injuries is not None and injuries < 0.90:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["INJURIES_LOW"],
                ),
                {**trace, "decision_path": ["INJURIES_LOW"]},
            )
        if warning_count > 3:
            return (
                V30Selection(
                    decision="NO_BET",
                    line=None,
                    profile="no_bet",
                    confidence_tier="no_bet",
                    reason_codes=[],
                    no_bet_reasons=["TOO_MANY_WARNINGS"],
                ),
                {**trace, "decision_path": ["TOO_MANY_WARNINGS"]},
            )

        reason_codes = [
            "PREMIUM_7_5",
            "V11_V21_CONSENSUS",
            "STRONG_PREDICTION",
            "MACRO_CONTROLLED",
            "NO_OVERHEAT",
            "LINEUP_OK",
        ]

        return (
            V30Selection(
                decision="GIOCA",
                line=7.5,
                profile="premium_7_5",
                confidence_tier="strong",
                reason_codes=reason_codes,
                no_bet_reasons=[],
            ),
            {**trace, "decision_path": ["PREMIUM_7_5"], "reason_codes": reason_codes, "confidence_tier": "strong"},
        )

    return (
        V30Selection(
            decision="NO_BET",
            line=None,
            profile="no_bet",
            confidence_tier="no_bet",
            reason_codes=[],
            no_bet_reasons=["UNSUPPORTED_LINE"],
        ),
        {**trace, "decision_path": ["UNSUPPORTED_LINE"]},
    )

