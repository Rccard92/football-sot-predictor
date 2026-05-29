"""Manifest e trace baseline_v2_0_lineup_impact."""

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
)
from app.services.model_applied_variable_manifest import is_countable_role, manifest_for_model
from app.services.model_applied_variable_trace import build_applied_variable_trace_side


def _v11_raw_minimal() -> dict:
    return {
        "prediction_valid": True,
        "formula_quality_status": "ok",
        "formula": {
            "type": "weighted_components",
            "terms": [
                {
                    "key": "offensive_production_component",
                    "value": 4.0,
                    "weight": 0.25,
                    "contribution": 1.0,
                    "status": "available",
                },
                {
                    "key": "opponent_defensive_resistance_component",
                    "value": 3.5,
                    "weight": 0.22,
                    "contribution": 0.77,
                    "status": "available",
                },
                {
                    "key": "home_away_split_component",
                    "value": 3.8,
                    "weight": 0.13,
                    "contribution": 0.49,
                    "status": "available",
                },
                {
                    "key": "recent_form_component",
                    "value": 3.6,
                    "weight": 0.15,
                    "contribution": 0.54,
                    "status": "available",
                },
                {
                    "key": "xg_chance_quality_component",
                    "value": 3.5,
                    "weight": 0.12,
                    "contribution": 0.42,
                    "status": "available",
                },
                {
                    "key": "player_layer_component",
                    "value": 3.4,
                    "weight": 0.13,
                    "contribution": 0.44,
                    "status": "available",
                },
            ],
        },
        "offensive_production_component": {"value": 4.0, "quality": {"status": "ok"}},
        "opponent_defensive_resistance_component": {"value": 3.5, "quality": {"status": "ok"}},
        "home_away_split_component": {"value": 3.8, "quality": {"status": "ok"}},
        "recent_form_component": {"value": 3.6, "quality": {"status": "ok"}},
        "xg_chance_quality_component": {"value": 3.5, "quality": {"status": "ok"}},
        "player_layer_component": {"value": 3.4, "quality": {"status": "ok"}},
    }


def _v20_raw_full() -> dict:
    return {
        "base_v1_1_sot": 5.0,
        "offensive_lineup_factor": 0.95,
        "opponent_defensive_weakness_factor": 1.05,
        "predicted_sot": round(5.0 * 0.95 * 1.05, 3),
        "sportapi_lineups_available": True,
        "sportapi_lineup_confirmed": True,
        "lineup_impact_status": "full",
        "lineup_impact_confidence": "alta",
        "v11_base": _v11_raw_minimal(),
        "lineup_impact_side": {
            "offensive_lineup_factor": 0.95,
            "opponent_defensive_weakness_factor": 1.05,
            "defensive_weakness_factor": 1.0,
            "excluded_players": [],
            "player_mapping_quality": {
                "starters_total": 11,
                "starters_mapped": 10,
                "starters_auto_safe": 9,
                "starters_review": 1,
                "starters_no_match": 1,
                "average_match_score": 91.2,
                "mapped_with_stats": 9,
                "mapped_with_shooting_impact": 7,
                "mapping_confidence": 82,
                "mapping_quality_label": "good",
            },
        },
        "player_mapping_confidence": 82,
        "pre_match_readiness": {
            "sportapi_mapping": "ok",
            "lineup_freshness": "ok",
            "roster_sync": "ok",
            "player_mapping": "ok",
            "model_v20": "ready",
        },
        "formula": {
            "type": "lineup_impact_multiplicative",
            "terms": [
                {"key": "base_v1_1_sot", "value": 5.0, "status": "available"},
                {"key": "offensive_lineup_factor", "value": 0.95, "status": "available"},
                {"key": "opponent_defensive_weakness_factor", "value": 1.05, "status": "available"},
                {"key": "adjusted_sot", "value": round(5.0 * 0.95 * 1.05, 3), "status": "available"},
            ],
        },
    }


