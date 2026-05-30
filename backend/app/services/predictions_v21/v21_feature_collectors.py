"""Raccolta raw values per micro-variabili v2.1 dal contesto side."""

from __future__ import annotations

from typing import Callable

from app.services.predictions_common.xg_strict_helpers import V21_XG_SOURCE_PATHS, v21_norm_from_strict_snapshot
from app.services.predictions_v21.v21_constants import TOP_SHOOTERS_COUNT, XG_PRUDENT_ADJ_MAX, XG_PRUDENT_ADJ_MIN
from app.services.predictions_v21.v21_feature_context import V21SideContext
from app.services.predictions_v21.v21_lineup_history import lineup_history_sufficient
from app.services.predictions_v21.v21_lineup_impact_helpers import (
    important_returns_score,
    injuries_top_shooter_absence_score,
    missing_api_ids,
    missing_name_set,
    player_layer_top_shooter_absence_score,
    starter_api_ids,
    starter_vs_bench_absence_score,
)
from app.services.predictions_v21.v21_manifest_definitions import V21MacroAreaSpec, V21MicroSpec
from app.services.predictions_v21.v21_xg_coverage import XG_MISSING_WARNING
from app.services.predictions_v21.v21_normalization import (
    V21MicroResult,
    clamp_micro_norm,
    neutral_micro,
    normalize_ratio_direct,
    normalize_v21_micro_variable,
)
from app.services.sportapi.sportapi_lineup_present import to_display_role


def _micro_kw(micro: V21MicroSpec, *, source_path: str | None = None) -> dict:
    return dict(
        key=micro.key,
        label=micro.label,
        micro_weight=micro.micro_weight,
        source_path=source_path if source_path is not None else micro.source_path,
    )


def _top_shooters(ctx: V21SideContext) -> list:
    entries = sorted(
        ctx.profile_entries,
        key=lambda e: (
            float(e.shots_on_target_per90 or 0.0),
            float(e.team_sot_share_pct or 0.0),
            float(e.shooting_impact_score or 0.0),
            float(e.reliability_score or 0.0),
        ),
        reverse=True,
    )
    return entries[:TOP_SHOOTERS_COUNT]


def _starter_names(ctx: V21SideContext) -> set[str]:
    starters = ctx.sportapi_side.get("starters") or []
    names: set[str] = set()
    for p in starters:
        if isinstance(p, dict):
            n = str(p.get("player_name") or p.get("name") or "").strip().lower()
            if n:
                names.add(n)
    return names


def _missing_names(ctx: V21SideContext) -> set[str]:
    return missing_name_set(ctx)


def _normalize_formation_label(formation: str | None) -> str | None:
    if not formation:
        return None
    cleaned = str(formation).strip().replace(" ", "")
    return cleaned or None


