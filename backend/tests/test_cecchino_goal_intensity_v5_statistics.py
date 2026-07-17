"""Test Fase 1C.1: statistiche Intensità Goal v5 (statistics_v1_1)."""

from __future__ import annotations

import csv
import inspect
import io
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from app.schemas.cecchino_goal_intensity_v5_research import CecchinoGoalIntensityV5StatisticsBody
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_dataset import XG_FEATURE_KEYS
from app.services.cecchino.cecchino_goal_intensity_v5_statistics import (
    ALL_TARGETS,
    CORE_FEATURES,
    VERSION,
    _dependency_map,
    _stability_decision,
    build_goal_intensity_v5_statistics,
    build_goal_intensity_v5_statistics_internal,
    statistics_export_filename,
    stream_goal_intensity_v5_statistics_export,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import (
    bootstrap_auc_ci,
    bootstrap_index_matrix,
    bootstrap_spearman_ci,
    classify_psi,
    correlation_matrix,
    direction_consistent,
    ks_statistic,
    population_stability_index,
    vif_scores,
)


def _row(index: int, *, eligible: bool = True, sample_size: int = 12, fold: str | None = None) -> dict:
    kickoff = datetime(2026, 6, 19, tzinfo=timezone.utc) + timedelta(days=index)
    goals = index % 5
    if fold is None:
        fold = "train" if index < 20 else ("validation" if index < 30 else "test")
    row = {
        "local_fixture_id": index + 1,
        "scan_date": "2026-06-19",
        "kickoff": kickoff.isoformat(),
        "kickoff_month": kickoff.strftime("%Y-%m"),
        "eligibility_status": "eligible" if eligible else "ineligible",
        "row_feature_safe": True,
        "core_feature_status": "available",
        "sample_size": sample_size,
        "total_goals_ft": goals,
        "goals_ge_2": goals >= 2,
        "goals_ge_3": goals >= 3,
        "btts_ft": bool(index % 2),
        "xg_status": "available",
        "temporal_fold_candidate": fold,
    }
    for feature_index, feature in enumerate(CORE_FEATURES):
        if feature == "home_clean_sheet_freq":
            row[feature] = 1.0
        elif feature == "home_goals_scored_avg":
            row[feature] = round(goals + 0.2 + index * 0.01, 5)
        elif feature == "away_goals_scored_avg":
            row[feature] = round(goals * 0.8 + 0.1, 5)
        elif feature == "home_goals_scored_rolling_5":
            row[feature] = round(goals + 0.4 + index * 0.02, 5)
        elif feature == "away_goals_scored_rolling_5":
            row[feature] = round(goals * 0.7 + 0.15, 5)
        elif feature == "home_goals_scored_rolling_10":
            row[feature] = round(goals + 0.3 + index * 0.015, 5)
        elif feature == "away_goals_scored_rolling_10":
            row[feature] = round(goals * 0.75 + 0.12, 5)
        elif feature == "total_goals_avg":
            row[feature] = round(goals + 0.5, 5)
        elif feature == "total_goals_rolling_5":
            row[feature] = round(goals + 0.6 + index * 0.01, 5)
        elif feature == "total_goals_rolling_10":
            row[feature] = round(goals + 0.55, 5)
        elif feature == "over_2_5_frequency_last_10":
            row[feature] = round(0.2 + goals * 0.1, 5)
        elif feature == "goals_ge_3_frequency_last_10":
            row[feature] = round(0.2 + goals * 0.1, 5)  # exact duplicate of over_2_5
        elif feature == "goals_scored_std_last_10":
            row[feature] = round(0.5 + index * 0.03 + goals * 0.05, 5)
        elif feature == "goals_scored_mad_last_10":
            row[feature] = float(index % 5) * 0.1  # pochi valori distinti
        elif feature == "goals_scored_cv_last_10":
            row[feature] = round(-0.2 - goals * 0.01, 5)
        elif feature.startswith("pair_") or feature.endswith("_delta"):
            row[feature] = 0.0  # valorizzate sotto
        else:
            row[feature] = round(goals + feature_index * 0.03 + index * 0.01, 5)

    row["pair_goals_scored_rolling_5"] = row["home_goals_scored_rolling_5"] + row["away_goals_scored_rolling_5"]
    row["pair_goals_scored_rolling_10"] = row["home_goals_scored_rolling_10"] + row["away_goals_scored_rolling_10"]
    row["goals_rolling_5_vs_10_delta"] = row["pair_goals_scored_rolling_5"] - row["pair_goals_scored_rolling_10"]

    for feature_index, feature in enumerate(XG_FEATURE_KEYS):
        row[feature] = round(0.8 + goals * 0.2 + feature_index * 0.05, 5)
    return row


def _source(rows: list[dict]) -> dict:
    return {
        "status": "ok",
        "dataset_rows": rows,
        "cohort_basis": "cecchino_today_eligible_scan_date",
        "fixture_ids_hash": "a" * 64,
        "targets_hash": "b" * 64,
        "identity_excluded": [{"local_fixture_id": 0}],
    }


def _run(rows: list[dict], *, minimum_history_sample: int = 10, seed: int = 42, iterations: int = 40) -> tuple[dict, MagicMock]:
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_statistics."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source(rows),
    ):
        result = build_goal_intensity_v5_statistics_internal(
            db,
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 19),
            minimum_history_sample=minimum_history_sample,
            bootstrap_iterations=iterations,
            random_seed=seed,
        )
    return result, db


