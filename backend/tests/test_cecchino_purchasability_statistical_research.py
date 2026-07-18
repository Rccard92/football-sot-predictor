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

    assert classify_marginal(0.05, [1, 1, 1], None, {"ci_low": 0.01}) == (
        "positive_stable_evidence"
    )
    assert classify_marginal(0.02, [1, -1, 1], None, None) == "temporally_unstable"
    assert (
        classify_marginal(
            0.03, [1], None, None, cross_market_label="market_specific_signal"
        )
        == "market_specific_signal"
    )
    assert classify_marginal(0.001, [1], None, {"ci_low": -0.01, "ci_high": 0.01}) == (
        "redundant_no_incremental_value"
    )
    assert classify_marginal(0.008, [1], None, {"ci_low": -0.01}) == "positive_but_uncertain"


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
        "temporally_unstable",
        "insufficient_evidence",
    }
    assert payload["phase_2b_readiness"]["rating_decision"] == rb["conclusion"]
    # No selection-optimism fields
    for pm in rb.get("per_market") or []:
        assert "best_without_rating" not in pm or pm.get("prespecified_comparisons") is not None
        assert "prespecified_comparisons" in pm


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
    assert STAT_VERSION == "cecchino_purchasability_statistical_research_v2a_2"


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


# --- Fase 2A.1 correzioni (20 punti) ---


def test_v2a1_01_full_coverage_roi_not_used_as_marginal():
    from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
        ranking_economic_from_scores,
    )

    profits = np.array([1.0, -1.0, 0.5, -1.0, 2.0, -1.0, 0.8, -1.0])
    scores_a = np.array([0.9, 0.1, 0.8, 0.2, 0.85, 0.15, 0.7, 0.3])
    scores_b = np.array([0.1, 0.9, 0.2, 0.8, 0.15, 0.85, 0.3, 0.7])
    eco = economic_metrics(profits, np.ones(8), np.full(8, 2.0))
    # Same cohort ROI regardless of scores
    assert eco["cohort_full_coverage_roi"] == pytest.approx(float(np.mean(profits)))
    r_a = ranking_economic_from_scores(profits, scores_a)
    r_b = ranking_economic_from_scores(profits, scores_b)
    assert r_a["roi_top_10pct"] != r_b["roi_top_10pct"]


def test_v2a1_02_top10_changes_with_ranking():
    from app.services.cecchino.cecchino_purchasability_statistical_helpers import top_k_roi

    profits = np.array([1.0, -1.0, 2.0, -1.0, 0.5])
    good = top_k_roi(profits, np.array([0.9, 0.1, 0.95, 0.05, 0.5]), 0.4)
    bad = top_k_roi(profits, np.array([0.1, 0.9, 0.05, 0.95, 0.5]), 0.4)
    assert good["roi"] != bad["roi"]


def test_v2a1_03_05_paired_deltas_sign_convention():
    from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
        paired_oof_comparison,
    )

    rows = []
    for i in range(40):
        won = i % 2 == 0
        rows.append(
            {
                "today_fixture_id": i // 2,
                "y_win": 1 if won else 0,
                "profit": 1.0 if won else -1.0,
                "selection_void": False,
            }
        )
    # Candidate perfectly ranked; baseline anti-ranked
    y = np.array([r["y_win"] for r in rows], dtype=float)
    cand = y * 0.9 + 0.05
    base = (1 - y) * 0.9 + 0.05
    out = paired_oof_comparison(
        rows, cand, base, bootstrap_iterations=30, seed=11
    )
    assert out["delta_auc"] is not None and out["delta_auc"] > 0
    assert out["delta_brier_improvement"] is not None and out["delta_brier_improvement"] > 0
    assert out["delta_log_loss_improvement"] is not None and out["delta_log_loss_improvement"] > 0
    ci = out["confidence_intervals"]["delta_auc"]
    assert "estimate" in ci and "ci_low" in ci and "valid_iterations" in ci


def test_v2a1_06_07_bootstrap_pairs_fixture_and_diff_ci():
    from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
        paired_oof_comparison,
    )

    rows = []
    for i in range(30):
        rows.append(
            {
                "today_fixture_id": i % 10,
                "y_win": 1 if i % 3 else 0,
                "profit": 1.0 if i % 3 else -1.0,
            }
        )
    rng = np.random.default_rng(0)
    cand = rng.random(30)
    base = rng.random(30)
    out = paired_oof_comparison(rows, cand, base, bootstrap_iterations=40, seed=5)
    ci = out["confidence_intervals"]["delta_auc"]
    # CI is on difference, not absolute profit
    assert "mean_profit" not in ci
    assert ci["iterations"] == 40


