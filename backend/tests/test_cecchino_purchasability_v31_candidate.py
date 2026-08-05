"""Test Acquistabilità V3.1 shadow — copertura, complementi, gate, HR, regressione V3."""

from __future__ import annotations

from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_CANDIDATE_NAME,
    PURCHASABILITY_V3_FORMULA_VERSION,
)
from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_CANDIDATE_NAME,
    PURCHASABILITY_V31_FORMULA_CONFIG_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION,
    PURCHASABILITY_V31_REGISTRY_STATUS,
)
from app.services.cecchino.cecchino_historical_reliability import MIN_SAMPLE
from app.services.cecchino.cecchino_kpi_explanations import ANALYZABLE_METRICS
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_candidate import (
    round_purchasability_score_half_up,
)
from app.services.cecchino.cecchino_purchasability_v3_candidate import (
    calculate_purchasability_v3_batch,
)
from app.services.cecchino.cecchino_purchasability_v31_candidate import (
    RATING_MIN_PURCHASE_SCOPE,
    calculate_purchasability_v31_batch,
    calculate_purchasability_v31_item,
    evaluate_v31_gate,
    resolve_execution_quote,
)
from app.services.cecchino.cecchino_purchasability_v31_opposition import (
    SUPPORTED_V31_MARKETS,
    complement_definition_for,
    complement_selection_keys,
    family_ambiguity_status_default,
    is_v31_supported_market,
    market_family_for,
    resolve_mathematical_complement,
)
from app.services.cecchino.cecchino_purchasability_v31_snapshot import (
    attach_purchasability_preview_v31_to_output,
    build_purchasability_preview_v31_snapshot,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)


def _row(
    mk: str,
    *,
    rating: float | None = 70,
    edge: float | None = 20.0,
    vant: float | None = 0.08,
    prob: float | None = 0.40,
    quota_book: float | None = 2.5,
    quota_cecchino: float | None = 2.0,
    book_source: str = "betfair_raw_match_winner",
    derived: bool = False,
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
        "book_source": book_source,
    }
    if derived:
        out["derived_quote"] = True
        out["force_derived_quote"] = True
        out["book_source"] = "derived_from_betfair_1x2"
    return out


def _fair(
    prob: float,
    *,
    verified: bool = True,
    source: str = "normalized_1x2_market",
    normalized_map: dict | None = None,
    overround: float | None = 1.05,
) -> dict:
    payload = {"status": "ok", "overround": overround}
    if normalized_map:
        payload["normalized_map"] = normalized_map
    return {
        "fair_book_probability": prob,
        "fair_book_probability_verified": verified,
        "fair_book_probability_source": source,
        "raw_implied_probability": prob,
        "market_overround": overround,
        "normalization_payload": payload,
        "normalization_status": "ok" if verified else "fallback_raw_implied",
    }


def _hr(
    *,
    score: float = 80,
    status: str = "ok",
    sample: int = 50,
) -> dict:
    return {
        "status": status,
        "score": score,
        "class": "Buona",
        "version": "cecchino_historical_reliability_v1_1",
        "selected_sample_size": sample,
        "local_sample_size": sample,
        "global_sample_size": sample,
        "rating_band": "70-79",
        "cohort_scope": "same_competition",
        "roi": 0.05,
        "realized_margin": 0.02,
        "stability_ratio": 0.6,
        "sample_confidence": min(1.0, sample / 100.0),
        "wins": 20,
        "losses": 25,
        "voids": 5,
    }


def _item(
    mk: str,
    by_mk: dict,
    fair_by: dict,
    hr: dict | None = None,
    *,
    fixture_meta: dict | None = None,
):
    model = {k: r.get("prob_cecchino") for k, r in by_mk.items()}
    gate_by = {k: evaluate_v31_gate(r) for k, r in by_mk.items()}
    edge_by = {k: r.get("edge_pct") for k, r in by_mk.items()}
    return calculate_purchasability_v31_item(
        mk,
        by_mk.get(mk) or {},
        by_mk,
        fair_by=fair_by,
        model_probs=model,
        historical_reliability_item=hr,
        gate_by_market=gate_by,
        edge_by_market=edge_by,
        fixture_meta=fixture_meta
        or {
            "kickoff": "2026-08-05T18:00:00+00:00",
            "snapshot_timestamp_verified": True,
            "kickoff_required": True,
        },
    )


# --- coverage ---


def test_all_19_markets_supported():
    assert len(SUPPORTED_V31_MARKETS) == 19
    assert set(SUPPORTED_V31_MARKETS) == set(PANEL_MARKET_KEYS)
    for mk in PANEL_MARKET_KEYS:
        assert is_v31_supported_market(mk)


