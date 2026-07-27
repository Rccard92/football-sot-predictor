"""Test integrazione KPI explanations / comparison contract v2."""

from __future__ import annotations

from app.services.cecchino.cecchino_kpi_explanations import (
    ANALYZABLE_METRICS,
    _METRIC_LABELS,
    _explain_purchasability,
    _explain_purchasability_delta,
    _explain_purchasability_v2,
)
from app.services.cecchino.cecchino_purchasability_v2_snapshot import (
    build_purchasability_comparison,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY


def test_analyzable_metrics_include_v2_keys():
    assert "purchasability" in ANALYZABLE_METRICS
    assert "purchasability_v1_1" in ANALYZABLE_METRICS
    assert "purchasability_v2" in ANALYZABLE_METRICS
    assert "purchasability_delta" in ANALYZABLE_METRICS
    assert _METRIC_LABELS["purchasability"] == "Acquistabilità v1.1"
    assert _METRIC_LABELS["purchasability_v2"] == "Acquistabilità v2"


def test_explain_v1_1_alias_label():
    row = {"market_key": SEL_AWAY}
    expl = _explain_purchasability(
        row,
        "2",
        {"score": 64, "status": "available", "phase_1_score": 70, "phase_2_score": 58, "class": "Alta"},
        None,
        {
            "candidate_version": "cecchino_purchasability_v1_preview_candidate_2",
            "candidate_name": "balanced_geometric_v1_1",
        },
        metric_key="purchasability_v1_1",
    )
    assert expl["metric_key"] == "purchasability_v1_1"
    assert expl["metric_label"] == "Acquistabilità v1.1"
    assert expl["stored_result"] == 64


def test_explain_v2_and_delta():
    row = {"market_key": SEL_AWAY}
    v2 = _explain_purchasability_v2(
        row,
        "2",
        {
            "score": 72,
            "status": "available",
            "phase_1_score": 78,
            "phase_2_score": 66,
            "raw_pre_gate_score": 71.6,
            "class": "Alta",
            "positive_value_gate": {"status": "passed", "reason_codes": []},
        },
        {
            "candidate_version": "cecchino_purchasability_v2_candidate_1",
            "candidate_name": "decision_quality_v2",
            "phase_1_value": {"score": 78},
            "phase_2_quality": {"score": 66},
            "positive_value_gate": {"status": "passed", "reason_codes": []},
            "normalization_profile": {
                "version": "cecchino_purchasability_v2_norm_profile_2026_07_26_v1",
                "hash": "abc",
                "cutoff": "2026-07-26",
            },
            "raw_pre_gate_score": 71.6,
            "score": 72,
        },
        {
            "candidate_version": "cecchino_purchasability_v2_candidate_1",
            "normalization_profile_version": "cecchino_purchasability_v2_norm_profile_2026_07_26_v1",
            "normalization_profile_hash": "abc",
            "normalization_profile_cutoff": "2026-07-26",
        },
        comparison_item={
            "v1_1_score": 64,
            "v2_score": 72,
            "delta_v2_minus_v1_1": 8,
            "comparison_status": "available",
        },
    )
    assert v2["metric_key"] == "purchasability_v2"
    assert v2["stored_result"] == 72
    assert "normalization_profile" in v2
    assert "positive_value_gate" in v2

    delta = _explain_purchasability_delta(
        row,
        "2",
        {
            "v1_1_score": 64,
            "v2_score": 72,
            "delta_v2_minus_v1_1": 8,
            "comparison_status": "available",
        },
    )
    assert delta["stored_result"] == 8
    assert delta["stored_result_display"] == "+8"

    delta_neg = _explain_purchasability_delta(
        row,
        "2",
        {
            "v1_1_score": 70,
            "v2_score": 60,
            "delta_v2_minus_v1_1": -10,
            "comparison_status": "available",
        },
    )
    assert delta_neg["stored_result_display"] == "-10"

    delta_miss = _explain_purchasability_delta(
        row,
        "2",
        {
            "v1_1_score": 64,
            "v2_score": None,
            "delta_v2_minus_v1_1": None,
            "comparison_status": "partial",
        },
    )
    assert delta_miss["status"] in ("partial", "unavailable")


def test_comparison_helper():
    cmp = build_purchasability_comparison(
        {"items": [{"market_key": SEL_AWAY, "score": 64}]},
        {"items": [{"market_key": SEL_AWAY, "score": 72}]},
    )
    assert cmp["items"][SEL_AWAY]["delta_v2_minus_v1_1"] == 8
