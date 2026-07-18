"""Test Fase 1D: indici candidati Intensità Goal v5 (candidate_indices_v1)."""

from __future__ import annotations

import csv
import hashlib
import inspect
import io
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from app.schemas.cecchino_goal_intensity_v5_research import (
    CecchinoGoalIntensityV5CandidateIndicesBody,
)
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    CANDIDATE_DEFINITIONS,
    COMPOSITE_IDS,
    EXPANDING_CANDIDATE_IDS,
    HARD_EXCLUDED_FEATURES,
    LOO_IDS,
    PILLAR_CANDIDATE_IDS,
    SCORE_FEATURES,
    VERSION,
    TrainEcdf,
    _calibrate_and_evaluate,
    _composite_scores,
    _fit_linear_calibration,
    _fit_logistic_calibration,
    _loo_composites,
    _paired_calibrated_comparison,
    _pareto_select,
    _pillar_scores_from_pct,
    _prospective_protocol,
    apply_ecdfs,
    build_goal_intensity_v5_candidate_indices,
    build_goal_intensity_v5_candidate_indices_internal,
    candidate_indices_export_filename,
    fit_train_ecdfs,
    stream_goal_intensity_v5_candidate_indices_export,
)
from app.services.cecchino.cecchino_goal_intensity_v5_dataset import XG_FEATURE_KEYS


