"""Test v3.0 value selector (anti-leakage + regole base)."""

from __future__ import annotations

from app.services.backtest.sot_v30_value_selector_logic import (
    FORBIDDEN_INPUT_FIELDS,
    guard_no_leakage,
    select_value_pick,
)


def _ctx(**overrides) -> dict:
    base = {
        "v1_1": {"predicted_total_sot": 7.8, "cautious_advice": "GIOCA", "cautious_line": 6.5},
        "v2_1": {
            "predicted_total_sot": 7.9,
            "cautious_advice": "GIOCA",
            "cautious_line": 6.5,
            "warnings": [],
            "confidence": "medium",
            "sample_bucket": "stable_sample",
        },
        "macros": {
            "weighted_macro_multiplier_avg": 1.0,
            "chance_quality_avg": 1.0,
            "pace_control_avg": 1.0,
            "lineups_avg": 0.98,
            "injuries_unavailable_avg": 0.95,
            "player_layer_avg": 1.05,
        },
        "fallback_count": 0,
        "data_quality": {"mapping": "ok", "lineup": "ok"},
    }
    base.update(overrides)
    return base


def test_guard_rejects_forbidden_fields():
    for field in FORBIDDEN_INPUT_FIELDS:
        ctx = _ctx()
        ctx[field] = 10
        try:
            guard_no_leakage(ctx)
            assert False, f"expected leakage error for {field}"
        except ValueError as exc:
            assert "v30_leakage_forbidden_fields_present" in str(exc)


def test_safe_65_play():
    sel, _trace = select_value_pick(_ctx())
    assert sel.decision in ("GIOCA", "BORDERLINE")
    assert sel.line == 6.5


def test_excludes_line_85_plus():
    sel, _trace = select_value_pick(_ctx(v2_1={**_ctx()["v2_1"], "cautious_line": 8.5}))
    assert sel.decision == "NO_BET"
    assert "LINE_TOO_HIGH" in (sel.no_bet_reasons or [])


def test_premium_75_requires_consensus_and_thresholds():
    ctx = _ctx(
        v2_1={**_ctx()["v2_1"], "cautious_line": 7.5, "predicted_total_sot": 8.6},
        v1_1={**_ctx()["v1_1"], "predicted_total_sot": 7.9, "cautious_advice": "GIOCA"},
        macros={
            **_ctx()["macros"],
            "weighted_macro_multiplier_avg": 1.02,
            "chance_quality_avg": 1.08,
            "pace_control_avg": 1.06,
            "lineups_avg": 0.99,
            "injuries_unavailable_avg": 0.92,
            "offensive_production_avg": 1.05,
        },
    )
    sel, _trace = select_value_pick(ctx)
    assert sel.decision == "GIOCA"
    assert sel.line == 7.5

