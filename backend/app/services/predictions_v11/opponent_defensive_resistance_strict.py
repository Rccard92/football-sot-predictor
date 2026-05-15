"""Resistenza difensiva avversaria v1.1 — strict, nessun fallback."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.defensive_feature_sources import (
    COMPONENT_KEY_DEFENSIVE,
    COMPONENT_LABEL_DEFENSIVE,
    DEFENSIVE_INPUT_API_SOURCES,
    DEFENSIVE_INPUT_DB_FIELDS,
    DEFENSIVE_INPUT_LABELS,
    DEFENSIVE_INTERNAL_WEIGHTS,
    DEFENSIVE_INPUT_SOURCE_PATHS,
)
from app.services.predictions_v11.opponent_stats_agg import agg_conceded_by_opponent
from app.services.predictions_v11.v11_shared import (
    clamp,
    last_n,
    missing_field,
    round2,
    round4,
    safe_float,
)
from app.services.sot_feature_registry import V11_MIN_COMPLETED_MATCHES

DEFENSIVE_INPUT_ORDER: tuple[str, ...] = tuple(DEFENSIVE_INTERNAL_WEIGHTS.keys())


def compute_opponent_defensive_resistance_component(
    ctx: V10PriorContext,
    *,
    league_baselines: dict[str, float],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, int]:
    """
    Ritorna (componente, missing, status, sample_count_avversario).
    """
    opponent_fixtures = ctx.opponent_prior_fixtures
    sample_count = len(opponent_fixtures)
    missing: list[dict[str, Any]] = []
    meta = {
        "api_sources": DEFENSIVE_INPUT_API_SOURCES,
        "db_fields": DEFENSIVE_INPUT_DB_FIELDS,
        "source_paths": DEFENSIVE_INPUT_SOURCE_PATHS,
    }

    if sample_count < V11_MIN_COMPLETED_MATCHES:
        return None, missing, "insufficient_sample", sample_count

    league_sot = float(league_baselines["league_avg_sot_conceded"])
    league_shots = float(league_baselines["league_avg_total_shots_conceded"])
    league_inside = float(league_baselines["league_avg_inside_box_shots_conceded"])
    league_outside = float(league_baselines["league_avg_outside_box_shots_conceded"])
    league_blocked = float(league_baselines["league_avg_blocked_shots_conceded"])

    season_agg = agg_conceded_by_opponent(
        fixtures=opponent_fixtures,
        stats_map=ctx.stats_map,
        opponent_id=int(ctx.opponent_id),
    )
    last5_agg = agg_conceded_by_opponent(
        fixtures=last_n(opponent_fixtures, 5),
        stats_map=ctx.stats_map,
        opponent_id=int(ctx.opponent_id),
    )

    def require_mean(agg: dict[str, Any], mean_key: str, count_key: str, feature_key: str) -> float | None:
        if int(agg.get(count_key) or 0) <= 0:
            missing.append(missing_field(feature_key, **meta))
            return None
        return safe_float(agg.get(mean_key))

    avg_sot = require_mean(season_agg, "sot_mean", "sot_n", "opponent_avg_sot_conceded")
    avg_shots = require_mean(season_agg, "shots_mean", "shots_n", "opponent_avg_total_shots_conceded")
    avg_inside = require_mean(season_agg, "inside_mean", "inside_n", "opponent_avg_inside_box_shots_conceded")
    avg_outside = require_mean(season_agg, "outside_mean", "outside_n", "opponent_avg_outside_box_shots_conceded")
    avg_blocked = require_mean(season_agg, "blocked_mean", "blocked_n", "opponent_avg_blocked_shots_conceded")

    if missing:
        return None, missing, "missing_required_data", sample_count

    assert avg_sot is not None
    assert avg_shots is not None
    assert avg_inside is not None
    assert avg_outside is not None
    assert avg_blocked is not None

    last5_sot = safe_float(last5_agg.get("sot_mean"))
    if last5_sot is None or int(last5_agg.get("sot_n") or 0) <= 0:
        missing.append(missing_field("opponent_defensive_trend_recent", **meta))
        return None, missing, "missing_required_data", sample_count

    trend_raw = float(last5_sot) - float(avg_sot)
    trend_clamped = clamp(trend_raw, -1.0, 1.0)
    norm_shots = avg_shots * league_sot / league_shots
    norm_inside = avg_inside * league_sot / league_inside
    norm_outside = avg_outside * league_sot / league_outside
    norm_blocked = avg_blocked * league_sot / league_blocked
    trend_scaled = float(avg_sot) + trend_clamped

    scaled_values: dict[str, tuple[float, float]] = {
        "opponent_avg_sot_conceded": (avg_sot, avg_sot),
        "opponent_avg_total_shots_conceded": (avg_shots, norm_shots),
        "opponent_avg_inside_box_shots_conceded": (avg_inside, norm_inside),
        "opponent_avg_outside_box_shots_conceded": (avg_outside, norm_outside),
        "opponent_avg_blocked_shots_conceded": (avg_blocked, norm_blocked),
        "opponent_defensive_trend_recent": (trend_raw, trend_scaled),
    }

    inputs_list: list[dict[str, Any]] = []
    component_sum = 0.0
    sym_parts: list[str] = []

    for key in DEFENSIVE_INPUT_ORDER:
        raw_v, norm_v = scaled_values[key]
        iw = DEFENSIVE_INTERNAL_WEIGHTS[key]
        ic = round4(norm_v * iw)
        component_sum += ic
        sym_parts.append(f"({DEFENSIVE_INPUT_LABELS[key]} × {iw})")
        inputs_list.append(
            {
                "key": key,
                "label": DEFENSIVE_INPUT_LABELS[key],
                "raw_value": round2(raw_v if key != "opponent_defensive_trend_recent" else trend_raw),
                "normalized_value": round2(norm_v),
                "internal_weight": iw,
                "internal_contribution": ic,
                "source_path": DEFENSIVE_INPUT_SOURCE_PATHS[key],
                "api_source": DEFENSIVE_INPUT_API_SOURCES[key],
                "db_field": DEFENSIVE_INPUT_DB_FIELDS[key],
                "sample_count": sample_count,
                "fallback_used": False,
                "no_data_leakage": True,
                "status": "available",
                "application_role": "component_input",
                "parent_component": COMPONENT_KEY_DEFENSIVE,
            },
        )

    component_value = round2(component_sum) or 0.0
    internal_formula = (
        f"{COMPONENT_KEY_DEFENSIVE} = "
        + " + ".join(sym_parts)
        + f"\n= {round2(component_sum)}"
    )

    comp = {
        "value": component_value,
        "label": COMPONENT_LABEL_DEFENSIVE,
        "internal_formula": internal_formula,
        "inputs": inputs_list,
        "quality": {
            "inputs_total": len(DEFENSIVE_INPUT_ORDER),
            "inputs_available": len(DEFENSIVE_INPUT_ORDER),
            "missing_required": [],
            "sample_minimum": V11_MIN_COMPLETED_MATCHES,
            "fallback_count": 0,
            "has_mock_data": False,
            "has_fallback_data": False,
            "no_data_leakage": True,
        },
        "fallbacks_used": [],
    }
    return comp, [], "ok", sample_count


def compute_opponent_defensive_for_side(
    db: Session,
    ctx: V10PriorContext,
    *,
    league_baselines: dict[str, float] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, int]:
    """Wrapper con league baselines opzionali (già caricate da compute_v11_side)."""
    if league_baselines is None:
        from app.services.predictions_v11.league_baselines_strict import compute_league_v11_baselines_strict

        league_baselines = compute_league_v11_baselines_strict(
            db,
            season_id=int(ctx.season_id),
            cutoff_kickoff=ctx.cutoff_kickoff,
            cutoff_fixture_id=int(ctx.cutoff_fixture_id),
        )
    return compute_opponent_defensive_resistance_component(ctx, league_baselines=league_baselines)