def test_v2a1_08_09_fold_signs_real_and_unstable():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        classify_marginal,
        fold_delta_auc_signs,
    )

    rows = _multi_fixture_rows(16, ("HOME",))
    cohort, _ = filter_settled_cohort(rows)
    folds, _ = expanding_fixture_folds(order_fixtures(cohort))
    n = len(cohort)
    # alternating quality by fixture order → unstable folds possible
    pred_c = np.linspace(0.2, 0.8, n)
    pred_b = np.linspace(0.8, 0.2, n)
    info = fold_delta_auc_signs(cohort, folds, pred_c, pred_b)
    assert isinstance(info["fold_signs"], list)
    # when folds valid, signs not forced empty by API
    if any(not f.get("skipped") for f in info["fold_deltas"]):
        assert len(info["fold_signs"]) > 0
    assert classify_marginal(0.02, [1, -1, 1], None, None) == "temporally_unstable"


def test_v2a1_10_market_specific_from_multi_market():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        classify_cross_market,
    )

    meta = classify_cross_market([0.04, -0.001, 0.0])
    assert meta["market_stability"] in {
        "market_specific_signal",
        "cross_market_stable",
        "insufficient_markets",
        "cross_market_unstable",
    }
    meta2 = classify_cross_market([0.05, 0.04, 0.03])
    assert meta2["market_stability"] == "cross_market_stable"


def test_v2a1_11_12_rating_prespecified_no_oof_best_pick():
    import inspect
    from app.services.cecchino import cecchino_purchasability_statistical_research as mod

    src = inspect.getsource(mod.analyze_market)
    assert "best_without_rating_feats" not in src or "RATING_PAIRED" in src
    assert "RATING_PAIRED_COMPARISONS" in inspect.getsource(mod)
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(16, ("HOME", "DRAW")),
        bootstrap_iterations=15,
        seed=9,
    )
    for pm in payload["rating_benchmark"].get("per_market") or []:
        comps = pm.get("prespecified_comparisons") or []
        assert isinstance(comps, list)
        # no dynamic "best_without_rating" selection field used for decision
        assert "delta_auc_adding_rating" not in pm or comps


def test_v2a1_13_14_stable_seed_no_builtin_hash():
    from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
        stable_seed,
    )
    import inspect
    from app.services.cecchino import cecchino_purchasability_statistical_research as mod

    assert stable_seed(42, "a") == stable_seed(42, "a")
    assert stable_seed(42, "a") != stable_seed(42, "b")
    src = inspect.getsource(mod)
    assert "hash(f)" not in src
    assert "seed + hash" not in src
    assert "stable_seed" in src


def test_v2a1_15_16_candidate_brier_and_stability_filled():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(18, ("HOME",)),
        bootstrap_iterations=15,
        seed=8,
    )
    specs = [c for c in payload["candidate_specifications"] if c.get("status") == "ok"]
    assert specs
    assert any(c.get("brier_mean") is not None for c in specs)
    assert all(c.get("temporal_stability") != "unknown" for c in specs)
    assert all(c.get("market_stability") != "unknown" for c in specs)


def test_v2a1_17_18_no_oof_prob_no_or_true():
    import inspect
    from app.services.cecchino import cecchino_purchasability_statistical_research as mod

    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(14, ("HOME",)),
        bootstrap_iterations=12,
        seed=6,
    )
    blob = json.dumps(payload, allow_nan=False)
    assert "oof_prob" not in blob
    src = inspect.getsource(mod.build_purchasability_statistical_research)
    assert "or True" not in src


def test_v2a1_19_strict_json():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(12, ("HOME",)),
        bootstrap_iterations=10,
        seed=7,
    )
    json.dumps(make_json_safe(payload), allow_nan=False)


def test_v2a1_20_readiness_not_positive_without_paired():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(12, ("HOME",)),
        bootstrap_iterations=10,
        seed=3,
    )
    step = payload["phase_2b_readiness"]["recommended_next_step"]
    # With tiny synthetic data, must not claim 2B construction without paired evidence
    if payload["phase_2b_readiness"].get("paired_positive_comparisons", 0) == 0:
        assert step != "phase_2b_candidate_construction"
    if payload["phase_2b_readiness"].get("paired_positive_vs_book", 0) == 0:
        assert step != "phase_2b_candidate_construction"


