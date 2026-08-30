"""Test registry preset Pattern Lab + filtri signal_active / range V3.6 / fingerprint."""

from __future__ import annotations

from app.services.cecchino_data_lab.pattern_lab_filters import (
    parse_pattern_lab_filters,
    row_passes_filters,
)
from app.services.cecchino_data_lab.pattern_lab_presets import (
    FROZEN_SCIENTIFIC_FILTERS_SHA256,
    PATTERN_LAB_PRESETS,
    PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
    PRESET_REGISTRY_VERSION,
    derive_preset_status_group,
    list_pattern_lab_presets,
    preset_scientific_filters,
    scientific_filters_sha256,
)


def test_registry_has_p01_to_p12():
    ids = [p["id"] for p in PATTERN_LAB_PRESETS]
    assert ids == [f"P{i:02d}" for i in range(1, 13)]
    payload = list_pattern_lab_presets()
    assert payload["registry_version"] == PRESET_REGISTRY_VERSION
    assert PRESET_REGISTRY_VERSION == "pattern_lab_presets_v3"
    assert len(payload["presets"]) == 12


def test_p01_to_p05_scientific_filters_sha256_frozen():
    """Formule P01–P05 immutate: hash congelati prima di questo intervento."""
    for pid in ("P01", "P02", "P03", "P04", "P05"):
        p = next(x for x in PATTERN_LAB_PRESETS if x["id"] == pid)
        h = scientific_filters_sha256(preset_scientific_filters(p))
        assert h == FROZEN_SCIENTIFIC_FILTERS_SHA256[pid], pid


def test_p06_to_p12_scientific_filters_sha256_frozen():
    """Hash P06–P12 congelati prima della Run 2024/25."""
    for pid in ("P06", "P07", "P08", "P09", "P10", "P11", "P12"):
        p = next(x for x in PATTERN_LAB_PRESETS if x["id"] == pid)
        h = scientific_filters_sha256(preset_scientific_filters(p))
        assert h == FROZEN_SCIENTIFIC_FILTERS_SHA256[pid], pid


def test_p01_p05_status_after_oos_2023_24():
    by_id = {p["id"]: p for p in PATTERN_LAB_PRESETS}
    assert by_id["P01"]["status"] == "initial_replica_followup_negative"
    assert by_id["P03"]["status"] == "positive_oos_weakened"
    for pid in ("P02", "P04", "P05"):
        assert by_id[pid]["status"] == "failed_oos_2023_24"
    for pid in ("P06", "P07", "P08", "P09", "P10", "P11", "P12"):
        assert by_id[pid]["status"] == "candidate_oos_2024_25"
        assert by_id[pid]["first_oos_season"] == "2024/2025"
        assert by_id[pid]["discovery_seasons"] == [
            "2021/2022",
            "2022/2023",
            "2023/2024",
        ]


def test_status_group_derived_not_in_registry_source():
    for p in PATTERN_LAB_PRESETS:
        assert "status_group" not in p
    payload = list_pattern_lab_presets()
    for p in payload["presets"]:
        assert p["status_group"] == derive_preset_status_group(p["status"])
        assert p["scientific_filters_sha256"] == FROZEN_SCIENTIFIC_FILTERS_SHA256[p["id"]]


def test_preset_filters_have_no_quote_type_real():
    for p in PATTERN_LAB_PRESETS:
        f = preset_scientific_filters(p)
        assert f.get("quote_type") is None
        assert p.get("performance_quote_policy") == PERFORMANCE_QUOTE_POLICY_REAL_ONLY
        parsed = parse_pattern_lab_filters(f)
        assert parsed.get("quote_type") is None


def test_status_history_flags_not_in_scientific_filters():
    for p in PATTERN_LAB_PRESETS:
        f = preset_scientific_filters(p)
        for banned in (
            "status",
            "validation_history",
            "flags",
            "ui_badge",
            "performance_quote_policy",
            "scientific_filters_sha256",
        ):
            assert banned not in f


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


def test_p06_range_30_40_exclusive():
    p = next(x for x in PATTERN_LAB_PRESETS if x["id"] == "P06")
    f = parse_pattern_lab_filters(preset_scientific_filters(p))
    assert f["market_keys"] == ["DRAW"]
    assert f["goal_pillar_filters"]["offensive_production"]["class"] == "low"
    assert f["purchasability_v36_status"] == "score"
    assert f["purchasability_v36_min"] == 30.0
    assert f["purchasability_v36_max"] == 40.0
    assert f["purchasability_v36_max_exclusive"] is True

    base = {
        "market_key": "DRAW",
        "pre_goal_v4_compat_offensive_production_class": "low",
        "pre_purch_v36_status": "score",
        "pre_purch_v36_score": 30.0,
        "pre_rating": 40,
        "pre_value_positive": True,
    }
    assert row_passes_filters(base, f) is True
    assert row_passes_filters({**base, "pre_purch_v36_score": 39.999}, f) is True
    assert row_passes_filters({**base, "pre_purch_v36_score": 40.0}, f) is False
    assert row_passes_filters({**base, "pre_purch_v36_score": 29.9}, f) is False


