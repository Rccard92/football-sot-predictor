"""Raccolta raw values per micro-variabili v2.1 dal contesto side."""

from __future__ import annotations

from typing import Callable

from app.services.predictions_v21.v21_constants import TOP_SHOOTERS_COUNT
from app.services.predictions_v21.v21_feature_context import V21SideContext
from app.services.predictions_v21.v21_manifest_definitions import V21MacroAreaSpec, V21MicroSpec
from app.services.predictions_v21.v21_normalization import (
    V21MicroResult,
    neutral_micro,
    normalize_ratio_direct,
    normalize_v21_micro_variable,
)
from app.services.sportapi.sportapi_lineup_present import to_display_role


def _top_shooters(ctx: V21SideContext) -> list:
    entries = sorted(
        ctx.profile_entries,
        key=lambda e: float(e.shots_on_target_per90 or 0.0),
        reverse=True,
    )
    return entries[:TOP_SHOOTERS_COUNT]


def _starter_names(ctx: V21SideContext) -> set[str]:
    starters = ctx.sportapi_side.get("starters") or []
    return {str(p.get("name") or "").strip().lower() for p in starters if isinstance(p, dict) and p.get("name")}


def _missing_names(ctx: V21SideContext) -> set[str]:
    mp = ctx.sportapi_side.get("missing_players") or {}
    names: set[str] = set()
    if isinstance(mp, dict):
        for grp in mp.values():
            if isinstance(grp, list):
                for p in grp:
                    if isinstance(p, dict) and p.get("name"):
                        names.add(str(p["name"]).strip().lower())
    return names


