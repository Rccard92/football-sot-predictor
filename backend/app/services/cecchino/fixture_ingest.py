"""Salvataggio di squadre e partite API-Football per Cecchino (senza il vecchio motore SOT).

Stesso comportamento dei metodi `IngestionService._upsert_team_from_api_item` e
`_upsert_fixture_from_api_item` del vecchio motore SOT, copiati qui senza modifiche: la scansione
di Cecchino Today e il collegamento dati non importano piu' `ingestion_service` (che resta intatto,
con i suoi dati, per il motore SOT).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, League, Season, Team
from app.services.datetime_utils import ensure_datetime_utc

logger = logging.getLogger(__name__)


def _parse_dt(value: str | None):
    if not value:
        raise ValueError("data partita mancante")
    parsed = ensure_datetime_utc(value, field_name="fixture.date")
    if parsed is None:
        raise ValueError("data partita mancante")
    return parsed


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    try:
        return int(str(val).strip())
    except ValueError:
        return None


def upsert_team_from_api_item(db: Session, item: dict[str, Any]) -> None:
    t = item.get("team") or {}
    v = item.get("venue") or {}
    api_team_id = int(t["id"])
    name = str(t.get("name") or "")
    logo = t.get("logo")
    logo_url = str(logo) if logo else None
    code_raw = t.get("code")
    code = str(code_raw).strip()[:16] if code_raw else None
    country_raw = t.get("country")
    country = str(country_raw) if country_raw else None
    founded = _parse_int(t.get("founded"))
    national = bool(t.get("national")) if t.get("national") is not None else False
    venue_name_raw = v.get("name")
    venue_name = str(venue_name_raw)[:255] if venue_name_raw else None
    venue_city_raw = v.get("city")
    venue_city = str(venue_city_raw)[:128] if venue_city_raw else None
    team = db.scalar(select(Team).where(Team.api_team_id == api_team_id))
    if team is None:
        team = Team(
            api_team_id=api_team_id,
            name=name,
            code=code,
            country=country,
            founded=founded,
            national=national,
            logo_url=logo_url,
            venue_name=venue_name,
            venue_city=venue_city,
            raw_json=item,
        )
        db.add(team)
    else:
        team.name = name or team.name
        team.code = code or team.code
        team.country = country or team.country
        team.founded = founded if founded is not None else team.founded
        team.national = national
        team.logo_url = logo_url or team.logo_url
        team.venue_name = venue_name or team.venue_name
        team.venue_city = venue_city or team.venue_city
        team.raw_json = item


def upsert_fixture_from_api_item(
    db: Session,
    league: League,
    season_row: Season,
    item: dict[str, Any],
    *,
    competition_id: int | None = None,
) -> bool:
    fx = item.get("fixture") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    venue_fx = fx.get("venue") or {}
    api_fixture_id = int(fx["id"])
    status_obj = fx.get("status") or {}
    status_short = str(status_obj.get("short") or "NS")
    status_long_raw = status_obj.get("long")
    status_long = str(status_long_raw)[:128] if status_long_raw else None
    elapsed = _parse_int(status_obj.get("elapsed"))
    kickoff_at = _parse_dt(fx.get("date"))
    home_api = int((teams.get("home") or {})["id"])
    away_api = int((teams.get("away") or {})["id"])
    league_meta = item.get("league") or {}
    round_raw = fx.get("round")
    if round_raw is None:
        round_raw = league_meta.get("round")
    round_str = str(round_raw)[:64] if round_raw is not None else None
    referee_raw = fx.get("referee")
    referee = str(referee_raw)[:255] if referee_raw else None
    tz_raw = fx.get("timezone")
    timezone_str = str(tz_raw)[:64] if tz_raw else None
    vn_raw = venue_fx.get("name")
    venue_name = str(vn_raw)[:255] if vn_raw else None
    vc_raw = venue_fx.get("city")
    venue_city = str(vc_raw)[:128] if vc_raw else None

    home_team = db.scalar(select(Team).where(Team.api_team_id == home_api))
    away_team = db.scalar(select(Team).where(Team.api_team_id == away_api))
    if home_team is None or away_team is None:
        logger.warning(
            "Fixture %s saltata: team mancante in DB (home=%s away=%s)",
            api_fixture_id,
            home_api,
            away_api,
        )
        return False

    goals_home = _parse_int(goals.get("home"))
    goals_away = _parse_int(goals.get("away"))

    row = db.scalar(select(Fixture).where(Fixture.api_fixture_id == api_fixture_id))
    if row is None:
        row = Fixture(
            api_fixture_id=api_fixture_id,
            league_id=league.id,
            season_id=season_row.id,
            competition_id=competition_id,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            round=round_str,
            referee=referee,
            timezone=timezone_str,
            kickoff_at=kickoff_at,
            status=status_short,
            status_long=status_long,
            elapsed=elapsed,
            goals_home=goals_home,
            goals_away=goals_away,
            venue_name=venue_name,
            venue_city=venue_city,
            raw_json=item,
        )
        db.add(row)
    else:
        row.league_id = league.id
        row.season_id = season_row.id
        if competition_id is not None:
            row.competition_id = competition_id
        row.home_team_id = home_team.id
        row.away_team_id = away_team.id
        row.round = round_str
        row.referee = referee
        row.timezone = timezone_str
        row.kickoff_at = kickoff_at
        row.status = status_short
        row.status_long = status_long
        row.elapsed = elapsed
        row.goals_home = goals_home
        row.goals_away = goals_away
        row.venue_name = venue_name
        row.venue_city = venue_city
        row.raw_json = item
    return True


class FixtureIngest:
    """Stessa interfaccia dei due metodi usati da Cecchino sul vecchio IngestionService."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _upsert_team_from_api_item(self, db: Session, item: dict[str, Any]) -> None:
        upsert_team_from_api_item(db, item)

    def _upsert_fixture_from_api_item(
        self,
        db: Session,
        league: League,
        season_row: Season,
        item: dict[str, Any],
        *,
        competition_id: int | None = None,
    ) -> bool:
        return upsert_fixture_from_api_item(db, league, season_row, item, competition_id=competition_id)
