"""Test Cecchino Today Fase 9 — timeline, scan-day, update-results, filtri API."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_EXCLUDED_CUP,
    ELIGIBILITY_EXCLUDED_STARTED,
    MATCH_FINISHED,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_today_constants import TIMELINE_WINDOW_DAYS
from app.services.cecchino.cecchino_today_service import (
    build_exclusion_reason_message,
    build_fixture_status_debug,
    cleanup_cecchino_today_snapshots,
    debug_search,
    list_available_days,
    list_eligible_today,
    list_excluded_today_enriched,
    run_scan_day,
    update_today_fixture_results,
)

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _eligible_row(**kwargs) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    row.id = kwargs.get("row_id", 1)
    row.scan_date = kwargs.get("scan_date", date(2026, 6, 4))
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    row.provider_fixture_id = kwargs.get("provider_fixture_id", 100)
    row.local_fixture_id = None
    row.competition_id = None
    row.home_team_name = kwargs.get("home", "Juventus")
    row.away_team_name = kwargs.get("away", "Inter")
    row.league_name = kwargs.get("league", "Serie A")
    row.country_name = kwargs.get("country", "Italy")
    row.kickoff = datetime(2026, 6, 4, 20, 0, tzinfo=timezone.utc)
    row.home_team_logo_url = kwargs.get("home_logo", "https://media/logo-home.png")
    row.away_team_logo_url = kwargs.get("away_logo", "https://media/logo-away.png")
    row.country_flag_url = kwargs.get("flag", "https://media/flag.png")
    row.league_logo_url = kwargs.get("league_logo", "https://media/league.png")
    row.match_display_status = kwargs.get("match_display_status", MATCH_UPCOMING)
    row.fixture_status = kwargs.get("fixture_status", "NS")
    row.elapsed_minutes = None
    row.goals_home = kwargs.get("goals_home")
    row.goals_away = kwargs.get("goals_away")
    row.score_fulltime_home = kwargs.get("score_fulltime_home")
    row.score_fulltime_away = kwargs.get("score_fulltime_away")
    row.kpi_panel_json = {"rows": []}
    row.cecchino_output_json = {"signals_matrix": {}}
    row.odds_snapshot_json = {}
    row.stats_snapshot_json = {}
    row.warnings_json = []
    row.raw_fixture_json = kwargs.get("raw_fixture_json", {})
    row.eligibility_reason = None
    row.bookmaker_status = "ok"
    row.stats_status = "ok"
    row.cecchino_status = "ok"
    return row


def test_days_endpoint_includes_plus_minus_7():
    db = MagicMock()
    with (
        patch("app.routes.cecchino_today.list_available_days") as mock_days,
    ):
        mock_days.return_value = {
            "status": "ok",
            "today": "2026-06-04",
            "selected_default": "2026-06-04",
            "days": [{"date": "2026-06-04", "is_today": True, "eligible_count": 3}],
        }
        resp = client.get("/api/cecchino/today/days")
    assert resp.status_code == 200


def test_list_available_days_window_and_is_today():
    db = MagicMock()
    today = date(2026, 6, 4)
    agg = {
        today: {
            "eligible_count": 11,
            "excluded_count": 80,
            "upcoming_count": 3,
            "live_count": 0,
            "finished_count": 8,
            "last_scan_at": "2026-06-04T10:00:00+00:00",
            "has_scan": True,
        },
    }
    with (
        patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=today),
        patch("app.services.cecchino.cecchino_today_service.rome_tomorrow", return_value=date(2026, 6, 5)),
        patch("app.services.cecchino.cecchino_today_service._aggregate_scan_dates", return_value=agg),
    ):
        payload = list_available_days(db)
    assert len(payload["days"]) == TIMELINE_WINDOW_DAYS * 2 + 1
    today_entry = next(d for d in payload["days"] if d["date"] == "2026-06-04")
    assert today_entry["is_today"] is True
    assert today_entry["eligible_count"] == 11
    assert payload["selected_default"] == "2026-06-04"


def test_scan_day_skips_when_already_scanned():
    db = MagicMock()
    with (
        patch(
            "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
            return_value={"has_scan": True, "is_scanned": True},
        ),
        patch("app.services.cecchino.cecchino_today_service.run_scan") as mock_run,
    ):
        result = run_scan_day(db, scan_date=date(2026, 6, 4), force_rescan=False)
    assert result["status"] == "already_scanned"
    mock_run.assert_not_called()


def test_scan_day_force_rescan_calls_run_scan():
    db = MagicMock()
    meta_after = {"has_scan": True, "eligible_count": 1, "is_scanned": True}
    with (
        patch(
            "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
            side_effect=[{"has_scan": True}, meta_after],
        ),
        patch("app.services.cecchino.cecchino_today_service.run_scan", return_value={"status": "ok"}) as mock_run,
    ):
        result = run_scan_day(db, scan_date=date(2026, 6, 4), force_rescan=True)
    assert result["status"] == "ok"
    mock_run.assert_called_once()


def test_update_results_updates_score():
    db = MagicMock()
    row = _eligible_row(
        match_display_status=MATCH_UPCOMING,
        provider_fixture_id=555,
    )
    db.scalars.return_value.all.return_value = [row]
    db.commit = MagicMock()

    api_item = {
        "fixture": {"id": 555, "status": {"short": "FT", "elapsed": 90}},
        "goals": {"home": 2, "away": 1},
        "score": {"fulltime": {"home": 2, "away": 1}},
        "league": {"flag": "https://f.png", "logo": "https://l.png", "country": "Italy", "name": "Serie A"},
        "teams": {"home": {"logo": "https://h.png"}, "away": {"logo": "https://a.png"}},
    }
    client_mock = MagicMock()
    client_mock.get_fixture_by_id.return_value = api_item

    with patch("app.services.cecchino.cecchino_today_service.time.sleep"):
        result = update_today_fixture_results(
            db,
            scan_date=date(2026, 6, 4),
            client=client_mock,
        )
    assert result["results_updated"] == 1
    assert row.match_display_status == MATCH_FINISHED
    assert row.score_fulltime_home == 2


def test_list_eligible_includes_finished_and_logos():
    db = MagicMock()
    row = _eligible_row(match_display_status=MATCH_FINISHED, goals_home=2, goals_away=1)
    db.scalars.return_value.all.return_value = [row]
    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={
            "has_scan": True,
            "is_scanned": True,
            "eligible_count": 1,
            "excluded_count": 0,
            "upcoming_count": 0,
            "live_count": 0,
            "finished_count": 1,
            "last_scan_at": None,
            "day_status": "available",
        },
    ):
        payload = list_eligible_today(db, scan_date=date(2026, 6, 4))
    assert payload["summary"]["finished_count"] == 1
    fx = payload["countries"][0]["leagues"][0]["fixtures"][0]
    assert fx["status"] == MATCH_FINISHED
    assert fx["home_team_logo_url"] == "https://media/logo-home.png"
    assert fx["score"]["available"] is True
    assert "bookmakers" not in fx


def test_excluded_debug_includes_fixture_status_and_reason():
    row = _eligible_row()
    row.eligibility_status = ELIGIBILITY_EXCLUDED_STARTED
    row.eligibility_reason = "fixture_already_started_or_finished"
    row.raw_fixture_json = {"fixture": {"status": {"short": "1H", "elapsed": 30}}}
    dbg = build_fixture_status_debug(row)
    assert dbg["fixture_status_at_scan"] == "NS" or dbg["fixture_status_at_scan"] == "1H"
    msg = build_exclusion_reason_message(row)
    assert msg is not None


def test_debug_search_finds_excluded():
    db = MagicMock()
    row = _eligible_row()
    row.eligibility_status = ELIGIBILITY_EXCLUDED_CUP
    row.home_team_name = "Roma"
    db.scalars.return_value.all.return_value = [row]
    payload = debug_search(db, scan_date=date(2026, 6, 4), q="Roma")
    assert payload["results"][0]["match_type"] == "excluded"


def test_cleanup_does_not_touch_today():
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.rowcount = 2
    db.execute.return_value = mock_result
    with patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 4)):
        result = cleanup_cecchino_today_snapshots(db, retention_days=7, commit=True)
    assert result["protected_from"] == "2026-06-04"


def test_scan_day_endpoint():
    with patch("app.routes.cecchino_today.run_scan_day", return_value={"status": "ok"}) as mock_run:
        resp = client.post(
            "/api/admin/cecchino/today/scan-day",
            json={"date": "2026-06-04", "force_rescan": False},
        )
    assert resp.status_code == 200
    mock_run.assert_called_once()


def test_update_results_endpoint():
    with patch(
        "app.routes.cecchino_today.update_today_fixture_results",
        return_value={"status": "ok", "results_updated": 5},
    ):
        resp = client.post(
            "/api/admin/cecchino/today/update-results",
            json={"date": "2026-06-04"},
        )
    assert resp.status_code == 200
    assert resp.json()["results_updated"] == 5


def test_list_excluded_enriched_has_fixture_status_debug():
    db = MagicMock()
    row = _eligible_row()
    row.eligibility_status = ELIGIBILITY_EXCLUDED_CUP
    db.scalars.return_value.all.return_value = [row]
    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={"has_scan": True, "eligible_count": 0, "excluded_count": 1},
    ):
        payload = list_excluded_today_enriched(db, scan_date=date(2026, 6, 4))
    assert "fixture_status_debug" in payload["fixtures"][0]