def _collect_offensive_production(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    agg = ctx.team_agg
    lb = ctx.league_baselines
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)

    if micro.key == "avg_sot_for":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("sot_mean"), baseline=lb.get("league_avg_sot_for"), sample_count=agg.get("sot_n"))
    if micro.key == "avg_total_shots_for":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("shots_mean"), baseline=lb.get("league_avg_total_shots_for"), sample_count=agg.get("shots_n"))
    if micro.key == "shot_accuracy":
        sot = agg.get("sot_mean")
        shots = agg.get("shots_mean")
        acc = (float(sot) / float(shots)) if sot is not None and shots and float(shots) > 0 else None
        base_acc = lb.get("league_avg_shot_accuracy")
        return normalize_v21_micro_variable(**kw, raw_value=acc, baseline=base_acc, sample_count=agg.get("sot_n"))
    if micro.key == "avg_inside_box_shots":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("inside_mean"), baseline=lb.get("league_avg_inside_box_shots_for"), sample_count=agg.get("inside_n"))
    if micro.key == "avg_outside_box_shots":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("outside_mean"), baseline=lb.get("league_avg_outside_box_shots_for"), sample_count=agg.get("outside_n"))
    if micro.key == "avg_blocked_shots":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("blocked_mean"), baseline=lb.get("league_avg_blocked_shots_for"), sample_count=agg.get("blocked_n"))
    if micro.key == "avg_off_target_shots":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("off_goal_mean"), baseline=lb.get("league_avg_shots_off_goal_for"), sample_count=agg.get("off_goal_n"))
    if micro.key == "avg_goals_for":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("goals_mean"), baseline=lb.get("league_avg_goals_for"), sample_count=agg.get("goals_n"))
    if micro.key == "offensive_trend":
        season = agg.get("sot_mean")
        recent = ctx.team_last5_agg.get("sot_mean")
        ratio = (float(recent) / float(season)) if recent is not None and season and float(season) > 0 else None
        return normalize_ratio_direct(**kw, ratio=ratio, sample_count=ctx.team_last5_agg.get("sot_n"), status="available" if ratio is not None else "missing")
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_opponent_defensive(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    agg = ctx.opp_conceded_agg
    lb = ctx.league_baselines
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)

    if micro.key == "opp_sot_conceded":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("sot_mean"), baseline=lb.get("league_avg_sot_conceded"), sample_count=agg.get("sot_n"))
    if micro.key == "opp_total_shots_conceded":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("shots_mean"), baseline=lb.get("league_avg_total_shots_conceded"), sample_count=agg.get("shots_n"))
    if micro.key == "opp_inside_box_conceded":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("inside_mean"), baseline=lb.get("league_avg_inside_box_shots_conceded"), sample_count=agg.get("inside_n"))
    if micro.key == "opp_outside_box_conceded":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("outside_mean"), baseline=lb.get("league_avg_outside_box_shots_conceded"), sample_count=agg.get("outside_n"))
    if micro.key == "opp_blocked_shots":
        return normalize_v21_micro_variable(**kw, raw_value=agg.get("blocked_mean"), baseline=lb.get("league_avg_blocked_shots_conceded"), sample_count=agg.get("blocked_n"))
    if micro.key == "opp_defensive_trend":
        season = agg.get("sot_mean")
        last5 = ctx.opp_last5_conceded_agg.get("sot_mean")
        ratio = (float(last5) / float(season)) if last5 is not None and season and float(season) > 0 else None
        return normalize_ratio_direct(**kw, ratio=ratio, sample_count=ctx.opp_last5_conceded_agg.get("sot_n"))
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_home_away_split(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    team_s = ctx.team_split_agg
    opp_s = ctx.opp_split_conceded_agg
    team_all = ctx.team_agg
    lb = ctx.league_baselines
    split_key = "home" if ctx.is_home else "away"
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)

    if micro.key == "split_sot_for":
        base = lb.get(f"{split_key}_league_split_avg_sot_for") or team_all.get("sot_mean")
        return normalize_v21_micro_variable(**kw, raw_value=team_s.get("sot_mean"), baseline=base, sample_count=team_s.get("sot_n"))
    if micro.key == "split_opp_sot_conceded":
        base = lb.get(f"{split_key}_league_split_avg_sot_conceded") or ctx.opp_conceded_agg.get("sot_mean")
        return normalize_v21_micro_variable(**kw, raw_value=opp_s.get("sot_mean"), baseline=base, sample_count=opp_s.get("sot_n"))
    if micro.key == "split_shots_for":
        base = lb.get(f"{split_key}_league_split_avg_total_shots_for") or team_all.get("shots_mean")
        return normalize_v21_micro_variable(**kw, raw_value=team_s.get("shots_mean"), baseline=base, sample_count=team_s.get("shots_n"))
    if micro.key == "split_shots_conceded":
        base = lb.get(f"{split_key}_league_split_avg_total_shots_conceded") or ctx.opp_conceded_agg.get("shots_mean")
        return normalize_v21_micro_variable(**kw, raw_value=opp_s.get("shots_mean"), baseline=base, sample_count=opp_s.get("shots_n"))
    if micro.key == "split_performance_delta":
        season_sot = team_all.get("sot_mean")
        split_sot = team_s.get("sot_mean")
        ratio = (float(split_sot) / float(season_sot)) if split_sot is not None and season_sot and float(season_sot) > 0 else None
        return normalize_ratio_direct(**kw, ratio=ratio, sample_count=team_s.get("sot_n"))
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_recent_form(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    t5 = ctx.team_last5_agg
    o5 = ctx.opp_last5_conceded_agg
    lb = ctx.league_baselines
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)

    if micro.key == "last5_sot_for":
        return normalize_v21_micro_variable(**kw, raw_value=t5.get("sot_mean"), baseline=lb.get("league_recent_avg_sot_for") or ctx.team_agg.get("sot_mean"), sample_count=t5.get("sot_n"))
    if micro.key == "last5_opp_sot_conceded":
        return normalize_v21_micro_variable(**kw, raw_value=o5.get("sot_mean"), baseline=lb.get("league_recent_avg_sot_conceded") or ctx.opp_conceded_agg.get("sot_mean"), sample_count=o5.get("sot_n"))
    if micro.key == "last5_shots_for":
        return normalize_v21_micro_variable(**kw, raw_value=t5.get("shots_mean"), baseline=lb.get("league_recent_avg_total_shots_for") or ctx.team_agg.get("shots_mean"), sample_count=t5.get("shots_n"))
    if micro.key == "last5_shots_conceded":
        return normalize_v21_micro_variable(**kw, raw_value=o5.get("shots_mean"), baseline=lb.get("league_recent_avg_total_shots_conceded") or ctx.opp_conceded_agg.get("shots_mean"), sample_count=o5.get("shots_n"))
    if micro.key == "last5_goals_for":
        return normalize_v21_micro_variable(**kw, raw_value=t5.get("goals_mean"), baseline=lb.get("league_recent_avg_goals_for") or ctx.team_agg.get("goals_mean"), sample_count=t5.get("goals_n"))
    if micro.key == "form_trend_vs_season":
        ratios: list[float] = []
        for k in ("sot_mean", "shots_mean"):
            season_v = ctx.team_agg.get(k)
            recent_v = t5.get(k)
            if season_v and recent_v is not None and float(season_v) > 0:
                ratios.append(float(recent_v) / float(season_v))
        ratio = sum(ratios) / len(ratios) if ratios else None
        return normalize_ratio_direct(**kw, ratio=ratio, sample_count=t5.get("sot_n"))
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_chance_quality(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)
    if not ctx.league_xg_available:
        return neutral_micro(**kw, status="missing", warning="xG non disponibile per questa competition")

    lb = ctx.league_baselines
    team_xg = ctx.team_agg.get("xg_mean")
    opp_xg = ctx.opp_conceded_agg.get("xg_mean")

    if micro.key == "xg_produced":
        return normalize_v21_micro_variable(**kw, raw_value=team_xg, baseline=lb.get("league_avg_xg_for"), sample_count=ctx.team_agg.get("xg_n"))
    if micro.key == "xg_conceded_by_opponent":
        return normalize_v21_micro_variable(**kw, raw_value=opp_xg, baseline=lb.get("league_avg_xg_conceded"), sample_count=ctx.opp_conceded_agg.get("xg_n"))
    if micro.key == "xg_delta_vs_league":
        if team_xg is None or lb.get("league_avg_xg_for") is None:
            return neutral_micro(**kw, status="missing", warning="Delta xG squadra non calcolabile")
        delta = float(team_xg) - float(lb["league_avg_xg_for"])
        return normalize_v21_micro_variable(**kw, raw_value=delta + float(lb["league_avg_xg_for"]), baseline=lb.get("league_avg_xg_for"), sample_count=ctx.team_agg.get("xg_n"))
    if micro.key == "opp_xg_conceded_delta":
        if opp_xg is None or lb.get("league_avg_xg_conceded") is None:
            return neutral_micro(**kw, status="missing", warning="Delta xG avversario non calcolabile")
        delta = float(opp_xg) - float(lb["league_avg_xg_conceded"])
        return normalize_v21_micro_variable(**kw, raw_value=delta + float(lb["league_avg_xg_conceded"]), baseline=lb.get("league_avg_xg_conceded"), sample_count=ctx.opp_conceded_agg.get("xg_n"))
    if micro.key == "xg_prudent_adjustment":
        if team_xg is None or opp_xg is None:
            return neutral_micro(**kw, status="missing")
        signal = (float(team_xg) + float(opp_xg)) / 2.0
        base = lb.get("league_avg_xg_for")
        return normalize_v21_micro_variable(**kw, raw_value=signal, baseline=base, sample_count=min(ctx.team_agg.get("xg_n") or 0, ctx.opp_conceded_agg.get("xg_n") or 0) or None)
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_player_layer(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)
    tops = _top_shooters(ctx)
    if not tops:
        return neutral_micro(**kw, status="missing", warning="Profili giocatori non disponibili")

    fallback = ctx.lineup_profiles_mode == "fallback_historical_profiles"
    fb_status = "fallback_historical_profiles" if fallback else "available"

    if micro.key == "top_sot_per90":
        vals = [float(e.shots_on_target_per90) for e in tops if e.shots_on_target_per90 is not None]
        raw = sum(vals) / len(vals) if vals else None
        base = ctx.team_agg.get("sot_mean")
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=base, sample_count=len(vals), status=fb_status, fallback_used=fallback)
    if micro.key == "top_shots_per90":
        vals = [float(e.shots_total_per90) for e in tops if e.shots_total_per90 is not None]
        raw = sum(vals) / len(vals) if vals else None
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=ctx.team_agg.get("shots_mean"), sample_count=len(vals), status=fb_status, fallback_used=fallback)
    if micro.key == "top_sot_share":
        vals = [float(e.team_sot_share_pct) for e in tops if e.team_sot_share_pct is not None]
        raw = sum(vals) / len(vals) if vals else None
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=50.0, sample_count=len(vals), status=fb_status, fallback_used=fallback)
    if micro.key == "top_shots_share":
        return neutral_micro(**kw, status="not_tracked_yet", warning="Quota tiri top player non tracciata in v2.1.0 engine")
    if micro.key == "offensive_recent_minutes":
        vals = [float(e.total_minutes) for e in tops if e.total_minutes is not None]
        raw = sum(vals) / len(vals) if vals else None
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=900.0, sample_count=len(vals), status=fb_status, fallback_used=fallback)
    if micro.key == "offensive_avg_rating":
        vals = [float(e.shooting_impact_score) for e in tops if e.shooting_impact_score is not None]
        raw = sum(vals) / len(vals) if vals else None
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=1.0, sample_count=len(vals), status=fb_status, fallback_used=fallback)
    if micro.key == "top_profile_reliability":
        vals = [float(e.reliability_score) for e in tops if e.reliability_score is not None]
        raw = sum(vals) / len(vals) if vals else None
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=70.0, sample_count=len(vals), status=fb_status, fallback_used=fallback)

    starters = _starter_names(ctx)
    missing = _missing_names(ctx)
    top_name = tops[0].name.strip().lower() if tops else ""

    if micro.key == "top_shooter_presence":
        present = 1.0 if top_name and top_name in starters else 0.0 if ctx.sportapi_audit.get("available") else None
        return normalize_v21_micro_variable(**kw, raw_value=present, baseline=1.0, sample_count=1 if present is not None else None, status="available" if present is not None else "missing")
    if micro.key == "player_layer_top_shooter_absence":
        absent = 1.0 if top_name and top_name in missing else 0.0 if missing or starters else None
        return normalize_v21_micro_variable(**kw, raw_value=absent, baseline=0.0 if absent is not None else None, sample_count=1 if absent is not None else None, status="available" if absent is not None else "missing", invert=True)
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_lineups(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)
    side = ctx.sportapi_side
    if not ctx.sportapi_audit.get("available"):
        return neutral_micro(**kw, status="missing", warning="Lineups SportAPI non disponibili")

    confirmed = side.get("confirmed")
    starters = side.get("starters") or []
    subs = side.get("substitutes") or []
    formation = side.get("formation")

    if micro.key == "official_lineup":
        raw = 1.0 if confirmed is True else 0.0
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=1.0, sample_count=1, status="partial" if confirmed is not True else "available", warning=None if confirmed is True else "Formazione non ufficiale (confirmed=false)")
    if micro.key == "confirmed_starters":
        raw = len(starters) / 11.0 if starters else 0.0
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=1.0, sample_count=len(starters))
    if micro.key == "bench":
        raw = float(len(subs))
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=7.0, sample_count=len(subs))
    if micro.key == "tactical_module":
        if not formation:
            return neutral_micro(**kw, status="missing")
        digits = [int(c) for c in str(formation) if c.isdigit()]
        raw = float(sum(digits)) if digits else None
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=10.0, sample_count=1)
    if micro.key == "module_change_vs_avg":
        return neutral_micro(**kw, status="not_tracked_yet", warning="Cambio modulo vs media non tracciato in prima versione engine")
    if micro.key == "attackers_starters":
        atk = sum(1 for p in starters if isinstance(p, dict) and to_display_role(p.get("position")) == "A")
        raw = atk / max(len(starters), 1)
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=0.25, sample_count=len(starters))
    if micro.key == "offensive_defensive_turnover":
        return neutral_micro(**kw, status="not_tracked_yet", warning="Turnover titolari non tracciato in prima versione engine")
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_injuries(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)
    mp = ctx.sportapi_side.get("missing_players") or {}
    if not isinstance(mp, dict):
        mp = {}
    injured = mp.get("injured") or []
    suspended = mp.get("suspended") or []
    other = mp.get("other") or []
    tops = _top_shooters(ctx)
    top_name = tops[0].name.strip().lower() if tops else ""
    missing = _missing_names(ctx)

    if micro.key == "injured":
        return normalize_v21_micro_variable(**kw, raw_value=float(len(injured)), baseline=1.0, sample_count=len(injured), status="partial" if injured else "available", invert=True)
    if micro.key == "suspended":
        return normalize_v21_micro_variable(**kw, raw_value=float(len(suspended)), baseline=0.0, sample_count=len(suspended), status="partial" if suspended else "available", invert=True)
    if micro.key == "unavailable":
        return normalize_v21_micro_variable(**kw, raw_value=float(len(other)), baseline=1.0, sample_count=len(other), status="partial", invert=True)
    if micro.key == "absent_player_weight":
        weights = [float(e.shots_on_target_per90 or 0) for e in tops if e.name.strip().lower() in missing]
        raw = sum(weights) if weights else 0.0
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=1.0, sample_count=len(weights), status="partial" if not ctx.sportapi_audit.get("available") else "available", invert=True)
    if micro.key == "starter_vs_bench_absence":
        return neutral_micro(**kw, status="not_tracked_yet")
    if micro.key == "injuries_top_shooter_absence":
        absent = 1.0 if top_name and top_name in missing else 0.0 if missing or ctx.sportapi_audit.get("available") else None
        return normalize_v21_micro_variable(**kw, raw_value=absent, baseline=0.0, sample_count=1 if absent is not None else None, invert=True)
    if micro.key == "key_defender_absence_opp":
        opp_mp = ctx.sportapi_opponent_side.get("missing_players") or {}
        opp_missing = []
        if isinstance(opp_mp, dict):
            for grp in opp_mp.values():
                if isinstance(grp, list):
                    opp_missing.extend(grp)
        defs = [p for p in opp_missing if isinstance(p, dict) and to_display_role(p.get("position")) == "D"]
        return normalize_v21_micro_variable(**kw, raw_value=float(len(defs)), baseline=0.0, sample_count=len(defs))
    if micro.key == "important_returns":
        return neutral_micro(**kw, status="not_tracked_yet")
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_pace_control(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    pace = ctx.team_pace_agg
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight, source_path=micro.source_path)

    if micro.key == "avg_possession":
        return normalize_v21_micro_variable(**kw, raw_value=pace.get("possession_mean"), baseline=50.0, sample_count=pace.get("possession_n"))
    if micro.key == "total_passes":
        return normalize_v21_micro_variable(**kw, raw_value=pace.get("passes_mean"), baseline=400.0, sample_count=pace.get("passes_n"))
    if micro.key == "passes_completed":
        return neutral_micro(**kw, status="not_tracked_yet", warning="Passaggi completati non aggregati separatamente")
    if micro.key == "pass_accuracy":
        return normalize_v21_micro_variable(**kw, raw_value=pace.get("pass_accuracy_mean"), baseline=80.0, sample_count=pace.get("pass_accuracy_n"))
    if micro.key == "territorial_control":
        return normalize_v21_micro_variable(**kw, raw_value=pace.get("territorial_control_index"), baseline=0.5, sample_count=pace.get("possession_n"))
    if micro.key == "estimated_pace":
        return normalize_v21_micro_variable(**kw, raw_value=pace.get("estimated_pace"), baseline=200.0, sample_count=pace.get("passes_n"))
    return neutral_micro(**kw, status="not_tracked_yet")


_MACRO_COLLECTORS: dict[str, Callable[[V21SideContext, V21MicroSpec], V21MicroResult]] = {
    "offensive_production": _collect_offensive_production,
    "opponent_defensive_resistance": _collect_opponent_defensive,
    "home_away_split": _collect_home_away_split,
    "recent_form": _collect_recent_form,
    "chance_quality": _collect_chance_quality,
    "player_layer": _collect_player_layer,
    "lineups": _collect_lineups,
    "injuries_unavailable": _collect_injuries,
    "pace_control": _collect_pace_control,
}


def collect_v21_micro_variables(
    macro_spec: V21MacroAreaSpec,
    ctx: V21SideContext,
) -> list[V21MicroResult]:
    collector = _MACRO_COLLECTORS.get(macro_spec.key)
    if collector is None:
        return [
            neutral_micro(
                key=m.key,
                label=m.label,
                micro_weight=m.micro_weight,
                source_path=m.source_path,
                status="not_tracked_yet",
            )
            for m in macro_spec.micros
        ]
    return [collector(ctx, m) for m in macro_spec.micros]
