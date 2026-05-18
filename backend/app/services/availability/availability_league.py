"""Risoluzione league internal id vs API-Football api_league_id per availability."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import League, Season
from app.services.ingestion_service import IngestionService


class AvailabilityLeagueConfigError(ValueError):
    """api_league_id mancante o non valido per Serie A."""


@dataclass(frozen=True)
class SerieALeagueContext:
    league_internal_id: int
    api_league_id: int
    league_name: str | None
    season_row_id: int


def resolve_serie_a_league_context(db: Session, season_year: int) -> SerieALeagueContext:
    """
    season.league_id è FK interno (leagues.id).
    Le chiamate API-Football injuries devono usare League.api_league_id (es. 135 Serie A).
    """
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, int(season_year))
    league = db.scalar(select(League).where(League.id == int(season_row.league_id)))
    if league is None:
        raise AvailabilityLeagueConfigError(
            f"Lega interna id={season_row.league_id} non trovata per stagione {season_year}",
        )
    api_id = league.api_league_id
    if api_id is None or int(api_id) <= 0:
        raise AvailabilityLeagueConfigError("API league id mancante per Serie A")
    return SerieALeagueContext(
        league_internal_id=int(league.id),
        api_league_id=int(api_id),
        league_name=league.name,
        season_row_id=int(season_row.id),
    )
