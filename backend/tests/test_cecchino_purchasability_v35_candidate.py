"""Test Cecchino Purchasability V3.5 — componenti, gate, candidate, indipendenza V3.1."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_candidate import (
    SUPPORTED_V35_MARKETS,
    calculate_purchasability_v35_batch,
    calculate_purchasability_v35_item,
    score_candidate,
)
from app.services.cecchino.cecchino_purchasability_v35_components import (
    compute_executable_value,
    compute_information_quality,
    compute_market_disagreement,
    compute_structural_coherence,
    delta_logit,
    logit,
)
from app.services.cecchino.cecchino_purchasability_v35_config import (
    CANDIDATE_WEIGHTS,
    D_MARKET_DISAGREEMENT_SCALE,
    GATE_REASON_EXECUTION_QUOTE_NOT_REAL,
    GATE_REASON_INVALID_PRE_MATCH_SNAPSHOT,
    GATE_REASON_MISSING_EXECUTION_QUOTE,
    GATE_REASON_MODEL_NOT_ABOVE_FAIR,
    GATE_REASON_NON_POSITIVE_EV,
    GATE_REASON_RATING_BELOW_50,
    RATING_MIN_GATE,
    V_EXECUTABLE_VALUE_SCALE,
    V35_FORBIDDEN_INPUT_KEYS,
)
from app.services.cecchino.cecchino_purchasability_v35_features import (
    assert_no_forbidden_keys_in_row,
    evaluate_v35_gate,
    resolve_execution_quote_v35,
    sanitize_kpi_row,
    verify_pre_match_snapshot,
)
from app.services.cecchino.cecchino_purchasability_v35_relations import (
    RELATION_REGISTRY,
    scoreable_relations_for_market,
)
from app.services.cecchino.cecchino_purchasability_v35_utils import clamp_v35
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_X_TWO,
)

_V35_BACKEND = Path(__file__).resolve().parents[1] / "app" / "services" / "cecchino"
_LEGACY_IMPORT_PREFIXES = (
    "cecchino_purchasability_candidate",
    "cecchino_purchasability_v31",
    "cecchino_purchasability_v3_candidate",
)


def _fixture_meta(
    *,
    snapshot_at: str = "2026-08-19T10:00:00+00:00",
    kickoff: str = "2026-08-19T15:00:00+00:00",
) -> dict:
    return {
        "today_fixture_id": 1,
        "snapshot_at": snapshot_at,
        "kickoff": kickoff,
    }


def _row(
    mk: str,
    *,
    rating: float | None = 70,
    prob: float | None = 0.40,
    quota_book: float | None = 2.5,
    book_source: str = "betfair_raw_match_winner",
    derived: bool = False,
    book_fallback: bool = False,
    **extra,
) -> dict:
    out = {
        "market_key": mk,
        "quota_book": quota_book,
        "prob_cecchino": prob,
        "rating": rating,
        "book_source": book_source,
        "book_fallback_used": book_fallback,
    }
    if derived:
        out["derived_quote"] = True
        out["not_real_book_quote"] = True
    out.update(extra)
    return out


def _fair(prob: float, *, verified: bool = True, overround: float | None = 0.05) -> dict:
    return {
        "fair_book_probability": prob,
        "fair_book_probability_verified": verified,
        "fair_book_probability_source": "normalized_two_way_market",
        "market_overround": overround,
        "normalization_payload": {"overround": overround},
    }


def _exec_real(quota: float = 2.5) -> dict:
    return {
        "execution_quote": quota,
        "execution_quote_real": True,
        "performance_type": "real",
        "reason_code": None,
        "fair_probability_may_be_derived": False,
    }


def _gate_pass_row(
    mk: str = SEL_HOME,
    *,
    prob: float = 0.55,
    fair_prob: float = 0.45,
    quota: float = 2.2,
    rating: float = 60,
) -> tuple[dict, dict, dict]:
    row = _row(mk, rating=rating, prob=prob, quota_book=quota)
    fair = _fair(fair_prob)
    exec_info = _exec_real(quota)
    return row, fair, exec_info


# ---------------------------------------------------------------------------
# V component
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ev,expected",
    [
        (0.05, 100 * (1 - math.exp(-0.05 / V_EXECUTABLE_VALUE_SCALE))),
        (0.10, 100 * (1 - math.exp(-0.10 / V_EXECUTABLE_VALUE_SCALE))),
        (0.20, 100 * (1 - math.exp(-0.20 / V_EXECUTABLE_VALUE_SCALE))),
        (0.30, 100 * (1 - math.exp(-0.30 / V_EXECUTABLE_VALUE_SCALE))),
        (0.50, 100 * (1 - math.exp(-0.50 / V_EXECUTABLE_VALUE_SCALE))),
        (1.00, 100 * (1 - math.exp(-1.00 / V_EXECUTABLE_VALUE_SCALE))),
    ],
)
def test_v_component_formula(ev, expected):
    result = compute_executable_value(ev)
    assert result["executable_value_score"] == pytest.approx(expected, rel=1e-9)
    assert result["score"] == pytest.approx(clamp_v35(expected), rel=1e-9)
    assert 0 <= result["score"] <= 100


def test_v_component_monotonicity():
    prev = -1.0
    for ev in [0.01, 0.05, 0.10, 0.20, 0.50, 1.0]:
        s = compute_executable_value(ev)["score"]
        assert s > prev
        prev = s


def test_v_component_saturation():
    high = compute_executable_value(10.0)["score"]
    assert high >= 99.0


# ---------------------------------------------------------------------------
# D component
# ---------------------------------------------------------------------------


def test_d_component_equal_probs_near_zero():
    p = 0.50
    d = compute_market_disagreement(p, p)
    assert d["delta_logit"] == pytest.approx(0.0, abs=1e-9)
    assert d["score"] == pytest.approx(0.0, abs=1e-9)


def test_d_component_positive_disagreement():
    d = compute_market_disagreement(0.60, 0.50)
    assert d["delta_logit"] > 0
    assert d["score"] > 0


def test_d_component_monotonicity():
    prev = -1.0
    for p_model in [0.51, 0.55, 0.60, 0.70, 0.80]:
        s = compute_market_disagreement(p_model, 0.50)["score"]
        assert s > prev
        prev = s


# ---------------------------------------------------------------------------
# S component
# ---------------------------------------------------------------------------


def _structural_fixture(*, related_delta: float) -> tuple[str, dict, dict, dict]:
    """HOME with ONE_X related market support."""
    p_fair_related = 0.50
    dl = related_delta
    p_related = math.exp(logit(p_fair_related) + dl) / (
        1 + math.exp(logit(p_fair_related) + dl)
    )
    by_mk = {
        SEL_HOME: _row(SEL_HOME, rating=70, prob=0.55, quota_book=2.2),
        SEL_ONE_X: _row(SEL_ONE_X, rating=70, prob=p_related, quota_book=1.5),
    }
    fair_by = {
        SEL_HOME: _fair(0.45),
        SEL_ONE_X: _fair(p_fair_related),
    }
    model_probs = {
        SEL_HOME: by_mk[SEL_HOME]["prob_cecchino"],
        SEL_ONE_X: by_mk[SEL_ONE_X]["prob_cecchino"],
    }
    return SEL_HOME, by_mk, fair_by, model_probs


def test_s_component_positive_support():
    _, by_mk, fair_by, model_probs = _structural_fixture(related_delta=0.5)
    s = compute_structural_coherence(
        SEL_HOME, by_mk=by_mk, fair_by=fair_by, model_probs=model_probs
    )
    assert s["raw_score"] is not None
    assert s["raw_score"] > 50
    assert s["score"] is not None
    assert s["score"] < s["raw_score"]  # side_cover weight attenuates


def test_s_component_neutral_support():
    _, by_mk, fair_by, model_probs = _structural_fixture(related_delta=0.0)
    s = compute_structural_coherence(
        SEL_HOME, by_mk=by_mk, fair_by=fair_by, model_probs=model_probs
    )
    assert s["raw_score"] == pytest.approx(50.0, abs=0.5)
    assert s["score"] == pytest.approx(50.0, abs=0.5)


def test_s_component_negative_support():
    _, by_mk, fair_by, model_probs = _structural_fixture(related_delta=-0.5)
    s = compute_structural_coherence(
        SEL_HOME, by_mk=by_mk, fair_by=fair_by, model_probs=model_probs
    )
    assert s["raw_score"] is not None
    assert s["raw_score"] < 50
    assert s["score"] is not None
    assert s["score"] > s["raw_score"]  # attenuation pulls toward 50 from below


def test_s_side_cover_weight_attenuates():
    """weight=0.60 must not cancel: S_effective < S_raw when S_raw > 50."""
    _, by_mk, fair_by, model_probs = _structural_fixture(related_delta=0.8)
    s = compute_structural_coherence(
        SEL_HOME, by_mk=by_mk, fair_by=fair_by, model_probs=model_probs
    )
    assert s["relation_strength"] == pytest.approx(0.60, abs=1e-9)
    assert s["coverage"] == pytest.approx(1.0, abs=1e-9)
    assert s["structural_confidence"] == pytest.approx(0.60, abs=1e-9)
    assert s["raw_score"] > 50
    assert s["score"] == pytest.approx(50 + (s["raw_score"] - 50) * 0.60, abs=0.01)


def test_s_over_25_partial_coverage():
    """OVER_2_5 has 2 adjacent relations; only one with data → coverage=0.5."""
    p_fair = 0.50
    p_related = 0.65
    by_mk = {
        SEL_OVER_2_5: _row(SEL_OVER_2_5, rating=70, prob=0.60, quota_book=2.0),
        SEL_OVER_1_5: _row(SEL_OVER_1_5, rating=70, prob=p_related, quota_book=1.4),
    }
    fair_by = {
        SEL_OVER_2_5: _fair(0.48),
        SEL_OVER_1_5: _fair(p_fair),
    }
    model_probs = {k: v["prob_cecchino"] for k, v in by_mk.items()}
    s = compute_structural_coherence(
        SEL_OVER_2_5, by_mk=by_mk, fair_by=fair_by, model_probs=model_probs
    )
    assert s["configured_relation_count"] == 2
    assert s["available_relation_count"] == 1
    assert s["coverage"] == pytest.approx(0.5, abs=1e-9)
    assert s["relation_strength"] == pytest.approx(1.0, abs=1e-9)
    assert s["structural_confidence"] == pytest.approx(0.5, abs=1e-9)


def test_s_component_unavailable_no_relations():
    s = compute_structural_coherence(
        SEL_DRAW, by_mk={}, fair_by={}, model_probs={}
    )
    assert s["score"] is None
    assert s["structural_status"] == "unavailable"


def test_s_deterministic_relations_excluded_from_score():
    for rel in RELATION_REGISTRY:
        if rel.relation_type == "deterministic":
            assert rel.used_in_score is False


def test_s_scoreable_relations_not_include_complements():
    over_rels = scoreable_relations_for_market(SEL_OVER_2_5)
    related_keys = {r.related_market for r in over_rels}
    assert SEL_UNDER_2_5 not in related_keys


# ---------------------------------------------------------------------------
# Q component
# ---------------------------------------------------------------------------


def test_q_overround_penalty():
    q_low = compute_information_quality(
        overround=0.03,
        book_fallback_used=False,
        fair_probability_may_be_derived=False,
        delta_logit_value=0.5,
        hours_to_kickoff=24.0,
    )
    assert q_low["overround_penalty"] == 0.0

    q_mid = compute_information_quality(
        overround=0.10,
        book_fallback_used=False,
        fair_probability_may_be_derived=False,
        delta_logit_value=0.5,
        hours_to_kickoff=24.0,
    )
    assert q_mid["overround_penalty"] == pytest.approx(12.5, abs=0.1)

    q_high = compute_information_quality(
        overround=0.20,
        book_fallback_used=False,
        fair_probability_may_be_derived=False,
        delta_logit_value=0.5,
        hours_to_kickoff=24.0,
    )
    assert q_high["overround_penalty"] == 25.0


def test_q_fallback_penalty():
    q = compute_information_quality(
        overround=0.03,
        book_fallback_used=True,
        fair_probability_may_be_derived=False,
        delta_logit_value=0.5,
        hours_to_kickoff=24.0,
    )
    assert q["fallback_penalty"] == 10.0


def test_q_derived_fair_penalty():
    q = compute_information_quality(
        overround=0.03,
        book_fallback_used=False,
        fair_probability_may_be_derived=True,
        delta_logit_value=0.5,
        hours_to_kickoff=24.0,
    )
    assert q["derived_fair_penalty"] == 10.0


def test_q_extreme_divergence_penalty():
    q_none = compute_information_quality(
        overround=0.03,
        book_fallback_used=False,
        fair_probability_may_be_derived=False,
        delta_logit_value=1.0,
        hours_to_kickoff=24.0,
    )
    assert q_none["extreme_divergence_penalty"] == 0.0

    q_full = compute_information_quality(
        overround=0.03,
        book_fallback_used=False,
        fair_probability_may_be_derived=False,
        delta_logit_value=3.0,
        hours_to_kickoff=24.0,
    )
    assert q_full["extreme_divergence_penalty"] == 20.0


def test_q_combined_penalties():
    q = compute_information_quality(
        overround=0.10,
        book_fallback_used=True,
        fair_probability_may_be_derived=True,
        delta_logit_value=3.0,
        hours_to_kickoff=12.0,
    )
    assert q["snapshot_age_used_in_score"] is False
    expected = clamp_v35(100 - 12.5 - 10 - 10 - 20)
    assert q["score"] == pytest.approx(expected, abs=0.1)


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_gate_rating_49_fails():
    row, fair, exec_info = _gate_pass_row(rating=49)
    gate = evaluate_v35_gate(
        row=row,
        fair_info=fair,
        exec_info=exec_info,
        probability_cecchino=0.55,
        fair_book_probability=0.45,
        fixture_meta=_fixture_meta(),
    )
    assert gate["item_status"] == "gate_failed"
    assert GATE_REASON_RATING_BELOW_50 in gate["gate_reason_codes"]


def test_gate_rating_50_can_pass():
    row, fair, exec_info = _gate_pass_row(rating=50)
    gate = evaluate_v35_gate(
        row=row,
        fair_info=fair,
        exec_info=exec_info,
        probability_cecchino=0.55,
        fair_book_probability=0.45,
        fixture_meta=_fixture_meta(),
    )
    assert gate["gate_status"] == "passed"


def test_gate_ev_non_positive():
    row, fair, exec_info = _gate_pass_row(prob=0.40, quota=2.0, fair_prob=0.35)
    # EV = 0.40 * 2.0 - 1 = -0.20
    gate = evaluate_v35_gate(
        row=row,
        fair_info=fair,
        exec_info=exec_info,
        probability_cecchino=0.40,
        fair_book_probability=0.35,
        fixture_meta=_fixture_meta(),
    )
    assert gate["item_status"] == "gate_failed"
    assert GATE_REASON_NON_POSITIVE_EV in gate["gate_reason_codes"]


def test_gate_model_not_above_fair():
    row, fair, exec_info = _gate_pass_row(prob=0.50, fair_prob=0.50, quota=2.5)
    gate = evaluate_v35_gate(
        row=row,
        fair_info=fair,
        exec_info=exec_info,
        probability_cecchino=0.50,
        fair_book_probability=0.50,
        fixture_meta=_fixture_meta(),
    )
    assert gate["item_status"] == "gate_failed"
    assert GATE_REASON_MODEL_NOT_ABOVE_FAIR in gate["gate_reason_codes"]


def test_gate_missing_quote():
    row = _row(SEL_HOME, quota_book=None)
    exec_info = resolve_execution_quote_v35(_fair(0.45), row)
    gate = evaluate_v35_gate(
        row=row,
        fair_info=_fair(0.45),
        exec_info=exec_info,
        probability_cecchino=0.55,
        fair_book_probability=0.45,
        fixture_meta=_fixture_meta(),
    )
    assert gate["item_status"] == "not_calculable"
    assert GATE_REASON_MISSING_EXECUTION_QUOTE in gate["gate_reason_codes"]


def test_gate_derived_quote_not_executable():
    row = _row(SEL_HOME, derived=True)
    exec_info = resolve_execution_quote_v35(_fair(0.45), row)
    assert exec_info["execution_quote_real"] is False
    gate = evaluate_v35_gate(
        row=row,
        fair_info=_fair(0.45),
        exec_info=exec_info,
        probability_cecchino=0.55,
        fair_book_probability=0.45,
        fixture_meta=_fixture_meta(),
    )
    assert gate["item_status"] == "not_calculable"
    assert GATE_REASON_EXECUTION_QUOTE_NOT_REAL in gate["gate_reason_codes"]


# ---------------------------------------------------------------------------
# Pre-match invariant
# ---------------------------------------------------------------------------


def test_prematch_snapshot_before_kickoff_passes():
    assert verify_pre_match_snapshot(_fixture_meta())["verified"] is True


def test_prematch_snapshot_equal_kickoff_fails():
    meta = _fixture_meta(
        snapshot_at="2026-08-19T15:00:00+00:00",
        kickoff="2026-08-19T15:00:00+00:00",
    )
    check = verify_pre_match_snapshot(meta)
    assert check["verified"] is False
    row, fair, exec_info = _gate_pass_row()
    gate = evaluate_v35_gate(
        row=row,
        fair_info=fair,
        exec_info=exec_info,
        probability_cecchino=0.55,
        fair_book_probability=0.45,
        fixture_meta=meta,
    )
    assert gate["item_status"] == "not_calculable"
    assert GATE_REASON_INVALID_PRE_MATCH_SNAPSHOT in gate["gate_reason_codes"]


def test_prematch_snapshot_after_kickoff_fails():
    meta = _fixture_meta(
        snapshot_at="2026-08-19T16:00:00+00:00",
        kickoff="2026-08-19T15:00:00+00:00",
    )
    gate = evaluate_v35_gate(
        row=_gate_pass_row()[0],
        fair_info=_gate_pass_row()[1],
        exec_info=_gate_pass_row()[2],
        probability_cecchino=0.55,
        fair_book_probability=0.45,
        fixture_meta=meta,
    )
    assert gate["item_status"] == "not_calculable"
    assert GATE_REASON_INVALID_PRE_MATCH_SNAPSHOT in gate["gate_reason_codes"]


def test_prematch_invalid_timestamp_fails():
    meta = {"snapshot_at": "not-a-date", "kickoff": "2026-08-19T15:00:00+00:00"}
    assert verify_pre_match_snapshot(meta)["verified"] is False
    gate = evaluate_v35_gate(
        row=_gate_pass_row()[0],
        fair_info=_gate_pass_row()[1],
        exec_info=_gate_pass_row()[2],
        probability_cecchino=0.55,
        fair_book_probability=0.45,
        fixture_meta=meta,
    )
    assert GATE_REASON_INVALID_PRE_MATCH_SNAPSHOT in gate["gate_reason_codes"]


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


def test_candidates_share_components_differ_only_weights():
    comps = {"V": 70.0, "D": 60.0, "S": 55.0, "Q": 80.0}
    results = {k: score_candidate(comps, k) for k in ("A", "B", "C", "D")}
    for k in ("A", "B", "C", "D"):
        assert results[k]["configured_weights"] == dict(CANDIDATE_WEIGHTS[k])
    scores = [results[k]["score"] for k in ("A", "B", "C", "D")]
    assert len(set(scores)) > 1


def test_s_missing_normalization():
    comps = {"V": 60.0, "D": 50.0, "S": None, "Q": 80.0}
    a = score_candidate(comps, "A")
    # (0.40*60 + 0.25*50 + 0.15*80) / 0.80 = 48.5 / 0.80 = 60.625
    assert a["raw_score"] == pytest.approx(60.63, abs=0.01)
    assert a["score"] == 61  # ROUND_HALF_UP
    assert a["missing_components"] == ["S"]
    assert "S" not in a["effective_weights"]

    b = score_candidate(comps, "B")
    # (0.55*60 + 0.20*50 + 0.10*80) / 0.85 = 51 / 0.85 = 60.0
    assert b["raw_score"] == pytest.approx(60.0, abs=0.01)

    c = score_candidate(comps, "C")
    # (0.35*60 + 0.20*50 + 0.15*80) / 0.70 = 43 / 0.70 ≈ 61.43
    assert c["raw_score"] == pytest.approx(61.43, abs=0.01)

    d = score_candidate(comps, "D")
    # (0.35*60 + 0.20*50 + 0.30*80) / 0.85 = 55 / 0.85 ≈ 64.71
    assert d["raw_score"] == pytest.approx(64.71, abs=0.01)


# ---------------------------------------------------------------------------
# Sanity UNDER_3_5 pre-match
# ---------------------------------------------------------------------------


def test_sanity_under_35_pre_match():
    mk = SEL_UNDER_3_5
    p_cec = 0.8243391521
    p_fair = 0.7524752475
    quota = 1.25
    row = _row(mk, rating=50, prob=p_cec, quota_book=quota, book_fallback=False)
    fair_by = {mk: _fair(p_fair, overround=0.0631578947)}
    by_mk = {mk: row}

    item = calculate_purchasability_v35_item(
        mk, row, by_mk, fair_by=fair_by, model_probs={mk: p_cec},
        fixture_meta=_fixture_meta(),
    )

    ev = p_cec * quota - 1
    dl = delta_logit(p_cec, p_fair)
    v = compute_executable_value(ev)["score"]
    d = compute_market_disagreement(p_cec, p_fair)["score"]
    q = compute_information_quality(
        overround=0.0631578947,
        book_fallback_used=False,
        fair_probability_may_be_derived=False,
        delta_logit_value=dl,
        hours_to_kickoff=None,
    )["score"]

    assert item["status"] == "score"
    assert math.isfinite(ev)
    assert math.isfinite(dl)
    assert 0 <= v <= 100
    assert 0 <= d <= 100
    assert 0 <= q <= 100

    s_block = item["components"]["structural_coherence"]
    assert s_block["score"] is None
    assert s_block["structural_status"] == "unavailable"

    for ck in ("A", "B", "C", "D"):
        cand = item["candidates"][ck]
        assert cand["score"] is not None
        assert 0 <= cand["score"] <= 100
        assert "S" in cand["missing_components"]

    assert item["components"]["executable_value"]["expected_value"] == pytest.approx(
        ev, rel=1e-6
    )
    assert item["components"]["market_disagreement"]["delta_logit"] == pytest.approx(
        dl, rel=1e-6
    )


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_invariants_no_nan_inf():
    rows = [
        _row(SEL_HOME, rating=60, prob=0.55, quota_book=2.2),
        _row(SEL_DRAW, rating=55, prob=0.30, quota_book=3.5),
        _row(SEL_UNDER_3_5, rating=50, prob=0.8243391521, quota_book=1.25),
    ]
    fair_by = {
        SEL_HOME: _fair(0.45),
        SEL_DRAW: _fair(0.28),
        SEL_UNDER_3_5: _fair(0.7524752475, overround=0.063),
    }
    by_mk = {r["market_key"]: r for r in rows}
    for mk, row in by_mk.items():
        item = calculate_purchasability_v35_item(
            mk, row, by_mk, fair_by=fair_by, model_probs={mk: row["prob_cecchino"]},
            fixture_meta=_fixture_meta(),
        )
        for comp_name, comp in item["components"].items():
            if comp is None:
                continue
            sc = comp.get("score")
            if sc is not None:
                assert math.isfinite(sc)
                assert 0 <= sc <= 100
        for ck in ("A", "B", "C", "D"):
            sc = item["candidates"][ck].get("score")
            if sc is not None:
                assert math.isfinite(sc)
                assert 0 <= sc <= 100


# ---------------------------------------------------------------------------
# V3.1 independence
# ---------------------------------------------------------------------------


def test_v35_independent_of_v31_fields():
    base_extra = {
        "v3_score": 88,
        "v31_score": 77,
        "score_acquisto": 12.5,
        "historical_reliability": {"score": 90},
        "won": True,
        "result": "1-0",
    }
    mk = SEL_HOME
    row_a = _row(mk, rating=60, prob=0.55, quota_book=2.2, **base_extra)
    row_b = _row(
        mk,
        rating=60,
        prob=0.55,
        quota_book=2.2,
        v3_score=1,
        v31_score=1,
        score_acquisto=999,
        historical_reliability_score=1,
    )
    fair_by = {mk: _fair(0.45)}
    by_mk_a = {mk: row_a}
    by_mk_b = {mk: row_b}

    out_a = calculate_purchasability_v35_item(
        mk, row_a, by_mk_a, fair_by=fair_by, model_probs={mk: 0.55},
        fixture_meta=_fixture_meta(),
    )
    out_b = calculate_purchasability_v35_item(
        mk, row_b, by_mk_b, fair_by=fair_by, model_probs={mk: 0.55},
        fixture_meta=_fixture_meta(),
    )

    assert out_a["candidates"] == out_b["candidates"]
    assert out_a["components"] == out_b["components"]
    assert assert_no_forbidden_keys_in_row(sanitize_kpi_row(row_a)) == []


def test_forbidden_keys_stripped_from_sanitize():
    row = _row(SEL_HOME, rating=60, prob=0.55, quota_book=2.2)
    row["won"] = True
    row["settlement"] = "won"
    clean = sanitize_kpi_row(row)
    assert "won" not in clean
    assert "settlement" not in clean
    for fk in V35_FORBIDDEN_INPUT_KEYS:
        assert fk not in clean


# ---------------------------------------------------------------------------
# Batch 19 markets
# ---------------------------------------------------------------------------


def test_batch_covers_19_markets():
    rows = [_row(mk, rating=60, prob=0.55, quota_book=2.2) for mk in PANEL_MARKET_KEYS]
    batch = calculate_purchasability_v35_batch(
        kpi_panel={"rows": rows}, fixture_meta=_fixture_meta(),
    )
    assert batch["summary"]["supported_markets"] == 19
    assert len(batch["items"]) == 19
    assert set(SUPPORTED_V35_MARKETS) == set(PANEL_MARKET_KEYS)
    assert batch["pre_match_only"] is True
    assert batch["pre_match_verified"] is True
    assert batch["contains_post_match_fields"] is False


def test_batch_relation_registry_once():
    rows = [_row(SEL_HOME, rating=60, prob=0.55, quota_book=2.2)]
    batch = calculate_purchasability_v35_batch(
        kpi_panel={"rows": rows}, fixture_meta=_fixture_meta(),
    )
    assert "relation_registry" in batch
    assert batch["relation_registry_version"]
    assert len(batch["relation_registry"]) > 0
    for item in batch["items"]:
        assert "relation_registry" not in item.get("diagnostics", {})


def test_item_has_market_relations_only():
    p_related = 0.65
    rows = [
        _row(SEL_HOME, rating=60, prob=0.55, quota_book=2.2),
        _row(SEL_ONE_X, rating=70, prob=p_related, quota_book=1.4),
    ]
    batch = calculate_purchasability_v35_batch(
        kpi_panel={"rows": rows}, fixture_meta=_fixture_meta(),
    )
    home = next(it for it in batch["items"] if it["market_key"] == SEL_HOME)
    s_block = home["components"]["structural_coherence"]
    if s_block and s_block.get("relations"):
        assert all("related_market" in r for r in s_block["relations"])


def test_batch_dependency_meta():
    batch = calculate_purchasability_v35_batch(
        kpi_panel={"rows": []}, fixture_meta=_fixture_meta(),
    )
    dm = batch["dependency_meta"]
    assert dm["rating_used_as_gate"] is True
    assert dm["rating_used_in_score"] is False
    assert dm["historical_reliability_used"] is False
    assert dm["score_acquisto_used"] is False


# ---------------------------------------------------------------------------
# Audit scenarios (8 synthetic cases)
# ---------------------------------------------------------------------------


def _audit_item(
    scenario: str,
    mk: str,
    *,
    rating: float | None,
    prob: float | None,
    fair_prob: float | None,
    quota: float | None,
    verified: bool = True,
    derived: bool = False,
    overround: float | None = 0.05,
    related_rows: dict | None = None,
    related_fair: dict | None = None,
) -> dict:
    row = _row(
        mk,
        rating=rating,
        prob=prob,
        quota_book=quota,
        derived=derived,
    )
    by_mk = {mk: row}
    fair_by: dict = {}
    if fair_prob is not None:
        fair_by[mk] = _fair(fair_prob, verified=verified, overround=overround)
    if related_rows:
        by_mk.update(related_rows)
    if related_fair:
        fair_by.update(related_fair)

    model_probs = {k: v.get("prob_cecchino") for k, v in by_mk.items()}
    item = calculate_purchasability_v35_item(
        mk, row, by_mk, fair_by=fair_by, model_probs=model_probs,
        fixture_meta=_fixture_meta(),
    )

    ev = None
    dl = None
    if prob and quota:
        ev = prob * quota - 1
    if prob and fair_prob:
        dl = delta_logit(prob, fair_prob)

    comps = item["components"] or {}
    s_block = comps.get("structural_coherence") or {}
    return {
        "scenario": scenario,
        "market": mk,
        "rating": rating,
        "quota": quota,
        "p_model": prob,
        "p_book_fair": fair_prob,
        "EV": ev,
        "delta_logit": dl,
        "V": (comps.get("executable_value") or {}).get("score"),
        "D": (comps.get("market_disagreement") or {}).get("score"),
        "S_raw": s_block.get("raw_score"),
        "structural_confidence": s_block.get("structural_confidence"),
        "S_effective": s_block.get("score"),
        "Q": (comps.get("information_quality") or {}).get("score"),
        "score_A": item["candidates"]["A"]["score"],
        "score_B": item["candidates"]["B"]["score"],
        "score_C": item["candidates"]["C"]["score"],
        "score_D": item["candidates"]["D"]["score"],
        "gate_status": item["gate_status"],
        "status": item["status"],
    }


def test_audit_eight_scenarios(capsys):
    """Stampa tabella audit per revisione matematica."""
    p_related_pos = 0.65
    p_fair_related = 0.50
    related_row = _row(SEL_ONE_X, rating=70, prob=p_related_pos, quota_book=1.4)
    related_fair = {SEL_ONE_X: _fair(p_fair_related)}

    p_related_neg = 0.35
    related_row_neg = _row(SEL_ONE_X, rating=70, prob=p_related_neg, quota_book=2.8)

    scenarios = [
        _audit_item("1_valore_piccolo", SEL_HOME, rating=60, prob=0.52, fair_prob=0.48, quota=2.05),
        _audit_item("2_valore_medio", SEL_AWAY, rating=65, prob=0.45, fair_prob=0.38, quota=2.50),
        _audit_item("3_valore_alto", SEL_OVER_2_5, rating=70, prob=0.60, fair_prob=0.48, quota=2.00),
        _audit_item(
            "4_divergenza_estrema",
            SEL_HOME,
            rating=60,
            prob=0.85,
            fair_prob=0.45,
            quota=1.50,
            overround=0.14,
        ),
        _audit_item(
            "5_struttura_positiva",
            SEL_HOME,
            rating=60,
            prob=0.55,
            fair_prob=0.45,
            quota=2.20,
            related_rows={SEL_ONE_X: related_row},
            related_fair=related_fair,
        ),
        _audit_item(
            "6_struttura_contraria",
            SEL_HOME,
            rating=60,
            prob=0.55,
            fair_prob=0.45,
            quota=2.20,
            related_rows={SEL_ONE_X: related_row_neg},
            related_fair=related_fair,
        ),
        _audit_item("7_S_unavailable", SEL_DRAW, rating=60, prob=0.35, fair_prob=0.30, quota=3.20),
        _audit_item("8_rating_49_gate", SEL_HOME, rating=49, prob=0.55, fair_prob=0.45, quota=2.20),
    ]

    header = (
        "scenario\tmarket\trating\tquota\tp_model\tp_book_fair\tEV\tdelta_logit\t"
        "V\tD\tS_raw\tconfidence\tS_effective\tQ\tscore_A\tscore_B\tscore_C\tscore_D\tgate_status"
    )
    print("\n=== V3.5 AUDIT TABLE ===")
    print(header)
    for s in scenarios:
        line = "\t".join(
            str(s[k])
            for k in (
                "scenario",
                "market",
                "rating",
                "quota",
                "p_model",
                "p_book_fair",
                "EV",
                "delta_logit",
                "V",
                "D",
                "S_raw",
                "structural_confidence",
                "S_effective",
                "Q",
                "score_A",
                "score_B",
                "score_C",
                "score_D",
                "gate_status",
            )
        )
        print(line)

    assert scenarios[6]["S_effective"] is None
    assert scenarios[7]["gate_status"] == "gate_failed"
    assert scenarios[7]["status"] == "gate_failed"
    assert scenarios[4]["S_effective"] is not None
    assert scenarios[4]["S_raw"] is not None
    assert scenarios[4]["S_effective"] < scenarios[4]["S_raw"]
    assert scenarios[5]["S_effective"] is not None
    assert scenarios[5]["S_effective"] > scenarios[5]["S_raw"]


def test_v35_no_legacy_scoring_imports():
    """V3.5 must not import legacy purchasability scoring modules."""
    v35_files = sorted(_V35_BACKEND.glob("cecchino_purchasability_v35*.py"))
    assert v35_files, "expected v35 modules"
    offenders: list[str] = []
    for path in v35_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    if any(mod.startswith(p) for p in _LEGACY_IMPORT_PREFIXES):
                        offenders.append(f"{path.name}: import {mod}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                if any(
                    mod == p or mod.startswith(p + ".")
                    for p in _LEGACY_IMPORT_PREFIXES
                ):
                    offenders.append(f"{path.name}: from {mod}")
    assert offenders == []


def test_audit_structural_before_after(capsys):
    """BEFORE/AFTER table for structural confidence fix."""
    p_fair_related = 0.50
    related_pos = _row(SEL_ONE_X, rating=70, prob=0.65, quota_book=1.4)
    related_neg = _row(SEL_ONE_X, rating=70, prob=0.35, quota_book=2.8)
    related_fair = {SEL_ONE_X: _fair(p_fair_related)}

    over_both = [
        _row(SEL_OVER_2_5, rating=70, prob=0.60, quota_book=2.0),
        _row(SEL_OVER_1_5, rating=70, prob=0.65, quota_book=1.4),
        _row(SEL_OVER_3_5, rating=70, prob=0.55, quota_book=2.2),
    ]
    over_one = [
        _row(SEL_OVER_2_5, rating=70, prob=0.60, quota_book=2.0),
        _row(SEL_OVER_1_5, rating=70, prob=0.65, quota_book=1.4),
    ]
    fair_over = {
        SEL_OVER_2_5: _fair(0.48),
        SEL_OVER_1_5: _fair(0.50),
        SEL_OVER_3_5: _fair(0.45),
    }

    cases = [
        _audit_item(
            "HOME_side_cover_positive",
            SEL_HOME,
            rating=60,
            prob=0.55,
            fair_prob=0.45,
            quota=2.20,
            related_rows={SEL_ONE_X: related_pos},
            related_fair=related_fair,
        ),
        _audit_item(
            "HOME_side_cover_contrary",
            SEL_HOME,
            rating=60,
            prob=0.55,
            fair_prob=0.45,
            quota=2.20,
            related_rows={SEL_ONE_X: related_neg},
            related_fair=related_fair,
        ),
        _audit_item(
            "OVER_2_5_both_relations",
            SEL_OVER_2_5,
            rating=70,
            prob=0.60,
            fair_prob=0.48,
            quota=2.00,
            related_rows={r["market_key"]: r for r in over_both if r["market_key"] != SEL_OVER_2_5},
            related_fair=fair_over,
        ),
        _audit_item(
            "OVER_2_5_one_relation",
            SEL_OVER_2_5,
            rating=70,
            prob=0.60,
            fair_prob=0.48,
            quota=2.00,
            related_rows={r["market_key"]: r for r in over_one if r["market_key"] != SEL_OVER_2_5},
            related_fair={k: v for k, v in fair_over.items() if k != SEL_OVER_3_5},
        ),
        _audit_item(
            "S_unavailable",
            SEL_DRAW,
            rating=60,
            prob=0.35,
            fair_prob=0.30,
            quota=3.20,
        ),
    ]

    print("\n=== STRUCTURAL BEFORE/AFTER (S_effective vs old S_raw-only) ===")
    print(
        "scenario\tS_raw\tconfidence\tS_effective\tA\tB\tC\tD\t"
        "note_before=S_raw_used_as_score"
    )
    for c in cases:
        s_raw = c["S_raw"]
        conf = c["structural_confidence"]
        s_eff = c["S_effective"]
        before_a = c["score_A"]
        note = "unchanged" if s_raw is None else f"before_A≈used_S_raw={s_raw}"
        print(
            f"{c['scenario']}\t{s_raw}\t{conf}\t{s_eff}\t"
            f"{c['score_A']}\t{c['score_B']}\t{c['score_C']}\t{c['score_D']}\t{note}"
        )

    home_pos = cases[0]
    assert home_pos["S_raw"] > 50
    assert home_pos["structural_confidence"] == pytest.approx(0.60, abs=0.01)
    assert home_pos["S_effective"] == pytest.approx(
        50 + (home_pos["S_raw"] - 50) * 0.60, abs=0.5
    )
    assert home_pos["S_effective"] < home_pos["S_raw"]

    over_one = cases[3]
    assert over_one["structural_confidence"] == pytest.approx(0.5, abs=0.01)

    assert cases[4]["S_effective"] is None
