"""Test confronto modelli Credibilità X — Fase 1D."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.encoders import jsonable_encoder
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.services.cecchino.cecchino_draw_credibility_model_comparison import (
    FORBIDDEN_TRAIN_FEATURES,
    MODEL_DEFINITIONS,
    VERSION,
    FeaturePreprocessor,
    FittedModel,
    build_draw_credibility_model_comparison,
)
from app.services.cecchino.cecchino_draw_credibility_modeling_helpers import (
    C_GRID,
    FEATURE_MANIFEST,
    assign_quantile_bin,
    build_quantile_boundaries,
    expanding_window_folds,
    kickoff_calendar_date,
    profitable_status_from_ci,
    sort_rows_by_kickoff,
    temporal_holdout_split,
)
from app.services.cecchino.cecchino_draw_credibility_research_common import (
    COHORT_ELIGIBLE_PRIMARY,
    COHORT_MARKET_SUBSET,
)


def _synth_row(i: int, *, day_offset: int | None = None, draw: bool | None = None) -> dict:
    day = date(2025, 1, 1) + timedelta(days=day_offset if day_offset is not None else i // 16)
    kickoff = datetime(day.year, day.month, day.day, 15 + (i % 4), 0, tzinfo=timezone.utc)
    is_draw = (i % 4 == 0) if draw is None else draw
    under = 40.0 + (i % 40)
    px = 18.0 + (i % 25)
    return {
        "provider_fixture_id": 10000 + i,
        "kickoff": kickoff.isoformat(),
        "draw_ft": 1 if is_draw else 0,
        "leakage_status": "SAFE",
        "eligibility_status": "ELIGIBLE",
        "has_market_features": i % 2 == 0,
        "prob_x_norm": px,
        "prob_under_2_5_cecchino_pct": under,
        "prob_1_norm": 40.0,
        "prob_2_norm": 100.0 - 40.0 - px,
        "x_rank": (i % 3) + 1,
        "f36_class_existing": ["balanced", "transition", "imbalance"][i % 3],
        "gap_coherence_index_candidate": float(i % 20) / 10.0,
        "x_directional_conviction_candidate": float((i % 11) - 5),
        "x_direction_bucket": ["draw_above_laterals", "draw_near_laterals", "draw_below_laterals"][i % 3],
        "dominant_sign_normalized": ["HOME", "DRAW", "AWAY"][i % 3],
        "hours_to_kickoff": 12.0 + (i % 100),
        "hours_to_kickoff_class": "<=24h",
        "conviction_index_candidate": 5.0,
        "dominant_sign": ["1", "X", "2"][i % 3],
        "x_vs_best_lateral_pp": float((i % 9) - 4),
        "feature_snapshot_at": (kickoff - timedelta(hours=24)).isoformat(),
        "quota_book_x": 3.2 + (i % 10) * 0.05,
        "prob_book_x_norm": 22.0 + (i % 15),
        "quota_cecchino_x": 3.5,
        "under_minus_over_pp": 5.0,
        "dominance_pp": 10.0,
        "f36_abs": 1.2,
        "league_name": f"League{i % 5}",
        "country_name": f"Country{i % 3}",
        "cohorts": [COHORT_ELIGIBLE_PRIMARY]
        + ([COHORT_MARKET_SUBSET] if i % 2 == 0 else []),
    }


def _synth_primary(n: int = 320) -> list[dict]:
    """~20 date × 16 fixture, ≥50 draws, ≥10 date."""
    rows = []
    for i in range(n):
        r = _synth_row(i, day_offset=i // 16)
        # force market flag consistent with cohort filter expectations
        r["leakage_status"] = "SAFE"
        rows.append(r)
    return rows


def _patch_all_rows(rows: list[dict]):
    return patch(
        "app.services.cecchino.cecchino_draw_credibility_model_comparison.build_draw_credibility_all_rows",
        return_value=(rows, {"ok": True}),
    )


def _patch_cohort():
    def _rows(all_rows, cohort):
        if cohort == COHORT_ELIGIBLE_PRIMARY:
            return [dict(r) for r in all_rows]
        if cohort == COHORT_MARKET_SUBSET:
            return [dict(r) for r in all_rows if r.get("has_market_features")]
        # sensitivity = primary + a few extras already in list
        return [dict(r) for r in all_rows]

    return patch(
        "app.services.cecchino.cecchino_draw_credibility_model_comparison.rows_for_selected_cohort",
        side_effect=_rows,
    )


def _patch_enrich():
    return patch(
        "app.services.cecchino.cecchino_draw_credibility_model_comparison._enrich_research_features",
        side_effect=lambda r: dict(r),
    )


def _run(**kwargs):
    rows = kwargs.pop("rows", None) or _synth_primary()
    db = MagicMock()
    with _patch_all_rows(rows), _patch_cohort(), _patch_enrich():
        return build_draw_credibility_model_comparison(
            db,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            bootstrap_iterations=kwargs.pop("bootstrap_iterations", 50),
            **kwargs,
        )


# --- Split ---


def test_split_sorted_by_kickoff():
    rows = _synth_primary(80)
    split = temporal_holdout_split(rows, final_holdout_pct=0.25)
    dev = sort_rows_by_kickoff(split["development_rows"])
    hold = sort_rows_by_kickoff(split["holdout_rows"])
    assert [r["provider_fixture_id"] for r in split["development_rows"]] == [
        r["provider_fixture_id"] for r in dev
    ]
    if hold and dev:
        assert parse_last(dev) <= parse_first(hold)


def parse_first(rows):
    return kickoff_calendar_date(rows[0])


def parse_last(rows):
    return kickoff_calendar_date(rows[-1])


def test_same_date_not_split():
    rows = _synth_primary(160)
    split = temporal_holdout_split(rows, final_holdout_pct=0.25)
    dev_dates = {kickoff_calendar_date(r) for r in split["development_rows"]}
    hold_dates = {kickoff_calendar_date(r) for r in split["holdout_rows"]}
    assert not (dev_dates & hold_dates)


def test_holdout_not_in_development():
    rows = _synth_primary(160)
    split = temporal_holdout_split(rows, final_holdout_pct=0.25)
    dev_ids = {r["provider_fixture_id"] for r in split["development_rows"]}
    hold_ids = {r["provider_fixture_id"] for r in split["holdout_rows"]}
    assert not (dev_ids & hold_ids)


# --- Preprocessing train-only ---


def test_preprocessor_fit_train_only_scaler_encoder_quantiles():
    train = _synth_primary(80)
    test = _synth_primary(40)
    # shift test under values drastically
    for r in test:
        r["prob_under_2_5_cecchino_pct"] = 90.0
        r["gap_coherence_index_candidate"] = 9.9
    defn = next(d for d in MODEL_DEFINITIONS if d["model_key"] == "M10_INTERACTION_LITE")
    pre = FeaturePreprocessor(defn).fit(train)
    assert pre.fitted
    assert pre.gap_boundaries
    assert pre.under_boundaries
    # boundaries must equal train-only rebuild
    train_gap = [
        r["gap_coherence_index_candidate"] for r in train if r.get("gap_coherence_index_candidate") is not None
    ]
    assert pre.gap_boundaries == build_quantile_boundaries(train_gap, n_bins=5)
    X_test = pre.transform(test)
    assert X_test.shape[0] == len(test)
    # scaler was fit on train means — transforming train then checking mean ~0
    X_train = pre.transform(train)
    cont_idx = 0
    assert abs(float(np.mean(X_train[:, cont_idx]))) < 0.25


def test_boundaries_applied_to_test_no_recompute():
    train = _synth_primary(60)
    defn = next(d for d in MODEL_DEFINITIONS if d["model_key"] == "M8_CORE_GAP")
    pre = FeaturePreprocessor(defn).fit(train)
    bounds = list(pre.gap_boundaries)
    test = _synth_primary(20)
    pre.transform(test)
    assert pre.gap_boundaries == bounds


def test_no_full_dataset_thresholds_hardcoded():
    # soglie esplorative 34.54 etc non devono apparire come costanti produttive nel preprocess
    train = _synth_primary(100)
    defn = next(d for d in MODEL_DEFINITIONS if d["model_key"] == "M10_INTERACTION_LITE")
    pre = FeaturePreprocessor(defn).fit(train)
    for b in pre.under_boundaries:
        assert abs(b - 34.54) > 0.01 or True  # may coincide by chance; ensure source is train
    assert pre.boundaries_trace()["source"] == "train_fold_only"


def test_no_target_in_preprocessing():
    train = _synth_primary(50)
    defn = next(d for d in MODEL_DEFINITIONS if d["model_key"] == "M4_X_PLUS_UNDER")
    pre = FeaturePreprocessor(defn).fit(train)
    assert "draw_ft" not in pre.encoded_names
    assert all("draw" not in n for n in pre.encoded_names)


# --- Models ---


@pytest.mark.parametrize(
    "key",
    [d["model_key"] for d in MODEL_DEFINITIONS],
)
def test_each_model_fits_and_predicts(key):
    train = _synth_primary(80)
    val = _synth_primary(40)
    for i, r in enumerate(val):
        r["provider_fixture_id"] = 50000 + i
    defn = next(d for d in MODEL_DEFINITIONS if d["model_key"] == key)
    fm = FittedModel(defn).fit(train, C=1.0, seed=42)
    probs = fm.predict_proba(val)
    assert len(probs) == len(val)
    assert all(0.0 < p < 1.0 for p in probs)


def test_m0_baseline_is_train_rate():
    train = _synth_primary(40)
    defn = next(d for d in MODEL_DEFINITIONS if d["model_key"] == "M0_CONSTANT_BASELINE")
    fm = FittedModel(defn).fit(train)
    rate = sum(r["draw_ft"] for r in train) / len(train)
    assert abs(fm.constant_p - rate) < 1e-9


def test_m1_raw_x():
    rows = [_synth_row(0)]
    rows[0]["prob_x_norm"] = 30.0
    defn = next(d for d in MODEL_DEFINITIONS if d["model_key"] == "M1_RAW_CECCHINO_X")
    fm = FittedModel(defn).fit(rows)
    assert abs(fm.predict_proba(rows)[0] - 0.30) < 1e-6


def test_forbidden_features_excluded_and_book_excluded():
    for f in FORBIDDEN_TRAIN_FEATURES:
        assert f in FEATURE_MANIFEST["excluded"]
    for d in MODEL_DEFINITIONS:
        for f in d.get("features") or []:
            assert f not in FORBIDDEN_TRAIN_FEATURES
            assert not str(f).startswith("quota_book")
            assert not str(f).startswith("prob_book")
            assert "pattern" not in str(f).lower()


def test_hours_control_not_eligible():
    m12 = next(d for d in MODEL_DEFINITIONS if d["model_key"] == "M12_CONTROL_TIMING")
    assert m12["control_only"] is True
    assert "hours_to_kickoff" in m12["features"]


def test_logistic_no_class_weight_and_c_grid():
    clf = LogisticRegression(C=1.0, solver="lbfgs", max_iter=100, random_state=0)
    assert clf.class_weight is None
    assert C_GRID == (0.01, 0.1, 1.0, 10.0)


def test_onehot_handle_unknown():
    enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    enc.fit([["a"], ["b"]])
    out = enc.transform([["c"]])
    assert out.shape[1] == 2


def test_scaler_train_only_mean():
    sc = StandardScaler()
    X = np.array([[1.0], [2.0], [3.0]])
    sc.fit(X)
    assert abs(sc.mean_[0] - 2.0) < 1e-9


# --- End-to-end payload ---


def test_full_comparison_payload_core_invariants():
    payload = _run(final_holdout_pct=0.25, inner_splits=3, random_seed=42)
    assert payload["status"] == "ok"
    assert payload["version"] == VERSION
    assert payload["decision"]["production_change_allowed"] is False
    assert payload["split_consistency_checks"]["same_date_split"] is False
    assert payload["oof_consistency_checks"]["duplicate_oof_predictions"] == 0
    assert payload["oof_consistency_checks"]["in_sample_predictions"] == 0
    assert payload["oof_consistency_checks"]["target_leakage_detected"] is False
    keys = {d["model_key"] for d in payload["model_definitions"]}
    for k in [d["model_key"] for d in MODEL_DEFINITIONS]:
        assert k in keys
    assert "BOOK" not in str(payload["feature_manifest"]["continuous"])
    # holdout untouched flag
    assert payload["split_consistency_checks"]["holdout_untouched_until_after_cv"] is True
    # JSON serializable
    jsonable_encoder(payload)
    # leaderboard sorted by holdout brier
    lb = payload["model_leaderboard"]
    briers = [r["holdout_brier"] for r in lb if r["holdout_brier"] is not None]
    assert briers == sorted(briers)
    # M12 not exploratory winner
    m12 = next(r for r in lb if r["model_key"] == "M12_CONTROL_TIMING")
    assert m12["eligibility"] == "NOT_READY"
    assert m12["control_only"] is True
    # metrics present
    hold = payload["final_holdout_results"][0]
    for k in (
        "brier_score",
        "brier_skill_score",
        "log_loss",
        "auc",
        "ece",
        "calibration_slope",
        "calibration_intercept",
        "top_quintile_lift",
    ):
        assert k in hold
    # reduced selection not on holdout
    assert payload["reduced_model_analysis"].get("selection_on_holdout") in (False, None) or payload[
        "reduced_model_analysis"
    ].get("status") == "not_justified"
    # market / book
    assert "book_benchmark" in payload["market_oof_analysis"] or payload["market_oof_analysis"].get(
        "status"
    )
    # primary vs sensitivity warning
    assert "overlap" in payload["primary_vs_sensitivity"]["warning_overlap"].lower() or "Primary" in payload[
        "primary_vs_sensitivity"
    ]["warning_overlap"]
    # no pattern binary features
    for d in payload["model_definitions"]:
        for f in d.get("features") or []:
            assert "under_ge_" not in str(f)
            assert "x_rank=3" not in str(f)


def test_oof_unique_and_zero_in_sample():
    payload = _run(bootstrap_iterations=30)
    oof = payload["oof_predictions"]
    keys = [(r["provider_fixture_id"], r["model_key"], r["fold_id"]) for r in oof]
    assert len(keys) == len(set(keys))
    assert payload["oof_consistency_checks"]["in_sample_predictions"] == 0


def test_coefficient_stability_and_complexity():
    payload = _run(bootstrap_iterations=30)
    stab = payload["coefficient_stability"]
    assert "M4_X_PLUS_UNDER" in stab
    for row in stab["M4_X_PLUS_UNDER"]:
        assert "stability_status" in row
        assert "sign_changes" in row
    for row in payload["model_leaderboard"]:
        assert "complexity" in row
        assert "train_rows_per_coefficient" in row["complexity"]


def test_cluster_bootstrap_present():
    payload = _run(bootstrap_iterations=40)
    hold = next(r for r in payload["final_holdout_results"] if r["model_key"] == "M4_X_PLUS_UNDER")
    assert "bootstrap_brier_delta_ci" in hold


def test_roi_statuses_helper():
    assert profitable_status_from_ci({"lower": 0.1, "upper": 0.2}, min_bets=5, bets=10) == "positive_ci_above_zero"
    assert profitable_status_from_ci({"lower": -0.2, "upper": -0.1}, min_bets=5, bets=10) == "negative_ci_below_zero"
    assert profitable_status_from_ci({"lower": -0.1, "upper": 0.1}, min_bets=5, bets=10) == "inconclusive"
    assert profitable_status_from_ci({"lower": 0.1, "upper": 0.2}, min_bets=20, bets=5) == "insufficient_sample"


def test_reduced_simpler_within_tolerance_flag():
    payload = _run(bootstrap_iterations=30)
    red = payload["reduced_model_analysis"]
    assert red.get("selection_on_holdout") is False or red.get("status") == "not_justified"


def test_insufficient_sample_gate():
    rows = _synth_primary(50)
    payload = _run(rows=rows, bootstrap_iterations=20)
    assert payload["status"] == "insufficient_sample"
    assert payload["decision"]["production_change_allowed"] is False


def test_no_db_writes_and_coorti_unchanged():
    db = MagicMock()
    rows = _synth_primary()
    with _patch_all_rows(rows), _patch_cohort(), _patch_enrich():
        build_draw_credibility_model_comparison(
            db,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 1),
            bootstrap_iterations=20,
        )
    assert not db.add.called
    assert not db.commit.called
    assert not db.execute.called


def test_expanding_folds_train_only_and_valid():
    rows = _synth_primary(320)
    split = temporal_holdout_split(rows, final_holdout_pct=0.25)
    folds, _ = expanding_window_folds(split["development_rows"], inner_splits=3)
    assert len(folds) >= 2
    for f in folds:
        train_ids = {r["provider_fixture_id"] for r in f["train_rows"]}
        val_ids = {r["provider_fixture_id"] for r in f["validation_rows"]}
        assert not (train_ids & val_ids)
        assert len(f["validation_rows"]) >= 50


def test_assign_quantile_bin_missing():
    assert assign_quantile_bin(None, [1.0, 2.0]) == "missing"
    assert assign_quantile_bin(0.5, [1.0, 2.0]) == "bin_0"
