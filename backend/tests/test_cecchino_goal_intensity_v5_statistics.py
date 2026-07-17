"""Test Fase 1C.2: normalizzazione raccomandazioni Intensità Goal v5 (statistics_v1_2)."""

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
    # Target monotono per fold: evita inversioni spurii di segno Spearman.
    goals = 1 + (index // 6) % 4
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
            row[feature] = round(max(0.05, 0.55 - goals * 0.08), 5)
        elif feature == "away_clean_sheet_freq":
            row[feature] = round(max(0.05, 0.5 - goals * 0.07), 5)
        elif feature == "home_goals_conceded_avg":
            row[feature] = round(0.6 + goals * 0.4, 5)
        elif feature == "away_goals_conceded_avg":
            row[feature] = round(0.55 + goals * 0.38, 5)
        elif feature == "home_goals_scored_avg":
            row[feature] = round(0.4 + goals * 0.55, 5)
        elif feature.startswith("away_goals_scored"):
            base = 0.3 + goals * 0.5
            row[feature] = round((4.0 - base) if fold == "test" else base, 5)
        elif feature == "home_goals_scored_rolling_5":
            row[feature] = round(0.45 + goals * 0.5, 5)
        elif feature == "home_goals_scored_rolling_10":
            row[feature] = round(0.42 + goals * 0.52, 5)
        elif feature == "total_goals_avg":
            row[feature] = round(0.5 + goals * 0.7, 5)
        elif feature == "total_goals_rolling_5":
            row[feature] = round(0.55 + goals * 0.65, 5)
        elif feature == "total_goals_rolling_10":
            row[feature] = round(0.52 + goals * 0.66, 5)
        elif feature == "over_2_5_frequency_last_10":
            row[feature] = round(0.15 + goals * 0.12, 5)
        elif feature == "goals_ge_3_frequency_last_10":
            row[feature] = round(0.15 + goals * 0.12, 5)
        elif feature == "goals_ge_2_frequency_last_10":
            row[feature] = round(0.25 + goals * 0.1, 5)
        elif feature == "gg_frequency_last_10":
            row[feature] = round(0.2 + goals * 0.08, 5)
        elif feature == "goals_scored_std_last_10":
            row[feature] = round(0.4 + goals * 0.25 + index * 0.02, 5)
        elif feature == "goals_scored_mad_last_10":
            row[feature] = float(goals % 5) * 0.1
        elif feature == "goals_scored_cv_last_10":
            row[feature] = round(-0.15 - goals * 0.02, 5)
        elif feature.startswith("pair_") or feature.endswith("_delta"):
            row[feature] = 0.0
        else:
            row[feature] = round(0.2 + goals * 0.2 + feature_index * 0.01, 5)

    row["pair_goals_scored_rolling_5"] = round(
        0.5 * (row["home_goals_scored_rolling_5"] + row["away_goals_scored_rolling_5"]), 5
    )
    row["pair_goals_scored_rolling_10"] = round(
        0.5 * (row["home_goals_scored_rolling_10"] + row["away_goals_scored_rolling_10"]), 5
    )
    row["goals_rolling_5_vs_10_delta"] = round(
        row["pair_goals_scored_rolling_5"] - row["pair_goals_scored_rolling_10"], 5
    )

    for feature_index, feature in enumerate(XG_FEATURE_KEYS):
        row[feature] = round(0.5 + goals * 0.25 + feature_index * 0.03, 5)
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


def _by_key(result):
    return {r["feature_key"]: r for r in result["feature_recommendations"]}


def _rolling_groups(result):
    return {g["group"]: g for g in result["rolling_window_comparison"]["groups"]}


def test_version_and_v4_unchanged(sample_result):
    result, db, _ = sample_result
    assert VERSION == "cecchino_goal_intensity_v5_statistics_v1_2"
    assert result["version"] == VERSION
    assert result["v4_version"] == V4_VERSION
    assert result["performance"]["v4_unchanged"] is True
    assert result["performance"]["no_v5_formula"] is True
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_selected_not_in_excluded(sample_result):
    for group in sample_result[0]["rolling_window_comparison"]["groups"]:
        selected = group.get("selected_feature")
        excluded = group.get("excluded_redundant_features") or []
        if selected:
            assert selected not in excluded


def test_secondary_not_in_excluded(sample_result):
    for group in sample_result[0]["rolling_window_comparison"]["groups"]:
        secondary = group.get("secondary_feature")
        excluded = group.get("excluded_redundant_features") or []
        if secondary:
            assert secondary not in excluded


def test_selected_differs_from_secondary(sample_result):
    for group in sample_result[0]["rolling_window_comparison"]["groups"]:
        selected = group.get("selected_feature")
        secondary = group.get("secondary_feature")
        if selected and secondary:
            assert selected != secondary


def test_pair_rolling_5_derived(sample_result):
    deps = sample_result[0]["redundancy_summary"]["dependencies"]
    assert deps["pair_goals_scored_rolling_5"]["dependency_type"] in {"derived_aggregate", "derived_linear"}
    assert set(deps["pair_goals_scored_rolling_5"]["source_features"]) == {
        "home_goals_scored_rolling_5", "away_goals_scored_rolling_5",
    }


def test_pair_rolling_10_derived(sample_result):
    deps = sample_result[0]["redundancy_summary"]["dependencies"]
    assert deps["pair_goals_scored_rolling_10"]["dependency_type"] in {"derived_aggregate", "derived_linear"}


def test_delta_derived(sample_result):
    deps = sample_result[0]["redundancy_summary"]["dependencies"]
    assert deps["goals_rolling_5_vs_10_delta"]["dependency_type"] == "derived_linear"


def test_exact_duplicate_over_ge3(sample_result):
    deps = sample_result[0]["redundancy_summary"]["dependencies"]
    assert deps["goals_ge_3_frequency_last_10"]["dependency_type"] == "exact_duplicate"
    assert deps["goals_ge_3_frequency_last_10"]["source_features"] == ["over_2_5_frequency_last_10"]


def test_exact_duplicate_not_candidate_core(sample_result):
    rec = _by_key(sample_result[0])["goals_ge_3_frequency_last_10"]
    assert rec["recommendation"] != "candidate_core"


def test_stability_excluded_not_candidate_core(sample_result):
    excluded = set(sample_result[0]["stability_metric_comparison"]["excluded_or_unstable_metrics"] or [])
    by_key = _by_key(sample_result[0])
    for feature in excluded:
        assert by_key[feature]["recommendation"] != "candidate_core"


def test_cv_not_candidate_core(sample_result):
    assert _by_key(sample_result[0])["goals_scored_cv_last_10"]["recommendation"] != "candidate_core"


def test_mad_not_candidate_core(sample_result):
    assert _by_key(sample_result[0])["goals_scored_mad_last_10"]["recommendation"] != "candidate_core"


def test_std_candidate_core(sample_result):
    assert _by_key(sample_result[0])["goals_scored_std_last_10"]["recommendation"] == "candidate_core"
    assert sample_result[0]["stability_metric_comparison"]["preferred_stability_metric"] == "goals_scored_std_last_10"


def test_total_goals_avg_match_tempo_core(sample_result):
    pillars = sample_result[0]["pillar_recommendations"]["match_tempo"]["candidate_core"]
    assert "total_goals_avg" in pillars
    groups = _rolling_groups(sample_result[0])
    assert groups["match_tempo"]["selected_feature"] == "total_goals_avg"


def test_goals_conceded_defensive_reps_or_core(sample_result):
    defensive = sample_result[0]["pillar_recommendations"]["defensive_solidity"]
    assert defensive["candidate_core"], "difesa non deve restare senza core se idonea"
    assert any("goals_conceded_avg" in f for f in defensive["candidate_core"])


def test_clean_sheet_not_cluster_representative(sample_result):
    meta = sample_result[0]["redundancy_summary"]["cluster_meta"]
    for feature, info in meta.items():
        if "clean_sheet" in feature and info.get("representative_of_cluster"):
            group = info.get("redundant_with") or []
            assert not any("goals_conceded_avg" in g for g in group)


def test_xg_remains_optional(sample_result):
    xg = sample_result[0]["xg_value_summary"]
    assert xg["xg_value_assessment"] == "neutral"
    assert xg["evidence_level"] == "low"
    for feature in XG_FEATURE_KEYS:
        assert _by_key(sample_result[0])[feature]["recommendation"] == "candidate_optional_xg"


def test_readiness_false_with_contradictions():
    rows = [_row(i) for i in range(12)]
    for row in rows:
        row["xg_status"] = "missing"
        for key in XG_FEATURE_KEYS:
            row[key] = None
    result, _ = _run(rows)
    readiness = result["phase_1d_readiness"]
    assert readiness["xg_univariate_analysis_complete"] is False
    assert readiness["recommended_next_step"] == "complete_phase_1c_analysis"


def test_readiness_true_when_coherent(sample_result):
    readiness = sample_result[0]["phase_1d_readiness"]
    for key in (
        "rolling_selection_consistent",
        "recommendation_consistency_verified",
        "dependency_consistency_verified",
        "pillar_recommendations_consistent",
        "stability_recommendations_consistent",
        "rolling_window_decision_available",
        "target_specific_analysis_complete",
        "xg_univariate_analysis_complete",
    ):
        assert readiness[key] is True, key
    assert readiness["recommended_next_step"] == "phase_1d_candidate_indices"
    assert readiness["blocking_issues"] == []


def test_metrics_signal_still_present(sample_result):
    signal = sample_result[0]["_feature_signal"][0]
    assert set(signal["targets"]) == set(ALL_TARGETS)
    tg = signal["targets"]["total_goals_ft"]
    assert tg["spearman"] is not None and tg["pearson"] is not None
    assert signal["targets"]["goals_ge_2"]["auc"] is not None
    assert signal["targets"]["goals_ge_3"]["auc"] is not None
    assert signal["targets"]["btts_ft"]["auc"] is not None


def test_v4_invariata_e_no_formula(sample_result):
    source = Path(inspect.getsourcefile(build_goal_intensity_v5_statistics_internal) or "").read_text(encoding="utf-8")
    assert "eligibility_validator" not in source
    assert sample_result[0]["performance"]["no_v5_formula"] is True
    assert all(target not in CORE_FEATURES for target in ALL_TARGETS)


def test_total_goals_and_binary_metrics(sample_result):
    signal = sample_result[0]["_feature_signal"][0]
    assert "spearman_bootstrap" in signal["targets"]["total_goals_ft"]
    assert "auc_bootstrap" in signal["targets"]["goals_ge_2"]
    assert set(sample_result[0]["feature_recommendations"][0]["target_specific_strengths"]) == set(ALL_TARGETS)


def test_bootstrap_deterministic(sample_result):
    rows = sample_result[2]
    first, _ = _run(rows, seed=42)
    second, _ = _run(rows, seed=42)
    assert first["_feature_signal"] == second["_feature_signal"]


def test_spearman_and_auc_ci_helpers():
    xs = list(range(20))
    ys = [x * 0.5 + (i % 3) for i, x in enumerate(xs)]
    idx = bootstrap_index_matrix(len(xs), 50, 42)
    out = bootstrap_spearman_ci(xs, ys, iterations=50, seed=42, indices=idx)
    assert out["ci_lower"] <= out["ci_upper"]
    y = np.asarray([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 0], dtype=float)
    x = np.asarray([0.1, 0.9, 0.2, 0.8, 0.15, 0.85, 0.3, 0.7, 0.25, 0.75, 0.95, 0.05])
    auc = bootstrap_auc_ci(y, x, bootstrap_index_matrix(len(x), 40, 7))
    assert auc["auc"] is not None


def test_stability_insufficient_evidence_unit():
    fake_signals = [
        {
            "feature": f,
            "distribution": {"n_unique": 2},
            "targets": {"total_goals_ft": {"spearman": -0.1}},
        }
        for f in (
            "goals_scored_std_last_10",
            "goals_scored_mad_last_10",
            "goals_scored_cv_last_10",
            "goals_rolling_5_vs_10_delta",
        )
    ]
    temporal = {"features": {s["feature"]: {"direction_consistent": False} for s in fake_signals}}
    out = _stability_decision(fake_signals, temporal)
    assert out["preferred_stability_metric"] is None
    assert out["recommendation"] == "insufficient_evidence"


def test_dependency_map_unit_aggregate_and_sum():
    n = 10
    home5 = np.arange(n, dtype=float)
    away5 = np.arange(n, dtype=float) * 0.5
    arrays = {
        "home_goals_scored_rolling_5": home5,
        "away_goals_scored_rolling_5": away5,
        "pair_goals_scored_rolling_5": 0.5 * (home5 + away5),
        "over_2_5_frequency_last_10": np.ones(n),
        "goals_ge_3_frequency_last_10": np.ones(n),
        "pair_goals_scored_rolling_10": 0.5 * home5,
        "home_goals_scored_rolling_10": home5,
        "away_goals_scored_rolling_10": np.zeros(n),
        "goals_rolling_5_vs_10_delta": 0.5 * (home5 + away5) - 0.5 * home5,
    }
    deps = _dependency_map(arrays)
    assert deps["goals_ge_3_frequency_last_10"]["dependency_type"] == "exact_duplicate"
    assert deps["pair_goals_scored_rolling_5"]["dependency_type"] == "derived_aggregate"


def test_singular_vif_and_helpers():
    out = vif_scores({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [2.0, 4.0, 6.0, 8.0, 10.0],
        "c": [1.0, 1.0, 2.0, 2.0, 3.0],
    })
    assert out["status"] == "singular_design"
    assert CecchinoGoalIntensityV5StatisticsBody(
        date_from=date(2026, 6, 19), date_to=date(2026, 6, 19)
    ).date_from == date(2026, 6, 19)
    with pytest.raises(ValidationError):
        CecchinoGoalIntensityV5StatisticsBody(date_from=date(2026, 6, 18), date_to=date(2026, 6, 18))
    assert classify_psi(None) == "insufficient_sample"
    assert direction_consistent([1, -1]) is False
    assert ks_statistic([1.0, 2.0], [1.0, 3.0]) == 0.5
    assert population_stability_index([1.0] * 5, [1.0] * 5) is None
    assert correlation_matrix({"a": [1.0, None, 3.0], "b": [1.0, 2.0, None]})["matrix"]["a"]["b"] is None


def test_fail_closed_ineligible():
    rows = [_row(i) for i in range(20)] + [_row(99, eligible=False)]
    bad, _ = _run(rows)
    assert bad["status"] == "error"
    assert bad["error"] == "ineligible_match_entered_statistics_dataset"


def test_exports_rolling_and_recommendations(sample_result):
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_statistics."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source(sample_result[2]),
    ):
        for kind in ("rolling_comparison", "stability_metrics", "feature_recommendations", "redundancy_clusters"):
            chunks = list(stream_goal_intensity_v5_statistics_export(
                db, kind=kind, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19),
                bootstrap_iterations=20,
            ))
            body = "".join(chunks).lstrip("\ufeff")
            header = next(csv.reader(io.StringIO(body)))
            if kind == "rolling_comparison":
                assert "recommendation" in header and "excluded_redundant_features" in header
            if kind == "stability_metrics":
                assert "preferred_stability_metric" in header
            if kind == "feature_recommendations":
                assert "target_specific_strengths" in header
            assert statistics_export_filename(
                kind=kind, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19)
            ).endswith(".csv")


def test_payload_compatto(sample_result):
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_statistics."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source(sample_result[2]),
    ):
        compact = build_goal_intensity_v5_statistics(
            db, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19), bootstrap_iterations=20,
        )
    assert all(not str(k).startswith("_") for k in compact)
    assert compact["performance"]["response_payload_bytes"] < 2_000_000


def test_performance_diagnostics(sample_result):
    perf = sample_result[0]["performance"]
    for key in (
        "dataset_internal_ms", "descriptive_ms", "univariate_ms", "bootstrap_ms",
        "redundancy_ms", "temporal_ms", "xg_models_ms", "recommendation_ms",
        "serialization_ms", "elapsed_ms",
    ):
        assert key in perf


def test_away_rolling_insufficient_when_unstable(sample_result):
    away = _rolling_groups(sample_result[0])["away_attack"]
    assert away["recommendation"] == "insufficient_evidence"
    assert away["selected_feature"] is None
