"""Player layer v1.1 — profili storici/recent o lineup-adjusted (stage 7B), nessun fallback."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, PlayerRegistry, PlayerSeasonProfile, PlayerTeamSeason, Season, Team
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.player_layer_feature_sources import (
    COMPONENT_KEY_PLAYER,
    COMPONENT_LABEL_PLAYER,
    LEAGUE_PLAYER_BASELINE_FIELD_MAP,
    LINEUP_INTERNAL_WEIGHTS,
    LINEUP_LEAGUE_BASELINE_FIELD_MAP,
    LINEUP_NUMERIC_INPUT_ORDER,
    PLAYER_INPUT_API_SOURCES,
    PLAYER_INPUT_DB_FIELDS,
    PLAYER_INPUT_LABELS,
    PLAYER_INPUT_ORDER,
    PLAYER_INPUT_SOURCE_PATHS,
    PLAYER_INTERNAL_WEIGHTS,
    PLAYER_LAYER_MODE_HISTORICAL,
    PLAYER_LAYER_MODE_LINEUP,
    PLAYER_LINEUP_CONTEXT_INPUT_ORDER,
    PLAYER_NUMERIC_INPUT_ORDER,
    REQUIRED_LEAGUE_PLAYER_KEYS,
    TOP_SHOOTER_ABSENCE_AUDIT_NOTE,
)
from app.services.predictions_v11.player_layer_lineup_helpers import (
    LINEUP_STARTERS_PROFILE_WARNING_THRESHOLD,
    classify_top_shooters_in_lineup,
    fixture_both_lineups_available,
    lineup_presence_absence_signals,
    load_fixture_for_lineup,
    load_lineup_players_by_role,
    load_team_lineup_for_fixture,
    normalize_absence_signal,
    normalize_presence_signal,
    profile_map_for_team,
    select_top_shooter_api_ids,
    starter_has_offensive_profile,
)
from app.services.predictions_v11.v11_shared import (
    missing_field,
    round2,
    round4,
    safe_float,
)
from app.services.sot_feature_registry import (
    V11_MIN_PLAYER_MINUTES,
    V11_MIN_PLAYER_PROFILE_PLAYERS,
    V11_TOP_PLAYERS_USED,
)


class MissingPlayerLeagueBaselineError(Exception):
    def __init__(self, missing_keys: list[str]) -> None:
        self.missing_keys = missing_keys
        super().__init__(f"missing_player_league_baseline:{','.join(missing_keys)}")


@dataclass
class _ProfileRow:
    profile: PlayerSeasonProfile
    name: str
    position: str | None


def _float_from_decimal(v: Decimal | float | int | None) -> float | None:
    return safe_float(v)


def _is_eligible(p: PlayerSeasonProfile) -> bool:
    mins = p.minutes_total
    if mins is None or float(mins) < V11_MIN_PLAYER_MINUTES:
        return False
    if p.reliability_score is None:
        return False
    if p.shots_on_per90 is None and p.shots_total_per90 is None:
        return False
    return True


def _sort_key(p: PlayerSeasonProfile) -> tuple:
    impact = _float_from_decimal(p.shooting_impact_score)
    sot90 = _float_from_decimal(p.shots_on_per90)
    mins = _float_from_decimal(p.minutes_total)
    return (
        impact is None,
        -(impact or 0.0),
        -(sot90 or 0.0),
        -(mins or 0.0),
    )


def select_top_player_profiles(profiles: list[_ProfileRow], *, limit: int = V11_TOP_PLAYERS_USED) -> list[_ProfileRow]:
    eligible = [r for r in profiles if _is_eligible(r.profile)]
    eligible.sort(key=lambda r: _sort_key(r.profile))
    return eligible[:limit]


def _avg_field(rows: list[_ProfileRow], getter) -> float | None:
    vals: list[float] = []
    for r in rows:
        fv = _float_from_decimal(getter(r))
        if fv is not None:
            vals.append(float(fv))
    if not vals:
        return None
    return sum(vals) / len(vals)


def team_signals_from_top(top: list[_ProfileRow]) -> dict[str, float | None]:
    return {
        "top_players_sot_per90_signal": _avg_field(top, lambda r: r.profile.shots_on_per90),
        "top_players_shots_per90_signal": _avg_field(top, lambda r: r.profile.shots_total_per90),
        "top_players_sot_share_signal": _avg_field(top, lambda r: r.profile.team_sot_share),
        "top_players_shots_share_signal": _avg_field(top, lambda r: r.profile.team_shots_share),
        "top_players_recent_minutes_signal": _avg_field(top, lambda r: r.profile.recent_minutes_last5),
        "top_players_rating_signal": _avg_field(top, lambda r: r.profile.avg_rating),
        "top_players_reliability_signal": _avg_field(top, lambda r: r.profile.reliability_score),
    }


def team_signals_from_starters(starters: list[_ProfileRow]) -> dict[str, float | None]:
    return {
        "starters_sot_per90_signal": _avg_field(starters, lambda r: r.profile.shots_on_per90),
        "starters_shots_per90_signal": _avg_field(starters, lambda r: r.profile.shots_total_per90),
        "starters_sot_share_signal": _avg_field(starters, lambda r: r.profile.team_sot_share),
        "starters_shots_share_signal": _avg_field(starters, lambda r: r.profile.team_shots_share),
        "starters_recent_minutes_signal": _avg_field(starters, lambda r: r.profile.recent_minutes_last5),
        "starters_rating_signal": _avg_field(starters, lambda r: r.profile.avg_rating),
        "starters_reliability_signal": _avg_field(starters, lambda r: r.profile.reliability_score),
    }


def _scale_to_sot(team_val: float | None, league_player_avg: float | None, league_sot_for: float) -> float | None:
    if team_val is None or league_player_avg is None or league_player_avg <= 0:
        return None
    return float(team_val) * float(league_sot_for) / float(league_player_avg)


def _pack_top_player(r: _ProfileRow) -> dict[str, Any]:
    p = r.profile
    return {
        "api_player_id": int(p.api_player_id),
        "name": r.name,
        "position": r.position,
        "minutes_total": _float_from_decimal(p.minutes_total),
        "recent_minutes_last5": _float_from_decimal(p.recent_minutes_last5),
        "shots_on_per90": _float_from_decimal(p.shots_on_per90),
        "shots_total_per90": _float_from_decimal(p.shots_total_per90),
        "team_sot_share": _float_from_decimal(p.team_sot_share),
        "team_shots_share": _float_from_decimal(p.team_shots_share),
        "avg_rating": _float_from_decimal(p.avg_rating),
        "shooting_impact_score": _float_from_decimal(p.shooting_impact_score),
        "reliability_score": int(p.reliability_score) if p.reliability_score is not None else None,
        "is_starter": r.position is not None and getattr(r, "_is_starter", False),
    }


def _pack_starter_player(r: _ProfileRow) -> dict[str, Any]:
    row = _pack_top_player(r)
    row["is_starter"] = True
    return row


def load_team_profile_rows(
    db: Session,
    *,
    season_year: int,
    league_id: int,
    api_team_id: int,
) -> list[_ProfileRow]:
    rows = db.execute(
        select(PlayerSeasonProfile, PlayerRegistry, PlayerTeamSeason.position)
        .join(PlayerRegistry, PlayerRegistry.id == PlayerSeasonProfile.player_id)
        .outerjoin(
            PlayerTeamSeason,
            (PlayerTeamSeason.season == PlayerSeasonProfile.season)
            & (PlayerTeamSeason.league_id == PlayerSeasonProfile.league_id)
            & (PlayerTeamSeason.api_team_id == PlayerSeasonProfile.api_team_id)
            & (PlayerTeamSeason.api_player_id == PlayerSeasonProfile.api_player_id),
        )
        .where(
            PlayerSeasonProfile.season == int(season_year),
            PlayerSeasonProfile.league_id == int(league_id),
            PlayerSeasonProfile.api_team_id == int(api_team_id),
        ),
    ).all()
    out: list[_ProfileRow] = []
    for pr, reg, pos in rows:
        out.append(_ProfileRow(profile=pr, name=reg.name, position=pos))
    return out


def compute_league_player_baselines_strict(
    db: Session,
    *,
    season_year: int,
    league_id: int,
) -> dict[str, float]:
    api_teams = db.scalars(
        select(PlayerSeasonProfile.api_team_id)
        .where(
            PlayerSeasonProfile.season == int(season_year),
            PlayerSeasonProfile.league_id == int(league_id),
        )
        .distinct(),
    ).all()

    team_avgs: dict[str, list[float]] = {k: [] for k in REQUIRED_LEAGUE_PLAYER_KEYS}

    for api_team_id in api_teams:
        rows = load_team_profile_rows(
            db,
            season_year=season_year,
            league_id=league_id,
            api_team_id=int(api_team_id),
        )
        top = select_top_player_profiles(rows)
        if len(top) < V11_MIN_PLAYER_PROFILE_PLAYERS:
            continue
        signals = team_signals_from_top(top)
        for sig_key, league_key in LEAGUE_PLAYER_BASELINE_FIELD_MAP.items():
            v = signals.get(sig_key)
            if v is not None:
                team_avgs[league_key].append(float(v))

    out: dict[str, float] = {}
    for k in REQUIRED_LEAGUE_PLAYER_KEYS:
        xs = team_avgs[k]
        out[k] = sum(xs) / len(xs) if xs else 0.0

    missing = [k for k in REQUIRED_LEAGUE_PLAYER_KEYS if out.get(k) is None or float(out[k]) <= 0]
    if missing:
        raise MissingPlayerLeagueBaselineError(missing)
    return out


def _build_input_blob(
    *,
    key: str,
    raw_v: float | None,
    norm_v: float | None,
    iw: float,
    ic: float,
    sample_count: int,
    status: str,
    application_role: str,
    audit_note: str | None = None,
) -> dict[str, Any]:
    blob: dict[str, Any] = {
        "key": key,
        "label": PLAYER_INPUT_LABELS[key],
        "raw_value": round2(raw_v),
        "normalized_value": round2(norm_v),
        "internal_weight": iw,
        "internal_contribution": ic,
        "source_path": PLAYER_INPUT_SOURCE_PATHS[key],
        "api_source": PLAYER_INPUT_API_SOURCES[key],
        "db_field": PLAYER_INPUT_DB_FIELDS[key],
        "sample_count": sample_count,
        "fallback_used": False,
        "no_data_leakage": True,
        "status": status,
        "application_role": application_role,
        "parent_component": COMPONENT_KEY_PLAYER,
    }
    if audit_note:
        blob["audit_note"] = audit_note
    return blob


def _compute_historical_player_layer(
    db: Session,
    ctx: V10PriorContext,
    *,
    league_baselines: dict[str, float],
    player_league_baselines: dict[str, float],
    season: Season,
    team: Team,
    rows: list[_ProfileRow],
    players_considered: int,
    top: list[_ProfileRow],
    meta: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, list[dict[str, Any]], dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    lsot_for = league_baselines.get("league_avg_sot_for")
    if lsot_for is None or float(lsot_for) <= 0:
        missing.append(missing_field("league_avg_sot_for", **meta))
        return None, missing, "missing_required_player_league_baseline", [], {}

    raw_signals = team_signals_from_top(top)
    normalized: dict[str, float | None] = {}
    for sig_key, league_key in LEAGUE_PLAYER_BASELINE_FIELD_MAP.items():
        team_v = raw_signals.get(sig_key)
        league_v = player_league_baselines.get(league_key)
        normalized[sig_key] = _scale_to_sot(team_v, league_v, float(lsot_for))

    inputs_list: list[dict[str, Any]] = []
    component_sum = 0.0
    sym_parts: list[str] = []
    top_n = len(top)

    for key in PLAYER_NUMERIC_INPUT_ORDER:
        norm_v = normalized.get(key)
        if norm_v is None:
            missing.append(missing_field(key, **meta))
            return None, missing, "missing_required_data", [_pack_top_player(r) for r in top], {
                "players_considered": players_considered,
                "top_players_used": top_n,
            }
        iw = PLAYER_INTERNAL_WEIGHTS[key]
        ic = round4(float(norm_v) * iw)
        component_sum += ic
        sym_parts.append(f"({PLAYER_INPUT_LABELS[key]} × {iw})")
        inputs_list.append(
            _build_input_blob(
                key=key,
                raw_v=raw_signals.get(key),
                norm_v=norm_v,
                iw=iw,
                ic=ic,
                sample_count=top_n,
                status="available",
                application_role="component_input",
            ),
        )

    for key in PLAYER_LINEUP_CONTEXT_INPUT_ORDER:
        inputs_list.append(
            _build_input_blob(
                key=key,
                raw_v=None,
                norm_v=None,
                iw=0.0,
                ic=0.0,
                sample_count=top_n,
                status="not_available_yet",
                application_role="context_risk",
            ),
        )

    component_value = round2(component_sum) or 0.0
    internal_formula = (
        f"{COMPONENT_KEY_PLAYER} = "
        + " + ".join(sym_parts)
        + f"\n= {round2(component_sum)}"
    )

    top_players_payload = [_pack_top_player(r) for r in top]
    quality = {
        "players_considered": players_considered,
        "top_players_used": top_n,
        "minimum_players_required": V11_MIN_PLAYER_PROFILE_PLAYERS,
        "fallback_count": 0,
        "has_mock_data": False,
        "has_fallback_data": False,
        "no_data_leakage": True,
        "inputs_total": len(PLAYER_INPUT_ORDER),
        "inputs_available": len(PLAYER_NUMERIC_INPUT_ORDER),
        "missing_required": [],
        "mode_note": "Lineups non disponibili, Player layer in modalità storico/recent impact.",
    }

    comp: dict[str, Any] = {
        "key": COMPONENT_KEY_PLAYER,
        "label": COMPONENT_LABEL_PLAYER,
        "mode": PLAYER_LAYER_MODE_HISTORICAL,
        "lineups_available": False,
        "value": component_value,
        "internal_formula": internal_formula,
        "inputs": inputs_list,
        "top_players": top_players_payload,
        "lineup_starters": [],
        "lineup_adjustment": {
            "status": "not_applied",
            "reason": "Lineups non disponibili per entrambe le squadre",
        },
        "availability_adjustment": {
            "status": "not_applied",
            "reason": "Injuries/sidelined non ancora integrati",
        },
        "quality": quality,
        "fallbacks_used": [],
    }
    return comp, [], "ok", top_players_payload, quality


def _compute_lineup_adjusted_player_layer(
    db: Session,
    ctx: V10PriorContext,
    *,
    league_baselines: dict[str, float],
    player_league_baselines: dict[str, float],
    season: Season,
    team: Team,
    fx: Fixture,
    all_rows: list[_ProfileRow],
    meta: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, list[dict[str, Any]], dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    lsot_for = league_baselines.get("league_avg_sot_for")
    if lsot_for is None or float(lsot_for) <= 0:
        missing.append(missing_field("league_avg_sot_for", **meta))
        return None, missing, "missing_required_player_league_baseline", [], {}

    lineup = load_team_lineup_for_fixture(db, fixture_id=int(fx.id), team_id=int(ctx.team_id))
    if lineup is None:
        return None, missing, "missing_required_data", [], {}

    starters_lp, bench_lp = load_lineup_players_by_role(db, fixture_lineup_id=int(lineup.id))
    profiles_by_api = profile_map_for_team(
        db,
        season_year=int(season.year),
        league_id=int(season.league_id),
        api_team_id=int(team.api_team_id),
    )

    name_by_api: dict[int, str] = {int(r.profile.api_player_id): r.name for r in all_rows}
    pos_by_api: dict[int, str | None] = {int(r.profile.api_player_id): r.position for r in all_rows}

    starter_rows: list[_ProfileRow] = []
    missing_lineup_player_profiles: list[dict[str, Any]] = []

    for lp in starters_lp:
        if lp.api_player_id is None:
            missing_lineup_player_profiles.append(
                {"player_name": lp.player_name, "reason": "api_player_id assente"},
            )
            continue
        pr = profiles_by_api.get(int(lp.api_player_id))
        if not starter_has_offensive_profile(pr):
            missing_lineup_player_profiles.append(
                {
                    "api_player_id": int(lp.api_player_id),
                    "player_name": lp.player_name,
                    "reason": "profilo stagionale assente o senza metriche tiri",
                },
            )
            continue
        starter_rows.append(
            _ProfileRow(
                profile=pr,
                name=name_by_api.get(int(lp.api_player_id), lp.player_name),
                position=lp.position or pos_by_api.get(int(lp.api_player_id)),
            ),
        )

    if len(starter_rows) < V11_MIN_PLAYER_PROFILE_PLAYERS:
        return None, missing, "insufficient_player_profile_sample", [], {
            "starters_with_profile": len(starter_rows),
            "minimum_required": V11_MIN_PLAYER_PROFILE_PLAYERS,
        }

    top_shooter_ids = select_top_shooter_api_ids(profiles_by_api)
    starter_ids = {int(lp.api_player_id) for lp in starters_lp if lp.api_player_id is not None}
    bench_ids = {int(lp.api_player_id) for lp in bench_lp if lp.api_player_id is not None}
    ts_class = classify_top_shooters_in_lineup(top_shooter_ids, starter_ids, bench_ids, profiles_by_api)
    presence_signal, absence_signal = lineup_presence_absence_signals(
        top_shooters_starting=int(ts_class["top_shooters_starting"]),
        top_shooters_on_bench=int(ts_class["top_shooters_on_bench"]),
        top_shooters_total=int(ts_class["top_shooters_total"]),
    )

    raw_starter_signals = team_signals_from_starters(starter_rows)
    raw_signals = dict(raw_starter_signals)
    raw_signals["top_shooter_starter_presence_signal"] = presence_signal
    raw_signals["top_shooter_lineup_absence_signal"] = absence_signal

    normalized: dict[str, float | None] = {}
    for sig_key, league_key in LINEUP_LEAGUE_BASELINE_FIELD_MAP.items():
        team_v = raw_starter_signals.get(sig_key)
        league_v = player_league_baselines.get(league_key)
        normalized[sig_key] = _scale_to_sot(team_v, league_v, float(lsot_for))

    normalized["top_shooter_starter_presence_signal"] = normalize_presence_signal(
        presence_signal,
        float(lsot_for),
    )
    normalized["top_shooter_lineup_absence_signal"] = normalize_absence_signal(
        absence_signal,
        float(lsot_for),
    )

    inputs_list: list[dict[str, Any]] = []
    component_sum = 0.0
    sym_parts: list[str] = []
    starter_n = len(starter_rows)

    for key in LINEUP_NUMERIC_INPUT_ORDER:
        norm_v = normalized.get(key)
        if norm_v is None:
            missing.append(missing_field(key, **meta))
            return None, missing, "missing_required_data", [_pack_starter_player(r) for r in starter_rows], {
                "starters_with_profile": starter_n,
            }
        iw = LINEUP_INTERNAL_WEIGHTS[key]
        ic = round4(float(norm_v) * iw)
        component_sum += ic
        sym_parts.append(f"({PLAYER_INPUT_LABELS[key]} × {iw})")
        audit_note = TOP_SHOOTER_ABSENCE_AUDIT_NOTE if key == "top_shooter_lineup_absence_signal" else None
        inputs_list.append(
            _build_input_blob(
                key=key,
                raw_v=raw_signals.get(key),
                norm_v=norm_v,
                iw=iw,
                ic=ic,
                sample_count=starter_n,
                status="available",
                application_role="component_input",
                audit_note=audit_note,
            ),
        )

    component_value = round2(component_sum) or 0.0
    internal_formula = (
        f"{COMPONENT_KEY_PLAYER} [lineup_adjusted] = "
        + " + ".join(sym_parts)
        + f"\n= {round2(component_sum)}"
    )

    top_shooters_payload = [
        _pack_top_player(
            _ProfileRow(
                profile=profiles_by_api[i],
                name=name_by_api.get(i, str(i)),
                position=pos_by_api.get(i),
            ),
        )
        for i in top_shooter_ids
        if i in profiles_by_api
    ]

    warnings: list[str] = []
    if starter_n < LINEUP_STARTERS_PROFILE_WARNING_THRESHOLD:
        warnings.append(
            f"Solo {starter_n} titolari con profilo valido (soglia warning {LINEUP_STARTERS_PROFILE_WARNING_THRESHOLD}).",
        )
    if missing_lineup_player_profiles:
        warnings.append(
            f"{len(missing_lineup_player_profiles)} titolari senza profilo stagionale utilizzabile.",
        )

    quality = {
        "players_considered": len(all_rows),
        "starters_with_profile": starter_n,
        "top_players_used": len(top_shooter_ids),
        "minimum_players_required": V11_MIN_PLAYER_PROFILE_PLAYERS,
        "fallback_count": 0,
        "has_mock_data": False,
        "has_fallback_data": False,
        "no_data_leakage": True,
        "inputs_total": len(LINEUP_NUMERIC_INPUT_ORDER),
        "inputs_available": len(LINEUP_NUMERIC_INPUT_ORDER),
        "missing_required": [],
        "missing_lineup_player_profiles": missing_lineup_player_profiles,
        "warnings": warnings,
        "mode_note": "Modalità: lineup-adjusted",
    }

    comp: dict[str, Any] = {
        "key": COMPONENT_KEY_PLAYER,
        "label": COMPONENT_LABEL_PLAYER,
        "mode": PLAYER_LAYER_MODE_LINEUP,
        "lineups_available": True,
        "value": component_value,
        "internal_formula": internal_formula,
        "inputs": inputs_list,
        "top_players": top_shooters_payload,
        "top_shooters": top_shooters_payload,
        "lineup_starters": [_pack_starter_player(r) for r in starter_rows],
        "starting_top_shooters": ts_class["starting_top_shooters"],
        "bench_top_shooters": ts_class["bench_top_shooters"],
        "missing_top_shooters_from_lineup": ts_class["missing_top_shooters_from_lineup"],
        "lineup_adjustment": {
            "status": "applied",
            "top_shooters_total": ts_class["top_shooters_total"],
            "top_shooters_starting": ts_class["top_shooters_starting"],
            "top_shooters_on_bench": ts_class["top_shooters_on_bench"],
            "top_shooters_not_in_lineup": ts_class["top_shooters_not_in_lineup"],
            "presence_signal": round2(presence_signal),
            "absence_signal": round2(absence_signal),
            "warning": warnings[0] if warnings else None,
        },
        "availability_adjustment": {
            "status": "not_applied",
            "reason": "Injuries/sidelined non ancora integrati",
        },
        "quality": quality,
        "fallbacks_used": [],
    }
    return comp, [], "ok", [_pack_starter_player(r) for r in starter_rows], quality


def compute_player_layer_component(
    db: Session,
    ctx: V10PriorContext,
    *,
    league_baselines: dict[str, float],
    player_league_baselines: dict[str, float],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str, list[dict[str, Any]], dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    meta = {
        "api_sources": PLAYER_INPUT_API_SOURCES,
        "db_fields": PLAYER_INPUT_DB_FIELDS,
        "source_paths": PLAYER_INPUT_SOURCE_PATHS,
    }

    season = db.get(Season, int(ctx.season_id))
    if season is None:
        missing.append(missing_field("player_season_profiles", **meta))
        return None, missing, "missing_required_data", [], {}

    team = db.get(Team, int(ctx.team_id))
    if team is None:
        missing.append(missing_field("api_team_id", **meta))
        return None, missing, "missing_required_data", [], {}

    rows = load_team_profile_rows(
        db,
        season_year=int(season.year),
        league_id=int(season.league_id),
        api_team_id=int(team.api_team_id),
    )
    players_considered = len([r for r in rows if _is_eligible(r.profile)])
    top = select_top_player_profiles(rows)

    if len(top) < V11_MIN_PLAYER_PROFILE_PLAYERS:
        return None, missing, "insufficient_player_profile_sample", [], {
            "players_considered": players_considered,
            "top_players_used": len(top),
        }

    fx = load_fixture_for_lineup(db, int(ctx.cutoff_fixture_id))
    use_lineup = False
    if fx is not None:
        use_lineup = fixture_both_lineups_available(
            db,
            fixture_id=int(fx.id),
            home_team_id=int(fx.home_team_id),
            away_team_id=int(fx.away_team_id),
        )

    if use_lineup and fx is not None:
        lineup_result = _compute_lineup_adjusted_player_layer(
            db,
            ctx,
            league_baselines=league_baselines,
            player_league_baselines=player_league_baselines,
            season=season,
            team=team,
            fx=fx,
            all_rows=rows,
            meta=meta,
        )
        if lineup_result[2] == "insufficient_player_profile_sample":
            pass
        else:
            return lineup_result

    return _compute_historical_player_layer(
        db,
        ctx,
        league_baselines=league_baselines,
        player_league_baselines=player_league_baselines,
        season=season,
        team=team,
        rows=rows,
        players_considered=players_considered,
        top=top,
        meta=meta,
    )
