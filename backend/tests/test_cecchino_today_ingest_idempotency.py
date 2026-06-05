"""Test idempotenza ingest Cecchino Today — Fase 12."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import League
from app.models.cecchino_today_fixture import ELIGIBILITY_EXCLUDED_MAPPING, CecchinoTodayFixture
from app.services.cecchino.league_ingest_helpers import (
    get_or_create_league_by_api_id,
    recover_session_if_inactive,
)
from app.services.cecchino.cecchino_today_service import (
    _mapping_blocking_reasons,
    _upsert_today_snapshot,
    build_cecchino_today_report,
    run_scan,
)


def test_get_or_create_league_reuses_existing():
    db = MagicMock()
    existing = League(api_league_id=268, name="Old", country="Uruguay")
    existing.id = 10
    db.scalar.return_value = existing

    league = get_or_create_league_by_api_id(
        db,
        api_league_id=268,
        name="Primera División - Apertura",
        country="Uruguay",
        logo_url="https://example.com/logo.png",
        raw_json={"id": 268},
    )

    assert league is existing
    assert league.name == "Primera División - Apertura"
    db.add.assert_not_called()


def test_get_or_create_league_integrity_error_recovers_existing():
    db = MagicMock()
    existing = League(api_league_id=268, name="Existing", country="Uruguay")
    existing.id = 99

    call_count = {"n": 0}

    def scalar_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return None
        return existing

    db.scalar.side_effect = scalar_side_effect

    nested = MagicMock()
    db.begin_nested.return_value = nested
    db.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate key"))

    league = get_or_create_league_by_api_id(
        db,
        api_league_id=268,
        name="Primera División - Apertura",
        country="Uruguay",
    )

    assert league is existing
    nested.rollback.assert_called_once()


def test_ensure_competition_with_existing_league_no_crash():
    from app.services.cecchino.cecchino_today_bootstrap import ensure_competition_and_history

    db = MagicMock()
    league = League(api_league_id=268, name="Liga", country="Uruguay")
    league.id = 1

    with (
        patch(
            "app.services.cecchino.cecchino_today_bootstrap.get_or_create_league_by_api_id",
            return_value=league,
        ) as mock_league,
        patch("app.services.cecchino.cecchino_today_bootstrap.get_or_create_season") as mock_season,
        patch(
            "app.services.cecchino.cecchino_today_bootstrap.get_or_create_competition_for_league_season",
        ) as mock_comp,
        patch("app.services.cecchino.cecchino_today_bootstrap.ApiFootballClient") as mock_client_cls,
        patch("app.services.cecchino.cecchino_today_bootstrap.IngestionService") as mock_ingest_cls,
    ):
        season = MagicMock()
        season.id = 2
        mock_season.return_value = season
        comp = MagicMock()
        comp.id = 3
        comp.key = "cecchino_today_268_2025"
        mock_comp.return_value = (comp, False)

        client = MagicMock()
        client.get_teams.return_value = []
        client.get_fixtures.return_value = []
        mock_client_cls.return_value = client

        ingest = MagicMock()
        ingest._upsert_fixture_from_api_item.return_value = True
        mock_ingest_cls.return_value = ingest

        db.scalar.return_value = MagicMock(id=100)

        api_item = {
            "league": {"id": 268, "season": 2025, "name": "Primera", "country": "Uruguay"},
            "fixture": {"id": 999001},
        }
        comp_out, fx, warnings = ensure_competition_and_history(db, api_item=api_item)

    assert comp_out is comp
    mock_league.assert_called_once()
    assert fx is not None


def test_recover_session_if_inactive_rolls_back():
    db = MagicMock()
    db.is_active = False
    recover_session_if_inactive(db)
    db.rollback.assert_called_once()


def test_pending_rollback_avoided_after_handled_mapping_error():
    db = MagicMock()
    db.is_active = False
    exc = IntegrityError("insert", {}, Exception("uq_leagues_api_league_id"))
    recover_session_if_inactive(db)
    reasons = _mapping_blocking_reasons(exc)
    assert "league_upsert_error" in reasons
    assert "integrity_error" in reasons
    db.rollback.assert_called_once()


def test_upsert_today_snapshot_same_scan_date_updates_not_duplicates():
    db = MagicMock()
    existing = MagicMock(spec=CecchinoTodayFixture)
    db.scalar.return_value = existing

    api_item = {
        "fixture": {"id": 12345, "status": {"short": "NS"}, "date": "2026-06-04T20:00:00+00:00"},
        "league": {"id": 268, "season": 2025, "name": "Liga", "country": "UY"},
        "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
    }

    row1 = _upsert_today_snapshot(
        db,
        scan_date=date(2026, 6, 4),
        api_item=api_item,
        eligibility_status="eligible",
    )
    row2 = _upsert_today_snapshot(
        db,
        scan_date=date(2026, 6, 4),
        api_item=api_item,
        eligibility_status="excluded_mapping_error",
    )

    assert row1 is existing
    assert row2 is existing
    db.add.assert_not_called()


def test_scan_continues_after_mapping_error_on_one_fixture():
    items = [
        {
            "fixture": {"id": 1, "status": {"short": "NS"}, "date": "2026-06-04T18:00:00+00:00"},
            "league": {"id": 268, "season": 2025, "name": "Liga", "country": "UY"},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        },
        {
            "fixture": {"id": 2, "status": {"short": "NS"}, "date": "2026-06-04T20:00:00+00:00"},
            "league": {"id": 999, "season": 2025, "name": "Other", "country": "XX"},
            "teams": {"home": {"name": "C"}, "away": {"name": "D"}},
        },
    ]

    db = MagicMock()
    db.is_active = True
    db.begin_nested.return_value = MagicMock()
    db.scalar.return_value = None

    client = MagicMock()
    client.get_fixtures_by_date.return_value = items
    client.get_fixture_odds.return_value = []

    bootstrap_calls = {"n": 0}

    def bootstrap_side_effect(*args, **kwargs):
        bootstrap_calls["n"] += 1
        if bootstrap_calls["n"] == 1:
            raise IntegrityError("insert", {}, Exception("uq_leagues_api_league_id"))
        return None, None, []

    with (
        patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=__import__("datetime").timezone.utc),
        patch("app.services.cecchino.cecchino_today_service.is_cecchino_allowed_competition", return_value=(True, None)),
        patch("app.services.cecchino.cecchino_today_service.is_fixture_not_started", return_value=True),
        patch(
            "app.services.cecchino.cecchino_today_service.verify_complete_1x2_odds",
            return_value=(True, {"bookmakers": {}}, None),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.ensure_competition_and_history",
            side_effect=bootstrap_side_effect,
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots",
            return_value={"deleted": 0},
        ),
        patch("app.services.cecchino.cecchino_today_service._upsert_today_snapshot") as mock_upsert,
    ):
        report = run_scan(db, scan_date=date(2026, 6, 4), client=client)

    assert report["status"] == "ok"
    assert mock_upsert.call_count >= 2
    mapping_calls = [
        c for c in mock_upsert.call_args_list
        if c.kwargs.get("eligibility_status") == ELIGIBILITY_EXCLUDED_MAPPING
    ]
    assert len(mapping_calls) >= 1


def test_build_report_includes_errors_and_excluded_summary():
    report = build_cecchino_today_report(
        scan_date=date(2026, 6, 4),
        total=5,
        by_status={"eligible": 2, ELIGIBILITY_EXCLUDED_MAPPING: 1},
        warnings=[],
        errors=[],
    )
    assert report["errors"] == []
    assert report["excluded_summary"][ELIGIBILITY_EXCLUDED_MAPPING] == 1
