"""Test consiglio giocata pre-match Step H.1."""

from __future__ import annotations

from app.services.backtest.sot_pick_evaluation_logic import (
    DEFAULT_PICK_LINES,
    ConfidenceSignals,
    build_over_pick,
    evaluate_over_picks,
)
from app.services.backtest.sot_pick_play_advice_logic import (
    PlayAdviceConfig,
    PlayAdviceSignals,
    REASON_EARLY_SAMPLE,
    REASON_LOW_EDGE,
    compute_play_advice,
)

_LINES = list(DEFAULT_PICK_LINES)
_CONFIG = PlayAdviceConfig()
_SIGNALS = ConfidenceSignals(min_prior_matches=14, warnings_count=0, player_layer_neutral=False)


def _advice_signals(**kwargs) -> PlayAdviceSignals:
    base = {
        "min_prior_matches": 14,
        "warnings_count": 0,
        "sample_bucket": "stable_sample",
        "player_layer_fallback": False,
        "split_fallback": False,
        "pick_kind": "aggressive",
        "no_line_available": False,
        "no_lower_line": False,
    }
    base.update(kwargs)
    return PlayAdviceSignals(**base)


def test_milan_aggressive_no_play_cautious_play():
    aggressive, cautious, _ = evaluate_over_picks(
        8.63, _LINES, 14, cautious_drop_threshold=0.75, signals=_SIGNALS,
    )
    assert aggressive is not None
    assert round(aggressive.edge, 2) == 0.13
    assert aggressive.outcome == "win"

    agg_advice = compute_play_advice(
        aggressive,
        _advice_signals(pick_kind="aggressive"),
        _CONFIG,
    )
    assert agg_advice.play_advice == "no_play"
    assert agg_advice.play_advice_label == "NON GIOCARE"
    assert REASON_LOW_EDGE in agg_advice.advice_reasons

    assert cautious is not None
    assert cautious.line == 7.5
    assert round(cautious.edge, 2) == 1.13
    assert cautious.outcome == "win"

    caut_advice = compute_play_advice(
        cautious,
        _advice_signals(pick_kind="cautious"),
        _CONFIG,
    )
    assert caut_advice.play_advice == "play"
    assert caut_advice.play_advice_label == "GIOCA"


def test_early_sample_hard_block():
    pick = build_over_pick(
        7.5,
        8.0,
        None,
        confidence_kind="aggressive",
        signals=ConfidenceSignals(min_prior_matches=3, warnings_count=0, player_layer_neutral=False),
    )
    advice = compute_play_advice(
        pick,
        _advice_signals(
            min_prior_matches=3,
            sample_bucket="early_low_sample",
            pick_kind="aggressive",
        ),
        _CONFIG,
    )
    assert advice.play_advice == "no_play"
    assert REASON_EARLY_SAMPLE in advice.advice_reasons or "LOW_SAMPLE" in advice.advice_reasons


def test_no_line_available():
    advice = compute_play_advice(
        None,
        _advice_signals(no_line_available=True, pick_kind="aggressive"),
        _CONFIG,
    )
    assert advice.play_advice == "no_play"
    assert advice.advice_reasons[0] in ("NO_LINE_AVAILABLE", "NO_LOWER_LINE")


def test_advice_independent_of_outcome():
    pick_win = build_over_pick(8.5, 8.63, 14, confidence_kind="aggressive", signals=_SIGNALS)
    pick_none = build_over_pick(8.5, 8.63, None, confidence_kind="aggressive", signals=_SIGNALS)
    signals = _advice_signals(pick_kind="aggressive")
    advice_win = compute_play_advice(pick_win, signals, _CONFIG)
    advice_none = compute_play_advice(pick_none, signals, _CONFIG)
    assert advice_win.play_advice == advice_none.play_advice
    assert advice_win.advice_reasons == advice_none.advice_reasons
