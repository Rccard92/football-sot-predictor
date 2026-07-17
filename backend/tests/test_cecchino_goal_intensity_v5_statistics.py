"""Test Fase 1C: statistiche esplorative Intensità Goal v5."""

from __future__ import annotations

import csv
import inspect
import io
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.cecchino_goal_intensity_v5_research import CecchinoGoalIntensityV5StatisticsBody
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_dataset import XG_FEATURE_KEYS
from app.services.cecchino.cecchino_goal_intensity_v5_statistics import (
    ALL_TARGETS,
    CORE_FEATURES,
    VERSION,
    build_goal_intensity_v5_statistics_internal,
    statistics_export_filename,
    stream_goal_intensity_v5_statistics_export,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import (
    classify_psi,
    correlation_matrix,
    direction_consistent,
    ks_statistic,
    population_stability_index,
    vif_scores,
)


def _row(index: int, *, eligible: bool = True, sample_size: int = 12) -> dict:
    """Riga sintetica feature-safe con segnali, xG e fold temporale."""
    kickoff = datetime(2026, 6, 19, tzinfo=timezone.utc) + timedelta(days=index)
    goals = index % 5
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
        "temporal_fold_candidate": "train" if index < 24 else "test",
    }
    for feature_index, feature in enumerate(CORE_FEATURES):
        # Una feature costante verifica low-variance; le altre restano numeriche.
        row[feature] = 1.0 if feature == "home_clean_sheet_freq" else round(
            goals + feature_index * 0.03 + index * 0.01, 5
        )
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
        "identity_excluded": [],
    }


def _run(rows: list[dict], *, minimum_history_sample: int = 10, seed: int = 42) -> tuple[dict, MagicMock]:
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
            bootstrap_iterations=20,
            random_seed=seed,
        )
    return result, db


def test_statistics_contract_signals_bootstrap_and_readiness():
    rows = [_row(i) for i in range(40)]
    result, db = _run(rows)

    assert VERSION == "cecchino_goal_intensity_v5_statistics_v1"
    assert result["v4_version"] == V4_VERSION
    assert result["research_limitations"]["eligibility_engine_version"] == "legacy_pre_utc_fix"
    assert result["cohort_summary"]["core_min10"] == 40
    assert result["cohort_summary"]["core_min20"] == 0
    assert result["cohort_summary"]["ineligible_in_model"] == 0
    assert result["performance"]["v4_unchanged"] is True
    assert result["performance"]["no_v5_formula"] is True

    signal = result["_feature_signal"][0]
    continuous = signal["targets"]["total_goals_ft"]
    binary = signal["targets"]["goals_ge_2"]
    assert set(ALL_TARGETS) == set(signal["targets"])
    assert continuous["pearson_bootstrap"]["valid_bootstrap_iterations"] >= 10
    assert continuous["spearman_bootstrap"]["valid_bootstrap_iterations"] >= 10
    assert continuous["quintiles"]["monotonicity"]["monotonic_direction"] in {
        "increasing", "decreasing", "non_monotonic", "flat",
    }
    assert binary["point_biserial"] is not None
    assert binary["auc"] is not None
    assert binary["auc_bootstrap"]["valid_bootstrap_iterations"] >= 10
    low_variance = next(
        item for item in result["feature_signal_summary"]
        if item["feature_key"] == "home_clean_sheet_freq"
    )
    assert low_variance["low_variance"] is True
    low_variance_raw = next(
        item for item in result["_feature_signal"]
        if item["feature"] == "home_clean_sheet_freq"
    )
    assert low_variance_raw["distribution"]["n_unique"] == 1

    assert set(result["redundancy_summary"]["clusters"]) == {"0.8", "0.85", "0.9"}
    assert result["redundancy_summary"]["vif"]["status"] in {"ok", "failed", "insufficient_variance"}
    assert result["temporal_stability_summary"]["psi_thresholds"] == {
        "stable_lt": 0.10, "moderate_le": 0.25,
    }
    assert result["xg_value_summary"]["xg_value_assessment"] in {
        "positive", "neutral", "inconclusive",
    }
    assert result["xg_value_summary"]["evidence_level"] == "low"
    assert result["phase_1d_readiness"]["blocking_issues"] == ["core_sample_too_small"]
    assert "legacy_pre_utc_fix" not in result["phase_1d_readiness"]["blocking_issues"]
    assert all(
        item["recommendation"] in {
            "candidate_core", "candidate_secondary", "insufficient_evidence",
            "unstable_candidate", "redundant_candidate", "candidate_optional_xg",
        }
        for item in result["feature_recommendations"]
    )
    assert all(target not in CORE_FEATURES for target in ALL_TARGETS)
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_statistics_is_deterministic_min20_and_fail_closed():
    rows = [_row(i, sample_size=20 if i < 25 else 12) for i in range(40)]
    first, _ = _run(rows, minimum_history_sample=20, seed=42)
    second, _ = _run(rows, minimum_history_sample=20, seed=42)
    assert first["_feature_signal"] == second["_feature_signal"]
    assert first["cohort_summary"]["primary_analyzed"] == 25

    bad, _ = _run(rows + [_row(99, eligible=False)])
    assert bad["status"] == "error"
    assert bad["error"] == "ineligible_match_entered_statistics_dataset"


