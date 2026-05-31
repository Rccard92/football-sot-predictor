"""Consiglio giocata pre-match per pick evaluation SOT (Step H.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.backtest.sot_pick_evaluation_logic import OverPickResult

PlayAdviceKind = Literal["play", "no_play", "borderline"]
PlayAdviceLabel = Literal["GIOCA", "NON GIOCARE", "BORDERLINE"]
PickKind = Literal["aggressive", "cautious"]

REASON_OK = "OK"
REASON_LOW_EDGE = "LOW_EDGE"
REASON_LOW_SAMPLE = "LOW_SAMPLE"
REASON_EARLY_SAMPLE = "EARLY_SAMPLE"
REASON_TOO_MANY_WARNINGS = "TOO_MANY_WARNINGS"
REASON_LOW_CONFIDENCE = "LOW_CONFIDENCE"
REASON_PLAYER_LAYER_FALLBACK = "PLAYER_LAYER_FALLBACK"
REASON_SPLIT_FALLBACK = "SPLIT_FALLBACK"
REASON_NO_LOWER_LINE = "NO_LOWER_LINE"
REASON_NO_LINE_AVAILABLE = "NO_LINE_AVAILABLE"

REASON_SUMMARY: dict[str, str] = {
    REASON_OK: "OK",
    REASON_LOW_EDGE: "Edge basso",
    REASON_LOW_SAMPLE: "Campione storico insufficiente",
    REASON_EARLY_SAMPLE: "Campione ridotto",
    REASON_TOO_MANY_WARNINGS: "Troppi warning",
    REASON_LOW_CONFIDENCE: "Confidence bassa",
    REASON_PLAYER_LAYER_FALLBACK: "Player layer fallback",
    REASON_SPLIT_FALLBACK: "Split fallback",
    REASON_NO_LOWER_LINE: "Nessuna linea cauta inferiore",
    REASON_NO_LINE_AVAILABLE: "Nessuna linea disponibile",
}


@dataclass(frozen=True)
class PlayAdviceConfig:
    min_prior_matches_for_play: int = 10
    min_aggressive_edge_for_play: float = 0.25
    min_cautious_edge_for_play: float = 1.00
    max_warnings_for_play: int = 6
    allow_early_low_sample: bool = False
    allow_low_confidence: bool = False
    include_borderline_as_playable: bool = False


@dataclass(frozen=True)
class PlayAdviceSignals:
    min_prior_matches: int
    warnings_count: int
    sample_bucket: str
    player_layer_fallback: bool
    split_fallback: bool
    pick_kind: PickKind
    no_line_available: bool
    no_lower_line: bool = False


@dataclass(frozen=True)
class PlayAdviceResult:
    play_advice: PlayAdviceKind
    play_advice_label: PlayAdviceLabel
    playability_score: int
    advice_reasons: list[str]
    advice_summary: str


def _clamp_score(score: int) -> int:
    return max(0, min(100, score))


def _min_edge_for_kind(config: PlayAdviceConfig, pick_kind: PickKind) -> float:
    if pick_kind == "aggressive":
        return config.min_aggressive_edge_for_play
    return config.min_cautious_edge_for_play


def _edge_below_threshold(edge: float, config: PlayAdviceConfig, pick_kind: PickKind) -> bool:
    return edge < _min_edge_for_kind(config, pick_kind)


def _compute_playability_score(
    pick: OverPickResult,
    signals: PlayAdviceSignals,
    config: PlayAdviceConfig,
) -> int:
    score = 100
    if signals.sample_bucket == "early_low_sample":
        score -= 50
    elif signals.sample_bucket == "medium_sample":
        score -= 10
    if signals.min_prior_matches < config.min_prior_matches_for_play:
        score -= 40
    if signals.warnings_count > config.max_warnings_for_play:
        score -= 25
    if pick.confidence == "low":
        score -= 35
    elif pick.confidence == "medium":
        score -= 10
    if _edge_below_threshold(pick.edge, config, signals.pick_kind):
        score -= 50
    if signals.player_layer_fallback:
        score -= 20
    if signals.split_fallback:
        score -= 10
    return _clamp_score(score)


def _score_to_advice_kind(score: int) -> PlayAdviceKind:
    if score >= 70:
        return "play"
    if score >= 50:
        return "borderline"
    return "no_play"


def _advice_label(kind: PlayAdviceKind) -> PlayAdviceLabel:
    if kind == "play":
        return "GIOCA"
    if kind == "borderline":
        return "BORDERLINE"
    return "NON GIOCARE"


def _build_summary(reasons: list[str]) -> str:
    if reasons == [REASON_OK]:
        return REASON_SUMMARY[REASON_OK]
    parts = [REASON_SUMMARY.get(r, r) for r in reasons[:3]]
    return ", ".join(parts)


def _collect_hard_blocks(
    pick: OverPickResult | None,
    signals: PlayAdviceSignals,
    config: PlayAdviceConfig,
) -> list[str]:
    reasons: list[str] = []
    if pick is None or signals.no_line_available:
        if signals.no_lower_line:
            reasons.append(REASON_NO_LOWER_LINE)
        else:
            reasons.append(REASON_NO_LINE_AVAILABLE)
        return reasons

    if signals.min_prior_matches < config.min_prior_matches_for_play:
        reasons.append(REASON_LOW_SAMPLE)
    if signals.sample_bucket == "early_low_sample" and not config.allow_early_low_sample:
        reasons.append(REASON_EARLY_SAMPLE)
    if signals.warnings_count > config.max_warnings_for_play:
        reasons.append(REASON_TOO_MANY_WARNINGS)
    if _edge_below_threshold(pick.edge, config, signals.pick_kind):
        reasons.append(REASON_LOW_EDGE)
    if pick.confidence == "low" and not config.allow_low_confidence:
        reasons.append(REASON_LOW_CONFIDENCE)
    return reasons


def _collect_soft_reasons(
    pick: OverPickResult,
    signals: PlayAdviceSignals,
) -> list[str]:
    reasons: list[str] = []
    if signals.player_layer_fallback:
        reasons.append(REASON_PLAYER_LAYER_FALLBACK)
    if signals.split_fallback:
        reasons.append(REASON_SPLIT_FALLBACK)
    return reasons


def is_playable_advice(
    advice: PlayAdviceResult | None,
    config: PlayAdviceConfig,
) -> bool:
    if advice is None:
        return False
    kind = advice.play_advice if isinstance(advice, PlayAdviceResult) else getattr(advice, "play_advice", None)
    if kind == "play":
        return True
    if kind == "borderline" and config.include_borderline_as_playable:
        return True
    return False


def compute_play_advice(
    pick: OverPickResult | None,
    signals: PlayAdviceSignals,
    config: PlayAdviceConfig,
) -> PlayAdviceResult:
    hard_blocks = _collect_hard_blocks(pick, signals, config)
    if hard_blocks:
        return PlayAdviceResult(
            play_advice="no_play",
            play_advice_label="NON GIOCARE",
            playability_score=_clamp_score(
                _compute_playability_score(pick, signals, config) if pick else 0,
            ),
            advice_reasons=hard_blocks[:2] if len(hard_blocks) > 2 else hard_blocks,
            advice_summary=_build_summary(hard_blocks[:2] if len(hard_blocks) > 2 else hard_blocks),
        )

    assert pick is not None
    score = _compute_playability_score(pick, signals, config)
    advice_kind = _score_to_advice_kind(score)
    soft = _collect_soft_reasons(pick, signals)
    if advice_kind == "play" and not soft:
        reasons = [REASON_OK]
    elif advice_kind == "play":
        reasons = soft[:2]
    else:
        reasons = soft[:2] if soft else [REASON_LOW_EDGE]

    return PlayAdviceResult(
        play_advice=advice_kind,
        play_advice_label=_advice_label(advice_kind),
        playability_score=score,
        advice_reasons=reasons,
        advice_summary=_build_summary(reasons),
    )


def detect_player_layer_fallback(
    home_status: str | None,
    away_status: str | None,
    fallback_variables: list[str],
) -> bool:
    statuses = [s for s in (home_status, away_status) if s]
    if statuses and any(s in ("neutral_fallback", "not_built_yet") for s in statuses):
        return True
    return any("player_layer" in fb for fb in fallback_variables)


def detect_split_fallback(
    home_trace_macros: list,
    away_trace_macros: list,
    fallback_variables: list[str],
) -> bool:
    for macros in (home_trace_macros, away_trace_macros):
        for macro in macros:
            key = macro.key if hasattr(macro, "key") else macro.get("key")
            status = macro.status if hasattr(macro, "status") else macro.get("status")
            if key == "home_away_split" and status == "neutral_fallback":
                return True
    return any("split_home_away" in fb or "split" in fb.lower() for fb in fallback_variables)
