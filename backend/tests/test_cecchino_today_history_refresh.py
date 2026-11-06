"""Storico dei campionati: si reimporta quando ci sono partite finite dopo l'ultimo import (06/11/2026).

Caso reale: il Brasileirao era stato importato a maggio con tutto il calendario; le partite esistevano
gia' nel DB, quindi la scansione non reimportava mai i risultati e da luglio restavano "da giocare".
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_FOOTBALL_KEY", "test-key")

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


from app.models.cecchino_league_stats_cache import CecchinoLeagueStatsCache  # noqa: E402
from app.models.fixture import Fixture  # noqa: E402
from app.services.cecchino.cecchino_today_bootstrap import history_needs_refresh, results_pending  # noqa: E402

NOW = datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc)
_next_id = iter(range(1, 10_000))


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for m in (Fixture, CecchinoLeagueStatsCache):
        m.__table__.create(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


def _fx(db, kickoff, status, league=3, season=2):
    i = next(_next_id)
    db.add(
        Fixture(
            id=i, api_fixture_id=1000 + i, league_id=league, season_id=season, home_team_id=1, away_team_id=2,
            kickoff_at=kickoff, status=status, created_at=NOW, updated_at=NOW,
        )
    )
    db.flush()


def _cache(db, imported_at, ok=True):
    db.add(
        CecchinoLeagueStatsCache(
            id=next(_next_id), provider_league_id=71, season=2026, last_stats_import_at=imported_at,
            fixtures_ft_imported=100, has_minimum_stats=ok, stats_quality_status="imported",
            created_at=imported_at, updated_at=imported_at,
        )
    )
    db.flush()


def _needs(db):
    return history_needs_refresh(db, provider_league_id=71, season=2026, league_id=3, season_id=2)


def test_match_finished_after_last_import_is_pending(db):
    _fx(db, NOW - timedelta(hours=10), "NS")  # giocata ieri sera, ancora "da giocare" da noi
    assert results_pending(db, league_id=3, season_id=2, since=NOW - timedelta(hours=24), now=NOW)


def test_postponed_before_last_import_is_not_pending(db):
    _fx(db, NOW - timedelta(days=20), "NS")  # rinviata: non deve far reimportare ogni giorno
    assert not results_pending(db, league_id=3, season_id=2, since=NOW - timedelta(hours=24), now=NOW)


def test_finished_or_future_matches_are_not_pending(db):
    _fx(db, NOW - timedelta(hours=10), "FT")
    _fx(db, NOW - timedelta(hours=1), "1H")  # in corso da meno di 3 ore
    _fx(db, NOW + timedelta(hours=12), "NS")
    _fx(db, NOW - timedelta(hours=10), "NS", league=99)  # altro campionato
    assert not results_pending(db, league_id=3, season_id=2, since=NOW - timedelta(hours=24), now=NOW)


def test_never_imported_league_with_stale_calendar_is_pending(db):
    _fx(db, NOW - timedelta(days=100), "NS")
    assert results_pending(db, league_id=3, season_id=2, since=None, now=NOW)


def test_no_cache_row_needs_refresh(db):
    assert _needs(db)


def test_fresh_cache_without_new_results_does_not_refresh(db, monkeypatch):
    # SQLite rilegge le date senza fuso: la validita' della cache (24 ore) qui si da' per buona
    monkeypatch.setattr("app.services.cecchino.cecchino_today_bootstrap.is_league_stats_cache_valid", lambda row: row is not None)
    _cache(db, datetime.now(timezone.utc) - timedelta(hours=2))
    _fx(db, datetime.now(timezone.utc) + timedelta(hours=5), "NS")
    assert not _needs(db)


def test_fresh_cache_with_result_after_import_refreshes(db, monkeypatch):
    monkeypatch.setattr("app.services.cecchino.cecchino_today_bootstrap.is_league_stats_cache_valid", lambda row: row is not None)
    now = datetime.now(timezone.utc)
    _cache(db, now - timedelta(hours=20))
    _fx(db, now - timedelta(hours=8), "NS")  # finita dopo l'import di ieri mattina
    assert _needs(db)


def test_naive_import_time_is_read_as_utc(db):
    now = datetime.now(timezone.utc)
    _fx(db, now - timedelta(hours=8), "NS")
    assert results_pending(db, league_id=3, season_id=2, since=(now - timedelta(hours=20)).replace(tzinfo=None))
