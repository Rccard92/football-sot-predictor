"""Test collegamento xG reali alla macroarea Qualità occasioni v2.1."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.predictions_v21.v21_constants import (
    MICRO_NORM_MAX,
    MICRO_NORM_MIN,
    XG_PRUDENT_ADJ_MAX,
    XG_PRUDENT_ADJ_MIN,
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


def _ctx(*, team_xg=1.45, opp_xg=1.35, league_for=1.25, league_conc=1.20, team_n=10, opp_n=9):
    return SimpleNamespace(
        league_xg_available=True,
        league_baselines={
            "league_avg_xg_for": league_for,
            "league_avg_xg_conceded": league_conc,
        },
        team_agg={"xg_mean": team_xg, "xg_n": team_n},
        opp_conceded_agg={"xg_mean": opp_xg, "xg_n": opp_n},
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


def test_xg_delta_uses_ratio_cap():
    micro = _chance_quality_micro("xg_delta_vs_league")
    ctx = _ctx(team_xg=2.0, league_for=1.0)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert result.normalized_value == MICRO_NORM_MAX
    assert result.source_path == "derived.team_xg_for_vs_league_avg"
    assert result.leakage_guard is True


def test_opp_xg_conceded_delta_vs_league_for_baseline():
    micro = _chance_quality_micro("opp_xg_conceded_delta")
    ctx = _ctx(opp_xg=1.5, league_for=1.25)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    expected_ratio = 1.5 / 1.25
    assert abs(float(result.raw_value) - expected_ratio) < 0.001


def test_xg_prudent_adjustment_cap():
    micro = _chance_quality_micro("xg_prudent_adjustment")
    ctx = _ctx(team_xg=2.5, opp_xg=2.5, league_for=1.0)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert result.normalized_value == XG_PRUDENT_ADJ_MAX
    assert float(result.raw_value) > XG_PRUDENT_ADJ_MAX


def test_xg_prudent_adjustment_neutral_band():
    micro = _chance_quality_micro("xg_prudent_adjustment")
    ctx = _ctx(team_xg=1.25, opp_xg=1.25, league_for=1.25)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert result.normalized_value == 1.0


def test_all_chance_quality_micros_available():
    ctx = _ctx()
    for micro in _chance_quality_macro().micros:
        result = _collect_chance_quality(ctx, micro)
        assert result.status == "available", micro.key
        trace = result.to_trace_input()
        assert trace.get("leakage_guard") is True
        assert trace.get("latest_fixture_used_at") is not None


def test_chance_quality_macro_available_full_coverage():
    ctx = _ctx()
    micro_results = [_collect_chance_quality(ctx, m) for m in _chance_quality_macro().micros]
    macro_result = aggregate_v21_macro_score(_chance_quality_macro(), micro_results)
    assert macro_result.status == "available"
    assert macro_result.coverage_pct == 100.0


def test_fixture_key_before_excludes_future():
    cutoff = datetime(2026, 5, 25, tzinfo=timezone.utc)
    assert fixture_key_before(datetime(2026, 5, 24, tzinfo=timezone.utc), 1, cutoff, 99) is True
    assert fixture_key_before(datetime(2026, 5, 25, tzinfo=timezone.utc), 1, cutoff, 99) is False
    assert fixture_key_before(datetime(2026, 5, 25, tzinfo=timezone.utc), 100, cutoff, 99) is True


@patch("app.services.predictions_v21.v21_xg_league_features.select")
def test_compute_v21_xg_league_baselines_scoped_competition(mock_select):
    db = MagicMock()
    comp1_fx = SimpleNamespace(
        id=1,
        home_team_id=10,
        away_team_id=20,
        kickoff_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        competition_id=1,
    )
    db.scalars.return_value.all.side_effect = [
        [comp1_fx],
        [
            SimpleNamespace(
                fixture_id=1,
                team_id=10,
                expected_goals=1.4,
                raw_json=None,
            ),
            SimpleNamespace(
                fixture_id=1,
                team_id=20,
                expected_goals=1.1,
                raw_json=None,
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
    assert out["leakage_guard"] is True
    assert out["sample_fixtures"] == 1


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


def test_xg_delta_missing_when_baseline_absent():
    micro = _chance_quality_micro("xg_delta_vs_league")
    ctx = _ctx()
    ctx.league_baselines["league_avg_xg_for"] = None
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "missing"


def test_xg_prudent_min_cap():
    micro = _chance_quality_micro("xg_prudent_adjustment")
    ctx = _ctx(team_xg=0.5, opp_xg=0.5, league_for=1.0)
    result = _collect_chance_quality(ctx, micro)
    assert result.normalized_value == XG_PRUDENT_ADJ_MIN
    assert float(result.raw_value) < XG_PRUDENT_ADJ_MIN