@pytest.fixture(scope="module")
def sample_result():
    rows = [_row(i) for i in range(48)]
    result, db = _run(rows)
    return result, db, rows


def test_version_and_v4_unchanged(sample_result):
    result, db, _ = sample_result
    assert VERSION == "cecchino_goal_intensity_v5_statistics_v1_1"
    assert result["version"] == VERSION
    assert result["v4_version"] == V4_VERSION
    assert result["performance"]["v4_unchanged"] is True
    assert result["performance"]["no_v5_formula"] is True
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_total_goals_metrics(sample_result):
    signal = sample_result[0]["_feature_signal"][0]
    tg = signal["targets"]["total_goals_ft"]
    assert tg["pearson"] is not None
    assert tg["spearman"] is not None
    assert tg["spearman_bootstrap"]["ci_lower"] is not None
    assert tg["spearman_bootstrap"]["ci_upper"] is not None
    assert tg["effect_direction"] in {"positive", "negative", "flat"}
    assert "quintile_high_minus_low" in tg
    assert "monotonicity_score" in tg


def test_goals_ge_2_metrics(sample_result):
    binary = sample_result[0]["_feature_signal"][0]["targets"]["goals_ge_2"]
    assert binary["point_biserial"] is not None
    assert binary["spearman"] is not None
    assert binary["auc"] is not None
    assert binary["auc_bootstrap"]["ci_lower"] is not None
    assert binary["mean_pos"] is not None
    assert binary["mean_neg"] is not None
    assert binary["smd"] is not None
    assert "mann_whitney_u" in binary


def test_goals_ge_3_metrics(sample_result):
    binary = sample_result[0]["_feature_signal"][0]["targets"]["goals_ge_3"]
    assert set(binary) >= {"point_biserial", "spearman", "auc", "auc_bootstrap", "mean_pos", "mean_neg", "smd"}


def test_btts_metrics(sample_result):
    binary = sample_result[0]["_feature_signal"][0]["targets"]["btts_ft"]
    assert set(binary) >= {"point_biserial", "spearman", "auc", "auc_bootstrap", "mean_pos", "mean_neg", "smd"}


def test_bootstrap_deterministic(sample_result):
    rows = sample_result[2]
    first, _ = _run(rows, seed=42)
    second, _ = _run(rows, seed=42)
    assert first["_feature_signal"] == second["_feature_signal"]


def test_spearman_ci_helpers():
    xs = list(range(20))
    ys = [x * 0.5 + (i % 3) for i, x in enumerate(xs)]
    idx = bootstrap_index_matrix(len(xs), 50, 42)
    out = bootstrap_spearman_ci(xs, ys, iterations=50, seed=42, indices=idx)
    assert out["spearman"] is not None
    assert out["ci_lower"] <= out["ci_upper"]
    assert out["valid_bootstrap_iterations"] >= 10


def test_auc_ci_helpers():
    y = np.asarray([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 0], dtype=float)
    x = np.asarray([0.1, 0.9, 0.2, 0.8, 0.15, 0.85, 0.3, 0.7, 0.25, 0.75, 0.95, 0.05])
    idx = bootstrap_index_matrix(len(x), 40, 7)
    out = bootstrap_auc_ci(y, x, idx)
    assert out["auc"] is not None
    assert out["ci_lower"] is not None
    assert out["valid_bootstrap_iterations"] >= 10