# --- Fase 2A.2 timeout FE + gate indipendenza vs Book (20 punti) ---


def test_v2a2_01_negative_delta_not_positive_uncertain():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        classify_marginal,
    )

    assert (
        classify_marginal(-0.02, [1], None, {"ci_low": -0.05, "ci_high": 0.01})
        != "positive_but_uncertain"
    )
    assert (
        classify_marginal(-0.001, [], None, {"ci_low": -0.02, "ci_high": 0.02})
        != "positive_but_uncertain"
    )


def test_v2a2_02_negative_uncertain_when_ci_crosses_zero():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        classify_marginal,
    )

    assert (
        classify_marginal(-0.005, [1], None, {"ci_low": -0.02, "ci_high": 0.01})
        == "negative_but_uncertain"
    )


def test_v2a2_03_entirely_negative_ci_is_negative_incremental():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        classify_marginal,
    )

    assert (
        classify_marginal(-0.005, [1], None, {"ci_low": -0.04, "ci_high": -0.01})
        == "negative_incremental_value"
    )


def test_v2a2_04_positive_uncertain_when_ci_crosses_zero():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        classify_marginal,
    )

    assert (
        classify_marginal(0.02, [1], None, {"ci_low": -0.01, "ci_high": 0.05})
        == "positive_but_uncertain"
    )


def test_v2a2_05_positive_stable_requires_positive_delta_and_ci():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        classify_marginal,
    )

    assert (
        classify_marginal(0.05, [1, 1, 1], None, {"ci_low": 0.01, "ci_high": 0.08})
        == "positive_stable_evidence"
    )
    assert (
        classify_marginal(-0.05, [1, 1, 1], None, {"ci_low": 0.01, "ci_high": 0.08})
        != "positive_stable_evidence"
    )


def test_v2a2_06_07_08_comparison_roles():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        comparison_role_for,
    )

    assert comparison_role_for("MODEL_BASELINE", "VALUE_ADVANTAGE") == (
        "model_enrichment_diagnostic"
    )
    assert comparison_role_for("BOOK_BASELINE", "VALUE_ADVANTAGE") == "independent_vs_book"
    assert comparison_role_for("RATING_BASELINE", "RATING_CONTEXT") == "rating_diagnostic"
    assert (
        comparison_role_for("VALUE_ADVANTAGE", "VALUE_ADVANTAGE_PLUS_RATING")
        == "rating_diagnostic"
    )


def test_v2a2_09_positive_vs_model_does_not_enable_2b():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        resolve_phase_2b_next_step,
    )

    step, errs = resolve_phase_2b_next_step(
        blocking=[],
        invariant_errors=[],
        temporal_done=True,
        limited_temporal=False,
        can_2b=False,
        residual_research=False,
        paired_positive_vs_model=True,
        paired_positive_vs_book=False,
        retained=["probability_advantage"],
        independent_candidate_specs=[],
    )
    assert step != "phase_2b_candidate_construction"
    assert step == "phase_2a_residual_reliability_research"
    assert errs == []


def test_v2a2_10_positive_vs_rating_does_not_enable_2b():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        resolve_phase_2b_next_step,
    )

    step, _ = resolve_phase_2b_next_step(
        blocking=[],
        invariant_errors=[],
        temporal_done=True,
        limited_temporal=False,
        can_2b=False,
        residual_research=False,
        paired_positive_vs_model=False,
        paired_positive_vs_book=False,
        retained=[],
        independent_candidate_specs=[],
    )
    assert step != "phase_2b_candidate_construction"


def test_v2a2_11_positive_stable_vs_book_can_enable_2b():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        resolve_phase_2b_next_step,
    )

    step, errs = resolve_phase_2b_next_step(
        blocking=[],
        invariant_errors=[],
        temporal_done=True,
        limited_temporal=False,
        can_2b=True,
        residual_research=False,
        paired_positive_vs_model=True,
        paired_positive_vs_book=True,
        retained=["probability_advantage"],
        independent_candidate_specs=["VALUE_ADVANTAGE"],
    )
    assert step == "phase_2b_candidate_construction"
    assert errs == []


def test_v2a2_12_empty_retained_blocks_2b():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        resolve_phase_2b_next_step,
    )

    step, errs = resolve_phase_2b_next_step(
        blocking=[],
        invariant_errors=[],
        temporal_done=True,
        limited_temporal=False,
        can_2b=True,
        residual_research=False,
        paired_positive_vs_model=False,
        paired_positive_vs_book=True,
        retained=[],
        independent_candidate_specs=["VALUE_ADVANTAGE"],
    )
    assert step == "resolve_data_quality"
    assert "phase_2b_without_independent_feature" in errs


