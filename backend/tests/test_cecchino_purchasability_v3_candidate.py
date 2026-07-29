"""Test candidate Acquistabilità v3 — gate, scale fisse, penalità, regression."""

from __future__ import annotations

import json
import math

from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_CANDIDATE_VERSION,
    PURCHASABILITY_V3_FORMULA_VERSION,
    PURCHASABILITY_V3_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_candidate import (
    ACTIVE_PURCHASABILITY_CANDIDATE_NAME,
    ACTIVE_PURCHASABILITY_CANDIDATE_VERSION,
    round_purchasability_score_half_up,
)
from app.services.cecchino.cecchino_purchasability_v3_candidate import (
    DERIVED_QUOTE_PENALTY_POINTS,
    OPPOSITE_PRESSURE_MAX_POINTS,
    VALUE_EDGE_FULL_SCORE_PCT,
    calculate_purchasability_v3_batch,
    calculate_purchasability_v3_item,
    compute_extreme_divergence_penalty,
    compute_family_ambiguity_penalty,
    compute_opposite_pressure_penalty,
    compute_probability_risk_penalty,
    compute_value_score,
    evaluate_v3_gate,
)
from app.services.cecchino.cecchino_purchasability_v3_opposition import (
    competitors_for_market,
    linked_market_key_for,
    market_family_for,
    resolve_opposite_selection,
)
from app.services.cecchino.cecchino_purchasability_v3_snapshot import (
    attach_purchasability_preview_v3_to_output,
    build_purchasability_preview_v3_snapshot,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_kpi_explanations import (
    ANALYZABLE_METRICS,
    _METRIC_LABELS,
    _explain_purchasability_v3,
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
    score_acquisto: float | None = None,
    force_derived_quote: bool = False,
) -> dict:
    out = {
        "market_key": mk,
        "segno": mk,
        "rating": rating,
        "edge_pct": edge,
        "vantaggio_prob": vant,
        "prob_cecchino": prob,
        "prob_book": (1.0 / quota_book) if quota_book else None,
        "quota_book": quota_book,
        "quota_cecchino": quota_cecchino,
    }
    if score_acquisto is not None:
        out["score_acquisto"] = score_acquisto
    if force_derived_quote:
        out["force_derived_quote"] = True
        out["derived_quote"] = True
    return out


def _fair(
    prob: float,
    *,
    verified: bool = True,
    source: str = "normalized_1x2_market",
) -> dict:
    return {
        "fair_book_probability": prob,
        "fair_book_probability_verified": verified,
        "fair_book_probability_source": source,
        "raw_implied_probability": prob,
    }


def _item(mk: str, by_mk: dict, fair_by: dict, model_probs: dict | None = None):
    model = model_probs or {k: r.get("prob_cecchino") for k, r in by_mk.items()}
    gate_by = {k: evaluate_v3_gate(r) for k, r in by_mk.items()}
    edge_by = {k: r.get("edge_pct") for k, r in by_mk.items()}
    return calculate_purchasability_v3_item(
        mk,
        by_mk[mk],
        by_mk,
        fair_by=fair_by,
        model_probs=model,
        gate_by_market=gate_by,
        edge_by_market=edge_by,
    )


# --- parity / constants ---


def test_v1_1_and_v2_constants_unchanged():
    assert (
        ACTIVE_PURCHASABILITY_CANDIDATE_VERSION
        == "cecchino_purchasability_v1_preview_candidate_2"
    )
    assert ACTIVE_PURCHASABILITY_CANDIDATE_NAME == "balanced_geometric_v1_1"
    assert (
        PURCHASABILITY_V3_CANDIDATE_VERSION
        == "cecchino_purchasability_v3_candidate_1"
    )
    assert (
        PURCHASABILITY_V3_FORMULA_VERSION
        == "cecchino_purchasability_v3_fixed_discount_v1"
    )
    assert VALUE_EDGE_FULL_SCORE_PCT == 50.0


def test_analyzable_metrics_include_v3():
    assert "purchasability_v3" in ANALYZABLE_METRICS
    assert _METRIC_LABELS["purchasability_v3"] == "Acquistabilità v3"
    assert "purchasability_v2" in ANALYZABLE_METRICS
    assert "purchasability_v1_1" in ANALYZABLE_METRICS


# --- families ---


def test_families_1x2_separated_from_dc():
    assert market_family_for(SEL_HOME) == "MATCH_WINNER_FT"
    assert market_family_for(SEL_ONE_X) == "DOUBLE_CHANCE"
    assert set(competitors_for_market(SEL_AWAY)) == {SEL_HOME, SEL_DRAW}
    assert SEL_X_TWO not in competitors_for_market(SEL_AWAY)
    assert set(competitors_for_market(SEL_ONE_X)) == {SEL_X_TWO, SEL_ONE_TWO}


def test_linked_context_away_x_two():
    mk, rel = linked_market_key_for(SEL_AWAY)
    assert mk == SEL_X_TWO
    assert rel is not None


# --- gate ---


def test_gate_passed():
    g = evaluate_v3_gate(_row(SEL_AWAY, edge=10, vant=0.05))
    assert g["gate_status"] == "passed"


def test_gate_edge_failed():
    g = evaluate_v3_gate(_row(SEL_AWAY, edge=-1, vant=0.05))
    assert g["gate_status"] == "failed_non_positive_edge"
    by = {SEL_AWAY: _row(SEL_AWAY, edge=-1, vant=0.05)}
    item = _item(SEL_AWAY, by, {SEL_AWAY: _fair(0.3), SEL_HOME: _fair(0.5)})
    assert item["score"] is None
    assert item["class"] is None
    assert item["status"] == "not_applicable"


def test_gate_vantaggio_failed():
    g = evaluate_v3_gate(_row(SEL_AWAY, edge=10, vant=-0.01))
    assert g["gate_status"] == "failed_non_positive_probability_advantage"


def test_gate_multiple_failed():
    g = evaluate_v3_gate(_row(SEL_AWAY, edge=-5, vant=-0.02))
    assert g["gate_status"] == "failed_multiple_non_positive_components"


def test_gate_unavailable_inputs():
    g = evaluate_v3_gate(_row(SEL_AWAY, edge=None, vant=0.05))
    assert g["gate_status"] == "unavailable_inputs"
    g2 = evaluate_v3_gate(_row(SEL_AWAY, edge=10, vant=None))
    assert g2["gate_status"] == "unavailable_inputs"


def test_gate_failed_no_molto_bassa():
    by = {
        SEL_HOME: _row(SEL_HOME, edge=-10, vant=-0.05, prob=0.7),
        SEL_DRAW: _row(SEL_DRAW, edge=1, vant=0.01),
        SEL_AWAY: _row(SEL_AWAY, edge=5, vant=0.02),
    }
    fair = {SEL_HOME: _fair(0.7), SEL_DRAW: _fair(0.15), SEL_AWAY: _fair(0.15)}
    item = _item(SEL_HOME, by, fair)
    assert item["score"] is None
    assert item["class"] is None
    assert item["status"] == "not_applicable"
    assert "Molto Bassa" not in str(item.get("reading_short") or "")


# --- value score ladder ---


def test_value_score_ladder():
    assert compute_value_score(0) == 0
    assert compute_value_score(10) == 20
    assert compute_value_score(20) == 40
    assert compute_value_score(25) == 50
    assert compute_value_score(40) == 80
    assert compute_value_score(50) == 100
    assert compute_value_score(80) == 100  # cap


# --- penalties ---


def test_probability_risk_penalties():
    assert compute_probability_risk_penalty(35)["penalty_points"] == 0
    assert compute_probability_risk_penalty(40)["penalty_points"] == 0
    assert compute_probability_risk_penalty(10)["penalty_points"] == 20
    mid = compute_probability_risk_penalty(22.5)["penalty_points"]
    assert abs(mid - 10.0) < 0.01


def test_opposite_pressure_penalties():
    assert compute_opposite_pressure_penalty(50)["penalty_points"] == 0
    assert compute_opposite_pressure_penalty(40)["penalty_points"] == 0
    assert compute_opposite_pressure_penalty(75)["penalty_points"] == 35
    mid = compute_opposite_pressure_penalty(62.5)["penalty_points"]
    assert abs(mid - 17.5) < 0.01


def test_extreme_divergence_rules():
    # Edge basso → 0
    assert (
        compute_extreme_divergence_penalty(edge_pct=20, probability_cecchino_pct=15)[
            "penalty_points"
        ]
        == 0
    )
    # Prob alta → 0
    assert (
        compute_extreme_divergence_penalty(edge_pct=50, probability_cecchino_pct=40)[
            "penalty_points"
        ]
        == 0
    )
    # Fragile
    p = compute_extreme_divergence_penalty(
        edge_pct=83.04, probability_cecchino_pct=19.645
    )
    assert p["penalty_points"] > 5
    assert p["applied"] is True


def test_family_ambiguity_cases():
    # Tie → 15
    tie = compute_family_ambiguity_penalty(
        selected_edge=20,
        gate_passed_family_edges={SEL_AWAY: 20, SEL_DRAW: 20},
        market_key=SEL_AWAY,
    )
    assert abs(tie["penalty_points"] - 15) < 0.01

    # Gap >= 25 → 0
    clear = compute_family_ambiguity_penalty(
        selected_edge=50,
        gate_passed_family_edges={SEL_AWAY: 50, SEL_DRAW: 20},
        market_key=SEL_AWAY,
    )
    assert clear["penalty_points"] == 0
    assert clear["ambiguity_status"] == "leader_clear"

    # Not leader → >= 15
    sub = compute_family_ambiguity_penalty(
        selected_edge=20,
        gate_passed_family_edges={SEL_AWAY: 83, SEL_DRAW: 20},
        market_key=SEL_DRAW,
    )
    assert sub["penalty_points"] >= 15
    assert sub["ambiguity_status"] == "not_leader"

    # Insufficient
    alone = compute_family_ambiguity_penalty(
        selected_edge=20,
        gate_passed_family_edges={SEL_AWAY: 20},
        market_key=SEL_AWAY,
    )
    assert alone["penalty_points"] == 0
    assert alone["ambiguity_status"] == "insufficient_family_comparison"


def test_quote_real_vs_derived():
    by = {
        SEL_AWAY: _row(SEL_AWAY, edge=10, vant=0.05, prob=0.40),
        SEL_HOME: _row(SEL_HOME, edge=-5, vant=-0.02, prob=0.45),
        SEL_DRAW: _row(SEL_DRAW, edge=-1, vant=-0.01, prob=0.15),
    }
    fair = {
        SEL_AWAY: _fair(0.20),
        SEL_HOME: _fair(0.55),
        SEL_DRAW: _fair(0.25),
    }
    real = _item(SEL_AWAY, by, fair)
    assert real["penalties"]["quote_quality"]["penalty_points"] == 0

    by_dc = {
        SEL_ONE_X: _row(
            SEL_ONE_X, edge=10, vant=0.05, prob=0.60, force_derived_quote=True
        ),
        SEL_X_TWO: _row(SEL_X_TWO, edge=-2, vant=-0.01, prob=0.50),
        SEL_ONE_TWO: _row(SEL_ONE_TWO, edge=-1, vant=-0.01, prob=0.70),
        SEL_HOME: _row(SEL_HOME, edge=-5, vant=-0.02),
        SEL_AWAY: _row(SEL_AWAY, edge=5, vant=0.02),
        SEL_DRAW: _row(SEL_DRAW, edge=1, vant=0.01),
    }
    fair_dc = {
        SEL_ONE_X: _fair(
            0.60, source="derived_double_chance_from_normalized_1x2"
        ),
        SEL_X_TWO: _fair(0.50, source="derived_double_chance_from_normalized_1x2"),
        SEL_ONE_TWO: _fair(0.70, source="derived_double_chance_from_normalized_1x2"),
        SEL_HOME: _fair(0.40),
        SEL_AWAY: _fair(0.35),
        SEL_DRAW: _fair(0.25),
    }
    # ONE_X opposite is AWAY with fair 0.35 → 35% → no opposite pressure
    derived = _item(SEL_ONE_X, by_dc, fair_dc)
    assert derived["status"] == "available"
    assert (
        derived["penalties"]["quote_quality"]["penalty_points"]
        == DERIVED_QUOTE_PENALTY_POINTS
    )


def test_quote_absent_score_unavailable():
    by = {
        SEL_AWAY: _row(SEL_AWAY, edge=10, vant=0.05, prob=0.40, quota_book=None),
        SEL_HOME: _row(SEL_HOME, edge=-5, vant=-0.02),
        SEL_DRAW: _row(SEL_DRAW, edge=-1, vant=-0.01),
    }
    fair = {SEL_AWAY: _fair(0.2), SEL_HOME: _fair(0.55), SEL_DRAW: _fair(0.25)}
    item = _item(SEL_AWAY, by, fair)
    assert item["score"] is None
    assert "quote_unavailable" in item["reason_codes"]


# --- final formula ---


def test_final_formula_not_geometric():
    by = {
        SEL_AWAY: _row(SEL_AWAY, edge=25, vant=0.08, prob=0.40),
        SEL_HOME: _row(SEL_HOME, edge=-10, vant=-0.05, prob=0.45),
        SEL_DRAW: _row(SEL_DRAW, edge=-2, vant=-0.01, prob=0.15),
    }
    fair = {SEL_AWAY: _fair(0.20), SEL_HOME: _fair(0.50), SEL_DRAW: _fair(0.30)}
    item = _item(SEL_AWAY, by, fair)
    assert item["status"] == "available"
    vs = item["value_score"]
    qs = item["quality_score"]
    expected_raw = vs * qs / 100.0
    assert abs(item["raw_score"] - expected_raw) < 0.02
    # Non media geometrica
    geom = math.sqrt(vs * qs)
    assert abs(item["raw_score"] - geom) > 0.5 or abs(vs - qs) < 0.01
    assert item["score"] == round_purchasability_score_half_up(expected_raw)
    assert 0 <= item["score"] <= 100


def test_round_half_up_and_clamp():
    assert round_purchasability_score_half_up(46.5) == 47
    assert round_purchasability_score_half_up(46.4) == 46
    assert round_purchasability_score_half_up(-1) == 0
    assert round_purchasability_score_half_up(150) == 100


# --- regression case ---


def _regression_panel():
    """Caso reale AWAY 9.50 / 5.19."""
    home = _row(
        SEL_HOME,
        rating=40,
        edge=-15.0,
        vant=-0.08,
        prob=0.60,
        quota_book=1.35,
        quota_cecchino=1.67,
    )
    draw = _row(
        SEL_DRAW,
        rating=55,
        edge=20.0,
        vant=0.04,
        prob=0.20389,
        quota_book=5.0,
        quota_cecchino=4.17,
    )
    away = _row(
        SEL_AWAY,
        rating=85,
        edge=83.04,
        vant=0.0874,
        prob=0.19645,
        quota_book=9.50,
        quota_cecchino=5.19,
    )
    by = {SEL_HOME: home, SEL_DRAW: draw, SEL_AWAY: away}
    # HOME fair ≈ 75.707%
    fair = {
        SEL_HOME: _fair(0.75707),
        SEL_DRAW: _fair(0.10),
        SEL_AWAY: _fair(0.14293),
    }
    model = {
        SEL_HOME: 0.60,
        SEL_DRAW: 0.20389,
        SEL_AWAY: 0.19645,
    }
    return by, fair, model


def test_regression_away_approx_47():
    by, fair, model = _regression_panel()
    item = _item(SEL_AWAY, by, fair, model)
    assert item["gate_status"] == "passed"
    assert item["value_score"] == 100
    pens = item["penalties"]
    assert abs(pens["probability_risk"]["penalty_points"] - 12.284) < 0.05
    assert pens["opposite_market_pressure"]["penalty_points"] == OPPOSITE_PRESSURE_MAX_POINTS
    assert abs(pens["extreme_divergence"]["penalty_points"] - 5.886) < 0.1
    assert pens["family_ambiguity"]["penalty_points"] == 0
    assert abs(item["quality_score"] - 46.83) < 0.2
    assert abs(item["raw_score"] - 46.83) < 0.2
    assert item["score"] == 47
    assert item["class"] == "Media"
    # Linked X_TWO diagnostic, not in family competitors
    assert item["linked_market_context"]["linked_market_key"] == SEL_X_TWO
    assert item["linked_market_context"]["used_in_score"] is False
    assert SEL_X_TWO not in item["family_competitors"]
    # Reading deterministica
    assert "valore teorico molto alto" in (item["reading_detailed"] or "").lower() or (
        "valore teorico" in (item["reading_detailed"] or "").lower()
    )
    assert "ottima giocata" not in (item["reading_detailed"] or "").lower()


def test_regression_draw_low_score():
    by, fair, model = _regression_panel()
    item = _item(SEL_DRAW, by, fair, model)
    assert item["gate_status"] == "passed"
    assert item["value_score"] == 40
    assert item["penalties"]["opposite_market_pressure"]["penalty_points"] == 35
    assert item["penalties"]["family_ambiguity"]["penalty_points"] >= 15
    assert item["selected_is_family_edge_leader"] is False
    assert item["score"] is not None
    assert item["score"] < 34
    assert abs(item["score"] - 11) <= 2


def test_regression_home_not_applicable():
    by, fair, model = _regression_panel()
    item = _item(SEL_HOME, by, fair, model)
    assert item["gate_status"] in (
        "failed_non_positive_edge",
        "failed_non_positive_probability_advantage",
        "failed_multiple_non_positive_components",
    )
    assert item["score"] is None
    assert item["class"] is None
    assert item["status"] == "not_applicable"


# --- anti double counting / no historical ---


def test_no_rating_vantaggio_score_acquisto_in_score():
    by, fair, model = _regression_panel()
    a = _item(SEL_AWAY, by, fair, model)
    by2 = {k: dict(v) for k, v in by.items()}
    by2[SEL_AWAY]["rating"] = 1
    by2[SEL_AWAY]["score_acquisto"] = 99
    by2[SEL_AWAY]["vantaggio_prob"] = 0.50  # still positive gate
    b = _item(SEL_AWAY, by2, fair, model)
    # Same edge/prob/opposite/family → same score (vantaggio only gate, not weight)
    assert a["value_score"] == b["value_score"]
    assert a["score"] == b["score"]
    assert a["dependency_meta"]["rating_used_in_score"] is False
    assert a["dependency_meta"]["probability_advantage_used_as_weight"] is False
    assert a["dependency_meta"]["score_acquisto_used"] is False
    assert a["historical_profile_used"] is False
    assert a["fixed_scales_used"] is True


def test_payload_rejects_historical_norm_fields():
    batch = calculate_purchasability_v3_batch(
        kpi_panel={
            "rows": [
                _row(SEL_AWAY, edge=10, vant=0.05, prob=0.40),
                _row(SEL_HOME, edge=-5, vant=-0.02, prob=0.45),
                _row(SEL_DRAW, edge=-1, vant=-0.01, prob=0.15),
            ]
        }
    )
    raw = json.dumps(batch)
    assert "normalization_profile" not in raw
    assert "historical_cap" not in raw
    assert '"cap_source"' not in raw
    assert "sample_total" not in raw or batch.get("historical_profile_used") is False
    assert batch["historical_profile_used"] is False
    assert batch["fixed_scales_used"] is True
    snap = build_purchasability_preview_v3_snapshot(batch=batch)
    snap_raw = json.dumps(snap)
    assert "normalization_profile" not in snap_raw
    assert snap["parallel_candidate"] is True
    assert snap["current_operational_version"] is False
    assert snap["snapshot_version"] == PURCHASABILITY_V3_SNAPSHOT_VERSION


def test_no_post_match_fields():
    batch = calculate_purchasability_v3_batch(
        kpi_panel={"rows": [_row(SEL_AWAY), _row(SEL_HOME), _row(SEL_DRAW)]}
    )
    snap = build_purchasability_preview_v3_snapshot(batch=batch)
    assert snap["contains_post_match_fields"] is False
    assert snap["pre_match_only"] is True


def test_snapshot_parallel_does_not_touch_v1_v2():
    from datetime import datetime, timezone

    output = {
        "purchasability_preview": {"candidate_version": "v1_keep", "items": []},
        "purchasability_preview_v2": {
            "snapshot_version": "cecchino_purchasability_snapshot_v2",
            "candidate_version": "cecchino_purchasability_v2_candidate_1",
            "items": [],
        },
    }
    panel = {
        "rows": [
            _row(SEL_AWAY, edge=10, vant=0.05, prob=0.40),
            _row(SEL_HOME, edge=-5, vant=-0.02, prob=0.45),
            _row(SEL_DRAW, edge=-1, vant=-0.01, prob=0.15),
        ]
    }
    snap_at = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    kick = datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc)
    attach_purchasability_preview_v3_to_output(
        cecchino_output=output,
        kpi_panel=panel,
        fixture_meta={"today_fixture_id": 1, "kickoff": kick},
        snapshot_info={
            "snapshot_at": snap_at,
            "snapshot_timestamp_verified": True,
        },
    )
    assert "purchasability_preview_v3" in output
    assert output["purchasability_preview"]["candidate_version"] == "v1_keep"
    assert (
        output["purchasability_preview_v2"]["candidate_version"]
        == "cecchino_purchasability_v2_candidate_1"
    )


