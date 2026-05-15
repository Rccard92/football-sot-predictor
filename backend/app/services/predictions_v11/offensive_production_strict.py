"""
Produzione offensiva composita v1.1 — solo dati reali, nessun fallback.
"""

from __future__ import annotations

from typing import Any

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext
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
    compute_league_offensive_baselines_strict,
)
from app.services.predictions_v11.v11_side_result import V11SideResult
from app.services.sot_feature_registry import V11_ARCHITECTURE, V11_MIN_COMPLETED_MATCHES, V11_MODEL_STAGE

MISSING_DATA_MSG = "Dato obbligatorio non disponibile per il modello v1.1"


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def _round4(x: float) -> float:
    return round(float(x), 4)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _last_n(fixtures: list[Fixture], n: int) -> list[Fixture]:
    xs = sorted(fixtures, key=lambda f: (f.kickoff_at, f.id), reverse=True)[:n]
    return sorted(xs, key=lambda f: (f.kickoff_at, f.id))


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


def _missing_field(feature_key: str) -> dict[str, Any]:
    return {
        "feature_key": feature_key,
        "api_source": INPUT_API_SOURCES.get(feature_key, ""),
        "db_field": INPUT_DB_FIELDS.get(feature_key, ""),
        "source_path": INPUT_SOURCE_PATHS.get(feature_key, ""),
        "message": MISSING_DATA_MSG,
    }


def _incomplete_raw_json(
    *,
    missing: list[dict[str, Any]],
    formula_quality_status: str,
    sample_count: int,
    league_error: list[str] | None = None,
) -> dict[str, Any]:
    if league_error:
        for key in league_error:
            missing.append(
                {
                    "feature_key": key,
                    "api_source": "league_baseline",
                    "db_field": f"league.{key}",
                    "message": "Media lega obbligatoria mancante o non valida per v1.1",
                },
            )
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "architecture": V11_ARCHITECTURE,
        "model_stage": V11_MODEL_STAGE,
        "status": "incomplete",
        "prediction_valid": False,
        "expected_sot": None,
        "formula_quality_status": formula_quality_status,
        "missing_required_fields": missing,
        "sample_count": sample_count,
        "warnings": [],
    }


