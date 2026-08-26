"""Test Structural V2 — math, multi-block S, properties, anti-leakage, freeze."""

from __future__ import annotations

import ast
import copy
import math
from pathlib import Path

import pytest

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_v2_components import (
    compute_acquisition_core,
    compute_adjusted_and_final,
    compute_base_rate_reliability,
    compute_executable_value_v2,
    compute_information_quality_v2,
    compute_market_disagreement_v2,
    compute_structural_coherence_v2,
    compute_value_core,
    delta_logit,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    ACTIVE_V35_STRUCTURAL_VERSION,
    D_SCALE_V2,
    V_SCALE_V2,
    V35_V2_FORBIDDEN_INPUT_KEYS,
    compute_v2_formula_freeze_sha256,
    frozen_math_config_v35_v2,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_engine import (
    calculate_purchasability_v35_v2_item_from_prematch,
    score_structural_v2_from_components,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_features import (
    evaluate_v35_v2_gate_from_inputs,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_relations import (
    assert_no_synthetic_pt_dc_markets,
    blocks_for_market,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_utils import (
    classify_score_v2,
    round_score_v2,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
    SEL_ONE_X,
    SEL_X_TWO,
)

_V2_BACKEND = Path(__file__).resolve().parents[1] / "app" / "services" / "cecchino"


def _probs(
    mapping: dict[str, tuple[float, float]],
) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {
        mk: {"probability_cecchino": None, "fair_book_probability": None}
        for mk in PANEL_MARKET_KEYS
    }
    for mk, (p_cec, p_fair) in mapping.items():
        out[mk] = {
            "probability_cecchino": p_cec,
            "fair_book_probability": p_fair,
        }
    return out


def test_v_scale_numerical():
    assert compute_executable_value_v2(0.0)["score"] == 0.0
    v10 = compute_executable_value_v2(0.10)["score"]
    v20 = compute_executable_value_v2(0.20)["score"]
    v50 = compute_executable_value_v2(0.50)["score"]
    v100 = compute_executable_value_v2(1.00)["score"]
    assert abs(v10 - 15.35) < 0.05
    assert abs(v20 - 28.35) < 0.05
    assert abs(v50 - 56.54) < 0.05
    assert abs(v100 - 81.11) < 0.05
    assert V_SCALE_V2 == 0.60


def test_d_scale_numerical():
    # delta_logit for known probs
    d = compute_market_disagreement_v2(0.60, 0.40)
    expected_dl = delta_logit(0.60, 0.40)
    expected = 100.0 * (1.0 - math.exp(-expected_dl / D_SCALE_V2))
    assert abs(d["score"] - expected) < 1e-9
    assert D_SCALE_V2 == 0.85


def test_base_rate_reliability_longshot_vs_covered():
    longshot = compute_base_rate_reliability(0.40, 0.24)
    covered = compute_base_rate_reliability(0.68, 0.58)
    assert abs(longshot["R"] - 100.0 * math.sqrt(0.40 * 0.24)) < 1e-9
    assert abs(covered["R"] - 100.0 * math.sqrt(0.68 * 0.58)) < 1e-9
    assert covered["R"] > longshot["R"]
    assert longshot["is_calibrated_probability"] is False
    assert longshot["label"] == "Base-rate Reliability"


def test_value_and_acquisition_core():
    vc = compute_value_core(80.0, 60.0)
    assert abs(vc["value_core"] - (0.55 * 80 + 0.45 * 60)) < 1e-9
    ac = compute_acquisition_core(vc["value_core"], 40.0)
    assert abs(ac["acquisition_core"] - math.sqrt(vc["value_core"] * 40.0)) < 1e-9


def test_final_score_is_clamped_adjusted_no_display_transform():
    finals = compute_adjusted_and_final(
        acquisition_core=70.0,
        structural_factor=0.9,
        quality_factor=0.8,
    )
    assert finals["display_transform"] is None
    assert abs(finals["final_score_raw"] - 70.0 * 0.9 * 0.8) < 1e-9


def test_q2_penalties():
    q = compute_information_quality_v2(
        overround=0.15,
        book_fallback_used=True,
        fair_probability_may_be_derived=True,
        delta_logit_value=2.0,
    )
    assert q["fallback_penalty"] == 20.0
    assert q["derived_fair_penalty"] == 15.0
    assert q["score"] <= 100.0
    assert 0.5 <= q["quality_factor"] <= 1.0


def test_class_and_rounding():
    assert classify_score_v2(39) == "Molto Bassa"
    assert classify_score_v2(40) == "Bassa"
    assert classify_score_v2(55) == "Media"
    assert classify_score_v2(65) == "Alta"
    assert classify_score_v2(75) == "Molto Alta"
    assert classify_score_v2(80) == "Eccezionale"
    assert round_score_v2(54.5) == 55


def test_no_synthetic_pt_dc():
    assert_no_synthetic_pt_dc_markets()
    for mk in ("HOME_PT", "DRAW_PT", "AWAY_PT", "HOME", "DRAW", "AWAY"):
        blocks = blocks_for_market(mk)
        assert any(b.block_type == "same_family_opposition" for b in blocks)
    home_blocks = blocks_for_market(SEL_HOME)
    assert any(b.block_type == "side_cover" for b in home_blocks)
    assert any(b.block_type == "same_family_opposition" for b in home_blocks)
    # HOME has exactly 2 scoreable blocks, not 3 independent relations
    assert len(home_blocks) == 2


def test_pt_family_opposition_available():
    probs = _probs(
        {
            SEL_HOME_PT: (0.45, 0.35),
            SEL_DRAW_PT: (0.30, 0.35),
            SEL_AWAY_PT: (0.25, 0.30),
        }
    )
    for mk in (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT):
        s = compute_structural_coherence_v2(mk, probs_by_market=probs)
        assert s["status"] == "available"
        assert s["score"] is not None


def test_ft_family_and_side_cover_multi_block():
    probs = _probs(
        {
            SEL_HOME: (0.50, 0.40),
            SEL_DRAW: (0.25, 0.30),
            SEL_AWAY: (0.25, 0.30),
            SEL_ONE_X: (0.70, 0.65),
        }
    )
    s = compute_structural_coherence_v2(SEL_HOME, probs_by_market=probs)
    assert s["status"] == "available"
    assert s["configured_block_count"] == 2
    types = {b["block_type"] for b in s["blocks"]}
    assert types == {"same_family_opposition", "side_cover"}


def test_partial_coverage_shrinks_toward_50():
    # Only one opponent available for PT family → coverage 0.5, strength 0.75
    probs_partial = _probs(
        {
            SEL_HOME_PT: (0.55, 0.40),
            SEL_DRAW_PT: (0.20, 0.35),  # opponent underweighted by cecchino → support
            # AWAY_PT missing
        }
    )
    probs_full = _probs(
        {
            SEL_HOME_PT: (0.55, 0.40),
            SEL_DRAW_PT: (0.20, 0.35),
            SEL_AWAY_PT: (0.20, 0.35),
        }
    )
    s_partial = compute_structural_coherence_v2(
        SEL_HOME_PT, probs_by_market=probs_partial
    )
    s_full = compute_structural_coherence_v2(SEL_HOME_PT, probs_by_market=probs_full)
    assert s_partial["status"] == "available"
    assert s_full["status"] == "available"
    # Full positive coverage should push S farther above 50 than partial
    assert s_full["score"] > s_partial["score"]


def test_zero_coverage_unavailable():
    probs = _probs({SEL_HOME_PT: (0.55, 0.40)})
    s = compute_structural_coherence_v2(SEL_HOME_PT, probs_by_market=probs)
    assert s["status"] == "unavailable"
    assert s["structural_factor"] == 0.55
    assert s["structural_missing_penalty_applied"] is True


def _score_with_s(s_block, *, r=50.0, q_good=True):
    v = compute_executable_value_v2(0.25)
    d = compute_market_disagreement_v2(0.55, 0.45)
    q = compute_information_quality_v2(
        overround=0.03 if q_good else 0.20,
        book_fallback_used=False,
        fair_probability_may_be_derived=False,
        delta_logit_value=0.2,
    )
    return score_structural_v2_from_components(
        v_score=v["score"],
        d_score=d["score"],
        r_score=r,
        s_block=s_block,
        q_block=q,
    )


def test_property_s_missing_score_below_s100():
    s100 = {
        "status": "available",
        "score": 100.0,
        "structural_factor": 1.0,
        "structural_missing_penalty_applied": False,
    }
    s_missing = {
        "status": "unavailable",
        "score": None,
        "structural_factor": 0.55,
        "structural_missing_penalty_applied": True,
    }
    a = _score_with_s(s100)
    b = _score_with_s(s_missing)
    assert b["score"] < a["score"]


def test_property_partial_coverage_below_full_positive():
    probs_partial = _probs(
        {
            SEL_HOME: (0.55, 0.40),
            SEL_DRAW: (0.20, 0.35),
            # AWAY and ONE_X missing → partial family + missing side cover
        }
    )
    probs_full = _probs(
        {
            SEL_HOME: (0.55, 0.40),
            SEL_DRAW: (0.20, 0.35),
            SEL_AWAY: (0.20, 0.35),
            SEL_ONE_X: (0.75, 0.60),
        }
    )
    s_partial = compute_structural_coherence_v2(SEL_HOME, probs_by_market=probs_partial)
    s_full = compute_structural_coherence_v2(SEL_HOME, probs_by_market=probs_full)
    score_partial = _score_with_s(s_partial)
    score_full = _score_with_s(s_full)
    assert score_partial["score"] < score_full["score"]


def test_property_lower_r_lower_score():
    s = {
        "status": "available",
        "score": 80.0,
        "structural_factor": 0.90,
        "structural_missing_penalty_applied": False,
    }
    high = _score_with_s(s, r=70.0)
    low = _score_with_s(s, r=30.0)
    assert low["score"] < high["score"]


def test_property_lower_q_lower_score():
    s = {
        "status": "available",
        "score": 80.0,
        "structural_factor": 0.90,
        "structural_missing_penalty_applied": False,
    }
    good = _score_with_s(s, q_good=True)
    bad = _score_with_s(s, q_good=False)
    assert bad["score"] < good["score"]


def test_longshot_high_ev_stays_prudent():
    # EV large via high quote, but low absolute probs
    p_cec, p_fair, quote = 0.30, 0.15, 5.0
    ev = p_cec * quote - 1.0
    assert ev >= 0.50
    v = compute_executable_value_v2(ev)
    d = compute_market_disagreement_v2(p_cec, p_fair)
    r = compute_base_rate_reliability(p_cec, p_fair)
    assert v["score"] > 50
    assert r["R"] < 30
    s = {
        "status": "available",
        "score": 70.0,
        "structural_factor": 0.85,
        "structural_missing_penalty_applied": False,
    }
    q = compute_information_quality_v2(
        overround=0.04,
        book_fallback_used=False,
        fair_probability_may_be_derived=False,
        delta_logit_value=d["delta_logit"],
    )
    longshot = score_structural_v2_from_components(
        v_score=v["score"],
        d_score=d["score"],
        r_score=r["R"],
        s_block=s,
        q_block=q,
    )

    # Covered moderate EV
    p2_cec, p2_fair, q2 = 0.70, 0.60, 1.55
    ev2 = p2_cec * q2 - 1.0
    assert ev2 > 0
    v2 = compute_executable_value_v2(ev2)
    d2 = compute_market_disagreement_v2(p2_cec, p2_fair)
    r2 = compute_base_rate_reliability(p2_cec, p2_fair)
    covered = score_structural_v2_from_components(
        v_score=v2["score"],
        d_score=d2["score"],
        r_score=r2["R"],
        s_block=s,
        q_block=q,
    )
    assert r2["R"] > r["R"]
    # Covered may outrank longshot on reliability-driven acquisition
    assert covered["acquisition_core"] > longshot["acquisition_core"] or covered[
        "score"
    ] >= longshot["score"] - 5


def test_gate_unchanged():
    ok = evaluate_v35_v2_gate_from_inputs(
        execution_quote=2.2,
        execution_quote_real=True,
        probability_cecchino=0.55,
        fair_book_probability=0.40,
        rating=70.0,
    )
    assert ok["gate_status"] == "passed"
    bad = evaluate_v35_v2_gate_from_inputs(
        execution_quote=2.2,
        execution_quote_real=True,
        probability_cecchino=0.55,
        fair_book_probability=0.40,
        rating=40.0,
    )
    assert bad["item_status"] == "gate_failed"


def test_active_version_declared_not_wired_in_phase_a():
    assert ACTIVE_V35_STRUCTURAL_VERSION == "v2"
    cfg = frozen_math_config_v35_v2()
    assert cfg["active_v35_structural_version_wired"] is False


def test_formula_freeze_sha_stable():
    a = compute_v2_formula_freeze_sha256()
    b = compute_v2_formula_freeze_sha256()
    assert a == b
    assert len(a) == 64


def test_anti_leakage_forbidden_keys_recursive_ast():
    """V2 score-path modules must not use outcome/settlement identifiers."""
    forbidden_names = {
        "outcome",
        "profit_1u",
        "ht_home",
        "ft_home",
        "match_status",
        "historical_reliability",
        "score_A",
    }
    files = [
        "cecchino_purchasability_v35_v2_components.py",
        "cecchino_purchasability_v35_v2_engine.py",
        "cecchino_purchasability_v35_v2_config.py",
        "cecchino_purchasability_v35_v2_relations.py",
    ]
    for fname in files:
        src = (_V2_BACKEND / fname).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                pytest.fail(f"{fname} references forbidden name {node.id}")
    # Synthetic PT DC markets must not appear as related/selected markets in registry
    assert_no_synthetic_pt_dc_markets()
    for mk in PANEL_MARKET_KEYS:
        for block in blocks_for_market(mk):
            assert block.selected_market not in {
                "ONE_X_PT",
                "X_TWO_PT",
                "ONE_TWO_PT",
            }
            for rel in block.related_markets:
                assert rel not in {"ONE_X_PT", "X_TWO_PT", "ONE_TWO_PT"}


def test_panel_market_keys_count_19():
    assert len(PANEL_MARKET_KEYS) == 19


def test_item_from_prematch_no_abcd():
    probs = _probs(
        {
            SEL_HOME: (0.55, 0.40),
            SEL_DRAW: (0.22, 0.30),
            SEL_AWAY: (0.23, 0.30),
            SEL_ONE_X: (0.72, 0.65),
        }
    )
    gate = evaluate_v35_v2_gate_from_inputs(
        execution_quote=2.1,
        execution_quote_real=True,
        probability_cecchino=0.55,
        fair_book_probability=0.40,
        rating=70.0,
    )
    item = calculate_purchasability_v35_v2_item_from_prematch(
        SEL_HOME,
        gate=gate,
        input_payload={
            "execution_quote": 2.1,
            "execution_quote_real": True,
            "probability_cecchino": 0.55,
            "fair_book_probability": 0.40,
            "rating": 70.0,
            "overround": 0.05,
            "book_fallback_used": False,
            "fair_probability_may_be_derived": False,
        },
        probs_by_market=probs,
    )
    assert "candidates" not in item
    assert item["status"] == "score"
    assert item["reference"]["id"] == "v35_structural_v2_reference"
    assert item["components"]["base_rate_reliability"]["is_calibrated_probability"] is False
