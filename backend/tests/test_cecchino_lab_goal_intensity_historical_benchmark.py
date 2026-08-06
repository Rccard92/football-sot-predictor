"""Test job benchmark storico Goal Intensity V4 vs V5."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models.cecchino_goal_intensity_v5_preview import (
    BUNDLE_STATUS_ACTIVE,
    BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
)
from app.models.cecchino_lab_goal_intensity_benchmark_job import (
    CONFIRM_FULL,
    CONFIRM_PILOT,
    JOB_VERSION,
    MODE_FULL,
    MODE_PILOT,
    REQUIRED_BUNDLE_VERSION,
    STATUS_COMPLETED,
    STATUS_QUEUED,
)
from app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark import V4_MODEL_ID
from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import (
    ACTIVE_CANDIDATE_IDS,
    ARCHIVED_CANDIDATE_IDS,
    DEVELOPMENT_PROTOCOL_VERSION,
    GI_E_ID,
    GI_F_ID,
    GI_F_PILLARS,
    TARGET_BUNDLE_VERSION,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    CHALLENGER_ID,
    PRIMARY_ID,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_independence import (
    INDEPENDENCE_EXTERNAL,
    INDEPENDENCE_FULL,
    INDEPENDENCE_PARTIAL,
    INDEPENDENCE_UNKNOWN,
    assess_independence,
)
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_metrics import (
    evaluate_paired_rows,
)
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_scoring import (
    extract_ft_target,
    extract_v4_from_historical_snapshot,
    extract_v5_features_from_snapshot,
    get_frozen_goal_intensity_candidate_bundle,
    score_five_models_with_frozen_bundle,
    validate_frozen_candidate_bundle,
)
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_selection import (
    select_pilot_snapshots,
)
from app.services.cecchino_data_lab import goal_intensity_historical_benchmark_service as svc


def _cal_block(intercept: float = 0.5, coef: float = 0.02) -> dict:
    return {
        "total_goals_ft": {"intercept": intercept, "coefficient": coef, "train_n": 100},
        "goals_ge_2": {"intercept": -1.0, "coefficient": 0.03, "train_n": 100},
        "goals_ge_3": {"intercept": -2.0, "coefficient": 0.03, "train_n": 100},
        "btts_ft": {"intercept": -1.5, "coefficient": 0.02, "train_n": 100},
    }


def _frozen_bundle(**overrides):
    weights = {p: round(1.0 / len(GI_F_PILLARS), 6) for p in GI_F_PILLARS}
    defs = {
        "parent_bundle_id": 1,
        "parent_bundle_version": "cecchino_goal_intensity_v5_preview_v1_1",
        "parent_definition_hash": "parenthash",
        "development_protocol_version": DEVELOPMENT_PROTOCOL_VERSION,
        "active_candidate_ids": list(ACTIVE_CANDIDATE_IDS),
        "archived_candidate_ids": list(ARCHIVED_CANDIDATE_IDS),
        "intended_use": "historical_external_benchmark_only",
        "live_scoring_enabled": False,
        "signals_integration_enabled": False,
        "no_2021_22_usage": True,
        "holdout_access_count": 1,
        "gi_f_weights": weights,
        "selected_alpha": 1.0,
        GI_F_ID: {"weights": weights, "selected_alpha": 1.0},
        "split_metadata": {
            "train": {"fixture_ids_hash": "t", "n": 100},
            "validation": {"fixture_ids_hash": "v", "n": 40},
            "holdout": {"fixture_ids_hash": "h", "n": 60},
        },
    }
    # Minimal ECDF train values
    norm = {
        "features": {
            k: {"train_values": [float(i) for i in range(1, 21)], "distribution_hash": f"h-{k}"}
            for k in (
                "home_goals_scored_avg",
                "home_goals_scored_rolling_5",
                "home_goals_conceded_avg",
                "away_goals_conceded_avg",
                "total_goals_avg",
                "total_goals_rolling_5",
                "goals_scored_std_last_10",
            )
        }
    }
    cal = {
        PRIMARY_ID: _cal_block(0.4, 0.025),
        CHALLENGER_ID: _cal_block(0.45, 0.024),
        GI_E_ID: _cal_block(0.35, 0.028),
        GI_F_ID: _cal_block(0.38, 0.026),
    }
    row = SimpleNamespace(
        id=99,
        version=TARGET_BUNDLE_VERSION,
        status=BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
        is_active=False,
        candidate_definition_hash="defhash123",
        fixture_ids_hash="fixhash",
        targets_hash="tgthash",
        normalization_payload=norm,
        calibration_payload=cal,
        candidate_definitions_payload=defs,
        retrospective_date_from=None,
        retrospective_date_to=None,
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def _features() -> dict:
    return {
        "home_goals_scored_avg": 1.4,
        "home_goals_scored_rolling_5": 1.6,
        "home_goals_conceded_avg": 1.1,
        "away_goals_conceded_avg": 1.2,
        "total_goals_avg": 2.5,
        "total_goals_rolling_5": 2.7,
        "goals_scored_std_last_10": 0.9,
    }


def _snap(**kwargs):
    now = datetime(2021, 10, 15, 15, 0, tzinfo=timezone.utc)
    base = dict(
        id=1,
        lab_match_id=1001,
        competition_name="E0",
        kickoff_at=now,
        chronological_order=1,
        cecchino_output_json={
            "goal_intensity_analysis": {
                "status": "available",
                "expected_goals_total": 2.4,
                "version": "cecchino_goal_intensity_v4_expected_goals",
            }
        },
        goal_intensity_compatibility_json={
            "inputs": {"bundle_features": _features()},
        },
        result_json={"fulltime": {"home": 2, "away": 1}},
        input_snapshot_json={},
        module_availability_json={},
        balance_v5_json={},
        historical_kpi_json={},
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_validate_frozen_bundle_ok():
    meta = validate_frozen_candidate_bundle(_frozen_bundle())
    assert meta["is_active"] is False
    assert meta["version"] == TARGET_BUNDLE_VERSION
    assert meta["intended_use"] == "historical_external_benchmark_only"


def test_active_bundle_rejected():
    b = _frozen_bundle(is_active=True, status=BUNDLE_STATUS_ACTIVE)
    with pytest.raises(CecchinoLabImportError) as ei:
        validate_frozen_candidate_bundle(b)
    assert ei.value.code == "frozen_candidate_bundle_invalid"


def test_get_frozen_rejects_wrong_version():
    db = MagicMock()
    with pytest.raises(CecchinoLabImportError):
        get_frozen_goal_intensity_candidate_bundle(db, version="cecchino_goal_intensity_v5_preview_v1_1")


def test_extract_v4_from_persisted_payload():
    v4, reason = extract_v4_from_historical_snapshot(_snap())
    assert reason is None
    assert v4 is not None
    assert v4["expected_goals_total"] == 2.4


def test_extract_v4_missing():
    s = _snap(cecchino_output_json={})
    v4, reason = extract_v4_from_historical_snapshot(s)
    assert v4 is None
    assert reason == "missing_persisted_v4_expected_goals"


def test_extract_v5_features_and_missing():
    feats, reason = extract_v5_features_from_snapshot(_snap())
    assert reason is None
    assert feats is not None
    assert feats["total_goals_avg"] == 2.5
    bad, reason2 = extract_v5_features_from_snapshot(
        _snap(goal_intensity_compatibility_json={})
    )
    assert bad is None
    assert reason2 == "missing_v5_features"


def test_extract_ft_target():
    t, r = extract_ft_target({"fulltime": {"home": 1, "away": 1}})
    assert r is None
    assert t["total_goals_ft"] == 2
    assert t["btts_ft"] == 1
    assert t["goals_ge_2"] == 1


def test_score_five_models_gi_e_equals_gi_a_and_no_refit():
    bundle = _frozen_bundle()
    v4, _ = extract_v4_from_historical_snapshot(_snap())
    pred = score_five_models_with_frozen_bundle(
        features=_features(), v4_payload=v4, bundle=bundle
    )
    assert pred["five_models_available"] is True
    assert pred["no_refit"] is True
    assert pred["gi_e_raw_equals_gi_a"] is True
    models = pred["models"]
    assert models[PRIMARY_ID]["raw_score"] == models[GI_E_ID]["raw_score"]
    assert models[GI_F_ID]["raw_score"] is not None
    assert set(pred["gi_f_weights_frozen"].keys()) == set(GI_F_PILLARS)
    assert models[V4_MODEL_ID]["btts_status"] == "not_comparable"
    assert ARCHIVED_CANDIDATE_IDS[0] in pred["archived_not_selected"]


def test_score_rejects_result_leakage_in_features():
    bundle = _frozen_bundle()
    v4, _ = extract_v4_from_historical_snapshot(_snap())
    leak = {**_features(), "total_goals_ft": 3}
    with pytest.raises(CecchinoLabImportError) as ei:
        score_five_models_with_frozen_bundle(features=leak, v4_payload=v4, bundle=bundle)
    assert ei.value.code == "result_leakage_in_features"


def test_prediction_before_result_order_spy():
    """Spy: lo scorer non riceve il risultato nel payload feature."""
    bundle = _frozen_bundle()
    v4, _ = extract_v4_from_historical_snapshot(_snap())
    calls = []

    def _spy(features, v4_payload, bundle):  # noqa: ARG001
        calls.append(dict(features))
        assert "total_goals_ft" not in features
        assert "result" not in features
        return score_five_models_with_frozen_bundle(
            features=features, v4_payload=v4_payload, bundle=bundle
        )

    with patch.object(svc, "score_five_models_with_frozen_bundle", side_effect=_spy):
        out = svc._process_one_snapshot(
            snap=_snap(),
            bundle=bundle,
            bundle_hash="defhash123",
        )
    assert calls
    assert out["included_in_main_cohort"] is True
    assert out["target_payload_json"]["total_goals_ft"] == 3


def test_pilot_deterministic_and_not_target_based():
    snaps = []
    base = datetime(2021, 8, 1, tzinfo=timezone.utc)
    for i in range(60):
        snaps.append(
            SimpleNamespace(
                id=i + 1,
                lab_match_id=1000 + i,
                competition_name=["E0", "I1", "SP1"][i % 3],
                kickoff_at=base + timedelta(days=i),
                chronological_order=i,
                # decoy target fields that must be ignored
                result_json={"fulltime": {"home": i % 5, "away": i % 3}},
            )
        )
    a = select_pilot_snapshots(snaps, pilot_size=12, random_seed=42)
    b = select_pilot_snapshots(snaps, pilot_size=12, random_seed=42)
    assert a["selection_hash"] == b["selection_hash"]
    assert a["snapshot_ids"] == b["snapshot_ids"]
    assert len(a["snapshot_ids"]) == 12
    assert len(set(a["snapshot_ids"])) == 12
    assert set(a["competition_distribution"].keys()) >= {"E0", "I1", "SP1"}


def test_independence_external_2021_22():
    db = MagicMock()
    run = SimpleNamespace(id=1, season_label="2021/22", status="completed")
    snaps = [
        SimpleNamespace(
            id=i,
            lab_match_id=i,
            kickoff_at=datetime(2021, 9, i + 1, tzinfo=timezone.utc),
            input_snapshot_json={},
            module_availability_json={},
            cecchino_output_json={},
        )
        for i in range(1, 6)
    ]
    parent = SimpleNamespace(
        id=1,
        fixture_ids_hash="parentfx",
        targets_hash="parenttg",
        retrospective_date_from=datetime(2025, 1, 1).date(),
        retrospective_date_to=datetime(2025, 6, 1).date(),
        candidate_definitions_payload={
            "prospective_guard": {
                "retrospective_today_fixture_ids": [9001, 9002],
                "retrospective_local_fixture_ids": [],
                "retrospective_provider_fixture_ids": [],
            }
        },
    )
    with patch(
        "app.services.cecchino_data_lab.goal_intensity_historical_benchmark_independence.get_active_bundle",
        return_value=parent,
    ):
        report = assess_independence(
            db=db, run=run, snapshots=snaps, candidate_bundle=_frozen_bundle()
        )
    assert report["status"] == INDEPENDENCE_EXTERNAL
    assert report["overlap_count"] == 0


def test_independence_partial_and_full_overlap():
    db = MagicMock()
    run = SimpleNamespace(id=1, season_label="2025", status="completed")
    snaps = [
        SimpleNamespace(
            id=1,
            lab_match_id=1,
            kickoff_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
            input_snapshot_json={"today_fixture_id": 10},
            module_availability_json={},
            cecchino_output_json={},
        ),
        SimpleNamespace(
            id=2,
            lab_match_id=2,
            kickoff_at=datetime(2025, 3, 2, tzinfo=timezone.utc),
            input_snapshot_json={"today_fixture_id": 11},
            module_availability_json={},
            cecchino_output_json={},
        ),
        SimpleNamespace(
            id=3,
            lab_match_id=3,
            kickoff_at=datetime(2025, 3, 3, tzinfo=timezone.utc),
            input_snapshot_json={"today_fixture_id": 12},
            module_availability_json={},
            cecchino_output_json={},
        ),
    ]
    parent = SimpleNamespace(
        id=1,
        fixture_ids_hash="p",
        targets_hash="t",
        retrospective_date_from=datetime(2025, 1, 1).date(),
        retrospective_date_to=datetime(2025, 12, 1).date(),
        candidate_definitions_payload={
            "prospective_guard": {
                "retrospective_today_fixture_ids": [10],
                "retrospective_local_fixture_ids": [],
                "retrospective_provider_fixture_ids": [],
            }
        },
    )
    cand = _frozen_bundle()
    cand.candidate_definitions_payload = {
        **cand.candidate_definitions_payload,
        "parent_bundle_id": None,
    }
    db.get.return_value = None
    with patch(
        "app.services.cecchino_data_lab.goal_intensity_historical_benchmark_independence.get_active_bundle",
        return_value=parent,
    ):
        partial = assess_independence(
            db=db, run=run, snapshots=snaps, candidate_bundle=cand
        )
    assert partial["status"] == INDEPENDENCE_PARTIAL

    parent2 = SimpleNamespace(
        id=1,
        fixture_ids_hash="p",
        targets_hash="t",
        retrospective_date_from=datetime(2025, 1, 1).date(),
        retrospective_date_to=datetime(2025, 12, 1).date(),
        candidate_definitions_payload={
            "prospective_guard": {
                "retrospective_today_fixture_ids": [10, 11, 12],
                "retrospective_local_fixture_ids": [],
                "retrospective_provider_fixture_ids": [],
            }
        },
    )
    with patch(
        "app.services.cecchino_data_lab.goal_intensity_historical_benchmark_independence.get_active_bundle",
        return_value=parent2,
    ):
        full = assess_independence(
            db=db, run=run, snapshots=snaps, candidate_bundle=cand
        )
    assert full["status"] == INDEPENDENCE_FULL


def test_independence_unknown_without_identities():
    db = MagicMock()
    run = SimpleNamespace(id=1, season_label="mystery", status="completed")
    snaps = [
        SimpleNamespace(
            id=1,
            lab_match_id=1,
            kickoff_at=None,
            input_snapshot_json={},
            module_availability_json={},
            cecchino_output_json={},
        )
    ]
    with patch(
        "app.services.cecchino_data_lab.goal_intensity_historical_benchmark_independence.get_active_bundle",
        return_value=None,
    ):
        report = assess_independence(
            db=db,
            run=run,
            snapshots=snaps,
            candidate_bundle=_frozen_bundle(
                candidate_definitions_payload={
                    **_frozen_bundle().candidate_definitions_payload,
                    "no_2021_22_usage": False,
                    "parent_bundle_id": None,
                }
            ),
        )
    assert report["status"] in {INDEPENDENCE_UNKNOWN, INDEPENDENCE_EXTERNAL}


def test_metrics_and_bootstrap_pairwise():
    rows = []
    for i in range(40):
        y = 2.0 + (i % 3)
        rows.append(
            {
                "snapshot_id": i,
                "competition": "E0",
                "kickoff": f"2021-09-{(i % 28) + 1:02d}T15:00:00+00:00",
                "month": "2021-09",
                "models": {
                    V4_MODEL_ID: {
                        "expected_total_goals": y + 0.2,
                        "probability_goals_ge_2": 0.7,
                        "probability_goals_ge_3": 0.4,
                    },
                    PRIMARY_ID: {
                        "raw_score": 50 + i % 10,
                        "expected_total_goals": y + 0.1,
                        "probability_goals_ge_2": 0.72,
                        "probability_goals_ge_3": 0.41,
                        "probability_btts": 0.55,
                    },
                    CHALLENGER_ID: {
                        "raw_score": 48,
                        "expected_total_goals": y + 0.15,
                        "probability_goals_ge_2": 0.71,
                        "probability_goals_ge_3": 0.42,
                        "probability_btts": 0.54,
                    },
                    GI_E_ID: {
                        "raw_score": 50,
                        "expected_total_goals": y + 0.05,
                        "probability_goals_ge_2": 0.73,
                        "probability_goals_ge_3": 0.43,
                        "probability_btts": 0.56,
                    },
                    GI_F_ID: {
                        "raw_score": 49,
                        "expected_total_goals": y,
                        "probability_goals_ge_2": 0.74,
                        "probability_goals_ge_3": 0.44,
                        "probability_btts": 0.57,
                    },
                },
                "target": {
                    "total_goals_ft": y,
                    "goals_ge_2": int(y >= 2),
                    "goals_ge_3": int(y >= 3),
                    "btts_ft": 1,
                },
            }
        )
    ev = evaluate_paired_rows(rows)
    assert ev["paired_n"] == 40
    assert V4_MODEL_ID in ev["model_metrics"]
    assert ev["model_metrics"][V4_MODEL_ID]["btts"]["status"] == "not_comparable"
    assert len(ev["pairwise"]) == 9


def test_confirm_tokens_and_job_version():
    assert CONFIRM_PILOT == "RUN_GOAL_INTENSITY_HISTORICAL_BENCHMARK_PILOT"
    assert CONFIRM_FULL == "RUN_GOAL_INTENSITY_HISTORICAL_BENCHMARK_FULL"
    assert JOB_VERSION == "cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1"
    assert REQUIRED_BUNDLE_VERSION == TARGET_BUNDLE_VERSION


def test_start_rejects_non_completed_run():
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=1, status="running", season_label="2021/22")
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.start_goal_intensity_benchmark_job(
            db, 1, mode=MODE_PILOT, confirm=CONFIRM_PILOT, background=False
        )
    assert ei.value.code == "run_not_completed"


def test_start_rejects_bad_confirm():
    db = MagicMock()
    db.get.return_value = SimpleNamespace(
        id=1, status="completed", season_label="2021/22", source_git_commit="abc"
    )
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.start_goal_intensity_benchmark_job(
            db, 1, mode=MODE_PILOT, confirm="WRONG", background=False
        )
    assert ei.value.code == "confirm_token_invalid"


def test_full_gate_requires_pilot():
    db = MagicMock()
    run = SimpleNamespace(
        id=1, status="completed", season_label="2021/22", source_git_commit="abc"
    )
    bundle = _frozen_bundle()

    def _get(model, pk):  # noqa: ARG001
        if pk == 1:
            return run
        return None

    db.get.side_effect = _get
    with (
        patch.object(svc, "get_frozen_goal_intensity_candidate_bundle", return_value=bundle),
        patch.object(svc, "_load_snapshots", return_value=[_snap()]),
        patch.object(
            svc,
            "build_goal_intensity_benchmark_preflight",
            return_value={
                "pilot_allowed": True,
                "independence": {"status": INDEPENDENCE_EXTERNAL, "details": {"run_fixture_ids_hash": "x"}},
                "pilot": {"selection_hash": "sel", "selected": 1, "requested": 1},
            },
        ),
        patch.object(svc, "_find_completed_pilot", return_value=None),
    ):
        with pytest.raises(CecchinoLabImportError) as ei:
            svc.start_goal_intensity_benchmark_job(
                db, 1, mode=MODE_FULL, confirm=CONFIRM_FULL, background=False
            )
    assert ei.value.code == "pilot_gate_missing"


def test_cancel_sets_flag():
    db = MagicMock()
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(
        id=7,
        historical_run_id=1,
        bundle_id=9,
        job_version=JOB_VERSION,
        mode=MODE_PILOT,
        status=STATUS_QUEUED,
        independence_status=INDEPENDENCE_EXTERNAL,
        job_key="k",
        random_seed=42,
        requested_sample_size=300,
        total_snapshots=10,
        eligible_snapshots=10,
        selected_snapshots=10,
        processed_snapshots=0,
        paired_complete=0,
        skipped=0,
        errors=0,
        progress_pct=None,
        cancel_requested=False,
        params_json={},
        preflight_json={},
        summary_json=None,
        missing_by_reason_json=None,
        error_json=None,
        bundle_definition_hash="h",
        run_fixture_ids_hash="r",
        source_git_commit="abc",
        started_at=None,
        last_checkpoint_at=None,
        completed_at=None,
        cancelled_at=None,
        created_at=now,
        updated_at=now,
    )
    db.get.return_value = job
    out = svc.cancel_goal_intensity_benchmark_job(db, 7)
    assert job.cancel_requested is True
    assert out["status"] == "cancelled"


def test_process_excludes_missing_v4():
    bundle = _frozen_bundle()
    out = svc._process_one_snapshot(
        snap=_snap(cecchino_output_json={}),
        bundle=bundle,
        bundle_hash="h",
    )
    assert out["included_in_main_cohort"] is False
    assert out["exclusion_reason"] == "missing_persisted_v4_expected_goals"