def compute_v11_side(
    db,
    ctx: V10PriorContext,
    prior_fixtures: list[Fixture],
) -> V11SideResult:
    """Calcola produzione offensiva strict o ritorna payload incomplete."""
    team_id = ctx.team_id
    stats_map = ctx.stats_map
    sample_count = len(prior_fixtures)
    missing: list[dict[str, Any]] = []

    if sample_count < V11_MIN_COMPLETED_MATCHES:
        raw = _incomplete_raw_json(
            missing=missing,
            formula_quality_status="insufficient_sample",
            sample_count=sample_count,
        )
        return V11SideResult(
            valid=False,
            expected_sot=None,
            component=None,
            raw_json=raw,
            missing_required_fields=raw["missing_required_fields"],
            formula_quality_status="insufficient_sample",
            sample_count=sample_count,
        )

    try:
        lb = compute_league_offensive_baselines_strict(
            db,
            season_id=int(ctx.season_id),
            cutoff_kickoff=ctx.cutoff_kickoff,
            cutoff_fixture_id=int(ctx.cutoff_fixture_id),
        )
    except MissingLeagueBaselineError as exc:
        raw = _incomplete_raw_json(
            missing=[],
            formula_quality_status="missing_required_league_baseline",
            sample_count=sample_count,
            league_error=exc.missing_keys,
        )
        return V11SideResult(
            valid=False,
            expected_sot=None,
            component=None,
            raw_json=raw,
            missing_required_fields=raw["missing_required_fields"],
            formula_quality_status="missing_required_league_baseline",
            sample_count=sample_count,
        )

    league_sot = float(lb["league_avg_sot_for"])
    league_shots = float(lb["league_avg_total_shots_for"])
    league_inside = float(lb["league_avg_inside_box_shots_for"])
    league_outside = float(lb["league_avg_outside_box_shots_for"])
    league_blocked = float(lb["league_avg_blocked_shots_for"])
    league_off_goal = float(lb["league_avg_shots_off_goal_for"])
    league_goals = float(lb["league_avg_goals_for"])
    league_acc = float(lb["league_avg_shot_accuracy"])

    season_agg = _agg_for_team(fixtures=prior_fixtures, stats_map=stats_map, team_id=team_id)
    last5_agg = _agg_for_team(
        fixtures=_last_n(prior_fixtures, 5),
        stats_map=stats_map,
        team_id=team_id,
    )

    def require_mean(agg: dict[str, Any], mean_key: str, count_key: str, feature_key: str) -> float | None:
        if int(agg.get(count_key) or 0) <= 0:
            missing.append(_missing_field(feature_key))
            return None
        return _safe_float(agg.get(mean_key))

    avg_sot_for = require_mean(season_agg, "sot_mean", "sot_n", "avg_sot_for")
    avg_shots_raw = require_mean(season_agg, "shots_mean", "shots_n", "avg_total_shots_for")
    avg_inside_raw = require_mean(season_agg, "inside_mean", "inside_n", "avg_inside_box_shots_for")
    avg_outside_raw = require_mean(season_agg, "outside_mean", "outside_n", "avg_outside_box_shots_for")
    avg_blocked_raw = require_mean(season_agg, "blocked_mean", "blocked_n", "avg_blocked_shots_for")
    avg_off_goal_raw = require_mean(season_agg, "off_goal_mean", "off_goal_n", "avg_shots_off_goal_for")
    avg_goals_raw = require_mean(season_agg, "goals_mean", "goals_n", "avg_goals_for")

    if missing:
        raw = _incomplete_raw_json(
            missing=missing,
            formula_quality_status="missing_required_data",
            sample_count=sample_count,
        )
        return V11SideResult(
            valid=False,
            expected_sot=None,
            component=None,
            raw_json=raw,
            missing_required_fields=missing,
            formula_quality_status="missing_required_data",
            sample_count=sample_count,
        )

    assert avg_sot_for is not None
    assert avg_shots_raw is not None
    assert avg_inside_raw is not None
    assert avg_outside_raw is not None
    assert avg_blocked_raw is not None
    assert avg_off_goal_raw is not None
    assert avg_goals_raw is not None

    shot_accuracy_raw = avg_sot_for / avg_shots_raw if avg_shots_raw > 0 else None
    if shot_accuracy_raw is None:
        missing.append(_missing_field("shot_accuracy_for"))
        raw = _incomplete_raw_json(
            missing=missing,
            formula_quality_status="missing_required_data",
            sample_count=sample_count,
        )
        return V11SideResult(
            valid=False,
            expected_sot=None,
            component=None,
            raw_json=raw,
            missing_required_fields=missing,
            formula_quality_status="missing_required_data",
            sample_count=sample_count,
        )

    last5_sot = _safe_float(last5_agg.get("sot_mean"))
    if last5_sot is None or int(last5_agg.get("sot_n") or 0) <= 0:
        missing.append(_missing_field("offensive_trend"))
        raw = _incomplete_raw_json(
            missing=missing,
            formula_quality_status="missing_required_data",
            sample_count=sample_count,
        )
        return V11SideResult(
            valid=False,
            expected_sot=None,
            component=None,
            raw_json=raw,
            missing_required_fields=missing,
            formula_quality_status="missing_required_data",
            sample_count=sample_count,
        )

    trend_raw = float(last5_sot) - float(avg_sot_for)
    trend_clamped = _clamp(trend_raw, -1.0, 1.0)

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
        ic = _round4(norm_v * iw)
        component_sum += ic
        sym_parts.append(f"({INPUT_LABELS[key]} × {iw})")
        inputs_list.append(
            {
                "key": key,
                "label": INPUT_LABELS[key],
                "raw_value": _round2(raw_v if key != "offensive_trend" else trend_raw),
                "normalized_value": _round2(norm_v),
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
                "parent_component": "offensive_production_component",
            },
        )

    component_value = _round2(component_sum) or 0.0
    expected_sot = float(component_value)

    internal_formula = (
        "offensive_production_component = "
        + " + ".join(sym_parts)
        + f"\n= {_round2(component_sum)}"
    )

    off_comp = {
        "value": component_value,
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

    raw_json: dict[str, Any] = {
        "model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "architecture": V11_ARCHITECTURE,
        "model_stage": V11_MODEL_STAGE,
        "status": "ok",
        "prediction_valid": True,
        "expected_sot": expected_sot,
        "formula": {
            "type": "single_component",
            "terms_count": 1,
            "terms": [
                {
                    "key": "offensive_production_component",
                    "label": "Produzione offensiva composita",
                    "value": component_value,
                    "weight": 1.0,
                    "contribution": component_value,
                    "status": "available",
                },
            ],
            "final_sum": component_value,
        },
        "components": {
            "offensive_production_component": off_comp,
        },
        "offensive_production_component": off_comp,
        "formula_quality_status": "ok",
        "warnings": [],
        "sample_count": sample_count,
        "no_data_leakage": True,
    }

    return V11SideResult(
        valid=True,
        expected_sot=expected_sot,
        component=off_comp,
        raw_json=raw_json,
        missing_required_fields=[],
        formula_quality_status="ok",
        sample_count=sample_count,
    )