def test_v20_manifest_not_empty_includes_v11_and_lineup():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    assert len(specs) > len(manifest_for_model(BASELINE_SOT_MODEL_VERSION_V11_SOT))
    v20_formula = [s for s in specs if s.trace_key.startswith("v20_formula_")]
    assert len(v20_formula) == 4
    v11_terms = [s for s in specs if s.trace_key.startswith("v11_term_")]
    assert len(v11_terms) == 6


def test_v20_trace_formula_terms_with_values():
    raw = _v20_raw_full()
    trace = build_applied_variable_trace_side(
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        raw,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=12.0,
        prediction_confidence=None,
    )
    assert len(trace) > 0
    formula_final = [r for r in trace if r.get("application_role") == "direct_formula_component" and r.get("value") is not None]
    v20_formula = [r for r in formula_final if str(r.get("trace_key", "")).startswith("v20_formula_")]
    assert len(v20_formula) >= 3
    keys = {r["trace_key"] for r in v20_formula}
    assert "v20_formula_base_sot_v11" in keys
    assert "v20_formula_offensive_lineup_factor" in keys
    assert "v20_formula_opponent_defensive_weakness" in keys


def test_v20_trace_fallback_lineup_vars_missing_not_empty_manifest():
    raw = {
        "base_v1_1_sot": 4.2,
        "offensive_lineup_factor": 1.0,
        "opponent_defensive_weakness_factor": 1.0,
        "lineup_impact_status": "fallback_v11_only",
        "sportapi_lineups_available": False,
        "v11_base": _v11_raw_minimal(),
        "lineup_impact_side": {},
        "formula": {
            "type": "lineup_impact_multiplicative",
            "terms": [
                {"key": "base_v1_1_sot", "value": 4.2},
                {"key": "offensive_lineup_factor", "value": 1.0},
                {"key": "opponent_defensive_weakness_factor", "value": 1.0},
                {"key": "adjusted_sot", "value": 4.2},
            ],
        },
    }
    trace = build_applied_variable_trace_side(
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        raw,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=None,
        prediction_confidence=None,
    )
    assert len(trace) == len(manifest_for_model(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT))
    base_row = next(r for r in trace if r["trace_key"] == "v20_formula_base_sot_v11")
    assert base_row["value"] == 4.2
    status_row = next(r for r in trace if r["trace_key"] == "v20_context_lineup_impact_status")
    assert "fallback" in str(status_row.get("value") or "")


def test_v20_countable_roles_match_v11_plus_lineup():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    countable = [s for s in specs if is_countable_role(s.application_role)]
    assert len(countable) >= 40


def test_v20_trace_player_mapping_confidence_available():
    raw = _v20_raw_full()
    trace = build_applied_variable_trace_side(
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        raw,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=12.0,
        prediction_confidence=None,
    )
    row = next(r for r in trace if r["trace_key"] == "v20_quality_player_mapping_confidence")
    assert row["status"] == "available"
    assert row["value"] == 82
    assert row["unit"] == "punteggio"
    assert "Mapping giocatori buono" in str(row.get("notes") or "")


def test_v20_enrich_raw_for_trace_fills_mapping_confidence():
    from app.services.sportapi.lineup_player_profile_lookup import enrich_v20_raw_for_trace

    raw = {
        "base_v1_1_sot": 5.0,
        "sportapi_lineups_available": True,
        "lineup_impact_side": {},
    }
    lineup_impact = {
        "home": {
            "player_mapping_quality": {
                "starters_total": 11,
                "starters_mapped": 10,
                "starters_auto_safe": 9,
                "mapping_confidence": 82,
                "mapping_quality_label": "good",
            },
            "player_layer_usage": {"offensive_factor": 0.98, "final_factor": 0.98},
        }
    }
    enriched = enrich_v20_raw_for_trace(raw, lineup_impact, is_home=True)
    assert enriched["player_mapping_confidence"] == 82
    assert enriched["lineup_impact_side"]["player_mapping_quality"]["mapping_confidence"] == 82
    trace = build_applied_variable_trace_side(
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        enriched,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=12.0,
        prediction_confidence=None,
    )
    row = next(r for r in trace if r["trace_key"] == "v20_quality_player_mapping_confidence")
    assert row["status"] == "available"
    assert row["value"] == 82
