"""Test RollingPlayerLayerService e helper (Step G2B)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.schemas.backtest_historical_fixture_snapshot import (
    HistoricalFixtureSideSnapshot,
    HistoricalSnapshotPlayerRow,
)
from app.schemas.backtest_historical_lineup_audit import (
    HistoricalLineupPlayerPriorStats,
    HistoricalLineupSideCoverage,
)
from app.schemas.backtest_point_in_time import (
    ActualsForScoring,
    LeaguePointInTimeBaselines,
    LineupDiagnostic,
    PointInTimeContextResponse,
    PlayerStatsDiagnostic,
    TeamLast5Form,
    TeamPlayerLayerPointInTime,
    TeamPointInTimeStats,
    TeamSplitPointInTimeStats,
)
from app.services.backtest.rolling_player_layer_service import (
    RollingPlayerLayerService,
    _clamp,
    _role_weight,
)
from app.services.backtest.sot_v21_pit_macro_builder import build_pit_side_preview

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def _player(
    *,
    name: str,
    role: str = "F",
    sot_per90: float = 0.5,
    share: float = 0.15,
    minutes: int = 900,
    matches: int = 10,
    latest: datetime | None = None,
    is_starter: bool = True,
) -> HistoricalLineupPlayerPriorStats:
    return HistoricalLineupPlayerPriorStats(
        player_name=name,
        provider_player_id=1,
        internal_player_id=1,
        api_player_id=100,
        role=role,
        is_starter=is_starter,
        prior_minutes=minutes,
        prior_shots_total=20,
        prior_shots_on=10,
        prior_sot_per90=sot_per90,
        prior_shots_per90=1.0,
        prior_team_sot_share=share,
        prior_matches_count=matches,
        latest_player_stat_fixture_used_at=latest,
        mapping_status="matched",
        warnings=[],
    )


def test_role_weights():
    assert _role_weight("F") == 1.00
    assert _role_weight("ST") == 1.00
    assert _role_weight("M") == 0.75
    assert _role_weight("CM") == 0.75
    assert _role_weight("D") == 0.35
    assert _role_weight("CB") == 0.35
    assert _role_weight("G") == 0.00
    assert _role_weight("GK") == 0.00


def test_player_layer_index_cap():
    offensive = 2.0
    top_sh = 1.5
    bench = 1.2
    index = _clamp(0.55 * offensive + 0.30 * top_sh + 0.15 * bench, 0.70, 1.30)
    assert index == 1.30


def test_top_shooter_all_in_xi():
    svc = RollingPlayerLayerService()
    starters = [
        _player(name="A", share=0.30),
        _player(name="B", share=0.25),
        _player(name="C", share=0.20),
    ]
    index, warnings = svc._compute_top_shooter_presence(starters=starters, bench=[], cutoff=_CUTOFF)
    assert index == 1.10
    assert "top_shooter_missing_from_xi" not in warnings


def test_top_shooter_one_on_bench():
    svc = RollingPlayerLayerService()
    starters = [_player(name="A", share=0.30), _player(name="B", share=0.25)]
    bench = [_player(name="C", share=0.20, minutes=900, is_starter=False)]
    index, warnings = svc._compute_top_shooter_presence(
        starters=starters,
        bench=bench,
        cutoff=_CUTOFF,
    )
    assert index == 0.95
    assert "top_shooter_only_bench" in warnings


def test_baseline_missing_fallback_index():
    svc = RollingPlayerLayerService()
    layer = svc._neutral_fallback(["player_layer_baseline_missing"])
    assert layer.status == "neutral_fallback"
    assert layer.player_layer_index == 1.0


def test_leakage_exclusion_neutral_fallback():
    svc = RollingPlayerLayerService()
    db = MagicMock()
    fixture = MagicMock()
    fixture.id = 146
    fixture.home_team_id = 1
    fixture.away_team_id = 2
    db.get.return_value = fixture

    coverage = HistoricalLineupSideCoverage(
        has_official_xi=True,
        starters_count=11,
        bench_count=5,
        formation="4-3-3",
    )
    side_snapshot = HistoricalFixtureSideSnapshot(
        team_id=1,
        side="home",
        status="available",
        formation="4-3-3",
        coverage=coverage,
        starters=[
            HistoricalSnapshotPlayerRow(player_name="Leaky", api_player_id=1, position="F", is_starter=True),
        ],
    )
    with patch(
        "app.services.backtest.rolling_player_layer_service.build_player_prior_stats",
        return_value=_player(
            name="Leaky",
            latest=datetime(2026, 3, 15, 20, 0, tzinfo=timezone.utc),
        ),
    ), patch(
        "app.services.backtest.rolling_player_layer_service.build_mapping_summary",
    ) as mock_map:
        mock_map.return_value.mapping_coverage_pct = 100.0
        mock_map.return_value.player_stats_prior_coverage_pct = 100.0
        result = svc.build_team_player_layer(
            db,
            competition_id=1,
            team_id=1,
            cutoff_time=_CUTOFF,
            side_snapshot=side_snapshot,
        )
    assert result.status == "neutral_fallback"
    assert result.player_layer_index == 1.0
    assert "possible_player_stats_leakage" in result.warnings


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


def test_pre_lineup_player_layer_macro_neutral():
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
    pl = next(m for m in result.macro_results if m.key == "player_layer")
    assert pl.macro_index == 1.0
    assert pl.status == "not_built_yet"
    assert "player_layer_point_in_time_not_built_yet" in pl.warnings


def test_historical_official_xi_player_layer_macro_available():
    layer = TeamPlayerLayerPointInTime(
        status="available",
        formation="4-3-3",
        starters_count=11,
        bench_count=7,
        mapping_coverage_pct=100.0,
        prior_stats_coverage_pct=100.0,
        offensive_xi_strength_index=1.08,
        top_shooter_presence_index=1.10,
        replacement_depth_index=1.02,
        player_layer_index=1.08,
        top_starters=[{"player_name": "Striker", "contribution_score": 1.2}],
        warnings=[],
    )
    ctx = _base_ctx(
        mode="historical_official_xi",
        lineup_diagnostic=LineupDiagnostic(lineup_mode="historical_official_xi", lineups_available=True),
        home_player_layer=layer,
        away_player_layer=layer,
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
    pl = next(m for m in result.macro_results if m.key == "player_layer")
    assert pl.macro_index == 1.08
    assert pl.status == "available"
    assert pl.macro_weight == 9
    assert "player_layer_point_in_time_not_built_yet" not in pl.warnings