def test_batch_never_unsupported_market():
    rows = [
        _row(SEL_HOME, quota_book=2.1),
        _row(SEL_DRAW, quota_book=3.4, edge=5),
        _row(SEL_AWAY, quota_book=3.8, edge=3),
        _row(SEL_HOME_PT, book_source="betfair_raw_first_half_match_winner"),
        _row(SEL_DRAW_PT, book_source="betfair_raw_first_half_match_winner"),
        _row(SEL_AWAY_PT, book_source="betfair_raw_first_half_match_winner"),
        _row(SEL_ONE_X, book_source="betfair_raw_double_chance"),
        _row(SEL_X_TWO, book_source="betfair_raw_double_chance"),
        _row(SEL_ONE_TWO, book_source="betfair_raw_double_chance"),
        _row(SEL_OVER_1_5, book_source="betfair_raw_over_under"),
        _row(SEL_UNDER_1_5, book_source="betfair_raw_over_under"),
        _row(SEL_OVER_2_5, book_source="betfair_raw_over_under"),
        _row(SEL_UNDER_2_5, book_source="betfair_raw_over_under"),
        _row(SEL_OVER_3_5, book_source="betfair_raw_over_under"),
        _row(SEL_UNDER_3_5, book_source="betfair_raw_over_under"),
        _row(SEL_OVER_PT_0_5, book_source="betfair_raw_over_under_first_half"),
        _row(SEL_UNDER_PT_0_5, book_source="betfair_raw_over_under_first_half"),
        _row(SEL_OVER_PT_1_5, book_source="betfair_raw_over_under_first_half"),
        _row(SEL_UNDER_PT_1_5, book_source="betfair_raw_over_under_first_half"),
    ]
    panel = {"rows": rows}
    hr_map = {r["market_key"]: _hr() for r in rows}
    batch = calculate_purchasability_v31_batch(
        kpi_panel=panel,
        fixture_meta={
            "kickoff": "2026-08-05T18:00:00+00:00",
            "snapshot_timestamp_verified": True,
            "kickoff_required": True,
            "today_fixture_id": 1,
        },
        historical_by_market=hr_map,
    )
    assert len(batch["items"]) == 19
    for it in batch["items"]:
        assert "unsupported_market" not in (it.get("reason_codes") or [])
        assert it.get("status") in ("score", "gate_failed", "non_calculable")


# --- complements ---


def test_complements_match_winner_ft():
    for mk, p in ((SEL_HOME, 0.45), (SEL_DRAW, 0.28), (SEL_AWAY, 0.27)):
        res = resolve_mathematical_complement(mk, selected_fair_probability=p)
        assert abs(res["complement_fair_probability"] - (1 - p)) < 1e-9
        assert res["complement_sum_ok"] is True


def test_complements_match_winner_ht():
    for mk in (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT):
        res = resolve_mathematical_complement(mk, selected_fair_probability=0.33)
        assert abs(res["complement_fair_probability"] - 0.67) < 1e-9
        assert res["complement_sum_ok"] is True


def test_complements_double_chance():
    assert complement_selection_keys(SEL_ONE_X) == [SEL_AWAY]
    assert complement_selection_keys(SEL_X_TWO) == [SEL_HOME]
    assert complement_selection_keys(SEL_ONE_TWO) == [SEL_DRAW]
    norm = {SEL_HOME: 0.4, SEL_DRAW: 0.3, SEL_AWAY: 0.3}
    res = resolve_mathematical_complement(
        SEL_ONE_X,
        selected_fair_probability=0.7,
        normalized_fair_probabilities=norm,
    )
    assert abs(res["complement_fair_probability"] - 0.3) < 1e-9


def test_complements_over_under_pairs():
    pairs = [
        (SEL_OVER_1_5, SEL_UNDER_1_5),
        (SEL_OVER_2_5, SEL_UNDER_2_5),
        (SEL_OVER_3_5, SEL_UNDER_3_5),
        (SEL_OVER_PT_0_5, SEL_UNDER_PT_0_5),
        (SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5),
    ]
    for over, under in pairs:
        assert complement_selection_keys(over) == [under]
        assert complement_selection_keys(under) == [over]
        res = resolve_mathematical_complement(over, selected_fair_probability=0.55)
        assert abs(res["complement_fair_probability"] - 0.45) < 1e-9
        assert res["complement_sum_ok"] is True