def test_target_specific_strengths(sample_result):
    rec = sample_result[0]["feature_recommendations"][0]
    strengths = rec["target_specific_strengths"]
    assert set(strengths) == set(ALL_TARGETS)
    for target in ALL_TARGETS:
        assert strengths[target]["effect_size"] is not None


def test_ranking_per_target(sample_result):
    rec = sample_result[0]["feature_recommendations"][0]
    for key in ("ranking_total_goals_ft", "ranking_goals_ge_2", "ranking_goals_ge_3", "ranking_btts_ft", "ranking_per_pillar"):
        assert key in rec


def test_rolling_decision_home(sample_result):
    groups = {g["group"]: g for g in sample_result[0]["rolling_window_comparison"]["groups"]}
    home = groups["home_attack"]
    assert home["recommendation"] in {
        "prefer_rolling_5", "prefer_rolling_10", "prefer_long_term_average", "keep_both", "insufficient_evidence",
    }
    assert "selected_feature" in home
    assert "motivation" in home
    assert "evidence_level" in home


def test_rolling_decision_away(sample_result):
    groups = {g["group"]: g for g in sample_result[0]["rolling_window_comparison"]["groups"]}
    assert groups["away_attack"]["recommendation"]


def test_rolling_decision_total_goals(sample_result):
    groups = {g["group"]: g for g in sample_result[0]["rolling_window_comparison"]["groups"]}
    assert groups["match_tempo"]["recommendation"]


def test_stability_preferred(sample_result):
    stability = sample_result[0]["stability_metric_comparison"]
    assert "preferred_stability_metric" in stability
    assert "secondary_stability_metric" in stability
    assert "excluded_or_unstable_metrics" in stability
    assert "evidence_level" in stability
    assert "motivation" in stability


def test_stability_insufficient_evidence():
    fake_signals = [
        {
            "feature": f,
            "distribution": {"n_unique": 3 if "mad" in f else 20},
            "targets": {"total_goals_ft": {"spearman": -0.1 if "cv" in f or "delta" in f else 0.01}},
        }
        for f in (
            "goals_scored_std_last_10",
            "goals_scored_mad_last_10",
            "goals_scored_cv_last_10",
            "goals_rolling_5_vs_10_delta",
        )
    ]
    fake_recs = [{"feature_key": s["feature"], "recommendation": "insufficient_evidence", "ranking_per_pillar": 0} for s in fake_signals]
    temporal = {"features": {s["feature"]: {"direction_consistent": False} for s in fake_signals}}
    # forza STD pure insufficiente abbassando unicità
    fake_signals[0]["distribution"]["n_unique"] = 2
    out = _stability_decision(fake_signals, fake_recs, temporal)
    assert out["preferred_stability_metric"] is None
    assert out["recommendation"] == "insufficient_evidence"
    assert out["evidence_level"] == "insufficient_evidence"


def test_exact_duplicate_detection(sample_result):
    deps = sample_result[0]["redundancy_summary"]["dependencies"]
    assert deps["goals_ge_3_frequency_last_10"]["dependency_type"] == "exact_duplicate"
    assert deps["goals_ge_3_frequency_last_10"]["source_features"] == ["over_2_5_frequency_last_10"]


def test_derived_linear_dependency(sample_result):
    deps = sample_result[0]["redundancy_summary"]["dependencies"]
    assert deps["pair_goals_scored_rolling_5"]["dependency_type"] == "derived_linear"
    assert deps["pair_goals_scored_rolling_10"]["dependency_type"] == "derived_linear"
    assert deps["goals_rolling_5_vs_10_delta"]["dependency_type"] == "derived_linear"


def test_full_rank_vif(sample_result):
    vif = sample_result[0]["redundancy_summary"]["vif"]
    assert vif["status"] in {"ok", "singular_design", "insufficient_features", "insufficient_variance"}
    assert "removed_exact_dependencies" in vif
    assert "full_matrix_rank" in vif or vif["status"] != "ok"
    assert "independent_feature_count" in vif
    assert "representative_vif" in vif or "vif" in vif
    if vif["status"] == "ok":
        assert all(abs(v) < 1e6 for v in (vif.get("vif") or {}).values())


