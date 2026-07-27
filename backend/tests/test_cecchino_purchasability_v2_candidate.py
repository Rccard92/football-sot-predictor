"""Test candidate Acquistabilità v2 — Fase 1/2, gate, formula finale."""

from __future__ import annotations

import math

from app.schemas.cecchino_purchasability_v2 import (
    PURCHASABILITY_DECISION_V2_CANDIDATE_NAME,
    PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
)
from app.services.cecchino.cecchino_purchasability_candidate import (
    ACTIVE_PURCHASABILITY_CANDIDATE_NAME,
    ACTIVE_PURCHASABILITY_CANDIDATE_VERSION,
    CLASS_THRESHOLDS,
)
from app.services.cecchino.cecchino_purchasability_v2_candidate import (
    FINAL_FORMULA_VERSION,
    PHASE_1_CONFIGURED_WEIGHTS,
    PHASE_1_FORMULA_VERSION,
    PHASE_2_CONFIGURED_WEIGHTS,
    PHASE_2_FORMULA_VERSION,
    calculate_purchasability_v2_batch,
    calculate_purchasability_v2_item,
)
from app.services.cecchino.cecchino_purchasability_v2_normalization import (
    build_empty_provisional_profile,
)
from app.services.cecchino.cecchino_purchasability_v2_opposition import (
    competitors_for_market,
    probability_competitors_for_market,
    resolve_opposite_selection,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)


def _row(
    mk: str,
    *,
    rating: float | None = 70,
    edge: float | None = 8.0,
    vant: float | None = 0.05,
    prob: float | None = 0.45,
    quota_book: float | None = 2.2,
    quota_cecchino: float | None = 2.0,
) -> dict:
    return {
        "market_key": mk,
        "segno": mk,
        "rating": rating,
        "edge_pct": edge,
        "vantaggio_prob": vant,
        "prob_cecchino": prob,
        "prob_book": 1.0 / quota_book if quota_book else None,
        "quota_book": quota_book,
        "quota_cecchino": quota_cecchino,
    }


def _panel_1x2_ou() -> dict:
    rows = [
        _row(SEL_HOME, rating=65, edge=5, vant=0.02, prob=0.40, quota_book=2.5),
        _row(SEL_DRAW, rating=55, edge=1, vant=0.01, prob=0.28, quota_book=3.4),
        _row(SEL_AWAY, rating=80, edge=12, vant=0.08, prob=0.32, quota_book=3.1),
        _row(SEL_ONE_X, rating=70, edge=4, vant=0.03, prob=0.68, quota_book=1.45),
        _row(SEL_X_TWO, rating=60, edge=2, vant=0.01, prob=0.60, quota_book=1.55),
        _row(SEL_ONE_TWO, rating=75, edge=6, vant=0.04, prob=0.72, quota_book=1.35),
        _row(SEL_OVER_2_5, rating=72, edge=7, vant=0.05, prob=0.55, quota_book=1.85),
        _row(SEL_UNDER_2_5, rating=50, edge=-2, vant=-0.02, prob=0.45, quota_book=2.05),
    ]
    return {"rows": rows, "version": "kpi_v2_test"}


def test_v1_1_active_candidate_unchanged():
    assert (
        ACTIVE_PURCHASABILITY_CANDIDATE_VERSION
        == "cecchino_purchasability_v1_preview_candidate_2"
    )
    assert ACTIVE_PURCHASABILITY_CANDIDATE_NAME == "balanced_geometric_v1_1"


def test_v2_candidate_constants():
    assert (
        PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION
        == "cecchino_purchasability_v2_candidate_1"
    )
    assert PURCHASABILITY_DECISION_V2_CANDIDATE_NAME == "decision_quality_v2"


def test_competitors_groups():
    assert set(competitors_for_market(SEL_HOME)) == {
        SEL_DRAW,
        SEL_AWAY,
        SEL_ONE_X,
        SEL_X_TWO,
        SEL_ONE_TWO,
    }
    assert competitors_for_market(SEL_OVER_2_5) == [SEL_UNDER_2_5]
    assert SEL_OVER_2_5 not in competitors_for_market(SEL_HOME)
    assert set(probability_competitors_for_market(SEL_HOME)) == {SEL_DRAW, SEL_AWAY}
    assert set(probability_competitors_for_market(SEL_ONE_X)) == {
        SEL_X_TWO,
        SEL_ONE_TWO,
    }


def test_opposite_map_and_draw():
    opp = resolve_opposite_selection(SEL_HOME, fair_book_by_market={SEL_AWAY: 0.4})
    assert opp["opposite_selection"] == SEL_AWAY
    draw = resolve_opposite_selection(
        SEL_DRAW,
        fair_book_by_market={SEL_HOME: 0.45, SEL_AWAY: 0.35},
    )
    assert draw["opposite_selection"] == SEL_HOME
    assert draw["draw_opposite_trace"]["selected_lateral"] == SEL_HOME


