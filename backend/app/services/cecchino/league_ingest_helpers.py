"""Helper idempotenti get-or-create per ingest Cecchino Today (leghe, stagioni, competizioni)."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Competition, League, Season, Team
from app.services.ingestion_service import IngestionService

T = TypeVar("T")


def _flush_or_fetch_existing(
    db: Session,
    *,
    factory: Callable[[], T],
    fetch: Callable[[], T | None],
) -> T:
    """INSERT in savepoint; su IntegrityError rollback savepoint e ri-fetch."""
    existing = fetch()
    if existing is not None:
        return existing

    nested = db.begin_nested()
    try:
        obj = factory()
        db.add(obj)
        db.flush()
        nested.commit()
        return obj
    except IntegrityError:
        nested.rollback()
        existing = fetch()
        if existing is None:
            raise
        return existing


def _update_league_fields(
    league: League,
    *,
    name: str,
    country: str | None,
    logo_url: str | None,
    raw_json: dict[str, Any] | None,
) -> None:
    if name:
        league.name = name
    if country:
        league.country = country
    if logo_url:
        league.logo_url = logo_url
    if raw_json:
        league.raw_json = raw_json


def get_or_create_league_by_api_id(
    db: Session,
    *,
    api_league_id: int,
    name: str,
    country: str | None = None,
    logo_url: str | None = None,
    raw_json: dict[str, Any] | None = None,
) -> League:
    league = db.scalar(select(League).where(League.api_league_id == api_league_id))
    if league is not None:
        _update_league_fields(
            league,
            name=name,
            country=country,
            logo_url=logo_url,
            raw_json=raw_json,
        )
        return league

    def _fetch() -> League | None:
        return db.scalar(select(League).where(League.api_league_id == api_league_id))

    def _factory() -> League:
        return League(
            api_league_id=api_league_id,
            name=name or f"League {api_league_id}",
            country=country,
            logo_url=logo_url,
            raw_json=raw_json,
        )

    league = _flush_or_fetch_existing(db, factory=_factory, fetch=_fetch)
    _update_league_fields(
        league,
        name=name,
        country=country,
        logo_url=logo_url,
        raw_json=raw_json,
    )
    return league


def get_or_create_season(
    db: Session,
    *,
    league_id: int,
    year: int,
    label: str | None = None,
    raw_json: dict[str, Any] | None = None,
) -> Season:
    season_row = db.scalar(
        select(Season).where(Season.league_id == league_id, Season.year == year),
    )
    if season_row is not None:
        if label:
            season_row.label = label
        if raw_json:
            season_row.raw_json = raw_json
        return season_row

    def _fetch() -> Season | None:
        return db.scalar(
            select(Season).where(Season.league_id == league_id, Season.year == year),
        )

    def _factory() -> Season:
        return Season(
            league_id=league_id,
            year=year,
            label=label or str(year),
            is_current=True,
            raw_json=raw_json or {"year": year},
        )

    season_row = _flush_or_fetch_existing(db, factory=_factory, fetch=_fetch)
    if label:
        season_row.label = label
    if raw_json:
        season_row.raw_json = raw_json
    return season_row


def _competition_slug_key(league_id: int, season: int) -> str:
    return f"cecchino_today_{league_id}_{season}"


def get_or_create_competition_for_league_season(
    db: Session,
    *,
    provider_league_id: int,
    season: int,
    league_id: int,
    season_id: int,
    league_meta: dict[str, Any],
    league_name: str,
    league_country: str | None,
) -> tuple[Competition, bool]:
    """Ritorna (competition, created)."""
    comp = db.scalar(
        select(Competition).where(
            Competition.provider_league_id == provider_league_id,
            Competition.season == season,
        ),
    )
    if comp is not None:
        if league_name:
            comp.name = league_name
        if league_country:
            comp.country = league_country
        comp.league_id = league_id
        comp.season_id = season_id
        if league_meta:
            comp.raw_payload = league_meta
        return comp, False

    comp_key = _competition_slug_key(provider_league_id, season)

    def _fetch() -> Competition | None:
        found = db.scalar(
            select(Competition).where(
                Competition.provider_league_id == provider_league_id,
                Competition.season == season,
            ),
        )
        if found is not None:
            return found
        return db.scalar(select(Competition).where(Competition.key == comp_key))

    def _factory() -> Competition:
        return Competition(
            key=comp_key,
            name=league_name,
            country=league_country,
            provider="api_sports",
            provider_league_id=provider_league_id,
            season=season,
            timezone="Europe/Rome",
            is_active=True,
            is_primary=False,
            pre_match_cron_enabled=False,
            status="cecchino_today_bootstrap",
            league_id=league_id,
            season_id=season_id,
            raw_payload=league_meta,
        )

    comp = _flush_or_fetch_existing(db, factory=_factory, fetch=_fetch)
    if league_name:
        comp.name = league_name
    if league_country:
        comp.country = league_country
    comp.league_id = league_id
    comp.season_id = season_id
    if league_meta:
        comp.raw_payload = league_meta
    return comp, True


def safe_upsert_team_from_api_item(
    db: Session,
    ingest: IngestionService,
    item: dict[str, Any],
) -> None:
    """Upsert team con recovery IntegrityError (race su api_team_id)."""
    api_team_id = int((item.get("team") or {})["id"])

    def _fetch() -> Team | None:
        return db.scalar(select(Team).where(Team.api_team_id == api_team_id))

    if _fetch() is not None:
        ingest._upsert_team_from_api_item(db, item)
        return

    nested = db.begin_nested()
    try:
        ingest._upsert_team_from_api_item(db, item)
        db.flush()
        nested.commit()
    except IntegrityError:
        nested.rollback()
        existing = _fetch()
        if existing is None:
            raise
        ingest._upsert_team_from_api_item(db, item)


def recover_session_if_inactive(db: Session) -> None:
    """Ripristina sessione SQLAlchemy dopo errore DB non gestito."""
    if not db.is_active:
        db.rollback()
