"""Test candidato Acquistabilità Fase 3 — formula, casi, audit."""

from __future__ import annotations

import ast
import importlib
import json
import math
from pathlib import Path

import pytest

from app.services.cecchino.cecchino_purchasability_candidate import (
    ACTIVE_PURCHASABILITY_CANDIDATE_NAME,
    ACTIVE_PURCHASABILITY_CANDIDATE_VERSION,
    PHASE_1_FORMULA_VERSION,
    PHASE_2_FORMULA_VERSION,
    PURCHASABILITY_CANDIDATE_NAME,
    PURCHASABILITY_CANDIDATE_REGISTRY,
    PURCHASABILITY_CANDIDATE_V1_VERSION,
    PURCHASABILITY_CANDIDATE_V2_VERSION,
    PURCHASABILITY_CANDIDATE_VERSION,
    audit_candidate_independence,
    calculate_purchasability_candidate_batch,
    calculate_purchasability_candidate_item,
    compare_purchasability_combiners,
    map_score_to_class,
    round_purchasability_score_half_up,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
)


def _base_dq(**kw):
    base = {
        "today_fixture_id": 1,
        "snapshot_timestamp_verified": True,
        "snapshot_before_kickoff": True,
        "pre_match_only": True,
        "no_post_match_features": True,
        "contains_settlement_fields": False,
        "contains_result_fields": False,
    }
    base.update(kw)
    return base


def _feature_item(
    *,
    market_key=SEL_HOME,
    feature_status="ready",
    prob_cecchino=0.50,
    edge_pct=20.0,
    rating=70,
    score_acquisto=0.1,
    model_context_probability=0.55,
    opposition_pressure_model=0.30,
    opposition_pressure_book=0.30,
    favourite_alignment="aligned",
    favourite_intensity_book=0.40,
    book_favourite_selection=SEL_AWAY,
    comparator_selections=None,
    absolute_model_book_gap=0.05,
    model_book_gap=0.05,
    gap_direction="positive",
    data_quality=None,
    **extra_inputs,
):
    comps = comparator_selections
    if comps is None:
        comps = [SEL_DRAW, SEL_AWAY]
    inputs = {
        "prob_cecchino": prob_cecchino,
        "edge_pct": edge_pct,
        "rating": rating,
        "score_acquisto": score_acquisto,
        "vantaggio_prob": 0.1,
        "rating_label": "Buona",
    }
    inputs.update(extra_inputs)
    return {
        "version": "cecchino_purchasability_v1_preview_contract",
        "feature_version": "cecchino_purchasability_features_v1",
        "feature_status": feature_status,
        "status": "not_calculated",
        "score": None,
        "class": None,
        "reading": None,
        "market_key": market_key,
        "selection": market_key,
        "phase_1_value": {
            "status": "available",
            "score": None,
            "inputs": inputs,
        },
        "phase_2_quality": {
            "status": "available",
            "score": None,
            "model_context_probability": model_context_probability,
            "opposition_pressure_model": opposition_pressure_model,
            "opposition_pressure_book": opposition_pressure_book,
            "favourite_alignment": favourite_alignment,
            "favourite_intensity_book": favourite_intensity_book,
            "book_favourite": {
                "selection": book_favourite_selection,
                "implied_prob": favourite_intensity_book,
            },
            "comparator_selections": comps,
            "absolute_model_book_gap": absolute_model_book_gap,
            "model_book_gap": model_book_gap,
            "gap_direction": gap_direction,
        },
        "context_hooks": {
            "balance_v5": {"status": "available_not_used"},
            "goal_intensity_v5": {"status": "available_not_used"},
        },
        "reason_codes": ["purchasability_score_formula_not_implemented"],
        "data_quality": data_quality or _base_dq(),
    }


# --- §19 Phase 1 ---


def test_phase1_prob_50_edge_20():
    item = calculate_purchasability_candidate_item(
        _feature_item(prob_cecchino=0.50, edge_pct=20.0)
    )
    p1 = item["phase_1_value"]
    assert p1["probability_strength_score"] == 50.0
    assert p1["edge_value_score"] == 100.0
    assert p1["score"] == pytest.approx(70.71, abs=0.01)
    assert p1["formula_version"] == PHASE_1_FORMULA_VERSION


