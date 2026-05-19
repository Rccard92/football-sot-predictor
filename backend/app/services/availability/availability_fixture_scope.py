"""Classificazione scope record e applicabilità per fixture."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture, PlayerAvailability, Season, Team
from app.models.player_availability import (
    SCOPE_FIXTURE_LEVEL,
    SCOPE_MANUAL_FIXTURE_LEVEL,
    SCOPE_MANUAL_TEAM_LEVEL,
    SCOPE_SEASON_LEVEL,
    SCOPE_TEAM_LEVEL,
)
from app.services.availability.availability_parsing import SOURCE_INJURIES, ParsedAvailabilityRecord

SOURCE_MANUAL = "manual_override"

Applicability = Literal["applicable", "generic_not_applied", "excluded"]


@dataclass(frozen=True)
class FixtureContext:
    fixture_id: int
    api_fixture_id: int
    kickoff: date
    season_year: int
    league_id: int
    home_team_id: int
    away_team_id: int
    api_home_team_id: int
    api_away_team_id: int
    home_name: str
    away_name: str


@dataclass
class FixtureAvailabilityBuckets:
    ctx: FixtureContext
    applicable: list[PlayerAvailability] = field(default_factory=list)
    generic_not_applied: list[PlayerAvailability] = field(default_factory=list)
    excluded: list[PlayerAvailability] = field(default_factory=list)


def _kickoff_date(fixture: Fixture) -> date:
    ko = fixture.kickoff_at
    if isinstance(ko, datetime):
        return ko.date()
    return ko  # type: ignore[return-value]


def _is_manual_source(source: str | None) -> bool:
    if not source:
        return False
    s = source.strip().lower()
    return s == SOURCE_MANUAL or "manual" in s


def infer_record_scope(
    *,
    source: str,
    api_fixture_id: int | None,
    api_team_id: int | None,
    fixture_id_fk: int | None = None,
    has_start_or_end_date: bool = False,
) -> str:
    manual = _is_manual_source(source)
    if manual and fixture_id_fk is not None:
        return SCOPE_MANUAL_FIXTURE_LEVEL
    if manual and (api_team_id is not None or has_start_or_end_date):
        return SCOPE_MANUAL_TEAM_LEVEL
    if api_fixture_id is not None:
        return SCOPE_FIXTURE_LEVEL
    if api_team_id is not None:
        return SCOPE_TEAM_LEVEL
    return SCOPE_SEASON_LEVEL


def infer_record_scope_from_row(row: PlayerAvailability) -> str:
    if row.record_scope:
        return row.record_scope
    return infer_record_scope(
        source=row.source,
        api_fixture_id=row.api_fixture_id,
        api_team_id=row.api_team_id,
        fixture_id_fk=row.fixture_id,
        has_start_or_end_date=row.start_date is not None or row.end_date is not None,
    )


def _team_api_ids(ctx: FixtureContext) -> set[int]:
    return {ctx.api_home_team_id, ctx.api_away_team_id}


def _record_team_in_fixture(row: PlayerAvailability, ctx: FixtureContext) -> bool:
    if row.api_team_id is not None:
        return int(row.api_team_id) in _team_api_ids(ctx)
    if row.team_id is not None:
        return int(row.team_id) in (ctx.home_team_id, ctx.away_team_id)
    return False


def _fixture_level_matches(row: PlayerAvailability, ctx: FixtureContext) -> bool:
    if row.api_fixture_id is not None and int(row.api_fixture_id) == ctx.api_fixture_id:
        return _record_team_in_fixture(row, ctx)
    if row.fixture_id is not None and int(row.fixture_id) == ctx.fixture_id:
        return _record_team_in_fixture(row, ctx)
    return False


def _kickoff_in_date_range(kickoff: date, start: date | None, end: date | None) -> bool:
    if start is None:
        return False
    if kickoff < start:
        return False
    if end is not None and kickoff > end:
        return False
    return True


def classify_record_for_fixture(row: PlayerAvailability, ctx: FixtureContext) -> Applicability:
    scope = infer_record_scope_from_row(row)

    if not _record_team_in_fixture(row, ctx):
        if scope == SCOPE_SEASON_LEVEL:
            return "excluded"
        if row.api_fixture_id is not None and int(row.api_fixture_id) != ctx.api_fixture_id:
            return "excluded"
        return "excluded"

    if scope in (SCOPE_FIXTURE_LEVEL, SCOPE_MANUAL_FIXTURE_LEVEL):
        if _fixture_level_matches(row, ctx):
            return "applicable"
        return "excluded"

    if scope == SCOPE_TEAM_LEVEL:
        if (row.source or "").strip() == SOURCE_INJURIES:
            return "excluded"
        if row.start_date is None:
            return "generic_not_applied"
        if not _kickoff_in_date_range(ctx.kickoff, row.start_date, row.end_date):
            return "excluded"
        return "generic_not_applied"

    if scope == SCOPE_MANUAL_TEAM_LEVEL:
        if row.api_fixture_id is not None and int(row.api_fixture_id) != ctx.api_fixture_id:
            return "excluded"
        if row.start_date is None:
            return "generic_not_applied"
        if not _kickoff_in_date_range(ctx.kickoff, row.start_date, row.end_date):
            return "excluded"
        return "applicable"

    if scope == SCOPE_SEASON_LEVEL:
        return "excluded"

    return "excluded"


def build_fixture_context(db: Session, fixture_id: int) -> FixtureContext | None:
    fx = db.scalar(
        select(Fixture)
        .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
        .where(Fixture.id == int(fixture_id)),
    )
    if fx is None:
        return None
    season_row = db.scalar(select(Season).where(Season.id == int(fx.season_id)))
    if season_row is None:
        return None
    home = fx.home_team
    away = fx.away_team
    if home is None or away is None:
        return None
    return FixtureContext(
        fixture_id=int(fx.id),
        api_fixture_id=int(fx.api_fixture_id),
        kickoff=_kickoff_date(fx),
        season_year=int(season_row.year),
        league_id=int(fx.league_id),
        home_team_id=int(home.id),
        away_team_id=int(away.id),
        api_home_team_id=int(home.api_team_id),
        api_away_team_id=int(away.api_team_id),
        home_name=home.name,
        away_name=away.name,
    )


def load_fixture_availability_buckets(db: Session, fixture_id: int) -> FixtureAvailabilityBuckets | None:
    ctx = build_fixture_context(db, fixture_id)
    if ctx is None:
        return None

    api_teams = [ctx.api_home_team_id, ctx.api_away_team_id]
    team_ids = [ctx.home_team_id, ctx.away_team_id]

    candidates = list(
        db.scalars(
            select(PlayerAvailability).where(
                PlayerAvailability.season == ctx.season_year,
                PlayerAvailability.league_id == ctx.league_id,
                PlayerAvailability.is_active.is_(True),
                or_(
                    PlayerAvailability.api_team_id.in_(api_teams),
                    PlayerAvailability.team_id.in_(team_ids),
                ),
            ),
        ).all(),
    )

    buckets = FixtureAvailabilityBuckets(ctx=ctx)
    for row in candidates:
        bucket = classify_record_for_fixture(row, ctx)
        if bucket == "applicable":
            buckets.applicable.append(row)
        elif bucket == "generic_not_applied":
            buckets.generic_not_applied.append(row)
        else:
            buckets.excluded.append(row)

    return buckets


def applicable_for_team(
    buckets: FixtureAvailabilityBuckets,
    *,
    api_team_id: int,
    team_id: int | None = None,
) -> list[PlayerAvailability]:
    out: list[PlayerAvailability] = []
    for row in buckets.applicable:
        if row.api_team_id is not None and int(row.api_team_id) == int(api_team_id):
            out.append(row)
        elif team_id is not None and row.team_id is not None and int(row.team_id) == int(team_id):
            out.append(row)
    return out


def generic_for_team(
    buckets: FixtureAvailabilityBuckets,
    *,
    api_team_id: int,
    team_id: int | None = None,
) -> list[PlayerAvailability]:
    out: list[PlayerAvailability] = []
    for row in buckets.generic_not_applied:
        if row.api_team_id is not None and int(row.api_team_id) == int(api_team_id):
            out.append(row)
        elif team_id is not None and row.team_id is not None and int(row.team_id) == int(team_id):
            out.append(row)
    return out


def infer_record_scope_from_parsed(
    parsed: ParsedAvailabilityRecord,
    *,
    fixture_id_fk: int | None,
) -> str:
    return infer_record_scope(
        source=parsed.source,
        api_fixture_id=parsed.api_fixture_id,
        api_team_id=parsed.api_team_id,
        fixture_id_fk=fixture_id_fk,
        has_start_or_end_date=parsed.start_date is not None or parsed.end_date is not None,
    )
