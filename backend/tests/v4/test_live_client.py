"""`V4ApiClient`: guardia budget, filtro ai 16 campionati, paginazione quote, contesto d'uso per job."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.services.api_usage_context import BudgetGuardStop
from app.services.cecchino_v4.live.client import V4ApiClient, api_calls_today, ensure_budget
from tests.v4.test_live_support import NOW, FakeClient, create_usage_table, load_sample, seed_usage_events


@pytest.fixture()
def usage_db(v4_db):
    create_usage_table(v4_db)
    return v4_db


def test_fixtures_by_date_filters_to_16_leagues(usage_db):
    fake = FakeClient()
    client = V4ApiClient(fake, db=usage_db, stop_at=100)
    items = client.fixtures_by_date(date(2026, 9, 21))
    assert [it["fixture"]["id"] for it in items] == [1001, 1002, 1003]  # 1999 (Champions League) escluso
    assert client.calls == 1
    assert fake.calls[0] == ("fixtures", {"date": "2026-09-21", "timezone": "Europe/Rome"})


def test_budget_guard_refuses_when_daily_count_reached(usage_db):
    seed_usage_events(usage_db, 5)  # oggi, ora reale: la guardia conta il giorno UTC corrente
    assert api_calls_today(usage_db) == 5
    with pytest.raises(BudgetGuardStop) as exc:
        ensure_budget(usage_db, stop_at=5)
    assert exc.value.details == {"calls_today": 5, "stop_at": 5}
    assert ensure_budget(usage_db, stop_at=6) == 5


def test_budget_counts_only_today_and_real_calls(usage_db):
    today = datetime.now(timezone.utc)
    seed_usage_events(usage_db, 3, when=today - timedelta(days=1))
    seed_usage_events(usage_db, 2, when=today)
    usage_db.execute(
        text("INSERT INTO api_usage_events (provider_source, endpoint, cache_hit, negative_cache_hit, created_at) VALUES ('api_football', 'odds', 1, 0, :ts)"),
        {"ts": today.replace(tzinfo=None)},
    )
    usage_db.commit()
    assert api_calls_today(usage_db) == 2  # la cache non conta
    assert api_calls_today(usage_db, day=(today - timedelta(days=1)).date()) == 3


def test_client_stops_mid_run_and_records_usage(usage_db, monkeypatch):
    monkeypatch.setattr("app.services.cecchino_v4.settings.api_daily_stop", lambda: 3)
    fake = FakeClient()
    client = V4ApiClient(fake, db=usage_db)
    client.bind(usage_db, job_id="job-1", scan_date=NOW.date())
    client.fixture_statistics(1003)
    client.fixture_events(1003)
    client.fixture_players(1003)
    usage_db.commit()
    assert api_calls_today(usage_db) == 3
    with pytest.raises(BudgetGuardStop):
        client.fixture_lineups(1003)
    assert client.calls == 3  # la quarta non e' partita
    assert len(fake.calls) == 3
    # contesto d'uso: job e partita
    assert all(ctx.job_id == "job-1" for ctx in fake.contexts)
    assert [ctx.provider_fixture_id for ctx in fake.contexts] == [1003, 1003, 1003]


def test_odds_by_league_date_paginates(usage_db):
    page1 = load_sample("odds_by_league_date")
    page1["paging"] = {"current": 1, "total": 2}
    page2 = load_sample("odds_by_league_date")
    page2["paging"] = {"current": 2, "total": 2}
    page2["response"] = page2["response"][:1]
    page2["response"][0]["fixture"]["id"] = 1005
    fake = FakeClient(odds_pages=[page1, page2])
    client = V4ApiClient(fake, db=usage_db, stop_at=100)
    items = client.odds_by_league_date(135, 2026, date(2026, 9, 21), 8)
    assert [it["fixture"]["id"] for it in items] == [1001, 1004, 1005]
    assert client.calls == 2
    assert fake.calls[0][1] == {"league": 135, "season": 2026, "date": "2026-09-21", "bookmaker": 8, "page": 1}
    assert fake.calls[1][1]["page"] == 2
    assert all(ctx.provider_league_id == 135 for ctx in fake.contexts)


def test_other_helpers_count_one_call_each(usage_db):
    fake = FakeClient()
    client = V4ApiClient(fake, db=usage_db, stop_at=100)
    assert client.fixture_by_id(1003)["fixture"]["id"] == 1003
    assert len(client.injuries(135, 2026)) == 2
    assert len(client.standings(135, 2026)) == 1
    assert len(client.odds_by_fixture(1001)) == 1
    assert [b["name"] for b in client.bookmakers()] == ["10Bet", "Betfair", "Bet365", "1xBet"]
    assert len(client.fixtures_by_league_season(135, 2026)) == 2
    assert client.calls == 6
    assert fake.endpoints() == ["fixtures", "injuries", "standings", "odds", "odds/bookmakers", "fixtures"]
