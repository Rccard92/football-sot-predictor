"""Test audit xG v2.0 vs v2.1 — detection e enrichment."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.fixture_team_stats_mapping import backfill_shot_columns_from_raw_json_if_null
from app.services.predictions_v11.shared_stats import expected_goals_from_team_stat
from app.services.predictions_v21.v21_audit_enrichment import enrich_v21_raw_for_audit
from app.services.predictions_v21.v21_feature_collectors import _collect_chance_quality
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS
from app.services.predictions_v21.v21_xg_coverage import resolve_league_xg_available


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
    ctx = SimpleNamespace(
        league_xg_available=True,
        league_baselines={"league_avg_xg_for": 1.3, "league_avg_xg_conceded": 1.2},
        team_agg={"xg_mean": 1.5, "xg_n": 8},
        opp_conceded_agg={"xg_mean": 1.1, "xg_n": 8},
        xg_leakage_trace={"latest_fixture_used_at": "2026-05-20T18:00:00", "leakage_guard": True},
    )
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "available"
    assert result.raw_value == 1.5
    assert result.source_path == "fixture_team_stats.expected_goals"


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
    ctx = SimpleNamespace(
        league_xg_available=True,
        league_baselines={"league_avg_xg_for": 1.3, "league_avg_xg_conceded": 1.2},
        team_agg={"xg_mean": 1.5, "xg_n": 8},
        opp_conceded_agg={"xg_mean": 1.1, "xg_n": 8},
        xg_leakage_trace={"latest_fixture_used_at": "2026-05-20T18:00:00", "leakage_guard": True},
    )
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
