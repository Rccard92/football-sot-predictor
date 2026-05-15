"""Forma recente v1.1 — strict (ultime 5 partite squadra e avversario), nessun fallback."""

from __future__ import annotations

from typing import Any

from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.league_baselines_strict import REQUIRED_LEAGUE_RECENT_KEYS
from app.services.predictions_v11.opponent_stats_agg import agg_conceded_by_opponent
from app.services.predictions_v11.recent_feature_sources import (
    COMPONENT_KEY_RECENT,
    COMPONENT_LABEL_RECENT,
    RECENT_INPUT_API_SOURCES,
    RECENT_INPUT_DB_FIELDS,
    RECENT_INPUT_LABELS,
    RECENT_INPUT_ORDER,
    RECENT_INPUT_SOURCE_PATHS,
    RECENT_INTERNAL_WEIGHTS,
)
from app.services.predictions_v11.shared_stats import agg_for_team
from app.services.predictions_v11.v11_shared import (
    clamp,
    last_n,
    missing_field,
    round2,
    round4,
    safe_float,
)
from app.services.sot_feature_registry import V11_MIN_RECENT_MATCHES

LEAGUE_RECENT_BASELINE_SOURCE_PATH_IT = (
    "fixtures.goals_home / fixtures.goals_away (goal fatti dalla squadra in ogni match); "
    "per league_recent_*: ultime 5 partite finite per squadra con almeno 5 precedenti prima del cutoff, "
    "poi media aritmetica fra le squadri che entrano nel campione (stesso perimetro di SOT/tiri)."
)


def _missing_recent_league_keys(league_baselines: dict[str, float]) -> list[str]:
    miss: list[str] = []
    for k in REQUIRED_LEAGUE_RECENT_KEYS:
        v = league_baselines.get(k)
        if v is None or float(v) <= 0:
            miss.append(k)
    return miss


