"""Applicazione pick Agg/Cauta ai risultati adapter Round Analysis."""

from __future__ import annotations

from typing import Any

from app.schemas.backtest_sot_v21_preview import SotV21PreviewResponse
from app.services.backtest.round_analysis_pick_builder import (
    build_aggressive_cautious_payload,
    v11_confidence_signals,
    v21_advice_signals,
)
from app.services.backtest.sot_pick_evaluation_logic import evaluate_over_picks, sample_bucket_key
from app.services.backtest.sot_pick_evaluation_logic import player_layer_is_neutral
from app.services.backtest.sot_pick_evaluation_preview_service import _player_layer_status
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig, PlayAdviceSignals


def apply_v11_style_picks(
    *,
    predicted_total: float,
    home_prior: int,
    away_prior: int,
    warnings: list[str],
    sample_bucket: str,
    player_layer_neutral: bool,
    lines: list[float],
    cautious_drop_threshold: float,
    play_config: PlayAdviceConfig,
    actual_total: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    signals = v11_confidence_signals(
        home_prior=home_prior,
        away_prior=away_prior,
        warnings_count=len(warnings),
        player_layer_neutral=player_layer_neutral,
    )
    aggressive, cautious, fixture_warnings = evaluate_over_picks(
        predicted_total,
        lines,
        actual_total,
        cautious_drop_threshold=cautious_drop_threshold,
        signals=signals,
    )
    no_lower = "no_lower_cautious_line_available" in fixture_warnings
    picks = build_aggressive_cautious_payload(
        predicted_total=predicted_total,
        actual_total=actual_total,
        lines=lines,
        cautious_drop_threshold=cautious_drop_threshold,
        signals=signals,
        play_config=play_config,
        advice_signals=PlayAdviceSignals(
            min_prior_matches=signals.min_prior_matches,
            warnings_count=signals.warnings_count,
            sample_bucket=sample_bucket,
            player_layer_fallback=player_layer_neutral,
            split_fallback=False,
            pick_kind="aggressive",
            no_line_available=aggressive is None,
        ),
        cautious_advice_signals=PlayAdviceSignals(
            min_prior_matches=signals.min_prior_matches,
            warnings_count=signals.warnings_count,
            sample_bucket=sample_bucket,
            player_layer_fallback=player_layer_neutral,
            split_fallback=False,
            pick_kind="cautious",
            no_line_available=cautious is None,
            no_lower_line=no_lower,
        ),
    )
    merged_warnings = list(dict.fromkeys(warnings + list(picks.get("warnings") or [])))
    prediction_patch = {
        "predicted_total_sot": picks.get("predicted_total_sot", predicted_total),
        "warnings": merged_warnings,
    }
    pick_fields = {
        k: v
        for k, v in picks.items()
        if k not in ("predicted_total_sot", "warnings")
    }
    return prediction_patch, pick_fields


def apply_v21_picks(
    *,
    preview: SotV21PreviewResponse,
    predicted_total: float,
    lines: list[float],
    cautious_drop_threshold: float,
    play_config: PlayAdviceConfig,
    actual_total: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    home_prior = int(preview.home_prior_matches_count)
    away_prior = int(preview.away_prior_matches_count)
    bucket = sample_bucket_key(home_prior, away_prior)
    signals = v11_confidence_signals(
        home_prior=home_prior,
        away_prior=away_prior,
        warnings_count=len(preview.warnings),
        player_layer_neutral=player_layer_is_neutral(
            _player_layer_status(preview, "home"),
            _player_layer_status(preview, "away"),
        ),
    )
    aggressive, cautious, fixture_warnings = evaluate_over_picks(
        predicted_total,
        lines,
        actual_total,
        cautious_drop_threshold=cautious_drop_threshold,
        signals=signals,
    )
    no_lower = "no_lower_cautious_line_available" in fixture_warnings
    picks = build_aggressive_cautious_payload(
        predicted_total=predicted_total,
        actual_total=actual_total,
        lines=lines,
        cautious_drop_threshold=cautious_drop_threshold,
        signals=signals,
        play_config=play_config,
        advice_signals=v21_advice_signals(
            preview,
            pick_kind="aggressive",
            no_line=aggressive is None,
            no_lower=False,
        ),
        cautious_advice_signals=v21_advice_signals(
            preview,
            pick_kind="cautious",
            no_line=cautious is None,
            no_lower=no_lower,
        ),
    )
    merged_warnings = list(dict.fromkeys(list(preview.warnings) + list(picks.get("warnings") or [])))
    pick_fields = {
        k: v
        for k, v in picks.items()
        if k not in ("predicted_total_sot", "warnings")
    }
    return (
        {"predicted_total_sot": picks.get("predicted_total_sot"), "sample_bucket": bucket, "warnings": merged_warnings},
        pick_fields,
    )
