"""Mapper feature pre-match per dataset calibrazione v3.1."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR,
)
from app.schemas.backtest_point_in_time import PointInTimeContextResponse
from app.services.backtest.round_analysis_report_builder import _iso
from app.services.backtest.round_analysis_v21_trace_helpers import (
    SPLIT_MACRO_ALIASES,
    macro_index,
)

V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V20 = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
V30 = BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR

MACRO_FEATURE_KEYS = (
    ("offensive_production_index", "offensive_production"),
    ("opponent_defensive_resistance_index", "opponent_defensive_resistance"),
    ("recent_form_index", "recent_form"),
    ("chance_quality_index", "chance_quality"),
    ("pace_control_index", "pace_control"),
    ("home_away_split_index", "home_away_split"),
    ("player_layer_index", "player_layer"),
    ("injuries_unavailable_index", "injuries_unavailable"),
    ("lineups_index", "lineups"),
)


def _round4(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 4)


def _status_ok(st: str | None) -> bool:
    return str(st or "").strip().lower() in ("ok", "available", "partial_low_sample")


def season_phase(round_number: int, max_round: int) -> str:
    if max_round <= 0:
        return "mid"
    third = max_round / 3.0
    if round_number <= third:
        return "early"
    if round_number <= 2 * third:
        return "mid"
    return "late"


def _team_raw_side(
    team_stats: Any,
    split_stats: Any,
    opponent_stats: Any,
    opponent_split: Any,
) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    last5 = team_stats.last5

    def _req(obj: Any, attr: str) -> float | None:
        if obj is None:
            missing.append(attr)
            return None
        val = getattr(obj, attr, None)
        if val is None:
            missing.append(attr)
        return _round4(val) if val is not None else None

    out = {
        "avg_sot_for": _req(team_stats, "avg_sot_for"),
        "avg_sot_against": _req(team_stats, "avg_sot_against"),
        "avg_total_shots_for": _req(team_stats, "avg_total_shots_for"),
        "avg_total_shots_against": _req(team_stats, "avg_total_shots_against"),
        "avg_xg_for": _req(team_stats, "avg_xg_for"),
        "avg_xg_against": _req(team_stats, "avg_xg_against"),
        "last5_avg_sot_for": _req(last5, "last5_avg_sot_for"),
        "last5_avg_sot_against": _req(last5, "last5_avg_sot_against"),
        "last5_avg_xg_for": _req(last5, "last5_avg_xg_for"),
        "last5_avg_xg_against": _req(last5, "last5_avg_xg_against"),
        "sample_count": int(team_stats.sample_count or 0),
        "last5_count": int(last5.last5_count or 0),
        "home_away_split_sot_for": _req(split_stats, "avg_sot_for"),
        "home_away_split_sot_against": _req(split_stats, "avg_sot_against"),
        "home_away_split_xg_for": _req(split_stats, "avg_xg_for"),
        "home_away_split_xg_against": _req(split_stats, "avg_xg_against"),
        "split_sample_count": int(split_stats.matches_count or 0) if split_stats else 0,
        "opponent_conceded_sot_avg": _req(opponent_stats, "avg_sot_against"),
        "opponent_conceded_xg_avg": _req(opponent_stats, "avg_xg_against"),
    }
    return out, list(dict.fromkeys(missing))


def map_team_raw_features(ctx: PointInTimeContextResponse) -> dict[str, Any]:
    home, mh = _team_raw_side(
        ctx.home_team_stats,
        ctx.home_split_stats,
        ctx.away_team_stats,
        ctx.away_split_stats,
    )
    away, ma = _team_raw_side(
        ctx.away_team_stats,
        ctx.away_split_stats,
        ctx.home_team_stats,
        ctx.home_split_stats,
    )
    return {"home": home, "away": away, "missing_fields": mh + ma}


def _share_top_starters(top_starters: list[dict[str, Any]], n: int) -> float | None:
    shares = [
        float(p.get("prior_team_sot_share"))
        for p in top_starters[:n]
        if p.get("prior_team_sot_share") is not None
    ]
    if not shares:
        return None
    return _round4(sum(shares))


def _player_layer_side(pl: Any | None) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    if pl is None:
        return {
            k: None
            for k in (
                "starting_xi_available",
                "starters_count",
                "avg_starter_sot_per90",
                "avg_starter_shots_per90",
                "total_starter_prior_sot",
                "total_starter_prior_shots",
                "top3_starter_sot_share",
                "top5_starter_sot_share",
                "bench_top_shooter_flag",
                "player_layer_index_existing",
                "player_layer_sample_count",
                "player_layer_coverage_pct",
                "mapped_players_count",
                "unmapped_players_count",
            )
        }, ["player_layer"]

    top = list(pl.top_starters or [])
    sot_vals = [p.get("prior_sot_per90") for p in top if p.get("prior_sot_per90") is not None]
    shot_vals = [p.get("prior_shots_per90") for p in top if p.get("prior_shots_per90") is not None]
    prior_sot = [p.get("prior_sot") for p in top if p.get("prior_sot") is not None]
    prior_shots = [p.get("prior_shots") for p in top if p.get("prior_shots") is not None]

    bench_flag = pl.top_shooter_presence_index is not None and float(pl.top_shooter_presence_index) < 0.99
    if "top_shooter_only_bench" in (pl.warnings or []):
        bench_flag = True

    mapped = unmapped = None
    if pl.mapping_coverage_pct is not None:
        mapped = int(round(float(pl.mapping_coverage_pct) * max(pl.starters_count, 1)))
        unmapped = max(0, int(pl.starters_count) - mapped)

    return {
        "starting_xi_available": pl.starters_count >= 11 and _status_ok(pl.status),
        "starters_count": int(pl.starters_count),
        "avg_starter_sot_per90": _round4(sum(sot_vals) / len(sot_vals)) if sot_vals else None,
        "avg_starter_shots_per90": _round4(sum(shot_vals) / len(shot_vals)) if shot_vals else None,
        "total_starter_prior_sot": int(sum(prior_sot)) if prior_sot else None,
        "total_starter_prior_shots": int(sum(prior_shots)) if prior_shots else None,
        "top3_starter_sot_share": _share_top_starters(top, 3),
        "top5_starter_sot_share": _share_top_starters(top, 5),
        "bench_top_shooter_flag": bench_flag,
        "player_layer_index_existing": _round4(pl.player_layer_index),
        "player_layer_sample_count": int(pl.starters_count),
        "player_layer_coverage_pct": _round4(pl.prior_stats_coverage_pct),
        "mapped_players_count": mapped,
        "unmapped_players_count": unmapped,
    }, missing


def map_player_layer(ctx: PointInTimeContextResponse) -> dict[str, Any]:
    home, mh = _player_layer_side(ctx.home_player_layer)
    away, ma = _player_layer_side(ctx.away_player_layer)
    return {"home": home, "away": away, "missing_fields": mh + ma}


def _component_float(components: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if k in components and components[k] is not None:
            try:
                return _round4(float(components[k]))
            except (TypeError, ValueError):
                pass
    return None


def _lineup_side(lm: Any | None) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    if lm is None:
        return {
            "lineup_available": False,
            "formation": None,
            "formation_family": None,
            "starters_count": None,
            "continuity_pct": None,
            "lineup_macro_existing": None,
            "formation_attack_index": None,
            "formation_width_index": None,
            "formation_defensive_risk_index": None,
            "source_fixture_id": None,
            "mapping_coverage_pct": None,
        }, ["lineups"]

    comp = dict(lm.components or {})
    continuity = lm.previous_xi_overlap_pct
    return {
        "lineup_available": _status_ok(lm.status) and int(lm.starters_count or 0) > 0,
        "formation": lm.formation,
        "formation_family": comp.get("formation_family") if "formation_family" in comp else None,
        "starters_count": int(lm.starters_count or 0),
        "continuity_pct": _round4(continuity) if continuity is not None else None,
        "lineup_macro_existing": _round4(lm.lineup_macro_index),
        "formation_attack_index": _component_float(
            comp,
            "formation_attack_index",
            "attack_index",
        ),
        "formation_width_index": _component_float(comp, "formation_width_index", "width_index"),
        "formation_defensive_risk_index": _component_float(
            comp,
            "formation_defensive_risk_index",
            "defensive_risk_index",
        ),
        "source_fixture_id": lm.source_fixture_id,
        "mapping_coverage_pct": None,
    }, missing


def map_lineups(ctx: PointInTimeContextResponse) -> dict[str, Any]:
    home, mh = _lineup_side(ctx.home_lineup_macro)
    away, ma = _lineup_side(ctx.away_lineup_macro)
    return {"home": home, "away": away, "missing_fields": mh + ma}


def _top_absent_players(um: Any | None, max_n: int = 5) -> list[dict[str, Any]]:
    if um is None:
        return []
    players: list[dict[str, Any]] = []
    detail = um.unavailable_macro_detail
    if detail and detail.players:
        for p in detail.players[:max_n]:
            players.append(
                {
                    "player_name": p.player_name,
                    "status": p.status,
                    "role": p.role,
                    "prior_sot": p.prior_sot,
                    "prior_shots": p.prior_shots,
                    "prior_sot_per90": p.prior_sot_per90,
                    "prior_shots_per90": p.prior_shots_per90,
                    "team_sot_share": p.team_sot_share,
                    "impact_score": p.impact_score,
                    "is_important_absence": p.is_important_absence,
                    "mapping_status": p.mapping_status,
                },
            )
        return players
    for brief in (um.important_absences or [])[:max_n]:
        players.append(
            {
                "player_name": brief.player_name,
                "status": None,
                "role": brief.role,
                "prior_sot": None,
                "prior_shots": None,
                "prior_sot_per90": brief.prior_sot_per90,
                "prior_shots_per90": None,
                "team_sot_share": brief.prior_team_sot_share,
                "impact_score": brief.offensive_absence_score,
                "is_important_absence": True,
                "mapping_status": brief.mapping_status,
            },
        )
    return players


def _unavailable_side(um: Any | None) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    if um is None:
        return {
            "unavailable_count": None,
            "injured_count": None,
            "suspended_count": None,
            "important_absences_count": None,
            "unavailable_sot_share_lost": None,
            "unavailable_shots_share_lost": None,
            "unavailable_minutes_share_lost": None,
            "unavailable_macro_existing": None,
            "top_absent_players": [],
        }, ["unavailable"]

    comp = dict(um.components or {})
    return {
        "unavailable_count": int(um.unavailable_count),
        "injured_count": int(um.injured_count),
        "suspended_count": int(um.suspended_count),
        "important_absences_count": len(um.important_absences or []),
        "unavailable_sot_share_lost": comp.get("unavailable_sot_share_lost"),
        "unavailable_shots_share_lost": comp.get("unavailable_shots_share_lost"),
        "unavailable_minutes_share_lost": comp.get("unavailable_minutes_share_lost"),
        "unavailable_macro_existing": _round4(um.unavailable_macro_index),
        "top_absent_players": _top_absent_players(um),
    }, missing


def map_unavailable(ctx: PointInTimeContextResponse) -> dict[str, Any]:
    home, mh = _unavailable_side(ctx.home_unavailable_macro)
    away, ma = _unavailable_side(ctx.away_unavailable_macro)
    return {"home": home, "away": away, "missing_fields": mh + ma}


def _macro_side_from_explanation(side_data: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for export_key, macro_key in MACRO_FEATURE_KEYS:
        out[export_key] = _round4(macro_index(side_data, macro_key, aliases=SPLIT_MACRO_ALIASES if macro_key == "home_away_split" else ()))
    wmm = None
    if isinstance(side_data, dict):
        wmm = side_data.get("weighted_macro_multiplier")
        if wmm is None and isinstance(side_data.get("macros"), list):
            for m in side_data["macros"]:
                if isinstance(m, dict) and m.get("key") == "weighted_macro_multiplier":
                    wmm = m.get("value") or m.get("macro_index")
    out["weighted_macro_multiplier"] = _round4(float(wmm)) if wmm is not None else None
    return out


def map_existing_macro_features(
    ctx: PointInTimeContextResponse,
    explanation_v21: dict[str, Any] | None,
) -> dict[str, Any]:
    home_expl = (explanation_v21 or {}).get("home") if isinstance(explanation_v21, dict) else None
    away_expl = (explanation_v21 or {}).get("away") if isinstance(explanation_v21, dict) else None
    if isinstance(home_expl, dict) and isinstance(away_expl, dict):
        return {
            "home": _macro_side_from_explanation(home_expl),
            "away": _macro_side_from_explanation(away_expl),
            "missing_fields": [],
            "source": "explanation_v21_macros",
        }
    return {
        "home": {k: None for k, _ in MACRO_FEATURE_KEYS} | {"weighted_macro_multiplier": None},
        "away": {k: None for k, _ in MACRO_FEATURE_KEYS} | {"weighted_macro_multiplier": None},
        "missing_fields": ["existing_macro_features"],
        "source": "missing",
    }


def map_league_context(ctx: PointInTimeContextResponse, max_round: int) -> dict[str, Any]:
    lb = ctx.league_baselines
    rn = 0
    try:
        rn = int(ctx.fixture_round or 0)
    except (TypeError, ValueError):
        rn = 0
    return {
        "league_avg_sot_for": _round4(lb.league_avg_sot_for),
        "league_avg_sot_against": _round4(lb.league_avg_sot_against),
        "league_avg_total_shots": _round4(lb.league_avg_total_shots),
        "league_avg_xg_for": _round4(lb.league_avg_xg_for),
        "league_avg_xg_against": _round4(lb.league_avg_xg_conceded),
        "league_sample_count": int(lb.sample_count or 0),
        "round_number": rn,
        "season_phase": season_phase(rn, max_round),
    }


def map_data_quality(ctx: PointInTimeContextResponse, extra_missing: list[str]) -> dict[str, Any]:
    missing = list(dict.fromkeys(list(ctx.missing_variables or []) + extra_missing))
    fallbacks = list(ctx.fallback_variables or [])
    warnings = list(ctx.warnings or [])

    def _layer_status(obj: Any | None) -> str:
        if obj is None:
            return "missing"
        return str(getattr(obj, "status", "missing") or "missing")

    return {
        "team_stats_status": (
            "ok"
            if ctx.home_team_stats.sample_count > 0 and ctx.away_team_stats.sample_count > 0
            else "partial"
        ),
        "xg_status": "ok" if ctx.league_baselines.league_avg_xg_for is not None else "missing",
        "split_status": (
            "ok"
            if ctx.home_split_stats.status == "available" and ctx.away_split_stats.status == "available"
            else str(ctx.home_split_stats.status)
        ),
        "player_layer_status": _layer_status(ctx.home_player_layer),
        "lineup_status": _layer_status(ctx.home_lineup_macro),
        "unavailable_status": _layer_status(ctx.home_unavailable_macro),
        "mapping_status": "ok" if "mapping" not in missing else "missing",
        "fallback_count": len(fallbacks),
        "warning_count": len(warnings),
        "warnings": warnings,
        "missing_fields": missing,
        "actuals_used_as_input": False,
        "leakage_guard": bool(ctx.leakage_guard),
    }


def map_metadata(
    ctx: PointInTimeContextResponse,
    *,
    competition_id: int,
    season_year: int,
    round_number: int,
) -> dict[str, Any]:
    return {
        "fixture_id": int(ctx.fixture_id),
        "round_number": int(round_number),
        "kickoff_at": _iso(ctx.fixture_kickoff_at),
        "home_team_id": int(ctx.home_team_id),
        "home_team_name": ctx.home_team_name,
        "away_team_id": int(ctx.away_team_id),
        "away_team_name": ctx.away_team_name,
        "competition_id": int(competition_id),
        "season_year": int(season_year),
        "mode": ctx.mode,
        "leakage_guard": bool(ctx.leakage_guard),
        "cutoff_time": _iso(ctx.cutoff_time),
    }


def map_target(ctx: PointInTimeContextResponse) -> dict[str, Any]:
    a = ctx.actuals_for_scoring
    return {
        "actual_home_sot": a.actual_home_sot,
        "actual_away_sot": a.actual_away_sot,
        "actual_total_sot": a.actual_total_sot,
        "final_score": a.final_score,
        "fixture_status": a.fixture_status or ctx.fixture_status,
    }


def map_comparisons(models_json: dict[str, Any]) -> dict[str, Any]:
    v11 = models_json.get(V11) if isinstance(models_json.get(V11), dict) else {}
    v20 = models_json.get(V20) if isinstance(models_json.get(V20), dict) else {}
    v21 = models_json.get(V21) if isinstance(models_json.get(V21), dict) else {}
    v30 = models_json.get(V30) if isinstance(models_json.get(V30), dict) else {}
    trace = v30.get("trace_summary") if isinstance(v30.get("trace_summary"), dict) else {}
    sel = trace.get("selection") if isinstance(trace.get("selection"), dict) else {}

    return {
        "allowed_for_v31_training": False,
        "comparisons_are_not_features": True,
        "v1_1_predicted_total": v11.get("predicted_total_sot"),
        "v2_0_predicted_total": v20.get("predicted_total_sot"),
        "v2_1_predicted_total": v21.get("predicted_total_sot"),
        "v3_0_decision": v30.get("cautious_advice") or sel.get("decision"),
        "v3_0_selected_line": v30.get("cautious_line") or sel.get("line"),
        "v3_0_outcome": v30.get("cautious_outcome"),
    }


def build_features_bundle(
    ctx: PointInTimeContextResponse,
    *,
    explanation_v21: dict[str, Any] | None,
    max_round: int,
) -> dict[str, Any]:
    team = map_team_raw_features(ctx)
    player = map_player_layer(ctx)
    lineups = map_lineups(ctx)
    unavailable = map_unavailable(ctx)
    macros = map_existing_macro_features(ctx, explanation_v21)
    league = map_league_context(ctx, max_round)

    all_missing: list[str] = []
    for part in (team, player, lineups, unavailable, macros):
        all_missing.extend(part.pop("missing_fields", []))

    dq = map_data_quality(ctx, all_missing)
    features = {
        "team_raw_features": {"home": team["home"], "away": team["away"]},
        "player_layer": {"home": player["home"], "away": player["away"]},
        "lineups": {"home": lineups["home"], "away": lineups["away"]},
        "unavailable": {"home": unavailable["home"], "away": unavailable["away"]},
        "existing_macro_features": {
            "home": macros["home"],
            "away": macros["away"],
        },
        "league_context": league,
        "data_quality": dq,
    }
    return {"features": features}
