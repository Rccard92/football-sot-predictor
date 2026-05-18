"""Persist formazione da blocco API → fixture_lineups + fixture_lineup_players."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureLineup, FixtureLineupPlayer, PlayerRegistry, Season, Team
from app.services.lineups.lineup_parsing import (
    ParsedLineupPlayer,
    block_has_official_lineup,
    parse_api_lineup_block,
    parse_lineup_player_lists,
)

LINEUP_SOURCE = "api_football_fixtures_lineups"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_registry_id(db: Session, api_player_id: int | None) -> Any:
    if api_player_id is None:
        return None
    return db.scalar(select(PlayerRegistry.id).where(PlayerRegistry.api_player_id == int(api_player_id)))


def _insert_players(
    db: Session,
    *,
    lineup_row: FixtureLineup,
    fixture: Fixture,
    season_year: int,
    team: Team,
    players: list[ParsedLineupPlayer],
) -> int:
    n = 0
    for p in players:
        db.add(
            FixtureLineupPlayer(
                fixture_lineup_id=int(lineup_row.id),
                fixture_id=int(fixture.id),
                api_fixture_id=int(fixture.api_fixture_id),
                season=int(season_year),
                league_id=int(fixture.league_id),
                team_id=int(team.id),
                api_team_id=int(team.api_team_id),
                player_id=_resolve_registry_id(db, p.api_player_id),
                api_player_id=p.api_player_id,
                player_name=p.player_name,
                number=p.number,
                position=p.position,
                grid=p.grid,
                is_starter=p.is_starter,
                is_substitute=p.is_substitute,
            ),
        )
        n += 1
    return n


def upsert_lineup_from_api_block(
    db: Session,
    *,
    fixture: Fixture,
    season_row: Season,
    team: Team,
    block: dict[str, Any],
    fetched_at: datetime | None = None,
) -> tuple[FixtureLineup | None, int]:
    """
    Upsert fixture_lineups + replace fixture_lineup_players per un team block API.
    Ritorna (lineup_row, players_upserted). None se il block non ha startXI ufficiale.
    """
    if not block_has_official_lineup(block):
        return None, 0

    formation_str, coach_name, starters, subs = parse_api_lineup_block(block)
    start_xi = block.get("startXI")
    substitutes = block.get("substitutes")
    lineup_json = {
        "startXI": start_xi,
        "substitutes": substitutes,
        "coach": block.get("coach"),
    }
    now = fetched_at or _utc_now()
    season_year = int(season_row.year)

    row = db.scalar(
        select(FixtureLineup).where(
            FixtureLineup.fixture_id == int(fixture.id),
            FixtureLineup.team_id == int(team.id),
        ),
    )
    if row is None:
        row = FixtureLineup(
            fixture_id=int(fixture.id),
            team_id=int(team.id),
        )
        db.add(row)
        db.flush()

    row.api_fixture_id = int(fixture.api_fixture_id)
    row.season = season_year
    row.league_id = int(fixture.league_id)
    row.api_team_id = int(team.api_team_id)
    row.formation = formation_str
    row.coach_name = coach_name
    row.is_available = True
    row.is_official = True
    row.source = LINEUP_SOURCE
    row.fetched_at = now
    row.start_xi = start_xi  # type: ignore[assignment]
    row.substitutes = substitutes  # type: ignore[assignment]
    row.lineup_json = lineup_json
    row.raw_json = block

    db.execute(delete(FixtureLineupPlayer).where(FixtureLineupPlayer.fixture_lineup_id == int(row.id)))
    all_players = starters + subs
    players_n = _insert_players(
        db,
        lineup_row=row,
        fixture=fixture,
        season_year=season_year,
        team=team,
        players=all_players,
    )
    return row, players_n


def upsert_lineup_from_stored_jsonb(
    db: Session,
    *,
    fixture: Fixture,
    season_row: Season,
    team: Team,
    formation: str | None,
    coach_name: str | None,
    start_xi: Any,
    substitutes: Any,
    raw_json: dict[str, Any] | None,
) -> tuple[FixtureLineup, int]:
    """Compat legacy: persist da JSONB già salvato (bootstrap completed fixtures)."""
    starters, subs = parse_lineup_player_lists(start_xi, substitutes)
    if not starters:
        raise ValueError("no_starters_in_jsonb")

    now = _utc_now()
    season_year = int(season_row.year)
    row = db.scalar(
        select(FixtureLineup).where(
            FixtureLineup.fixture_id == int(fixture.id),
            FixtureLineup.team_id == int(team.id),
        ),
    )
    if row is None:
        row = FixtureLineup(fixture_id=int(fixture.id), team_id=int(team.id))
        db.add(row)
        db.flush()

    row.api_fixture_id = int(fixture.api_fixture_id)
    row.season = season_year
    row.league_id = int(fixture.league_id)
    row.api_team_id = int(team.api_team_id)
    row.formation = formation
    row.coach_name = coach_name
    row.is_available = True
    row.is_official = True
    row.source = LINEUP_SOURCE
    row.fetched_at = now
    row.start_xi = start_xi  # type: ignore[assignment]
    row.substitutes = substitutes  # type: ignore[assignment]
    row.lineup_json = {"startXI": start_xi, "substitutes": substitutes}
    row.raw_json = raw_json

    db.execute(delete(FixtureLineupPlayer).where(FixtureLineupPlayer.fixture_lineup_id == int(row.id)))
    players_n = _insert_players(
        db,
        lineup_row=row,
        fixture=fixture,
        season_year=season_year,
        team=team,
        players=starters + subs,
    )
    return row, players_n