def compute_recent_form_component(
    ctx: V10PriorContext,
    prior_fixtures: list[Fixture],
    *,
    league_baselines: dict[str, float],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, int, int]:
    """Ritorna (componente, missing, status, team_last5_n, opp_last5_n)."""
    opp_fixtures = ctx.opponent_prior_fixtures
    missing: list[dict[str, Any]] = []
    meta = {
        "api_sources": RECENT_INPUT_API_SOURCES,
        "db_fields": RECENT_INPUT_DB_FIELDS,
        "source_paths": RECENT_INPUT_SOURCE_PATHS,
    }

    team_n = len(prior_fixtures)
    opp_n = len(opp_fixtures)

    if team_n < V11_MIN_RECENT_MATCHES or opp_n < V11_MIN_RECENT_MATCHES:
        return None, missing, "insufficient_recent_sample", team_n, opp_n

    lb_miss = _missing_recent_league_keys(league_baselines)
    if lb_miss:
        return None, missing, "missing_required_recent_league_baseline", team_n, opp_n

    lr_sf = float(league_baselines["league_recent_avg_sot_for"])
    lr_sc = float(league_baselines["league_recent_avg_sot_conceded"])
    lr_tf = float(league_baselines["league_recent_avg_total_shots_for"])
    lr_tc = float(league_baselines["league_recent_avg_total_shots_conceded"])
    lr_g = float(league_baselines["league_recent_avg_goals_for"])

    team_last5 = last_n(prior_fixtures, V11_MIN_RECENT_MATCHES)
    opp_last5 = last_n(opp_fixtures, V11_MIN_RECENT_MATCHES)
    if len(team_last5) < V11_MIN_RECENT_MATCHES or len(opp_last5) < V11_MIN_RECENT_MATCHES:
        return None, missing, "insufficient_recent_sample", len(team_last5), len(opp_last5)

    tid = int(ctx.team_id)
    oid = int(ctx.opponent_id)
    stats_map = ctx.stats_map

    team_last5_agg = agg_for_team(fixtures=team_last5, stats_map=stats_map, team_id=tid)
    opp_last5_agg = agg_conceded_by_opponent(
        fixtures=opp_last5,
        stats_map=stats_map,
        opponent_id=oid,
    )
    season_team_agg = agg_for_team(fixtures=prior_fixtures, stats_map=stats_map, team_id=tid)
    season_opp_agg = agg_conceded_by_opponent(
        fixtures=opp_fixtures,
        stats_map=stats_map,
        opponent_id=oid,
    )

    def require_mean(
        agg: dict[str, Any],
        mean_key: str,
        count_key: str,
        feature_key: str,
        *,
        need_n: int | None = None,
    ) -> float | None:
        n_need = need_n if need_n is not None else V11_MIN_RECENT_MATCHES
        if int(agg.get(count_key) or 0) < n_need:
            missing.append(missing_field(feature_key, **meta))
            return None
        return safe_float(agg.get(mean_key))

    r_sot = require_mean(team_last5_agg, "sot_mean", "sot_n", "recent_avg_sot_for")
    r_shots = require_mean(team_last5_agg, "shots_mean", "shots_n", "recent_avg_total_shots_for")
    r_goals = require_mean(team_last5_agg, "goals_mean", "goals_n", "recent_avg_goals_for")
    r_osc = require_mean(opp_last5_agg, "sot_mean", "sot_n", "recent_opponent_avg_sot_conceded")
    r_ots = require_mean(opp_last5_agg, "shots_mean", "shots_n", "recent_opponent_avg_total_shots_conceded")

    s_sot = require_mean(season_team_agg, "sot_mean", "sot_n", "recent_avg_sot_for", need_n=1)
    s_osc = require_mean(season_opp_agg, "sot_mean", "sot_n", "recent_opponent_avg_sot_conceded", need_n=1)

    if missing:
        return None, missing, "missing_required_data", team_n, opp_n

    assert r_sot is not None and r_shots is not None and r_goals is not None
    assert r_osc is not None and r_ots is not None
    assert s_sot is not None and s_osc is not None

    delta_team = float(r_sot) - float(s_sot)
    delta_opp = float(r_osc) - float(s_osc)
    trend_raw = 0.60 * delta_team + 0.40 * delta_opp
    trend_clamped = clamp(trend_raw, -1.0, 1.0)
    trend_scaled = lr_sf + trend_clamped

    norm_sf = float(r_sot)
    norm_osc = float(r_osc) * lr_sf / lr_sc
    norm_tf = float(r_shots) * lr_sf / lr_tf
    norm_tsc = float(r_ots) * lr_sf / lr_tc
    norm_g = float(r_goals) * lr_sf / lr_g

    scaled_values: dict[str, tuple[float, float]] = {
        "recent_avg_sot_for": (float(r_sot), norm_sf),
        "recent_opponent_avg_sot_conceded": (float(r_osc), norm_osc),
        "recent_avg_total_shots_for": (float(r_shots), norm_tf),
        "recent_opponent_avg_total_shots_conceded": (float(r_ots), norm_tsc),
        "recent_avg_goals_for": (float(r_goals), norm_g),
        "recent_trend_vs_season": (trend_raw, trend_scaled),
    }

    inputs_list: list[dict[str, Any]] = []
    component_sum = 0.0
    sym_parts: list[str] = []
    window_n = V11_MIN_RECENT_MATCHES

    for key in RECENT_INPUT_ORDER:
        raw_v, norm_v = scaled_values[key]
        iw = RECENT_INTERNAL_WEIGHTS[key]
        ic = round4(norm_v * iw)
        component_sum += ic
        sym_parts.append(f"({RECENT_INPUT_LABELS[key]} × {iw})")
        inp_row: dict[str, Any] = {
            "key": key,
            "label": RECENT_INPUT_LABELS[key],
            "raw_value": round2(raw_v if key != "recent_trend_vs_season" else trend_raw),
            "normalized_value": round2(norm_v),
            "internal_weight": iw,
            "internal_contribution": ic,
            "source_path": RECENT_INPUT_SOURCE_PATHS[key],
            "api_source": RECENT_INPUT_API_SOURCES[key],
            "db_field": RECENT_INPUT_DB_FIELDS[key],
            "sample_count": window_n,
            "fallback_used": False,
            "no_data_leakage": True,
            "status": "available",
            "application_role": "component_input",
            "parent_component": COMPONENT_KEY_RECENT,
        }
        if key == "recent_avg_goals_for":
            inp_row["normalization"] = {
                "league_recent_avg_goals_for": round2(lr_g),
                "league_recent_avg_sot_for": round2(lr_sf),
            }
        inputs_list.append(inp_row)

    component_value = round2(component_sum) or 0.0
    internal_formula = (
        f"{COMPONENT_KEY_RECENT} = "
        + " + ".join(sym_parts)
        + f"\n= {round2(component_sum)}"
    )

    comp: dict[str, Any] = {
        "value": component_value,
        "label": COMPONENT_LABEL_RECENT,
        "internal_formula": internal_formula,
        "inputs": inputs_list,
        "quality": {
            "inputs_total": len(RECENT_INPUT_ORDER),
            "inputs_available": len(RECENT_INPUT_ORDER),
            "missing_required": [],
            "sample_minimum": V11_MIN_RECENT_MATCHES,
            "fallback_count": 0,
            "has_mock_data": False,
            "has_fallback_data": False,
            "no_data_leakage": True,
        },
        "fallbacks_used": [],
        "league_baselines_recent": {
            "league_recent_avg_goals_for": round2(lr_g),
            "league_recent_avg_sot_for": round2(lr_sf),
            "league_recent_avg_sot_conceded": round2(lr_sc),
            "league_recent_avg_total_shots_for": round2(lr_tf),
            "league_recent_avg_total_shots_conceded": round2(lr_tc),
            "source_path": LEAGUE_RECENT_BASELINE_SOURCE_PATH_IT,
            "sample_teams_count": int(float(league_baselines.get("league_recent_goals_baseline_team_count", 0) or 0)),
            "no_data_leakage": True,
        },
    }
    return comp, [], "ok", window_n, window_n
