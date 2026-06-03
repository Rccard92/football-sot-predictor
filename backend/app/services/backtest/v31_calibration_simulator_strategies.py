"""Cinque strategie sperimentali simulatore calibrazione v3.1."""

from __future__ import annotations

from typing import Any, Literal

from app.services.backtest.v31_calibration_simulator_base_sot import (
    CORE_BASE_WEIGHTS,
    DEFAULT_BASE_WEIGHTS,
    EQUAL_BASE_WEIGHTS,
)
from app.services.backtest.v31_calibration_simulator_confidence import compute_confidence_tier
from app.services.backtest.v31_calibration_simulator_explanations import build_human_explanation
from app.services.backtest.v31_calibration_simulator_feature_engine import extract_fixture_signals
from app.services.backtest.v31_calibration_simulator_predictor import predict_for_strategy

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
    "v31_equal_weights": "Base SOT uniforme sui componenti statistici; selector moderato.",
    "v31_core_sot_xg": "Peso alto su SOT, xG e volume; context multiplier più piatto.",
    "v31_context_adjusted": "Base statistica + moltiplicatori contestuali cappati.",
    "v31_conservative_selector": "Stessa predizione del contesto; selector severo.",
    "v31_balanced_selector": "Stessa predizione del contesto; selector più aperto.",
}

SelectorMode = Literal["moderate", "conservative", "balanced"]


def _prob(pred: dict[str, Any], line: float) -> float:
    key = f"estimated_probability_over_{str(line).replace('.', '_')}"
    return float(pred.get(key) or 0.0)


def _pick_line_and_decision(
    pred: dict[str, Any],
    signals: Any,
    *,
    mode: SelectorMode,
) -> tuple[float | None, str, list[str]]:
    reasons: list[str] = []
    total = pred.get("predicted_total_sot")
    if total is None:
        reasons.append("V31_MISSING_FEATURES")
        return None, "NO_BET", reasons

    mu = float(total)
    dq = signals.data_quality
    if str(dq.get("team_stats_status") or signals.team_stats_status) not in ("ok", "partial"):
        reasons.extend(["V31_DATA_QUALITY_WEAK", "V31_PROBABILITY_BELOW_THRESHOLD"])
        return None, "NO_BET", reasons

    candidates: list[tuple[float, str, list[str]]] = []

    def _try(line: float, p_min: float, min_margin: float, need_high: bool, code: str) -> None:
        p = _prob(pred, line)
        margin = mu - line
        tier = compute_confidence_tier(
            signals,
            predicted_total=mu,
            selected_line=line,
        )
        if margin < min_margin:
            return
        if p < p_min:
            return
        if need_high and tier != "high":
            return
        if mode == "conservative" and tier == "low":
            return
        r = [code, "V31_MARGIN_OK"]
        if tier == "high":
            r.append("V31_CONFIDENCE_HIGH")
        elif tier == "medium":
            r.append("V31_CONFIDENCE_MEDIUM")
        if dq.get("team_stats_status") == "ok":
            r.append("V31_DATA_QUALITY_OK")
        candidates.append((line, tier, r))

    if mode == "conservative":
        if mu >= 9.2:
            _try(8.5, 0.56, 0.9, True, "V31_OVER_8_5_PREMIUM")
        _try(7.5, 0.65, 0.7, True, "V31_OVER_7_5_PREMIUM")
        _try(6.5, 0.72, 0.5, False, "V31_OVER_6_5_PROB_OK")
    elif mode == "balanced":
        _try(8.5, 0.53, 0.5, False, "V31_OVER_8_5_PREMIUM")
        _try(7.5, 0.60, 0.4, False, "V31_OVER_7_5_PREMIUM")
        _try(6.5, 0.65, 0.35, False, "V31_OVER_6_5_PROB_OK")
    else:
        _try(7.5, 0.62, 0.45, False, "V31_OVER_7_5_PREMIUM")
        _try(6.5, 0.68, 0.30, False, "V31_OVER_6_5_PROB_OK")

    if not candidates:
        p65 = _prob(pred, 6.5)
        margin65 = mu - 6.5
        if p65 >= 0.65 and margin65 >= 0.2:
            tier = compute_confidence_tier(signals, predicted_total=mu, selected_line=6.5)
            if tier != "low":
                reasons.extend(["V31_BORDERLINE_SIGNAL", "V31_OVER_6_5_PROB_OK"])
                return 6.5, "BORDERLINE", reasons
        if margin65 < 0.4:
            reasons.append("V31_MARGIN_TOO_LOW")
        if p65 < 0.65:
            reasons.append("V31_PROBABILITY_BELOW_THRESHOLD")
        if signals.warning_count > 4:
            reasons.append("V31_DATA_QUALITY_WEAK")
        tier_probe = compute_confidence_tier(signals, predicted_total=mu, selected_line=6.5)
        if tier_probe == "low":
            reasons.append("V31_LOW_CONFIDENCE")
        if _prob(pred, 7.5) < 0.55 and mu < 8.0:
            reasons.append("V31_LINE_TOO_RISKY")
        return None, "NO_BET", list(dict.fromkeys(reasons))

    best = max(candidates, key=lambda c: (c[0], _prob(pred, c[0])))
    line, tier_used, r = best
    tier = compute_confidence_tier(signals, predicted_total=mu, selected_line=line)
    if mode == "conservative" and tier == "low":
        reasons.extend(["V31_LOW_CONFIDENCE", "V31_PROBABILITY_BELOW_THRESHOLD"])
        return None, "NO_BET", reasons

    decision = "GIOCA"
    margin = mu - float(line)
    prob_line = _prob(pred, line)
    if mode == "moderate" and tier == "medium" and prob_line < 0.72:
        decision = "BORDERLINE"
        r.append("V31_BORDERLINE_SIGNAL")
    elif mode == "balanced" and tier == "low":
        decision = "BORDERLINE"
        r.append("V31_BORDERLINE_SIGNAL")
    elif margin < 0.45 and prob_line < 0.62:
        decision = "BORDERLINE"
        r.append("V31_BORDERLINE_SIGNAL")

    return line, decision, list(dict.fromkeys(r))