def _row(index: int, *, eligible: bool = True, sample_size: int = 12, fold: str | None = None) -> dict:
    kickoff = datetime(2026, 6, 19, tzinfo=timezone.utc) + timedelta(hours=index * 6)
    goals = 1 + (index // 5) % 4
    if fold is None:
        fold = "train" if index < 28 else ("validation" if index < 36 else "test")
    row = {
        "today_fixture_id": index + 1000,
        "local_fixture_id": index + 1,
        "provider_fixture_id": f"p{index + 1}",
        "scan_date": "2026-06-19",
        "kickoff": kickoff.isoformat(),
        "competition_id": 1,
        "home_team_id": 10 + (index % 7),
        "away_team_id": 20 + (index % 9),
        "eligibility_status": "eligible" if eligible else "ineligible",
        "row_feature_safe": True,
        "core_feature_status": "available",
        "sample_size": sample_size,
        "total_goals_ft": goals,
        "goals_ge_2": int(goals >= 2),
        "goals_ge_3": int(goals >= 3),
        "btts_ft": int(index % 2),
        "xg_status": "available",
        "temporal_fold_candidate": fold,
        "home_goals_scored_avg": round(0.4 + goals * 0.55 + index * 0.01, 5),
        "home_goals_scored_rolling_5": round(0.45 + goals * 0.5 + index * 0.008, 5),
        "away_goals_scored_avg": round(0.35 + goals * 0.48, 5),
        "away_goals_scored_rolling_5": round(0.38 + goals * 0.46, 5),
        "home_goals_conceded_avg": round(0.6 + goals * 0.35, 5),
        "away_goals_conceded_avg": round(0.55 + goals * 0.32, 5),
        "total_goals_avg": round(0.5 + goals * 0.7, 5),
        "total_goals_rolling_5": round(0.55 + goals * 0.65, 5),
        "goals_scored_std_last_10": round(0.4 + goals * 0.2 + index * 0.015, 5),
        "goals_scored_mad_last_10": 0.1 * (index % 5),
        "goals_scored_cv_last_10": -0.1,
        "goals_rolling_5_vs_10_delta": 0.05,
        "goals_ge_3_frequency_last_10": 0.2,
        "pair_goals_scored_rolling_5": 1.0,
        "pair_goals_scored_rolling_10": 0.9,
    }
    for feature_index, feature in enumerate(XG_FEATURE_KEYS):
        row[feature] = round(0.5 + goals * 0.2 + feature_index * 0.03, 5)
    return row


def _source(rows: list[dict]) -> dict:
    return {
        "status": "ok",
        "dataset_rows": rows,
        "cohort_basis": "cecchino_today_eligible_scan_date",
        "fixture_ids_hash": "a" * 64,
        "targets_hash": "b" * 64,
    }


def _run(rows: list[dict], *, minimum_history_sample: int = 10, seed: int = 42, iterations: int = 40) -> tuple[dict, MagicMock]:
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source(rows),
    ):
        result = build_goal_intensity_v5_candidate_indices_internal(
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


def test_version_constant():
    assert VERSION == "cecchino_goal_intensity_v5_candidate_indices_v1_1"


def test_version_and_v4_unchanged(sample_result):
    result, db, _ = sample_result
    assert result["version"] == VERSION
    assert result["v4_version"] == V4_VERSION
    assert result["performance"]["v4_unchanged"] is True
    assert result["performance"]["no_v5_productive_formula"] is True
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_status_ok(sample_result):
    assert sample_result[0]["status"] == "ok"


def test_hard_exclusions_not_in_score_features():
    assert HARD_EXCLUDED_FEATURES.isdisjoint(SCORE_FEATURES)


def test_hard_exclusions_documented(sample_result):
    excluded = set(sample_result[0]["normalization_summary"]["hard_excluded_features"])
    assert HARD_EXCLUDED_FEATURES <= excluded


def test_ecdf_midrank_formula():
    ecdf = TrainEcdf([1.0, 2.0, 2.0, 3.0])
    expected = 100.0 * (1 + 0.5 * 2) / 4
    assert abs(ecdf.transform(2.0) - expected) < 1e-9


def test_ecdf_tie_midrank():
    ecdf = TrainEcdf([5.0, 5.0, 5.0])
    assert abs(ecdf.transform(5.0) - 50.0) < 1e-9


def test_ecdf_clamp_low():
    ecdf = TrainEcdf([2.0, 3.0, 4.0])
    assert ecdf.transform(0.0) == ecdf.transform(2.0)
    assert ecdf.clipping_low_count >= 1


def test_ecdf_clamp_high():
    ecdf = TrainEcdf([2.0, 3.0, 4.0])
    assert ecdf.transform(99.0) == ecdf.transform(4.0)
    assert ecdf.clipping_high_count >= 1


def test_ecdf_none_and_nan():
    ecdf = TrainEcdf([1.0, 2.0])
    assert ecdf.transform(None) is None
    assert ecdf.transform(float("nan")) is None


def test_ecdf_empty_train():
    ecdf = TrainEcdf([])
    assert ecdf.transform(1.0) is None
    assert ecdf.n == 0


def test_ecdf_score_bounds():
    ecdf = TrainEcdf(list(range(20)))
    for x in (-10, 0, 5, 19, 100):
        score = ecdf.transform(float(x))
        assert score is not None
        assert 0.0 <= score <= 100.0


def test_fit_train_only():
    rows = [
        {"temporal_fold_candidate": "train", "home_goals_scored_avg": 1.0},
        {"temporal_fold_candidate": "train", "home_goals_scored_avg": 2.0},
        {"temporal_fold_candidate": "test", "home_goals_scored_avg": 99.0},
    ]
    ecdfs = fit_train_ecdfs(rows, ("home_goals_scored_avg",))
    assert ecdfs["home_goals_scored_avg"].n == 2
    assert ecdfs["home_goals_scored_avg"].train_max == 2.0


def test_apply_ecdfs_uses_train_fit():
    rows = [
        {"temporal_fold_candidate": "train", "home_goals_scored_avg": float(i)}
        for i in range(10)
    ] + [{"temporal_fold_candidate": "test", "home_goals_scored_avg": 4.5}]
    ecdfs = fit_train_ecdfs(rows, ("home_goals_scored_avg",))
    scored = apply_ecdfs(rows[-1:], ecdfs)
    assert scored[0]["home_goals_scored_avg"] is not None
    assert 0 <= scored[0]["home_goals_scored_avg"] <= 100


def test_pillar_op1_formula():
    pillar = _pillar_scores_from_pct({"home_goals_scored_avg": 70.0})
    assert pillar["OP1_HOME_LONG_TERM"] == 70.0


def test_pillar_op2_mean():
    pillar = _pillar_scores_from_pct({
        "home_goals_scored_avg": 60.0,
        "home_goals_scored_rolling_5": 80.0,
    })
    assert pillar["OP2_HOME_RECENCY"] == 70.0


def test_pillar_dv1_mean():
    pillar = _pillar_scores_from_pct({
        "home_goals_conceded_avg": 40.0,
        "away_goals_conceded_avg": 60.0,
    })
    assert pillar["DV1_MEAN_CONCEDED"] == 50.0


def test_pillar_dv2_max():
    pillar = _pillar_scores_from_pct({
        "home_goals_conceded_avg": 40.0,
        "away_goals_conceded_avg": 60.0,
    })
    assert pillar["DV2_WEAKEST_DEFENCE"] == 60.0


def test_pillar_solidity_display_inverse():
    pillar = _pillar_scores_from_pct({
        "home_goals_conceded_avg": 30.0,
        "away_goals_conceded_avg": 50.0,
    })
    assert pillar["defensive_solidity_display"] == 60.0


def test_pillar_stability_display_inverse():
    pillar = _pillar_scores_from_pct({"goals_scored_std_last_10": 25.0})
    assert pillar["offensive_stability_display"] == 75.0


def test_gi_a_equal_weight():
    pillar = {
        "OP1_HOME_LONG_TERM": 10.0,
        "DV1_MEAN_CONCEDED": 20.0,
        "MT1_LONG_TERM": 30.0,
        "OV1_STD": 40.0,
    }
    assert _composite_scores(pillar)["GI_A_STRICT_CORE"] == 25.0


def test_gi_b_recency():
    pillar = {
        "OP2_HOME_RECENCY": 10.0,
        "DV1_MEAN_CONCEDED": 20.0,
        "MT2_LONG_TERM_PLUS_RECENCY": 30.0,
        "OV1_STD": 40.0,
    }
    assert _composite_scores(pillar)["GI_B_RECENCY"] == 25.0


def test_gi_c_diagnostic():
    pillar = {
        "OP3_SYMMETRIC_LONG_TERM_DIAGNOSTIC": 10.0,
        "DV1_MEAN_CONCEDED": 20.0,
        "MT1_LONG_TERM": 30.0,
        "OV1_STD": 40.0,
    }
    assert _composite_scores(pillar)["GI_C_SYMMETRIC_DIAGNOSTIC"] == 25.0


def test_gi_d_weakest():
    pillar = {
        "OP1_HOME_LONG_TERM": 10.0,
        "DV2_WEAKEST_DEFENCE": 20.0,
        "MT1_LONG_TERM": 30.0,
        "OV1_STD": 40.0,
    }
    assert _composite_scores(pillar)["GI_D_WEAKEST_DEFENCE"] == 25.0


def test_display_not_in_composite():
    pillar = _pillar_scores_from_pct({
        "home_goals_scored_avg": 50.0,
        "home_goals_conceded_avg": 40.0,
        "away_goals_conceded_avg": 60.0,
        "total_goals_avg": 55.0,
        "goals_scored_std_last_10": 45.0,
    })
    composite = _composite_scores(pillar)
    assert "defensive_solidity_display" not in composite
    assert "offensive_stability_display" not in composite


def test_loo_composites_keys():
    pillar = {
        "OP1_HOME_LONG_TERM": 10.0,
        "DV1_MEAN_CONCEDED": 20.0,
        "MT1_LONG_TERM": 30.0,
        "OV1_STD": 40.0,
    }
    loo = _loo_composites(pillar)
    assert set(loo) == {
        "without_production",
        "without_defence",
        "without_tempo",
        "without_volatility",
    }
    assert loo["without_production"] == pytest.approx(30.0)


def test_primary_default_gi_a(sample_result):
    assert sample_result[0]["primary_candidate"] == "GI_A_STRICT_CORE"


def test_challenger_present(sample_result):
    assert sample_result[0]["challenger_candidate"] in COMPOSITE_IDS
    assert sample_result[0]["challenger_candidate"] != "GI_A_STRICT_CORE"


def test_selection_evidence_low(sample_result):
    assert sample_result[0]["pareto_analysis"]["selection_evidence_level"] == "low"


def test_weight_status(sample_result):
    assert sample_result[0]["performance"]["weight_status"] == "equal_weight_research_baseline"
    assert CANDIDATE_DEFINITIONS["GI_A_STRICT_CORE"]["weight_status"] == "equal_weight_research_baseline"


def test_normalization_train_only(sample_result):
    norm = sample_result[0]["normalization_summary"]
    assert norm["method"] == "train_ecdf_midrank"
    assert norm["fit_split"] == "train"
    assert norm["no_target_used_in_normalization"] is True


def test_no_target_leakage_in_scores(sample_result):
    for row in sample_result[0]["_scored_rows"]:
        assert row["no_target_used_in_score"] is True
        for cid in COMPOSITE_IDS:
            assert 0 <= row[cid] <= 100


def test_scores_before_targets_in_export_order(sample_result):
    row = sample_result[0]["_scored_rows"][0]
    keys = list(row.keys())
    assert keys.index("GI_A_STRICT_CORE") < keys.index("total_goals_ft")
    assert keys.index("OP1_HOME_LONG_TERM") < keys.index("goals_ge_2")


def test_pillar_and_composite_metrics_present(sample_result):
    for cid in PILLAR_CANDIDATE_IDS:
        assert cid in sample_result[0]["pillar_metrics"]
    for cid in COMPOSITE_IDS:
        assert cid in sample_result[0]["composite_metrics"]


def test_ablation_complete(sample_result):
    ablation = sample_result[0]["ablation_summary"]
    assert "without_production" in ablation
    assert "without_defence" in ablation
    assert "without_tempo" in ablation
    assert "without_volatility" in ablation


def test_paired_comparisons(sample_result):
    paired = sample_result[0]["paired_candidate_comparisons"]
    assert "GI_B_RECENCY_vs_GI_A_STRICT_CORE" in paired
    assert "GI_A_STRICT_CORE_vs_MT1_LONG_TERM" in paired


def test_pillar_redundancy(sample_result):
    red = sample_result[0]["pillar_redundancy"]
    assert "pearson" in red
    assert "spearman" in red
    assert "correlation_with_MT1" in red


def test_xg_optional_not_promoted(sample_result):
    xg = sample_result[0]["xg_optional_analysis"]
    assert xg["xg_status"] == "optional_research_enrichment"
    assert xg.get("promoted_to_core") is False


def test_prospective_protocol_hash(sample_result):
    protocol = sample_result[0]["prospective_validation_protocol"]
    assert protocol["candidate_definition_hash"]
    assert protocol["no_retroactive_formula_changes"] is True
    assert protocol["validation_status"] == "retrospective_selection_informed"


def test_research_limitations(sample_result):
    lim = sample_result[0]["research_limitations"]
    assert lim["eligibility_engine_version"] == "legacy_pre_utc_fix"
    assert lim["validation_status"] == "retrospective_selection_informed"
    assert lim["no_productive_validation_claim"] is True


def test_phase_2a_readiness(sample_result):
    readiness = sample_result[0]["phase_2a_readiness"]
    assert readiness["primary_candidate_available"] is True
    assert readiness["xg_kept_optional"] is True
    assert "recommended_next_step" in readiness


def test_preview_rows_capped(sample_result):
    assert len(sample_result[0]["preview_rows"]) <= 100


def test_ineligible_rejected():
    rows = [_row(i, eligible=False) for i in range(10)]
    result, _ = _run(rows)
    assert result["status"] == "error"
    assert result["error"] == "ineligible_match_entered_candidate_indices_dataset"


def test_compact_strips_private_keys(sample_result):
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source([_row(i) for i in range(48)]),
    ):
        compact = build_goal_intensity_v5_candidate_indices(
            db,
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 19),
            bootstrap_iterations=20,
            random_seed=42,
        )
    assert "_scored_rows" not in compact
    assert "_ecdfs" not in compact
    assert compact["performance"]["response_payload_bytes"] > 0


