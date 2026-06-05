"""Test persistenza Cecchino Today — giornate, cleanup, diagnostica."""

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
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_today_service import (
    build_cecchino_today_report,
    build_bookmaker_debug,
    cleanup_cecchino_today_snapshots,
    debug_search,
    list_available_days,
    list_eligible_today,
    list_excluded_today_enriched,
    rome_today,
    rome_tomorrow,
    run_scan,
    run_scan_today,
    run_scan_tomorrow,
)


def _make_row(
    *,
    row_id: int = 1,
    scan_date: date,
    status: str,
    home: str = "Home",
    away: str = "Away",
    league: str = "Serie A",
) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    row.id = row_id
    row.scan_date = scan_date
    row.eligibility_status = status
    row.eligibility_reason = status
    row.home_team_name = home
    row.away_team_name = away
    row.league_name = league
    row.country_name = "Italy"
    row.provider_fixture_id = row_id
    row.local_fixture_id = None
    row.competition_id = None
    row.kickoff = datetime(2026, 6, 4, 20, 0, tzinfo=timezone.utc)
    row.bookmaker_status = "missing"
    row.stats_status = "insufficient"
    row.cecchino_status = None
    row.odds_snapshot_json = {"bookmakers": {}, "missing": ["Bet365"]}
    row.stats_snapshot_json = {}
    row.warnings_json = []
    row.blocking_reasons_json = []
    row.kpi_panel_json = {}
    row.cecchino_output_json = {}
    row.match_display_status = "upcoming"
    row.fixture_status = "NS"
    row.country_flag_url = None
    row.league_logo_url = None
    row.home_team_logo_url = None
    row.away_team_logo_url = None
    row.goals_home = None
    row.goals_away = None
    row.score_fulltime_home = None
    row.score_fulltime_away = None
    row.elapsed_minutes = None
    row.raw_fixture_json = {}
    return row


def test_rome_today_and_tomorrow():
    fixed = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)
    rome_tz = timezone.utc
    with (
        patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=rome_tz),
        patch("app.services.cecchino.cecchino_today_service.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = fixed
        assert rome_today("Europe/Rome") == date(2026, 6, 4)
        assert rome_tomorrow("Europe/Rome") == date(2026, 6, 5)


def test_run_scan_today_and_tomorrow_delegate_dates():
    db = MagicMock()
    today = date(2026, 6, 4)
    tomorrow = date(2026, 6, 5)
    with (
        patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=today),
        patch("app.services.cecchino.cecchino_today_service.rome_tomorrow", return_value=tomorrow),
        patch("app.services.cecchino.cecchino_today_service.run_scan") as mock_run,
    ):
        mock_run.return_value = {"status": "ok"}
        run_scan_today(db)
        run_scan_tomorrow(db)
    assert mock_run.call_args_list[0].kwargs["scan_date"] == today
    assert mock_run.call_args_list[1].kwargs["scan_date"] == tomorrow


def test_scan_tomorrow_does_not_touch_today_rows():
    """run_scan upserta solo per scan_date passata — oggi resta intatto."""
    db = MagicMock()
    db.scalar.return_value = None
    db.commit = MagicMock()
    db.flush = MagicMock()
    upsert_dates: list[date] = []

    def capture_upsert(*_args, **kwargs):
        upsert_dates.append(kwargs["scan_date"])
        return MagicMock()

    client_mock = MagicMock()
    client_mock.get_fixtures_by_date.return_value = [
        {
            "league": {"name": "Coppa Italia", "country": "Italy", "type": "Cup", "season": 2025, "id": 1},
            "fixture": {"id": 200, "date": "2026-06-05T20:00:00+00:00", "status": {"short": "NS"}},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        },
    ]

    today = date(2026, 6, 4)
    tomorrow = date(2026, 6, 5)
    with (
        patch("app.services.cecchino.cecchino_today_service._upsert_today_snapshot", side_effect=capture_upsert),
        patch(
            "app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots",
            return_value={"deleted": 0},
        ),
        patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=timezone.utc),
    ):
        run_scan(db, scan_date=tomorrow, client=client_mock)

    assert all(d == tomorrow for d in upsert_dates)
    assert today not in upsert_dates


