"""Test HistoricalPitExtensionsBuilder (Step JK.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.schemas.backtest_historical_fixture_snapshot import (
    HistoricalFixtureOfficialSnapshot,
    HistoricalFixtureSideSnapshot,
)
from app.schemas.backtest_point_in_time import (
    ActualsForScoring,
    LeaguePointInTimeBaselines,
    LineupDiagnostic,
    PlayerStatsDiagnostic,
    PointInTimeContextResponse,
    TeamLineupMacroPointInTime,
    TeamPlayerLayerPointInTime,
    TeamPointInTimeStats,
    TeamSplitPointInTimeStats,
    TeamUnavailableMacroPointInTime,
)
from app.services.backtest.historical_pit_extensions_builder import HistoricalPitExtensionsBuilder

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
_FID = 146


def _base_ctx() -> PointInTimeContextResponse:
    return PointInTimeContextResponse(
        competition_id=1,
        competition_key="serie_a",
        competition_name="Serie A",
        fixture_id=_FID,
        fixture_kickoff_at=_CUTOFF,
        fixture_status="FT",
        home_team_id=10,
        home_team_name="AC Milan",
        away_team_id=20,
        away_team_name="Sassuolo",
        mode="historical_official_xi",
        cutoff_time=_CUTOFF,
        home_team_stats=TeamPointInTimeStats(team_id=10, team_name="AC Milan", sample_count=10),
        away_team_stats=TeamPointInTimeStats(team_id=20, team_name="Sassuolo", sample_count=10),
        home_split_stats=TeamSplitPointInTimeStats(team_id=10, split_context="home", status="available"),
        away_split_stats=TeamSplitPointInTimeStats(team_id=20, split_context="away", status="available"),
        league_baselines=LeaguePointInTimeBaselines(sample_count=100, league_avg_sot_for=4.5),
        home_player_stats=PlayerStatsDiagnostic(),
        away_player_stats=PlayerStatsDiagnostic(),
        lineup_diagnostic=LineupDiagnostic(lineup_mode="historical_official_xi"),
        actuals_for_scoring=ActualsForScoring(),
    )


def _snapshot() -> HistoricalFixtureOfficialSnapshot:
    return HistoricalFixtureOfficialSnapshot(
        fixture_id=_FID,
        competition_id=1,
        home_team_id=10,
        away_team_id=20,
        cutoff_time=_CUTOFF,
        home=HistoricalFixtureSideSnapshot(team_id=10, side="home", status="available"),
        away=HistoricalFixtureSideSnapshot(team_id=20, side="away", status="available"),
    )


@patch("app.services.backtest.historical_pit_extensions_builder.HistoricalUnavailableMacroService")
@patch("app.services.backtest.historical_pit_extensions_builder.HistoricalLineupMacroService")
@patch("app.services.backtest.historical_pit_extensions_builder.RollingPlayerLayerService")
@patch("app.services.backtest.historical_pit_extensions_builder.HistoricalFixtureSnapshotService")
def test_build_historical_extensions_populates_summary(
    mock_snapshot_cls,
    mock_layer_cls,
    mock_lineup_cls,
    mock_unavail_cls,
):
    snapshot = _snapshot()
    mock_snapshot_cls.return_value.get_fixture_official_snapshot.return_value = snapshot

    home_layer = TeamPlayerLayerPointInTime(status="available", player_layer_index=1.02)
    away_layer = TeamPlayerLayerPointInTime(status="available", player_layer_index=0.98)
    mock_layer_cls.return_value.build_team_player_layer.side_effect = [home_layer, away_layer]

    home_lineup = TeamLineupMacroPointInTime(
        status="available",
        lineup_macro_index=1.01,
        source_fixture_id=_FID,
    )
    away_lineup = TeamLineupMacroPointInTime(
        status="available",
        lineup_macro_index=0.99,
        source_fixture_id=_FID,
    )
    mock_lineup_cls.return_value.build_team_lineup_macro.side_effect = [home_lineup, away_lineup]

    home_unavail = TeamUnavailableMacroPointInTime(
        status="neutral_fallback",
        unavailable_macro_index=1.0,
        source_fixture_id=_FID,
    )
    away_unavail = TeamUnavailableMacroPointInTime(
        status="neutral_fallback",
        unavailable_macro_index=1.0,
        source_fixture_id=_FID,
    )
    mock_unavail_cls.return_value.build_team_unavailable_macro.side_effect = [home_unavail, away_unavail]

    db = MagicMock()
    result = HistoricalPitExtensionsBuilder().build_historical_extensions(
        db,
        competition_id=1,
        fixture_id=_FID,
        ctx=_base_ctx(),
    )

    assert result.historical_summary is not None
    assert result.historical_summary.source_fixture_id == _FID
    assert result.historical_summary.source_fixture_id_lineup_home == _FID
    assert result.historical_summary.source_fixture_id_unavailable_away == _FID
    assert result.fixture_snapshot is not None
    assert result.home_lineup_macro is not None
    assert result.home_unavailable_macro is not None
