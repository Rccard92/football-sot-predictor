"""Audit read-only indisponibili per fixture / summary stagione."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture, PlayerAvailability, PlayerSeasonProfile, Season, Team
from app.services.availability.availability_helpers import (
    HIGH_IMPACT_THRESHOLD,
    select_top_shooter_api_ids,
)
from app.services.sot_feature_registry import V11_MIN_PLAYER_MINUTES

QUALITY_BLOCK: dict[str, Any] = {
    "source": "player_availability",
    "api_live_call": False,
    "model_impact": False,
    "note": (
        "Dati indisponibilità solo per audit (stage 8A). Nessun impatto sulla formula baseline_v1_1_sot. "
        "Penalità Player layer previste in stage 8B."
    ),
}

NOT_AVAILABLE_MESSAGE = (
    "Nessun record di indisponibilità attivo nel DB per questa partita. "
    "Esegui «Aggiorna indisponibili» da Admin (injuries API)."
)


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


def _kickoff_date(fixture: Fixture) -> date:
    ko = fixture.kickoff_at
    if isinstance(ko, datetime):
        return ko.date()
    return ko  # type: ignore[return-value]


def _date_in_range(kickoff: date, start: date | None, end: date | None) -> tuple[bool, str]:
    """
    Ritorna (include, date_window).
    - active_unbounded: end null e active
    - unknown: nessuna data
    - in_range / out_of_range
    """
    if start is None and end is None:
        return True, "unknown"
    if end is None:
        if start is not None and kickoff < start:
            return False, "out_of_range"
        return True, "active_unbounded"
    if start is not None and kickoff < start:
        return False, "out_of_range"
    if kickoff > end:
        return False, "out_of_range"
    return True, "in_range"


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


def _query_fixture_availability(
    db: Session,
    *,
    fixture: Fixture,
    season_year: int,
    league_id: int,
    home: Team,
    away: Team,
) -> tuple[list[PlayerAvailability], list[str]]:
    api_fx = int(fixture.api_fixture_id)
    api_home = int(home.api_team_id)
    api_away = int(away.api_team_id)
    kickoff = _kickoff_date(fixture)

    candidates = list(
        db.scalars(
            select(PlayerAvailability).where(
                PlayerAvailability.season == int(season_year),
                PlayerAvailability.league_id == int(league_id),
                PlayerAvailability.is_active.is_(True),
                or_(
                    PlayerAvailability.fixture_id == int(fixture.id),
                    PlayerAvailability.api_fixture_id == api_fx,
                    and_(
                        PlayerAvailability.api_team_id.in_([api_home, api_away]),
                        or_(
                            PlayerAvailability.api_fixture_id.is_(None),
                            PlayerAvailability.api_fixture_id == api_fx,
                        ),
                    ),
                ),
            )
            .order_by(PlayerAvailability.team_id.asc(), PlayerAvailability.player_name.asc()),
        ).all(),
    )

    warnings: list[str] = []
    included: list[PlayerAvailability] = []
    for row in candidates:
        ok, window = _date_in_range(kickoff, row.start_date, row.end_date)
        if not ok:
            continue
        included.append(row)
        if window == "active_unbounded":
            warnings.append(
                f"{row.player_name}: record attivo senza end_date (active_unbounded).",
            )
        elif window == "unknown":
            warnings.append(f"{row.player_name}: nessuna start/end_date (date_window unknown).")

    return included, warnings


def _pack_player_row(
    av: PlayerAvailability,
    profile: PlayerSeasonProfile | None,
    *,
    is_top_shooter: bool,
    kickoff: date,
) -> dict[str, Any]:
    impact = _float_or_none(profile.shooting_impact_score) if profile else None
    _, date_window = _date_in_range(kickoff, av.start_date, av.end_date)
    return {
        "api_player_id": av.api_player_id,
        "player_name": av.player_name,
        "availability_status": av.availability_status,
        "availability_type": av.availability_type,
        "reason": av.reason,
        "source": av.source,
        "api_fixture_id": av.api_fixture_id,
        "is_team_level": av.api_fixture_id is None and av.fixture_id is None,
        "date_window": date_window,
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
    records: list[PlayerAvailability],
    season_year: int,
    league_id: int,
    kickoff: date,
) -> dict[str, Any]:
    team_recs = [r for r in records if r.team_id == int(team.id) or r.api_team_id == int(team.api_team_id)]
    pmap = _profile_map_for_team(
        db,
        season_year=season_year,
        league_id=league_id,
        api_team_id=int(team.api_team_id),
    )
    top_ids = set(select_top_shooter_api_ids(pmap))
    players = [
        _pack_player_row(
            r,
            pmap.get(int(r.api_player_id)) if r.api_player_id is not None else None,
            is_top_shooter=r.api_player_id is not None and int(r.api_player_id) in top_ids,
            kickoff=kickoff,
        )
        for r in team_recs
    ]
    return {
        "team_id": int(team.id),
        "team_name": team.name,
        "api_team_id": int(team.api_team_id),
        "unavailable_count": len(players),
        "players": players,
    }


def build_fixture_availability_debug(db: Session, fixture_id: int) -> dict[str, Any]:
    fx = db.scalar(
        select(Fixture)
        .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
        .where(Fixture.id == int(fixture_id)),
    )
    if fx is None:
        return {"status": "error", "message": f"Fixture {fixture_id} non trovata", "fixture_id": int(fixture_id)}

    season_row = db.scalar(select(Season).where(Season.id == int(fx.season_id)))
    if season_row is None:
        return {"status": "error", "message": "Stagione non trovata", "fixture_id": int(fixture_id)}

    season_year = int(season_row.year)
    league_id = int(fx.league_id)
    home = fx.home_team
    away = fx.away_team
    if home is None or away is None:
        return {"status": "error", "message": "Squadre fixture non risolte", "fixture_id": int(fixture_id)}

    kickoff = _kickoff_date(fx)
    records, warnings = _query_fixture_availability(
        db,
        fixture=fx,
        season_year=season_year,
        league_id=league_id,
        home=home,
        away=away,
    )

    fixture_level_count = sum(
        1 for r in records if r.fixture_id == int(fx.id) or r.api_fixture_id == int(fx.api_fixture_id)
    )
    team_level_count = len(records) - fixture_level_count

    if not records:
        return {
            "status": "not_available_yet",
            "fixture_id": int(fixture_id),
            "api_fixture_id": int(fx.api_fixture_id),
            "season": season_year,
            "availability_available": False,
            "message": NOT_AVAILABLE_MESSAGE,
            "fixture_level_count": 0,
            "team_level_count": 0,
            "warnings": warnings,
            "home": {"team_name": home.name, "unavailable_count": 0, "players": []},
            "away": {"team_name": away.name, "unavailable_count": 0, "players": []},
            "quality": QUALITY_BLOCK,
        }

    return {
        "status": "ok",
        "fixture_id": int(fixture_id),
        "api_fixture_id": int(fx.api_fixture_id),
        "season": season_year,
        "availability_available": True,
        "fixture_level_count": fixture_level_count,
        "team_level_count": team_level_count,
        "warnings": warnings,
        "home": _pack_team_side(
            db,
            team=home,
            records=records,
            season_year=season_year,
            league_id=league_id,
            kickoff=kickoff,
        ),
        "away": _pack_team_side(
            db,
            team=away,
            records=records,
            season_year=season_year,
            league_id=league_id,
            kickoff=kickoff,
        ),
        "quality": QUALITY_BLOCK,
    }


def build_season_availability_summary(db: Session, season_year: int) -> dict[str, Any]:
    from app.services.ingestion_service import IngestionService

    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, int(season_year))
    league_id = int(season_row.league_id)

    rows = db.scalars(
        select(PlayerAvailability).where(
            PlayerAvailability.season == int(season_year),
            PlayerAvailability.league_id == league_id,
        ),
    ).all()
    active = [r for r in rows if r.is_active]
    with_fixture = sum(1 for r in active if r.fixture_id is not None or r.api_fixture_id is not None)
    with_registry = sum(1 for r in active if r.player_id is not None)
    sources: dict[str, int] = {}
    for r in active:
        sources[r.source] = sources.get(r.source, 0) + 1

    return {
        "status": "ok",
        "season": int(season_year),
        "league_id": league_id,
        "total_records": len(rows),
        "active_records": len(active),
        "inactive_records": len(rows) - len(active),
        "active_with_fixture": with_fixture,
        "active_with_registry": with_registry,
        "by_source": sources,
    }
