"""Test variabili derivate v2.1 (patch 2.1.8)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.predictions_v21.v21_feature_collectors import _collect_chance_quality, _collect_pace_control, _collect_player_layer
from app.services.predictions_v21.v21_feature_context import _agg_pace_for_team
from app.services.predictions_v21.v21_lineup_history import build_lineup_history, lineup_history_sufficient
from app.services.predictions_v21.v21_lineup_impact_helpers import top_shooter_absence_score
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS
from app.services.predictions_v21.v21_normalization import micro_status_counts_available
from app.services.predictions_v21.v21_variable_coverage import build_v21_variable_coverage_from_raw
from app.services.predictions_v21.v21_xg_coverage import XG_MISSING_WARNING
from app.services.sportapi.lineup_player_profile_lookup import LineupProfileEntry


def _micro_spec(macro_key: str, micro_key: str):
    for macro in V21_MANIFEST_DEFINITIONS:
        if macro.key == macro_key:
            for m in macro.micros:
                if m.key == micro_key:
                    return m
    raise KeyError((macro_key, micro_key))


def _ctx(**overrides):
    base = dict(
        team_agg={"shots_mean": 12.0, "sot_mean": 4.0},
        team_pace_agg={
            "passes_completed_mean": 420.0,
            "passes_completed_n": 8,
            "passes_completed_source": "derived",
            "passes_mean": 450.0,
        },
        sportapi_audit={"available": True},
        sportapi_side={
            "starters": [{"provider_player_id": 1, "player_name": "A"}],
            "missing_players": {"injured": [{"provider_player_id": 2, "player_name": "B"}]},
            "formation": "4-3-3",
        },
        profile_entries=[
            LineupProfileEntry(
                api_player_id=1,
                profile_key=1,
                name="A",
                normalized_name="a",
                team_id=10,
                player_profile_id="1",
                shots_on_target_per90=2.0,
                shots_total_per90=4.0,
                team_sot_share_pct=30.0,
                team_shots_share_pct=25.0,
                shots_total=40.0,
                shooting_impact_score=1.2,
                reliability_score=80,
                total_minutes=900.0,
                position="A",
                legacy_player_id=1,
                mock_player=MagicMock(),
                mock_profile=MagicMock(),
            ),
            LineupProfileEntry(
                api_player_id=2,
                profile_key=2,
                name="B",
                normalized_name="b",
                team_id=10,
                player_profile_id="2",
                shots_on_target_per90=1.5,
                shots_total_per90=3.0,
                team_sot_share_pct=20.0,
                team_shots_share_pct=15.0,
                shots_total=30.0,
                shooting_impact_score=1.0,
                reliability_score=70,
                total_minutes=800.0,
                position="A",
                legacy_player_id=2,
                mock_player=MagicMock(),
                mock_profile=MagicMock(),
            ),
        ],
        lineup_profiles_mode="lineup_and_profiles",
        lineup_history={
            "lineup_fixture_count": 5,
            "dominant_formation": "4-3-3",
            "typical_starter_api_ids": {1},
            "starter_frequency_by_api_id": {1: 0.8, 2: 0.2},
        },
        refresh_snapshot_missing_api_ids=None,
        league_xg_available=False,
        league_baselines={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_agg_pace_passes_completed_derived():
    st = SimpleNamespace(
        ball_possession_pct=55.0,
        total_passes=400,
        accurate_passes=None,
        pass_accuracy_pct=82.0,
    )
    fx = SimpleNamespace(id=1)
    out = _agg_pace_for_team(fixtures=[fx], stats_map={(1, 10): st}, team_id=10)
    assert out["passes_completed_mean"] is not None
    assert out["passes_completed_source"] == "derived"
    assert abs(float(out["passes_completed_mean"]) - 328.0) < 0.1


def test_collect_passes_completed_available_derived():
    ctx = _ctx()
    micro = _micro_spec("pace_control", "passes_completed")
    result = _collect_pace_control(ctx, micro)
    assert result.status == "available_derived"
    assert result.raw_value is not None
    assert result.source_path == "derived.passes_total_x_pass_accuracy"


def test_collect_top_shots_share():
    ctx = _ctx()
    micro = _micro_spec("player_layer", "top_shots_share")
    result = _collect_player_layer(ctx, micro)
    assert result.status == "available"
    assert result.raw_value == 20.0


def test_top_shooter_absence_weighted():
    ctx = _ctx()
    tops = ctx.profile_entries
    score = top_shooter_absence_score(ctx, tops)
    assert score is not None
    assert 0.0 < score <= 1.0


def test_lineup_history_sufficient():
    assert lineup_history_sufficient({"lineup_fixture_count": 3})
    assert not lineup_history_sufficient({"lineup_fixture_count": 1})


def test_xg_missing_warning_constant():
    assert "feed" in XG_MISSING_WARNING.lower()


def test_xg_micro_status_feed_unavailable():
    from types import SimpleNamespace

    micro = _micro_spec("chance_quality", "xg_produced")
    ctx = _ctx(league_xg_available=False)
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "feed_unavailable"
    assert result.source_path == "feed_unavailable.xg"


def test_variable_coverage_rollup():
    raw = {
        "macroareas": [
            {
                "key": "pace_control",
                "label": "Ritmo",
                "micros": [
                    {"key": "passes_completed", "status": "available_derived"},
                    {"key": "total_passes", "status": "available"},
                ],
            },
        ],
    }
    cov = build_v21_variable_coverage_from_raw(raw)
    assert cov["by_macro"]["pace_control"]["available_derived"] == 1
    assert cov["totals"]["total"] == 2


def test_manifest_weights_unchanged_for_passes_completed():
    micro = _micro_spec("pace_control", "passes_completed")
    assert micro.micro_weight == 5


def test_micro_status_counts_available_includes_derived():
    assert micro_status_counts_available("available_derived")
    assert micro_status_counts_available("fallback_partial")
    assert not micro_status_counts_available("missing")


def test_build_lineup_history_empty_db():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    hist = build_lineup_history(db, team_id=1, prior_fixtures=[])
    assert hist["lineup_fixture_count"] == 0