def _collect_offensive_production(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    agg = ctx.team_agg
    lb = ctx.league_baselines
    kw = _micro_kw(micro)

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
    kw = _micro_kw(micro)

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
    kw = _micro_kw(micro)

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
    kw = _micro_kw(micro)

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
    kw = dict(key=micro.key, label=micro.label, micro_weight=micro.micro_weight)
    snap = ctx.strict_xg
    trace_latest = (ctx.xg_leakage_trace or {}).get("latest_fixture_used_at") or (
        snap.latest_fixture_used_at if snap else None
    )
    trace_leakage = True

    if snap is None or not ctx.league_xg_available:
        return neutral_micro(
            **kw,
            source_path="feed_unavailable.xg",
            status="feed_unavailable",
            fallback_used=True,
            warning=XG_MISSING_WARNING,
        )

    if snap.status in ("missing_required_xg_league_baseline", "missing_required_data"):
        return neutral_micro(
            **kw,
            source_path=V21_XG_SOURCE_PATHS.get(micro.key, micro.source_path),
            status="missing",
            warning="; ".join(snap.warnings) if snap.warnings else "Dati xG strict non disponibili",
        )

    low_sample = snap.status == "insufficient_xg_sample"
    eff_status = "partial_low_sample" if low_sample else "available"
    eff_warning = snap.warnings[0] if low_sample and snap.warnings else None
    sample_use = min(snap.team_xg_n, snap.opp_xg_n) or None
    source_path = V21_XG_SOURCE_PATHS.get(micro.key, micro.source_path)

    raw_map = {
        "xg_produced": snap.avg_xg_for,
        "xg_conceded_by_opponent": snap.opponent_avg_xg_conceded,
        "xg_delta_vs_league": snap.team_xg_delta_vs_league,
        "opp_xg_conceded_delta": snap.opponent_xg_conceded_delta_vs_league,
        "xg_prudent_adjustment": snap.xg_adjustment_pct,
    }
    raw_value = raw_map.get(micro.key)
    if raw_value is None:
        return neutral_micro(
            **kw,
            source_path=source_path,
            status="missing",
            warning=f"Dato non disponibile per {micro.label}",
        )

    ratio = v21_norm_from_strict_snapshot(snap, micro.key)
    if ratio is None:
        return neutral_micro(
            **kw,
            source_path=source_path,
            status="missing",
            warning=f"Normalizzazione xG non calcolabile per {micro.label}",
        )

    if micro.key == "xg_prudent_adjustment":
        norm = clamp_micro_norm(float(ratio), norm_min=XG_PRUDENT_ADJ_MIN, norm_max=XG_PRUDENT_ADJ_MAX)
    else:
        norm = clamp_micro_norm(float(ratio))

    if norm > 1.02:
        contrib = "positiva"
    elif norm < 0.98:
        contrib = "negativa"
    else:
        contrib = "neutra"

    sample_count = sample_use
    if micro.key == "xg_produced":
        sample_count = snap.team_xg_n or sample_use
    elif micro.key == "xg_conceded_by_opponent":
        sample_count = snap.opp_xg_n or sample_use
    elif micro.key in ("xg_delta_vs_league", "opp_xg_conceded_delta", "xg_prudent_adjustment"):
        sample_count = sample_use

    return V21MicroResult(
        key=micro.key,
        label=micro.label,
        micro_weight=micro.micro_weight,
        source_path=source_path,
        raw_value=round(float(raw_value), 4),
        normalized_value=round(norm, 4),
        status=eff_status,
        sample_count=sample_count,
        fallback_used=False,
        contribution=contrib,
        warning=eff_warning,
        latest_fixture_used_at=trace_latest,
        leakage_guard=trace_leakage,
    )


def _collect_player_layer(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    kw = _micro_kw(micro)
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
        share_vals = [float(e.team_shots_share_pct) for e in tops if e.team_shots_share_pct is not None]
        raw = sum(share_vals) / len(share_vals) if share_vals else None
        if raw is None:
            shots_vals = [float(e.shots_total) for e in tops if e.shots_total is not None]
            team_shots = ctx.team_agg.get("shots_mean")
            if shots_vals and team_shots and float(team_shots) > 0:
                raw = sum(shots_vals) / float(team_shots)
        if raw is None:
            return neutral_micro(
                **kw,
                status="missing",
                warning="Quota tiri top player: total_shots squadra non disponibile",
            )
        return normalize_v21_micro_variable(
            **kw,
            raw_value=raw,
            baseline=50.0,
            sample_count=len(tops),
            status=fb_status,
            fallback_used=fallback,
        )
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
        if not tops:
            return neutral_micro(
                **kw,
                status="missing_dependency",
                fallback_used=True,
                warning="Assenza top shooter: profili giocatori non disponibili.",
            )
        if not ctx.sportapi_audit.get("available") and ctx.lineup_profiles_mode != "fallback_historical_profiles":
            return neutral_micro(
                **kw,
                status="missing_dependency",
                fallback_used=True,
                warning="Assenza top shooter: lineups non disponibili.",
            )
        score = player_layer_top_shooter_absence_score(ctx, tops)
        if score is None:
            return neutral_micro(
                **kw,
                status="missing_dependency",
                fallback_used=True,
                warning="Assenza top shooter non calcolabile: dipendenze mancanti.",
            )
        return normalize_v21_micro_variable(
            **kw,
            raw_value=score,
            baseline=1.0,
            sample_count=len(tops),
            status="available",
            invert=True,
        )
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_lineups(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    kw = _micro_kw(micro)
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
        hist = ctx.lineup_history
        if not lineup_history_sufficient(hist):
            return neutral_micro(
                **kw,
                status="missing",
                warning="Storico formazioni insufficiente per cambio modulo vs media",
            )
        current = _normalize_formation_label(formation)
        dominant = _normalize_formation_label(hist.get("dominant_formation"))
        if not current or not dominant:
            return neutral_micro(**kw, status="missing", warning="Modulo attuale o storico non disponibile")
        raw = 1.0 if current != dominant else 0.0
        return normalize_v21_micro_variable(
            **kw,
            raw_value=raw,
            baseline=1.0,
            sample_count=int(hist.get("lineup_fixture_count") or 0),
            status="available",
        )
    if micro.key == "attackers_starters":
        atk = sum(1 for p in starters if isinstance(p, dict) and to_display_role(p.get("position")) == "A")
        raw = atk / max(len(starters), 1)
        return normalize_v21_micro_variable(**kw, raw_value=raw, baseline=0.25, sample_count=len(starters))
    if micro.key == "offensive_defensive_turnover":
        hist = ctx.lineup_history
        typical = hist.get("typical_starter_api_ids") or set()
        current_ids = starter_api_ids(ctx)
        if not current_ids:
            return neutral_micro(**kw, status="missing", warning="Titolari correnti non disponibili")
        partial_warning = "Storico lineups insufficiente, turnover stimato con profili/minuti."
        if not typical:
            status = "fallback_partial"
            turnover = 0.5
            return normalize_v21_micro_variable(
                **kw,
                raw_value=turnover,
                baseline=0.3,
                sample_count=len(current_ids),
                status=status,
                warning=partial_warning,
            )
        overlap = len(current_ids & set(typical))
        turnover = 1.0 - (overlap / 11.0)
        status = "available" if lineup_history_sufficient(hist) else "fallback_partial"
        return normalize_v21_micro_variable(
            **kw,
            raw_value=round(turnover, 4),
            baseline=0.3,
            sample_count=int(hist.get("lineup_fixture_count") or len(current_ids)),
            status=status,
            warning=partial_warning if status == "fallback_partial" else None,
        )
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_injuries(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    kw = _micro_kw(micro)
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
        score = starter_vs_bench_absence_score(ctx)
        if score is None:
            return neutral_micro(**kw, status="missing", warning="Assenza titolare vs panchinaro non calcolabile")
        return normalize_v21_micro_variable(
            **kw,
            raw_value=score,
            baseline=1.0,
            sample_count=len(missing_api_ids(ctx)),
            status="available" if ctx.sportapi_audit.get("available") else "partial",
            invert=True,
        )
    if micro.key == "injuries_top_shooter_absence":
        if not tops:
            return neutral_micro(
                **kw,
                status="missing_dependency",
                fallback_used=True,
                warning="Assenza top shooter per infortuni: profili non disponibili.",
            )
        score = injuries_top_shooter_absence_score(ctx, tops)
        if score is None:
            return neutral_micro(
                **kw,
                status="missing_dependency",
                fallback_used=True,
                warning="Assenza top shooter per infortuni non calcolabile.",
            )
        return normalize_v21_micro_variable(
            **kw,
            raw_value=score,
            baseline=1.0,
            sample_count=len(tops),
            status="available" if ctx.sportapi_audit.get("available") else "partial",
            invert=True,
        )
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
        score, status, warning = important_returns_score(ctx)
        if score is None:
            return neutral_micro(**kw, status=status, warning=warning)  # type: ignore[arg-type]
        return normalize_v21_micro_variable(
            **kw,
            raw_value=score,
            baseline=0.5,
            sample_count=1,
            status=status,  # type: ignore[arg-type]
            warning=warning,
        )
    return neutral_micro(**kw, status="not_tracked_yet")


def _collect_pace_control(ctx: V21SideContext, micro: V21MicroSpec) -> V21MicroResult:
    pace = ctx.team_pace_agg
    kw = _micro_kw(micro)

    if micro.key == "avg_possession":
        return normalize_v21_micro_variable(**kw, raw_value=pace.get("possession_mean"), baseline=50.0, sample_count=pace.get("possession_n"))
    if micro.key == "total_passes":
        return normalize_v21_micro_variable(**kw, raw_value=pace.get("passes_mean"), baseline=400.0, sample_count=pace.get("passes_n"))
    if micro.key == "passes_completed":
        raw = pace.get("passes_completed_mean")
        src = pace.get("passes_completed_source") or "derived"
        if raw is None:
            return neutral_micro(
                **kw,
                status="missing",
                warning="Passaggi riusciti non calcolabili (passaggi totali/precisione assenti)",
            )
        eff_status = "available" if src == "column" else "available_derived"
        eff_source = (
            "team_stats.season_avg_passes_completed"
            if src == "column"
            else "derived.passes_total_x_pass_accuracy"
        )
        return normalize_v21_micro_variable(
            **_micro_kw(micro, source_path=eff_source),
            raw_value=raw,
            baseline=pace.get("passes_mean") or 350.0,
            sample_count=pace.get("passes_completed_n"),
            status=eff_status,
        )
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
