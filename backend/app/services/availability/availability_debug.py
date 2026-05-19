"""Audit read-only indisponibili per fixture / summary stagione."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, PlayerAvailability, PlayerSeasonProfile, Team
from app.services.availability.availability_fixture_scope import (
    applicable_for_team,
    build_fixture_context,
    generic_for_team,
    infer_record_scope_from_row,
    load_fixture_availability_buckets,
)
from app.services.availability.availability_helpers import (
    HIGH_IMPACT_THRESHOLD,
    select_top_shooter_api_ids,
)
from app.services.availability.availability_league import resolve_serie_a_league_context
from app.services.sot_feature_registry import V11_MIN_PLAYER_MINUTES

QUESTION = "Chi è indisponibile per questa partita?"
SCOPE_LABEL = "fixture_applicable_only"
EMPTY_APPLICABLE_MESSAGE = (
    "Nessun indisponibile applicabile a questa partita trovato nel DB."
)

QUALITY_BLOCK: dict[str, Any] = {
    "source": "player_availability",
    "api_live_call": False,
    "model_impact": True,
    "note": (
        "Solo record fixture-level salvati per questa partita (da availability-upcoming: "
        "league/season filtrato su upcoming, ids batch, o fixture direct). "
        "Raw stagionale e team-level non sono mostrati."
    ),
}


def _float_or_none(v: Decimal | float | int | None) -> float | None:
    if v is None:
        return None
    return float(v)


def _eligible_profile(p: PlayerSeasonProfile) -> bool:
    if p.reliability_score is None:
        return False
    mins = p.minutes_total
    if mins is None or float(mins) < V11_MIN_PLAYER_MINUTES:
        return False
    if p.shots_on_per90 is None and p.shots_total_per90 is None:
        return False
    return True


def _profile_map_for_team(
    db: Session,
    *,
    season_year: int,
    league_id: int,
    api_team_id: int,
) -> dict[int, PlayerSeasonProfile]:
    rows = db.scalars(
        select(PlayerSeasonProfile).where(
            PlayerSeasonProfile.season == int(season_year),
            PlayerSeasonProfile.league_id == int(league_id),
            PlayerSeasonProfile.api_team_id == int(api_team_id),
        ),
    ).all()
    return {int(p.api_player_id): p for p in rows}


def _date_window_label(kickoff: date, start: date | None, end: date | None) -> str:
    if start is None and end is None:
        return "unknown"
    if start is not None and kickoff < start:
        return "out_of_range"
    if end is not None and kickoff > end:
        return "out_of_range"
    if end is None and start is not None:
        return "active_unbounded"
    return "in_range"


def _pack_record_row(
    av: PlayerAvailability,
    profile: PlayerSeasonProfile | None,
    *,
    is_top_shooter: bool,
    kickoff: date,
    applicability_reason: str,
) -> dict[str, Any]:
    impact = _float_or_none(profile.shooting_impact_score) if profile else None
    return {
        "api_player_id": av.api_player_id,
        "player_name": av.player_name,
        "availability_status": av.availability_status,
        "availability_type": av.availability_type,
        "reason": av.reason,
        "source": av.source,
        "record_scope": infer_record_scope_from_row(av),
        "api_fixture_id": av.api_fixture_id,
        "fixture_date": av.fixture_date.isoformat() if av.fixture_date else None,
        "start_date": av.start_date.isoformat() if av.start_date else None,
        "end_date": av.end_date.isoformat() if av.end_date else None,
        "date_window": _date_window_label(kickoff, av.start_date, av.end_date),
        "applicability_reason": applicability_reason,
        "shots_on_per90": _float_or_none(profile.shots_on_per90) if profile else None,
        "team_sot_share": _float_or_none(profile.team_sot_share) if profile else None,
        "shooting_impact_score": impact,
        "is_top_shooter": is_top_shooter,
        "high_impact": impact is not None and impact >= HIGH_IMPACT_THRESHOLD,
        "profile_found": profile is not None and _eligible_profile(profile),
    }


def _pack_team_side(
    db: Session,
    *,
    team: Team,
    applicable: list[PlayerAvailability],
    generic: list[PlayerAvailability],
    season_year: int,
    league_id: int,
    kickoff: date,
) -> dict[str, Any]:
    pmap = _profile_map_for_team(
        db,
        season_year=season_year,
        league_id=league_id,
        api_team_id=int(team.api_team_id),
    )
    top_ids = set(select_top_shooter_api_ids(pmap))

    applicable_rows = [
        _pack_record_row(
            r,
            pmap.get(int(r.api_player_id)) if r.api_player_id is not None else None,
            is_top_shooter=r.api_player_id is not None and int(r.api_player_id) in top_ids,
            kickoff=kickoff,
            applicability_reason="fixture_applicable",
        )
        for r in applicable
    ]
    generic_rows = [
        _pack_record_row(
            r,
            pmap.get(int(r.api_player_id)) if r.api_player_id is not None else None,
            is_top_shooter=r.api_player_id is not None and int(r.api_player_id) in top_ids,
            kickoff=kickoff,
            applicability_reason="generic_not_applied",
        )
        for r in generic
    ]

    return {
        "team_id": int(team.id),
        "team_name": team.name,
        "api_team_id": int(team.api_team_id),
        "applicable_records": applicable_rows,
        "generic_records_not_applied": generic_rows,
        "unavailable_count": len(applicable_rows),
        "players": applicable_rows,
    }


def build_fixture_availability_debug(db: Session, fixture_id: int) -> dict[str, Any]:
    buckets = load_fixture_availability_buckets(db, int(fixture_id))
    if buckets is None:
        return {"status": "error", "message": f"Fixture {fixture_id} non trovata", "fixture_id": int(fixture_id)}

    ctx = buckets.ctx
    fx = db.scalar(select(Fixture).where(Fixture.id == int(fixture_id)))
    home = db.get(Team, ctx.home_team_id)
    away = db.get(Team, ctx.away_team_id)
    if fx is None or home is None or away is None:
        return {"status": "error", "message": "Fixture o squadre non risolte", "fixture_id": int(fixture_id)}

    home_applicable = applicable_for_team(
        buckets,
        api_team_id=ctx.api_home_team_id,
        team_id=ctx.home_team_id,
    )
    away_applicable = applicable_for_team(
        buckets,
        api_team_id=ctx.api_away_team_id,
        team_id=ctx.away_team_id,
    )
    home_generic = generic_for_team(
        buckets,
        api_team_id=ctx.api_home_team_id,
        team_id=ctx.home_team_id,
    )
    away_generic = generic_for_team(
        buckets,
        api_team_id=ctx.api_away_team_id,
        team_id=ctx.away_team_id,
    )

    fixture_label = f"{ctx.home_name} - {ctx.away_name}"
    home_side = _pack_team_side(
        db,
        team=home,
        applicable=home_applicable,
        generic=home_generic,
        season_year=ctx.season_year,
        league_id=ctx.league_id,
        kickoff=ctx.kickoff,
    )
    away_side = _pack_team_side(
        db,
        team=away,
        applicable=away_applicable,
        generic=away_generic,
        season_year=ctx.season_year,
        league_id=ctx.league_id,
        kickoff=ctx.kickoff,
    )

    total_applicable = len(home_applicable) + len(away_applicable)
    payload: dict[str, Any] = {
        "status": "success",
        "fixture_id": int(fixture_id),
        "api_fixture_id": ctx.api_fixture_id,
        "season": ctx.season_year,
        "fixture_label": fixture_label,
        "question": QUESTION,
        "availability_scope": SCOPE_LABEL,
        "availability_available": total_applicable > 0,
        "message": EMPTY_APPLICABLE_MESSAGE if total_applicable == 0 else None,
        "fixture_level_count": sum(
            1
            for r in buckets.applicable
            if r.api_fixture_id == ctx.api_fixture_id or r.fixture_id == ctx.fixture_id
        ),
        "team_level_count": sum(
            1
            for r in buckets.applicable
            if r.api_fixture_id is None and r.fixture_id is None
        ),
        "home": home_side,
        "away": away_side,
        "quality": QUALITY_BLOCK,
    }
    return payload


def build_season_availability_summary(db: Session, season_year: int) -> dict[str, Any]:
    ctx = resolve_serie_a_league_context(db, int(season_year))
    league_internal_id = ctx.league_internal_id

    rows = db.scalars(
        select(PlayerAvailability).where(
            PlayerAvailability.season == int(season_year),
            PlayerAvailability.league_id == league_internal_id,
        ),
    ).all()
    active = [r for r in rows if r.is_active]
    with_fixture = sum(1 for r in active if r.fixture_id is not None or r.api_fixture_id is not None)
    with_registry = sum(1 for r in active if r.player_id is not None)
    sources: dict[str, int] = {}
    scopes: dict[str, int] = {}
    for r in active:
        sources[r.source] = sources.get(r.source, 0) + 1
        sc = infer_record_scope_from_row(r)
        scopes[sc] = scopes.get(sc, 0) + 1

    return {
        "status": "ok",
        "season": int(season_year),
        "league_internal_id": league_internal_id,
        "api_league_id": ctx.api_league_id,
        "total_records": len(rows),
        "active_records": len(active),
        "inactive_records": len(rows) - len(active),
        "active_with_fixture": with_fixture,
        "active_with_registry": with_registry,
        "by_source": sources,
        "by_record_scope": scopes,
    }
