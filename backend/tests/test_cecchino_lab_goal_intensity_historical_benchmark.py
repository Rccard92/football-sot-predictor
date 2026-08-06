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


def _five_models_payload() -> dict:
    from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_scoring import (
        MAIN_MODEL_IDS,
    )

    models = {
        mid: {"expected_total_goals": 2.5, "probability_goals_ge_3": 0.4}
        for mid in MAIN_MODEL_IDS
    }
    return {"five_models_available": True, "models": models}


def _pilot_job(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=99,
        historical_run_id=1,
        bundle_id=9,
        job_version=JOB_VERSION,
        mode=MODE_PILOT,
        status=STATUS_COMPLETED,
        independence_status=INDEPENDENCE_EXTERNAL,
        job_key="k",
        random_seed=42,
        requested_sample_size=10,
        total_snapshots=10,
        eligible_snapshots=10,
        selected_snapshots=10,
        processed_snapshots=10,
        paired_complete=3,
        skipped=7,
        errors=0,
        progress_pct=100,
        cancel_requested=False,
        params_json={},
        preflight_json={},
        summary_json={
            "checks": {
                "external_api_calls": 0,
                "base_run_writes": 0,
                "result_used_in_prediction": False,
                "bundle_refit": False,
                "full_scan_restarted": False,
            },
            "reconciliation_ok": True,
            "reconciliation": {
                "ok": True,
                "all_paired_have_five_models": True,
                "selected": 10,
                "processed": 10,
            },
        },
        missing_by_reason_json=None,
        error_json=None,
        bundle_definition_hash="h",
        run_fixture_ids_hash="r",
        source_git_commit="abc",
        started_at=now,
        last_checkpoint_at=now,
        completed_at=now,
        cancelled_at=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _row(**overrides):
    base = dict(
        historical_snapshot_id=1,
        included_in_main_cohort=True,
        exclusion_reason=None,
        input_hash="abc123",
        prediction_payload_json=_five_models_payload(),
        target_payload_json={"total_goals_ft": 2},
        evaluation_payload_json={
            "included_in_main_cohort": True,
            "models_present": list(
                __import__(
                    "app.services.cecchino_data_lab.goal_intensity_historical_benchmark_scoring",
                    fromlist=["MAIN_MODEL_IDS"],
                ).MAIN_MODEL_IDS
            ),
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_pilot_gate_blocks_zero_paired():
    job = _pilot_job(paired_complete=0, skipped=10, errors=0, processed_snapshots=10)
    ok, reasons = svc._pilot_gate_ok(job)
    assert ok is False
    assert "pilot_zero_paired_complete" in reasons


def test_pilot_gate_blocks_errors():
    job = _pilot_job(errors=2, paired_complete=3, skipped=5, processed_snapshots=10)
    ok, reasons = svc._pilot_gate_ok(job)
    assert ok is False
    assert "pilot_errors_nonzero" in reasons


def test_pilot_gate_blocks_processed_selected_mismatch():
    job = _pilot_job(processed_snapshots=8, selected_snapshots=10)
    ok, reasons = svc._pilot_gate_ok(job)
    assert ok is False
    assert "pilot_processed_selected_mismatch" in reasons


def test_pilot_gate_blocks_sum_mismatch():
    job = _pilot_job(paired_complete=3, skipped=3, errors=0, processed_snapshots=10)
    ok, reasons = svc._pilot_gate_ok(job)
    assert ok is False
    assert "pilot_checks_failed" in reasons


def test_pilot_gate_blocks_missing_five_models():
    job = _pilot_job(
        summary_json={
            "checks": {
                "external_api_calls": 0,
                "base_run_writes": 0,
                "result_used_in_prediction": False,
                "bundle_refit": False,
                "full_scan_restarted": False,
            },
            "reconciliation_ok": True,
            "reconciliation": {"ok": True, "all_paired_have_five_models": False},
        }
    )
    bad = _row(
        prediction_payload_json={"five_models_available": False, "models": {}},
        evaluation_payload_json={"included_in_main_cohort": True, "models_present": []},
    )
    ok, reasons = svc._pilot_gate_ok(job, paired_rows=[bad])
    assert ok is False
    assert "pilot_five_models_missing" in reasons


def test_pilot_gate_accepts_valid():
    job = _pilot_job()
    good = _row()
    ok, reasons = svc._pilot_gate_ok(job, paired_rows=[good])
    assert ok is True
    assert reasons == []


def test_row_exception_needs_retry_deterministic_skip_complete():
    exc_row = _row(
        included_in_main_cohort=False,
        exclusion_reason="row_exception",
        input_hash=None,
        prediction_payload_json=None,
        evaluation_payload_json={"error": "boom"},
    )
    assert svc.row_is_complete(exc_row, "h") is False

    skip_row = _row(
        included_in_main_cohort=False,
        exclusion_reason="missing_persisted_v4_expected_goals",
        input_hash=None,
        prediction_payload_json=None,
        evaluation_payload_json=None,
    )
    assert svc.row_is_complete(skip_row, "h") is True

    paired = _row()
    assert svc.row_is_complete(paired, "h") is True


def test_recount_counters_no_double_count():
    rows = [
        _row(historical_snapshot_id=1, included_in_main_cohort=True, exclusion_reason=None),
        _row(
            historical_snapshot_id=2,
            included_in_main_cohort=False,
            exclusion_reason="missing_ft_result",
            input_hash=None,
            prediction_payload_json=None,
        ),
        _row(
            historical_snapshot_id=3,
            included_in_main_cohort=False,
            exclusion_reason="row_exception",
            input_hash=None,
            prediction_payload_json=None,
        ),
    ]
    c = svc.recount_counters_from_rows(rows)
    assert c["processed"] == 3
    assert c["paired"] == 1
    assert c["skipped"] == 1
    assert c["errors"] == 1
    assert c["duplicate_rows"] == 0


def test_reconciliation_requires_all_conditions():
    counters = {
        "processed": 10,
        "paired": 3,
        "skipped": 7,
        "errors": 0,
        "rows_persisted": 10,
        "duplicate_rows": 0,
    }
    recon = svc.build_reconciliation(selected=10, counters=counters, paired_have_five=True)
    assert recon["ok"] is True

    recon_err = svc.build_reconciliation(
        selected=10,
        counters={**counters, "errors": 1, "skipped": 6},
        paired_have_five=True,
    )
    assert recon_err["ok"] is False
    assert recon_err["errors"] == 1


def test_job_with_errors_not_completed_via_reconciliation():
    counters = {
        "processed": 5,
        "paired": 2,
        "skipped": 2,
        "errors": 1,
        "rows_persisted": 5,
        "duplicate_rows": 0,
    }
    recon = svc.build_reconciliation(selected=5, counters=counters, paired_have_five=True)
    assert recon["ok"] is False
    # worker marks failed when not ok — mirrored here
    status = STATUS_COMPLETED if recon["ok"] and counters["errors"] == 0 else "failed"
    assert status == "failed"


def test_stale_running_recoverable_fresh_not():
    from app.models.cecchino_lab_goal_intensity_benchmark_job import (
        GI_BENCH_STALE_CHECKPOINT_SECONDS,
        STATUS_RUNNING,
    )

    now = datetime.now(timezone.utc)
    stale_job = _pilot_job(
        status=STATUS_RUNNING,
        completed_at=None,
        last_checkpoint_at=now - timedelta(seconds=GI_BENCH_STALE_CHECKPOINT_SECONDS + 30),
        started_at=now - timedelta(seconds=GI_BENCH_STALE_CHECKPOINT_SECONDS + 60),
    )
    assert svc.is_job_stale(stale_job) is True
    assert svc.can_resume_job(stale_job) is True
    assert svc.effective_status(stale_job) == "interrupted"

    fresh_job = _pilot_job(
        status=STATUS_RUNNING,
        completed_at=None,
        last_checkpoint_at=now,
        started_at=now,
    )
    assert svc.is_job_stale(fresh_job) is False
    assert svc.can_resume_job(fresh_job) is False


def test_queued_orphan_recoverable():
    orphan = _pilot_job(
        status=STATUS_QUEUED,
        completed_at=None,
        started_at=None,
        last_checkpoint_at=None,
        updated_at=None,
    )
    # no live thread → stale/orphan
    assert svc.is_job_stale(orphan) is True
    assert svc.can_resume_job(orphan) is True


def test_resume_rejects_fresh_active():
    db = MagicMock()
    now = datetime.now(timezone.utc)
    job = _pilot_job(
        status="running",
        completed_at=None,
        last_checkpoint_at=now,
        started_at=now,
    )
    db.get.return_value = job
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.resume_goal_intensity_benchmark_job(db, 99)
    assert ei.value.code == "job_already_active"


def test_resume_allows_stale_running():
    from app.models.cecchino_lab_goal_intensity_benchmark_job import (
        GI_BENCH_STALE_CHECKPOINT_SECONDS,
    )

    db = MagicMock()
    now = datetime.now(timezone.utc)
    job = _pilot_job(
        status="running",
        completed_at=None,
        last_checkpoint_at=now - timedelta(seconds=GI_BENCH_STALE_CHECKPOINT_SECONDS + 10),
        started_at=now - timedelta(seconds=GI_BENCH_STALE_CHECKPOINT_SECONDS + 20),
    )
    db.get.return_value = job
    with patch.object(svc, "_spawn_worker"):
        out = svc.resume_goal_intensity_benchmark_job(db, 99)
    assert job.status == STATUS_QUEUED
    assert out["status"] == STATUS_QUEUED


def test_advisory_lock_blocks_second_worker():
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    with svc.acquire_gi_bench_job_lock(4242, engine=engine):
        with pytest.raises(svc.GiBenchJobLockNotAcquired):
            with svc.acquire_gi_bench_job_lock(4242, engine=engine):
                pass


def test_crash_after_batch_resume_retries_exception_only():
    """Simulate remaining selection: complete skip kept, row_exception retried."""
    complete_skip = _row(
        historical_snapshot_id=1,
        included_in_main_cohort=False,
        exclusion_reason="missing_persisted_v4_expected_goals",
        input_hash=None,
        prediction_payload_json=None,
        evaluation_payload_json=None,
    )
    failed = _row(
        historical_snapshot_id=2,
        included_in_main_cohort=False,
        exclusion_reason="row_exception",
        input_hash=None,
        prediction_payload_json=None,
        evaluation_payload_json={"error": "x"},
    )
    done_map = {1: complete_skip, 2: failed}
    selected = [1, 2, 3]
    remaining = [
        sid
        for sid in selected
        if sid not in done_map or not svc.row_is_complete(done_map[sid], "h")
    ]
    assert remaining == [2, 3]
    # recount after hypothetical resume of only new/failed
    after = [
        complete_skip,
        _row(historical_snapshot_id=2),  # recovered paired
        _row(
            historical_snapshot_id=3,
            included_in_main_cohort=False,
            exclusion_reason="missing_ft_result",
            input_hash=None,
            prediction_payload_json=None,
        ),
    ]
    c = svc.recount_counters_from_rows(after)
    assert c["processed"] == 3
    assert c["paired"] == 1
    assert c["skipped"] == 2
    assert c["errors"] == 0


def test_pilot_gate_blocks_reconciliation_failed():
    job = _pilot_job(
        summary_json={
            "checks": {
                "external_api_calls": 0,
                "base_run_writes": 0,
                "result_used_in_prediction": False,
                "bundle_refit": False,
                "full_scan_restarted": False,
            },
            "reconciliation_ok": False,
            "reconciliation": {"ok": False, "all_paired_have_five_models": True},
        }
    )
    ok, reasons = svc._pilot_gate_ok(job, paired_rows=[_row()])
    assert ok is False
    assert "pilot_reconciliation_failed" in reasons


# ---------------------------------------------------------------------------
# Regression: snapshot load uses ORM run_id (not historical_run_id)
# ---------------------------------------------------------------------------


def test_historical_match_snapshot_model_exposes_run_id():
    from app.models.cecchino_lab_goal_intensity_benchmark_job import (
        CecchinoLabGoalIntensityBenchmarkJob,
    )
    from app.models.cecchino_lab_historical_match_snapshot import (
        CecchinoLabHistoricalMatchSnapshot,
    )

    assert hasattr(CecchinoLabHistoricalMatchSnapshot, "run_id")
    assert not hasattr(CecchinoLabHistoricalMatchSnapshot, "historical_run_id")
    assert "run_id" in CecchinoLabHistoricalMatchSnapshot.__table__.c
    assert "historical_run_id" not in CecchinoLabHistoricalMatchSnapshot.__table__.c
    # Job model intentionally uses historical_run_id — must stay distinct
    assert hasattr(CecchinoLabGoalIntensityBenchmarkJob, "historical_run_id")


def test_load_snapshots_query_uses_run_id_and_orders_by_id():
    """Chiama _load_snapshots reale (no patch) contro il modello ORM reale."""
    from app.models.cecchino_lab_historical_match_snapshot import (
        CecchinoLabHistoricalMatchSnapshot,
    )

    run_id = 42
    ordered = [_snap(id=1, run_id=run_id), _snap(id=3, run_id=run_id)]
    db = MagicMock()
    captured: list = []

    def _scalars(stmt):
        captured.append(stmt)
        result = MagicMock()
        result.all.return_value = ordered
        return result

    db.scalars.side_effect = _scalars

    out = svc._load_snapshots(db, run_id)

    assert out == ordered
    assert len(captured) == 1
    stmt = captured[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "cecchino_lab_historical_match_snapshots.run_id" in compiled
    assert "historical_run_id" not in compiled
    assert str(run_id) in compiled
    assert "order by" in compiled
    assert "id" in compiled
    # Filtro sulla colonna ORM reale run_id
    assert stmt.whereclause.left.name == "run_id"
    assert int(stmt.whereclause.right.value) == run_id
    order_elems = list(stmt._order_by_clauses)
    assert order_elems
    assert "id" in " ".join(str(e) for e in order_elems).lower()
    assert stmt.column_descriptions[0]["entity"] is CecchinoLabHistoricalMatchSnapshot


def test_preflight_service_uses_real_load_snapshots_readonly():
    """Preflight completed run: supera il load snapshot senza AttributeError; read-only."""
    run_id = 7
    run = SimpleNamespace(
        id=run_id,
        status="completed",
        season_label="2021/22",
        source_git_commit="abc123",
    )
    snaps = [
        _snap(id=10, run_id=run_id),
        _snap(id=11, run_id=run_id),
    ]
    bundle = _frozen_bundle()
    db = MagicMock()
    db.get.return_value = run

    def _scalars(stmt):
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
        assert "run_id" in compiled
        assert "historical_run_id" not in compiled
        assert str(run_id) in compiled
        result = MagicMock()
        result.all.return_value = snaps
        return result

    db.scalars.side_effect = _scalars

    independence = {
        "status": INDEPENDENCE_EXTERNAL,
        "details": {"run_fixture_ids_hash": "fx"},
    }
    with (
        patch.object(svc, "get_frozen_goal_intensity_candidate_bundle", return_value=bundle),
        patch.object(
            svc,
            "validate_frozen_candidate_bundle",
            return_value={
                "is_active": False,
                "live_scoring_enabled": False,
                "intended_use": "historical_external_benchmark_only",
                "version": TARGET_BUNDLE_VERSION,
            },
        ),
        patch.object(svc, "assess_independence", return_value=independence),
        patch.object(
            svc,
            "_estimate_availability",
            return_value={
                "paired_complete_estimate": 2,
                "v4_rebuildable": 2,
                "five_models_probe_failed_completely": False,
            },
        ),
        patch.object(
            svc,
            "select_pilot_snapshots",
            return_value={
                "selected": 2,
                "requested": 2,
                "snapshot_ids": [10, 11],
                "selection_hash": "sel",
            },
        ),
    ):
        # _load_snapshots intentionally NOT patched — must use ORM run_id
        out = svc.build_goal_intensity_benchmark_preflight(db, run_id)

    assert out["status"] == "preview"
    assert out["run"]["id"] == run_id
    assert out["run"]["snapshots_found"] == 2
    assert out["independence"]["status"] == INDEPENDENCE_EXTERNAL
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.flush.assert_not_called()


def test_preflight_route_no_500_readonly_zero_jobs():
    """Route preflight: run completed + snapshot via run_id → 200, zero scritture."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.routes import cecchino_lab

    run_id = 3
    run = SimpleNamespace(
        id=run_id,
        status="completed",
        season_label="2021/22",
        source_git_commit="deadbeef",
    )
    snaps = [_snap(id=1, run_id=run_id), _snap(id=2, run_id=run_id)]
    bundle = _frozen_bundle()

    app = FastAPI()
    app.include_router(cecchino_lab.admin_router, prefix="/api")
    db = MagicMock()
    db.get.return_value = run

    def _scalars(stmt):
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
        assert "historical_run_id" not in compiled
        assert "run_id" in compiled
        result = MagicMock()
        result.all.return_value = snaps
        return result

    db.scalars.side_effect = _scalars

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    client = TestClient(app)

    with (
        patch.object(svc, "get_frozen_goal_intensity_candidate_bundle", return_value=bundle),
        patch.object(
            svc,
            "validate_frozen_candidate_bundle",
            return_value={
                "is_active": False,
                "live_scoring_enabled": False,
                "intended_use": "historical_external_benchmark_only",
                "version": TARGET_BUNDLE_VERSION,
            },
        ),
        patch.object(
            svc,
            "assess_independence",
            return_value={
                "status": INDEPENDENCE_EXTERNAL,
                "details": {"run_fixture_ids_hash": "fx"},
            },
        ),
        patch.object(
            svc,
            "_estimate_availability",
            return_value={
                "paired_complete_estimate": 2,
                "v4_rebuildable": 2,
                "five_models_probe_failed_completely": False,
            },
        ),
        patch.object(
            svc,
            "select_pilot_snapshots",
            return_value={
                "selected": 2,
                "requested": 2,
                "snapshot_ids": [1, 2],
                "selection_hash": "sel",
            },
        ),
    ):
        res = client.post(
            f"/api/admin/cecchino-lab/historical/runs/{run_id}/goal-intensity-benchmark/preflight",
            json={},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "preview"
    assert body["run"]["snapshots_found"] == 2
    assert body["run"]["id"] == run_id
    db.add.assert_not_called()
    db.commit.assert_not_called()
    assert db.add.call_count == 0