def test_schema_rejects_bad_history():
    with pytest.raises(ValidationError):
        CecchinoGoalIntensityV5CandidateIndicesBody(
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 19),
            minimum_history_sample=15,
        )


def test_schema_accepts_10_20():
    body = CecchinoGoalIntensityV5CandidateIndicesBody(
        date_from=date(2026, 6, 19),
        date_to=date(2026, 7, 19),
        minimum_history_sample=20,
    )
    assert body.minimum_history_sample == 20


def test_export_filenames():
    name = candidate_indices_export_filename(
        kind="candidate_scores",
        date_from=date(2026, 6, 19),
        date_to=date(2026, 7, 19),
    )
    assert name.endswith(".csv")
    assert "candidate_scores" in name


def test_export_stream_candidate_scores():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source([_row(i) for i in range(48)]),
    ):
        chunks = list(
            stream_goal_intensity_v5_candidate_indices_export(
                db,
                kind="candidate_scores",
                date_from=date(2026, 6, 19),
                date_to=date(2026, 7, 19),
                bootstrap_iterations=20,
            )
        )
    text = "".join(chunks)
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = list(reader)
    assert rows
    assert "GI_A_STRICT_CORE" in rows[0]
    assert "total_goals_ft" in rows[0]
    keys = list(rows[0].keys())
    assert keys.index("GI_A_STRICT_CORE") < keys.index("total_goals_ft")