def test_phase1_edge_zero():
    item = calculate_purchasability_candidate_item(
        _feature_item(edge_pct=0.0)
    )
    assert item["phase_1_value"]["score"] == 0.0
    assert "no_positive_value_detected" in item["phase_1_value"]["reason_codes"]


def test_phase1_edge_negative():
    item = calculate_purchasability_candidate_item(
        _feature_item(edge_pct=-5.0)
    )
    assert item["phase_1_value"]["score"] == 0.0


def test_phase1_edge_capped():
    item = calculate_purchasability_candidate_item(
        _feature_item(edge_pct=40.0)
    )
    assert item["phase_1_value"]["edge_value_score"] == 100.0


def test_phase1_rating_ignored():
    a = calculate_purchasability_candidate_item(
        _feature_item(rating=50, score_acquisto=0.01)
    )
    b = calculate_purchasability_candidate_item(
        _feature_item(rating=95, score_acquisto=0.99)
    )
    assert a["phase_1_value"]["score"] == b["phase_1_value"]["score"]
    assert a["score"] == b["score"]


def test_phase1_no_historical_reliability_import():
    mod = importlib.import_module(
        "app.services.cecchino.cecchino_purchasability_candidate"
    )
    src = Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "historical_reliability" not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "historical_reliability" not in (alias.name or "")


# --- §20 Phase 2 ---


def test_phase2_model_support_above_50():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            model_context_probability=0.60,
            opposition_pressure_model=0.30,
        )
    )
    cs = item["phase_2_quality"]["component_scores"]
    assert cs["model_opposition_support"] > 50


def test_phase2_model_support_below_50():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            model_context_probability=0.30,
            opposition_pressure_model=0.55,
        )
    )
    assert item["phase_2_quality"]["component_scores"][
        "model_opposition_support"
    ] < 50


def test_phase2_book_resistance_75():
    item = calculate_purchasability_candidate_item(
        _feature_item(opposition_pressure_book=0.75)
    )
    assert item["phase_2_quality"]["component_scores"][
        "book_opposition_resistance"
    ] == 25.0


def test_phase2_book_resistance_20():
    item = calculate_purchasability_candidate_item(
        _feature_item(opposition_pressure_book=0.20)
    )
    assert item["phase_2_quality"]["component_scores"][
        "book_opposition_resistance"
    ] == 80.0


def test_phase2_opposite_favourite_intensity():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            book_favourite_selection=SEL_AWAY,
            comparator_selections=[SEL_DRAW, SEL_AWAY],
            favourite_intensity_book=0.60,
        )
    )
    assert item["phase_2_quality"]["component_scores"][
        "opposite_favourite_intensity"
    ] == 40.0


def test_phase2_favourite_not_comparator():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            market_key=SEL_ONE_X,
            book_favourite_selection=SEL_HOME,
            comparator_selections=[SEL_AWAY],
            favourite_intensity_book=0.80,
        )
    )
    assert item["phase_2_quality"]["component_scores"][
        "opposite_favourite_intensity"
    ] == 100.0


def test_phase2_alignment_aligned():
    item = calculate_purchasability_candidate_item(
        _feature_item(favourite_alignment="aligned")
    )
    assert item["phase_2_quality"]["component_scores"][
        "favourite_alignment"
    ] == 100.0


def test_phase2_alignment_disagree():
    item = calculate_purchasability_candidate_item(
        _feature_item(favourite_alignment="disagree")
    )
    assert item["phase_2_quality"]["component_scores"][
        "favourite_alignment"
    ] == 50.0


def test_phase2_large_gap_no_score_change():
    a = calculate_purchasability_candidate_item(
        _feature_item(absolute_model_book_gap=0.02, model_book_gap=0.02)
    )
    b = calculate_purchasability_candidate_item(
        _feature_item(
            absolute_model_book_gap=0.25,
            model_book_gap=0.25,
            gap_direction="positive",
        )
    )
    assert a["phase_2_quality"]["score"] == b["phase_2_quality"]["score"]
    assert "model_materially_above_book" in b["phase_2_quality"]["reason_codes"]
    assert b["phase_2_quality"]["large_gap_is_automatic_penalty"] is False