def test_family_ambiguity_not_on_dc_or_ou():
    assert family_ambiguity_status_default("DOUBLE_CHANCE_FT") == (
        "not_applicable_overlapping_outcomes"
    )
    assert family_ambiguity_status_default("GOALS_FT_2_5") == (
        "not_applicable_binary_complement"
    )
    assert market_family_for(SEL_HOME) == "MATCH_WINNER_FT"
    assert market_family_for(SEL_HOME_PT) == "MATCH_WINNER_HT"


# --- gate ---


def test_gate_edge_non_positive():
    g = evaluate_v31_gate(_row(SEL_HOME, edge=0, vant=0.05, rating=60))
    assert g["gate_status"] == "gate_failed"
    assert "failed_non_positive_edge" in g["gate_reason_codes"]


def test_gate_vantaggio_non_positive():
    g = evaluate_v31_gate(_row(SEL_HOME, edge=10, vant=0, rating=60))
    assert g["gate_status"] == "gate_failed"
    assert "failed_non_positive_probability_advantage" in g["gate_reason_codes"]


def test_gate_rating_below_50():
    g = evaluate_v31_gate(_row(SEL_HOME, edge=10, vant=0.05, rating=49))
    assert g["gate_status"] == "gate_failed"
    assert "rating_below_purchase_scope" in g["gate_reason_codes"]
    assert RATING_MIN_PURCHASE_SCOPE == 50


def test_gate_null_inputs_non_calculable():
    g = evaluate_v31_gate(_row(SEL_HOME, edge=None, vant=0.05, rating=60))
    assert g["gate_status"] == "unavailable_inputs"
    assert g["item_status"] == "non_calculable"
    g2 = evaluate_v31_gate(_row(SEL_HOME, edge=10, vant=None, rating=60))
    assert g2["item_status"] == "non_calculable"
    g3 = evaluate_v31_gate(_row(SEL_HOME, edge=10, vant=0.05, rating=None))
    assert g3["item_status"] == "non_calculable"


# --- quotes ---


def test_derived_quote_non_calculable():
    by = {
        SEL_ONE_X: _row(SEL_ONE_X, derived=True),
        SEL_HOME: _row(SEL_HOME),
        SEL_DRAW: _row(SEL_DRAW),
        SEL_AWAY: _row(SEL_AWAY),
    }
    fair = {
        SEL_ONE_X: _fair(
            0.7,
            source="derived_double_chance_from_normalized_1x2",
            normalized_map={SEL_HOME: 0.4, SEL_DRAW: 0.3, SEL_AWAY: 0.3},
        ),
        SEL_HOME: _fair(0.4),
        SEL_DRAW: _fair(0.3),
        SEL_AWAY: _fair(0.3),
    }
    it = _item(SEL_ONE_X, by, fair, _hr())
    assert it["status"] == "non_calculable"
    assert it["score"] is None
    assert "derived_quote_not_executable" in it["reason_codes"]


def test_real_dc_quote_can_score():
    by = {
        SEL_ONE_X: _row(
            SEL_ONE_X, book_source="betfair_raw_double_chance", edge=25, rating=70
        ),
        SEL_HOME: _row(SEL_HOME, edge=10),
        SEL_DRAW: _row(SEL_DRAW, edge=5),
        SEL_AWAY: _row(SEL_AWAY, edge=3),
    }
    fair = {
        SEL_ONE_X: _fair(
            0.7,
            source="derived_double_chance_from_normalized_1x2",
            normalized_map={SEL_HOME: 0.4, SEL_DRAW: 0.3, SEL_AWAY: 0.3},
        ),
        SEL_HOME: _fair(0.4),
        SEL_DRAW: _fair(0.3),
        SEL_AWAY: _fair(0.3),
    }
    it = _item(SEL_ONE_X, by, fair, _hr(score=100))
    assert it["status"] == "score"
    assert it["score"] is not None
    assert it["input"]["execution_quote_real"] is True


def test_missing_book_quote_non_calculable():
    by = {SEL_HOME: _row(SEL_HOME, quota_book=None)}
    fair = {SEL_HOME: _fair(0.4)}
    it = _item(SEL_HOME, by, fair, _hr())
    assert it["status"] == "non_calculable"
    assert "book_quote_unavailable" in it["reason_codes"]


# --- historical ---