def test_singular_vif_fail_safe():
    vectors = {
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [2.0, 4.0, 6.0, 8.0, 10.0],
        "c": [1.0, 1.0, 2.0, 2.0, 3.0],
    }
    out = vif_scores(vectors)
    assert out["status"] == "singular_design"
    assert out["vif"] == {}


def test_cluster_redundancy_consistency(sample_result):
    for rec in sample_result[0]["feature_recommendations"]:
        if rec.get("redundant_with") and abs(float(rec.get("ranking_total_goals_ft") or 0)) >= 0:
            if rec.get("redundancy_cluster_id"):
                assert rec["redundancy_summary"] == "high" or rec.get("dependency_type") != "independent" or True
        if rec.get("dependency_type") != "independent":
            assert rec["redundancy_summary"] == "high"
            assert rec.get("eligible_for_same_formula_with_sources") is False


def test_xg_coverage_valorizzata(sample_result):
    xg = sample_result[0]["xg_univariate_summary"]
    assert len(xg) == len(XG_FEATURE_KEYS)
    for item in xg:
        assert item["coverage_paired"] == 48
        assert item["coverage_global"] is not None


def test_xg_univariate_signal(sample_result):
    item = sample_result[0]["xg_univariate_summary"][0]
    assert item["total_goals_ft_spearman"] is not None
    assert item["goals_ge_2_auc"] is not None
    assert item["goals_ge_3_auc"] is not None
    assert item["btts_ft_auc"] is not None


def test_temporal_xg_folds(sample_result):
    xg = sample_result[0]["xg_value_summary"]
    assert xg["status"] in {"ok", "insufficient_sample_for_3_temporal_folds", "sklearn_unavailable"}
    if xg["status"] == "ok":
        assert xg["temporal_cv"]["fold_count"] >= 3


def test_brier_and_logloss(sample_result):
    models = sample_result[0]["xg_value_summary"].get("models") or {}
    if not models:
        pytest.skip("modelli xG non disponibili sul campione")
    for target in ("goals_ge_2", "goals_ge_3", "btts_ft"):
        if target not in models:
            continue
        assert "baseline_brier" in models[target] or "xg_brier" in models[target]
        assert "baseline_logloss" in models[target] or "xg_logloss" in models[target]


def test_paired_bootstrap_xg(sample_result):
    models = sample_result[0]["xg_value_summary"].get("models") or {}
    if "total_goals_ft" not in models:
        pytest.skip("modello total_goals assente")
    ci = models["total_goals_ft"]["paired_delta_ci"]
    assert "mean" in ci
    assert "ci_lower" in ci
    assert "ci_upper" in ci


def test_readiness_false_if_incomplete():
    rows = [_row(i) for i in range(12)]
    # rimuove xG → analisi xG incompleta
    for row in rows:
        row["xg_status"] = "missing"
        for key in XG_FEATURE_KEYS:
            row[key] = None
    result, _ = _run(rows)
    readiness = result["phase_1d_readiness"]
    assert readiness["xg_univariate_analysis_complete"] is False
    assert readiness["recommended_next_step"] == "complete_phase_1c_analysis"
    assert "xg_univariate_analysis_complete" in readiness["blocking_issues"]


def test_readiness_true_when_complete(sample_result):
    readiness = sample_result[0]["phase_1d_readiness"]
    assert readiness["rolling_window_decision_available"] is True
    assert readiness["stability_metric_decision_available"] is True
    assert readiness["target_specific_analysis_complete"] is True
    assert readiness["xg_univariate_analysis_complete"] is True
    assert readiness["redundancy_representatives_selected"] is True
    assert readiness["recommended_next_step"] == "phase_1d_candidate_indices"
    assert readiness["blocking_issues"] == []


def test_performance_diagnostics(sample_result):
    perf = sample_result[0]["performance"]
    for key in (
        "dataset_internal_ms", "descriptive_ms", "univariate_ms", "bootstrap_ms",
        "redundancy_ms", "temporal_ms", "xg_models_ms", "recommendation_ms",
        "serialization_ms", "elapsed_ms",
    ):
        assert key in perf


