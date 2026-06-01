"""Test risoluzione summary da fixture persistiti."""

from __future__ import annotations

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.services.backtest.round_analysis_summary_resolver import (
    advice_bucket,
    build_round_model_chips,
    is_advised_label,
    is_summary_usable,
    resolve_model_summary,
)

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT


def _row(advice: str = "GIOCA", outcome: str = "WIN") -> dict:
    return {
        "status": "ok",
        "actual_total_sot": 10,
        "models_json": {
            V11: {
                "status": "ok",
                "predicted_total_sot": 9.5,
                "aggressive_advice": advice,
                "aggressive_outcome": outcome,
                "cautious_advice": advice,
                "cautious_outcome": outcome,
            },
        },
        "explanation_json": {},
    }


def test_legacy_play_label_is_advised():
    assert is_advised_label("play")
    assert advice_bucket("play") == "GIOCA"


def test_empty_summary_rebuilt_from_fixtures():
    rows = [_row()]
    summary, source = resolve_model_summary(model_summary={}, rows=rows, model_keys=[V11])
    assert source == "rebuilt_from_fixtures"
    assert summary[V11]["predictions_available"] == 1


def test_chips_not_dash_when_outcomes_exist():
    rows = [_row("play", "WIN"), _row("play", "LOSS")]
    chips = build_round_model_chips(rows, [V11])
    assert "—" not in chips[V11]["cautious_display"]
    assert "—" not in chips[V11]["aggressive_display"]


def test_is_summary_usable_false_when_empty():
    assert not is_summary_usable({}, [_row()], [V11])
