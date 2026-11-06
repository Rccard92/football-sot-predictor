"""Bootstrap minimo DB per Cecchino Today (no SOT)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture
from app.services.api_football_client import ApiFootballClient
from app.services.cecchino.cecchino_league_stats_cache_service import (
    get_league_stats_cache,
    is_league_stats_cache_valid,
    upsert_league_stats_cache,
)
from app.services.cecchino.league_ingest_helpers import (
    get_or_create_competition_for_league_season,
    get_or_create_league_by_api_id,
    get_or_create_season,
    safe_upsert_team_from_api_item,
)
from app.services.cecchino.fixture_ingest import FixtureIngest

logger = logging.getLogger(__name__)

# Una partita e' "finita da registrare" 3 ore dopo il calcio d'inizio.
RESULT_PENDING_AFTER_KICKOFF = timedelta(hours=3)
_NOT_FINISHED = ("NS", "TBD", "1H", "HT", "2H", "ET", "BT", "P", "LIVE", "SUSP", "INT")


def results_pending(
    db: Session,
    *,
    league_id: int,
    season_id: int,
    since: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Il campionato ha partite ancora "da giocare" nel nostro archivio ma gia' finite dopo l'ultimo import.

    Dal 06/11/2026: prima lo storico si reimportava solo alla scadenza della cache (24 ore) e solo per le
    partite nuove nel DB. Cosi' il Brasileirao, importato a maggio con tutto il calendario, e' rimasto
    fermo per mesi; e con la scansione su due giorni le partite create il giorno prima avrebbero perso i
    risultati della sera. Le partite rinviate non contano: valgono solo quelle iniziate dopo l'ultimo import."""
    now = now or datetime.now(dt_timezone.utc)
    q = select(Fixture.id).where(
        Fixture.league_id == int(league_id),
        Fixture.season_id == int(season_id),
        Fixture.status.in_(_NOT_FINISHED),
        Fixture.kickoff_at < now - RESULT_PENDING_AFTER_KICKOFF,
    )
    if since is not None:
        since = since if since.tzinfo else since.replace(tzinfo=dt_timezone.utc)
        q = q.where(Fixture.kickoff_at > since - RESULT_PENDING_AFTER_KICKOFF)
    return db.scalar(q.limit(1)) is not None


def history_needs_refresh(
    db: Session,
    *,
    provider_league_id: int,
    season: int,
    league_id: int,
    season_id: int,
) -> bool:
    """Va reimportato lo storico FT del campionato? Cache scaduta o risultati arrivati dopo l'ultimo import."""
    cache_row = get_league_stats_cache(db, provider_league_id=provider_league_id, season=season)
    if not is_league_stats_cache_valid(cache_row):
        return True
    return results_pending(db, league_id=league_id, season_id=season_id, since=cache_row.last_stats_import_at)


def ensure_competition_and_history(
    db: Session,
    *,
    api_item: dict[str, Any],
    client: ApiFootballClient | None = None,
    skip_api_import: bool = False,
    bootstrapped_leagues: set[tuple[int, int]] | None = None,
    metrics: Any | None = None,
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
    ingest = FixtureIngest(client=af_client)

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

    league_key = (provider_league_id, season_year)
    cache_row = get_league_stats_cache(db, provider_league_id=provider_league_id, season=season_year)
    cache_valid = is_league_stats_cache_valid(cache_row)
    in_memory_hit = bootstrapped_leagues is not None and league_key in bootstrapped_leagues

    stale_results = (
        cache_valid
        and not in_memory_hit
        and results_pending(db, league_id=int(league.id), season_id=int(season_row.id), since=cache_row.last_stats_import_at)
    )
    should_import = not skip_api_import and not in_memory_hit and (not cache_valid or stale_results)

    fixtures_imported = int(cache_row.fixtures_ft_imported) if cache_row else 0
    if should_import:
        try:
            teams = af_client.get_teams(provider_league_id, season_year)
            if metrics is not None:
                metrics.api_calls["teams"] = metrics.api_calls.get("teams", 0) + 1
                metrics.sync_api_calls_total()
            for t in teams:
                safe_upsert_team_from_api_item(db, ingest, t)
        except Exception as exc:
            warnings.append(f"teams_import_error:{exc!s}"[:200])

        try:
            ft_items = af_client.get_fixtures(provider_league_id, season_year, status="FT")
            if metrics is not None:
                metrics.api_calls["fixtures"] = metrics.api_calls.get("fixtures", 0) + 1
                metrics.sync_api_calls_total()
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
            fixtures_imported = n
            warnings.append(f"fixtures_ft_imported:{n}")
            upsert_league_stats_cache(
                db,
                provider_league_id=provider_league_id,
                season=season_year,
                country=league_country,
                league_name=league_name,
                fixtures_ft_imported=n,
                has_minimum_stats=n >= 6,
                stats_quality_status="imported" if n >= 6 else "low_sample",
            )
        except Exception as exc:
            warnings.append(f"fixtures_import_error:{exc!s}"[:200])
    elif cache_valid or in_memory_hit:
        warnings.append(f"league_stats_cache_hit:{provider_league_id}:{season_year}")

    if bootstrapped_leagues is not None:
        bootstrapped_leagues.add(league_key)

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