def test_list_available_days_includes_timeline_window():
    db = MagicMock()
    with (
        patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 4)),
        patch("app.services.cecchino.cecchino_today_service.rome_tomorrow", return_value=date(2026, 6, 5)),
        patch("app.services.cecchino.cecchino_today_service._aggregate_scan_dates", return_value={}),
    ):
        payload = list_available_days(db)
    dates = [d["date"] for d in payload["days"]]
    assert len(dates) == 15
    assert "2026-06-04" in dates
    assert "2026-06-05" in dates
    assert payload["selected_default"] == "2026-06-04"


def test_cleanup_does_not_touch_today_tomorrow_future():
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.rowcount = 3
    db.execute.return_value = mock_result

    with patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 4)):
        result = cleanup_cecchino_today_snapshots(db, retention_days=7, commit=True)

    assert result["deleted"] == 3
    assert result["cutoff_date"] == "2026-05-28"
    assert result["protected_from"] == "2026-06-04"
    db.execute.assert_called_once()


def test_list_eligible_today_filters_scan_date_and_eligible():
    db = MagicMock()
    eligible_row = _make_row(row_id=10, scan_date=date(2026, 6, 4), status=ELIGIBILITY_ELIGIBLE)
    db.scalars.return_value.all.return_value = [eligible_row]

    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={"has_scan": True, "day_status": "available", "eligible_count": 1, "excluded_count": 0},
    ):
        payload = list_eligible_today(db, scan_date=date(2026, 6, 4))

    assert payload["total"] == 1
    assert payload["scan_date"] == "2026-06-04"
    assert payload["scan_meta"]["day_status"] == "available"


def test_list_excluded_today_enriched_includes_debug_blocks():
    db = MagicMock()
    row = _make_row(row_id=2, scan_date=date(2026, 6, 4), status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER)
    db.scalars.return_value.all.return_value = [row]

    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={"has_scan": True, "day_status": "available", "eligible_count": 0, "excluded_count": 1},
    ):
        payload = list_excluded_today_enriched(db, scan_date=date(2026, 6, 4))

    fx = payload["fixtures"][0]
    assert "bookmaker_debug" in fx
    assert "stats_debug" in fx
    assert "competition_filter_debug" in fx
    assert fx["bookmaker_debug"]["Bet365"] == "missing"


def test_debug_search_finds_excluded_with_reason():
    db = MagicMock()
    row = _make_row(
        row_id=3,
        scan_date=date(2026, 6, 4),
        status=ELIGIBILITY_EXCLUDED_CUP,
        home="Juventus",
        away="Milan",
    )
    db.scalars.return_value.all.return_value = [row]

    payload = debug_search(db, scan_date=date(2026, 6, 4), q="Juventus")
    assert payload["results"][0]["match_type"] == "excluded"
    assert "excluded_cup" in payload["results"][0]["message"]


def test_report_contains_top_exclusion_reasons():
    report = build_cecchino_today_report(
        scan_date=date(2026, 6, 4),
        total=10,
        by_status={
            ELIGIBILITY_ELIGIBLE: 2,
            ELIGIBILITY_EXCLUDED_CUP: 5,
            ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER: 3,
        },
        warnings=[],
    )
    assert report["fixtures_found"] == 10
    assert len(report["top_exclusion_reasons"]) == 2
    assert report["top_exclusion_reasons"][0]["status"] == ELIGIBILITY_EXCLUDED_CUP
    assert report["top_exclusion_reasons"][0]["count"] == 5


def test_build_bookmaker_debug_available():
    row = _make_row(scan_date=date(2026, 6, 4), status=ELIGIBILITY_ELIGIBLE)
    row.odds_snapshot_json = {
        "bookmakers": {
            "Bet365": {"HOME": 2.0, "DRAW": 3.0, "AWAY": 4.0},
            "Betfair": {"HOME": 2.1, "DRAW": 3.1, "AWAY": 4.1},
            "Pinnacle": {"HOME": 2.2, "DRAW": 3.2, "AWAY": 4.2},
        },
    }
    dbg = build_bookmaker_debug(row)
    assert dbg["Bet365"] == "available"
    assert dbg["Pinnacle"] == "available"
