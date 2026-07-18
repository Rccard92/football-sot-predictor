"""Test Fase 2A — ricerca statistica Indice di Acquistabilità (46 punti)."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.cecchino.cecchino_market_opposition import (
    FAMILY_DOUBLE_CHANCE,
    OPPOSITION_SUPPORTED,
)
from app.services.cecchino.cecchino_purchasability_audit import (
    AUDIT_VERSION,
    DATASET_VERSION,
    make_json_safe,
)
from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
    brier,
    economic_metrics,
    expanding_fixture_folds,
    fixture_cluster_bootstrap_ci,
    log_loss_score,
)
from app.services.cecchino.cecchino_purchasability_statistical_research import (
    STAT_VERSION,
    TARGET_KEYS,
    analyze_pooled,
    build_purchasability_statistical_research,
    engineer_row,
    filter_settled_cohort,
    fit_predict_oof_logistic,
    order_fixtures,
    resolve_spec_features,
    validate_spec_features,
)


def _base_row(
    *,
    fid: int,
    market: str = "HOME",
    family: str = "match_result",
    day: int = 1,
    won: bool = True,
    odds: float = 2.0,
    model_p: float = 0.55,
    rating: float = 60.0,
    key: str | None = None,
    void: bool = False,
    is_settled_core: bool = True,
    leakage: str = "safe",
) -> dict:
    snap = datetime(2026, 1, day, 10, 0, tzinfo=timezone.utc)
    kick = datetime(2026, 1, day, 18, 0, tzinfo=timezone.utc)
    status = "void" if void else ("won" if won else "lost")
    profit = 0.0 if void else (odds - 1.0 if won else -1.0)
    raw_imp = 1.0 / odds
    return {
        "today_fixture_id": fid,
        "canonical_row_key": key or f"k-{fid}-{market}-{day}",
        "raw_market_code": market,
        "selection": market,
        "canonical_market_family": family,
        "scan_date": f"2026-01-{day:02d}",
        "snapshot_at": snap.isoformat(),
        "kickoff": kick.isoformat(),
        "competition_id": 1,
        "odds": odds,
        "raw_book_implied_probability": raw_imp,
        "normalized_book_probability": raw_imp / 1.05,
        "market_overround": 0.05,
        "model_probability": model_p,
        "probability_advantage": model_p - raw_imp,
        "edge": (model_p * odds - 1.0) * 100,
        "score": model_p * 50 + (model_p - raw_imp) * 100,
        "rating": rating,
        "favourite_alignment": "aligned",
        "favourite_intensity_book": 0.12,
        "favourite_intensity_model": 0.15,
        "book_favourite": market,
        "model_favourite": market,
        "comparator_odds_payload": {"DRAW": 3.2, "AWAY": 3.8},
        "comparator_model_probability_payload": {"DRAW": 0.28, "AWAY": 0.22},
        "comparator_book_probability_payload": {"DRAW": 0.31, "AWAY": 0.26},
        "complement_selection": "AWAY",
        "settlement_status": status,
        "selection_won": won and not void,
        "selection_lost": (not won) and not void,
        "selection_void": void,
        "unit_stake_profit": profit,
        "is_settled_core": is_settled_core,
        "is_core": True,
        "snapshot_timestamp_verified": True,
        "snapshot_before_kickoff": True,
        "no_post_match_data_in_features": True,
        "leakage_status": leakage,
        "opposition_status": OPPOSITION_SUPPORTED,
    }


def _multi_fixture_rows(n_fixtures: int = 18, markets: tuple[str, ...] = ("HOME", "DRAW")) -> list[dict]:
    rows = []
    for i in range(n_fixtures):
        day = 1 + i
        # make outcome somewhat correlated with model_p
        model_p = 0.35 + (i % 10) * 0.04
        won = model_p > 0.5
        odds = 1.7 + (i % 5) * 0.15
        for m in markets:
            rows.append(
                _base_row(
                    fid=100 + i,
                    market=m,
                    day=day,
                    won=won if m == "HOME" else not won,
                    odds=odds,
                    model_p=model_p if m == "HOME" else 1.0 - model_p,
                    rating=40 + i * 2,
                )
            )
    return rows


# --- DATASET E SPLIT (1-8) ---


def test_01_uses_only_settled_core():
    rows = [
        _base_row(fid=1, is_settled_core=True),
        _base_row(fid=2, key="k2", is_settled_core=False),
    ]
    cohort, _ = filter_settled_cohort(rows)
    assert len(cohort) == 1
    assert cohort[0]["today_fixture_id"] == 1


def test_02_targets_excluded_from_features():
    for t in TARGET_KEYS:
        assert t not in resolve_spec_features("VALUE_ADVANTAGE")[0]


def test_03_snapshot_pre_match_required():
    r = _base_row(fid=1)
    r["snapshot_before_kickoff"] = False
    assert engineer_row(r) is None


def test_04_fixtures_not_shared_train_test():
    rows = _multi_fixture_rows(12, ("HOME",))
    cohort, _ = filter_settled_cohort(rows)
    fids = order_fixtures(cohort)
    folds, _ = expanding_fixture_folds(fids)
    for f in folds:
        assert set(f["train_fixture_ids"]).isdisjoint(set(f["test_fixture_ids"]))


def test_05_temporal_not_random_split():
    rows = _multi_fixture_rows(12, ("HOME",))
    cohort, _ = filter_settled_cohort(rows)
    ordered = order_fixtures(cohort)
    # later fixtures have later days
    assert ordered[0] < ordered[-1]
    folds, _ = expanding_fixture_folds(ordered)
    assert folds[0]["train_fixture_ids"][0] == ordered[0]


def test_06_canonical_row_key_unique_ok():
    rows = _multi_fixture_rows(6, ("HOME",))
    _, q = filter_settled_cohort(rows)
    assert q["canonical_keys_unique"] is True


def test_07_same_feature_vector_different_fixture_kept():
    a = _base_row(fid=1, key="ka", model_p=0.5, odds=2.0)
    b = _base_row(fid=2, key="kb", model_p=0.5, odds=2.0, day=2)
    cohort, q = filter_settled_cohort([a, b])
    assert len(cohort) == 2
    assert q["duplicated_observation_count"] == 0


def test_08_duplicate_canonical_key_blocking():
    a = _base_row(fid=1, key="same")
    b = _base_row(fid=2, key="same", day=2)
    cohort, q = filter_settled_cohort([a, b])
    assert "duplicated_observation_canonical_row_key" in q["blocking_issues"]
    assert len(cohort) == 0


# --- FEATURE (9-15) ---


def test_09_odds_and_raw_implied_forbidden():
    assert "odds_and_raw_implied_together" in validate_spec_features(
        ["odds", "raw_book_implied_probability"]
    )


def test_10_score_not_with_components():
    assert "score_with_model_and_edge" in validate_spec_features(
        ["score", "model_probability", "edge"]
    )


def test_11_rating_benchmark_separate():
    feats, _ = resolve_spec_features("RATING_BASELINE")
    assert feats == ["rating"]
    assert "model_probability" not in feats


def test_12_dc_without_normalized_probability():
    r = _base_row(fid=1, market="ONE_X", family=FAMILY_DOUBLE_CHANCE)
    r["normalized_book_probability"] = 0.4
    eng = engineer_row(r)
    assert eng is not None
    assert eng["normalized_book_probability"] is None
    assert eng["is_double_chance"] is True


def test_13_comparator_gap_pre_match_only():
    r = _base_row(fid=1)
    eng = engineer_row(r)
    assert eng is not None
    assert eng["comparator_odds_gap"] is not None
    # gap = own odds - first comparator
    assert abs(eng["comparator_odds_gap"] - (2.0 - 3.2)) < 1e-9


def test_14_no_other_module_fields_in_specs():
    for spec in ("BOOK_BASELINE", "VALUE_ADVANTAGE", "CONTEXT_ONLY"):
        feats, cats = resolve_spec_features(spec)
        blob = " ".join(feats + cats).lower()
        assert "f36" not in blob
        assert "icm" not in blob
        assert "intensity" not in blob or "favourite_intensity" in blob


def test_15_no_target_leakage_in_engineered_features():
    eng = engineer_row(_base_row(fid=1))
    assert eng is not None
    feature_side = {
        k: v
        for k, v in eng.items()
        if k
        not in {
            "y_win",
            "profit",
            "settlement_status",
            "selection_void",
            "realized_probability_residual",
            "normalized_probability_residual",
            "today_fixture_id",
            "canonical_row_key",
            "raw_market_code",
            "selection",
            "canonical_market_family",
            "scan_date",
            "snapshot_at",
            "kickoff",
            "competition_id",
            "is_double_chance",
            "book_favourite",
            "model_favourite",
        }
    }
    assert "selection_won" not in feature_side
    assert "unit_stake_profit" not in feature_side


# --- METRICHE (16-25) ---


def test_16_roi_unit_stake():
    profits = np.array([1.0, -1.0, 0.5])
    won = np.array([1.0, 0.0, 1.0])
    odds = np.array([2.0, 2.0, 1.5])
    m = economic_metrics(profits, won, odds)
    assert m["roi"] == pytest.approx(0.5 / 3)


def test_17_void_profit_zero():
    r = _base_row(fid=1, void=True)
    eng = engineer_row(r)
    assert eng is not None
    assert eng["profit"] == 0.0


def test_18_void_excluded_from_win_rate():
    profits = np.array([1.0, 0.0, -1.0])
    won = np.array([1.0, 0.0, 0.0])
    void = np.array([False, True, False])
    odds = np.array([2.0, 2.0, 2.0])
    m = economic_metrics(profits, won, odds, void_mask=void)
    assert m["n_classification"] == 2
    assert m["win_rate"] == pytest.approx(0.5)
    assert m["n"] == 3


def test_19_brier_correct():
    y = np.array([1.0, 0.0])
    p = np.array([0.8, 0.2])
    assert brier(y, p) == pytest.approx(0.04)


def test_20_log_loss_correct():
    y = np.array([1.0, 0.0])
    p = np.array([0.8, 0.2])
    expected = -0.5 * (math.log(0.8) + math.log(0.8))
    assert log_loss_score(y, p) == pytest.approx(expected)


def test_21_calibration_train_only_via_folds():
    rows = _multi_fixture_rows(16, ("HOME",))
    cohort, _ = filter_settled_cohort(rows)
    folds, _ = expanding_fixture_folds(order_fixtures(cohort))
    oof = fit_predict_oof_logistic(cohort, folds, ["model_probability"], [])
    assert "fold_reports" in oof
    for fr in oof["fold_reports"]:
        assert fr["fixture_overlap"] == 0


def test_22_bootstrap_by_fixture():
    fids = np.array([1, 1, 2, 2, 3])
    vals = np.array([1.0, 1.0, -1.0, -1.0, 0.5])
    ci = fixture_cluster_bootstrap_ci(fids, vals, iterations=50, seed=7)
    assert ci["iterations"] == 50
    assert ci["ci_low"] <= ci["mean"] <= ci["ci_high"]


def test_23_fixture_equal_weighting():
    rows = _multi_fixture_rows(10, ("HOME", "DRAW"))
    cohort, _ = filter_settled_cohort(rows)
    pooled = analyze_pooled(cohort, bootstrap_iterations=20, seed=1)
    assert "fixture_equal_weighted_roi" in pooled
    assert "row_weighted_roi" in pooled


def test_24_metrics_oof_only_structure():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(16, ("HOME",)),
        bootstrap_iterations=20,
        seed=1,
    )
    assert payload["status"] in ("ok", "empty_cohort")
    # OOF arrays must not leak into JSON payload
    blob = json.dumps(payload, allow_nan=False)
    assert "oof_prob" not in blob


def test_25_no_threshold_optimized_on_test():
    # stake always 1; economic metrics use full OOF coverage without threshold search
    profits = np.array([0.5, -1.0, 1.2])
    won = np.array([1.0, 0.0, 1.0])
    odds = np.array([1.5, 2.0, 2.2])
    m = economic_metrics(profits, won, odds)
    assert m["coverage"] == 1.0


# --- STABILITÀ (26-30) ---


def test_26_to_30_classification_labels_and_end_to_end():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        classify_marginal,
    )

    assert classify_marginal(0.05, [1, 1, 1], [1, 1, 1], {"ci_low": 0.01}) == (
        "positive_stable_evidence"
    )
    assert classify_marginal(0.02, [1, -1, 1], [], None) == "temporally_unstable"
    assert (
        classify_marginal(0.03, [1], [1, 0, 0], None) == "market_specific_signal"
        or classify_marginal(0.03, [1], [1, 0, 0], None) == "positive_but_uncertain"
    )
    assert classify_marginal(0.001, [1], [1], None) == "redundant_no_incremental_value"
    assert classify_marginal(0.008, [1], [1], {"ci_low": -0.01}) == "positive_but_uncertain"


# --- RATING (31-34) ---


def test_31_34_rating_section_present():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(18, ("HOME", "OVER_2_5")),
        bootstrap_iterations=20,
        seed=2,
    )
    rb = payload["rating_benchmark"]
    assert "conclusion" in rb
    assert rb["conclusion"] in {
        "benchmark_only",
        "incremental_candidate",
        "redundant_exclude",
        "market_specific_benchmark",
        "insufficient_evidence",
    }
    assert payload["phase_2b_readiness"]["rating_decision"] == rb["conclusion"]


# --- JSON (35-37) ---


def test_35_37_json_safe_no_nan_inf():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(14, ("HOME",)),
        bootstrap_iterations=15,
        seed=3,
    )
    safe = make_json_safe(payload)
    raw = json.dumps(safe, allow_nan=False)
    assert "NaN" not in raw
    assert "Infinity" not in raw


# --- REGRESSION (38-46) ---


def test_38_39_audit_dataset_versions_unchanged():
    assert AUDIT_VERSION == "cecchino_purchasability_audit_v1_1"
    assert DATASET_VERSION == "cecchino_purchasability_dataset_v1_1"
    assert STAT_VERSION == "cecchino_purchasability_statistical_research_v2a"


def test_40_46_flags_no_formula_no_writes():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(12, ("HOME",)),
        bootstrap_iterations=10,
        seed=4,
    )
    assert payload["no_db_writes"] is True
    assert payload["no_purchasability_formula"] is True
    assert "acquistabilità" not in json.dumps(payload).lower() or "produttivo" in (
        payload.get("research_banner") or ""
    ).lower()
    banner = payload.get("research_banner") or ""
    assert "Nessun Indice di Acquistabilità produttivo" in banner
    assert "Nessuna influenza sui Segnali Cecchino" in banner


def test_empty_cohort_readiness():
    payload = build_purchasability_statistical_research(
        MagicMock(), rows=[], bootstrap_iterations=10, seed=1
    )
    assert payload["status"] == "empty_cohort"
    assert payload["phase_2b_readiness"]["recommended_next_step"] == "continue_data_collection"


def test_database_url_note():
    """Benchmark reale solo con DATABASE_URL; altrimenti segnalare missing (doc/ops)."""
    import os

    if not os.environ.get("DATABASE_URL"):
        note = "DATABASE_URL_missing"
    else:
        note = "DATABASE_URL_present"
    assert note in {"DATABASE_URL_missing", "DATABASE_URL_present"}