@pytest.mark.parametrize(
    "kind",
    [
        "summary",
        "candidate_definitions",
        "pillar_metrics",
        "composite_metrics",
        "temporal_metrics",
        "decile_calibration",
        "ablation_analysis",
        "paired_candidate_comparison",
        "pillar_redundancy",
        "xg_optional_enrichment",
        "prospective_validation_protocol",
    ],
)
def test_export_kinds_produce_output(kind):
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source([_row(i) for i in range(48)]),
    ):
        chunks = list(
            stream_goal_intensity_v5_candidate_indices_export(
                db,
                kind=kind,
                date_from=date(2026, 6, 19),
                date_to=date(2026, 7, 19),
                bootstrap_iterations=15,
            )
        )
    assert "".join(chunks)


def test_pareto_defaults_primary_a():
    metrics = {
        cid: {
            "total_goals_ft": {"spearman": 0.1, "mae": 1.5, "rmse": 1.8},
            "goals_ge_2": {"auc": 0.55, "brier": 0.2},
        }
        for cid in COMPOSITE_IDS
    }
    temporal = {cid: {"direction_consistent": True} for cid in COMPOSITE_IDS}
    expanding = {"candidates": {cid: {"direction_consistent": True} for cid in COMPOSITE_IDS}}
    paired = {
        "GI_B_RECENCY_vs_GI_A_STRICT_CORE": {
            "total_goals_ft": {"delta_mae_ci": {"mean": 0.01, "ci_lower": -0.05, "ci_upper": 0.07}}
        }
    }
    out = _pareto_select(metrics, temporal, expanding, paired)
    assert out["primary_candidate"] == "GI_A_STRICT_CORE"
    assert out["selection_evidence_level"] == "low"
    assert "nominal_pareto_front" in out
    assert "statistically_supported_pareto_front" in out
    assert out["uses_calibrated_metrics"] is True


