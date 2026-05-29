"""Test audit enrichment v2.1 (patch 2.1.10)."""

from __future__ import annotations

from app.services.predictions_v21.v21_audit_enrichment import enrich_v21_raw_for_audit
from app.services.predictions_v21.v21_feature_collectors import _collect_chance_quality
from app.services.predictions_v21.v21_lineup_impact_helpers import (
    injuries_top_shooter_absence_score,
    player_layer_top_shooter_absence_score,
)
from app.services.predictions_v21.v21_macro_aggregators import aggregate_v21_macro_score
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS
from app.services.predictions_v21.v21_normalization import neutral_micro
from app.services.sot_fixture_explanation_service import _build_formula_breakdown_v21, _categorize_trace_missing


def _chance_quality_macro():
    for m in V21_MANIFEST_DEFINITIONS:
        if m.key == "chance_quality":
            return m
    raise KeyError("chance_quality")


def test_xg_micro_feed_unavailable():
    micro = _chance_quality_macro().micros[0]
    from types import SimpleNamespace

    ctx = SimpleNamespace(league_xg_available=False, league_baselines={}, team_agg={}, opp_conceded_agg={})
    result = _collect_chance_quality(ctx, micro)
    assert result.status == "feed_unavailable"
    assert result.source_path == "feed_unavailable.xg"
    assert result.normalized_value == 1.0
    assert result.fallback_used is True
    assert "feed" in (result.warning or "").lower()


def test_chance_quality_macro_degraded_feed_unavailable():
    macro = _chance_quality_macro()
    micros = [
        neutral_micro(
            key=m.key,
            label=m.label,
            micro_weight=m.micro_weight,
            source_path="feed_unavailable.xg",
            status="feed_unavailable",
            fallback_used=True,
            warning="xG non disponibile nel feed importato.",
        )
        for m in macro.micros
    ]
    result = aggregate_v21_macro_score(macro, micros)
    assert result.status == "degraded_feed_unavailable"
    assert result.macro_index == 1.0
    assert result.coverage_pct == 0.0


def test_enrich_v21_raw_reclassifies_xg_missing():
    raw = {
        "base_anchor_sot": 4.72,
        "final_multiplier": 1.0,
        "predicted_sot": 4.72,
        "warnings": ["xG non disponibile nel feed importato."],
        "components": {
            "chance_quality": {
                "value": 1.0,
                "macro_index": 1.0,
                "macro_weight": 17,
                "status": "missing",
                "inputs": {
                    "xg_produced": {
                        "value": None,
                        "normalized_value": 1.0,
                        "status": "missing",
                        "warning": "xG non disponibile nel feed importato.",
                    },
                    "xg_conceded_by_opponent": {
                        "value": None,
                        "normalized_value": 1.0,
                        "status": "missing",
                        "warning": "xG non disponibile nel feed importato.",
                    },
                    "xg_delta_vs_league": {
                        "value": None,
                        "normalized_value": 1.0,
                        "status": "missing",
                        "warning": "xG non disponibile nel feed importato.",
                    },
                    "opp_xg_conceded_delta": {
                        "value": None,
                        "normalized_value": 1.0,
                        "status": "missing",
                        "warning": "xG non disponibile nel feed importato.",
                    },
                    "xg_prudent_adjustment": {
                        "value": None,
                        "normalized_value": 1.0,
                        "status": "missing",
                        "warning": "xG non disponibile nel feed importato.",
                    },
                },
            },
        },
    }
    enriched = enrich_v21_raw_for_audit(raw, db=None, competition_id=None)
    cq = enriched["components"]["chance_quality"]
    assert cq["status"] == "degraded_feed_unavailable"
    assert enriched["components"]["chance_quality"]["inputs"]["xg_produced"]["status"] == "feed_unavailable"
    assert float(enriched["base_anchor_sot"]) == 4.72
    assert float(enriched["final_multiplier"]) == 1.0


def test_enrich_preserves_sot_values():
    raw = {
        "base_anchor_sot": 3.5,
        "final_multiplier": 1.02,
        "predicted_sot": 3.57,
        "components": {},
    }
    enriched = enrich_v21_raw_for_audit(raw)
    assert enriched["base_anchor_sot"] == 3.5
    assert enriched["final_multiplier"] == 1.02
    assert enriched["predicted_sot"] == 3.57


def test_formula_breakdown_v21_extended():
    raw = {
        "base_anchor_sot": 4.72,
        "final_multiplier": 1.0,
        "anchor_breakdown": {"team_sot_avg": 4.8, "opponent_sot_conceded_avg": 4.63},
        "components": {
            "offensive_production": {
                "macro_index": 1.02,
                "macro_weight": 16,
                "value": 1.02,
                "status": "available",
                "warnings": [],
                "inputs": {},
            },
            "chance_quality": {
                "macro_index": 1.0,
                "macro_weight": 17,
                "value": 1.0,
                "status": "degraded_feed_unavailable",
                "warnings": ["Macroarea neutralizzata: dati xG non disponibili nel feed."],
                "inputs": {
                    "xg_produced": {"status": "feed_unavailable", "normalized_value": 1.0},
                },
            },
        },
    }
    fb = _build_formula_breakdown_v21(raw, 4.72)
    assert fb.get("macro_areas_table")
    assert len(fb["macro_areas_table"]) == 9
    assert fb.get("anchor_breakdown_table")
    assert fb.get("v21_coverage_summary")
    assert "4.72" in fb["formula_numeric"]


def test_categorize_trace_missing():
    trace = [
        {"key": "v21_micro_a", "status": "missing"},
        {"key": "v21_micro_b", "status": "feed_unavailable", "value": 1.0},
        {"key": "v21_macro_c", "status": "degraded_feed_unavailable", "value": 1.0},
        {"key": "v21_micro_d", "status": "not_tracked_yet"},
    ]
    cats = _categorize_trace_missing(trace)
    assert "v21_micro_a" in cats["missing_real"]
    assert "v21_micro_b" in cats["feed_unavailable"]
    assert "v21_macro_c" in cats["fallback_neutral"]


def test_player_vs_injuries_top_shooter_different():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.sportapi.lineup_player_profile_lookup import LineupProfileEntry

    entry = LineupProfileEntry(
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
    )
    ctx = SimpleNamespace(
        sportapi_audit={"available": True},
        sportapi_side={
            "starters": [{"provider_player_id": 1, "player_name": "A"}],
            "substitutes": [],
            "missing_players": {"injured": [{"provider_player_id": 2, "player_name": "B"}]},
        },
        profile_entries=[entry],
    )
    player_score = player_layer_top_shooter_absence_score(ctx, [entry])
    injury_score = injuries_top_shooter_absence_score(ctx, [entry])
    assert player_score is not None and player_score > 0
    assert injury_score is not None and injury_score > 0
