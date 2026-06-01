"""Costruzione payload pick per analisi giornata (Step I)."""

from __future__ import annotations

from typing import Any

from app.schemas.backtest_sot_v21_preview import SotV21PreviewResponse
from app.services.backtest.sot_pick_evaluation_logic import (
    ConfidenceSignals,
    OverPickResult,
    evaluate_over_picks,
    sample_bucket_key,
)
from app.services.backtest.sot_pick_play_advice_logic import (
    PlayAdviceConfig,
    PlayAdviceResult,
    PlayAdviceSignals,
    compute_play_advice,
    detect_player_layer_fallback,
    detect_split_fallback,
)


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


_CONFIDENCE_IT = {"low": "Bassa", "medium": "Media", "high": "Alta"}
_OUTCOME_IT = {"win": "WIN", "loss": "LOSS"}


def build_aggressive_cautious_payload(
    *,
    predicted_total: float,
    actual_total: int | None,
    lines: list[float],
    cautious_drop_threshold: float,
    signals: ConfidenceSignals,
    play_config: PlayAdviceConfig,
    advice_signals: PlayAdviceSignals,
    cautious_advice_signals: PlayAdviceSignals,
) -> dict[str, Any]:
    aggressive, cautious, fixture_warnings = evaluate_over_picks(
        predicted_total,
        lines,
        actual_total,
        cautious_drop_threshold=cautious_drop_threshold,
        signals=signals,
    )
    agg_advice = compute_play_advice(aggressive, advice_signals, play_config)
    caut_advice = compute_play_advice(cautious, cautious_advice_signals, play_config)

    base: dict[str, Any] = {
        "predicted_total_sot": _round4(predicted_total),
        "warnings": list(fixture_warnings),
    }

    if aggressive is not None:
        base.update(
            {
                "aggressive_line": aggressive.line,
                "aggressive_edge": _round4(aggressive.edge),
                "aggressive_outcome": _OUTCOME_IT.get(aggressive.outcome or "", aggressive.outcome),
                "aggressive_advice": agg_advice.play_advice_label,
                "aggressive_reason": agg_advice.advice_summary,
                "confidence": _CONFIDENCE_IT.get(aggressive.confidence, aggressive.confidence),
            },
        )
    else:
        base.update(
            {
                "aggressive_line": None,
                "aggressive_edge": None,
                "aggressive_outcome": None,
                "aggressive_advice": agg_advice.play_advice_label,
                "aggressive_reason": agg_advice.advice_summary,
                "confidence": None,
            },
        )

    if cautious is not None:
        base.update(
            {
                "cautious_line": cautious.line,
                "cautious_edge": _round4(cautious.edge),
                "cautious_outcome": _OUTCOME_IT.get(cautious.outcome or "", cautious.outcome),
                "cautious_advice": caut_advice.play_advice_label,
                "cautious_reason": caut_advice.advice_summary,
            },
        )
    else:
        base.update(
            {
                "cautious_line": None,
                "cautious_edge": None,
                "cautious_outcome": None,
                "cautious_advice": caut_advice.play_advice_label,
                "cautious_reason": caut_advice.advice_summary,
            },
        )

    return base


def v21_advice_signals(
    preview: SotV21PreviewResponse,
    *,
    pick_kind: str,
    no_line: bool,
    no_lower: bool,
) -> PlayAdviceSignals:
    from app.services.backtest.sot_pick_evaluation_preview_service import (
        _lineups_macro_status_index,
        _player_layer_status,
    )

    home_pl = _player_layer_status(preview, "home")
    away_pl = _player_layer_status(preview, "away")
    bucket = sample_bucket_key(
        int(preview.home_prior_matches_count),
        int(preview.away_prior_matches_count),
    )
    return PlayAdviceSignals(
        min_prior_matches=min(
            int(preview.home_prior_matches_count),
            int(preview.away_prior_matches_count),
        ),
        warnings_count=len(preview.warnings),
        sample_bucket=bucket,
        player_layer_fallback=detect_player_layer_fallback(
            home_pl,
            away_pl,
            list(preview.fallback_variables),
        ),
        split_fallback=detect_split_fallback(
            preview.home_trace.macros,
            preview.away_trace.macros,
            list(preview.fallback_variables),
        ),
        pick_kind=pick_kind,  # type: ignore[arg-type]
        no_line_available=no_line,
        no_lower_line=no_lower,
    )


def v11_confidence_signals(
    *,
    home_prior: int,
    away_prior: int,
    warnings_count: int,
    player_layer_neutral: bool,
) -> ConfidenceSignals:
    return ConfidenceSignals(
        min_prior_matches=min(home_prior, away_prior),
        warnings_count=warnings_count,
        player_layer_neutral=player_layer_neutral,
    )
