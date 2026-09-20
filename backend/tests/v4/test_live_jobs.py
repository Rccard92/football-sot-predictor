"""Job della pipeline live V4 su SQLite con client finto: upsert e mappa, post partita, formazioni,
infortuni e classifiche, registro quote (istantanee e chiusura), copertura, backfill, budget, job fermi,
qualita' dati."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.cecchino_v4 import (
    CecchinoV4Fixture,
    CecchinoV4Job,
    CecchinoV4LeagueDay,
    CecchinoV4OddsSnapshot,
    CecchinoV4PlayerMinutes,
    CecchinoV4TeamMap,
)
from app.services.cecchino_v4.live import jobs as live_jobs
from app.services.cecchino_v4.live.client import V4ApiClient
from app.services.cecchino_v4.live.jobs import (
    JobAlreadyRunning,
    UnknownJob,
    api_budget_today,
    data_quality,
    engine_data,
    mark_stale_jobs,
    odds_registry_status,
    run_job,
)
from tests.v4.test_live_support import HISTORY_NAMES, NOW, FakeClient, create_usage_table, seed_usage_events


@pytest.fixture()
def db(v4_db):
    create_usage_table(v4_db)
    return v4_db


def _client(fake: FakeClient | None = None, *, stop_at: int = 1000) -> tuple[FakeClient, V4ApiClient]:
    fake = fake or FakeClient()
    return fake, V4ApiClient(fake, stop_at=stop_at)


def _run(db, name, *, fake=None, params=None, now=NOW, stop_at=1000):
    fake, client = _client(fake, stop_at=stop_at)
    job = run_job(db, name, client=client, params=params, now=now, history_names=HISTORY_NAMES)
    return job, fake


def _fixture(db, api_id: int) -> CecchinoV4Fixture:
    return db.scalars(select(CecchinoV4Fixture).where(CecchinoV4Fixture.api_fixture_id == api_id)).one()


# --- fixtures ---------------------------------------------------------------------------------------------
def test_fixtures_job_upserts_and_maps_teams(db):
    job, fake = _run(db, "fixtures")
    assert job.status == "done", job.error_message
    assert job.api_calls == 8  # oggi + 7 giorni, una chiamata per data
    assert fake.endpoints() == ["fixtures"] * 8
    assert job.result_json["fixtures_seen"] == 3 * 8 and job.result_json["created"] == 3
    assert job.result_json["updated"] == 21 and job.result_json["unmapped_teams"] == []
    assert db.scalar(select(CecchinoV4Fixture.id).where(CecchinoV4Fixture.api_fixture_id == 1999)) is None

    milan_inter = _fixture(db, 1001)
    assert milan_inter.league_code == "I1" and milan_inter.competition == "Serie A" and milan_inter.season_label == "2026/2027"
    assert milan_inter.home_team == "AC Milan" and milan_inter.home_team_history == "Milan"
    assert milan_inter.away_team == "Inter" and milan_inter.away_team_history == "Inter"
    assert milan_inter.status == "NS" and milan_inter.lineups_status == "non_note"

    derby = _fixture(db, 1002)
    assert derby.league_code == "E0"
    assert (derby.home_team_history, derby.away_team_history) == ("Man City", "Man United")

    finished = _fixture(db, 1003)
    assert finished.status == "FT" and (finished.ft_home, finished.ft_away, finished.ht_home, finished.ht_away) == (2, 1, 1, 0)

    maps = db.scalars(select(CecchinoV4TeamMap)).all()
    assert len(maps) == 6  # 4 squadre Serie A + 2 Premier, una riga ciascuna
    assert all(m.confidence >= 0.8 and not m.verified for m in maps)


def test_fixtures_job_respects_existing_verified_map_and_flags_unknown(db):
    db.add(CecchinoV4TeamMap(league_code="I1", api_team_id=489, api_team_name="AC Milan", history_team_name="Milan (verificato)", confidence=0.3, verified=True))
    db.commit()
    names = {"I1": {"Inter", "Juventus", "Napoli"}, "E0": set()}
    fake, client = _client()
    job = run_job(db, "fixtures", client=client, params={"days": 0}, now=NOW, history_names=names)
    assert job.status == "done"
    assert _fixture(db, 1001).home_team_history == "Milan (verificato)"
    assert _fixture(db, 1002).home_team_history is None  # nessun nome storico per la Premier: candidato ma non applicato
    unmapped = job.result_json["unmapped_teams"]
    assert {u["api_team_name"] for u in unmapped} == {"Manchester City", "Manchester United"}


def test_fixtures_job_with_date_param_and_second_run_updates(db):
    job, _ = _run(db, "fixtures", params={"date": "2026-09-21", "days": 1})
    assert job.result_json["dates"] == ["2026-09-21", "2026-09-22"]
    fx = _fixture(db, 1001)
    fx.stats_json = {"home": {"shots": 1}, "away": {"shots": 2}}
    db.commit()
    job2, _ = _run(db, "fixtures", params={"days": 0})
    assert job2.result_json["created"] == 0 and job2.result_json["updated"] == 3
    assert _fixture(db, 1001).stats_json == {"home": {"shots": 1}, "away": {"shots": 2}}  # l'upsert non tocca le statistiche


# --- post partita ---------------------------------------------------------------------------------------------
def test_post_match_job_fills_stats_events_players(db):
    _run(db, "fixtures", params={"days": 0})
    job, fake = _run(db, "post_match")
    assert job.status == "done", job.error_message
    assert job.result_json == {"dates_refreshed": 0, "fixtures_processed": 1, "with_stats": 1, "without_stats": 0}
    assert fake.endpoints() == ["fixtures/statistics", "fixtures/events", "fixtures/players"]
    assert job.api_calls == 3

    fx = _fixture(db, 1003)
    assert fx.stats_json["home"]["shots"] == 14 and fx.stats_json["home"]["sot"] == 6 and fx.stats_json["away"]["red"] == 1
    assert fx.stats_json["home"]["possession"] == 55 and fx.stats_json["home"]["xg"] == 1.87
    assert fx.stats_fetched_at is not None
    assert len(fx.events_json) == 5 and fx.events_json[0]["type"] == "goal"
    minutes = db.scalars(select(CecchinoV4PlayerMinutes).where(CecchinoV4PlayerMinutes.fixture_id == fx.id)).all()
    assert len(minutes) == 6 and sum(1 for m in minutes if m.started) == 4

    # seconda corsa: niente da fare, nessuna chiamata
    job2, fake2 = _run(db, "post_match")
    assert job2.result_json["fixtures_processed"] == 0 and fake2.calls == []


def test_post_match_refreshes_stale_status_and_fetches_score(db):
    _run(db, "fixtures", params={"days": 0})
    fx = _fixture(db, 1001)
    fx.status = "NS"
    fx.kickoff_at = NOW - timedelta(hours=5)  # ieri sera, ma in tabella ancora NS
    fx.match_date = (NOW - timedelta(hours=5)).date()
    db.commit()
    job, fake = _run(db, "post_match")
    assert job.status == "done", job.error_message
    assert job.result_json["dates_refreshed"] == 1  # una chiamata /fixtures?date= per la data da aggiornare
    assert fake.calls[0] == ("fixtures", {"date": "2026-09-20", "timezone": "Europe/Rome"})
    assert _fixture(db, 1003).stats_json is not None

    # risultato mancante su una partita finita: una chiamata /fixtures?id= prima delle statistiche
    fin = _fixture(db, 1003)
    fin.ft_home = None
    fin.ft_away = None
    fin.stats_json = None
    db.commit()
    job2, fake2 = _run(db, "post_match")
    assert job2.result_json["dates_refreshed"] == 0
    assert fake2.calls[0] == ("fixtures", {"id": 1003})
    assert fake2.endpoints() == ["fixtures", "fixtures/statistics", "fixtures/events", "fixtures/players"]
    assert (_fixture(db, 1003).ft_home, _fixture(db, 1003).ft_away) == (2, 1)


# --- formazioni ---------------------------------------------------------------------------------------------
def test_lineups_job_only_in_window(db):
    _run(db, "fixtures", params={"days": 1})
    early = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)  # City-United alle 15:30 UTC e Milan-Inter alle 18:45: fuori finestra
    job, fake = _run(db, "lineups", now=early)
    assert job.result_json["fixtures_checked"] == 0 and fake.calls == []

    at_60 = datetime(2026, 9, 21, 17, 45, tzinfo=timezone.utc)
    job, fake = _run(db, "lineups", now=at_60)
    assert job.result_json == {"fixtures_checked": 1, "official": 1, "pending": 0}
    assert fake.endpoints() == ["fixtures/lineups"]
    fx = _fixture(db, 1001)
    assert fx.lineups_status == "ufficiali" and fx.lineups_json["home"]["formation"] == "3-5-2"

    at_30 = datetime(2026, 9, 21, 18, 15, tzinfo=timezone.utc)
    job, fake = _run(db, "lineups", now=at_30)
    assert job.result_json["fixtures_checked"] == 0  # gia' ufficiali: nessuna chiamata


# --- infortuni e classifiche ------------------------------------------------------------------------------------
def test_injuries_and_standings_one_call_per_league(db):
    job, fake = _run(db, "injuries")
    assert job.status == "done" and job.api_calls == 16
    assert job.result_json["season"] == 2026 and job.result_json["day"] == "2026-09-20"
    assert {p["league"] for _, p in fake.calls} == {39, 40, 41, 42, 135, 136, 140, 141, 78, 79, 61, 62, 88, 144, 94, 203}
    rows = db.scalars(select(CecchinoV4LeagueDay)).all()
    assert len(rows) == 16 and all(len(r.injuries_json) == 2 for r in rows)

    job2, fake2 = _run(db, "standings", params={"league_code": "I1"})
    assert job2.api_calls == 1 and fake2.calls[0] == ("standings", {"league": 135, "season": 2026})
    row = db.scalars(select(CecchinoV4LeagueDay).where(CecchinoV4LeagueDay.league_code == "I1")).one()
    assert row.standings_json[0]["team"] == "Juventus" and row.injuries_json is not None  # stessa riga del giorno
    assert len(db.scalars(select(CecchinoV4LeagueDay)).all()) == 16


# --- registro quote ---------------------------------------------------------------------------------------------
def test_odds_snapshot_kind_and_skip_rules(db):
    _run(db, "fixtures", params={"days": 2})
    job, fake = _run(db, "odds_snapshot")  # 12:00 Roma -> pomeriggio
    assert job.status == "done", job.error_message
    assert job.result_json["kind"] == "pomeriggio"
    assert job.result_json["days"] == ["2026-09-20", "2026-09-21", "2026-09-22"]
    # solo campionato/data con partite in tabella (I1 e E0 del 21) per 2 bookmaker: 4 chiamate su 96 possibili
    assert job.result_json["league_date_calls"] == 4 and job.api_calls == 4
    assert {(p["league"], p["date"], p["bookmaker"]) for _, p in fake.calls} == {(135, "2026-09-21", 8), (135, "2026-09-21", 3), (39, "2026-09-21", 8), (39, "2026-09-21", 3)}
    snaps = db.scalars(select(CecchinoV4OddsSnapshot)).all()
    assert len(snaps) == 1  # il campione Bet365 copre solo la partita 1001; 1004 non e' in tabella
    snap = snaps[0]
    assert snap.fixture_id == _fixture(db, 1001).id and snap.bookmaker_id == 8 and snap.kind == "pomeriggio"
    assert snap.markets_json["HOME"] == 2.6 and snap.markets_json["STAT:sot:total:over:8.5"] == 1.9

    # stessa istantanea entro 3 ore: I1/Bet365 saltato, gli altri ritentati
    job2, fake2 = _run(db, "odds_snapshot", now=NOW + timedelta(hours=1))
    assert job2.result_json["league_date_calls"] == 3
    assert len(db.scalars(select(CecchinoV4OddsSnapshot)).all()) == 1

    # la sera e' un'altra istantanea
    evening = NOW.replace(hour=17)  # 19:00 Roma
    job3, _ = _run(db, "odds_snapshot", now=evening)
    assert job3.result_json["kind"] == "sera" and job3.result_json["snapshots_stored"] == 1
    kinds = sorted(s.kind for s in db.scalars(select(CecchinoV4OddsSnapshot)).all())
    assert kinds == ["pomeriggio", "sera"]


def test_odds_snapshot_morning_kind(db):
    _run(db, "fixtures", params={"days": 2})
    job, _ = _run(db, "odds_snapshot", now=NOW.replace(hour=7))  # 09:00 Roma
    assert job.result_json["kind"] == "mattina"


def test_odds_closing_per_fixture_all_bookmakers(db):
    _run(db, "fixtures", params={"days": 1})
    before = datetime(2026, 9, 21, 18, 20, tzinfo=timezone.utc)  # 25 minuti prima di Milan-Inter
    job, fake = _run(db, "odds_closing", now=before)
    assert job.status == "done", job.error_message
    assert job.result_json == {"fixtures_in_window": 1, "fixtures_fetched": 1, "snapshots_stored": 2}
    assert fake.calls == [("odds", {"fixture": 1001})]
    snaps = db.scalars(select(CecchinoV4OddsSnapshot).order_by(CecchinoV4OddsSnapshot.bookmaker_id)).all()
    assert [(s.bookmaker_id, s.kind) for s in snaps] == [(3, "chiusura"), (8, "chiusura")]
    assert snaps[0].markets_json["AH_HOME:-0.5"] == 3.1
    assert all(s.taken_at is not None for s in snaps)

    job2, fake2 = _run(db, "odds_closing", now=before + timedelta(minutes=5))
    assert job2.result_json["fixtures_fetched"] == 0 and fake2.calls == []  # chiusura gia' registrata

    too_early = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
    job3, fake3 = _run(db, "odds_closing", now=too_early)
    assert job3.result_json["fixtures_in_window"] == 0


# --- copertura ------------------------------------------------------------------------------------------------------
def test_coverage_scan_builds_matrix_and_unmapped(db):
    _run(db, "fixtures", params={"days": 1})
    job, fake = _run(db, "coverage_scan")
    assert job.status == "done", job.error_message
    assert job.api_calls == 2 and fake.endpoints() == ["odds", "odds"]  # le due partite NS della settimana
    result = job.result_json
    assert result["fixtures_checked"] == 2
    by_code = {c["league_code"]: c for c in result["coverage"]}
    assert len(by_code) == 16
    i1 = by_code["I1"]
    assert i1["fixtures_checked"] == 1 and i1["fixtures_with_odds"] == 1
    assert i1["markets"] == {"FT_1X2": True, "DOUBLE_CHANCE": True, "FT_OVER_UNDER": True, "HT_1X2": True, "AH": True, "STAT:shots": True, "STAT:sot": True, "STAT:corners": True, "STAT:cards": True, "STAT:fouls": True}
    assert i1["by_bookmaker"]["Betfair"]["STAT:sot"] is False and i1["by_bookmaker"]["Betfair"]["STAT:corners"] is True
    assert i1["by_bookmaker"]["Bet365"]["STAT:fouls"] is True
    assert by_code["I2"]["fixtures_checked"] == 0 and not any(by_code["I2"]["markets"].values())
    names = {u["bet_name"]: u for u in result["unmapped_bets"]}
    assert set(names) == {"Both Teams Score", "HT/FT Double", "Corners 1x2", "Player Shots On Target"}
    assert names["Both Teams Score"]["count"] == 2 and names["Both Teams Score"]["bookmakers"] == ["Bet365"]
    assert sorted(names["Both Teams Score"]["leagues"]) == ["E0", "I1"]
    # la chiamata vale anche come istantanea del registro
    assert result["snapshots_stored"] == 4
    assert live_jobs.latest_coverage(db) == result["coverage"]


def test_coverage_scan_limit_and_league_filter(db):
    _run(db, "fixtures", params={"days": 1})
    job, fake = _run(db, "coverage_scan", params={"league_code": "E0", "limit": 5})
    assert job.api_calls == 1 and fake.calls == [("odds", {"fixture": 1002})]


# --- backfill --------------------------------------------------------------------------------------------------------
def test_backfill_is_resumable_and_needs_params(db):
    job, _ = _run(db, "backfill", params={"league_code": "I1"})
    assert job.status == "failed" and "season" in job.error_message

    job, fake = _run(db, "backfill", params={"league_code": "I1", "season": 2026})
    assert job.status == "done", job.error_message
    assert job.result_json["fixtures_final"] == 1 and job.result_json["processed"] == 1 and job.result_json["remaining_without_stats"] == 0
    assert fake.endpoints() == ["fixtures", "fixtures/statistics", "fixtures/events", "fixtures/players", "fixtures/lineups"]
    fx = _fixture(db, 1003)
    assert fx.stats_json is not None and fx.lineups_status == "ufficiali"
    assert db.scalar(select(CecchinoV4Fixture.id).where(CecchinoV4Fixture.api_fixture_id == 1001)) is None  # solo partite finite

    job2, fake2 = _run(db, "backfill", params={"league_code": "I1", "season": 2026})
    assert job2.api_calls == 1 and job2.result_json["processed"] == 0  # ripresa: niente da rifare


# --- budget, quota, job fermi ----------------------------------------------------------------------------------------------
def test_job_refuses_to_start_when_budget_reached(db, monkeypatch):
    monkeypatch.setattr("app.services.cecchino_v4.settings.api_daily_stop", lambda: 10)
    seed_usage_events(db, 10)
    fake = FakeClient()
    job = run_job(db, "fixtures", client=V4ApiClient(fake), now=NOW, history_names=HISTORY_NAMES)
    assert job.status == "failed" and "budget" in job.error_message.lower()
    assert job.api_calls == 0 and fake.calls == []
    assert job.result_json == {"budget": {"calls_today": 10, "stop_at": 10}}
    assert api_budget_today(db) == {"date": datetime.now(timezone.utc).date().isoformat(), "calls": 10, "stop_at": 10}


def test_job_stops_mid_run_when_budget_reached_and_keeps_partial_data(db, monkeypatch):
    monkeypatch.setattr("app.services.cecchino_v4.settings.api_daily_stop", lambda: 2)
    fake = FakeClient()
    job = run_job(db, "fixtures", client=V4ApiClient(fake), now=NOW, history_names=HISTORY_NAMES)
    assert job.status == "failed" and "Arresto budget" in job.error_message
    assert job.api_calls == 2 and len(fake.calls) == 2  # la terza data non e' stata chiesta
    assert len(db.scalars(select(CecchinoV4Fixture)).all()) == 3  # le prime due date sono in tabella
    assert api_budget_today(db)["calls"] == 2


def test_job_fails_cleanly_on_provider_quota_exhausted(db):
    job, fake = _run(db, "fixtures", fake=FakeClient(fail_after=3))
    assert job.status == "failed" and "Quota API-Football esaurita" in job.error_message
    assert job.api_calls == 4  # la quarta e' partita ed e' fallita
    assert job.finished_at is not None


def test_stale_jobs_are_marked_and_fresh_running_job_blocks(db):
    old = CecchinoV4Job(id=str(uuid.uuid4()), name="fixtures", status="running", heartbeat_at=NOW - timedelta(minutes=45), created_at=NOW - timedelta(hours=1))
    db.add(old)
    db.commit()
    job, _ = _run(db, "fixtures", params={"days": 0})
    assert job.status == "done"
    db.refresh(old)
    assert old.status == "stale" and old.finished_at is not None and "heartbeat" in old.error_message

    fresh = CecchinoV4Job(id=str(uuid.uuid4()), name="odds_snapshot", status="running", heartbeat_at=NOW - timedelta(minutes=10), created_at=NOW - timedelta(minutes=10))
    db.add(fresh)
    db.commit()
    with pytest.raises(JobAlreadyRunning):
        _run(db, "odds_snapshot")
    assert mark_stale_jobs(db, now=NOW + timedelta(minutes=25)) == 1  # 35 minuti senza heartbeat
    with pytest.raises(UnknownJob):
        _run(db, "predict")


def test_job_row_bookkeeping(db):
    job, _ = _run(db, "injuries", params={"league_code": "I1"})
    assert job.name == "injuries" and job.params_json == {"league_code": "I1"}
    assert job.progress_pct == 100.0 and job.step == "completato"
    assert job.created_at is not None and job.finished_at is not None and job.heartbeat_at is not None
    listed = live_jobs.recent_jobs(db)
    assert listed[0]["job_id"] == job.id and listed[0]["status"] == "done" and listed[0]["api_calls"] == 1
    assert listed[0]["created_at"].endswith("+00:00")


# --- qualita' dati e GET /engine/data ------------------------------------------------------------------------------------------
def test_data_quality_and_engine_data(db):
    _run(db, "fixtures", params={"days": 1})
    quality = {q["league_code"]: q for q in data_quality(db, 14, now=NOW)}
    assert len(quality) == 16
    assert quality["I1"] == {"league_code": "I1", "competition": "Serie A", "fixtures": 1, "missing_stats_pct": 100.0, "missing_lineups_pct": 100.0, "missing_odds_pct": 100.0}
    assert quality["E0"]["fixtures"] == 0 and quality["E0"]["missing_stats_pct"] is None

    _run(db, "post_match")
    fx = _fixture(db, 1003)
    db.add(CecchinoV4OddsSnapshot(fixture_id=fx.id, bookmaker_id=8, kind="chiusura", taken_at=NOW - timedelta(hours=20), markets_json={"HOME": 2.1}, created_at=NOW))
    db.commit()
    q = {q["league_code"]: q for q in data_quality(db, 14, now=NOW)}["I1"]
    assert q["missing_stats_pct"] == 0.0 and q["missing_odds_pct"] == 0.0 and q["missing_lineups_pct"] == 100.0

    registry = odds_registry_status(db, now=NOW)
    assert registry["snapshots_today"] == 0  # istantanea di ieri sera (ora di Roma)
    assert registry["last_taken_at"] == (NOW - timedelta(hours=20)).isoformat()
    db.add(CecchinoV4OddsSnapshot(fixture_id=fx.id, bookmaker_id=3, kind="pomeriggio", taken_at=NOW, markets_json={"HOME": 2.2}, created_at=NOW))
    db.commit()
    registry = odds_registry_status(db, now=NOW)
    assert registry["snapshots_today"] == 1 and registry["by_kind"] == {"pomeriggio": 1}

    payload = engine_data(db, now=NOW)
    assert set(payload) == {"coverage", "quality", "api_budget", "odds_registry"}
    assert payload["coverage"] == []  # nessun coverage_scan ancora
    assert payload["api_budget"]["stop_at"] == 7000