def test_distribution_hash_stable():
    a = TrainEcdf([1.0, 2.0, 3.0])
    b = TrainEcdf([1.0, 2.0, 3.0])
    assert a.distribution_hash == b.distribution_hash


def test_candidate_definition_hash_deterministic():
    h1 = hashlib.sha256(json.dumps(CANDIDATE_DEFINITIONS, sort_keys=True, default=str).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(CANDIDATE_DEFINITIONS, sort_keys=True, default=str).encode()).hexdigest()
    assert h1 == h2


def test_service_does_not_import_write_helpers():
    source = Path(
        inspect.getfile(
            __import__(
                "app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices",
                fromlist=["*"],
            )
        )
    ).read_text(encoding="utf-8")
    assert "db.add" not in source
    assert "db.commit" not in source
    assert "alembic" not in source.lower()


def test_core_min20_path(sample_result):
    assert "core_min20" in sample_result[0]["temporal_metrics"]


def test_month_diagnostic(sample_result):
    month = sample_result[0]["temporal_metrics"]["month_diagnostic"]
    assert "june" in month
    assert "july" in month
    assert month["june"]["status"] == "diagnostic_only"

def test_baseline_metrics(sample_result):
    baseline = sample_result[0]["baseline_metrics"]
    assert "MT1_LONG_TERM" in baseline
    assert "OP1_HOME_LONG_TERM" in baseline


def test_statistics_module_untouched():
    """Regressione: statistics v1_2 non deve essere alterata da 1D."""
    from app.services.cecchino.cecchino_goal_intensity_v5_statistics import VERSION as STATS_VERSION

    assert STATS_VERSION == "cecchino_goal_intensity_v5_statistics_v1_2"


def test_routes_register_candidate_indices():
    routes_path = Path(__file__).resolve().parents[1] / "app" / "routes" / "cecchino_research.py"
    source = routes_path.read_text(encoding="utf-8")
    assert "/goal-intensity-v5/candidate-indices" in source
    assert "candidate-indices/export/summary" in source
    assert "candidate-indices/export/prospective-validation-protocol" in source


def test_expanding_or_insufficient(sample_result):
    expanding = sample_result[0]["temporal_metrics"]["expanding"]
    assert expanding["status"] in {"ok", "insufficient_sample_for_3_temporal_folds"}


def test_ecdf_metadata_fields():
    ecdf = TrainEcdf([1.0, 2.0, 2.0, 4.0, 5.0])
    meta = ecdf.metadata()
    assert meta["normalization_method"] == "train_ecdf_midrank"
    assert meta["train_n"] == 5
    assert "quantiles" in meta
    assert meta["ties_count"] >= 1


def test_op3_symmetric():
    pillar = _pillar_scores_from_pct({
        "home_goals_scored_avg": 40.0,
        "away_goals_scored_avg": 60.0,
    })
    assert pillar["OP3_SYMMETRIC_LONG_TERM_DIAGNOSTIC"] == 50.0


def test_mt2_formula():
    pillar = _pillar_scores_from_pct({
        "total_goals_avg": 40.0,
        "total_goals_rolling_5": 60.0,
    })
    assert pillar["MT2_LONG_TERM_PLUS_RECENCY"] == 50.0


# --- Fase 1D.1: calibrazione / paired / expanding / readiness ---