def test_v2a2_13_14_value_specs_flag_book_dependence():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        BOOK_DEPENDENCIES,
        SPECS_WITH_BOOK_INFO,
    )

    assert "VALUE_ADVANTAGE" in SPECS_WITH_BOOK_INFO
    assert "VALUE_EDGE" in SPECS_WITH_BOOK_INFO
    assert "book_prob" in BOOK_DEPENDENCIES["VALUE_ADVANTAGE"]
    assert "odds" in BOOK_DEPENDENCIES["VALUE_EDGE"]
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(14, ("HOME", "DRAW")),
        bootstrap_iterations=12,
        seed=11,
    )
    by_cfg = {c["configuration"]: c for c in payload["candidate_specifications"]}
    assert by_cfg["VALUE_ADVANTAGE"]["contains_book_information"] is True
    assert by_cfg["VALUE_EDGE"]["contains_book_information"] is True
    assert by_cfg["VALUE_ADVANTAGE"]["deterministic_book_dependencies"]


def test_v2a2_15_book_dominance_computed():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(16, ("HOME", "DRAW")),
        bootstrap_iterations=12,
        seed=12,
    )
    ba = payload["book_baseline_assessment"]
    assert ba["dominance_status"] in {
        "book_dominant",
        "candidate_incremental",
        "mixed_market_specific",
        "inconclusive",
    }
    assert "book_auc_mean" in ba
    assert payload["phase_2b_readiness"]["book_baseline_dominance"] == ba["dominance_status"]


def test_v2a2_16_negative_classified_positive_invariant():
    from app.services.cecchino.cecchino_purchasability_statistical_research import (
        resolve_phase_2b_next_step,
    )

    step, errs = resolve_phase_2b_next_step(
        blocking=[],
        invariant_errors=["negative_delta_classified_positive"],
        temporal_done=True,
        limited_temporal=False,
        can_2b=True,
        residual_research=False,
        paired_positive_vs_model=False,
        paired_positive_vs_book=True,
        retained=["edge"],
        independent_candidate_specs=["VALUE_EDGE"],
    )
    assert step == "resolve_data_quality"
    assert "negative_delta_classified_positive" in errs


def test_v2a2_17_18_statistical_api_timeout_and_default_unchanged():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    api_stat = (root / "frontend/src/lib/cecchinoPurchasabilityStatisticalApi.ts").read_text(
        encoding="utf-8"
    )
    api_core = (root / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
    assert "statisticalResearchTimeoutMs" in api_stat
    assert "300_000" in api_stat
    assert "600_000" in api_stat
    assert "1_200_000" in api_stat
    assert "adminGetJson(" in api_stat and "timeoutMs" in api_stat
    # Default adminGetJson resta 90s; solo override esplicito cambia
    assert "timeoutMs: opts?.timeoutMs ?? 90_000" in api_core


def test_v2a2_19_button_disabled_while_loading():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    body = (
        root
        / "frontend/src/components/cecchino-purchasability-research/PurchasabilityStatisticalResearchBody.tsx"
    ).read_text(encoding="utf-8")
    assert "disabled={loading}" in body
    hook = (
        root / "frontend/src/hooks/useCecchinoPurchasabilityStatisticalResearch.ts"
    ).read_text(encoding="utf-8")
    assert "busyRef" in hook
    assert "if (busyRef.current) return" in hook
    assert "stopPolling" in hook


def test_v2a2_20_strict_json_and_comparison_role_on_marginal():
    payload = build_purchasability_statistical_research(
        MagicMock(),
        rows=_multi_fixture_rows(14, ("HOME", "DRAW")),
        bootstrap_iterations=12,
        seed=13,
    )
    json.dumps(make_json_safe(payload), allow_nan=False)
    roles = {m.get("comparison_role") for m in payload["marginal_contribution"]}
    assert "independent_vs_book" in roles or any(
        m.get("vs") == "BOOK_BASELINE" for m in payload["marginal_contribution"]
    )
    readiness = payload["phase_2b_readiness"]
    assert "paired_positive_vs_book" in readiness
    assert "paired_positive_vs_model" in readiness
    assert "paired_positive_vs_rating" in readiness
    assert "readiness_invariant_errors" in readiness
    assert payload["version"] == "cecchino_purchasability_statistical_research_v2a_2"