def test_p06_to_p12_formulas_exact():
    by_id = {p["id"]: p for p in PATTERN_LAB_PRESETS}

    f06 = parse_pattern_lab_filters(preset_scientific_filters(by_id["P06"]))
    assert f06["market_keys"] == ["DRAW"]
    assert f06["goal_pillar_filters"] == {"offensive_production": {"class": "low"}}

    f07 = parse_pattern_lab_filters(preset_scientific_filters(by_id["P07"]))
    assert f07["market_keys"] == ["AWAY"]
    assert f07["goal_pillar_filters"]["offensive_production"]["class"] == "medium"
    assert f07["goal_pillar_filters"]["match_tempo"]["class"] == "very_low"

    f08 = parse_pattern_lab_filters(preset_scientific_filters(by_id["P08"]))
    assert f08["market_keys"] == ["AWAY"]
    assert f08["signal_active"] is True
    assert f08["goal_pillar_filters"]["match_tempo"]["class"] == "high"

    f09 = parse_pattern_lab_filters(preset_scientific_filters(by_id["P09"]))
    assert f09["market_keys"] == ["DRAW"]
    assert f09["goal_pillar_filters"]["offensive_production"]["class"] == "medium"
    assert f09["goal_pillar_filters"]["match_tempo"]["class"] == "low"

    f10 = parse_pattern_lab_filters(preset_scientific_filters(by_id["P10"]))
    assert f10["market_keys"] == ["AWAY"]
    assert f10["goal_final_class"] == "high"
    assert f10["goal_pillar_filters"]["match_tempo"]["class"] == "medium"
    assert by_id["P10"]["flags"]["high_variance"] is True
    assert by_id["P10"]["flags"]["longshot_pattern"] is True

    f11 = parse_pattern_lab_filters(preset_scientific_filters(by_id["P11"]))
    assert f11["market_keys"] == ["HOME"]
    assert f11["goal_final_class"] == "low"
    assert f11["goal_pillar_filters"]["offensive_production"]["class"] == "very_low"

    # P03 immutato; P12 = refinement metadata-only vs P03 + match_tempo high
    f03 = parse_pattern_lab_filters(preset_scientific_filters(by_id["P03"]))
    assert f03["market_keys"] == ["AWAY"]
    assert f03["signal_active"] is True
    assert f03["goal_pillar_filters"] == {"defensive_solidity": {"class": "medium"}}
    assert "match_tempo" not in f03["goal_pillar_filters"]

    f12 = parse_pattern_lab_filters(preset_scientific_filters(by_id["P12"]))
    assert f12["market_keys"] == ["AWAY"]
    assert f12["signal_active"] is True
    assert f12["goal_pillar_filters"]["defensive_solidity"]["class"] == "medium"
    assert f12["goal_pillar_filters"]["match_tempo"]["class"] == "high"
    assert by_id["P12"]["flags"]["low_sample"] is True
    assert by_id["P12"]["flags"]["refinement_pattern"] is True
    assert by_id["P12"]["flags"]["derived_from"] == "P03"
    assert "flags" not in preset_scientific_filters(by_id["P12"])


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
        README_FOR_AI_MD,
    )

    assert REPORT_SCHEMA_VERSION == "cecchino_lab_ai_report_v4"
    assert LEGACY_REPORT_SCHEMA_VERSION == "cecchino_lab_ai_report_v4"
    assert AI_SUMMARY_SCHEMA_VERSION == "cecchino_lab_ai_report_v5"
    assert V5 == "cecchino_lab_ai_report_v5"
    assert "Acquistabilità ufficiale = **solo V3**" not in AI_INSTRUCTIONS_V5_MD
    assert "Non usare V1.1/V2 né `purchasability_compatibility_json`" not in AI_INSTRUCTIONS_V5_MD
    assert "V3.6" in AI_INSTRUCTIONS_V5_MD
    assert "P01" in AI_INSTRUCTIONS_V5_MD
    assert "P06–P12" in README_FOR_AI_MD
    assert "low-sample refinement candidate" in README_FOR_AI_MD
    assert "first OOS 2024/25" in README_FOR_AI_MD
    assert "candidate_oos_2024_25" in README_FOR_AI_MD
    assert "scientific_filters_sha256" in AI_INSTRUCTIONS_V5_MD
    assert "pattern_lab_presets_v3" in README_FOR_AI_MD
