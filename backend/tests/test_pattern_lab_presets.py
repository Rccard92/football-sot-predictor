"""Test registry preset Pattern Lab + filtri signal_active / P05 range."""

from __future__ import annotations

from app.services.cecchino_data_lab.pattern_lab_filters import (
    parse_pattern_lab_filters,
    row_passes_filters,
)
from app.services.cecchino_data_lab.pattern_lab_presets import (
    PATTERN_LAB_PRESETS,
    PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
    PRESET_REGISTRY_VERSION,
    list_pattern_lab_presets,
    preset_scientific_filters,
)


def test_registry_has_p01_to_p05():
    ids = [p["id"] for p in PATTERN_LAB_PRESETS]
    assert ids == ["P01", "P02", "P03", "P04", "P05"]
    payload = list_pattern_lab_presets()
    assert payload["registry_version"] == PRESET_REGISTRY_VERSION
    assert len(payload["presets"]) == 5


def test_p01_validated_others_candidate():
    by_id = {p["id"]: p for p in PATTERN_LAB_PRESETS}
    assert by_id["P01"]["status"] == "validated_2_seasons"
    for pid in ("P02", "P03", "P04", "P05"):
        assert by_id[pid]["status"] == "candidate_oos_2023_24"
        assert by_id[pid]["first_oos_season"] == "2023/2024"


def test_preset_filters_have_no_quote_type_real():
    for p in PATTERN_LAB_PRESETS:
        f = preset_scientific_filters(p)
        assert f.get("quote_type") is None
        assert p.get("performance_quote_policy") == PERFORMANCE_QUOTE_POLICY_REAL_ONLY
        parsed = parse_pattern_lab_filters(f)
        assert parsed.get("quote_type") is None


def test_p01_filters_exact():
    p = next(x for x in PATTERN_LAB_PRESETS if x["id"] == "P01")
    f = parse_pattern_lab_filters(preset_scientific_filters(p))
    assert f["market_keys"] == ["HOME"]
    assert f["goal_pillar_filters"]["offensive_stability"]["class"] == "high"
    assert f["eligibility"] == "eligible_core"
    assert f["market_informative"] is True


def test_p03_signal_active_filter():
    p = next(x for x in PATTERN_LAB_PRESETS if x["id"] == "P03")
    f = parse_pattern_lab_filters(preset_scientific_filters(p))
    assert f["signal_active"] is True
    assert f["market_keys"] == ["AWAY"]
    assert f["goal_pillar_filters"]["defensive_solidity"]["class"] == "medium"

    row_on = {
        "pre_signal_active": True,
        "market_key": "AWAY",
        "pre_goal_v4_compat_defensive_solidity_class": "medium",
        "pre_rating": 40,
        "pre_value_positive": True,
    }
    row_off = {**row_on, "pre_signal_active": False}
    # market_informative true: need kpi/signals/v36 — signal_active alone is signals informative
    assert row_passes_filters(row_on, f) is True
    assert row_passes_filters(row_off, f) is False


def test_signal_active_not_confused_with_count():
    f = parse_pattern_lab_filters({"signal_active": True, "market_informative": False})
    row = {"pre_signal_active": False, "pre_signal_count": 5}
    assert row_passes_filters(row, f) is False
    row2 = {"pre_signal_active": True, "pre_signal_count": 0}
    assert row_passes_filters(row2, f) is True


def test_p05_range_40_60_exclusive():
    p = next(x for x in PATTERN_LAB_PRESETS if x["id"] == "P05")
    f = parse_pattern_lab_filters(preset_scientific_filters(p))
    assert f["purchasability_v36_min"] == 40.0
    assert f["purchasability_v36_max"] == 60.0
    assert f["purchasability_v36_max_exclusive"] is True
    assert f["purchasability_v36_status"] == "score"

    base = {
        "market_key": "AWAY",
        "pre_purch_v36_status": "score",
        "pre_purch_v36_score": 40.0,
        "pre_rating": 40,
        "pre_value_positive": True,
    }
    assert row_passes_filters(base, f) is True
    assert row_passes_filters({**base, "pre_purch_v36_score": 59.9}, f) is True
    assert row_passes_filters({**base, "pre_purch_v36_score": 60.0}, f) is False
    assert row_passes_filters({**base, "pre_purch_v36_score": 39.9}, f) is False


def test_global_max_still_inclusive_by_default():
    f = parse_pattern_lab_filters(
        {
            "purchasability_v36_max": 60,
            "market_informative": False,
        }
    )
    assert f["purchasability_v36_max_exclusive"] is False
    row = {"pre_purch_v36_score": 60.0}
    assert row_passes_filters(row, f) is True
    row2 = {"pre_purch_v36_score": 60.1}
    assert row_passes_filters(row2, f) is False


def test_ai_summary_schema_constants_separated():
    from app.services.cecchino_data_lab.historical_ai_report import (
        AI_SUMMARY_SCHEMA_VERSION,
        LEGACY_REPORT_SCHEMA_VERSION,
        REPORT_SCHEMA_VERSION,
    )
    from app.services.cecchino_data_lab.pattern_lab_ai_summary import (
        AI_SUMMARY_SCHEMA_VERSION as V5,
        AI_INSTRUCTIONS_V5_MD,
    )

    assert REPORT_SCHEMA_VERSION == "cecchino_lab_ai_report_v4"
    assert LEGACY_REPORT_SCHEMA_VERSION == "cecchino_lab_ai_report_v4"
    assert AI_SUMMARY_SCHEMA_VERSION == "cecchino_lab_ai_report_v5"
    assert V5 == "cecchino_lab_ai_report_v5"
    assert "Acquistabilità ufficiale = **solo V3**" not in AI_INSTRUCTIONS_V5_MD
    assert "Non usare V1.1/V2 né `purchasability_compatibility_json`" not in AI_INSTRUCTIONS_V5_MD
    assert "V3.6" in AI_INSTRUCTIONS_V5_MD
    assert "P01" in AI_INSTRUCTIONS_V5_MD
