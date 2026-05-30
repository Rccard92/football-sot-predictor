"""Test audit xG v2.0 vs v2.1 — detection e enrichment."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.fixture_team_stats_mapping import backfill_shot_columns_from_raw_json_if_null
from app.services.predictions_common.xg_strict_helpers import build_strict_xg_snapshot
from app.services.predictions_v11.shared_stats import expected_goals_from_team_stat
from app.services.predictions_v21.v21_audit_enrichment import enrich_v21_raw_for_audit
from app.services.predictions_v21.v21_feature_collectors import _collect_chance_quality
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS
from app.services.predictions_v21.v21_xg_coverage import resolve_league_xg_available


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


def _strict_ctx(*, team_xg=1.5, opp_xg=1.1, league_for=1.3, league_conc=1.2):
    team_fixtures = []
    opp_fixtures = []
    stats_map = {}
    ko = datetime(2026, 5, 1, tzinfo=timezone.utc)
    for i in range(8):
        fid = i + 1
        team_fixtures.append(SimpleNamespace(id=fid, home_team_id=1, away_team_id=99, kickoff_at=ko, goals_home=1, goals_away=0))
        stats_map[(fid, 1)] = _team_stat(expected_goals=team_xg)
        ofid = 100 + i
        opp_fixtures.append(SimpleNamespace(id=ofid, home_team_id=88, away_team_id=2, kickoff_at=ko, goals_home=0, goals_away=1))
        stats_map[(ofid, 88)] = _team_stat(expected_goals=opp_xg)
    league_baselines = {
        "league_avg_xg_for": league_for,
        "league_avg_xg_conceded": league_conc,
        "league_avg_sot_for": 4.0,
        "league_avg_sot_conceded": 4.0,
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
        team_agg={"xg_mean": team_xg, "xg_n": 8},
        opp_conceded_agg={"xg_mean": opp_xg, "xg_n": 8},
        strict_xg=strict_xg,
        xg_leakage_trace={"latest_fixture_used_at": "2026-05-20T18:00:00", "leakage_guard": True},
    )


def _chance_quality_micro(key: str):
    for macro in V21_MANIFEST_DEFINITIONS:
        if macro.key == "chance_quality":
            for m in macro.micros:
                if m.key == key:
                    return m
    raise KeyError(key)


def test_expected_goals_from_raw_json_statistics():
    st = SimpleNamespace(
        expected_goals=None,
        raw_json={
            "statistics": [
                {"type": "expected_goals", "value": "1.85"},
            ],
        },
    )
    val, src = expected_goals_from_team_stat(st)
    assert val == 1.85
    assert "raw_json" in src


def test_backfill_expected_goals_from_raw_json():
    row = SimpleNamespace(
        expected_goals=None,
        blocked_shots=1,
        shots_off_goal=2,
        raw_json={
            "statistics": [
                {"type": "expected goals", "value": "2.10"},
            ],
        },
    )
    backfill_shot_columns_from_raw_json_if_null(row)
    assert row.expected_goals == 2.10


def test_resolve_league_xg_available_from_team_agg():
    db = MagicMock()
    available = resolve_league_xg_available(
        db,
        competition_id=99,
        league_baselines={"league_avg_xg_for": None},
        team_agg={"xg_n": 3, "xg_mean": 1.2},
        opp_conceded_agg={"xg_n": 0},
    )
    assert available is True


def test_resolve_league_xg_available_from_competition_feed():
    db = MagicMock()
    with patch(
        "app.services.predictions_v21.v21_xg_coverage.competition_has_xg_in_team_stats",
        return_value=True,
    ):
        available = resolve_league_xg_available(
            db,
            competition_id=71,
            league_baselines={},
            team_agg={"xg_n": 0},
            opp_conceded_agg={"xg_n": 0},
        )
    assert available is True


def test_collect_chance_quality_uses_real_xg_when_available():
    micro = _chance_quality_micro("xg_produced")
    ctx = _strict_ctx()
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert result.raw_value == 1.5
    assert "fixture_team_stats.expected_goals" in result.source_path


def test_enrich_does_not_reclassify_when_components_have_real_xg():
    raw = {
        "base_anchor_sot": 4.72,
        "final_multiplier": 1.0,
        "predicted_sot": 4.72,
        "warnings": ["xG non disponibile nel feed importato."],
        "components": {
            "chance_quality": {
                "value": 1.05,
                "macro_index": 1.05,
                "status": "available",
                "inputs": {
                    "xg_produced": {
                        "raw_value": 1.5,
                        "value": 1.5,
                        "normalized_value": 1.08,
                        "status": "available",
                    },
                },
            },
        },
    }
    with patch(
        "app.services.predictions_v21.v21_audit_enrichment.competition_has_xg_in_team_stats",
        return_value=False,
    ):
        enriched = enrich_v21_raw_for_audit(raw, db=MagicMock(), competition_id=1)
    cq = enriched["components"]["chance_quality"]
    assert cq["inputs"]["xg_produced"]["status"] == "available"
    assert cq["status"] != "degraded_feed_unavailable"


def test_collect_chance_quality_all_micros_with_league_baselines():
    ctx = _strict_ctx()
    for key in (
        "xg_produced",
        "xg_conceded_by_opponent",
        "xg_delta_vs_league",
        "opp_xg_conceded_delta",
        "xg_prudent_adjustment",
    ):
        micro = _chance_quality_micro(key)
        result = _collect_chance_quality(ctx, micro)
        assert result.status == "available", key
        assert result.to_trace_input().get("leakage_guard") is True


def test_resolve_league_xg_coherent_with_feed_available():
    db = MagicMock()
    with patch(
        "app.services.predictions_v21.v21_xg_coverage.competition_has_xg_in_team_stats",
        return_value=True,
    ):
        available = resolve_league_xg_available(
            db,
            competition_id=2,
            league_baselines={"league_avg_xg_for": 1.2128},
            team_agg={"xg_n": 5, "xg_mean": 1.3},
            opp_conceded_agg={"xg_n": 5, "xg_mean": 1.2},
        )
    assert available is True


def test_enrich_reclassifies_only_when_feed_verified_absent():
    raw = {
        "base_anchor_sot": 4.72,
        "final_multiplier": 1.0,
        "predicted_sot": 4.72,
        "components": {
            "chance_quality": {
                "value": 1.0,
                "macro_index": 1.0,
                "status": "missing",
                "inputs": {
                    "xg_produced": {"value": None, "normalized_value": 1.0, "status": "missing"},
                    "xg_conceded_by_opponent": {"value": None, "normalized_value": 1.0, "status": "missing"},
                    "xg_delta_vs_league": {"value": None, "normalized_value": 1.0, "status": "missing"},
                    "opp_xg_conceded_delta": {"value": None, "normalized_value": 1.0, "status": "missing"},
                    "xg_prudent_adjustment": {"value": None, "normalized_value": 1.0, "status": "missing"},
                },
            },
        },
    }
    with patch(
        "app.services.predictions_v21.v21_audit_enrichment.competition_has_xg_in_team_stats",
        return_value=False,
    ):
        enriched = enrich_v21_raw_for_audit(raw, db=MagicMock(), competition_id=71)
    assert enriched["components"]["chance_quality"]["status"] == "degraded_feed_unavailable"
    assert enriched["components"]["chance_quality"]["inputs"]["xg_produced"]["status"] == "feed_unavailable"
    assert float(enriched["predicted_sot"]) == 4.72