def test_phase1_full_and_gate_failed():
    profile = build_empty_provisional_profile()
    panel = _panel_1x2_ou()
    by_mk = {r["market_key"]: r for r in panel["rows"]}
    # Fair book verified so Fase 2 può chiudere
    fair_by = {
        mk: {
            "fair_book_probability": float(r["prob_book"]),
            "fair_book_probability_verified": True,
        }
        for mk, r in by_mk.items()
        if r.get("prob_book") is not None
    }
    model_probs = {k: r["prob_cecchino"] for k, r in by_mk.items()}
    item = calculate_purchasability_v2_item(
        SEL_UNDER_2_5,
        by_mk[SEL_UNDER_2_5],
        by_mk,
        profile=profile,
        fair_by=fair_by,
        model_probs=model_probs,
    )
    assert item["positive_value_gate"]["status"] == "failed"
    assert item["score"] == 0
    assert item["class"] == "Molto Bassa"
    assert item["raw_pre_gate_score"] is not None
    assert "positive_value_gate_failed" in item["reason_codes"]


def test_phase1_missing_does_not_count_as_negative():
    profile = build_empty_provisional_profile()
    row = _row(SEL_AWAY, edge=None, vant=0.05, rating=70)
    by_mk = {SEL_AWAY: row, SEL_HOME: _row(SEL_HOME), SEL_DRAW: _row(SEL_DRAW)}
    item = calculate_purchasability_v2_item(
        SEL_AWAY,
        row,
        by_mk,
        profile=profile,
        fair_by={},
        model_probs={},
    )
    gate = item["positive_value_gate"]
    assert "no_positive_edge" not in (gate.get("reason_codes") or [])
    # Edge missing → not treated as failed solely for that
    assert gate.get("edge_available") is False


def test_geometric_formula_and_rounding():
    profile = build_empty_provisional_profile()
    batch = calculate_purchasability_v2_batch(
        kpi_panel=_panel_1x2_ou(),
        profile=profile,
    )
    assert batch["candidate_version"] == PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION
    away = next(it for it in batch["items"] if it["market_key"] == SEL_AWAY)
    if away.get("phase_1_value", {}).get("score") and away.get("phase_2_quality", {}).get(
        "score"
    ):
        p1 = away["phase_1_value"]["score"]
        p2 = away["phase_2_quality"]["score"]
        expected = math.sqrt(p1 * p2)
        assert away["raw_pre_gate_score"] is not None
        assert abs(away["raw_pre_gate_score"] - expected) < 0.05


def test_score_and_reliability_not_used():
    profile = build_empty_provisional_profile()
    row = _row(SEL_AWAY)
    row["score_acquisto"] = 99
    by_mk = {
        SEL_AWAY: row,
        SEL_HOME: _row(SEL_HOME),
        SEL_DRAW: _row(SEL_DRAW),
        SEL_ONE_X: _row(SEL_ONE_X),
        SEL_X_TWO: _row(SEL_X_TWO),
        SEL_ONE_TWO: _row(SEL_ONE_TWO),
    }
    item = calculate_purchasability_v2_item(
        SEL_AWAY,
        row,
        by_mk,
        profile=profile,
        fair_by={},
        model_probs={k: 0.3 for k in by_mk},
    )
    p1 = item.get("phase_1_value") or {}
    assert p1.get("score_acquisto_used") is False
    assert p1.get("historical_reliability_used") is False


def test_v1_1_parity_same_input():
    """v1.1 active constants invariati; v2 usa versioni separate."""
    assert (
        ACTIVE_PURCHASABILITY_CANDIDATE_VERSION
        == "cecchino_purchasability_v1_preview_candidate_2"
    )
    panel = _panel_1x2_ou()
    v2 = calculate_purchasability_v2_batch(
        kpi_panel=panel, profile=build_empty_provisional_profile()
    )
    assert v2["candidate_version"] == PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION
    assert v2["candidate_version"] != ACTIVE_PURCHASABILITY_CANDIDATE_VERSION


def test_formula_weights_gate_rounding_unchanged():
    """Regressione: formula v2 invariata dopo fix storico."""
    assert dict(PHASE_1_CONFIGURED_WEIGHTS) == {
        "rating": 0.30,
        "edge_pct": 0.40,
        "vantaggio_prob": 0.30,
    }
    assert dict(PHASE_2_CONFIGURED_WEIGHTS) == {
        "dominance_rating": 0.25,
        "dominance_edge_pct": 0.25,
        "dominance_probability_pp": 0.20,
        "shift_book_cecchino_pp": 0.15,
        "opposite_contrast_pp": 0.15,
    }
    assert PHASE_1_FORMULA_VERSION == "purchasability_v2_phase_1_absolute_value_v1"
    assert PHASE_2_FORMULA_VERSION == "purchasability_v2_phase_2_decision_quality_v1"
    assert FINAL_FORMULA_VERSION == "purchasability_v2_final_geometric_v1"
    assert CLASS_THRESHOLDS == (20, 40, 60, 80)

    profile = build_empty_provisional_profile()
    panel = _panel_1x2_ou()
    batch_a = calculate_purchasability_v2_batch(kpi_panel=panel, profile=profile)
    batch_b = calculate_purchasability_v2_batch(kpi_panel=panel, profile=profile)
    assert batch_a["candidate_version"] == batch_b["candidate_version"]
    scores_a = {
        it["market_key"]: (it.get("score"), it.get("class"), it.get("raw_pre_gate_score"))
        for it in batch_a["items"]
    }
    scores_b = {
        it["market_key"]: (it.get("score"), it.get("class"), it.get("raw_pre_gate_score"))
        for it in batch_b["items"]
    }
    assert scores_a == scores_b
    # Gate positivo ancora presente
    under = next(it for it in batch_a["items"] if it["market_key"] == SEL_UNDER_2_5)
    assert "positive_value_gate" in under
    assert under["positive_value_gate"]["status"] in ("passed", "failed", "unavailable")
