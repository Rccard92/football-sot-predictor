"""Risoluzione cartellini: events → statistics → DB team stats."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.fixture_team_stat import FixtureTeamStat
from app.models.referee_fixture_card_summary import (
    CARD_SOURCE_DB_TEAM_STATS,
    CARD_SOURCE_EVENTS,
    CARD_SOURCE_STATISTICS,
    RefereeFixtureCardSummary,
)
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.referee_cards_parser import (
    MatchCardsBySide,
    cards_by_side_from_team_stats_rows,
    match_cards_by_side_from_statistics_blocks,
    match_cards_from_events,
)
from sqlalchemy import select


def resolve_cards_for_api_fixture(
    client: ApiFootballClient,
    *,
    api_fixture_id: int,
    home_team_api_id: int | None,
    away_team_api_id: int | None,
    db: Session | None = None,
    fixture_id: int | None = None,
) -> tuple[MatchCardsBySide | None, str | None]:
    """Restituisce (cards, card_source)."""
    try:
        events = client.get_fixture_events(int(api_fixture_id))
        by_side = match_cards_from_events(
            events,
            home_team_api_id=home_team_api_id,
            away_team_api_id=away_team_api_id,
        )
        if by_side.has_data():
            return by_side, CARD_SOURCE_EVENTS
    except ApiFootballError:
        pass

    try:
        blocks = client.get_fixture_statistics(int(api_fixture_id))
        by_side = match_cards_by_side_from_statistics_blocks(
            blocks,
            home_team_api_id=home_team_api_id,
            away_team_api_id=away_team_api_id,
        )
        if by_side.has_data():
            return by_side, CARD_SOURCE_STATISTICS
    except ApiFootballError:
        pass

    if db is not None and fixture_id is not None:
        rows = list(
            db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == int(fixture_id))).all(),
        )
        by_side_map = {str(r.side or "").lower(): r for r in rows}
        home_row = by_side_map.get("home") or (rows[0] if rows else None)
        away_row = by_side_map.get("away") or (rows[1] if len(rows) > 1 else None)
        by_side = cards_by_side_from_team_stats_rows(home_row, away_row)
        if by_side.has_data():
            return by_side, CARD_SOURCE_DB_TEAM_STATS

    return None, None


def card_summary_to_dict(row: RefereeFixtureCardSummary) -> dict[str, Any]:
    return {
        "api_fixture_id": int(row.api_fixture_id),
        "fixture_id": int(row.fixture_id) if row.fixture_id else None,
        "match": f"{row.home_team_name or 'Casa'} - {row.away_team_name or 'Trasferta'}",
        "date": row.kickoff_at.isoformat() if row.kickoff_at else None,
        "yellow_cards": row.total_yellow,
        "red_cards": row.total_red,
        "home_yellow": row.home_yellow,
        "away_yellow": row.away_yellow,
        "home_red": row.home_red,
        "away_red": row.away_red,
        "card_source": row.card_source,
        "league_api_id": int(row.league_api_id),
        "season_year": int(row.season_year),
    }
