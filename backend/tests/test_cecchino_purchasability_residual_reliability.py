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
    resolve_fair_book_probability,
)
from app.services.cecchino.cecchino_purchasability_research_jobs import (
    MODE_RESIDUAL,
    MODE_STATISTICAL,
    filters_hash_for,
)
from app.services.cecchino.cecchino_purchasability_residual_reliability import (
    RESIDUAL_RELIABILITY_VERSION,
    SPECS,
    _residual_row,
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
    return [
        _row(fid=fid, market=SEL_HOME, odds=2.10, day=day, **kw),
        _row(fid=fid, market=SEL_DRAW, odds=3.40, day=day, **kw),
        _row(fid=fid, market=SEL_AWAY, odds=3.60, day=day, **kw),
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
        # DC derived
        for m in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO):
            dc = _row(fid=fid, market=m, odds=1.45, day=day, model_p=model_p, won=won)
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
    assert RESIDUAL_RELIABILITY_VERSION == "cecchino_purchasability_residual_reliability_v2a_4"


def test_v2a4_36_economic_positive_value_only():
    rows = _multi_residual_rows(10)
    payload = build_purchasability_residual_reliability(
        MagicMock(), rows=rows, bootstrap_iterations=6, seed=11
    )
    # residual rows with positive_value should drive economic n
    eco = payload["economic_diagnostics"]
    assert isinstance(eco.get("positive_value_rows"), int)