def test_phase2_optional_missing_renormalize():
    feat = _feature_item(favourite_alignment="unavailable")
    item = calculate_purchasability_candidate_item(feat)
    p2 = item["phase_2_quality"]
    assert p2["status"] == "partial"
    assert "favourite_alignment" in p2["missing_components"]
    assert "favourite_alignment" not in p2["applied_weights"]
    assert abs(sum(p2["applied_weights"].values()) - 1.0) < 0.02
    assert p2["score"] is not None


def test_phase2_required_missing_null():
    feat = _feature_item()
    feat["phase_2_quality"]["opposition_pressure_book"] = None
    item = calculate_purchasability_candidate_item(feat)
    assert item["phase_2_quality"]["score"] is None
    assert item["status"] == "unavailable"
    assert item["score"] is None


# --- §21 Combiners ---


def test_combiner_geometric_80_20():
    c = compare_purchasability_combiners(phase_1_score=80, phase_2_score=20)
    assert c["geometric"] == pytest.approx(40.0)
    assert c["official"] == "geometric"
    assert c["production_candidate"] == PURCHASABILITY_CANDIDATE_NAME


def test_combiner_geometric_60_60():
    c = compare_purchasability_combiners(phase_1_score=60, phase_2_score=60)
    assert c["geometric"] == pytest.approx(60.0)


def test_combiner_phase1_zero():
    item = calculate_purchasability_candidate_item(_feature_item(edge_pct=0))
    assert item["score"] == 0


def test_combiner_ordering():
    c = compare_purchasability_combiners(phase_1_score=80, phase_2_score=20)
    assert c["harmonic"] <= c["geometric"] <= c["arithmetic"]


def test_only_geometric_feeds_official_score():
    item = calculate_purchasability_candidate_item(_feature_item())
    fc = item["final_combination"]
    assert fc["official"] == "geometric"
    assert item["score"] == fc["rounded_final_score"]
    assert item["score"] == int(round(fc["geometric"]))
    # arithmetic/harmonic differ when p1 != p2, but class from geometric only
    assert item["class"] == map_score_to_class(item["score"])


# --- §22 Casi A–H ---


def test_caso_a_weak_opposition_beats_strong():
    weak = calculate_purchasability_candidate_item(
        _feature_item(opposition_pressure_book=0.20, opposition_pressure_model=0.20)
    )
    strong = calculate_purchasability_candidate_item(
        _feature_item(opposition_pressure_book=0.75, opposition_pressure_model=0.55)
    )
    assert weak["score"] > strong["score"]


def test_caso_b_higher_edge_higher_score():
    low = calculate_purchasability_candidate_item(_feature_item(edge_pct=5.0))
    high = calculate_purchasability_candidate_item(_feature_item(edge_pct=18.0))
    assert high["score"] > low["score"]


def test_caso_c_disagree_no_auto_zero():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            favourite_alignment="disagree",
            opposition_pressure_book=0.25,
            opposition_pressure_model=0.25,
        )
    )
    assert item["score"] is not None and item["score"] > 0
    assert item["phase_2_quality"]["large_gap_is_automatic_penalty"] is False


def test_caso_d_strong_comparator_reduces_not_disagree():
    disagree_weak = calculate_purchasability_candidate_item(
        _feature_item(
            favourite_alignment="disagree",
            opposition_pressure_book=0.25,
        )
    )
    disagree_strong = calculate_purchasability_candidate_item(
        _feature_item(
            favourite_alignment="disagree",
            opposition_pressure_book=0.80,
            book_favourite_selection=SEL_AWAY,
            favourite_intensity_book=0.80,
        )
    )
    assert disagree_strong["score"] < disagree_weak["score"]


def test_caso_e_same_rating_different_context():
    a = calculate_purchasability_candidate_item(
        _feature_item(rating=70, opposition_pressure_book=0.20)
    )
    b = calculate_purchasability_candidate_item(
        _feature_item(rating=70, opposition_pressure_book=0.80)
    )
    assert a["score"] != b["score"]


