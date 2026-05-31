"""Test HistoricalFixtureSnapshotService (Step J/K)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.schemas.backtest_historical_fixture_snapshot import HistoricalFixtureSideSnapshot
from app.schemas.backtest_historical_lineup_audit import HistoricalLineupSideCoverage
from app.services.backtest.historical_fixture_snapshot_service import HistoricalFixtureSnapshotService
from app.services.backtest.pit_player_rolling_stats import RawPlayerRow

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def _fixture_mock(*, fixture_id: int = 146, competition_id: int = 1):
    fx = MagicMock()
    fx.id = fixture_id
    fx.competition_id = competition_id
    fx.home_team_id = 10
    fx.away_team_id = 20
    fx.kickoff_at = _CUTOFF
    return fx


@patch("app.services.backtest.historical_fixture_snapshot_service.resolve_side_lineup")
@patch("app.services.backtest.historical_fixture_snapshot_service.load_sportapi_missing_by_side")
def test_snapshot_uses_target_fixture_id_only(mock_missing, mock_resolve):
    mock_missing.return_value = ([], [])
    coverage = HistoricalLineupSideCoverage(
        has_official_xi=True,
        starters_count=11,
        bench_count=7,
        formation="4-3-3",
        source_table="fixture_lineups",
        source_provider="api_football",
        source_timestamp_status="safe",
    )
    starters = [
        RawPlayerRow(
            player_name="Striker",
            provider_player_id=None,
            api_player_id=1,
            position="F",
            is_starter=True,
        )
    ]
    mock_resolve.return_value = (coverage, starters, [], [])

    db = MagicMock()
    db.get.return_value = _fixture_mock(fixture_id=146)

    snapshot = HistoricalFixtureSnapshotService().get_fixture_official_snapshot(
        db,
        competition_id=1,
        fixture_id=146,
    )

    assert snapshot.fixture_id == 146
    assert snapshot.home.status == "available"
    assert len(snapshot.home.starters) == 1
    assert mock_missing.call_args[0][1] == 146
    assert mock_resolve.call_args.kwargs["fixture"].id == 146


def test_snapshot_missing_lineup_status():
    db = MagicMock()
    db.get.return_value = None
    snapshot = HistoricalFixtureSnapshotService().get_fixture_official_snapshot(
        db,
        competition_id=1,
        fixture_id=146,
    )
    assert snapshot.fixture_id == 146
    assert snapshot.home.status == "missing"
    assert "target_fixture_lineup_missing" in snapshot.warnings


def test_competition_mismatch():
    db = MagicMock()
    db.get.return_value = _fixture_mock(fixture_id=146, competition_id=99)
    snapshot = HistoricalFixtureSnapshotService().get_fixture_official_snapshot(
        db,
        competition_id=1,
        fixture_id=146,
    )
    assert "competition_id_mismatch" in snapshot.warnings
