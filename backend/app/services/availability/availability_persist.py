"""Upsert record player_availability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from app.models import Fixture, PlayerAvailability, PlayerRegistry, Team
from app.services.availability.availability_fixture_scope import infer_record_scope_from_parsed
from app.models.player_availability import (
    SCOPE_FIXTURE_LEVEL,
    SOURCE_API_FOOTBALL_INJURIES,
    SOURCE_API_FOOTBALL_SIDELINED,
)
from app.services.availability.availability_parsing import SOURCE_INJURIES, ParsedAvailabilityRecord
from app.services.availability.providers.types import NormalizedAvailabilityCandidate

API_AUTO_SOURCES = (SOURCE_API_FOOTBALL_INJURIES, SOURCE_API_FOOTBALL_SIDELINED)


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


def _match_existing_parsed(
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
    if parsed.source_detail is not None:
        q = q.where(PlayerAvailability.source_detail == parsed.source_detail)
    if parsed.api_fixture_id is not None:
        q = q.where(PlayerAvailability.api_fixture_id == int(parsed.api_fixture_id))
    else:
        q = q.where(
            PlayerAvailability.api_fixture_id.is_(None),
            PlayerAvailability.reason == parsed.reason,
        )
    return db.scalar(q)


def _match_existing_candidate(
    db: Session,
    candidate: NormalizedAvailabilityCandidate,
) -> PlayerAvailability | None:
    q = select(PlayerAvailability).where(
        PlayerAvailability.season == int(candidate.season),
        PlayerAvailability.league_id == int(candidate.league_id),
        PlayerAvailability.source == candidate.source,
        PlayerAvailability.source_detail == candidate.source_detail,
        PlayerAvailability.api_team_id == candidate.api_team_id,
        PlayerAvailability.api_player_id == candidate.api_player_id,
        PlayerAvailability.api_fixture_id == int(candidate.api_fixture_id),
    )
    return db.scalar(q)


def deactivate_fixture_injuries(
    db: Session,
    *,
    season: int,
    league_id: int,
    api_fixture_id: int,
) -> int:
    """Disattiva solo record API injuries (legacy)."""
    return deactivate_fixture_api_availability(
        db,
        season=season,
        league_id=league_id,
        api_fixture_id=api_fixture_id,
        sources=(SOURCE_INJURIES,),
    )


def deactivate_fixture_api_availability(
    db: Session,
    *,
    season: int,
    league_id: int,
    api_fixture_id: int,
    sources: tuple[str, ...] = API_AUTO_SOURCES,
) -> int:
    """Disattiva record API automatici per fixture (non manual_override)."""
    stmt = (
        update(PlayerAvailability)
        .where(
            PlayerAvailability.season == int(season),
            PlayerAvailability.league_id == int(league_id),
            PlayerAvailability.is_active.is_(True),
            PlayerAvailability.source.in_(list(sources)),
            PlayerAvailability.api_fixture_id == int(api_fixture_id),
        )
        .values(is_active=False)
    )
    res = db.execute(stmt)
    return int(res.rowcount or 0)


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
) -> tuple[PlayerAvailability, bool, bool]:
    """
    Upsert idempotente. Ritorna (row, registry_matched, created).
    registry_matched=True se player_id risolto in player_registry.
    """
    now = fetched_at or _utc_now()
    fixture = _resolve_fixture(db, parsed.api_fixture_id, season, league_id)
    team = _resolve_team(db, parsed.api_team_id)
    registry_id = _resolve_registry_id(db, parsed.api_player_id)
    matched = registry_id is not None

    row = _match_existing_parsed(db, season=season, league_id=league_id, parsed=parsed)
    created = row is None
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
    row.source_detail = parsed.source_detail
    row.reported_at = parsed.reported_at
    row.start_date = parsed.start_date
    row.end_date = parsed.end_date
    row.fixture_date = parsed.fixture_date
    if row.fixture_date is None and fixture is not None and fixture.kickoff_at is not None:
        ko = fixture.kickoff_at
        row.fixture_date = ko.date() if hasattr(ko, "date") else ko
    row.record_scope = infer_record_scope_from_parsed(
        parsed,
        fixture_id_fk=int(fixture.id) if fixture is not None else None,
    )
    row.fetched_at = now
    row.is_active = True
    raw = dict(parsed.raw_json) if parsed.raw_json else {}
    meta = raw.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
        raw["_meta"] = meta
    row.raw_json = raw
    return row, matched, created


def upsert_availability_candidate(
    db: Session,
    *,
    candidate: NormalizedAvailabilityCandidate,
    fetched_at: datetime | None = None,
) -> tuple[PlayerAvailability, bool, bool]:
    """Upsert da candidato provider normalizzato."""
    now = fetched_at or _utc_now()
    if candidate.team_id is None and candidate.api_team_id is not None:
        team = _resolve_team(db, candidate.api_team_id)
        if team is not None:
            candidate.team_id = int(team.id)
    registry_id = _resolve_registry_id(db, candidate.api_player_id)
    matched_reg = registry_id is not None

    row = _match_existing_candidate(db, candidate)
    created = row is None
    if row is None:
        row = PlayerAvailability(
            season=int(candidate.season),
            league_id=int(candidate.league_id),
            player_name=candidate.player_name,
            source=candidate.source,
            source_detail=candidate.source_detail,
        )
        db.add(row)

    row.fixture_id = int(candidate.fixture_id)
    row.api_fixture_id = int(candidate.api_fixture_id)
    row.team_id = candidate.team_id
    row.api_team_id = candidate.api_team_id
    row.team_name = candidate.team_name
    row.player_id = registry_id
    row.api_player_id = candidate.api_player_id
    row.player_name = candidate.player_name
    row.availability_status = candidate.availability_status
    row.availability_type = candidate.availability_type
    row.reason = candidate.reason
    row.source_detail = candidate.source_detail
    row.reported_at = candidate.reported_at
    row.start_date = candidate.start_date
    row.end_date = candidate.end_date
    row.fixture_date = candidate.fixture_date
    row.record_scope = candidate.record_scope
    row.fetched_at = now
    row.is_active = True
    raw = dict(candidate.raw_json) if candidate.raw_json else {}
    meta = raw.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["confidence"] = candidate.confidence
        meta["applicability_status"] = candidate.applicability_status
        meta["applicability_reason"] = candidate.applicability_reason
        meta["api_league_id"] = int(candidate.api_league_id)
    row.raw_json = raw
    return row, matched_reg, created


def upsert_fixture_injury_record(
    db: Session,
    *,
    fx: Fixture,
    season_year: int,
    league_internal_id: int,
    parsed: ParsedAvailabilityRecord,
    fetched_at: datetime | None = None,
    source_detail: str | None = None,
    api_league_id: int | None = None,
) -> tuple[PlayerAvailability, bool, bool]:
    """Upsert fixture-level con FK e date dalla fixture DB."""
    ko = fx.kickoff_at
    parsed.api_fixture_id = int(fx.api_fixture_id)
    parsed.fixture_date = ko.date() if hasattr(ko, "date") else ko
    if source_detail:
        parsed.source_detail = source_detail
    if api_league_id is not None and parsed.raw_json is not None:
        meta = parsed.raw_json.setdefault("_meta", {})
        if isinstance(meta, dict):
            meta["api_league_id"] = int(api_league_id)
    row, matched, created = upsert_availability_record(
        db,
        season=int(season_year),
        league_id=int(league_internal_id),
        parsed=parsed,
        fetched_at=fetched_at,
    )
    row.fixture_id = int(fx.id)
    row.api_fixture_id = int(fx.api_fixture_id)
    row.record_scope = SCOPE_FIXTURE_LEVEL
    if row.fixture_date is None and ko is not None:
        row.fixture_date = ko.date() if hasattr(ko, "date") else ko
    return row, matched, created