def test_historical_factor_math_deterministic():
    """theoretical_raw=80, historical=25 → raw=20, score=20."""
    by = {
        SEL_HOME: _row(SEL_HOME, edge=40, prob=0.50, rating=70),
        SEL_DRAW: _row(SEL_DRAW, edge=5),
        SEL_AWAY: _row(SEL_AWAY, edge=5),
    }
    fair = {
        SEL_HOME: _fair(0.35, normalized_map={SEL_HOME: 0.35, SEL_DRAW: 0.33, SEL_AWAY: 0.32}),
        SEL_DRAW: _fair(0.33),
        SEL_AWAY: _fair(0.32),
    }
    # Force theoretical path by inspecting formula with known HR
    it = _item(SEL_HOME, by, fair, _hr(score=25, sample=40))
    assert it["status"] == "score"
    theor = it["theoretical"]["theoretical_raw_score"]
    factor = it["historical"]["historical_factor"]
    expected_raw = theor * (25 / 100.0)
    assert abs(factor - 0.25) < 1e-9
    assert abs(it["raw_score_v31"] - expected_raw) < 1e-3
    assert it["score_v31"] == round_purchasability_score_half_up(expected_raw)


def test_historical_scores_scale():
    by = {
        SEL_HOME: _row(SEL_HOME, edge=40, prob=0.55, rating=75),
        SEL_DRAW: _row(SEL_DRAW, edge=2),
        SEL_AWAY: _row(SEL_AWAY, edge=2),
    }
    fair = {
        SEL_HOME: _fair(0.30, normalized_map={SEL_HOME: 0.30, SEL_DRAW: 0.35, SEL_AWAY: 0.35}),
        SEL_DRAW: _fair(0.35),
        SEL_AWAY: _fair(0.35),
    }
    scores = {}
    for hs in (10, 44, 50, 85, 100):
        it = _item(SEL_HOME, by, fair, _hr(score=hs))
        assert it["status"] == "score"
        scores[hs] = it["score"]
    assert scores[10] < scores[44] < scores[85] <= scores[100]
    assert scores[10] < 30  # storico basso impedisce score elevato


def test_historical_insufficient():
    by = {SEL_HOME: _row(SEL_HOME), SEL_DRAW: _row(SEL_DRAW), SEL_AWAY: _row(SEL_AWAY)}
    fair = {
        SEL_HOME: _fair(0.4, normalized_map={SEL_HOME: 0.4, SEL_DRAW: 0.3, SEL_AWAY: 0.3}),
        SEL_DRAW: _fair(0.3),
        SEL_AWAY: _fair(0.3),
    }
    it = _item(
        SEL_HOME,
        by,
        fair,
        _hr(status="insufficient_data", sample=MIN_SAMPLE - 1, score=None),  # type: ignore[arg-type]
    )
    assert it["status"] == "non_calculable"
    assert "historical_sample_insufficient" in it["reason_codes"]


def test_historical_absent():
    by = {SEL_HOME: _row(SEL_HOME), SEL_DRAW: _row(SEL_DRAW), SEL_AWAY: _row(SEL_AWAY)}
    fair = {
        SEL_HOME: _fair(0.4, normalized_map={SEL_HOME: 0.4, SEL_DRAW: 0.3, SEL_AWAY: 0.3}),
        SEL_DRAW: _fair(0.3),
        SEL_AWAY: _fair(0.3),
    }
    it = _item(SEL_HOME, by, fair, None)
    assert it["status"] == "non_calculable"
    assert "historical_reliability_unavailable" in it["reason_codes"]


def test_gate_failed_skips_historical():
    by = {
        SEL_HOME: _row(SEL_HOME, edge=-5, rating=70),
        SEL_DRAW: _row(SEL_DRAW),
        SEL_AWAY: _row(SEL_AWAY),
    }
    fair = {
        SEL_HOME: _fair(0.4, normalized_map={SEL_HOME: 0.4, SEL_DRAW: 0.3, SEL_AWAY: 0.3}),
        SEL_DRAW: _fair(0.3),
        SEL_AWAY: _fair(0.3),
    }
    it = _item(SEL_HOME, by, fair, _hr(score=10))
    assert it["status"] == "gate_failed"
    assert it.get("historical") == {} or not it.get("historical", {}).get(
        "historical_factor"
    )


# --- incomplete fair ---


def test_incomplete_fair_non_calculable():
    by = {SEL_HOME: _row(SEL_HOME)}
    fair = {SEL_HOME: _fair(0.4, verified=False)}
    it = _item(SEL_HOME, by, fair, _hr())
    assert it["status"] == "non_calculable"
    codes = it["reason_codes"]
    assert (
        "fair_book_probability_unavailable" in codes
        or "fair_book_complete_set_incomplete" in codes
    )


# --- regression V3 ---


