"""Player layer v1.1 — profili storici/recent da player_season_profiles, nessun fallback."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlayerRegistry, PlayerSeasonProfile, PlayerTeamSeason, Season, Team
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.player_layer_feature_sources import (
    COMPONENT_KEY_PLAYER,
    COMPONENT_LABEL_PLAYER,
    LEAGUE_PLAYER_BASELINE_FIELD_MAP,
    PLAYER_CONTEXT_INPUT_ORDER,
    PLAYER_INPUT_API_SOURCES,
    PLAYER_INPUT_DB_FIELDS,
    PLAYER_INPUT_LABELS,
    PLAYER_INPUT_ORDER,
    PLAYER_INPUT_SOURCE_PATHS,
    PLAYER_INTERNAL_WEIGHTS,
    PLAYER_LAYER_MODE,
    PLAYER_NUMERIC_INPUT_ORDER,
    REQUIRED_LEAGUE_PLAYER_KEYS,
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
    }


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

    lsot_for = league_baselines.get("league_avg_sot_for")
    if lsot_for is None or float(lsot_for) <= 0:
        missing.append(missing_field("league_avg_sot_for", **meta))
        return None, missing, "missing_required_player_league_baseline", [], {}

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
        raw_v = raw_signals.get(key)
        inputs_list.append(
            {
                "key": key,
                "label": PLAYER_INPUT_LABELS[key],
                "raw_value": round2(raw_v),
                "normalized_value": round2(norm_v),
                "internal_weight": iw,
                "internal_contribution": ic,
                "source_path": PLAYER_INPUT_SOURCE_PATHS[key],
                "api_source": PLAYER_INPUT_API_SOURCES[key],
                "db_field": PLAYER_INPUT_DB_FIELDS[key],
                "sample_count": top_n,
                "fallback_used": False,
                "no_data_leakage": True,
                "status": "available",
                "application_role": "component_input",
                "parent_component": COMPONENT_KEY_PLAYER,
            },
        )

    for key in PLAYER_CONTEXT_INPUT_ORDER:
        status = (
            "not_applicable_until_lineups"
            if key == "top_shooter_presence_status"
            else "not_applicable_until_injuries_or_lineups"
        )
        inputs_list.append(
            {
                "key": key,
                "label": PLAYER_INPUT_LABELS[key],
                "raw_value": None,
                "normalized_value": None,
                "internal_weight": 0.0,
                "internal_contribution": 0.0,
                "source_path": PLAYER_INPUT_SOURCE_PATHS[key],
                "api_source": PLAYER_INPUT_API_SOURCES[key],
                "db_field": PLAYER_INPUT_DB_FIELDS[key],
                "sample_count": top_n,
                "fallback_used": False,
                "no_data_leakage": True,
                "status": status,
                "application_role": "context_risk",
                "parent_component": COMPONENT_KEY_PLAYER,
            },
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
    }

    comp: dict[str, Any] = {
        "key": COMPONENT_KEY_PLAYER,
        "label": COMPONENT_LABEL_PLAYER,
        "mode": PLAYER_LAYER_MODE,
        "value": component_value,
        "internal_formula": internal_formula,
        "inputs": inputs_list,
        "top_players": top_players_payload,
        "lineup_adjustment": {
            "status": "not_applied",
            "reason": "Lineups non ancora integrate nel modello v1.1",
        },
        "availability_adjustment": {
            "status": "not_applied",
            "reason": "Injuries/sidelined non ancora integrati nel modello v1.1",
        },
        "quality": quality,
        "fallbacks_used": [],
    }
    return comp, [], "ok", top_players_payload, quality