def test_v11_binary_prob_not_score_over_100(sample_result):
    ge2 = sample_result[0]["composite_metrics"]["GI_A_STRICT_CORE"]["goals_ge_2"]
    assert ge2["uses_score_over_100_as_probability"] is False
    assert ge2["calibration_method"] == "train_logistic_regression"
    scores = [
        r["GI_A_STRICT_CORE"]
        for r in sample_result[0]["_scored_rows"]
        if r.get("GI_A_STRICT_CORE") is not None
    ]
    y = [
        r["goals_ge_2"]
        for r in sample_result[0]["_scored_rows"]
        if r.get("GI_A_STRICT_CORE") is not None
    ]
    naive = float(
        np.mean((np.clip(np.asarray(scores) / 100.0, 1e-6, 1 - 1e-6) - np.asarray(y)) ** 2)
    )
    assert ge2["brier"] is not None
    assert abs(float(ge2["brier"]) - naive) > 1e-9


def test_v11_logistic_fit_train_only():
    scores = [float(i) for i in range(20)]
    targets = [0.0] * 10 + [1.0] * 10
    cal = _fit_logistic_calibration(scores[:14], targets[:14])
    assert cal is not None
    assert cal["calibration_method"] == "train_logistic_regression"
    assert cal["train_n"] == 14


def test_v11_validation_not_in_logistic_fit(sample_result):
    ge2 = sample_result[0]["composite_metrics"]["GI_A_STRICT_CORE"]["goals_ge_2"]
    train_n = sum(1 for r in sample_result[0]["_scored_rows"] if r["split"] == "train")
    assert ge2["train_n"] <= train_n


def test_v11_test_not_in_logistic_fit(sample_result):
    ge2 = sample_result[0]["composite_metrics"]["GI_A_STRICT_CORE"]["goals_ge_2"]
    assert ge2["train_n"] is not None
    total = len(sample_result[0]["_scored_rows"])
    assert ge2["train_n"] < total


def test_v11_linear_calibration_train_only(sample_result):
    tg = sample_result[0]["composite_metrics"]["GI_A_STRICT_CORE"]["total_goals_ft"]
    assert tg["calibration_method"] == "train_linear_regression"
    assert tg["intercept"] is not None
    assert tg["coefficient"] is not None
    assert tg["mae"] is not None
    assert tg["rmse"] is not None


def test_v11_paired_mae_same_cohort(sample_result):
    paired = sample_result[0]["paired_candidate_comparisons"]["GI_B_RECENCY_vs_GI_A_STRICT_CORE"]
    assert paired["dimensionally_valid"] is True
    assert paired["uses_raw_score_vs_goals"] is False
    assert paired["total_goals_ft"]["n_paired"] > 0
    assert "delta_mae" in paired["total_goals_ft"]


def test_v11_paired_rmse_same_cohort(sample_result):
    paired = sample_result[0]["paired_candidate_comparisons"]["GI_B_RECENCY_vs_GI_A_STRICT_CORE"]
    assert "delta_rmse" in paired["total_goals_ft"]


def test_v11_delta_error_negative_favors_left(sample_result):
    paired = sample_result[0]["paired_candidate_comparisons"]["GI_B_RECENCY_vs_GI_A_STRICT_CORE"]
    assert paired["direction_notes"]["delta_mae"] == "delta<0 favorisce left"


def test_v11_delta_auc_positive_favors_left(sample_result):
    paired = sample_result[0]["paired_candidate_comparisons"]["GI_B_RECENCY_vs_GI_A_STRICT_CORE"]
    assert paired["direction_notes"]["delta_auc"] == "delta>0 favorisce left"


def test_v11_delta_brier_negative_favors_left(sample_result):
    paired = sample_result[0]["paired_candidate_comparisons"]["GI_B_RECENCY_vs_GI_A_STRICT_CORE"]
    assert paired["direction_notes"]["delta_brier"] == "delta<0 favorisce left"


def test_v11_paired_bootstrap_deterministic(sample_result):
    a = sample_result[0]["paired_candidate_comparisons"]["GI_A_STRICT_CORE_vs_MT1_LONG_TERM"]
    result2, _ = _run([_row(i) for i in range(48)], iterations=40, seed=42)
    b = result2["paired_candidate_comparisons"]["GI_A_STRICT_CORE_vs_MT1_LONG_TERM"]
    assert a["total_goals_ft"]["delta_mae"] == b["total_goals_ft"]["delta_mae"]


def test_v11_no_raw_score_vs_total_goals(sample_result):
    for comp in sample_result[0]["paired_candidate_comparisons"].values():
        assert comp.get("uses_raw_score_vs_goals") is False


