"""Test HistoricalLineupMacroService e integrazione macro lineups (Step J)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.schemas.backtest_historical_fixture_snapshot import (
    HistoricalFixtureOfficialSnapshot,
    HistoricalFixtureSideSnapshot,
)
from app.schemas.backtest_historical_lineup_audit import HistoricalLineupSideCoverage
from app.schemas.backtest_point_in_time import (
    ActualsForScoring,
    LeaguePointInTimeBaselines,
    LineupDiagnostic,
    PlayerStatsDiagnostic,
    PointInTimeContextResponse,
    TeamLast5Form,
    TeamLineupMacroPointInTime,
    TeamPointInTimeStats,
    TeamSplitPointInTimeStats,
    TeamUnavailableMacroPointInTime,
)
from app.services.backtest.historical_lineup_macro_service import (
    HistoricalLineupMacroService,
    compute_lineup_macro_index,
    starter_completeness_index,
    xi_continuity_index,
)
from app.services.backtest.sot_v21_pit_macro_builder import build_pit_side_preview

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def test_xi_continuity_overlap_8_of_11():
    assert xi_continuity_index(8) == 1.03


def test_starter_completeness_11_starters():
    assert starter_completeness_index(11) == 1.00


def test_compute_lineup_macro_index_with_continuity_boost():
    components = {
        "official_xi_presence_index": 1.0,
        "starter_completeness_index": 1.0,
        "formation_structure_index": 1.0,
        "xi_continuity_index": 1.03,
        "formation_change_index": 1.0,
        "offensive_starter_count_index": 1.0,
        "bench_availability_index": 1.0,
    }
    assert compute_lineup_macro_index(components) == 1.0075


@patch("app.services.backtest.historical_lineup_macro_service.load_previous_official_lineups", return_value=[])
def test_absent_xi_returns_neutral_fallback(mock_prev):
    del mock_prev
    coverage = HistoricalLineupSideCoverage(has_official_xi=False, starters_count=0, bench_count=0)
    side = HistoricalFixtureSideSnapshot(
        team_id=1,
        side="home",
        status="missing",
        coverage=coverage,
        warnings=["target_fixture_lineup_missing"],
    )
    snapshot = HistoricalFixtureOfficialSnapshot(
        fixture_id=146,
        competition_id=1,
        home_team_id=1,
        away_team_id=2,
        cutoff_time=_CUTOFF,
        home=side,
        away=side.model_copy(update={"team_id": 2, "side": "away"}),
    )

    result = HistoricalLineupMacroService().build_team_lineup_macro(
        MagicMock(),
        snapshot=snapshot,
        competition_id=1,
        team_id=1,
        cutoff_time=_CUTOFF,
        side="home",
    )

    assert result.status == "neutral_fallback"
    assert result.lineup_macro_index == 1.0
    assert "target_fixture_lineup_missing" in result.warnings
    assert result.source_fixture_id == 146


def _base_ctx(**updates) -> PointInTimeContextResponse:
    data = dict(
        competition_id=1,
        competition_key="serie-a",
        competition_name="Serie A",
        fixture_id=146,
        fixture_kickoff_at=_CUTOFF,
        fixture_status="FT",
        home_team_id=1,
        home_team_name="Home",
        away_team_id=2,
        away_team_name="Away",
        mode="pre_lineup",
        cutoff_time=_CUTOFF,
        home_team_stats=TeamPointInTimeStats(team_id=1, team_name="Home", avg_sot_for=5.0),
        away_team_stats=TeamPointInTimeStats(team_id=2, team_name="Away", avg_sot_for=4.0),
        home_split_stats=TeamSplitPointInTimeStats(team_id=1, split_context="home", matches_count=5),
        away_split_stats=TeamSplitPointInTimeStats(team_id=2, split_context="away", matches_count=5),
        league_baselines=LeaguePointInTimeBaselines(league_avg_sot_for=5.0, league_avg_total_shots=12.0),
        home_player_stats=PlayerStatsDiagnostic(),
        away_player_stats=PlayerStatsDiagnostic(),
        lineup_diagnostic=LineupDiagnostic(lineup_mode="pre_lineup_no_official"),
        actuals_for_scoring=ActualsForScoring(),
    )
    data.update(updates)
    return PointInTimeContextResponse(**data)


def _team_opp_league():
    team = TeamPointInTimeStats(
        team_id=1,
        team_name="Home",
        avg_sot_for=5.0,
        avg_sot_against=4.5,
        avg_total_shots_for=12.0,
        avg_xg_for=1.2,
        last5=TeamLast5Form(last5_avg_sot_for=5.1, last5_count=5),
    )
    opp = TeamPointInTimeStats(
        team_id=2,
        team_name="Away",
        avg_sot_for=4.0,
        avg_sot_against=5.0,
        avg_total_shots_for=11.0,
        avg_xg_against=1.1,
        last5=TeamLast5Form(last5_avg_sot_against=4.8, last5_count=5),
    )
    league = LeaguePointInTimeBaselines(
        league_avg_sot_for=5.0,
        league_avg_total_shots=12.0,
        league_avg_xg_for=1.2,
        league_avg_xg_conceded=1.2,
    )
    return team, opp, league


def _sample_lineup_macro(**updates) -> TeamLineupMacroPointInTime:
    data = dict(
        status="available",
        lineup_macro_index=1.0075,
        formation="4-3-3",
        starters_count=11,
        bench_count=7,
        previous_xi_overlap_count=8,
        previous_xi_overlap_pct=72.73,
        formation_changed_vs_previous=False,
        formation_changed_vs_common=False,
        components={
            "official_xi_presence_index": 1.03,
            "starter_completeness_index": 1.0,
            "formation_structure_index": 1.02,
            "xi_continuity_index": 1.03,
            "formation_change_index": 1.0,
            "offensive_starter_count_index": 1.0,
            "bench_availability_index": 1.01,
        },
        warnings=[],
        fallback_variables=[],
    )
    data.update(updates)
    return TeamLineupMacroPointInTime(**data)


def test_pre_lineup_lineups_macro_still_neutral():
    ctx = _base_ctx()
    team, opp, league = _team_opp_league()
    result = build_pit_side_preview(
        team=team,
        opponent=opp,
        league=league,
        ctx=ctx,
        is_home=True,
        mode="pre_lineup",
    )
    lineups = next(m for m in result.macro_results if m.key == "lineups")
    assert lineups.macro_index == 1.0
    assert lineups.status == "not_built_yet"
    assert "no_historical_probable_lineups" in lineups.warnings


def _sample_unavailable_macro(**updates) -> TeamUnavailableMacroPointInTime:
    data = dict(
        status="available",
        unavailable_macro_index=1.0,
        unavailable_count=0,
        injured_count=0,
        suspended_count=0,
        components={"offensive_absence_penalty": 0.0, "opponent_defensive_absence_boost": 0.0},
        reason="no_unavailable_players_for_fixture",
        source_fixture_id=146,
    )
    data.update(updates)
    return TeamUnavailableMacroPointInTime(**data)


def test_historical_official_xi_unavailable_macro_available():
    lineup = _sample_lineup_macro(source_fixture_id=146)
    unavail = _sample_unavailable_macro()
    ctx = _base_ctx(
        mode="historical_official_xi",
        lineup_diagnostic=LineupDiagnostic(lineup_mode="historical_official_xi", lineups_available=True),
        home_lineup_macro=lineup,
        away_lineup_macro=lineup,
        home_unavailable_macro=unavail,
        away_unavailable_macro=unavail,
    )
    team, opp, league = _team_opp_league()
    result = build_pit_side_preview(
        team=team,
        opponent=opp,
        league=league,
        ctx=ctx,
        is_home=True,
        mode="historical_official_xi",
    )
    injuries = next(m for m in result.macro_results if m.key == "injuries_unavailable")
    assert injuries.macro_index == 1.0
    assert injuries.status == "available"
    assert "injuries_point_in_time_not_built_yet" not in injuries.warnings
    trace = next(t for t in result.macro_traces if t["key"] == "injuries_unavailable")
    assert trace["source_fixture_id"] == 146


def test_historical_official_xi_lineups_macro_available():
    lineup = _sample_lineup_macro(source_fixture_id=146)
    ctx = _base_ctx(
        mode="historical_official_xi",
        lineup_diagnostic=LineupDiagnostic(lineup_mode="historical_official_xi", lineups_available=True),
        home_lineup_macro=lineup,
        away_lineup_macro=lineup,
    )
    team, opp, league = _team_opp_league()
    result = build_pit_side_preview(
        team=team,
        opponent=opp,
        league=league,
        ctx=ctx,
        is_home=True,
        mode="historical_official_xi",
    )
    lineups = next(m for m in result.macro_results if m.key == "lineups")
    assert lineups.macro_index == 1.0075
    assert lineups.status == "available"
    assert lineups.macro_weight == 5
    assert "no_historical_probable_lineups" not in lineups.warnings
    assert "lineups_point_in_time_limited" not in lineups.warnings
    assert "lineups_point_in_time_neutral" not in result.fallback_variables
    trace = next(t for t in result.macro_traces if t["key"] == "lineups")
    assert trace.get("source_fixture_id") == 146
