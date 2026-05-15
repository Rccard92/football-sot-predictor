"""Rilevamento placeholder e risoluzione v0.1 nel builder termini v1.0."""

from app.services.predictions_v10.explicit_terms_from_v04 import (
    DUPLICATE_VALUES_WARNING,
    PLACEHOLDER_REASON,
    build_explicit_v04_terms_from_saved_raw,
)


def _raw_v04_all_placeholder(comp_value: float = 3.49) -> dict:
    return {
        "offensive_production_component": {
            "value": comp_value,
            "weight_in_model": 0.30,
            "inputs": {},
            "fallbacks_used": [],
            "cap_applied": False,
        },
        "debug": {
            "baseline_other_inputs": {
                "opp_avg_sot_conceded": comp_value,
                "team_split_avg_sot_for": comp_value,
                "opp_split_avg_sot_conceded": comp_value,
                "team_last5_avg_sot_for": 3.6,
                "opp_last5_avg_sot_conceded": comp_value,
            },
        },
    }


def test_placeholder_resolved_from_v01_breakdown():
    raw_v04 = _raw_v04_all_placeholder()
    raw_v01 = {
        "calculation_breakdown": {
            "opponent_season_avg_sot_conceded": 4.12,
            "team_home_away_avg_sot_for": 3.8,
            "opponent_home_away_avg_sot_conceded": 3.5,
            "team_last5_avg_sot_for": 3.6,
            "opponent_last5_avg_sot_conceded": 3.2,
        },
    }
    terms, expected, quality = build_explicit_v04_terms_from_saved_raw(raw_v04, raw_v01=raw_v01)
    by_key = {t["key"]: t for t in terms}
    assert by_key["opp_avg_sot_conceded"]["value"] == 4.12
    assert by_key["opp_avg_sot_conceded"]["source_path"] == "calculation_breakdown.opponent_season_avg_sot_conceded"
    assert not by_key["opp_avg_sot_conceded"]["fallback_used"]
    assert all(t.get("source_path") for t in terms)
    assert expected != round(3.49 * (0.3 + 0.25 + 0.15 + 0.1 + 0.1 + 0.1), 2)


def test_placeholder_without_v01_marks_fallback():
    terms, _expected, quality = build_explicit_v04_terms_from_saved_raw(_raw_v04_all_placeholder())
    bo_terms = [t for t in terms if t["key"] != "offensive_production_component"]
    fallback_n = sum(1 for t in bo_terms if t["fallback_used"])
    assert fallback_n >= 4
    opp = next(t for t in terms if t["key"] == "opp_avg_sot_conceded")
    assert opp["fallback_reason"] == PLACEHOLDER_REASON
    assert DUPLICATE_VALUES_WARNING in quality.get("formula_quality_warnings", [])


def test_distinct_values_no_duplicate_warning():
    raw = {
        "offensive_production_component": {"value": 3.5, "fallbacks_used": [], "cap_applied": False},
        "debug": {
            "baseline_other_inputs": {
                "opp_avg_sot_conceded": 3.2,
                "team_split_avg_sot_for": 3.3,
                "opp_split_avg_sot_conceded": 3.1,
                "team_last5_avg_sot_for": 3.4,
                "opp_last5_avg_sot_conceded": 3.0,
            },
        },
    }
    _terms, _exp, quality = build_explicit_v04_terms_from_saved_raw(raw)
    assert DUPLICATE_VALUES_WARNING not in quality.get("formula_quality_warnings", [])