def test_statistics_date_floor_helpers_and_none_safe_vif():
    assert CecchinoGoalIntensityV5StatisticsBody(
        date_from=date(2026, 6, 19), date_to=date(2026, 6, 19)
    ).date_from == date(2026, 6, 19)
    with pytest.raises(ValidationError):
        CecchinoGoalIntensityV5StatisticsBody(
            date_from=date(2026, 6, 18), date_to=date(2026, 6, 18)
        )

    matrix = correlation_matrix({"a": [1.0, None, 3.0], "b": [1.0, 2.0, None]})
    assert matrix["matrix"]["a"]["b"] is None
    assert vif_scores({"a": [1.0, None, 2.0, 3.0, 4.0], "b": [None] * 5})["status"] == "insufficient_features"
    assert vif_scores({"a": [1.0] * 5, "b": [2.0] * 5})["status"] == "insufficient_variance"
    assert classify_psi(None) == "insufficient_sample"
    assert population_stability_index([1.0] * 5, [1.0] * 5) is None
    assert ks_statistic([1.0, 2.0], [1.0, 3.0]) == 0.5
    assert direction_consistent([1, 1, 0]) is True
    assert direction_consistent([1, -1]) is False


def test_statistics_exports_payload_keys_and_no_validator_import():
    rows = [_row(i) for i in range(40)]
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_statistics."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source(rows),
    ):
        result = build_goal_intensity_v5_statistics_internal(
            db, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19),
            bootstrap_iterations=20,
        )
        for kind in (
            "feature_signal", "redundancy_matrix", "redundancy_clusters", "temporal_stability",
            "rolling_comparison", "stability_metrics", "xg_value", "feature_recommendations",
        ):
            chunks = list(stream_goal_intensity_v5_statistics_export(
                db, kind=kind, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19),
                bootstrap_iterations=20,
            ))
            assert statistics_export_filename(
                kind=kind, date_from=date(2026, 6, 19), date_to=date(2026, 7, 19)
            ).endswith(".csv")
            body = "".join(chunks).lstrip("\ufeff")
            if kind == "feature_signal":
                assert "feature_key" in next(csv.reader(io.StringIO(body)))

    expected = {
        "research_limitations", "cohort_summary", "feature_signal_summary", "redundancy_summary",
        "rolling_window_comparison", "stability_metric_comparison", "temporal_stability_summary",
        "xg_value_summary", "xg_availability_bias_report", "pillar_recommendations",
        "feature_recommendations", "phase_1d_readiness",
    }
    assert expected <= set(result)
    assert statistics_export_filename(
        kind="summary", date_from=date(2026, 6, 19), date_to=date(2026, 7, 19)
    ).endswith(".json")
    source = Path(inspect.getsourcefile(build_goal_intensity_v5_statistics_internal) or "").read_text(
        encoding="utf-8"
    )
    assert "eligibility_validator" not in source
