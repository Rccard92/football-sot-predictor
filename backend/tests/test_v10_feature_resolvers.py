import pytest

from app.services.predictions_v10.explicit_terms_from_v04 import build_formula_payload_v10
from app.services.predictions_v10.v10_feature_resolvers import assess_formula_quality
from app.services.sot_feature_registry import ResolvedFeature
from app.services.sot_fixture_explanation_service import _components_v10_feature_registry


def _term(key: str, value: float, *, path: str = "db:test", fallback: bool = False) -> ResolvedFeature:
    return ResolvedFeature(
        key=key,
        label=key,
        value=value,
        contribution=round(value * 0.1, 4),
        weight=0.1,
        source_table="fixture_team_stats",
        source_field="shots_on_target",
        api_source="fixtures/statistics",
        source_path=path,
        sample_count=5,
        fallback_used=fallback,
        fallback_reason=None,
        status="available",
    )


def test_assess_formula_quality_ok_when_values_differ():
    terms = [
        _term("offensive_production_component", 3.1, path="v10:offensive_production_blend"),
        _term("opp_avg_sot_conceded", 4.2, path="opponent_season_avg_sot_conceded"),
        _term("team_split_avg_sot_for", 3.8, path="home_away_avg_sot_for"),
        _term("opp_split_avg_sot_conceded", 4.0, path="opponent_home_away_avg_sot_conceded"),
        _term("team_last5_avg_sot_for", 3.5, path="last5_avg_sot_for"),
        _term("opp_last5_avg_sot_conceded", 4.1, path="opponent_last5_avg_sot_conceded"),
    ]
    q = assess_formula_quality(terms)
    assert q["formula_quality_status"] == "ok"
    assert not q["formula_quality_warnings"]


def test_assess_formula_quality_warns_on_duplicate_values():
    terms = [
        _term("offensive_production_component", 3.49, path="a"),
        _term("opp_avg_sot_conceded", 3.49, path="b"),
        _term("team_split_avg_sot_for", 3.49, path="c"),
        _term("opp_split_avg_sot_conceded", 3.49, path="d"),
        _term("team_last5_avg_sot_for", 3.49, path="e"),
        _term("opp_last5_avg_sot_conceded", 3.49, path="f"),
    ]
    q = assess_formula_quality(terms)
    assert q["formula_quality_status"] == "needs_review"
    assert any("sospetti" in w.lower() or "coincidenti" in w.lower() for w in q["formula_quality_warnings"])


def test_build_formula_payload_v10_has_seven_terms():
    base = [
        {"key": "offensive_production_component", "label": "Off", "value": 3.0, "weight": 0.30, "contribution": 0.9},
        {"key": "opp_avg_sot_conceded", "label": "Opp", "value": 4.0, "weight": 0.25, "contribution": 1.0},
        {"key": "team_split_avg_sot_for", "label": "Split", "value": 3.5, "weight": 0.15, "contribution": 0.525},
        {"key": "opp_split_avg_sot_conceded", "label": "OS", "value": 3.6, "weight": 0.10, "contribution": 0.36},
        {"key": "team_last5_avg_sot_for", "label": "L5", "value": 3.7, "weight": 0.10, "contribution": 0.37},
        {"key": "opp_last5_avg_sot_conceded", "label": "OL5", "value": 3.8, "weight": 0.10, "contribution": 0.38},
    ]
    payload = build_formula_payload_v10(
        base,
        base_explicit_sot=3.535,
        xg_component={"xg_adjustment_applied": True, "xg_adjustment_sot": 0.12},
        final_sot=3.655,
    )
    assert len(payload["terms"]) == 7
    keys = {t["key"] for t in payload["terms"]}
    assert "expected_goals" in keys


def test_components_v10_feature_registry_structure():
    raw = {
        "architecture": "feature_registry_explicit_terms_plus_xg",
        "base_explicit_sot_before_xg": 3.5,
        "formula_quality_status": "ok",
        "offensive_production_component": {
            "value": 3.2,
            "weight_in_model": 0.30,
            "contribution": 0.96,
            "inputs": {
                "avg_sot_for": {
                    "label": "SOT medi",
                    "value": 4.0,
                    "weight": 0.35,
                    "contribution": 1.4,
                    "source_path": "fixture_team_stats",
                },
            },
        },
        "formula": {
            "terms": [
                {"key": "offensive_production_component", "label": "Off", "value": 3.2, "weight": 0.30, "contribution": 0.96},
                {"key": "opp_avg_sot_conceded", "label": "Opp", "value": 4.1, "weight": 0.25, "contribution": 1.025, "source_path": "opponent_season_avg_sot_conceded"},
                {"key": "team_split_avg_sot_for", "label": "Split", "value": 3.9, "weight": 0.15, "contribution": 0.585, "source_path": "home_away_avg_sot_for"},
                {"key": "opp_split_avg_sot_conceded", "label": "OS", "value": 3.7, "weight": 0.10, "contribution": 0.37, "source_path": "opponent_home_away_avg_sot_conceded"},
                {"key": "team_last5_avg_sot_for", "label": "L5", "value": 3.6, "weight": 0.10, "contribution": 0.36, "source_path": "last5_avg_sot_for"},
                {"key": "opp_last5_avg_sot_conceded", "label": "OL5", "value": 4.0, "weight": 0.10, "contribution": 0.40, "source_path": "opponent_last5_avg_sot_conceded"},
                {"key": "expected_goals", "label": "xG", "value": 1.2, "weight": 0.10, "contribution": 0.15},
            ],
        },
        "xg_component": {
            "xg_adjustment_applied": True,
            "team_avg_xg_for": 1.2,
            "opponent_avg_xg_conceded": 1.1,
            "xg_adjustment_sot": 0.15,
            "xg_adjustment_pct": 0.04,
        },
    }
    comps = _components_v10_feature_registry(raw, 3.65)
    ids = [c["id"] for c in comps]
    assert "v10_offensive_production" in ids
    assert "v10_explicit_weighted_sum" in ids
    assert "v10_xg_quality" in ids
    weighted = next(c for c in comps if c["id"] == "v10_explicit_weighted_sum")
    assert len(weighted["variables"]) == 5
    assert weighted["variables"][0]["value"] != weighted["variables"][1]["value"]
