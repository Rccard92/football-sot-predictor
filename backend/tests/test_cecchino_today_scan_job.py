"""Test job asincrono scan Cecchino Today (Fase 16)."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi.testclient import TestClient

from app.main import app
from app.models.cecchino_today_scan_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    CecchinoTodayScanJob,
)
from app.services.cecchino.cecchino_constants import CECCHINO_BOOK_POLICY_VERSION
from app.services.cecchino.cecchino_today_odds_fetch import (
    _extract_odds_by_book_from_response,
    fetch_fixture_odds_for_cecchino_bookmakers,
    load_cached_odds_for_fixture,
)
from app.services.cecchino.cecchino_today_scan_job_service import (
    get_running_job_for_date,
    job_to_dict,
    recover_stale_scan_jobs,
    start_scan_job,
)
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics
from app.services.cecchino.cecchino_today_service import _emit_progress, run_scan

client = TestClient(app)


def _mock_1x2_bets(bid: int, h=2.0, d=3.0, a=4.0) -> list[dict]:
    return [
        {
            "bookmakers": [
                {
                    "id": bid,
                    "name": "Test",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": str(h)},
                                {"value": "Draw", "odd": str(d)},
                                {"value": "Away", "odd": str(a)},
                            ],
                        },
                    ],
                },
            ],
        },
    ]


def test_start_scan_job_creates_job_immediately():
    db = MagicMock()
    db.scalar.return_value = None
    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={"has_scan": False},
    ):
        with patch("app.services.cecchino.cecchino_today_scan_job_service.recover_stale_scan_jobs"):
            with patch("app.services.cecchino.cecchino_today_scan_job_service.threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                out = start_scan_job(db, scan_date=date(2026, 6, 4), timezone="Europe/Rome")
    assert out["status"] == JOB_STATUS_QUEUED
    assert out["job_id"]
    assert out["message"] == "Scansione avviata"
    db.add.assert_called_once()
    db.commit.assert_called()


def test_start_scan_job_returns_existing_running():
    db = MagicMock()
    existing = CecchinoTodayScanJob(
        job_id="existing-id",
        scan_date=date(2026, 6, 4),
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
    )
    with patch("app.services.cecchino.cecchino_today_scan_job_service.recover_stale_scan_jobs"):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_running_job_for_date",
            return_value=existing,
        ):
            out = start_scan_job(db, scan_date=date(2026, 6, 4), timezone="Europe/Rome", force_rescan=False)
    assert out["job_id"] == "existing-id"
    assert "già in corso" in out["message"]


def test_start_scan_job_conflict_on_force_rescan_with_running():
    db = MagicMock()
    existing = CecchinoTodayScanJob(
        job_id="running-id",
        scan_date=date(2026, 6, 4),
        timezone="Europe/Rome",
        force_rescan=True,
        status=JOB_STATUS_RUNNING,
    )
    with patch("app.services.cecchino.cecchino_today_scan_job_service.recover_stale_scan_jobs"):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_running_job_for_date",
            return_value=existing,
        ):
            out = start_scan_job(db, scan_date=date(2026, 6, 4), timezone="Europe/Rome", force_rescan=True)
    assert out["status"] == "conflict"


def test_recover_stale_scan_jobs():
    """RUNNING senza heartbeat recente → stale (non più per sola età started_at)."""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    stale = CecchinoTodayScanJob(
        job_id="stale",
        scan_date=date(2026, 6, 4),
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        started_at=now - timedelta(minutes=45),
        updated_at=now - timedelta(minutes=10),
    )
    db.scalars.return_value.all.return_value = [stale]
    count = recover_stale_scan_jobs(db, max_age_minutes=30, no_progress_minutes=5)
    assert count == 1
    assert stale.status == JOB_STATUS_FAILED
    assert "stale_job_timeout" in (stale.errors_json or [])[0]


def test_recover_stale_running_ignores_started_at_age_in_query():
    """RUNNING: la query stale NON usa started_at come causa autonoma."""
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    recover_stale_scan_jobs(db, max_age_minutes=30, no_progress_minutes=5)
    stmt = db.scalars.call_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    # SELECT elenca started_at come colonna; lo stale RUNNING non deve filtrare su età started_at.
    assert "started_at <" not in sql
    assert "updated_at" in sql
    assert "created_at" in sql


def test_job_to_dict_includes_progress():
    job = CecchinoTodayScanJob(
        job_id="abc",
        scan_date=date(2026, 6, 4),
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        progress_current=5,
        progress_total=10,
        current_step="fetching_odds",
    )
    d = job_to_dict(job)
    assert d["job_id"] == "abc"
    assert d["progress_current"] == 5
    assert d["current_step"] == "fetching_odds"


def test_emit_progress_calls_reporter():
    calls: list[dict] = []

    def reporter(**kwargs):
        calls.append(kwargs)

    _emit_progress(reporter, current_step="fetching_fixtures", progress_current=1, progress_total=10)
    assert calls[0]["current_step"] == "fetching_fixtures"


def test_run_scan_updates_progress_reporter():
    from datetime import timezone as tz

    db = MagicMock()
    db.commit = MagicMock()
    progress_calls: list[dict] = []

    def progress(**kwargs):
        progress_calls.append(kwargs)

    client_mock = MagicMock()
    client_mock.get_fixtures_by_date.return_value = []
    fixed_now = datetime(2026, 6, 4, 12, 0, tzinfo=tz.utc)
    with (
        patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=tz.utc),
        patch("app.services.cecchino.cecchino_today_service.datetime") as mock_dt,
        patch(
            "app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots",
            return_value={"deleted": 0},
        ),
    ):
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        report = run_scan(
            db,
            scan_date=date(2026, 6, 4),
            client=client_mock,
            progress=progress,
            metrics=ScanRunMetrics(started_at=0),
        )
    assert report["status"] == "ok"
    assert any(c.get("current_step") == "fetching_fixtures" for c in progress_calls)
    assert "result_summary" in report


def test_load_cached_odds_skips_api_when_snapshot_complete():
    db = MagicMock()
    row = MagicMock()
    row.odds_snapshot_json = {
        "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
        "raw_by_bookmaker_id": {
            "3": _mock_1x2_bets(3),
        },
    }
    db.scalar.return_value = row
    cached = load_cached_odds_for_fixture(db, scan_date=date(2026, 6, 4), provider_fixture_id=123)
    assert cached is not None
    assert 3 in cached


def test_fetch_fixture_odds_uses_cache_without_api():
    db = MagicMock()
    row = MagicMock()
    row.odds_snapshot_json = {
        "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
        "raw_by_bookmaker_id": {
            "3": _mock_1x2_bets(3),
        },
    }
    row.negative_cache_until = None
    db.scalar.return_value = row
    client = MagicMock()
    metrics = ScanRunMetrics()
    odds, _, strategy, _neg = fetch_fixture_odds_for_cecchino_bookmakers(
        client,
        123,
        db=db,
        scan_date=date(2026, 6, 4),
        force_rescan=False,
        metrics=metrics,
    )
    assert strategy == "cached"
    assert metrics.odds_from_cache == 1
    client.get_fixture_odds_by_fixture.assert_not_called()


def test_fetch_fixture_odds_force_rescan_calls_api():
    db = MagicMock()
    client = MagicMock()
    client.get_fixture_odds_by_fixture.return_value = [
        {
            "bookmakers": [
                {"id": 8, "bets": _mock_1x2_bets(8)[0]["bookmakers"][0]["bets"]},
                {"id": 3, "bets": _mock_1x2_bets(3)[0]["bookmakers"][0]["bets"]},
                {"id": 4, "bets": _mock_1x2_bets(4)[0]["bookmakers"][0]["bets"]},
            ],
        },
    ]
    client.get_fixture_odds.side_effect = lambda fid, bid: _mock_1x2_bets(bid)
    metrics = ScanRunMetrics()
    with patch("app.services.cecchino.cecchino_today_odds_fetch.time.sleep", lambda *_a, **_k: None):
        with patch(
            "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
            return_value=MagicMock(cecchino_odds_bookmaker_fallback=True),
        ):
            _, _, strategy, _neg = fetch_fixture_odds_for_cecchino_bookmakers(
                client,
                123,
                db=db,
                scan_date=date(2026, 6, 4),
                force_rescan=True,
                metrics=metrics,
            )
    assert "fixture_single_call" in strategy
    client.get_fixture_odds_by_fixture.assert_called_once()


def test_extract_odds_filters_bookmakers_canonical():
    raw = [
        {
            "bookmakers": [
                {"id": 8, "bets": []},
                {"id": 99, "bets": []},
                {"id": 3, "bets": []},
            ],
        },
    ]
    out = _extract_odds_by_book_from_response(raw)
    assert set(out.keys()) == {3, 8}
    assert 99 not in out


def test_fetch_fixture_odds_fallback_per_bookmaker():
    db = MagicMock()
    db.scalar.return_value = None
    client = MagicMock()
    client.get_fixture_odds_by_fixture.return_value = []
    client.get_fixture_odds.side_effect = lambda fid, bid: _mock_1x2_bets(bid)
    metrics = ScanRunMetrics()
    with patch("app.services.cecchino.cecchino_today_odds_fetch.time.sleep", lambda *_a, **_k: None):
        with patch(
            "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
            return_value=MagicMock(cecchino_odds_bookmaker_fallback=True),
        ):
            odds, _, strategy, _neg = fetch_fixture_odds_for_cecchino_bookmakers(
                client,
                456,
                db=db,
                scan_date=date(2026, 6, 4),
                force_rescan=True,
                metrics=metrics,
            )
    assert 3 in odds
    assert strategy in (
        "bookmaker_per_fixture",
        "fixture_single_call_with_bookmaker_fallback",
        "fixture_single_call_with_bet365_fallback",
    )
    assert client.get_fixture_odds.call_count >= 1


def test_scan_day_start_endpoint():
    with patch(
        "app.routes.cecchino_today.start_scan_job",
        return_value={
            "job_id": "test-job",
            "status": "queued",
            "scan_date": "2026-06-04",
            "message": "Scansione avviata",
        },
    ):
        resp = client.post(
            "/api/admin/cecchino/today/scan-day/start",
            json={"date": "2026-06-04", "timezone": "Europe/Rome", "force_rescan": False},
        )
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "test-job"


def test_scan_job_status_endpoint():
    job = CecchinoTodayScanJob(
        job_id="jid",
        scan_date=date(2026, 6, 4),
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_COMPLETED,
    )
    with patch("app.routes.cecchino_today.get_scan_job", return_value=job):
        with patch("app.routes.cecchino_today.recover_stale_scan_jobs"):
            resp = client.get("/api/admin/cecchino/today/scan-jobs/jid")
    assert resp.status_code == 200
    assert resp.json()["status"] == JOB_STATUS_COMPLETED


def test_scan_day_wrapper_returns_job_id():
    with patch(
        "app.routes.cecchino_today.start_scan_job",
        return_value={
            "job_id": "wrap-job",
            "status": "queued",
            "scan_date": "2026-06-04",
            "message": "Scansione avviata",
        },
    ):
        resp = client.post(
            "/api/admin/cecchino/today/scan-day",
            json={"date": "2026-06-04", "force_rescan": False},
        )
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "wrap-job"


def test_get_running_job_for_date_query():
    db = MagicMock()
    get_running_job_for_date(db, date(2026, 6, 4))
    db.scalar.assert_called_once()