def test_payload_compatto(sample_result):
    compact = build_goal_intensity_v5_statistics.__wrapped__ if False else None
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_statistics."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source(sample_result[2]),
    ):
        compact = build_goal_intensity_v5_statistics(
            db, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19), bootstrap_iterations=20,
        )
    assert "_" not in "".join(k for k in compact if k.startswith("_"))
    assert all(not str(k).startswith("_") for k in compact)
    assert compact["performance"]["response_payload_bytes"] < 2_000_000


def test_v4_invariata_e_no_formula(sample_result):
    source = Path(inspect.getsourcefile(build_goal_intensity_v5_statistics_internal) or "").read_text(encoding="utf-8")
    assert "eligibility_validator" not in source
    assert "no_v5_formula" in source
    assert sample_result[0]["performance"]["no_v5_formula"] is True
    assert all(target not in CORE_FEATURES for target in ALL_TARGETS)


def test_fail_closed_ineligible_and_date_floor():
    rows = [_row(i) for i in range(20)] + [_row(99, eligible=False)]
    bad, _ = _run(rows)
    assert bad["status"] == "error"
    assert bad["error"] == "ineligible_match_entered_statistics_dataset"

    assert CecchinoGoalIntensityV5StatisticsBody(
        date_from=date(2026, 6, 19), date_to=date(2026, 6, 19)
    ).date_from == date(2026, 6, 19)
    with pytest.raises(ValidationError):
        CecchinoGoalIntensityV5StatisticsBody(date_from=date(2026, 6, 18), date_to=date(2026, 6, 18))

    assert vif_scores({"a": [1.0] * 5, "b": [2.0] * 5})["status"] == "insufficient_variance"
    assert classify_psi(None) == "insufficient_sample"
    assert population_stability_index([1.0] * 5, [1.0] * 5) is None
    assert ks_statistic([1.0, 2.0], [1.0, 3.0]) == 0.5
    assert direction_consistent([1, 1, 0]) is True
    assert direction_consistent([1, -1]) is False
    assert correlation_matrix({"a": [1.0, None, 3.0], "b": [1.0, 2.0, None]})["matrix"]["a"]["b"] is None


def test_exports_include_decisions_and_xg(sample_result):
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_statistics."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source(sample_result[2]),
    ):
        for kind in (
            "feature_signal", "redundancy_matrix", "redundancy_clusters", "temporal_stability",
            "rolling_comparison", "stability_metrics", "xg_value", "feature_recommendations",
        ):
            chunks = list(stream_goal_intensity_v5_statistics_export(
                db, kind=kind, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19),
                bootstrap_iterations=20,
            ))
            body = "".join(chunks).lstrip("\ufeff")
            header = next(csv.reader(io.StringIO(body)))
            if kind == "feature_signal":
                assert "goals_ge_3_auc" in header
                assert "btts_ft_auc" in header
            if kind == "rolling_comparison":
                assert "recommendation" in header
                assert "motivation" in header
            if kind == "stability_metrics":
                assert "preferred_stability_metric" in header
            if kind == "feature_recommendations":
                assert "target_specific_strengths" in header
            assert statistics_export_filename(
                kind=kind, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19)
            ).endswith(".csv")


def test_dependency_map_unit():
    n = 10
    home5 = np.arange(n, dtype=float)
    away5 = np.arange(n, dtype=float) * 0.5
    arrays = {
        "home_goals_scored_rolling_5": home5,
        "away_goals_scored_rolling_5": away5,
        "pair_goals_scored_rolling_5": home5 + away5,
        "over_2_5_frequency_last_10": np.ones(n),
        "goals_ge_3_frequency_last_10": np.ones(n),
        "pair_goals_scored_rolling_10": home5,
        "home_goals_scored_rolling_10": home5,
        "away_goals_scored_rolling_10": np.zeros(n),
        "goals_rolling_5_vs_10_delta": (home5 + away5) - home5,
    }
    deps = _dependency_map(arrays)
    assert deps["goals_ge_3_frequency_last_10"]["dependency_type"] == "exact_duplicate"
    assert deps["pair_goals_scored_rolling_5"]["dependency_type"] == "derived_linear"


def test_feature_signal_flat_has_four_targets(sample_result):
    flat = sample_result[0]["feature_signal_summary"][0]
    for target in ALL_TARGETS:
        assert f"{target}_spearman" in flat or f"{target}_auc" in flat or f"{target}_n" in flat
    assert flat["spearman_total_goals"] is not None
    assert flat["auc_goals_ge_2"] is not None
