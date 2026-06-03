"""Cinque strategie sperimentali simulatore calibrazione v3.1."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_calibration_simulator_explanations import build_human_explanation
from app.services.backtest.v31_calibration_simulator_feature_engine import (
    V31_MACRO_AREA_KEYS,
    extract_fixture_signals,
)
from app.services.backtest.v31_calibration_simulator_predictor import predict_sides

STRATEGY_KEYS = (
    "v31_equal_weights",
    "v31_core_sot_xg",
    "v31_context_adjusted",
    "v31_conservative_selector",
    "v31_balanced_selector",
)

STRATEGY_LABELS: dict[str, str] = {
    "v31_equal_weights": "v3.1 — Pesi uguali (10 macroaree)",
    "v31_core_sot_xg": "v3.1 — Core SOT/xG/volume",
    "v31_context_adjusted": "v3.1 — Contesto aggiustato",
    "v31_conservative_selector": "v3.1 — Selector conservativo",
    "v31_balanced_selector": "v3.1 — Selector bilanciato",
}

STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "v31_equal_weights": "Dieci macroaree con peso uguale; selezione linea per margine μ−linea.",
    "v31_core_sot_xg": "Peso alto su SOT, xG e volume; basso su player layer e assenze.",
    "v31_context_adjusted": "Base core con moltiplicatori su split, forma, player, assenze e qualità dato.",
    "v31_conservative_selector": "Gioca solo con dati OK, pochi warning, confidenza alta e P(Over 6.5) elevata.",
    "v31_balanced_selector": "Più aperto: ammette Over 7.5 con probabilità e margine sufficienti.",
}


def _equal_weights() -> dict[str, float]:
    w = 1.0 / len(V31_MACRO_AREA_KEYS)
    return {k: w for k in V31_MACRO_AREA_KEYS}


def _core_weights() -> dict[str, float]:
    return {
        "offensive_production_index": 0.18,
        "opponent_defensive_resistance_index": 0.16,
        "chance_quality_index": 0.16,
        "pace_control_index": 0.14,
        "home_away_split_index": 0.10,
        "recent_form_index": 0.08,
        "player_layer_index": 0.05,
        "injuries_unavailable_index": 0.05,
        "lineups_index": 0.04,
        "weighted_macro_multiplier": 0.04,
    }


def _confidence_tier(score: float) -> str:
    if score >= 0.72:
        return "high"
    if score >= 0.48:
        return "medium"
    return "low"


def _pick_line_and_decision(
    pred: dict[str, Any],
    signals: Any,
    *,
    min_p_65: float,
    min_p_75: float | None,
    max_warnings: int,
    require_confidence: str,
    allow_75: bool,
) -> tuple[float | None, str, list[str]]:
    reasons: list[str] = []
    total = pred.get("predicted_total_sot")
    if total is None:
        reasons.append("missing_features")
        return None, "NO_BET", reasons

    conf = signals.confidence_score
    tier = _confidence_tier(conf)
    if signals.warning_count > max_warnings:
        reasons.append("warnings_high")
        return None, "NO_BET", reasons + ["no_bet_quality"]
    if signals.team_stats_status not in ("ok", "partial"):
        reasons.append("data_quality_weak")
        return None, "NO_BET", reasons + ["no_bet_quality"]
    if len(signals.missing_fields) > 12:
        reasons.append("missing_features")

    p65 = pred.get("estimated_probability_over_6_5") or 0.0
    p75 = pred.get("estimated_probability_over_7_5") or 0.0
    margins = {
        6.5: float(total) - 6.5,
        7.5: float(total) - 7.5,
        8.5: float(total) - 8.5,
    }

    selected: float | None = None
    if allow_75 and p75 >= (min_p_75 or 0.52) and margins[7.5] >= 0.35:
        selected = 7.5
        reasons.extend(["balanced_opens_75", "prob_over_75_sufficient", "line_65_best_margin"])
    elif p65 >= min_p_65 and margins[6.5] >= 0.25:
        selected = 6.5
        reasons.extend(["prob_over_65_sufficient", "line_65_best_margin"])
    elif margins[6.5] >= 0.15 and p65 >= min_p_65 - 0.06:
        selected = 6.5
        reasons.append("borderline_probability")

    if selected is None:
        if margins[7.5] < 0.35:
            reasons.append("line_75_excluded_margin")
        if margins[8.5] < 0.5:
            reasons.append("line_85_excluded")
        reasons.append("no_bet_probability")
        return None, "NO_BET", reasons

    if require_confidence == "high" and tier != "high":
        reasons.append("confidence_low")
        if require_confidence == "high":
            reasons.append("conservative_threshold")
            return selected, "NO_BET", reasons + ["no_bet_quality"]

    if tier == "high":
        reasons.append("confidence_high")
    else:
        reasons.append("confidence_low")

    if float(total) >= 7.0:
        reasons.append("stable_sot_production")
    off_h = signals.home.macros.get("offensive_production_index")
    off_a = signals.away.macros.get("offensive_production_index")
    if off_h and off_a and float(off_h) >= 1.0 and float(off_a) >= 1.0:
        reasons.append("strong_offensive_macro")
    if signals.home.macros.get("home_away_split_index") and signals.away.macros.get("home_away_split_index"):
        reasons.append("home_away_split_supports")
    if signals.home.macros.get("recent_form_index") or signals.away.macros.get("recent_form_index"):
        reasons.append("recent_form_positive")
    if signals.home.macros.get("player_layer_index"):
        reasons.append("player_layer_ok")
    if signals.home.macros.get("injuries_unavailable_index"):
        reasons.append("absences_light")
    reasons.append("data_quality_ok")

    decision = "GIOCA"
    if tier != "high" and p65 < min_p_65 + 0.04:
        decision = "BORDERLINE"
        reasons.append("borderline_probability")

    return selected, decision, list(dict.fromkeys(reasons))


def _strategy_config(key: str) -> dict[str, Any]:
    if key == "v31_equal_weights":
        return {
            "macro_weights": _equal_weights(),
            "multipliers": {},
            "selector": {"min_p_65": 0.52, "min_p_75": None, "max_warnings": 8, "require_confidence": "medium", "allow_75": False},
        }
    if key == "v31_core_sot_xg":
        return {
            "macro_weights": _core_weights(),
            "multipliers": {},
            "selector": {"min_p_65": 0.52, "min_p_75": None, "max_warnings": 8, "require_confidence": "medium", "allow_75": False},
        }
    if key == "v31_context_adjusted":
        return {
            "macro_weights": _core_weights(),
            "multipliers": {
                "home_away_split": 1.05,
                "recent_form": 1.04,
                "player_layer": 1.03,
                "injuries_unavailable": 0.98,
                "data_quality": 1.0,
            },
            "selector": {"min_p_65": 0.54, "min_p_75": 0.50, "max_warnings": 6, "require_confidence": "medium", "allow_75": True},
        }
    if key == "v31_conservative_selector":
        return {
            "macro_weights": _core_weights(),
            "multipliers": {"home_away_split": 1.03, "recent_form": 1.02, "player_layer": 1.02, "injuries_unavailable": 0.99, "data_quality": 1.0},
            "selector": {"min_p_65": 0.58, "min_p_75": None, "max_warnings": 3, "require_confidence": "high", "allow_75": False},
        }
    if key == "v31_balanced_selector":
        return {
            "macro_weights": _core_weights(),
            "multipliers": {"home_away_split": 1.05, "recent_form": 1.04, "player_layer": 1.03, "injuries_unavailable": 0.98, "data_quality": 1.0},
            "selector": {"min_p_65": 0.52, "min_p_75": 0.52, "max_warnings": 6, "require_confidence": "medium", "allow_75": True},
        }
    raise ValueError(f"Unknown strategy: {key}")


def simulate_row(row: dict[str, Any], strategy_key: str) -> dict[str, Any] | None:
    signals = extract_fixture_signals(row)
    if signals is None:
        return None
    cfg = _strategy_config(strategy_key)
    pred = predict_sides(
        signals,
        macro_weights=cfg["macro_weights"],
        multipliers=cfg.get("multipliers"),
    )
    sel = cfg["selector"]
    line, decision, reason_codes = _pick_line_and_decision(
        pred,
        signals,
        min_p_65=sel["min_p_65"],
        min_p_75=sel.get("min_p_75"),
        max_warnings=sel["max_warnings"],
        require_confidence=sel["require_confidence"],
        allow_75=sel["allow_75"],
    )
    tier = _confidence_tier(signals.confidence_score)
    if decision == "NO_BET":
        tier = "low"

    meta = row.get("metadata") or {}
    target = row.get("target") or {}
    actual = target.get("actual_total_sot")
    outcome = None
    if decision == "GIOCA" and line is not None and actual is not None:
        outcome = "WIN" if int(actual) > int(line) else "LOSS"

    human = build_human_explanation(
        decision=decision,
        selected_line=line,
        reason_codes=reason_codes,
        predicted_total=pred.get("predicted_total_sot"),
        home_name=signals.home_team_name,
        away_name=signals.away_team_name,
    )

    return {
        "fixture_id": signals.fixture_id,
        "round_number": signals.round_number,
        "match": f"{signals.home_team_name} vs {signals.away_team_name}",
        "predicted_total_sot": pred.get("predicted_total_sot"),
        "predicted_home_sot": pred.get("predicted_home_sot"),
        "predicted_away_sot": pred.get("predicted_away_sot"),
        "estimated_probability_over_5_5": pred.get("estimated_probability_over_5_5"),
        "estimated_probability_over_6_5": pred.get("estimated_probability_over_6_5"),
        "estimated_probability_over_7_5": pred.get("estimated_probability_over_7_5"),
        "estimated_probability_over_8_5": pred.get("estimated_probability_over_8_5"),
        "selected_line": line,
        "decision": decision,
        "confidence_tier": tier,
        "reason_codes": reason_codes,
        "human_explanation": human,
        "missing_fields": signals.missing_fields,
        "actual_total_sot": actual,
        "outcome": outcome,
        "trace": {
            "macro_weights": cfg["macro_weights"],
            "multipliers": cfg.get("multipliers"),
            "selector_thresholds": sel,
            "macro_blend_home": pred.get("macro_blend_home"),
            "macro_blend_away": pred.get("macro_blend_away"),
            "confidence_score": signals.confidence_score,
            "warning_count": signals.warning_count,
        },
        "comparisons_snapshot": row.get("comparisons") if isinstance(row.get("comparisons"), dict) else None,
    }


def get_strategy_weights_payload(strategy_key: str) -> dict[str, Any]:
    cfg = _strategy_config(strategy_key)
    return {
        "macro_areas": cfg["macro_weights"],
        "multipliers": cfg.get("multipliers") or {},
        "selector_thresholds": cfg["selector"],
    }
