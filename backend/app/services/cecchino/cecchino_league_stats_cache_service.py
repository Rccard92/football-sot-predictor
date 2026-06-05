"""Cache import storico lega/stagione Cecchino Today."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cecchino_league_stats_cache import CecchinoLeagueStatsCache


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_league_stats_cache(
    db: Session,
    *,
    provider_league_id: int,
    season: int,
) -> CecchinoLeagueStatsCache | None:
    return db.scalar(
        select(CecchinoLeagueStatsCache).where(
            CecchinoLeagueStatsCache.provider_league_id == int(provider_league_id),
            CecchinoLeagueStatsCache.season == int(season),
        ),
    )


def is_league_stats_cache_valid(row: CecchinoLeagueStatsCache | None) -> bool:
    if row is None or row.last_stats_import_at is None:
        return False
    if not isinstance(row.last_stats_import_at, datetime):
        return False
    settings = get_settings()
    ttl_hours = (
        int(settings.cecchino_league_stats_cache_hours_ok)
        if row.has_minimum_stats
        else int(settings.cecchino_league_stats_cache_hours)
    )
    cutoff = _utcnow() - timedelta(hours=ttl_hours)
    return row.last_stats_import_at >= cutoff


def upsert_league_stats_cache(
    db: Session,
    *,
    provider_league_id: int,
    season: int,
    country: str | None,
    league_name: str | None,
    fixtures_ft_imported: int,
    has_minimum_stats: bool,
    stats_quality_status: str,
) -> CecchinoLeagueStatsCache:
    row = get_league_stats_cache(db, provider_league_id=provider_league_id, season=season)
    if row is None:
        row = CecchinoLeagueStatsCache(
            provider_league_id=int(provider_league_id),
            season=int(season),
        )
        db.add(row)
    row.country = country
    row.league_name = league_name
    row.last_stats_import_at = _utcnow()
    row.fixtures_ft_imported = int(fixtures_ft_imported)
    row.has_minimum_stats = bool(has_minimum_stats)
    row.stats_quality_status = stats_quality_status
    db.flush()
    return row
