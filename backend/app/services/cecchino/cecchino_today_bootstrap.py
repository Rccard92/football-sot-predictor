"""Bootstrap minimo DB per Cecchino Today (no SOT)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture
from app.services.api_football_client import ApiFootballClient
from app.services.cecchino.league_ingest_helpers import (
    get_or_create_competition_for_league_season,
    get_or_create_league_by_api_id,
    get_or_create_season,
    safe_upsert_team_from_api_item,
)
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


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

    league_name = str(league_meta.get("name") or f"League {provider_league_id}")
    league_country = str(league_meta.get("country") or "") or None
    logo = league_meta.get("logo")
    logo_url = str(logo) if logo else None

    league = get_or_create_league_by_api_id(
        db,
        api_league_id=provider_league_id,
        name=league_name,
        country=league_country,
        logo_url=logo_url,
        raw_json=league_meta,
    )

    season_row = get_or_create_season(
        db,
        league_id=int(league.id),
        year=season_year,
        label=str(season_year),
        raw_json={"year": season_year},
    )

    comp, created = get_or_create_competition_for_league_season(
        db,
        provider_league_id=provider_league_id,
        season=season_year,
        league_id=int(league.id),
        season_id=int(season_row.id),
        league_meta=league_meta,
        league_name=league_name,
        league_country=league_country or league.country,
    )
    if created:
        warnings.append(f"created_competition:{comp.key}")

    try:
        teams = af_client.get_teams(provider_league_id, season_year)
        for t in teams:
            safe_upsert_team_from_api_item(db, ingest, t)
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
