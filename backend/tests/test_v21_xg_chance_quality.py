"""Test collegamento xG reali alla macroarea Qualità occasioni v2.1."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.predictions_common.xg_strict_helpers import (
    StrictXgSnapshot,
    build_strict_xg_snapshot,
)
from app.services.predictions_v21.v21_feature_collectors import _collect_chance_quality
from app.services.predictions_v21.v21_macro_aggregators import aggregate_v21_macro_score
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS
from app.services.predictions_v21.v21_xg_coverage import resolve_league_xg_available
from app.services.predictions_v21.v21_xg_league_features import (
    build_xg_leakage_trace,
    compute_v21_xg_league_baselines,
    latest_prior_kickoff,
)
from app.services.sot_feature_math import fixture_key_before


def _chance_quality_macro():
    for macro in V21_MANIFEST_DEFINITIONS:
        if macro.key == "chance_quality":
            return macro
    raise KeyError("chance_quality")


def _chance_quality_micro(key: str):
    macro = _chance_quality_macro()
    for m in macro.micros:
        if m.key == key:
            return m
    raise KeyError(key)


def _team_stat(**kwargs) -> SimpleNamespace:
    base = dict(
        expected_goals=1.2,
        raw_json=None,
        shots_on_target=4,
        total_shots=12,
        shots_inside_box=6,
        shots_outside_box=3,
        blocked_shots=2,
        shots_off_goal=5,
        ball_possession_pct=None,
        total_passes=None,
        accurate_passes=None,
        pass_accuracy_pct=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _prior_with_xg(*, team_xg: float, opp_xg: float, team_n: int, opp_n: int):
    team_fixtures = []
    opp_fixtures = []
    stats_map = {}
    base_ko = datetime(2026, 5, 1, tzinfo=timezone.utc)
    for i in range(team_n):
        fid = i + 1
        fx = SimpleNamespace(
            id=fid,
            home_team_id=1,
            away_team_id=99,
            kickoff_at=base_ko,
            goals_home=1,
            goals_away=0,
        )
        team_fixtures.append(fx)
        stats_map[(fid, 1)] = _team_stat(expected_goals=team_xg)
    for i in range(opp_n):
        fid = 100 + i
        fx = SimpleNamespace(
            id=fid,
            home_team_id=88,
            away_team_id=2,
            kickoff_at=base_ko,
            goals_home=0,
            goals_away=1,
        )
        opp_fixtures.append(fx)
        stats_map[(fid, 88)] = _team_stat(expected_goals=opp_xg)
    return team_fixtures, opp_fixtures, stats_map


def _ctx(
    *,
    team_xg=1.45,
    opp_xg=1.35,
    league_for=1.25,
    league_conc=1.20,
    lsot_for=4.0,
    lsot_conc=4.0,
    team_n=10,
    opp_n=9,
):
    team_fixtures, opp_fixtures, stats_map = _prior_with_xg(
        team_xg=team_xg,
        opp_xg=opp_xg,
        team_n=team_n,
        opp_n=opp_n,
    )
    league_baselines = {
        "league_avg_xg_for": league_for,
        "league_avg_xg_conceded": league_conc,
        "league_avg_sot_for": lsot_for,
        "league_avg_sot_conceded": lsot_conc,
    }
    strict_xg = build_strict_xg_snapshot(
        prior_fixtures=team_fixtures,
        opponent_prior_fixtures=opp_fixtures,
        stats_map=stats_map,
        team_id=1,
        opponent_id=2,
        league_baselines=league_baselines,
    )
    return SimpleNamespace(
        league_xg_available=True,
        league_baselines=league_baselines,
        team_agg={"xg_mean": team_xg, "xg_n": team_n},
        opp_conceded_agg={"xg_mean": opp_xg, "xg_n": opp_n},
        strict_xg=strict_xg,
        xg_leakage_trace={
            "sample_count": max(team_n, opp_n),
            "latest_fixture_used_at": "2026-05-20T18:00:00+00:00",
            "leakage_guard": True,
        },
    )


def test_latest_prior_kickoff():
    f1 = SimpleNamespace(kickoff_at=datetime(2026, 5, 10, tzinfo=timezone.utc), id=1)
    f2 = SimpleNamespace(kickoff_at=datetime(2026, 5, 20, tzinfo=timezone.utc), id=2)
    assert latest_prior_kickoff([f1, f2]) == f2.kickoff_at


def test_build_xg_leakage_trace():
    f1 = SimpleNamespace(kickoff_at=datetime(2026, 5, 15, tzinfo=timezone.utc), id=1)
    trace = build_xg_leakage_trace(
        team_fixtures=[f1],
        opp_fixtures=[],
        team_sample_count=5,
        opp_sample_count=3,
    )
    assert trace["leakage_guard"] is True
    assert trace["sample_count"] == 5
    assert trace["latest_fixture_used_at"] is not None


def test_xg_delta_raw_is_absolute_delta():
    micro = _chance_quality_micro("xg_delta_vs_league")
    ctx = _ctx(team_xg=2.0, league_for=1.0)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert float(result.raw_value) == 1.0
    assert "derived:avg_xg_for" in result.source_path
    assert result.normalized_value == 1.25
    assert result.leakage_guard is True


def test_opp_xg_conceded_delta_raw_is_absolute_delta():
    micro = _chance_quality_micro("opp_xg_conceded_delta")
    ctx = _ctx(opp_xg=1.5, league_conc=1.25)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert abs(float(result.raw_value) - 0.25) < 0.001
    assert "opponent_avg_xg_conceded" in result.source_path


def test_xg_prudent_adjustment_cap():
    micro = _chance_quality_micro("xg_prudent_adjustment")
    ctx = _ctx(team_xg=2.5, opp_xg=2.5, league_for=1.0)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert result.normalized_value == 1.08
    assert abs(float(result.raw_value)) <= 0.08


def test_xg_prudent_adjustment_neutral_band():
    micro = _chance_quality_micro("xg_prudent_adjustment")
    ctx = _ctx(team_xg=1.25, opp_xg=1.25, league_for=1.25)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert abs(result.normalized_value - 1.0) < 0.01


def test_all_chance_quality_micros_available():
    ctx = _ctx()
    for micro in _chance_quality_macro().micros:
        result = _collect_chance_quality(ctx, micro)
        assert result.status == "available", micro.key
        trace = result.to_trace_input()
        assert trace.get("leakage_guard") is True
        assert trace.get("latest_fixture_used_at") is not None
        assert trace.get("raw_value") is not None


def test_chance_quality_macro_available_full_coverage():
    ctx = _ctx()
    micro_results = [_collect_chance_quality(ctx, m) for m in _chance_quality_macro().micros]
    macro_result = aggregate_v21_macro_score(_chance_quality_macro(), micro_results)
    assert macro_result.status == "available"
    assert macro_result.coverage_pct == 100.0


def test_partial_low_sample_when_below_minimum():
    micro = _chance_quality_micro("xg_produced")
    ctx = _ctx(team_n=3, opp_n=3)
    assert ctx.strict_xg.status == "insufficient_xg_sample"
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "partial_low_sample"
    assert result.raw_value is not None


def test_fixture_key_before_excludes_future():
    cutoff = datetime(2026, 5, 25, tzinfo=timezone.utc)
    assert fixture_key_before(datetime(2026, 5, 24, tzinfo=timezone.utc), 1, cutoff, 99) is True
    assert fixture_key_before(datetime(2026, 5, 25, tzinfo=timezone.utc), 50, cutoff, 99) is True
    assert fixture_key_before(datetime(2026, 5, 25, tzinfo=timezone.utc), 100, cutoff, 99) is False
    assert fixture_key_before(datetime(2026, 5, 26, tzinfo=timezone.utc), 1, cutoff, 99) is False


@patch("app.services.predictions_v21.v21_xg_league_features.select")
def test_compute_v21_xg_league_baselines_scoped_competition(mock_select):
    db = MagicMock()
    comp1_fx = SimpleNamespace(
        id=1,
        home_team_id=10,
        away_team_id=20,
        kickoff_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        competition_id=1,
        status="FT",
    )
    db.scalars.return_value.all.side_effect = [
        [comp1_fx],
        [
            SimpleNamespace(
                fixture_id=1,
                team_id=10,
                expected_goals=1.4,
                raw_json=None,
                shots_on_target=5.0,
            ),
            SimpleNamespace(
                fixture_id=1,
                team_id=20,
                expected_goals=1.1,
                raw_json=None,
                shots_on_target=4.0,
            ),
        ],
    ]
    out = compute_v21_xg_league_baselines(
        db,
        season_id=1,
        cutoff_kickoff=datetime(2026, 5, 25, tzinfo=timezone.utc),
        cutoff_fixture_id=99,
        competition_id=1,
    )
    assert out["league_avg_xg_for"] == 1.25
    assert out["league_avg_sot_for"] == 4.5
    assert out["leakage_guard"] is True
    assert out["sample_fixtures"] == 1


@patch("app.services.predictions_v21.v21_xg_league_features.select")
def test_compute_v21_xg_league_baselines_fallback_without_season_id(mock_select):
    db = MagicMock()
    comp1_fx = SimpleNamespace(
        id=1,
        home_team_id=10,
        away_team_id=20,
        kickoff_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        competition_id=1,
        season_id=None,
        status="FT",
    )
    db.scalars.return_value.all.side_effect = [
        [],
        [comp1_fx],
        [
            SimpleNamespace(
                fixture_id=1,
                team_id=10,
                expected_goals=1.4,
                raw_json=None,
                shots_on_target=5.0,
            ),
            SimpleNamespace(
                fixture_id=1,
                team_id=20,
                expected_goals=1.1,
                raw_json=None,
                shots_on_target=4.0,
            ),
        ],
    ]
    out = compute_v21_xg_league_baselines(
        db,
        season_id=99,
        cutoff_kickoff=datetime(2026, 5, 25, tzinfo=timezone.utc),
        cutoff_fixture_id=99,
        competition_id=1,
    )
    assert out["league_avg_xg_for"] == 1.25
    assert out["sample_fixtures"] == 1
    assert out.get("season_id_fallback_used") is True


def test_resolve_league_xg_available_when_baseline_present():
    db = MagicMock()
    available = resolve_league_xg_available(
        db,
        competition_id=1,
        league_baselines={"league_avg_xg_for": 1.2536},
        team_agg={"xg_n": 0},
        opp_conceded_agg={"xg_n": 0},
    )
    assert available is True


def test_xg_delta_missing_when_strict_snapshot_missing_baseline():
    micro = _chance_quality_micro("xg_delta_vs_league")
    ctx = _ctx()
    ctx.strict_xg = StrictXgSnapshot(status="missing_required_xg_league_baseline")
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "missing"


def test_xg_prudent_min_cap():
    micro = _chance_quality_micro("xg_prudent_adjustment")
    ctx = _ctx(team_xg=0.1, opp_xg=0.1, league_for=1.0)
    result = _collect_chance_quality(ctx, micro)
    assert result.normalized_value == 0.92