def test_away_not_compared_with_x_two():
    by = {
        SEL_AWAY: _row(SEL_AWAY, edge=30, vant=0.08, prob=0.35),
        SEL_HOME: _row(SEL_HOME, edge=-10, vant=-0.05, prob=0.45),
        SEL_DRAW: _row(SEL_DRAW, edge=-2, vant=-0.01, prob=0.20),
        SEL_X_TWO: _row(SEL_X_TWO, edge=90, vant=0.20, prob=0.55),
    }
    fair = {
        SEL_AWAY: _fair(0.20),
        SEL_HOME: _fair(0.50),
        SEL_DRAW: _fair(0.30),
        SEL_X_TWO: _fair(0.55),
    }
    item = _item(SEL_AWAY, by, fair)
    assert SEL_X_TWO not in item["family_competitors"]
    assert item["linked_market_context"]["linked_market_key"] == SEL_X_TWO
    assert item["linked_markets_used_in_score"] is False


def test_audit_explain_v3_complete():
    by, fair, model = _regression_panel()
    item = _item(SEL_AWAY, by, fair, model)
    expl = _explain_purchasability_v3(
        by[SEL_AWAY],
        "2",
        item,
        item,
        {
            "candidate_version": PURCHASABILITY_V3_CANDIDATE_VERSION,
            "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
        },
    )
    assert expl["metric_key"] == "purchasability_v3"
    assert "gate" in expl
    assert "value" in expl
    assert "penalties_table" in expl
    assert "family_comparison" in expl
    assert "opposite_market" in expl
    assert "linked_market_context" in expl
    assert "final_calculation" in expl
    assert "data_origin" in expl
    assert "simple_explanation" in expl
    assert expl["historical_profile_used"] is False
    assert expl["stored_result"] == 47


def test_deterministic_natural_language():
    by, fair, model = _regression_panel()
    a = _item(SEL_AWAY, by, fair, model)
    b = _item(SEL_AWAY, by, fair, model)
    assert a["reading_detailed"] == b["reading_detailed"]
    assert a["score"] == b["score"]


def test_unsupported_ht_market():
    by = {SEL_OVER_PT_1_5: _row(SEL_OVER_PT_1_5, edge=10, vant=0.05)}
    item = _item(SEL_OVER_PT_1_5, by, {SEL_OVER_PT_1_5: _fair(0.5)})
    assert item["gate_status"] == "unsupported_market"
    assert item["score"] is None
    assert item["status"] == "not_applicable"
