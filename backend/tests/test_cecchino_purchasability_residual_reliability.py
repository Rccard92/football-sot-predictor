"""Test Fase 2A.4 — residual reliability Indice di Acquistabilità."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.cecchino.cecchino_purchasability_audit import (
    AUDIT_VERSION,
    DATASET_VERSION,
    make_json_safe,
)
from app.services.cecchino.cecchino_purchasability_fair_book import (
    SOURCE_1X2,
    SOURCE_DC_DERIVED,
    SOURCE_RAW_SECONDARY,
    SOURCE_TWO_WAY,
    cross_market_snapshot_key,
    resolve_fair_book_probability,
    resolve_fair_for_rows,
    same_market_sibling_key,
)
from app.services.cecchino.cecchino_purchasability_research_jobs import (
    MODE_RESIDUAL,
    MODE_STATISTICAL,
    filters_hash_for,
)
from app.services.cecchino.cecchino_purchasability_residual_reliability import (
    MIN_TEMPORAL_SPAN_DAYS,
    RESIDUAL_RELIABILITY_VERSION,
    SPECS,
    _baseline_prediction,
    _residual_row,
    _temporal_span,
    build_oof_evaluation_mask,
    build_purchasability_residual_reliability,
)
from app.services.cecchino.cecchino_purchasability_statistical_research import (
    STAT_VERSION,
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
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)


def _row(
    *,
    fid: int,
    market: str,
    odds: float,
    day: int = 1,
    bookmaker: str = "BM",
    source: str = "betfair",
    snapshot_hour: int = 10,
    model_p: float | None = None,
    won: bool = True,
    void: bool = False,
    settled_core: bool = True,
) -> dict:
    snap = datetime(2026, 1, day, snapshot_hour, 0, tzinfo=timezone.utc)
    kick = datetime(2026, 1, day, 18, 0, tzinfo=timezone.utc)
    status = "void" if void else ("won" if won else "lost")
    raw = 1.0 / odds if odds > 0 else None
    family = {
        SEL_HOME: "match_winner",
        SEL_DRAW: "match_winner",
        SEL_AWAY: "match_winner",
        SEL_ONE_X: "double_chance",
        SEL_X_TWO: "double_chance",
        SEL_ONE_TWO: "double_chance",
        SEL_OVER_2_5: "over_under",
        SEL_UNDER_2_5: "over_under",
        SEL_OVER_PT_1_5: "over_under",
        SEL_UNDER_PT_1_5: "over_under",
    }.get(market, "match_winner")
    period = "HT" if "PT" in market else "FT"
    line = None
    if market in (SEL_OVER_2_5, SEL_UNDER_2_5):
        line = 2.5
    if market in (SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5):
        line = 1.5
    mp = model_p if model_p is not None else (0.55 if won else 0.4)
    return {
        "today_fixture_id": fid,
        "canonical_row_key": f"k-{fid}-{market}-{day}-{snapshot_hour}",
        "raw_market_code": market,
        "selection": market,
        "canonical_market_family": family,
        "period": period,
        "line": line,
        "scan_date": f"2026-01-{day:02d}",
        "snapshot_at": snap.isoformat(),
        "kickoff": kick.isoformat(),
        "competition_id": 1,
        "odds": odds,
        "raw_book_implied_probability": raw,
        "model_probability": mp,
        "probability_advantage": mp - (raw or 0),
        "edge": (mp * odds - 1) * 100,
        "score": 50.0,
        "rating": 60.0,
        "bookmaker_name": bookmaker,
        "odds_source": source,
        "book_source": source,
        "snapshot_timestamp_verified": True,
        "snapshot_before_kickoff": True,
        "no_post_match_data_in_features": True,
        "leakage_status": "safe",
        "is_settled_core": settled_core,
        "settlement_status": status,
        "selection_won": won and not void,
        "selection_lost": (not won) and not void,
        "selection_void": void,
        "unit_stake_profit": 0.0 if void else (odds - 1.0 if won else -1.0),
        "favourite_intensity_book": 0.1,
        "favourite_intensity_model": 0.12,
        "favourite_alignment": "aligned",
        "book_favourite": SEL_HOME,
        "model_favourite": SEL_HOME,
        "comparator_odds_payload": {},
        "comparator_model_probability_payload": {},
        "comparator_book_probability_payload": {},
        "complement_selection": None,
        "market_overround": None,
    }


def _1x2_siblings(fid: int = 1, day: int = 1, **kw) -> list[dict]:
    src = kw.pop("source", "betfair_raw_match_winner")
    return [
        _row(fid=fid, market=SEL_HOME, odds=2.10, day=day, source=src, **kw),
        _row(fid=fid, market=SEL_DRAW, odds=3.40, day=day, source=src, **kw),
        _row(fid=fid, market=SEL_AWAY, odds=3.60, day=day, source=src, **kw),
    ]


# --- Fair book ---


def test_v2a4_01_1x2_normalized():
    sibs = _1x2_siblings()
    out = resolve_fair_book_probability(sibs[0], sibs)
    assert out["fair_book_probability_verified"] is True
    assert out["fair_book_probability_source"] == SOURCE_1X2
    probs = [resolve_fair_book_probability(r, sibs)["fair_book_probability"] for r in sibs]
    assert abs(sum(probs) - 1.0) < 1e-9


def test_v2a4_02_ou_normalized_same_line():
    sibs = [
        _row(fid=1, market=SEL_OVER_2_5, odds=1.90),
        _row(fid=1, market=SEL_UNDER_2_5, odds=1.95),
    ]
    out = resolve_fair_book_probability(sibs[0], sibs)
    assert out["fair_book_probability_source"] == SOURCE_TWO_WAY
    assert out["fair_book_probability_verified"] is True


def test_v2a4_03_ou_different_periods_not_mixed():
    sibs = [
        _row(fid=1, market=SEL_OVER_2_5, odds=1.90),
        _row(fid=1, market=SEL_UNDER_PT_1_5, odds=1.95),
    ]
    out = resolve_fair_book_probability(sibs[0], sibs)
    assert out["fair_book_probability_verified"] is False
    assert out["fair_book_probability_source"] == SOURCE_RAW_SECONDARY


def test_v2a4_04_06_dc_derived_from_1x2():
    mw = _1x2_siblings()
    fair_h = resolve_fair_book_probability(mw[0], mw)["fair_book_probability"]
    fair_d = resolve_fair_book_probability(mw[1], mw)["fair_book_probability"]
    fair_a = resolve_fair_book_probability(mw[2], mw)["fair_book_probability"]
    one_x = _row(fid=1, market=SEL_ONE_X, odds=1.4)
    x2 = _row(fid=1, market=SEL_X_TWO, odds=1.5)
    twelve = _row(fid=1, market=SEL_ONE_TWO, odds=1.35)
    o1 = resolve_fair_book_probability(one_x, mw)
    o2 = resolve_fair_book_probability(x2, mw)
    o3 = resolve_fair_book_probability(twelve, mw)
    assert o1["fair_book_probability_source"] == SOURCE_DC_DERIVED
    assert o1["fair_book_probability"] == pytest.approx(fair_h + fair_d)
    assert o2["fair_book_probability"] == pytest.approx(fair_d + fair_a)
    assert o3["fair_book_probability"] == pytest.approx(fair_h + fair_a)


def test_v2a4_07_dc_not_three_way_normalized():
    dc_only = [
        _row(fid=1, market=SEL_ONE_X, odds=1.4),
        _row(fid=1, market=SEL_X_TWO, odds=1.5),
        _row(fid=1, market=SEL_ONE_TWO, odds=1.35),
    ]
    out = resolve_fair_book_probability(dc_only[0], dc_only)
    assert out["fair_book_probability_verified"] is False
    assert out["fair_book_probability_source"] == SOURCE_RAW_SECONDARY


def test_v2a4_08_different_snapshot_excluded():
    home = _row(fid=1, market=SEL_HOME, odds=2.1, snapshot_hour=10)
    draw = _row(fid=1, market=SEL_DRAW, odds=3.4, snapshot_hour=11)
    away = _row(fid=1, market=SEL_AWAY, odds=3.6, snapshot_hour=10)
    out = resolve_fair_book_probability(home, [home, draw, away])
    assert out["fair_book_probability_verified"] is False


def test_v2a4_09_different_bookmaker_excluded():
    home = _row(fid=1, market=SEL_HOME, odds=2.1, bookmaker="A")
    draw = _row(fid=1, market=SEL_DRAW, odds=3.4, bookmaker="B")
    away = _row(fid=1, market=SEL_AWAY, odds=3.6, bookmaker="A")
    out = resolve_fair_book_probability(home, [home, draw, away])
    assert out["fair_book_probability_verified"] is False


def test_v2a4_10_raw_implied_secondary_only():
    alone = _row(fid=1, market=SEL_HOME, odds=2.0)
    out = resolve_fair_book_probability(alone, [alone])
    assert out["fair_book_probability_source"] == SOURCE_RAW_SECONDARY
    assert out["fair_book_probability_verified"] is False


# --- Target ---


def _verified_home_row(**kw):
    sibs = _1x2_siblings(**{k: kw[k] for k in ("fid", "day") if k in kw})
    if "fid" not in kw:
        kw = {**kw, "fid": 1}
    mapped = dict(kw)
    if "model_p" in mapped:
        mapped["model_probability"] = mapped.pop("model_p")
    if "won" in mapped:
        won = bool(mapped.pop("won"))
        mapped["settlement_status"] = "won" if won else "lost"
        mapped["selection_won"] = won
        mapped["selection_lost"] = not won
        mapped["selection_void"] = False
    for s in sibs:
        fair = resolve_fair_book_probability(s, sibs)
        s.update(fair)
    home = sibs[0]
    home.update(mapped)
    home.update(resolve_fair_book_probability(home, sibs))
    return home, sibs


def test_v2a4_11_15_gap_and_signed_residual():
    home, _ = _verified_home_row(model_p=0.70, won=True)
    r, reason = _residual_row(home)
    assert reason is None and r is not None
    assert r["model_book_gap"] == pytest.approx(0.70 - home["fair_book_probability"])
    assert r["signed_book_residual"] > 0  # positive gap + win

    home_l, _ = _verified_home_row(model_p=0.70, won=False, day=2, fid=2)
    r2, _ = _residual_row(home_l)
    assert r2["signed_book_residual"] < 0

    home_n, _ = _verified_home_row(model_p=0.10, won=True, day=3, fid=3)
    # force model below fair
    home_n["model_probability"] = 0.05
    home_n.update(resolve_fair_book_probability(home_n, _1x2_siblings(fid=3, day=3)))
    # re-apply verified fair from siblings
    sibs = _1x2_siblings(fid=3, day=3)
    for s in sibs:
        s.update(resolve_fair_book_probability(s, sibs))
    home_n = dict(sibs[0])
    home_n["model_probability"] = 0.05
    home_n["fair_book_probability"] = sibs[0]["fair_book_probability"]
    home_n["fair_book_probability_verified"] = True
    home_n["settlement_status"] = "won"
    home_n["selection_won"] = True
    r3, _ = _residual_row(home_n)
    assert r3["gap_direction"] == "negative"
    assert r3["signed_book_residual"] < 0  # negative gap * positive residual wrong direction

    home_n2 = dict(home_n)
    home_n2["settlement_status"] = "lost"
    home_n2["selection_won"] = False
    home_n2["selection_lost"] = True
    r4, _ = _residual_row(home_n2)
    assert r4["signed_book_residual"] > 0


def test_v2a4_16_18_direction_correct_and_book_dir_prob():
    home, _ = _verified_home_row(model_p=0.8, won=True)
    r, _ = _residual_row(home)
    assert r["direction_correct"] == 1
    assert r["book_direction_probability"] == pytest.approx(r["fair_book_probability"])
    # gap zero excluded from binary
    home2 = dict(home)
    home2["model_probability"] = home2["fair_book_probability"]
    r0, reason = _residual_row(home2)
    assert r0 is not None
    assert r0["direction_correct"] is None
    assert r0["gap_direction_code"] == 0


def test_v2a4_19_target_not_in_feature_specs():
    forbidden = {"y_win", "direction_correct", "signed_book_residual", "book_residual"}
    for spec in SPECS.values():
        assert not (forbidden & set(spec.get("numeric") or []))
        assert not (forbidden & set(spec.get("categorical") or []))


# --- End-to-end residual ---


def _multi_residual_rows(n_fixtures: int = 16) -> list[dict]:
    rows = []
    for i in range(n_fixtures):
        day = 1 + i
        fid = 100 + i
        model_p = 0.35 + (i % 10) * 0.05
        won = model_p > 0.5
        base = _1x2_siblings(fid=fid, day=day)
        for r in base:
            r["model_probability"] = model_p if r["selection"] == SEL_HOME else 1.0 - model_p
            r["settlement_status"] = "won" if (won if r["selection"] == SEL_HOME else not won) else "lost"
            r["selection_won"] = r["settlement_status"] == "won"
            r["selection_lost"] = r["settlement_status"] == "lost"
            r["unit_stake_profit"] = (r["odds"] - 1) if r["selection_won"] else -1.0
            fair = resolve_fair_book_probability(r, base)
            r.update(fair)
            # slight model edge so gap non-zero
            if abs(r["model_probability"] - r["fair_book_probability"]) < 1e-6:
                r["model_probability"] = min(0.99, r["model_probability"] + 0.02)
            rows.append(r)
        # DC derived — odds_source diverso (cross-market linkage)
        for m in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO):
            dc = _row(
                fid=fid,
                market=m,
                odds=1.45,
                day=day,
                model_p=model_p,
                won=won,
                source="betfair_raw_double_chance",
            )
            fair = resolve_fair_book_probability(dc, base)
            dc.update(fair)
            if dc.get("fair_book_probability_verified") and abs(
                dc["model_probability"] - dc["fair_book_probability"]
            ) < 1e-6:
                dc["model_probability"] = min(0.99, dc["model_probability"] + 0.03)
            rows.append(dc)
    return rows


def test_v2a4_20_30_pipeline_cv_specs_strict_json():
    rows = _multi_residual_rows(14)
    payload = build_purchasability_residual_reliability(
        MagicMock(),
        rows=rows,
        bootstrap_iterations=8,
        seed=7,
    )
    assert payload["version"] == RESIDUAL_RELIABILITY_VERSION
    assert payload["dataset_version"] == DATASET_VERSION
    assert payload["source_statistical_version"] == STAT_VERSION
    assert payload["no_purchasability_formula"] is True
    assert payload["no_db_writes"] is True
    json.dumps(make_json_safe(payload), allow_nan=False)
    assert "BOOK_DIRECTION_BASELINE" in payload["binary_results"]
    assert "GAP_ONLY" in payload["binary_results"]
    assert "GAP_RELIABILITY_CONTEXT" in payload["binary_results"]
    assert "RATING_RELIABILITY_CONTEXT_DIAGNOSTIC" in payload["binary_results"]
    assert "GAP_RELIABILITY_CONTEXT_vs_GAP_ONLY" in payload["paired_comparisons"]
    folds = payload["temporal_folds"]
    if folds:
        assert all((f.get("fixture_overlap") or 0) == 0 for f in folds)
    readiness = payload["phase_2b_residual_readiness"]
    assert readiness["recommended_next_step"] != "phase_2b_reliability_candidate_construction" or (
        readiness.get("context_beats_gap_only_or_residual_add")
        and readiness.get("context_beats_book")
    )
    # Rating cannot be retain
    for d in payload["feature_decisions"]:
        if d.get("feature") == "rating":
            assert d["decision"] != "retain_reliability_candidate"
    eco = payload["economic_diagnostics"]
    assert eco.get("stake") == 1
    # positive-value only
    assert "positive_value_rows" in eco


def test_v2a4_40_41_gap_only_or_rating_does_not_force_2b():
    rows = _multi_residual_rows(12)
    payload = build_purchasability_residual_reliability(
        MagicMock(), rows=rows, bootstrap_iterations=6, seed=9
    )
    readiness = payload["phase_2b_residual_readiness"]
    # Without context beating gap, should not authorize full 2B solely from GAP_ONLY
    if not readiness.get("context_beats_gap_only_or_residual_add"):
        assert readiness["recommended_next_step"] in {
            "stop_context_no_incremental_reliability",
            "continue_data_collection",
            "resolve_data_quality",
            "phase_2b_market_specific_reliability_candidate",
        }


def test_v2a4_45_blocking_fair_unverified_empty():
    payload = build_purchasability_residual_reliability(
        MagicMock(), rows=[], bootstrap_iterations=6, seed=1
    )
    assert "empty" in str(payload["phase_2b_residual_readiness"].get("blocking_issues"))


def test_v2a4_46_research_mode_in_hash():
    a = filters_hash_for(
        date_from=None,
        date_to=None,
        competition_id=None,
        market_family=None,
        selection=None,
        bootstrap_iterations=200,
        seed=42,
        research_mode=MODE_STATISTICAL,
    )
    b = filters_hash_for(
        date_from=None,
        date_to=None,
        competition_id=None,
        market_family=None,
        selection=None,
        bootstrap_iterations=200,
        seed=42,
        research_mode=MODE_RESIDUAL,
        statistical_version=RESIDUAL_RELIABILITY_VERSION,
    )
    assert a != b


def test_v2a4_55_63_versions_unchanged():
    assert STAT_VERSION == "cecchino_purchasability_statistical_research_v2a_2"
    assert DATASET_VERSION == "cecchino_purchasability_dataset_v1_1"
    assert AUDIT_VERSION.startswith("cecchino_purchasability_audit")
    assert RESIDUAL_RELIABILITY_VERSION == "cecchino_purchasability_residual_reliability_v2a_4_1"


def test_v2a4_36_economic_positive_value_only():
    rows = _multi_residual_rows(10)
    payload = build_purchasability_residual_reliability(
        MagicMock(), rows=rows, bootstrap_iterations=6, seed=11
    )
    eco = payload["economic_diagnostics"]
    assert isinstance(eco.get("positive_value_rows"), int)


# --- Fase 2A.4.1 ---


def test_v241_01_04_dc_cross_odds_source_linked():
    mw = [
        _row(fid=1, market=SEL_HOME, odds=2.10, source="betfair_raw_match_winner"),
        _row(fid=1, market=SEL_DRAW, odds=3.40, source="betfair_raw_match_winner"),
        _row(fid=1, market=SEL_AWAY, odds=3.60, source="betfair_raw_match_winner"),
    ]
    assert same_market_sibling_key(mw[0]) != same_market_sibling_key(
        _row(fid=1, market=SEL_ONE_X, odds=1.4, source="betfair_raw_double_chance")
    )
    assert cross_market_snapshot_key(mw[0]) == cross_market_snapshot_key(
        _row(fid=1, market=SEL_ONE_X, odds=1.4, source="betfair_raw_double_chance")
    )
    fair_h = resolve_fair_book_probability(mw[0], mw)["fair_book_probability"]
    fair_d = resolve_fair_book_probability(mw[1], mw)["fair_book_probability"]
    fair_a = resolve_fair_book_probability(mw[2], mw)["fair_book_probability"]
    one_x = _row(fid=1, market=SEL_ONE_X, odds=1.4, source="betfair_raw_double_chance")
    x2 = _row(fid=1, market=SEL_X_TWO, odds=1.5, source="betfair_raw_double_chance")
    twelve = _row(fid=1, market=SEL_ONE_TWO, odds=1.35, source="betfair_raw_double_chance")
    all_rows = mw + [one_x, x2, twelve]
    enriched = resolve_fair_for_rows(all_rows)
    by_sel = {r["selection"]: r for r in enriched}
    assert by_sel[SEL_ONE_X]["fair_book_probability_source"] == SOURCE_DC_DERIVED
    assert by_sel[SEL_ONE_X]["fair_book_probability_verified"] is True
    assert by_sel[SEL_ONE_X]["fair_book_probability"] == pytest.approx(fair_h + fair_d)
    assert by_sel[SEL_X_TWO]["fair_book_probability"] == pytest.approx(fair_d + fair_a)
    assert by_sel[SEL_ONE_TWO]["fair_book_probability"] == pytest.approx(fair_h + fair_a)
    assert by_sel[SEL_ONE_X]["normalization_payload"]["linkage_mode"] == (
        "cross_market_same_snapshot_provider"
    )


def test_v241_05_07_dc_mismatch_excluded():
    mw = _1x2_siblings(source="betfair_raw_match_winner")
    # different snapshot
    dc_snap = _row(
        fid=1, market=SEL_ONE_X, odds=1.4, source="betfair_raw_double_chance", snapshot_hour=11
    )
    assert resolve_fair_book_probability(dc_snap, mw)["fair_book_probability_verified"] is False
    # different bookmaker
    dc_bm = _row(
        fid=1, market=SEL_ONE_X, odds=1.4, source="betfair_raw_double_chance", bookmaker="OTHER"
    )
    assert resolve_fair_book_probability(dc_bm, mw)["fair_book_probability_verified"] is False
    # different provider
    for r in mw:
        r["bookmaker_provider_id"] = 1
        r["bookmaker_provider_source"] = "betfair"
    dc_prov = _row(fid=1, market=SEL_ONE_X, odds=1.4, source="betfair_raw_double_chance")
    dc_prov["bookmaker_provider_id"] = 99
    dc_prov["bookmaker_provider_source"] = "betfair"
    assert resolve_fair_book_probability(dc_prov, mw)["fair_book_probability_verified"] is False


def test_v241_08_09_dc_not_three_way_and_source():
    dc_only = [
        _row(fid=1, market=SEL_ONE_X, odds=1.4, source="betfair_raw_double_chance"),
        _row(fid=1, market=SEL_X_TWO, odds=1.5, source="betfair_raw_double_chance"),
        _row(fid=1, market=SEL_ONE_TWO, odds=1.35, source="betfair_raw_double_chance"),
    ]
    out = resolve_fair_book_probability(dc_only[0], dc_only)
    assert out["fair_book_probability_verified"] is False
    assert out["fair_book_probability_source"] == SOURCE_RAW_SECONDARY


def test_v241_10_fair_audit_observed_settled_residual():
    rows = _multi_residual_rows(8)
    # force DC with different odds_source
    for r in rows:
        if r["selection"] in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO):
            r["odds_source"] = "betfair_raw_double_chance"
            r["book_source"] = "betfair_raw_double_chance"
        else:
            r["odds_source"] = "betfair_raw_match_winner"
            r["book_source"] = "betfair_raw_match_winner"
    payload = build_purchasability_residual_reliability(
        MagicMock(), rows=rows, bootstrap_iterations=4, seed=3
    )
    audit = payload["fair_book_probability_audit"]
    assert "all_observed_source_counts" in audit
    assert "settled_source_counts" in audit
    assert "residual_source_counts" in audit
    assert audit["double_chance"]["dc_derived_verified_rows"] > 0
    residual_mk = set(audit["markets_residual_evaluated"])
    assert SEL_ONE_X in residual_mk and SEL_X_TWO in residual_mk and SEL_ONE_TWO in residual_mk


def test_v241_11_17_oof_mask_baseline_aligned():
    rows = _multi_residual_rows(16)
    payload = build_purchasability_residual_reliability(
        MagicMock(), rows=rows, bootstrap_iterations=4, seed=5
    )
    oof = payload["oof_evaluation_identity"]
    assert oof["oof_evaluable_rows"] < oof["source_residual_rows"]
    assert oof["train_only_initial_rows"] > 0
    base = payload["binary_results"]["BOOK_DIRECTION_BASELINE"]
    gap = payload["binary_results"]["GAP_ONLY"]
    assert base["n_oof"] == oof["oof_evaluable_rows"] or base["n_oof"] <= oof["oof_evaluable_rows"]
    assert base["n_oof"] == gap["n_oof"] or abs(base["n_oof"] - gap["n_oof"]) <= gap.get(
        "missing_prediction_rows", 0
    )
    assert "oof_coverage" in base and "n_source" in base
    paired = payload["paired_comparisons"]["GAP_RELIABILITY_CONTEXT_vs_GAP_ONLY"]
    assert paired.get("same_evaluation_cohort") is True
    assert paired.get("paired_row_key_hash")


def test_v241_baseline_nan_outside_mask():
    rows = [
        {"today_fixture_id": 1, "book_direction_probability": 0.4, "canonical_row_key": "a"},
        {"today_fixture_id": 2, "book_direction_probability": 0.5, "canonical_row_key": "b"},
        {"today_fixture_id": 3, "book_direction_probability": 0.6, "canonical_row_key": "c"},
    ]
    folds = [{"fold": 1, "train_fixture_ids": [1], "test_fixture_ids": [2, 3]}]
    mask = build_oof_evaluation_mask(rows, folds)
    pred = _baseline_prediction(rows, mask)
    assert np.isnan(pred[0])
    assert np.isfinite(pred[1]) and np.isfinite(pred[2])
    assert int(mask.sum()) == 2


def test_v241_18_20_economic_paired_common_cohort():
    rows = _multi_residual_rows(14)
    payload = build_purchasability_residual_reliability(
        MagicMock(), rows=rows, bootstrap_iterations=8, seed=13
    )
    eco = payload["economic_diagnostics"]
    assert "oof_positive_rows" in eco
    paired = eco.get("paired_comparisons") or {}
    assert "GAP_RELIABILITY_CONTEXT_vs_GAP_ONLY" in paired
    assert "RELIABILITY_CONTEXT_ONLY_vs_BOOK_DIRECTION_BASELINE" in paired
    block = paired["GAP_RELIABILITY_CONTEXT_vs_GAP_ONLY"]
    if block.get("status") == "ok":
        assert block["same_evaluation_cohort"] is True
        assert "ci_delta_roi_top_10pct" in block
        assert block["paired_row_key_hash"]


def test_v241_21_25_temporal_and_readiness():
    assert MIN_TEMPORAL_SPAN_DAYS == 90
    short_rows = []
    for i in range(10):
        r = _row(fid=200 + i, market=SEL_HOME, odds=2.1, day=1 + i, model_p=0.7, won=True)
        r["kickoff"] = datetime(2026, 6, 19 + (i % 10), 18, 0, tzinfo=timezone.utc).isoformat()
        short_rows.append(r)
    # fabricate residual-like rows for span helper
    for r in short_rows:
        r["fair_book_probability"] = 0.45
        r["fair_book_probability_verified"] = True
    span = _temporal_span(short_rows)
    assert span["temporal_span_days"] < 90
    assert span["limited_temporal_span"] is True

    long_rows = []
    for i in range(12):
        month = 1 + (i % 4)
        day = 5 + (i % 20)
        r = _row(fid=300 + i, market=SEL_HOME, odds=2.1, day=1, model_p=0.7, won=True)
        r["kickoff"] = datetime(2026, month, day, 18, 0, tzinfo=timezone.utc).isoformat()
        long_rows.append(r)
    span2 = _temporal_span(long_rows)
    assert span2["temporal_span_days"] >= 90
    assert span2["unique_calendar_months"] >= 3
    assert span2["limited_temporal_span"] is False

    rows = _multi_residual_rows(12)
    # keep dates within one month
    for i, r in enumerate(rows):
        r["kickoff"] = datetime(2026, 6, 19 + (i % 10), 18, 0, tzinfo=timezone.utc).isoformat()
    payload = build_purchasability_residual_reliability(
        MagicMock(), rows=rows, bootstrap_iterations=4, seed=2
    )
    ready = payload["phase_2b_residual_readiness"]
    assert ready["limited_temporal_span"] is True
    assert ready["recommended_next_step"] == "continue_data_collection"
    assert any("limited_temporal_span" in c for c in ready.get("readiness_reason_codes") or [])
    # stop not allowed while limited
    assert ready["recommended_next_step"] != "stop_context_no_incremental_reliability"