def _strategy_config(key: str) -> dict[str, Any]:
    if key == "v31_equal_weights":
        return {
            "prediction_key": key,
            "base_weights": EQUAL_BASE_WEIGHTS,
            "selector_mode": "moderate",
        }
    if key == "v31_core_sot_xg":
        return {
            "prediction_key": "v31_core_sot_xg",
            "base_weights": CORE_BASE_WEIGHTS,
            "selector_mode": "moderate",
        }
    if key == "v31_context_adjusted":
        return {
            "prediction_key": "v31_context_adjusted",
            "base_weights": DEFAULT_BASE_WEIGHTS,
            "selector_mode": "moderate",
        }
    if key == "v31_conservative_selector":
        return {
            "prediction_key": "v31_context_adjusted",
            "base_weights": DEFAULT_BASE_WEIGHTS,
            "selector_mode": "conservative",
        }
    if key == "v31_balanced_selector":
        return {
            "prediction_key": "v31_context_adjusted",
            "base_weights": DEFAULT_BASE_WEIGHTS,
            "selector_mode": "balanced",
        }
    raise ValueError(f"Unknown strategy: {key}")


def simulate_row(row: dict[str, Any], strategy_key: str) -> dict[str, Any] | None:
    signals = extract_fixture_signals(row)
    if signals is None:
        return None
    cfg = _strategy_config(strategy_key)
    pred = predict_for_strategy(signals, cfg["prediction_key"])
    line, decision, reason_codes = _pick_line_and_decision(
        pred,
        signals,
        mode=cfg["selector_mode"],
    )
    tier = compute_confidence_tier(
        signals,
        predicted_total=pred.get("predicted_total_sot"),
        selected_line=line,
    )
    if decision == "NO_BET":
        tier = "low"

    meta = row.get("metadata") or {}
    target = row.get("target") or {}
    actual = target.get("actual_total_sot")
    outcome = None
    if decision == "GIOCA" and line is not None and actual is not None:
        outcome = "WIN" if int(actual) > int(line) else "LOSS"

    prob_pct = None
    if line is not None:
        prob_pct = 100.0 * _prob(pred, line)

    human = build_human_explanation(
        decision=decision,
        selected_line=line,
        reason_codes=reason_codes,
        predicted_total=pred.get("predicted_total_sot"),
        prob_pct=prob_pct,
        home_name=signals.home_team_name,
        away_name=signals.away_team_name,
    )

    trace = pred.get("trace") or {}
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
        "estimated_probability_over_9_5": pred.get("estimated_probability_over_9_5"),
        "estimated_probability_over_10_5": pred.get("estimated_probability_over_10_5"),
        "estimated_probability_over_11_5": pred.get("estimated_probability_over_11_5"),
        "selected_line": line,
        "decision": decision,
        "confidence_tier": tier,
        "reason_codes": reason_codes,
        "human_explanation": human,
        "missing_fields": pred.get("missing_fields") or signals.missing_fields,
        "actual_total_sot": actual,
        "outcome": outcome,
        "trace": {
            "strategy_key": strategy_key,
            "prediction_key": cfg["prediction_key"],
            "selector_mode": cfg["selector_mode"],
            "home_base_sot": pred.get("home_base_sot"),
            "away_base_sot": pred.get("away_base_sot"),
            "home_context_multiplier": pred.get("home_context_multiplier"),
            "away_context_multiplier": pred.get("away_context_multiplier"),
            "sigma_total": pred.get("sigma_total"),
            **trace,
        },
    }


def get_strategy_weights_payload(strategy_key: str) -> dict[str, Any]:
    cfg = _strategy_config(strategy_key)
    from app.services.backtest.v31_calibration_simulator_base_sot import (
        CONTEXT_MACRO_WEIGHTS,
    )

    return {
        "macro_areas": cfg.get("base_weights") or DEFAULT_BASE_WEIGHTS,
        "context_macro_weights": CONTEXT_MACRO_WEIGHTS,
        "selector_mode": cfg["selector_mode"],
        "prediction_key": cfg["prediction_key"],
    }
