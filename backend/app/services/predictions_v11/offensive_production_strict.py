"""
Produzione offensiva + resistenza difensiva avversaria v1.1 — strict, nessun fallback.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture, Season
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.defensive_feature_sources import COMPONENT_KEY_DEFENSIVE, COMPONENT_LABEL_DEFENSIVE
from app.services.predictions_v11.home_away_split_strict import compute_home_away_split_component
from app.services.predictions_v11.split_feature_sources import COMPONENT_KEY_SPLIT, COMPONENT_LABEL_SPLIT
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
    REQUIRED_LEAGUE_RECENT_KEYS,
    REQUIRED_LEAGUE_XG_KEYS,
    compute_league_v11_baselines_strict,
)
from app.services.predictions_v11.opponent_defensive_resistance_strict import (
    compute_opponent_defensive_resistance_component,
)
from app.services.predictions_v11.recent_feature_sources import (
    COMPONENT_KEY_RECENT,
    COMPONENT_LABEL_RECENT,
)
from app.services.predictions_v11.recent_form_strict import compute_recent_form_component
from app.services.predictions_v11.shared_stats import agg_for_team
from app.services.predictions_v11.player_layer_feature_sources import (
    COMPONENT_KEY_PLAYER,
    COMPONENT_LABEL_PLAYER,
)
from app.services.predictions_v11.player_layer_strict import (
    MissingPlayerLeagueBaselineError,
    compute_league_player_baselines_strict,
    compute_player_layer_component,
)
from app.services.predictions_v11.xg_feature_sources import COMPONENT_KEY_XG, COMPONENT_LABEL_XG
from app.services.predictions_v11.xg_quality_strict import compute_xg_chance_quality_component
from app.services.predictions_v11.v11_shared import (
    FORMULA_DEFENSIVE_WEIGHT,
    FORMULA_OFFENSIVE_WEIGHT,
    FORMULA_PLAYER_WEIGHT,
    FORMULA_RECENT_WEIGHT,
    FORMULA_SPLIT_WEIGHT,
    FORMULA_XG_WEIGHT,
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

    season_agg = agg_for_team(fixtures=prior_fixtures, stats_map=stats_map, team_id=team_id)
    last5_agg = agg_for_team(
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
        spath = INPUT_SOURCE_PATHS[key]
        extra_notes: str | None = None
        if key == "avg_blocked_shots_for":
            spath = str(season_agg.get("blocked_shots_trace_path") or spath)
        elif key == "avg_shots_off_goal_for":
            spath = str(season_agg.get("shots_off_goal_trace_path") or spath)
        if key in ("avg_blocked_shots_for", "avg_shots_off_goal_for") and (
            "raw_json" in spath or " | " in spath
        ):
            extra_notes = (
                "Nel campione sono entrate partite con colonne DB nulle ma "
                "statistiche disponibili nel raw_json persistente (sempre dati API reali, senza imputazione)."
            )
        row_input: dict[str, Any] = {
            "key": key,
            "label": INPUT_LABELS[key],
            "raw_value": round2(raw_v if key != "offensive_trend" else trend_raw),
            "normalized_value": round2(norm_v),
            "internal_weight": iw,
            "internal_contribution": ic,
            "source_path": spath,
            "api_source": INPUT_API_SOURCES[key],
            "db_field": INPUT_DB_FIELDS[key],
            "sample_count": sample_count,
            "fallback_used": False,
            "no_data_leakage": True,
            "status": "available",
            "application_role": "component_input",
            "parent_component": COMPONENT_KEY_OFFENSIVE,
        }
        if extra_notes:
            row_input["notes"] = extra_notes
        inputs_list.append(row_input)

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
        split_component=None,
        recent_component=None,
        xg_component=None,
        player_layer_component=None,
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
    """Stage 6: blend 6 componenti (offensiva, difensiva, split, recente, xG, player layer)."""
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
        mk = set(exc.missing_keys)
        fq = "missing_required_league_baseline"
        if mk & set(REQUIRED_LEAGUE_XG_KEYS):
            fq = "missing_required_xg_league_baseline"
        elif mk & set(REQUIRED_LEAGUE_RECENT_KEYS):
            fq = "missing_required_recent_league_baseline"
        return _fail_result(
            missing=[],
            formula_quality_status=fq,
            sample_count=sample_count,
            league_error=exc.missing_keys,
        )

    season_row = db.get(Season, int(ctx.season_id))
    if season_row is None:
        return _fail_result(
            missing=[],
            formula_quality_status="missing_required_data",
            sample_count=sample_count,
        )

    try:
        player_lb = compute_league_player_baselines_strict(
            db,
            season_year=int(season_row.year),
            league_id=int(season_row.league_id),
        )
    except MissingPlayerLeagueBaselineError as exc:
        return _fail_result(
            missing=[],
            formula_quality_status="missing_required_player_league_baseline",
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
    split_comp, split_miss, split_status, team_split_n, opp_split_n = compute_home_away_split_component(
        ctx,
        prior_fixtures,
        league_baselines=lb,
    )
    recent_comp, recent_miss, recent_status, team_recent_n, opp_recent_n = compute_recent_form_component(
        ctx,
        prior_fixtures,
        league_baselines=lb,
    )
    xg_comp, xg_miss, xg_status, team_xg_n, opp_xg_n = compute_xg_chance_quality_component(
        ctx,
        prior_fixtures,
        league_baselines=lb,
    )
    player_comp, player_miss, player_status, _top_players, _player_quality = compute_player_layer_component(
        db,
        ctx,
        league_baselines=lb,
        player_league_baselines=player_lb,
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
    if split_comp is None:
        all_missing.extend(split_miss)
        if split_status == "insufficient_split_sample":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="insufficient_split_sample",
                sample_count=max(team_split_n, opp_split_n),
            )
        if split_status == "missing_required_league_split_baseline":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="missing_required_league_split_baseline",
                sample_count=max(team_split_n, opp_split_n),
            )
    if recent_comp is None:
        all_missing.extend(recent_miss)
        if recent_status == "insufficient_recent_sample":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="insufficient_recent_sample",
                sample_count=max(off_sample, def_sample, team_split_n, opp_split_n, team_recent_n, opp_recent_n),
            )
        if recent_status == "missing_required_recent_league_baseline":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="missing_required_recent_league_baseline",
                sample_count=max(team_recent_n, opp_recent_n),
            )
    if xg_comp is None:
        all_missing.extend(xg_miss)
        if xg_status == "insufficient_xg_sample":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="insufficient_xg_sample",
                sample_count=max(
                    off_sample,
                    def_sample,
                    team_split_n,
                    opp_split_n,
                    team_recent_n,
                    opp_recent_n,
                    team_xg_n,
                    opp_xg_n,
                ),
            )
        if xg_status == "missing_required_xg_league_baseline":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="missing_required_xg_league_baseline",
                sample_count=max(team_xg_n, opp_xg_n),
            )
    if player_comp is None:
        all_missing.extend(player_miss)
        if player_status == "insufficient_player_profile_sample":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="insufficient_player_profile_sample",
                sample_count=max(
                    off_sample,
                    def_sample,
                    team_split_n,
                    opp_split_n,
                    team_recent_n,
                    opp_recent_n,
                    team_xg_n,
                    opp_xg_n,
                ),
            )
        if player_status == "missing_required_player_league_baseline":
            return _fail_result(
                missing=all_missing,
                formula_quality_status="missing_required_player_league_baseline",
                sample_count=sample_count,
            )

    if (
        off_comp is None
        or def_comp is None
        or split_comp is None
        or recent_comp is None
        or xg_comp is None
        or player_comp is None
    ):
        fq = "missing_required_data"
        if off_status == "insufficient_sample" or def_status == "insufficient_sample":
            fq = "insufficient_sample"
        elif split_status == "insufficient_split_sample":
            fq = "insufficient_split_sample"
        elif split_status == "missing_required_league_split_baseline":
            fq = "missing_required_league_split_baseline"
        elif recent_status == "insufficient_recent_sample":
            fq = "insufficient_recent_sample"
        elif recent_status == "missing_required_recent_league_baseline":
            fq = "missing_required_recent_league_baseline"
        elif xg_status == "insufficient_xg_sample":
            fq = "insufficient_xg_sample"
        elif xg_status == "missing_required_xg_league_baseline":
            fq = "missing_required_xg_league_baseline"
        elif player_status == "insufficient_player_profile_sample":
            fq = "insufficient_player_profile_sample"
        elif player_status == "missing_required_player_league_baseline":
            fq = "missing_required_player_league_baseline"
        return _fail_result(
            missing=all_missing,
            formula_quality_status=fq,
            sample_count=max(
                off_sample,
                def_sample,
                team_split_n,
                opp_split_n,
                team_recent_n,
                opp_recent_n,
                team_xg_n,
                opp_xg_n,
            ),
        )

    off_val = float(off_comp["value"])
    def_val = float(def_comp["value"])
    split_val = float(split_comp["value"])
    recent_val = float(recent_comp["value"])
    xg_val = float(xg_comp["value"])
    player_val = float(player_comp["value"])
    off_contrib = round2(off_val * FORMULA_OFFENSIVE_WEIGHT) or 0.0
    def_contrib = round2(def_val * FORMULA_DEFENSIVE_WEIGHT) or 0.0
    split_contrib = round2(split_val * FORMULA_SPLIT_WEIGHT) or 0.0
    recent_contrib = round2(recent_val * FORMULA_RECENT_WEIGHT) or 0.0
    xg_contrib = round2(xg_val * FORMULA_XG_WEIGHT) or 0.0
    player_contrib = round2(player_val * FORMULA_PLAYER_WEIGHT) or 0.0
    expected_sot = round2(
        off_val * FORMULA_OFFENSIVE_WEIGHT
        + def_val * FORMULA_DEFENSIVE_WEIGHT
        + split_val * FORMULA_SPLIT_WEIGHT
        + recent_val * FORMULA_RECENT_WEIGHT
        + xg_val * FORMULA_XG_WEIGHT
        + player_val * FORMULA_PLAYER_WEIGHT,
    ) or 0.0

    raw_json: dict[str, Any] = {
        "model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "architecture": V11_ARCHITECTURE,
        "model_stage": V11_MODEL_STAGE,
        "status": "ok",
        "prediction_valid": True,
        "expected_sot": expected_sot,
        "formula": {
            "type": "weighted_components",
            "terms_count": 6,
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
                {
                    "key": COMPONENT_KEY_SPLIT,
                    "label": COMPONENT_LABEL_SPLIT,
                    "value": split_val,
                    "weight": FORMULA_SPLIT_WEIGHT,
                    "contribution": split_contrib,
                    "status": "available",
                },
                {
                    "key": COMPONENT_KEY_RECENT,
                    "label": COMPONENT_LABEL_RECENT,
                    "value": recent_val,
                    "weight": FORMULA_RECENT_WEIGHT,
                    "contribution": recent_contrib,
                    "status": "available",
                },
                {
                    "key": COMPONENT_KEY_XG,
                    "label": COMPONENT_LABEL_XG,
                    "value": xg_val,
                    "weight": FORMULA_XG_WEIGHT,
                    "contribution": xg_contrib,
                    "status": "available",
                },
                {
                    "key": COMPONENT_KEY_PLAYER,
                    "label": COMPONENT_LABEL_PLAYER,
                    "value": player_val,
                    "weight": FORMULA_PLAYER_WEIGHT,
                    "contribution": player_contrib,
                    "status": "available",
                    "mode": "historical_recent_profile",
                },
            ],
            "final_sum": expected_sot,
        },
        "components": {
            COMPONENT_KEY_OFFENSIVE: off_comp,
            COMPONENT_KEY_DEFENSIVE: def_comp,
            COMPONENT_KEY_SPLIT: split_comp,
            "recent_form_component": recent_comp,
            COMPONENT_KEY_XG: xg_comp,
            COMPONENT_KEY_PLAYER: player_comp,
        },
        COMPONENT_KEY_OFFENSIVE: off_comp,
        COMPONENT_KEY_DEFENSIVE: def_comp,
        COMPONENT_KEY_SPLIT: split_comp,
        COMPONENT_KEY_RECENT: recent_comp,
        COMPONENT_KEY_XG: xg_comp,
        COMPONENT_KEY_PLAYER: player_comp,
        "formula_quality_status": "ok",
        "warnings": [],
        "sample_count": sample_count,
        "opponent_sample_count": def_sample,
        "team_split_sample_count": team_split_n,
        "opponent_split_sample_count": opp_split_n,
        "team_recent_window_n": team_recent_n,
        "opponent_recent_window_n": opp_recent_n,
        "team_xg_sample_n": team_xg_n,
        "opponent_xg_sample_n": opp_xg_n,
        "no_data_leakage": True,
    }

    return V11SideResult(
        valid=True,
        expected_sot=expected_sot,
        component=off_comp,
        defensive_component=def_comp,
        split_component=split_comp,
        recent_component=recent_comp,
        xg_component=xg_comp,
        player_layer_component=player_comp,
        raw_json=raw_json,
        missing_required_fields=[],
        formula_quality_status="ok",
        sample_count=sample_count,
    )
