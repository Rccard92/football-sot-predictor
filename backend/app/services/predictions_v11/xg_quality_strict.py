"""Qualità occasioni / xG v1.1 — strict, solo expected_goals reale, nessun fallback."""

from __future__ import annotations

from typing import Any

from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.league_baselines_strict import REQUIRED_LEAGUE_XG_KEYS
from app.services.predictions_v11.opponent_stats_agg import agg_xg_conceded_by_opponent
from app.services.predictions_v11.shared_stats import agg_for_team
from app.services.predictions_v11.v11_shared import clamp, missing_field, round2, round4, safe_float
from app.services.predictions_v11.xg_feature_sources import (
    COMPONENT_KEY_XG,
    COMPONENT_LABEL_XG,
    XG_INPUT_API_SOURCES,
    XG_INPUT_DB_FIELDS,
    XG_INPUT_LABELS,
    XG_INPUT_ORDER,
    XG_INPUT_SOURCE_PATHS,
    XG_INTERNAL_WEIGHTS,
)
from app.services.sot_feature_registry import V11_MIN_XG_MATCHES


def _missing_xg_league_keys(league_baselines: dict[str, float]) -> list[str]:
    miss: list[str] = []
    for k in REQUIRED_LEAGUE_XG_KEYS:
        v = league_baselines.get(k)
        if v is None or float(v) <= 0:
            miss.append(k)
    return miss


def compute_xg_chance_quality_component(
    ctx: V10PriorContext,
    prior_fixtures: list[Fixture],
    *,
    league_baselines: dict[str, float],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, int, int]:
    """Ritorna (componente, missing, status, team_xg_n, opp_xg_n)."""
    missing: list[dict[str, Any]] = []
    meta = {
        "api_sources": XG_INPUT_API_SOURCES,
        "db_fields": XG_INPUT_DB_FIELDS,
        "source_paths": XG_INPUT_SOURCE_PATHS,
    }

    team_id = int(ctx.team_id)
    oid = int(ctx.opponent_id)
    stats_map = ctx.stats_map
    opp_fixtures = ctx.opponent_prior_fixtures

    lb_miss = _missing_xg_league_keys(league_baselines)
    if lb_miss:
        return None, missing, "missing_required_xg_league_baseline", len(prior_fixtures), len(opp_fixtures)

    lxg_for = float(league_baselines["league_avg_xg_for"])
    lxg_conc = float(league_baselines["league_avg_xg_conceded"])
    lsot_for = float(league_baselines["league_avg_sot_for"])
    lsot_conc = float(league_baselines["league_avg_sot_conceded"])

    team_agg = agg_for_team(fixtures=prior_fixtures, stats_map=stats_map, team_id=team_id)
    opp_agg = agg_xg_conceded_by_opponent(
        fixtures=opp_fixtures,
        stats_map=stats_map,
        opponent_id=oid,
    )

    team_xg_n = int(team_agg.get("xg_n") or 0)
    opp_xg_n = int(opp_agg.get("xg_n") or 0)

    if team_xg_n < V11_MIN_XG_MATCHES or opp_xg_n < V11_MIN_XG_MATCHES:
        return None, missing, "insufficient_xg_sample", team_xg_n, opp_xg_n

    avg_xg_for = safe_float(team_agg.get("xg_mean"))
    opponent_avg_xg_conc = safe_float(opp_agg.get("xg_mean"))
    if avg_xg_for is None or opponent_avg_xg_conc is None:
        missing.append(missing_field("avg_xg_for", **meta))
        return None, missing, "missing_required_data", team_xg_n, opp_xg_n

    xg_for_scaled = float(avg_xg_for) * lsot_for / lxg_for
    opponent_xg_conceded_scaled = float(opponent_avg_xg_conc) * lsot_conc / lxg_conc

    team_delta_raw = float(avg_xg_for) - lxg_for
    opp_delta_raw = float(opponent_avg_xg_conc) - lxg_conc

    team_xg_delta_scaled = lsot_for + clamp(
        (float(avg_xg_for) - lxg_for) * lsot_for / lxg_for,
        -1.0,
        1.0,
    )
    opponent_xg_conceded_delta_scaled = lsot_conc + clamp(
        (float(opponent_avg_xg_conc) - lxg_conc) * lsot_conc / lxg_conc,
        -1.0,
        1.0,
    )

    team_xg_delta_pct = (float(avg_xg_for) - lxg_for) / lxg_for
    opponent_xg_delta_pct = (float(opponent_avg_xg_conc) - lxg_conc) / lxg_conc
    combined_xg_delta_pct = 0.60 * team_xg_delta_pct + 0.40 * opponent_xg_delta_pct
    xg_adjustment_pct = clamp(combined_xg_delta_pct * 0.10, -0.08, 0.08)
    prudent_signal = lsot_for * (1.0 + xg_adjustment_pct)

    scaled_map: dict[str, tuple[float, float]] = {
        "avg_xg_for": (float(avg_xg_for), xg_for_scaled),
        "opponent_avg_xg_conceded": (float(opponent_avg_xg_conc), opponent_xg_conceded_scaled),
        "team_xg_delta_vs_league": (team_delta_raw, team_xg_delta_scaled),
        "opponent_xg_conceded_delta_vs_league": (opp_delta_raw, opponent_xg_conceded_delta_scaled),
        "xg_prudent_adjustment_signal": (xg_adjustment_pct, prudent_signal),
    }

    inputs_list: list[dict[str, Any]] = []
    component_sum = 0.0
    sym_parts: list[str] = []
    sample_use = min(team_xg_n, opp_xg_n)

    for key in XG_INPUT_ORDER:
        raw_v, norm_v = scaled_map[key]
        iw = XG_INTERNAL_WEIGHTS[key]
        ic = round4(norm_v * iw)
        component_sum += ic
        sym_parts.append(f"({XG_INPUT_LABELS[key]} × {iw})")
        raw_display = raw_v
        if key == "xg_prudent_adjustment_signal":
            raw_display = xg_adjustment_pct
        inputs_list.append(
            {
                "key": key,
                "label": XG_INPUT_LABELS[key],
                "raw_value": round2(raw_display),
                "normalized_value": round2(norm_v),
                "internal_weight": iw,
                "internal_contribution": ic,
                "source_path": XG_INPUT_SOURCE_PATHS[key],
                "api_source": XG_INPUT_API_SOURCES[key],
                "db_field": XG_INPUT_DB_FIELDS[key],
                "sample_count": sample_use,
                "fallback_used": False,
                "no_data_leakage": True,
                "status": "available",
                "application_role": "component_input",
                "parent_component": COMPONENT_KEY_XG,
            },
        )

    component_value = round2(component_sum) or 0.0
    internal_formula = (
        f"{COMPONENT_KEY_XG} = "
        + " + ".join(sym_parts)
        + f"\n= {round2(component_sum)}"
    )

    comp: dict[str, Any] = {
        "value": component_value,
        "label": COMPONENT_LABEL_XG,
        "internal_formula": internal_formula,
        "inputs": inputs_list,
        "quality": {
            "inputs_total": len(XG_INPUT_ORDER),
            "inputs_available": len(XG_INPUT_ORDER),
            "missing_required": [],
            "sample_minimum": V11_MIN_XG_MATCHES,
            "fallback_count": 0,
            "has_mock_data": False,
            "has_fallback_data": False,
            "no_data_leakage": True,
        },
        "fallbacks_used": [],
    }
    return comp, [], "ok", team_xg_n, opp_xg_n
