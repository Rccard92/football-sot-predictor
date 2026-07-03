"""Test helper datetime e robustezza PIT Cecchino."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models.cecchino_today_fixture import ELIGIBILITY_ERROR
from app.services.cecchino.cecchino_datetime import (
    ensure_datetime,
    ensure_datetime_utc,
    fixture_key_before_safe,
    safe_isoformat,
    utc_now,
)
from app.services.cecchino.cecchino_fixture_history import audit_leakage, build_fixture_contexts
from app.services.cecchino.cecchino_today_final_eligibility import build_kpi_debug
from app.services.cecchino.cecchino_today_service import _parse_kickoff
from app.services.ingestion_service import _parse_dt
from app.services.predictions_v10.v10_prior_context import _prior_fixtures_for_team

UTC = timezone.utc


def test_ensure_datetime_utc_aware_returns_utc():
    src = datetime(2026, 7, 4, 18, 0, tzinfo=timezone(timedelta(hours=2)))
    out = ensure_datetime_utc(src)
    assert out is not None
    assert out.tzinfo == UTC
    assert out.hour == 16


def test_ensure_datetime_utc_naive_assumes_utc():
    src = datetime(2026, 7, 4, 18, 0)
    out = ensure_datetime_utc(src)
    assert out == datetime(2026, 7, 4, 18, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "raw,expected_hour",
    [
        ("2026-07-04T18:00:00Z", 18),
        ("2026-07-04T18:00:00+00:00", 18),
        ("2026-07-04T18:00:00", 18),
    ],
)
def test_ensure_datetime_utc_iso_strings(raw: str, expected_hour: int):
    out = ensure_datetime_utc(raw)
    assert out is not None
    assert out.tzinfo == UTC
    assert out.hour == expected_hour


def test_ensure_datetime_utc_none_returns_none():
    assert ensure_datetime_utc(None) is None


def test_ensure_datetime_utc_bad_date_returns_none():
    assert ensure_datetime_utc("bad-date") is None


def test_ensure_datetime_alias():
    assert ensure_datetime("2026-07-04T18:00:00Z") == ensure_datetime_utc("2026-07-04T18:00:00Z")


def test_safe_isoformat():
    assert safe_isoformat("2026-07-04T18:00:00Z") == "2026-07-04T18:00:00+00:00"


def test_utc_now_is_aware():
    now = utc_now()
    assert now.tzinfo == UTC


def _fx(fid: int, kickoff, *, home: int = 10, away: int = 20) -> SimpleNamespace:
    return SimpleNamespace(
        id=fid,
        api_fixture_id=fid + 10000,
        kickoff_at=kickoff,
        home_team_id=home,
        away_team_id=away,
        competition_id=1,
        status="FT",
        goals_home=1,
        goals_away=0,
        season_id=10,
    )


def test_prior_fixtures_for_team_string_kickoff_no_crash():
    db = MagicMock()
    prior = _fx(1, "2026-06-01T15:00:00+00:00", home=10, away=99)
    target_ko = "2026-07-04T20:00:00Z"
    db.scalars.return_value.all.return_value = [prior]

    out = _prior_fixtures_for_team(
        db,
        season_id=10,
        cutoff_kickoff=target_ko,
        cutoff_fixture_id=100,
        team_id=10,
        competition_id=1,
        competition_scoped_only=True,
    )
    assert len(out) == 1


def test_prior_fixtures_for_team_string_cutoff_no_crash():
    db = MagicMock()
    prior = _fx(1, datetime(2026, 6, 1, 15, 0, tzinfo=UTC), home=10, away=99)
    db.scalars.return_value.all.return_value = [prior]

    out = _prior_fixtures_for_team(
        db,
        season_id=10,
        cutoff_kickoff="2026-07-04T20:00:00Z",
        cutoff_fixture_id=100,
        team_id=10,
        competition_id=1,
        competition_scoped_only=True,
    )
    assert len(out) == 1


def test_audit_leakage_string_kickoff_no_crash():
    target = _fx(100, "2026-07-04T20:00:00Z", home=10, away=20)
    prior = _fx(1, "2026-06-01T15:00:00+00:00", home=10, away=99)
    check, reasons = audit_leakage([prior], target)
    assert check["status"] in ("passed", "failed", "undefined")
    assert isinstance(reasons, list)


def test_build_fixture_contexts_string_kickoff_no_crash():
    db = MagicMock()
    target = _fx(100, "2026-07-04T20:00:00Z", home=10, away=20)

    with patch(
        "app.services.cecchino.cecchino_fixture_history._resolve_fixture_season_id",
        return_value=10,
    ), patch(
        "app.services.cecchino.cecchino_fixture_history._prior_fixtures_for_team",
        return_value=[],
    ):
        ctx = build_fixture_contexts(db, target)
    assert ctx.home_total.sample_count == 0


def test_build_current_season_team_xg_profile_string_kickoff_no_crash():
    from app.services.cecchino.cecchino_current_season_xg import build_current_season_team_xg_profile

    db = MagicMock()
    target = _fx(100, "2026-07-04T20:00:00Z", home=10, away=20)
    comp = MagicMock()
    comp.season = 2026
    comp.provider_league_id = 999
    comp.league_id = 5
    db.get.return_value = comp
    db.scalar.side_effect = [comp, MagicMock(id=5), MagicMock(id=99)]

    with patch(
        "app.services.cecchino.cecchino_current_season_xg.load_finished_fixtures_for_team",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg._resolve_season_league_ids",
        return_value=(2026, 5, 999),
    ):
        profile = build_current_season_team_xg_profile(db, target, 10)
    assert profile["sample_size"] == 0
    assert profile["anti_leakage"]["fixture_date_cutoff"] is not None


def test_parse_kickoff_api_item_iso_string():
    item = {"fixture": {"date": "2026-07-04T18:00:00Z"}}
    ko = _parse_kickoff(item)
    assert ko is not None
    assert ko.tzinfo == UTC


def test_ingestion_parse_dt_iso_string():
    dt = _parse_dt("2026-07-04T18:00:00Z")
    assert dt.tzinfo == UTC


def test_run_scan_bookmaker_fail_does_not_raise_str_utc():
    from app.services.cecchino.cecchino_today_service import run_scan

    db = MagicMock()
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []
    db.commit = MagicMock()

    api_item = {
        "fixture": {"id": 999001, "date": "2026-07-04T18:00:00Z", "status": {"short": "NS"}},
        "league": {"id": 256, "name": "US League Two", "season": 2026, "country": "USA"},
        "teams": {"home": {"id": 1, "name": "Inter Gainesville"}, "away": {"id": 2, "name": "Nona"}},
    }
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [api_item]
    client.set_usage_db = MagicMock()
    client.set_usage_context = MagicMock()

    with patch(
        "app.services.cecchino.cecchino_today_service.is_cecchino_allowed_competition",
        return_value=(True, None),
    ), patch(
        "app.services.cecchino.cecchino_today_service.is_fixture_not_started",
        return_value=True,
    ), patch(
        "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers",
        return_value=({}, [], "live", False),
    ), patch(
        "app.services.cecchino.cecchino_today_service.verify_complete_1x2_odds",
        return_value=(False, {}, "missing_betfair", ["missing_betfair"]),
    ), patch(
        "app.services.cecchino.cecchino_today_service.write_negative_odds_cache",
    ), patch(
        "app.services.cecchino.cecchino_today_service.check_api_budget_during_scan",
    ), patch(
        "app.services.cecchino.cecchino_today_service.sync_signals_for_scan_date",
        return_value={"fixtures": 0, "created": 0, "updated": 0, "deactivated": 0, "skipped": 0},
    ), patch(
        "app.services.cecchino.cecchino_today_service.get_api_usage_summary",
        return_value={},
    ):
        report = run_scan(
            db,
            scan_date=date(2026, 7, 4),
            timezone="Europe/Rome",
            client=client,
        )

    assert report["status"] == "ok"
    assert not any("has no attribute 'utc'" in str(e) for e in report.get("errors", []))


def test_kpi_debug_skipped_on_datetime_error():
    dbg = build_kpi_debug(
        None,
        eligibility_status=ELIGIBILITY_ERROR,
        eligibility_reason="'str' object has no attribute 'utc'",
        blocking_reasons=["datetime_normalization_error"],
    )
    assert dbg["kpi_status"] == "skipped_due_to_datetime_error"
    assert "kpi_panel_missing" not in dbg.get("missing_rows", [])


def test_fixture_key_before_safe_string_inputs():
    cutoff = "2026-07-04T20:00:00Z"
    prior = "2026-06-01T15:00:00+00:00"
    assert fixture_key_before_safe(prior, 1, cutoff, 100) is True
    assert fixture_key_before_safe("2026-07-05T15:00:00+00:00", 1, cutoff, 100) is False


def test_ensure_datetime_utc_date_only():
    out = ensure_datetime_utc(date(2026, 7, 4))
    assert out == datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