def test_v11_ablation_calibrated(sample_result):
    for label in ("without_production", "without_defence", "without_tempo", "without_volatility"):
        ab = sample_result[0]["ablation_summary"][label]
        assert ab["calibrated"] is True
        assert ab["uses_raw_score_vs_goals"] is False
        assert "pillar_incremental_assessment" in ab
        assert ab["evidence_level"] in {"low", "moderate", "strong"}


def test_v11_ablation_production(sample_result):
    assert sample_result[0]["ablation_summary"]["without_production"]["loo_key"] == "GI_A_without_production"


def test_v11_ablation_defence(sample_result):
    assert sample_result[0]["ablation_summary"]["without_defence"]["loo_key"] == "GI_A_without_defence"


def test_v11_ablation_tempo(sample_result):
    assert sample_result[0]["ablation_summary"]["without_tempo"]["loo_key"] == "GI_A_without_tempo"


def test_v11_ablation_volatility(sample_result):
    assert sample_result[0]["ablation_summary"]["without_volatility"]["loo_key"] == "GI_A_without_volatility"


@pytest.mark.parametrize(
    "cid",
    [
        "GI_A_STRICT_CORE",
        "GI_B_RECENCY",
        "GI_C_SYMMETRIC_DIAGNOSTIC",
        "GI_D_WEAKEST_DEFENCE",
        "MT1_LONG_TERM",
    ],
)
def test_v11_expanding_candidate(sample_result, cid):
    expanding = sample_result[0]["temporal_metrics"]["expanding"]
    if expanding["status"] != "ok":
        pytest.skip("insufficient folds on synthetic sample")
    assert cid in expanding["candidates"]


def test_v11_expanding_all_targets(sample_result):
    expanding = sample_result[0]["temporal_metrics"]["expanding"]
    if expanding["status"] != "ok":
        pytest.skip("insufficient folds")
    assert expanding["all_targets_present"] is True
    cand = expanding["candidates"]["GI_A_STRICT_CORE"]
    assert "auc_goals_ge_2" in cand
    assert "auc_goals_ge_3" in cand
    assert "auc_btts_ft" in cand


def test_v11_expanding_ecdf_refit_flag(sample_result):
    expanding = sample_result[0]["temporal_metrics"]["expanding"]
    if expanding["status"] == "ok":
        assert expanding["ecdf_refit_per_fold"] is True


def test_v11_expanding_calibration_refit_flag(sample_result):
    expanding = sample_result[0]["temporal_metrics"]["expanding"]
    if expanding["status"] == "ok":
        assert expanding["calibration_refit_per_fold"] is True


def test_v11_rank_stability(sample_result):
    expanding = sample_result[0]["temporal_metrics"]["expanding"]
    if expanding["status"] != "ok":
        pytest.skip("insufficient folds")
    for cid in COMPOSITE_IDS:
        rs = expanding["candidates"][cid]["rank_stability"]
        assert "mean_rank" in rs
        assert "ranks" in rs


def test_v11_pareto_calibrated_metrics(sample_result):
    pareto = sample_result[0]["pareto_analysis"]
    assert pareto["uses_calibrated_metrics"] is True
    assert "nominal_pareto_front" in pareto
    assert "statistically_supported_pareto_front" in pareto


def test_v11_mt1_comparison(sample_result):
    tempo = sample_result[0]["tempo_baseline_comparison"]
    assert tempo["composite_value_over_tempo"] in {"positive", "neutral", "negative", "inconclusive"}
    assert "GI_A_vs_MT1" in tempo
    assert "GI_B_vs_MT1" in tempo
    assert "GI_B_RECENCY_vs_MT1_LONG_TERM" in sample_result[0]["paired_candidate_comparisons"]


def test_v11_prospective_start_after_dataset_end():
    protocol = _prospective_protocol(date_to=date(2026, 7, 19))
    assert protocol["first_prospective_scan_date"] == "2026-07-20"
    assert protocol["dataset_end_date"] == "2026-07-19"
    assert protocol["first_prospective_scan_date"] > protocol["dataset_end_date"]


def test_v11_prospective_start_after_freeze():
    protocol = _prospective_protocol(date_to=date(2026, 7, 19))
    assert protocol["protocol_status"] == "waiting_for_prospective_data"
    assert protocol["prospective_matches_collected"] == 0
    assert protocol["prospective_window_started_at"] > protocol["candidate_definition_frozen_at"]


