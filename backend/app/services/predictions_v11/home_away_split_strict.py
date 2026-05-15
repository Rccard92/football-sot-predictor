"""Split casa/trasferta v1.1 — strict, nessun fallback."""

from __future__ import annotations

from typing import Any

from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.league_baselines_strict import split_league_baselines_for_context
from app.services.predictions_v11.shared_stats import agg_for_team
from app.services.predictions_v11.opponent_stats_agg import agg_conceded_by_opponent
from app.services.predictions_v11.split_feature_sources import (
    COMPONENT_KEY_SPLIT,
    COMPONENT_LABEL_SPLIT,
    SPLIT_INPUT_API_SOURCES,
    SPLIT_INPUT_DB_FIELDS,
    SPLIT_INPUT_LABELS,
    SPLIT_INPUT_ORDER,
    SPLIT_INPUT_SOURCE_PATHS,
    SPLIT_INTERNAL_WEIGHTS,
)
from app.services.predictions_v11.split_fixtures import (
    opponent_split_context_label,
    opponent_split_fixtures,
    split_context_label,
    team_split_fixtures,
)
from app.services.predictions_v11.v11_shared import clamp, missing_field, round2, round4, safe_float
from app.services.sot_feature_registry import V11_MIN_SPLIT_MATCHES


def compute_home_away_split_component(
    ctx: V10PriorContext,
    prior_fixtures: list[Fixture],
    *,
    league_baselines: dict[str, float],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, int, int]:
    """Ritorna (componente, missing, status, team_split_n, opponent_split_n)."""
    missing: list[dict[str, Any]] = []
    meta = {
        "api_sources": SPLIT_INPUT_API_SOURCES,
        "db_fields": SPLIT_INPUT_DB_FIELDS,
        "source_paths": SPLIT_INPUT_SOURCE_PATHS,
    }
    team_is_home = bool(ctx.is_home)
    split_ctx = split_context_label(is_home=team_is_home)
    opp_split_ctx = opponent_split_context_label(team_is_home=team_is_home)

    team_split = team_split_fixtures(prior_fixtures, int(ctx.team_id), is_home_context=team_is_home)
    opp_split = opponent_split_fixtures(
        ctx.opponent_prior_fixtures,
        int(ctx.opponent_id),
        team_is_home=team_is_home,
    )
    team_n = len(team_split)
    opp_n = len(opp_split)

    if team_n < V11_MIN_SPLIT_MATCHES or opp_n < V11_MIN_SPLIT_MATCHES:
        return None, missing, "insufficient_split_sample", team_n, opp_n

    try:
        lb_split = split_league_baselines_for_context(league_baselines, is_home_context=team_is_home)
    except KeyError as exc:
        missing.append(
            {
                "feature_key": str(exc),
                "api_source": "league_baseline",
                "message": "Media lega split mancante per v1.1",
            },
        )
        return None, missing, "missing_required_league_split_baseline", team_n, opp_n

    league_sot = float(lb_split["league_split_avg_sot_for"])
    league_sot_conceded = float(lb_split["league_split_avg_sot_conceded"])
    league_shots = float(lb_split["league_split_avg_total_shots_for"])
    league_shots_conceded = float(lb_split["league_split_avg_total_shots_conceded"])

    stats_map = ctx.stats_map
    team_split_agg = agg_for_team(fixtures=team_split, stats_map=stats_map, team_id=int(ctx.team_id))
    opp_split_agg = agg_conceded_by_opponent(
        fixtures=opp_split,
        stats_map=stats_map,
        opponent_id=int(ctx.opponent_id),
    )
    season_agg = agg_for_team(fixtures=prior_fixtures, stats_map=stats_map, team_id=int(ctx.team_id))

    def require_mean(agg: dict[str, Any], mean_key: str, count_key: str, feature_key: str) -> float | None:
        if int(agg.get(count_key) or 0) <= 0:
            missing.append(missing_field(feature_key, **meta))
            return None
        return safe_float(agg.get(mean_key))

    split_avg_sot = require_mean(team_split_agg, "sot_mean", "sot_n", "split_avg_sot_for")
    split_opp_sot = require_mean(opp_split_agg, "sot_mean", "sot_n", "split_opponent_avg_sot_conceded")
    split_avg_shots = require_mean(team_split_agg, "shots_mean", "shots_n", "split_avg_total_shots_for")
    split_opp_shots = require_mean(opp_split_agg, "shots_mean", "shots_n", "split_opponent_avg_total_shots_conceded")
    season_avg_sot = require_mean(season_agg, "sot_mean", "sot_n", "home_away_performance_delta")

    if missing:
        return None, missing, "missing_required_data", team_n, opp_n

    assert split_avg_sot is not None
    assert split_opp_sot is not None
    assert split_avg_shots is not None
    assert split_opp_shots is not None
    assert season_avg_sot is not None

    delta_raw = float(split_avg_sot) - float(season_avg_sot)
    delta_clamped = clamp(delta_raw, -1.0, 1.0)
    norm_shots_for = float(split_avg_shots) * league_sot / league_shots
    norm_shots_conceded = float(split_opp_shots) * league_sot_conceded / league_shots_conceded
    delta_scaled = float(split_avg_sot) + delta_clamped

    scaled_values: dict[str, tuple[float, float]] = {
        "split_avg_sot_for": (split_avg_sot, split_avg_sot),
        "split_opponent_avg_sot_conceded": (split_opp_sot, split_opp_sot),
        "split_avg_total_shots_for": (split_avg_shots, norm_shots_for),
        "split_opponent_avg_total_shots_conceded": (split_opp_shots, norm_shots_conceded),
        "home_away_performance_delta": (delta_raw, delta_scaled),
    }

    inputs_list: list[dict[str, Any]] = []
    component_sum = 0.0
    sym_parts: list[str] = []

    for key in SPLIT_INPUT_ORDER:
        raw_v, norm_v = scaled_values[key]
        iw = SPLIT_INTERNAL_WEIGHTS[key]
        ic = round4(norm_v * iw)
        component_sum += ic
        sym_parts.append(f"({SPLIT_INPUT_LABELS[key]} × {iw})")
        inputs_list.append(
            {
                "key": key,
                "label": SPLIT_INPUT_LABELS[key],
                "raw_value": round2(raw_v if key != "home_away_performance_delta" else delta_raw),
                "normalized_value": round2(norm_v),
                "internal_weight": iw,
                "internal_contribution": ic,
                "source_path": SPLIT_INPUT_SOURCE_PATHS[key],
                "api_source": SPLIT_INPUT_API_SOURCES[key],
                "db_field": SPLIT_INPUT_DB_FIELDS[key],
                "sample_count": team_n,
                "split_context": split_ctx,
                "fallback_used": False,
                "no_data_leakage": True,
                "status": "available",
                "application_role": "component_input",
                "parent_component": COMPONENT_KEY_SPLIT,
            },
        )

    component_value = round2(component_sum) or 0.0
    internal_formula = (
        f"{COMPONENT_KEY_SPLIT} = "
        + " + ".join(sym_parts)
        + f"\n= {round2(component_sum)}"
    )

    comp = {
        "value": component_value,
        "label": COMPONENT_LABEL_SPLIT,
        "split_context": split_ctx,
        "opponent_split_context": opp_split_ctx,
        "team_split_sample_count": team_n,
        "opponent_split_sample_count": opp_n,
        "internal_formula": internal_formula,
        "inputs": inputs_list,
        "quality": {
            "inputs_total": len(SPLIT_INPUT_ORDER),
            "inputs_available": len(SPLIT_INPUT_ORDER),
            "missing_required": [],
            "sample_minimum": V11_MIN_SPLIT_MATCHES,
            "fallback_count": 0,
            "has_mock_data": False,
            "has_fallback_data": False,
            "no_data_leakage": True,
        },
        "fallbacks_used": [],
    }
    return comp, [], "ok", team_n, opp_n
