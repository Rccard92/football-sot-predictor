"""Bootstrap minimo DB per Cecchino Today (no SOT)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, League, Season
from app.services.api_football_client import ApiFootballClient
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


def _slug_key(league_id: int, season: int) -> str:
    return f"cecchino_today_{league_id}_{season}"


def ensure_competition_and_history(
    db: Session,
    *,
    api_item: dict[str, Any],
    client: ApiFootballClient | None = None,
) -> tuple[Competition | None, Fixture | None, list[str]]:
    """
    Crea/trova competition, importa teams + fixture FT, upsert fixture odierna.
    Ritorna (competition, local_fixture, warnings).
    """
    warnings: list[str] = []
    league_meta = api_item.get("league") or {}
    provider_league_id = int(league_meta.get("id") or 0)
    season_year = int(league_meta.get("season") or 0)
    if not provider_league_id or not season_year:
        return None, None, ["missing_league_or_season_in_api_item"]

    af_client = client or ApiFootballClient()
    ingest = IngestionService(client=af_client)

    league = db.scalar(select(League).where(League.api_league_id == provider_league_id))
    if league is None:
        league = League(
            api_league_id=provider_league_id,
            name=str(league_meta.get("name") or f"League {provider_league_id}"),
            country=str(league_meta.get("country") or "") or None,
            logo_url=league_meta.get("logo"),
            raw_json=league_meta,
        )
        db.add(league)
        db.flush()

    season_row = db.scalar(
        select(Season).where(Season.league_id == league.id, Season.year == season_year),
    )
    if season_row is None:
        season_row = Season(
            league_id=league.id,
            year=season_year,
            label=str(season_year),
            is_current=True,
            raw_json={"year": season_year},
        )
        db.add(season_row)
        db.flush()

    comp = db.scalar(
        select(Competition).where(
            Competition.provider_league_id == provider_league_id,
            Competition.season == season_year,
        ),
    )
    if comp is None:
        comp = Competition(
            key=_slug_key(provider_league_id, season_year),
            name=str(league_meta.get("name") or league.name),
            country=str(league_meta.get("country") or league.country),
            provider="api_sports",
            provider_league_id=provider_league_id,
            season=season_year,
            timezone="Europe/Rome",
            is_active=True,
            is_primary=False,
            pre_match_cron_enabled=False,
            status="cecchino_today_bootstrap",
            league_id=league.id,
            season_id=season_row.id,
            raw_payload=league_meta,
        )
        db.add(comp)
        db.flush()
        warnings.append(f"created_competition:{comp.key}")

    try:
        teams = af_client.get_teams(provider_league_id, season_year)
        for t in teams:
            ingest._upsert_team_from_api_item(db, t)
    except Exception as exc:
        warnings.append(f"teams_import_error:{exc!s}"[:200])

    try:
        ft_items = af_client.get_fixtures(provider_league_id, season_year, status="FT")
        n = 0
        for item in ft_items:
            if ingest._upsert_fixture_from_api_item(
                db,
                league,
                season_row,
                item,
                competition_id=int(comp.id),
            ):
                n += 1
        warnings.append(f"fixtures_ft_imported:{n}")
    except Exception as exc:
        warnings.append(f"fixtures_import_error:{exc!s}"[:200])

    api_fixture_id = int((api_item.get("fixture") or {})["id"])
    if not ingest._upsert_fixture_from_api_item(
        db,
        league,
        season_row,
        api_item,
        competition_id=int(comp.id),
    ):
        warnings.append(f"today_fixture_upsert_failed:{api_fixture_id}")

    db.flush()
    local_fx = db.scalar(select(Fixture).where(Fixture.api_fixture_id == api_fixture_id))
    return comp, local_fx, warnings