def test_v11_readiness_false_when_temporal_incomplete():
    rows = [_row(i) for i in range(12)]
    result, _ = _run(rows, iterations=20)
    readiness = result["phase_2a_readiness"]
    assert readiness["temporal_validation_complete"] is False
    assert readiness["recommended_next_step"] == "complete_phase_1d_evaluation"
    assert readiness["ready_for_phase_2a"] is False


def test_v11_readiness_true_only_all_gates(sample_result):
    readiness = sample_result[0]["phase_2a_readiness"]
    if readiness.get("ready_for_phase_2a"):
        assert readiness["blocking_issues"] == []
        assert readiness["recommended_next_step"] == "phase_2a_preview"
        for key in (
            "binary_calibration_verified",
            "paired_comparison_dimensionally_valid",
            "ablation_calibrated",
            "prospective_start_strictly_after_freeze",
        ):
            assert readiness[key] is True
    else:
        assert readiness["recommended_next_step"] == "complete_phase_1d_evaluation"


def test_v11_candidate_scores_unchanged_structure(sample_result):
    row = sample_result[0]["_scored_rows"][0]
    for cid in COMPOSITE_IDS:
        assert 0 <= row[cid] <= 100
    assert row["no_target_used_in_score"] is True


def test_v11_hash_preserved(sample_result):
    assert sample_result[0]["cohort_summary"]["fixture_ids_hash"] == "a" * 64
    assert sample_result[0]["cohort_summary"]["targets_hash"] == "b" * 64


def test_v11_v4_unchanged(sample_result):
    assert sample_result[0]["v4_version"] == V4_VERSION
    assert sample_result[0]["performance"]["v4_unchanged"] is True


def test_v11_export_calibrated_predictions():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source([_row(i) for i in range(48)]),
    ):
        chunks = list(
            stream_goal_intensity_v5_candidate_indices_export(
                db,
                kind="calibrated_predictions",
                date_from=date(2026, 6, 19),
                date_to=date(2026, 7, 19),
                bootstrap_iterations=20,
            )
        )
    text = "".join(chunks)
    assert "calibrated_prediction" in text or "raw_score" in text


def test_v11_export_temporal_fold_metrics():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices."
        "build_goal_intensity_v5_dataset_internal",
        return_value=_source([_row(i) for i in range(48)]),
    ):
        chunks = list(
            stream_goal_intensity_v5_candidate_indices_export(
                db,
                kind="temporal_fold_metrics",
                date_from=date(2026, 6, 19),
                date_to=date(2026, 7, 19),
                bootstrap_iterations=20,
            )
        )
    assert "".join(chunks)


def test_v11_expanding_loo_candidates(sample_result):
    expanding = sample_result[0]["temporal_metrics"]["expanding"]
    if expanding["status"] != "ok":
        pytest.skip("insufficient folds")
    for loo in LOO_IDS:
        assert loo in expanding["candidates"]


def test_v11_gi_b_vs_mt1_present(sample_result):
    assert "GI_B_RECENCY_vs_MT1_LONG_TERM" in sample_result[0]["paired_candidate_comparisons"]


def test_v11_linear_fit_helper():
    cal = _fit_linear_calibration([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0])
    assert cal is not None
    preds = cal["_predict"]([5.0])
    assert abs(float(preds[0]) - 10.0) < 0.1


def test_v11_calibrate_and_evaluate_no_score100():
    rows = [_row(i) for i in range(40)]
    ecdfs = fit_train_ecdfs(rows, SCORE_FEATURES)
    from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import _score_rows

    scored = _score_rows(rows, ecdfs)
    metrics, preds = _calibrate_and_evaluate(
        scored,
        "GI_A_STRICT_CORE",
        bootstrap_iterations=20,
        random_seed=42,
        bootstrap_cache={},
        collect_predictions=True,
    )
    assert metrics["goals_ge_2"]["uses_score_over_100_as_probability"] is False
    assert any(p["target"] == "goals_ge_2" and p["probability"] is not None for p in preds)


def test_v11_routes_new_exports():
    routes_path = Path(__file__).resolve().parents[1] / "app" / "routes" / "cecchino_research.py"
    source = routes_path.read_text(encoding="utf-8")
    assert "calibrated-predictions" in source
    assert "temporal-fold-metrics" in source


def test_v11_expanding_candidate_ids_complete():
    assert "GI_A_STRICT_CORE" in EXPANDING_CANDIDATE_IDS
    assert "MT1_LONG_TERM" in EXPANDING_CANDIDATE_IDS
    for loo in LOO_IDS:
        assert loo in EXPANDING_CANDIDATE_IDS
