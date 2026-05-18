"""Upsert record player_availability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from app.models import Fixture, PlayerAvailability, PlayerRegistry, Team
from app.services.availability.availability_parsing import ParsedAvailabilityRecord


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_registry_id(db: Session, api_player_id: int | None) -> Any:
    if api_player_id is None:
        return None
    return db.scalar(select(PlayerRegistry.id).where(PlayerRegistry.api_player_id == int(api_player_id)))


def _resolve_fixture(db: Session, api_fixture_id: int | None, season: int, league_id: int) -> Fixture | None:
    if api_fixture_id is None:
        return None
    return db.scalar(
        select(Fixture).where(
            Fixture.api_fixture_id == int(api_fixture_id),
            Fixture.league_id == int(league_id),
        ),
    )


def _resolve_team(db: Session, api_team_id: int | None) -> Team | None:
    if api_team_id is None:
        return None
    return db.scalar(select(Team).where(Team.api_team_id == int(api_team_id)))


def _match_existing(
    db: Session,
    *,
    season: int,
    league_id: int,
    parsed: ParsedAvailabilityRecord,
) -> PlayerAvailability | None:
    q = select(PlayerAvailability).where(
        PlayerAvailability.season == int(season),
        PlayerAvailability.league_id == int(league_id),
        PlayerAvailability.source == parsed.source,
        PlayerAvailability.api_team_id == parsed.api_team_id,
        PlayerAvailability.api_player_id == parsed.api_player_id,
    )
    if parsed.api_fixture_id is not None:
        q = q.where(PlayerAvailability.api_fixture_id == int(parsed.api_fixture_id))
    else:
        q = q.where(
            PlayerAvailability.api_fixture_id.is_(None),
            PlayerAvailability.reason == parsed.reason,
        )
    return db.scalar(q)


def deactivate_scope(
    db: Session,
    *,
    season: int,
    league_id: int,
    fixture_ids: list[int] | None = None,
    team_ids: list[int] | None = None,
) -> int:
    """Imposta is_active=false per record attivi nello scope (force ingest)."""
    conds = [
        PlayerAvailability.season == int(season),
        PlayerAvailability.league_id == int(league_id),
        PlayerAvailability.is_active.is_(True),
    ]
    if fixture_ids:
        conds.append(PlayerAvailability.fixture_id.in_(fixture_ids))
    if team_ids:
        conds.append(PlayerAvailability.team_id.in_(team_ids))
    stmt = update(PlayerAvailability).where(and_(*conds)).values(is_active=False)
    res = db.execute(stmt)
    return int(res.rowcount or 0)


def upsert_availability_record(
    db: Session,
    *,
    season: int,
    league_id: int,
    parsed: ParsedAvailabilityRecord,
    fetched_at: datetime | None = None,
) -> tuple[PlayerAvailability, bool]:
    """
    Upsert idempotente. Ritorna (row, registry_matched).
  registry_matched=True se player_id risolto in player_registry.
    """
    now = fetched_at or _utc_now()
    fixture = _resolve_fixture(db, parsed.api_fixture_id, season, league_id)
    team = _resolve_team(db, parsed.api_team_id)
    registry_id = _resolve_registry_id(db, parsed.api_player_id)
    matched = registry_id is not None

    row = _match_existing(db, season=season, league_id=league_id, parsed=parsed)
    if row is None:
        row = PlayerAvailability(
            season=int(season),
            league_id=int(league_id),
            player_name=parsed.player_name,
            source=parsed.source,
        )
        db.add(row)

    row.fixture_id = int(fixture.id) if fixture is not None else None
    row.api_fixture_id = parsed.api_fixture_id
    row.team_id = int(team.id) if team is not None else None
    row.api_team_id = parsed.api_team_id
    row.team_name = parsed.team_name
    row.player_id = registry_id
    row.api_player_id = parsed.api_player_id
    row.player_name = parsed.player_name
    row.availability_status = parsed.availability_status
    row.availability_type = parsed.availability_type
    row.reason = parsed.reason
    row.reported_at = parsed.reported_at
    row.start_date = parsed.start_date
    row.end_date = parsed.end_date
    row.fetched_at = now
    row.is_active = True
    row.raw_json = parsed.raw_json
    return row, matched
