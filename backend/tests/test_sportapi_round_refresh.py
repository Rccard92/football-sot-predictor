"""Test refresh batch turno SportAPI — skip recente e summary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.sportapi.sportapi_round_refresh_service import (
    SKIP_FETCH_MINUTES,
    SportApiRoundRefreshService,
    _fetched_at_age_minutes,
)


def test_fetched_at_age_minutes_recent():
    ft = datetime.now(timezone.utc) - timedelta(minutes=3)
    age = _fetched_at_age_minutes(ft)
    assert age is not None
    assert age < SKIP_FETCH_MINUTES


def test_refresh_skips_recent_lineup_without_api_fetch():
    svc = SportApiRoundRefreshService()
    db = MagicMock()
    fx = SimpleNamespace(id=42, api_fixture_id=9001, home_team_id=1, away_team_id=2)
    lu = SimpleNamespace(
        confirmed=False,
        fetched_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )

    with (
        patch.object(svc, "_season_row", return_value=SimpleNamespace(id=1, year=2025)),
        patch.object(svc, "upcoming_next_round_fixtures", return_value=[fx]),
        patch.object(svc, "_has_mapping", return_value=True),
        patch(
            "app.services.sportapi.sportapi_round_refresh_service.lineup_row_for_fixture",
            return_value=lu,
        ),
        patch(
            "app.services.sportapi.sportapi_round_refresh_service.SportApiLineupService",
        ) as mock_lineup_cls,
    ):
        mock_lineup_cls.return_value.fetch_and_persist_lineups = MagicMock()
        out = svc.refresh_next_round_lineups(db, 2025, force=False)

    assert out["total_fixtures"] == 1
    assert out["skipped_recent"] == 1
    assert out["updated"] == 0
    assert out["failed"] == 0
    assert out["results"][0]["status"] == "skipped_recent"
    mock_lineup_cls.return_value.fetch_and_persist_lineups.assert_not_called()
