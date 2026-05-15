"""
Produzione offensiva + resistenza difensiva avversaria v1.1 — strict, nessun fallback.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.defensive_feature_sources import COMPONENT_KEY_DEFENSIVE, COMPONENT_LABEL_DEFENSIVE
from app.services.predictions_v11.feature_sources import (
    INPUT_API_SOURCES,
    INPUT_DB_FIELDS,
    INPUT_LABELS,
    INPUT_ORDER,
    INPUT_SOURCE_PATHS,
    OFFENSIVE_INTERNAL_WEIGHTS,
)
from app.services.predictions_v11.league_baselines_strict import (
    MissingLeagueBaselineError,
    compute_league_v11_baselines_strict,
)
from app.services.predictions_v11.opponent_defensive_resistance_strict import (
    compute_opponent_defensive_resistance_component,
)
from app.services.predictions_v11.v11_shared import (
    FORMULA_DEFENSIVE_WEIGHT,
    FORMULA_OFFENSIVE_WEIGHT,
    clamp,
    incomplete_raw_json,
    last_n,
    missing_field,
    round2,
    round4,
    safe_float,
)
from app.services.predictions_v11.v11_side_result import V11SideResult
from app.services.sot_feature_registry import V11_ARCHITECTURE, V11_MIN_COMPLETED_MATCHES, V11_MODEL_STAGE

COMPONENT_KEY_OFFENSIVE = "offensive_production_component"
COMPONENT_LABEL_OFFENSIVE = "Produzione offensiva composita"


def _agg_for_team(
    *,
    fixtures: list[Fixture],
    stats_map: dict,
    team_id: int,
) -> dict[str, Any]:
    sot_sum = sot_n = 0
    shots_sum = shots_n = 0
    in_sum = in_n = 0
    out_sum = out_n = 0
    blocked_sum = blocked_n = 0
    off_goal_sum = off_goal_n = 0
    goals_sum = goals_n = 0

    for f in fixtures:
        st = stats_map.get((int(f.id), int(team_id)))
        if st and st.shots_on_target is not None:
            sot_sum += int(st.shots_on_target)
            sot_n += 1
        if st and st.total_shots is not None:
            shots_sum += int(st.total_shots)
            shots_n += 1
        if st and st.shots_inside_box is not None:
            in_sum += int(st.shots_inside_box)
            in_n += 1
        if st and st.shots_outside_box is not None:
            out_sum += int(st.shots_outside_box)
            out_n += 1
        if st and st.blocked_shots is not None:
            blocked_sum += int(st.blocked_shots)
            blocked_n += 1
        if st and st.shots_off_target is not None:
            off_goal_sum += int(st.shots_off_target)
            off_goal_n += 1
        gf = f.goals_home if int(f.home_team_id) == int(team_id) else f.goals_away
        if gf is not None:
            goals_sum += int(gf)
            goals_n += 1

    def mean(sum_: int, n: int) -> float | None:
        return (sum_ / n) if n > 0 else None

    return {
        "matches_count": len(fixtures),
        "sot_mean": mean(sot_sum, sot_n),
        "sot_n": sot_n,
        "shots_mean": mean(shots_sum, shots_n),
        "shots_n": shots_n,
        "inside_mean": mean(in_sum, in_n),
        "inside_n": in_n,
        "outside_mean": mean(out_sum, out_n),
        "outside_n": out_n,
        "blocked_mean": mean(blocked_sum, blocked_n),
        "blocked_n": blocked_n,
        "off_goal_mean": mean(off_goal_sum, off_goal_n),
        "off_goal_n": off_goal_n,
        "goals_mean": mean(goals_sum, goals_n),
        "goals_n": goals_n,
    }


def compute_offensive_production_component(
    ctx: V10PriorContext,
    prior_fixtures: list[Fixture],
    *,
    league_baselines: dict[str, float],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, int]:
    """Ritorna (componente, missing, status, sample_count_squadra)."""
    team_id = ctx.team_id
    stats_map = ctx.stats_map
    sample_count = len(prior_fixtures)
    missing: list[dict[str, Any]] = []
    meta = {
        "api_sources": INPUT_API_SOURCES,
        "db_fields": INPUT_DB_FIELDS,
        "source_paths": INPUT_SOURCE_PATHS,
    }

    if sample_count < V11_MIN_COMPLETED_MATCHES:
        return None, missing, "insufficient_sample", sample_count

    league_sot = float(league_baselines["league_avg_sot_for"])
    league_shots = float(league_baselines["league_avg_total_shots_for"])
    league_inside = float(league_baselines["league_avg_inside_box_shots_for"])
    league_outside = float(league_baselines["league_avg_outside_box_shots_for"])
    league_blocked = float(league_baselines["league_avg_blocked_shots_for"])
    league_off_goal = float(league_baselines["league_avg_shots_off_goal_for"])
    league_goals = float(league_baselines["league_avg_goals_for"])
    league_acc = float(league_baselines["league_avg_shot_accuracy"])

    season_agg = _agg_for_team(fixtures=prior_fixtures, stats_map=stats_map, team_id=team_id)
    last5_agg = _agg_for_team(
        fixtures=last_n(prior_fixtures, 5),
        stats_map=stats_map,
        team_id=team_id,
    )

    def require_mean(agg: dict[str, Any], mean_key: str, count_key: str, feature_key: str) -> float | None:
        if int(agg.get(count_key) or 0) <= 0:
            missing.append(missing_field(feature_key, **meta))
            return None
        return safe_float(agg.get(mean_key))

    avg_sot_for = require_mean(season_agg, "sot_mean", "sot_n", "avg_sot_for")
    avg_shots_raw = require_mean(season_agg, "shots_mean", "shots_n", "avg_total_shots_for")
    avg_inside_raw = require_mean(season_agg, "inside_mean", "inside_n", "avg_inside_box_shots_for")
    avg_outside_raw = require_mean(season_agg, "outside_mean", "outside_n", "avg_outside_box_shots_for")
    avg_blocked_raw = require_mean(season_agg, "blocked_mean", "blocked_n", "avg_blocked_shots_for")
    avg_off_goal_raw = require_mean(season_agg, "off_goal_mean", "off_goal_n", "avg_shots_off_goal_for")
    avg_goals_raw = require_mean(season_agg, "goals_mean", "goals_n", "avg_goals_for")

    if missing:
        return None, missing, "missing_required_data", sample_count

    assert avg_sot_for is not None
    assert avg_shots_raw is not None
    assert avg_inside_raw is not None
    assert avg_outside_raw is not None
    assert avg_blocked_raw is not None
    assert avg_off_goal_raw is not None
    assert avg_goals_raw is not None

    shot_accuracy_raw = avg_sot_for / avg_shots_raw if avg_shots_raw > 0 else None
    if shot_accuracy_raw is None:
        missing.append(missing_field("shot_accuracy_for", **meta))
        return None, missing, "missing_required_data", sample_count

    last5_sot = safe_float(last5_agg.get("sot_mean"))
    if last5_sot is None or int(last5_agg.get("sot_n") or 0) <= 0:
        missing.append(missing_field("offensive_trend", **meta))
        return None, missing, "missing_required_data", sample_count

    trend_raw = float(last5_sot) - float(avg_sot_for)
    trend_clamped = clamp(trend_raw, -1.0, 1.0)

    avg_total_shots_norm = avg_shots_raw * league_sot / league_shots
    avg_inside_norm = avg_inside_raw * league_sot / league_inside
    avg_outside_norm = avg_outside_raw * league_sot / league_outside
    avg_blocked_norm = avg_blocked_raw * league_sot / league_blocked
    avg_off_goal_norm = avg_off_goal_raw * league_sot / league_off_goal
    shot_accuracy_scaled = (shot_accuracy_raw / league_acc) * league_sot
    avg_goals_scaled = (avg_goals_raw / league_goals) * league_sot
    offensive_trend_scaled = avg_sot_for + trend_clamped

    scaled_values: dict[str, tuple[float, float]] = {
        "avg_sot_for": (avg_sot_for, avg_sot_for),
        "avg_total_shots_for": (avg_shots_raw, avg_total_shots_norm),
        "shot_accuracy_for": (shot_accuracy_raw, shot_accuracy_scaled),
        "avg_inside_box_shots_for": (avg_inside_raw, avg_inside_norm),
        "avg_outside_box_shots_for": (avg_outside_raw, avg_outside_norm),
        "avg_blocked_shots_for": (avg_blocked_raw, avg_blocked_norm),
        "avg_shots_off_goal_for": (avg_off_goal_raw, avg_off_goal_norm),
        "avg_goals_for": (avg_goals_raw, avg_goals_scaled),
        "offensive_trend": (trend_raw, offensive_trend_scaled),
    }

    inputs_list: list[dict[str, Any]] = []
    component_sum = 0.0
    sym_parts: list[str] = []

    for key in INPUT_ORDER:
        raw_v, norm_v = scaled_values[key]
        iw = OFFENSIVE_INTERNAL_WEIGHTS[key]
        ic = round4(norm_v * iw)
        component_sum += ic
        sym_parts.append(f"({INPUT_LABELS[key]} × {iw})")
        inputs_list.append(
            {
                "key": key,
                "label": INPUT_LABELS[key],
                "raw_value": round2(raw_v if key != "offensive_trend" else trend_raw),
                "normalized_value": round2(norm_v),
                "internal_weight": iw,
                "internal_contribution": ic,
                "source_path": INPUT_SOURCE_PATHS[key],
                "api_source": INPUT_API_SOURCES[key],
                "db_field": INPUT_DB_FIELDS[key],
                "sample_count": sample_count,
                "fallback_used": False,
                "no_data_leakage": True,
                "status": "available",
                "application_role": "component_input",
                "parent_component": COMPONENT_KEY_OFFENSIVE,
            },
        )

    component_value = round2(component_sum) or 0.0
    internal_formula = (
        f"{COMPONENT_KEY_OFFENSIVE} = "
        + " + ".join(sym_parts)
        + f"\n= {round2(component_sum)}"
    )

    comp = {
        "value": component_value,
        "label": COMPONENT_LABEL_OFFENSIVE,
        "internal_formula": internal_formula,
        "inputs": inputs_list,
        "quality": {
            "inputs_total": len(INPUT_ORDER),
            "inputs_available": len(INPUT_ORDER),
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


def _fail_result(
    *,
    missing: list[dict[str, Any]],
    formula_quality_status: str,
    sample_count: int,
    league_error: list[str] | None = None,
) -> V11SideResult:
    raw = incomplete_raw_json(
        missing=missing,
        formula_quality_status=formula_quality_status,
        sample_count=sample_count,
        league_error=league_error,
    )
    return V11SideResult(
        valid=False,
        expected_sot=None,
        component=None,
        defensive_component=None,
        raw_json=raw,
        missing_required_fields=raw["missing_required_fields"],
        formula_quality_status=formula_quality_status,
        sample_count=sample_count,
    )


def compute_v11_side(
    db: Session,
    ctx: V10PriorContext,
    prior_fixtures: list[Fixture],
) -> V11SideResult:
    """Stage 2: blend 60% offensiva + 40% resistenza difensiva avversaria."""
    sample_count = len(prior_fixtures)
    all_missing: list[dict[str, Any]] = []

    try:
        lb = compute_league_v11_baselines_strict(
            db,
            season_id=int(ctx.season_id),
            cutoff_kickoff=ctx.cutoff_kickoff,
            cutoff_fixture_id=int(ctx.cutoff_fixture_id),
        )
    except MissingLeagueBaselineError as exc:
        return _fail_result(
            missing=[],
            formula_quality_status="missing_required_league_baseline",
            sample_count=sample_count,
            league_error=exc.missing_keys,
        )

    off_comp, off_miss, off_status, off_sample = compute_offensive_production_component(
        ctx,
        prior_fixtures,
        league_baselines=lb,
    )
    def_comp, def_miss, def_status, def_sample = compute_opponent_defensive_resistance_component(
        ctx,
        league_baselines=lb,
    )

    if off_comp is None:
        all_missing.extend(off_miss)
        if off_status == "insufficient_sample":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="insufficient_sample",
                sample_count=off_sample,
            )
    if def_comp is None:
        all_missing.extend(def_miss)
        if def_status == "insufficient_sample" and off_comp is not None:
            return _fail_result(
                missing=all_missing,
                formula_quality_status="insufficient_sample",
                sample_count=def_sample,
            )

    if off_comp is None or def_comp is None:
        fq = "missing_required_data"
        if off_status == "insufficient_sample" or def_status == "insufficient_sample":
            fq = "insufficient_sample"
        return _fail_result(
            missing=all_missing,
            formula_quality_status=fq,
            sample_count=max(off_sample, def_sample),
        )

    off_val = float(off_comp["value"])
    def_val = float(def_comp["value"])
    off_contrib = round2(off_val * FORMULA_OFFENSIVE_WEIGHT) or 0.0
    def_contrib = round2(def_val * FORMULA_DEFENSIVE_WEIGHT) or 0.0
    expected_sot = round2(off_val * FORMULA_OFFENSIVE_WEIGHT + def_val * FORMULA_DEFENSIVE_WEIGHT) or 0.0

    raw_json: dict[str, Any] = {
        "model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "architecture": V11_ARCHITECTURE,
        "model_stage": V11_MODEL_STAGE,
        "status": "ok",
        "prediction_valid": True,
        "expected_sot": expected_sot,
        "formula": {
            "type": "weighted_components",
            "terms_count": 2,
            "terms": [
                {
                    "key": COMPONENT_KEY_OFFENSIVE,
                    "label": COMPONENT_LABEL_OFFENSIVE,
                    "value": off_val,
                    "weight": FORMULA_OFFENSIVE_WEIGHT,
                    "contribution": off_contrib,
                    "status": "available",
                },
                {
                    "key": COMPONENT_KEY_DEFENSIVE,
                    "label": COMPONENT_LABEL_DEFENSIVE,
                    "value": def_val,
                    "weight": FORMULA_DEFENSIVE_WEIGHT,
                    "contribution": def_contrib,
                    "status": "available",
                },
            ],
            "final_sum": expected_sot,
        },
        "components": {
            COMPONENT_KEY_OFFENSIVE: off_comp,
            COMPONENT_KEY_DEFENSIVE: def_comp,
        },
        COMPONENT_KEY_OFFENSIVE: off_comp,
        COMPONENT_KEY_DEFENSIVE: def_comp,
        "formula_quality_status": "ok",
        "warnings": [],
        "sample_count": sample_count,
        "opponent_sample_count": def_sample,
        "no_data_leakage": True,
    }

    return V11SideResult(
        valid=True,
        expected_sot=expected_sot,
        component=off_comp,
        defensive_component=def_comp,
        raw_json=raw_json,
        missing_required_fields=[],
        formula_quality_status="ok",
        sample_count=sample_count,
    )
