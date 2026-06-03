"""Test spiegazioni umane v3.0 (pre-match, anti-leakage)."""

from __future__ import annotations

from app.services.backtest.sot_v30_human_explanation import (
    build_human_explanation,
    extract_important_absence_names,
    injury_phrase,
)
from app.services.backtest.sot_v30_value_selector_logic import select_value_pick
from app.services.backtest.sot_v30_value_selector_service import SotV30ValueSelectorService


def _genoa_ctx(**overrides) -> dict:
    base = {
        "v1_1": {"predicted_total_sot": 7.55, "cautious_advice": "GIOCA", "cautious_line": 6.5},
        "v2_1": {
            "predicted_total_sot": 7.8533,
            "cautious_advice": "GIOCA",
            "cautious_line": 6.5,
            "warnings": ["top_shooter_only_bench"],
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


def test_genoa_style_gioca_human_explanation():
    ctx = _genoa_ctx()
    sel, trace = select_value_pick(ctx)
    assert sel.decision in ("GIOCA", "BORDERLINE")
    assert sel.line == 6.5

    human = build_human_explanation(ctx, sel, trace)
    assert "6.5" in human["italian_text"] or "6,5" in human["italian_text"]
    assert "7.55" in human["italian_text"] or "7,55" in human["italian_text"]
    assert human["short_reason"]
    assert "outcome" not in human["italian_text"].lower()
    assert "win" not in human["italian_text"].lower().split()
    data = human["data_used"]
    assert data["v1_1_predicted_total_sot"] == 7.55
    assert abs(float(data["v2_1_predicted_total_sot"]) - 7.8533) < 0.01


def test_no_bet_v11_too_low_for_75_mentions_prudence():
    ctx = _genoa_ctx(
        v2_1={
            "predicted_total_sot": 8.6,
            "cautious_advice": "GIOCA",
            "cautious_line": 7.5,
            "warnings": [],
            "confidence": "medium",
            "sample_bucket": "stable_sample",
        },
        v1_1={"predicted_total_sot": 7.5, "cautious_advice": "GIOCA", "cautious_line": 6.5},
        macros={
            "weighted_macro_multiplier_avg": 1.02,
            "chance_quality_avg": 1.05,
            "pace_control_avg": 1.04,
            "lineups_avg": 0.99,
            "injuries_unavailable_avg": 0.92,
            "player_layer_avg": 1.02,
            "offensive_production_avg": 1.04,
        },
    )
    sel, trace = select_value_pick(ctx)
    if sel.decision != "NO_BET":
        return
    human = build_human_explanation(ctx, sel, trace)
    text = (human["italian_text"] + human["decision_reason"]).lower()
    assert "v1.1" in text or "prudent" in text or "7.5" in text


def test_human_explanation_never_uses_outcome_in_input():
    ctx = _genoa_ctx(actual_total_sot=12, outcome="WIN")
    try:
        from app.services.backtest.sot_v30_value_selector_logic import guard_no_leakage

        guard_no_leakage(ctx)
        assert False, "expected leakage guard"
    except ValueError:
        pass

    sel, trace = select_value_pick(_genoa_ctx())
    human = build_human_explanation(_genoa_ctx(), sel, trace)
    for forbidden in ("ha vinto", "ha perso", "risultato reale", "actual_total"):
        assert forbidden not in human["italian_text"].lower()


def test_injury_phrase_tiers():
    assert "non sembrano penalizzare" in injury_phrase(0.92, 1.0)
    assert "compensa" in injury_phrase(0.88, 1.05)
    assert "riducono" in injury_phrase(0.80, 0.95)


def test_extract_important_absence_names_from_explanation():
    expl = {
        "home": {
            "macros": [
                {
                    "key": "injuries_unavailable",
                    "details": {
                        "important_absences": [
                            {"player_name": "Retegui"},
                            {"player_name": "Leao"},
                        ],
                    },
                },
            ],
        },
    }
    names = extract_important_absence_names(expl)
    assert "Retegui" in names
    assert "Leao" in names


def test_build_selection_includes_human_explanation(monkeypatch):
    """Integrazione: trace_summary contiene human_explanation dopo build_selection."""

    class FakeFixture:
        id = 364

    class FakeDb:
        pass

    v11 = {"predicted_total_sot": 7.55, "cautious_advice": "GIOCA", "cautious_line": 6.5}
    v21 = {
        "predicted_total_sot": 7.85,
        "cautious_advice": "GIOCA",
        "cautious_line": 6.5,
        "warnings": [],
        "confidence": "medium",
        "sample_bucket": "stable_sample",
    }

    payload, trace_summary = SotV30ValueSelectorService().build_selection(
        FakeDb(),
        fixture=FakeFixture(),
        competition_id=1,
        mode="backtest",
        cutoff_time=None,
        v11_block=v11,
        v21_block=v21,
        explanation_v21=None,
        data_quality={"mapping": "ok", "lineup": "ok"},
    )
    assert "human_explanation" in payload
    assert payload["human_explanation"]["italian_text"]
    assert trace_summary["v1_1_predicted_total"] == 7.55
    assert trace_summary["v2_1_predicted_total"] == 7.85
    assert trace_summary["human_explanation"]["short_reason"]