def test_caso_f_different_rating_same_active_inputs():
    a = calculate_purchasability_candidate_item(
        _feature_item(rating=40, score_acquisto=0.01)
    )
    b = calculate_purchasability_candidate_item(
        _feature_item(rating=90, score_acquisto=0.50)
    )
    assert a["score"] == b["score"]
    assert a["phase_1_value"]["score"] == b["phase_1_value"]["score"]


def test_caso_g_historical_reliability_absent():
    item = calculate_purchasability_candidate_item(_feature_item())
    assert item["score_metadata"]["historical_reliability_used"] is False
    assert item["phase_1_value"]["historical_reliability_used"] is False


def test_caso_h_unsupported_market():
    item = calculate_purchasability_candidate_item(
        _feature_item(market_key=SEL_OVER_1_5)
    )
    assert item["status"] == "unavailable"
    assert item["score"] is None
    assert item["class"] is None
    assert "opposition_context_not_supported" in item["reason_codes"]


# --- §23 Data quality ---


def test_dq_verified_available():
    item = calculate_purchasability_candidate_item(
        _feature_item(feature_status="ready", data_quality=_base_dq())
    )
    assert item["status"] == "available"
    assert item["calculation_quality"] == "full"
    assert item["score"] is not None


def test_dq_unverified_partial():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            feature_status="partial",
            data_quality=_base_dq(snapshot_timestamp_verified=False),
        )
    )
    assert item["status"] == "partial"
    assert item["calculation_quality"] == "partial"
    assert item["score"] is not None


def test_dq_post_kickoff_unavailable():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            feature_status="unavailable",
            data_quality=_base_dq(snapshot_before_kickoff=False),
        )
    )
    assert item["status"] == "unavailable"
    assert item["score"] is None


def test_dq_no_settlement_fields():
    item = calculate_purchasability_candidate_item(_feature_item())
    dq = item["data_quality"]
    assert dq["contains_settlement_fields"] is False
    assert dq["contains_result_fields"] is False
    assert dq["pre_match_only"] is True


def test_dq_strict_json():
    batch = calculate_purchasability_candidate_batch(
        {
            "today_fixture_id": 1,
            "items": [_feature_item(), _feature_item(market_key=SEL_DRAW)],
        }
    )
    json.dumps(batch, allow_nan=False)


def test_batch_summary_and_flags():
    batch = calculate_purchasability_candidate_batch(
        {
            "today_fixture_id": 9,
            "items": [
                _feature_item(market_key=SEL_HOME),
                _feature_item(market_key=SEL_OVER_1_5),
            ],
        }
    )
    assert batch["candidate_version"] == PURCHASABILITY_CANDIDATE_V2_VERSION
    assert batch["candidate_name"] == ACTIVE_PURCHASABILITY_CANDIDATE_NAME
    assert batch["active_candidate_version"] == PURCHASABILITY_CANDIDATE_V2_VERSION
    assert batch["historical_reliability_used"] is False
    assert batch["rating_used_as_weight"] is False
    assert batch["ui_integration"] is True
    assert batch["db_persistence"] is True
    assert batch["summary"]["total"] == 2
    assert batch["summary"]["unavailable"] >= 1


def test_registry_frozen():
    assert PURCHASABILITY_CANDIDATE_V1_VERSION in PURCHASABILITY_CANDIDATE_REGISTRY
    assert PURCHASABILITY_CANDIDATE_V2_VERSION in PURCHASABILITY_CANDIDATE_REGISTRY
    assert ACTIVE_PURCHASABILITY_CANDIDATE_VERSION == PURCHASABILITY_CANDIDATE_V2_VERSION
    assert PURCHASABILITY_CANDIDATE_VERSION == PURCHASABILITY_CANDIDATE_V2_VERSION
    entry = PURCHASABILITY_CANDIDATE_REGISTRY[PURCHASABILITY_CANDIDATE_V2_VERSION]
    assert entry["name"] == ACTIVE_PURCHASABILITY_CANDIDATE_NAME
    assert entry["status"] == "active_preview"
    with pytest.raises(TypeError):
        entry["name"] = "mutated"  # type: ignore[index]
    with pytest.raises(TypeError):
        entry["configured_weights"]["model_opposition_support"] = 0.99  # type: ignore[index]
    with pytest.raises(TypeError):
        PURCHASABILITY_CANDIDATE_REGISTRY["x"] = {}  # type: ignore[index]
    v1 = PURCHASABILITY_CANDIDATE_REGISTRY[PURCHASABILITY_CANDIDATE_V1_VERSION]
    assert v1["status"] == "frozen_preview"
    assert v1["rounding_policy"] == "python_round_legacy"
    assert v1["superseded_by"] == PURCHASABILITY_CANDIDATE_V2_VERSION


