"""Builder macro v2.1 da PointInTimeContext (Step E preview)."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from app.schemas.backtest_point_in_time import (
    LeaguePointInTimeBaselines,
    PointInTimeContextResponse,
    TeamPointInTimeStats,
)
from app.services.predictions_v21.v21_constants import (
    ANCHOR_OPP_SOT_CONCEDED_WEIGHT,
    ANCHOR_TEAM_SOT_WEIGHT,
    PREDICTIVE_MACRO_KEYS,
)
from app.services.predictions_v21.v21_macro_aggregators import (
    V21MacroResult,
    calculate_v21_base_anchor_sot,
    calculate_v21_expected_sot,
    calculate_v21_weighted_macro_multiplier,
)
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS

PIT_MACRO_INDEX_MIN = 0.70
PIT_MACRO_INDEX_MAX = 1.30

_MACRO_LABELS = {m.key: m.label for m in V21_MANIFEST_DEFINITIONS if not m.is_quality_only}
_MACRO_WEIGHTS = {m.key: m.macro_weight for m in V21_MANIFEST_DEFINITIONS if not m.is_quality_only}


@dataclass
class PitSidePreviewResult:
    base_anchor_sot: float | None
    base_anchor_trace: dict[str, Any]
    weighted_macro_multiplier: float
    expected_sot: float | None
    macro_traces: list[dict[str, Any]]
    macro_results: list[V21MacroResult]
    warnings: list[str]
    fallback_variables: list[str]


def _clamp_index(value: float) -> float:
    return max(PIT_MACRO_INDEX_MIN, min(PIT_MACRO_INDEX_MAX, value))


def _pit_ratio(
    value: float | None,
    baseline: float | None,
    *,
    invert: bool = False,
) -> tuple[float, str, str | None]:
    if value is None or baseline is None or baseline <= 0:
        return 1.0, "neutral_fallback", "ratio_baseline_missing"
    ratio = float(value) / float(baseline)
    if invert:
        ratio = 2.0 - ratio
    return _clamp_index(ratio), "available", None


def _average_indices(indices: list[tuple[float, str, str | None]]) -> tuple[float, str, list[str]]:
    warnings: list[str] = []
    available = [idx for idx, status, w in indices if status == "available"]
    if not available:
        for _, _, w in indices:
            if w:
                warnings.append(w)
        return 1.0, "neutral_fallback", warnings
    for _, status, w in indices:
        if status != "available" and w:
            warnings.append(w)
    return _clamp_index(mean(available)), "available", warnings


def _neutral_macro(key: str, warning: str) -> tuple[V21MacroResult, dict[str, Any], str]:
    spec_weight = _MACRO_WEIGHTS[key]
    label = _MACRO_LABELS[key]
    result = V21MacroResult(
        key=key,
        label=label,
        macro_weight=spec_weight,
        macro_index=1.0,
        macro_contribution_to_multiplier=float(spec_weight),
        coverage_pct=0.0,
        status="not_built_yet",
        warnings=[warning],
        micros=[],
    )
    trace = {
        "key": key,
        "label": label,
        "macro_weight": spec_weight,
        "macro_index": 1.0,
        "status": "not_built_yet",
        "warnings": [warning],
    }
    return result, trace, warning


def _macro_from_index(
    key: str,
    macro_index: float,
    status: str,
    warnings: list[str],
) -> tuple[V21MacroResult, dict[str, Any]]:
    spec_weight = _MACRO_WEIGHTS[key]
    label = _MACRO_LABELS[key]
    result = V21MacroResult(
        key=key,
        label=label,
        macro_weight=spec_weight,
        macro_index=round(macro_index, 4),
        macro_contribution_to_multiplier=round(macro_index * spec_weight, 4),
        coverage_pct=100.0 if status == "available" else 0.0,
        status=status,
        warnings=warnings,
        micros=[],
    )
    trace = {
        "key": key,
        "label": label,
        "macro_weight": spec_weight,
        "macro_index": round(macro_index, 4),
        "status": status,
        "warnings": warnings,
    }
    return result, trace


def build_pit_side_preview(
    *,
    team: TeamPointInTimeStats,
    opponent: TeamPointInTimeStats,
    league: LeaguePointInTimeBaselines,
    ctx: PointInTimeContextResponse,
) -> PitSidePreviewResult:
    warnings: list[str] = []
    fallbacks: list[str] = []
    macro_results: list[V21MacroResult] = []
    macro_traces: list[dict[str, Any]] = []

    anchor, anchor_warnings = calculate_v21_base_anchor_sot(
        team_sot_for=team.avg_sot_for,
        opponent_sot_conceded=opponent.avg_sot_against,
    )
    warnings.extend(anchor_warnings)
    base_anchor_trace: dict[str, Any] = {
        "formula": "0.55 * avg_sot_for + 0.45 * opponent_avg_sot_against",
        "avg_sot_for": team.avg_sot_for,
        "opponent_avg_sot_against": opponent.avg_sot_against,
        "weight_team_attack": ANCHOR_TEAM_SOT_WEIGHT,
        "weight_opponent_concession": ANCHOR_OPP_SOT_CONCEDED_WEIGHT,
        "value": anchor,
    }

    league_sot = league.league_avg_sot_for
    league_shots = league.league_avg_total_shots
    league_xg = league.league_avg_xg_for
    league_xg_conceded = league.league_avg_xg_conceded

    off_parts = [
        _pit_ratio(team.avg_sot_for, league_sot),
        _pit_ratio(team.avg_total_shots_for, league_shots),
        _pit_ratio(team.avg_xg_for, league_xg),
    ]
    if team.avg_sot_for and team.last5.last5_avg_sot_for:
        off_parts.append(_pit_ratio(team.last5.last5_avg_sot_for, team.avg_sot_for))
    off_index, off_status, off_warns = _average_indices(off_parts)
    warnings.extend(off_warns)
    r, t = _macro_from_index("offensive_production", off_index, off_status, off_warns)
    macro_results.append(r)
    macro_traces.append(t)

    def_parts = [
        _pit_ratio(opponent.avg_sot_against, league_sot, invert=True),
        _pit_ratio(opponent.avg_total_shots_against, league_shots, invert=True),
        _pit_ratio(opponent.avg_xg_against, league_xg_conceded, invert=True),
    ]
    if opponent.avg_sot_against and opponent.last5.last5_avg_sot_against:
        def_parts.append(
            _pit_ratio(opponent.last5.last5_avg_sot_against, opponent.avg_sot_against, invert=True),
        )
    def_index, def_status, def_warns = _average_indices(def_parts)
    warnings.extend(def_warns)
    r, t = _macro_from_index("opponent_defensive_resistance", def_index, def_status, def_warns)
    macro_results.append(r)
    macro_traces.append(t)

    form_parts = [_pit_ratio(team.last5.last5_avg_sot_for, team.avg_sot_for)]
    if team.avg_xg_for and team.last5.last5_avg_xg_for:
        form_parts.append(_pit_ratio(team.last5.last5_avg_xg_for, team.avg_xg_for))
    form_index, form_status, form_warns = _average_indices(form_parts)
    if team.last5.status == "partial_low_sample":
        form_warns.append("recent_form_partial_low_sample")
        warnings.append("recent_form_partial_low_sample")
    warnings.extend(form_warns)
    r, t = _macro_from_index("recent_form", form_index, form_status, form_warns)
    macro_results.append(r)
    macro_traces.append(t)

    xg_parts = [
        _pit_ratio(team.avg_xg_for, league_xg),
        _pit_ratio(opponent.avg_xg_against, league_xg_conceded, invert=True),
    ]
    xg_index, xg_status, xg_warns = _average_indices(xg_parts)
    if xg_status == "neutral_fallback":
        xg_warns.append("chance_quality_xg_feed_missing")
        warnings.append("chance_quality_xg_feed_missing")
    warnings.extend(xg_warns)
    r, t = _macro_from_index("chance_quality", xg_index, xg_status, xg_warns)
    macro_results.append(r)
    macro_traces.append(t)

    pace_parts = [
        _pit_ratio(team.avg_total_shots_for, league_shots),
        _pit_ratio(opponent.avg_total_shots_against, league_shots, invert=True),
    ]
    pace_index, pace_status, pace_warns = _average_indices(pace_parts)
    warnings.extend(pace_warns)
    r, t = _macro_from_index("pace_control", pace_index, pace_status, pace_warns)
    macro_results.append(r)
    macro_traces.append(t)

    for key, fb_key, fb_msg in (
        ("home_away_split", "split_home_away_point_in_time_not_built_yet", "split_home_away_point_in_time_not_built_yet"),
        ("player_layer", "player_layer_point_in_time_not_built_yet", "player_layer_point_in_time_not_built_yet"),
        ("injuries_unavailable", "injuries_point_in_time_not_built_yet", "injuries_point_in_time_not_built_yet"),
    ):
        r, t, fb = _neutral_macro(key, fb_msg)
        macro_results.append(r)
        macro_traces.append(t)
        fallbacks.append(fb_key)
        warnings.append(fb_msg)

    lineup_warning = "no_historical_probable_lineups"
    if lineup_warning in ctx.warnings or not ctx.lineup_diagnostic.lineups_available:
        r, t, fb = _neutral_macro("lineups", lineup_warning)
    else:
        r, t, fb = _neutral_macro("lineups", "lineups_point_in_time_limited")
    macro_results.append(r)
    macro_traces.append(t)
    fallbacks.append("lineups_point_in_time_neutral")
    warnings.append(fb)

    predictive = [m for m in macro_results if m.key in PREDICTIVE_MACRO_KEYS]
    multiplier, _ = calculate_v21_weighted_macro_multiplier(predictive)
    expected = calculate_v21_expected_sot(
        base_anchor_sot=anchor,
        weighted_macro_multiplier=multiplier,
    )

    return PitSidePreviewResult(
        base_anchor_sot=anchor,
        base_anchor_trace=base_anchor_trace,
        weighted_macro_multiplier=multiplier,
        expected_sot=expected,
        macro_traces=macro_traces,
        macro_results=predictive,
        warnings=warnings,
        fallback_variables=fallbacks,
    )