def test_v3_regression_unchanged_on_same_inputs():
    rows = [
        _row(SEL_HOME, edge=12, vant=0.06, prob=0.42, quota_book=2.3),
        _row(SEL_DRAW, edge=4, vant=0.02, prob=0.28, quota_book=3.4),
        _row(SEL_AWAY, edge=8, vant=0.04, prob=0.30, quota_book=3.5),
        _row(SEL_OVER_2_5, edge=15, vant=0.07, prob=0.48, quota_book=2.1),
        _row(SEL_UNDER_2_5, edge=3, vant=0.01, prob=0.40, quota_book=1.85),
        _row(SEL_ONE_X, edge=10, vant=0.05, prob=0.65, quota_book=1.4),
        _row(SEL_X_TWO, edge=2, vant=0.01, prob=0.55, quota_book=1.5),
        _row(SEL_ONE_TWO, edge=6, vant=0.03, prob=0.70, quota_book=1.35),
    ]
    panel = {"rows": rows}
    b1 = calculate_purchasability_v3_batch(
        kpi_panel=panel, fixture_meta={"today_fixture_id": 99}
    )
    b2 = calculate_purchasability_v3_batch(
        kpi_panel=panel, fixture_meta={"today_fixture_id": 99}
    )
    assert b1["formula_version"] == PURCHASABILITY_V3_FORMULA_VERSION
    assert b1["candidate_name"] == PURCHASABILITY_V3_CANDIDATE_NAME
    assert [
        (i["market_key"], i["status"], i.get("score"), i.get("gate_status"))
        for i in b1["items"]
    ] == [
        (i["market_key"], i["status"], i.get("score"), i.get("gate_status"))
        for i in b2["items"]
    ]


def test_v31_versions_distinct_from_v3():
    assert PURCHASABILITY_V31_FORMULA_VERSION != PURCHASABILITY_V3_FORMULA_VERSION
    assert PURCHASABILITY_V31_CANDIDATE_NAME == "purchasability_v31_shadow"
    assert PURCHASABILITY_V31_REGISTRY_STATUS == "shadow_candidate"
    assert PURCHASABILITY_V31_FORMULA_CONFIG_VERSION == "fixed_discount_v31_empirical_v1"
    assert "purchasability_v31" in ANALYZABLE_METRICS


def test_attach_preserves_v3():
    output = {
        "purchasability_preview_v3": {
            "snapshot_version": "cecchino_purchasability_snapshot_v3",
            "candidate_version": "cecchino_purchasability_v3_candidate_1",
            "items": [{"market_key": SEL_HOME, "score": 55}],
            "status": "ok",
        }
    }
    panel = {
        "rows": [
            _row(SEL_HOME),
            _row(SEL_DRAW),
            _row(SEL_AWAY),
        ]
    }
    attach_purchasability_preview_v31_to_output(
        cecchino_output=output,
        kpi_panel=panel,
        fixture_meta={
            "today_fixture_id": 1,
            "kickoff": "2026-08-10T18:00:00+00:00",
        },
        snapshot_info={
            "snapshot_at": "2026-08-10T12:00:00+00:00",
            "snapshot_timestamp_verified": True,
        },
        historical_by_market={
            SEL_HOME: _hr(),
            SEL_DRAW: _hr(),
            SEL_AWAY: _hr(),
        },
    )
    assert "purchasability_preview_v3" in output
    assert output["purchasability_preview_v3"]["items"][0]["score"] == 55
    assert "purchasability_preview_v31" in output
    snap = output["purchasability_preview_v31"]
    assert snap["candidate_name"] == PURCHASABILITY_V31_CANDIDATE_NAME
    assert snap["current_operational_version"] is False
    assert snap["shadow_candidate"] is True
    assert snap.get("input_fingerprint")


def test_comparison_block_present():
    rows = [_row(SEL_HOME), _row(SEL_DRAW), _row(SEL_AWAY)]
    panel = {"rows": rows}
    v3 = calculate_purchasability_v3_batch(kpi_panel=panel)
    v3_by = {it["market_key"]: it for it in v3["items"]}
    batch = calculate_purchasability_v31_batch(
        kpi_panel=panel,
        fixture_meta={
            "kickoff": "2026-08-05T18:00:00+00:00",
            "snapshot_timestamp_verified": True,
            "kickoff_required": True,
        },
        historical_by_market={SEL_HOME: _hr(), SEL_DRAW: _hr(), SEL_AWAY: _hr()},
        v3_items_by_market=v3_by,
    )
    home = next(it for it in batch["items"] if it["market_key"] == SEL_HOME)
    assert "comparison_with_v3" in home
    assert "shadow_summary" in batch
    assert batch["shadow_summary"]["rows_v31_supported"] >= 3


def test_complement_definition_audit_fields():
    assert "1 - p_fair_HOME" in complement_definition_for(SEL_HOME)
    q = resolve_execution_quote(None, _row(SEL_HOME, quota_book=None))
    assert q["reason_code"] == "book_quote_unavailable"
