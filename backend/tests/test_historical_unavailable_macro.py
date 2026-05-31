"""Test HistoricalUnavailableMacroService (Step K)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.schemas.backtest_historical_fixture_snapshot import (
    HistoricalFixtureOfficialSnapshot,
    HistoricalFixtureSideSnapshot,
    HistoricalSnapshotPlayerRow,
)
from app.schemas.backtest_historical_lineup_audit import HistoricalLineupSideCoverage
from app.services.backtest.historical_unavailable_macro_service import (
    HistoricalUnavailableMacroService,
    compute_unavailable_macro_index,
    offensive_absence_score,
)

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def _snapshot(**side_updates) -> HistoricalFixtureOfficialSnapshot:
    home = HistoricalFixtureSideSnapshot(
        team_id=1,
        side="home",
        status="available",
        formation="4-3-3",
        coverage=HistoricalLineupSideCoverage(has_official_xi=True, starters_count=11),
        unavailable_source="none",
        **side_updates,
    )
    away = HistoricalFixtureSideSnapshot(
        team_id=2,
        side="away",
        status="available",
        formation="4-4-2",
        coverage=HistoricalLineupSideCoverage(has_official_xi=True, starters_count=11),
        unavailable_source="none",
    )
    return HistoricalFixtureOfficialSnapshot(
        fixture_id=146,
        competition_id=1,
        home_team_id=1,
        away_team_id=2,
        cutoff_time=_CUTOFF,
        home=home,
        away=away,
    )


def test_no_unavailable_players_index_one():
    svc = HistoricalUnavailableMacroService()
    db = MagicMock()
    result = svc.build_team_unavailable_macro(
        db,
        snapshot=_snapshot(),
        competition_id=1,
        team_id=1,
        cutoff_time=_CUTOFF,
        side="home",
        opponent_side=_snapshot().away,
        league_avg_sot_for=5.0,
    )
    assert result.status == "available"
    assert result.unavailable_macro_index == 1.0
    assert result.reason == "no_unavailable_players_for_fixture"
    assert result.source_fixture_id == 146


def test_compute_unavailable_macro_index_caps():
    idx = compute_unavailable_macro_index(offensive_penalty=0.25, opponent_defensive_boost=0.12)
    assert idx == 0.87


def test_offensive_absence_score_role_weight():
    score_f = offensive_absence_score(1.0, 1.0, 0.2, baseline=1.0, role="ST")
    score_d = offensive_absence_score(1.0, 1.0, 0.2, baseline=1.0, role="CB")
    assert score_f > score_d


@patch("app.services.backtest.historical_unavailable_macro_service.build_player_prior_stats")
def test_unavailable_with_mapping_incomplete(mock_prior):
    mock_prior.return_value = MagicMock(
        player_name="Unknown",
        role="ST",
        prior_sot_per90=0.5,
        prior_shots_per90=1.0,
        prior_team_sot_share=0.1,
        prior_minutes=900,
        prior_matches_count=10,
        mapping_status="no_provider_id",
    )
    unavailable = [
        HistoricalSnapshotPlayerRow(
            player_name="Unknown",
            is_unavailable=True,
            absence_group="injured",
        ),
    ]
    snap = _snapshot(unavailable=unavailable, injured=unavailable)
    result = HistoricalUnavailableMacroService().build_team_unavailable_macro(
        MagicMock(),
        snapshot=snap,
        competition_id=1,
        team_id=1,
        cutoff_time=_CUTOFF,
        side="home",
        opponent_side=snap.away,
        league_avg_sot_for=5.0,
    )
    assert result.unavailable_count == 1
    assert result.source_fixture_id == 146
    assert "unavailable_players_mapping_incomplete" in result.warnings