def test_round_half_up_thresholds():
    assert round_purchasability_score_half_up(19.49) == 19
    assert round_purchasability_score_half_up(19.50) == 20
    assert round_purchasability_score_half_up(39.50) == 40
    assert round_purchasability_score_half_up(59.50) == 60
    assert round_purchasability_score_half_up(79.50) == 80
    assert round_purchasability_score_half_up(99.50) == 100
    assert round_purchasability_score_half_up(-5) == 0
    assert round_purchasability_score_half_up(150) == 100
    assert map_score_to_class(round_purchasability_score_half_up(19.50)) == "Bassa"


def test_reading_phase1_zero_favorable():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            edge_pct=0,
            model_context_probability=0.70,
            opposition_pressure_model=0.25,
            opposition_pressure_book=0.25,
            favourite_alignment="aligned",
        )
    )
    assert item["score"] == 0
    assert item["class"] == "Molto Bassa"
    assert item["phase_2_quality"]["score"] is not None
    assert item["phase_2_quality"]["score"] >= 60
    assert "valore positivo" in item["reading"].lower()
    assert "favorevole" in item["reading"].lower()
    assert "scarsamente" not in item["reading"].lower()


def test_reading_phase1_zero_intermediate():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            edge_pct=0,
            model_context_probability=0.40,
            opposition_pressure_model=0.45,
            opposition_pressure_book=0.55,
            favourite_alignment="disagree",
            book_favourite_selection=SEL_AWAY,
            favourite_intensity_book=0.55,
            comparator_selections=[SEL_DRAW, SEL_AWAY],
        )
    )
    assert item["score"] == 0
    p2 = item["phase_2_quality"]["score"]
    assert p2 is not None and 40 <= p2 < 60
    assert "intermedia" in item["reading"].lower()


def test_reading_phase1_zero_limited():
    item = calculate_purchasability_candidate_item(
        _feature_item(
            edge_pct=0,
            model_context_probability=0.20,
            opposition_pressure_model=0.55,
            opposition_pressure_book=0.80,
            favourite_alignment="disagree",
            book_favourite_selection=SEL_AWAY,
            favourite_intensity_book=0.80,
            comparator_selections=[SEL_DRAW, SEL_AWAY],
        )
    )
    assert item["score"] == 0
    assert item["phase_2_quality"]["score"] is not None
    assert item["phase_2_quality"]["score"] < 40
    assert "supporto limitato" in item["reading"].lower()


def test_audit_independence():
    items = [
        calculate_purchasability_candidate_item(
            _feature_item(rating=70, edge_pct=10)
        ),
        calculate_purchasability_candidate_item(
            _feature_item(rating=90, edge_pct=15, market_key=SEL_DRAW)
        ),
    ]
    audit = audit_candidate_independence(items)
    assert audit["historical_reliability_imported"] is False
    assert audit["independence_invariants"][
        "candidate_formula_contains_rating"
    ] is False
    assert audit["compared_items"] == 2


def test_class_thresholds():
    assert map_score_to_class(0) == "Molto Bassa"
    assert map_score_to_class(19) == "Molto Bassa"
    assert map_score_to_class(20) == "Bassa"
    assert map_score_to_class(40) == "Media"
    assert map_score_to_class(60) == "Alta"
    assert map_score_to_class(80) == "Molto Alta"
    assert map_score_to_class(100) == "Molto Alta"


def test_reading_contains_base_phrase():
    item = calculate_purchasability_candidate_item(_feature_item())
    assert item["reading"]
    assert "valore individuato" in item["reading"].lower()
