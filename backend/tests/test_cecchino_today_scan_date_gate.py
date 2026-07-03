"""Test gate locale scan_date vs kickoff Cecchino Today."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_fixture import ELIGIBILITY_DISCOVERED, ELIGIBILITY_EXCLUDED_CUP
from app.services.cecchino.cecchino_today_fixture_filter import (
    fixture_belongs_to_scan_date,
    get_fixture_local_date,
)
from app.services.cecchino.cecchino_today_service import list_excluded_today_enriched, run_scan

SCAN_DATE = date(2026, 7, 4)
TZ = "Europe/Rome"


def _item(
    api_fid: int,
    kickoff: str,
    *,
    home: str = "Home",
    away: str = "Away",
) -> dict:
    return {
        "fixture": {"id": api_fid, "date": kickoff, "status": {"short": "NS"}},
        "league": {"id": 135, "name": "Serie A", "country": "Italy", "season": 2025, "type": "League"},
        "teams": {"home": {"name": home}, "away": {"name": away}},
    }


def test_local_date_same_scan_day():
    item = _item(1, "2026-07-04T18:00:00+00:00")
    belongs, debug = fixture_belongs_to_scan_date(item, SCAN_DATE, TZ)
    assert belongs is True
    assert debug["reason"] == "same_local_date"
    assert debug["fixture_local_date"] == "2026-07-04"
    assert get_fixture_local_date(item, TZ) == SCAN_DATE


def test_local_date_next_day_not_belongs():
    item = _item(2, "2026-07-05T18:00:00+00:00")
    belongs, debug = fixture_belongs_to_scan_date(item, SCAN_DATE, TZ)
    assert belongs is False
    assert debug["reason"] == "fixture_out_of_scan_date"
    assert debug["fixture_local_date"] == "2026-07-05"


def test_local_date_parses_z_suffix():
    item = _item(3, "2026-07-04T18:00:00Z")
    belongs, debug = fixture_belongs_to_scan_date(item, SCAN_DATE, TZ)
    assert belongs is True
    assert debug["reason"] == "same_local_date"


def test_unparseable_kickoff():
    item = _item(4, "not-a-date")
    belongs, debug = fixture_belongs_to_scan_date(item, SCAN_DATE, TZ)
    assert belongs is False
    assert debug["reason"] == "fixture_kickoff_unparseable"
    assert debug["fixture_local_date"] is None
    assert debug["fixture_utc"] is None


def test_naive_datetime_treated_as_utc():
    item = {
        "fixture": {"id": 5, "date": datetime(2026, 7, 4, 18, 0), "status": {"short": "NS"}},
        "league": {"id": 1, "name": "L", "country": "X", "season": 2025, "type": "League"},
        "teams": {"home": {"name": "H"}, "away": {"name": "A"}},
    }
    belongs, debug = fixture_belongs_to_scan_date(item, SCAN_DATE, TZ)
    assert belongs is True
    assert debug["reason"] == "same_local_date"


@contextmanager
def _run_scan_patches(*, upsert_side_effect=None):
    upsert_side_effect = upsert_side_effect or (lambda *_a, **_kw: MagicMock())
    with (
        patch("app.services.cecchino.cecchino_today_service._upsert_today_snapshot", side_effect=upsert_side_effect),
        patch("app.services.cecchino.cecchino_today_service.get_api_usage_summary", return_value={"total_calls": 1}),
        patch("app.services.cecchino.cecchino_today_service.sync_signals_for_scan_date", return_value={}),
        patch(
            "app.services.cecchino.cecchino_today_service.is_cecchino_allowed_competition",
            return_value=(False, ELIGIBILITY_EXCLUDED_CUP),
        ),
        patch("app.services.cecchino.cecchino_today_service.check_api_budget_during_scan"),
        patch("app.services.cecchino.cecchino_today_service.is_fixture_not_started", return_value=True),
        patch(
            "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers",
        ) as odds_fetch,
        patch(
            "app.services.cecchino.cecchino_today_service.ensure_competition_and_history",
        ) as bootstrap,
    ):
        yield odds_fetch, bootstrap


def test_run_scan_partitions_out_of_scan_date():
    db = MagicMock()
    db.commit = MagicMock()
    db.scalar = MagicMock(return_value=None)
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [
        _item(101, "2026-07-04T18:00:00+00:00", home="InScope", away="TeamA"),
        _item(102, "2026-07-05T18:00:00+00:00", home="Defensores Unidos", away="Argentino de Merlo"),
        _item(103, "2026-07-03T18:00:00+00:00", home="PrevDay", away="TeamC"),
    ]
    upserted_ids: list[int] = []

    def _track_upsert(_db, *, scan_date, api_item, **kwargs):
        upserted_ids.append(int((api_item.get("fixture") or {}).get("id") or 0))
        return MagicMock()

    with _run_scan_patches(upsert_side_effect=_track_upsert) as (odds_fetch, bootstrap):
        report = run_scan(
            db,
            scan_date=SCAN_DATE,
            timezone=TZ,
            client=client,
            force_rescan=True,
        )

    assert report["provider_items_received"] == 3
    assert report["provider_out_of_scan_date_skipped"] == 2
    assert report["fixtures_in_scan_date"] == 1
    assert report["fixtures_found"] == 1
    assert upserted_ids == [101, 101]
    odds_fetch.assert_not_called()
    bootstrap.assert_not_called()
    assert len(report.get("out_of_scan_date_examples") or []) >= 1


def test_out_of_scan_date_not_in_excluded_list():
    db = MagicMock()
    db.commit = MagicMock()
    db.scalar = MagicMock(return_value=None)
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [
        _item(201, "2026-07-04T18:00:00+00:00"),
        _item(202, "2026-07-05T18:00:00+00:00"),
    ]

    stored_rows: list[MagicMock] = []

    def _track_upsert(_db, *, scan_date, api_item, eligibility_status, **kwargs):
        row = MagicMock()
        row.id = len(stored_rows) + 1
        row.provider_fixture_id = int((api_item.get("fixture") or {}).get("id") or 0)
        row.scan_date = scan_date
        row.eligibility_status = eligibility_status
        row.eligibility_reason = kwargs.get("eligibility_reason")
        row.kickoff = datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc)
        row.home_team_name = (api_item.get("teams") or {}).get("home", {}).get("name", "")
        row.away_team_name = (api_item.get("teams") or {}).get("away", {}).get("name", "")
        row.league_name = "Serie A"
        row.country_name = "Italy"
        row.blocking_reasons_json = []
        row.odds_snapshot_json = {}
        row.stats_snapshot_json = {}
        row.cecchino_output_json = {}
        row.kpi_panel_json = {}
        row.warnings_json = []
        row.bookmaker_status = "missing"
        row.stats_status = "insufficient"
        row.fixture_status = "NS"
        row.raw_fixture_json = api_item
        stored_rows.append(row)
        return row

    def _scalars_query(*_a, **_kw):
        result = MagicMock()
        excluded = [r for r in stored_rows if r.eligibility_status != "eligible"]
        result.all.return_value = excluded
        return result

    db.scalars.side_effect = _scalars_query

    with _run_scan_patches(upsert_side_effect=_track_upsert):
        run_scan(db, scan_date=SCAN_DATE, timezone=TZ, client=client, force_rescan=True)

    payload = list_excluded_today_enriched(db, scan_date=SCAN_DATE, timezone=TZ)
    provider_ids = {f["provider_fixture_id"] for f in payload["fixtures"]}
    assert 201 in provider_ids or payload["total"] <= 1
    assert 202 not in provider_ids


def test_next_day_scan_processes_out_of_date_fixture():
    db = MagicMock()
    db.commit = MagicMock()
    db.scalar = MagicMock(return_value=None)
    client = MagicMock()
    fixture_b = _item(302, "2026-07-05T18:00:00+00:00", home="Defensores Unidos", away="Argentino de Merlo")
    upserted_by_scan: dict[date, list[int]] = {}

    def _track_upsert(_db, *, scan_date, api_item, **kwargs):
        upserted_by_scan.setdefault(scan_date, []).append(
            int((api_item.get("fixture") or {}).get("id") or 0),
        )
        return MagicMock()

    with _run_scan_patches(upsert_side_effect=_track_upsert):
        client.get_fixtures_by_date.return_value = [
            _item(301, "2026-07-04T18:00:00+00:00"),
            fixture_b,
        ]
        report_wrong_day = run_scan(db, scan_date=SCAN_DATE, timezone=TZ, client=client, force_rescan=True)
        assert 302 not in upserted_by_scan.get(SCAN_DATE, [])

        client.get_fixtures_by_date.return_value = [fixture_b]
        report_right_day = run_scan(
            db,
            scan_date=date(2026, 7, 5),
            timezone=TZ,
            client=client,
            force_rescan=True,
        )

    assert report_wrong_day["provider_out_of_scan_date_skipped"] == 1
    assert report_right_day["fixtures_in_scan_date"] == 1
    assert 302 in upserted_by_scan.get(date(2026, 7, 5), [])
