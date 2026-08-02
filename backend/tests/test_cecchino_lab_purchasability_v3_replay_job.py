"""Test job replay Acquistabilità V3 isolato (STEP 3B.1)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models.cecchino_lab_purchasability_v3_replay_result import (
    CecchinoLabPurchasabilityV3ReplayResult,
)
from app.models.cecchino_lab_purchasability_v3_replay_run import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    CecchinoLabPurchasabilityV3ReplayRun,
)
from app.routes import cecchino_lab
from app.schemas.cecchino_purchasability_v3 import PURCHASABILITY_V3_FORMULA_VERSION
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight import (
    FORMULA_PAYLOAD_ALLOWED_FIELDS,
    FORBIDDEN_FORMULA_FIELDS,
    INTEGRITY_POLICY_VERSION,
    PREFLIGHT_SCHEMA_VERSION,
    V3_MARKET_ORDER,
    build_adapter_panel_row,
)
from app.services.cecchino_data_lab import historical_purchasability_v3_replay_service as svc


def _ready_preflight(**overrides):
    base = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "integrity_policy_version": INTEGRITY_POLICY_VERSION,
        "status": "ready_with_warnings",
        "generated_at": "2026-08-02T10:00:00Z",
        "run": {
            "run_id": 3,
            "season_label": "2021/2022",
            "status": "completed",
            "scan_version": "hist_v1",
            "source_git_commit": "abc123",
        },
        "formula": {
            "candidate_version": "cecchino_purchasability_v3_candidate_1",
            "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
            "audit_version": "cecchino_purchasability_v3_audit_v1",
        },
        "source_integrity": {
            "snapshots_total": 10,
            "snapshots_eligible_core": 8,
            "with_payload_hash": 8,
            "with_historical_freeze_lock": 8,
            "score_performance_phase_separation_verified": True,
        },
        "workload": {
            "theoretical_evaluations": 64,
            "exact_replay_ready": 40,
            "ready_with_warning": 20,
            "gate_only_ready": 0,
            "not_replayable": 4,
            "invalid_integrity": 0,
            "ambiguous_market_join": 0,
            "classified_evaluations_total": 64,
            "unclassified_evaluations": 0,
        },
        "quote_quality": {
            "real": 40,
            "derived": 20,
            "unavailable": 4,
            "inconsistent": 0,
        },
        "blockers": [],
        "warnings": [{"code": "derived_quotes", "message": "derived"}],
        "anti_leakage": {
            "formula_input_whitelist_verified": True,
            "post_match_fields_excluded": True,
        },
    }
    base.update(overrides)
    return base


def _scan(run_id: int = 3):
    return SimpleNamespace(
        id=run_id,
        scan_version="hist_v1",
        source_git_commit="abc123",
        season_label="2021/2022",
        status="completed",
    )


def _replay_obj(**kwargs):
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=10,
        source_scan_run_id=3,
        status=STATUS_QUEUED,
        replay_schema_version=svc.REPLAY_SCHEMA_VERSION,
        replay_engine_version=svc.REPLAY_ENGINE_VERSION,
        candidate_version="cecchino_purchasability_v3_candidate_1",
        formula_version=PURCHASABILITY_V3_FORMULA_VERSION,
        audit_version="cecchino_purchasability_v3_audit_v1",
        preflight_schema_version=PREFLIGHT_SCHEMA_VERSION,
        integrity_policy_version=INTEGRITY_POLICY_VERSION,
        source_scan_git_commit="abc123",
        runtime_git_commit="def456",
        runtime_git_commit_source="git_rev_parse",
        source_scan_version="hist_v1",
        requested_at=now,
        started_at=None,
        heartbeat_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
        snapshots_total=8,
        snapshots_processed=0,
        evaluations_total=64,
        evaluations_processed=0,
        results_persisted=0,
        progress_pct=None,
        current_snapshot_id=None,
        current_chronological_order=None,
        current_competition=None,
        scored_count=0,
        gate_failed_count=0,
        unavailable_count=0,
        not_applicable_count=0,
        error_count=0,
        unclassified_count=0,
        exact_source_count=40,
        warning_source_count=20,
        non_replayable_source_count=4,
        real_quote_count=0,
        derived_quote_count=0,
        unavailable_quote_count=0,
        real_performance_ready_count=0,
        synthetic_performance_ready_count=0,
        performance_missing_count=0,
        cancel_requested=False,
        resume_count=0,
        attempt_count=1,
        idempotency_key="key",
        preflight_snapshot_json={},
        summary_json={},
        error_json=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Unit: versions, idempotency, whitelist, SHA, invariants
# ---------------------------------------------------------------------------


def test_replay_versions_constants():
    assert svc.REPLAY_SCHEMA_VERSION == "cecchino_lab_purchasability_v3_replay_v1"
    assert svc.REPLAY_ENGINE_VERSION == "cecchino_lab_purchasability_v3_replay_engine_v1"
    assert svc.REPLAY_BATCH_SNAPSHOTS == 100
    assert svc.REPLAY_HEARTBEAT_SECONDS == 5
    assert svc.REPLAY_STALE_HEARTBEAT_SECONDS == 120


def test_idempotency_key_deterministic():
    a = svc.build_idempotency_key(
        source_scan_run_id=3,
        source_scan_version="hist_v1",
        source_scan_git_commit="abc",
        formula_version=PURCHASABILITY_V3_FORMULA_VERSION,
        replay_schema_version=svc.REPLAY_SCHEMA_VERSION,
        integrity_policy_version=INTEGRITY_POLICY_VERSION,
    )
    b = svc.build_idempotency_key(
        source_scan_run_id=3,
        source_scan_version="hist_v1",
        source_scan_git_commit="abc",
        formula_version=PURCHASABILITY_V3_FORMULA_VERSION,
        replay_schema_version=svc.REPLAY_SCHEMA_VERSION,
        integrity_policy_version=INTEGRITY_POLICY_VERSION,
    )
    assert a == b
    assert len(a) == 64


def test_compact_preflight_no_issue_examples():
    pf = _ready_preflight(issue_examples={"x": [{"a": 1}] * 100})
    compact = svc.compact_preflight_snapshot(pf)
    assert "issue_examples" not in compact
    assert "counts" in compact
    assert "versions" in compact
    assert "blockers" in compact


def test_validate_preflight_confirm_gates():
    svc.validate_preflight_for_start(
        _ready_preflight(),
        expected_formula_version=PURCHASABILITY_V3_FORMULA_VERSION,
        expected_preflight_schema_version=PREFLIGHT_SCHEMA_VERSION,
        expected_integrity_policy_version=INTEGRITY_POLICY_VERSION,
    )


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"status": "blocked", "blockers": [{"code": "x", "message": "y"}]}, "preflight_blocked"),
        (
            {
                "workload": {
                    "theoretical_evaluations": 64,
                    "exact_replay_ready": 10,
                    "ready_with_warning": 0,
                    "gate_only_ready": 0,
                    "not_replayable": 0,
                    "invalid_integrity": 0,
                    "ambiguous_market_join": 0,
                    "classified_evaluations_total": 10,
                    "unclassified_evaluations": 54,
                }
            },
            "preflight_unclassified",
        ),
        (
            {
                "workload": {
                    "theoretical_evaluations": 64,
                    "exact_replay_ready": 60,
                    "ready_with_warning": 0,
                    "gate_only_ready": 0,
                    "not_replayable": 0,
                    "invalid_integrity": 4,
                    "ambiguous_market_join": 0,
                    "classified_evaluations_total": 64,
                    "unclassified_evaluations": 0,
                }
            },
            "preflight_invalid_integrity",
        ),
        (
            {
                "workload": {
                    "theoretical_evaluations": 64,
                    "exact_replay_ready": 60,
                    "ready_with_warning": 0,
                    "gate_only_ready": 0,
                    "not_replayable": 0,
                    "invalid_integrity": 0,
                    "ambiguous_market_join": 4,
                    "classified_evaluations_total": 64,
                    "unclassified_evaluations": 0,
                }
            },
            "preflight_ambiguous_join",
        ),
    ],
)
def test_validate_preflight_blocked_cases(overrides, code):
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.validate_preflight_for_start(
            _ready_preflight(**overrides),
            expected_formula_version=None,
            expected_preflight_schema_version=None,
            expected_integrity_policy_version=None,
        )
    assert ei.value.code == code
    assert ei.value.status_code == 409


def test_validate_version_mismatch():
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.validate_preflight_for_start(
            _ready_preflight(),
            expected_formula_version="wrong",
            expected_preflight_schema_version=None,
            expected_integrity_policy_version=None,
        )
    assert ei.value.code == "version_mismatch"


def test_panel_whitelist_and_forbidden():
    m = SimpleNamespace(
        market_key="HOME",
        edge_pct=10.0,
        vantaggio_prob=0.05,
        prob_cecchino=0.45,
        quota_book=2.0,
        quota_cecchino=2.2,
        quote_source_type="bet365_closing",
        is_real_book_quote=True,
        is_derived_quote=False,
        derivation_method=None,
    )
    row = build_adapter_panel_row(m)
    svc.assert_panel_whitelist([row])
    assert set(row.keys()) <= set(FORMULA_PAYLOAD_ALLOWED_FIELDS)
    bad = {**row, "won": True}
    with pytest.raises(svc.ReplayWorkerError) as ei:
        svc.assert_panel_whitelist([bad])
    assert ei.value.code == "forbidden_formula_field_detected"
    assert "won" in FORBIDDEN_FORMULA_FIELDS


def test_formula_payload_sha_deterministic():
    rows = [{"market_key": "HOME", "edge_pct": 1.0}]
    a = svc.formula_payload_sha256(rows)
    b = svc.formula_payload_sha256(rows)
    assert a == b
    expected = hashlib.sha256(
        json.dumps({"rows": rows}, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    assert a == expected


def test_validate_formula_items_mismatch_duplicate_unexpected():
    items = [{"market_key": "HOME"}, {"market_key": "DRAW"}]
    svc.validate_formula_items(expected_keys=["HOME", "DRAW"], items=items)
    with pytest.raises(svc.ReplayWorkerError) as e1:
        svc.validate_formula_items(expected_keys=["HOME"], items=items)
    assert e1.value.code == "formula_item_mismatch"
    with pytest.raises(svc.ReplayWorkerError) as e2:
        svc.validate_formula_items(
            expected_keys=["HOME", "DRAW"],
            items=[{"market_key": "HOME"}, {"market_key": "HOME"}],
        )
    assert e2.value.code == "formula_item_duplicate"
    with pytest.raises(svc.ReplayWorkerError) as e3:
        svc.validate_formula_items(
            expected_keys=["HOME", "DRAW"],
            items=[{"market_key": "HOME"}, {"market_key": "AWAY"}],
        )
    assert e3.value.code == "formula_unexpected_market"


def test_effective_status_interrupted():
    stale = datetime.now(timezone.utc) - timedelta(seconds=200)
    run = _replay_obj(status=STATUS_RUNNING, heartbeat_at=stale)
    assert svc.effective_status(run) == "interrupted"
    assert svc.can_resume(run) is True
    fresh = _replay_obj(status=STATUS_RUNNING, heartbeat_at=datetime.now(timezone.utc))
    assert svc.effective_status(fresh) == STATUS_RUNNING


def test_final_invariants():
    run = _replay_obj(
        results_persisted=64,
        evaluations_total=64,
        scored_count=40,
        gate_failed_count=20,
        unavailable_count=4,
        not_applicable_count=0,
        error_count=0,
        unclassified_count=0,
        real_quote_count=40,
        derived_quote_count=20,
        unavailable_quote_count=4,
    )
    ok, errs = svc._final_invariants_ok(run)
    assert ok and not errs
    run.error_count = 1
    run.scored_count = 39
    ok2, errs2 = svc._final_invariants_ok(run)
    assert not ok2


def test_performance_after_score_real_vs_derived():
    snap = SimpleNamespace(
        id=1,
        lab_match_id=10,
        competition_name="E0",
        kickoff_at=None,
        chronological_order=1,
        pre_match_payload_sha256="aa",
        pre_match_locked_at=None,
    )
    replay = _replay_obj()
    real_m = SimpleNamespace(
        id=1,
        market_key="HOME",
        is_real_book_quote=True,
        is_derived_quote=False,
        derivation_method=None,
        quota_book=2.0,
        quota_cecchino=2.1,
        prob_book_raw=0.5,
        prob_book_fair=0.48,
        prob_cecchino=0.5,
        edge_pct=10,
        vantaggio_prob=0.05,
        quote_source_type="bet365_closing",
        won=True,
        profit_1u_real=1.0,
        profit_1u_synthetic=None,
        result_reason="won",
        evaluation_status="won",
    )
    row = svc._build_result_row(
        replay=replay,
        snap=snap,
        market_key="HOME",
        market=real_m,
        item={"status": "available", "score": 70, "class": "Alta", "gate_status": "passed"},
        score_status="exact_replay_ready",
        score_reasons=[],
        formula_sha="sha",
        panel_fields=list(FORMULA_PAYLOAD_ALLOWED_FIELDS),
    )
    assert row["score"] == 70
    assert row["profit_1u_real"] is not None
    assert row["profit_1u_synthetic"] is None

    der_m = SimpleNamespace(
        id=2,
        market_key="ONE_X",
        is_real_book_quote=False,
        is_derived_quote=True,
        derivation_method="normalized_fair",
        quota_book=1.5,
        quota_cecchino=1.6,
        prob_book_raw=0.6,
        prob_book_fair=0.58,
        prob_cecchino=0.6,
        edge_pct=5,
        vantaggio_prob=0.02,
        quote_source_type="derived_from_bet365_1x2_closing",
        won=False,
        profit_1u_real=None,
        profit_1u_synthetic=-1.0,
        result_reason="lost",
        evaluation_status="lost",
    )
    row2 = svc._build_result_row(
        replay=replay,
        snap=snap,
        market_key="ONE_X",
        market=der_m,
        item={"status": "available", "score": 40, "class": "Media", "gate_status": "passed"},
        score_status="ready_with_warning",
        score_reasons=["derived_quote_diagnostic_only"],
        formula_sha="sha",
        panel_fields=list(FORMULA_PAYLOAD_ALLOWED_FIELDS),
    )
    assert row2["profit_1u_synthetic"] is not None
    assert row2["profit_1u_real"] is None


def test_unavailable_source_not_replayable_null_score():
    snap = SimpleNamespace(
        id=1,
        lab_match_id=10,
        competition_name="E0",
        kickoff_at=None,
        chronological_order=1,
        pre_match_payload_sha256="aa",
        pre_match_locked_at=None,
    )
    row = svc._build_result_row(
        replay=_replay_obj(),
        snap=snap,
        market_key="HOME",
        market=None,
        item=None,
        score_status="not_replayable",
        score_reasons=["market_row_missing"],
        formula_sha=None,
        panel_fields=[],
    )
    assert row["calculation_status"] == "source_not_replayable"
    assert row["score"] is None
    assert row["score_class"] is None
    assert "source_not_replayable" in row["reason_codes_json"]


# ---------------------------------------------------------------------------
# Start / cancel / resume service
# ---------------------------------------------------------------------------


def test_start_requires_confirm():
    db = MagicMock()
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.start_purchasability_v3_replay(db, 3, confirmed=False, background=False)
    assert ei.value.code == "confirm_required"
    assert ei.value.status_code == 400


def test_start_run_not_found():
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.start_purchasability_v3_replay(db, 99, confirmed=True, background=False)
    assert ei.value.code == "run_not_found"


@patch.object(svc, "run_purchasability_v3_replay_preflight")
def test_start_preflight_blocked(mock_pf):
    db = MagicMock()
    db.get.return_value = _scan()
    mock_pf.return_value = _ready_preflight(status="blocked", blockers=[{"code": "x", "message": "y"}])
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.start_purchasability_v3_replay(db, 3, confirmed=True, background=False)
    assert ei.value.status_code == 409


@patch.object(svc, "_spawn_worker")
@patch.object(svc, "resolve_code_revision", return_value={"git_commit": "x", "git_commit_source": "t", "revision_status": "resolved"})
@patch.object(svc, "run_purchasability_v3_replay_preflight")
def test_start_new_replay_queued(mock_pf, _rev, mock_spawn):
    db = MagicMock()
    db.get.return_value = _scan()
    mock_pf.return_value = _ready_preflight()
    db.scalars.return_value.first.return_value = None

    created = []

    def add(obj):
        created.append(obj)
        obj.id = 42

    db.add.side_effect = add
    db.refresh.side_effect = lambda o: None

    result = svc.start_purchasability_v3_replay(
        db,
        3,
        confirmed=True,
        expected_formula_version=PURCHASABILITY_V3_FORMULA_VERSION,
        expected_preflight_schema_version=PREFLIGHT_SCHEMA_VERSION,
        expected_integrity_policy_version=INTEGRITY_POLICY_VERSION,
        background=True,
    )
    assert result["status"] == STATUS_QUEUED
    assert result["reused_existing"] is False
    assert created[0].status == STATUS_QUEUED
    mock_spawn.assert_called_once_with(42)
    mock_pf.assert_called_once()
    assert mock_pf.call_args.kwargs.get("include_probe") is False or (
        len(mock_pf.call_args.args) >= 2 and mock_pf.call_args.kwargs.get("include_probe", False) is False
    )


@patch.object(svc, "run_purchasability_v3_replay_preflight")
def test_start_reuses_completed(mock_pf):
    db = MagicMock()
    db.get.return_value = _scan()
    mock_pf.return_value = _ready_preflight()
    existing = _replay_obj(status=STATUS_COMPLETED, id=7)
    db.scalars.return_value.first.return_value = existing
    result = svc.start_purchasability_v3_replay(db, 3, confirmed=True, background=True)
    assert result["reused_existing"] is True
    assert result["id"] == 7
    db.add.assert_not_called()


@patch.object(svc, "_spawn_worker")
@patch.object(svc, "run_purchasability_v3_replay_preflight")
def test_start_reuses_running(mock_pf, mock_spawn):
    db = MagicMock()
    db.get.return_value = _scan()
    mock_pf.return_value = _ready_preflight()
    existing = _replay_obj(status=STATUS_RUNNING, id=8)
    db.scalars.return_value.first.return_value = existing
    result = svc.start_purchasability_v3_replay(db, 3, confirmed=True, background=True)
    assert result["reused_existing"] is True
    mock_spawn.assert_called_once_with(8)


def test_cancel_sets_flag():
    db = MagicMock()
    run = _replay_obj(status=STATUS_RUNNING)
    db.get.return_value = run
    out = svc.cancel_purchasability_v3_replay(db, 10)
    assert run.cancel_requested is True
    assert run.status == "cancel_requested"
    assert out["cancel_requested"] is True


@patch.object(svc, "_spawn_worker")
def test_resume_from_failed(mock_spawn):
    db = MagicMock()
    run = _replay_obj(status=STATUS_FAILED, resume_count=0, attempt_count=1)
    db.get.return_value = run
    db.scalars.return_value.first.return_value = None
    out = svc.resume_purchasability_v3_replay(db, 10, background=True)
    assert run.status == STATUS_QUEUED
    assert run.resume_count == 1
    assert run.attempt_count == 2
    mock_spawn.assert_called_once()
    assert out["status"] == STATUS_QUEUED


def test_resume_blocks_completed():
    db = MagicMock()
    db.get.return_value = _replay_obj(status=STATUS_COMPLETED)
    with pytest.raises(CecchinoLabImportError) as ei:
        svc.resume_purchasability_v3_replay(db, 10)
    assert ei.value.code == "replay_already_completed"


# ---------------------------------------------------------------------------
# Models / migration metadata
# ---------------------------------------------------------------------------


def test_model_unique_and_indexes():
    run_args = CecchinoLabPurchasabilityV3ReplayRun.__table_args__
    res_args = CecchinoLabPurchasabilityV3ReplayResult.__table_args__
    run_names = {getattr(a, "name", None) for a in run_args}
    res_names = {getattr(a, "name", None) for a in res_args}
    assert "uq_cecchino_lab_p3_replay_runs_idempotency" in run_names
    assert "uq_cecchino_lab_p3_replay_res_run_snap_mkt" in res_names
    assert "ix_cecchino_lab_p3_replay_runs_status" in run_names
    assert "ix_cecchino_lab_p3_replay_res_market_key" in res_names
    assert CecchinoLabPurchasabilityV3ReplayRun.__tablename__ == (
        "cecchino_lab_purchasability_v3_replay_runs"
    )
    assert CecchinoLabPurchasabilityV3ReplayResult.__tablename__ == (
        "cecchino_lab_purchasability_v3_replay_results"
    )


def test_fk_ondelete_policies():
    run_fk = list(CecchinoLabPurchasabilityV3ReplayRun.__table__.foreign_keys)[0]
    assert run_fk.ondelete == "RESTRICT"
    result_fks = {fk.column.table.name: fk.ondelete for fk in CecchinoLabPurchasabilityV3ReplayResult.__table__.foreign_keys}
    # FK targets
    targets = {
        fk.column.table.name: fk.ondelete
        for fk in CecchinoLabPurchasabilityV3ReplayResult.__table__.foreign_keys
    }
    assert targets.get("cecchino_lab_purchasability_v3_replay_runs") == "CASCADE"
    assert targets.get("cecchino_lab_historical_scan_runs") == "RESTRICT"


def test_migration_only_new_tables():
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260802120000_cecchino_lab_purchasability_v3_replay_tables.py"
    )
    text = path.read_text(encoding="utf-8")
    assert 'create_table(\n        "cecchino_lab_purchasability_v3_replay_runs"' in text
    assert 'create_table(\n        "cecchino_lab_purchasability_v3_replay_results"' in text
    assert 'op.drop_table("cecchino_lab_purchasability_v3_replay_results")' in text
    assert "op.add_column" not in text
    assert "op.alter_column" not in text
    assert "20260727180000" in text
    assert 'revision: str = "20260802120000"' in text


# ---------------------------------------------------------------------------
# Route handlers (no TestClient — evita hang lifespan su Windows)
# ---------------------------------------------------------------------------


@patch.object(cecchino_lab, "start_purchasability_v3_replay")
def test_route_start_passes_versions(mock_start):
    mock_start.return_value = {"id": 1, "status": "queued", "reused_existing": False}
    db = MagicMock()
    body = {
        "confirmed": True,
        "expected_formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
        "expected_preflight_schema_version": PREFLIGHT_SCHEMA_VERSION,
        "expected_integrity_policy_version": INTEGRITY_POLICY_VERSION,
    }
    res = cecchino_lab.purchasability_v3_replay_start(3, body, db)
    assert res.status_code == 202
    kwargs = mock_start.call_args.kwargs
    assert kwargs["confirmed"] is True
    assert kwargs["expected_formula_version"] == PURCHASABILITY_V3_FORMULA_VERSION
    assert kwargs["expected_preflight_schema_version"] == PREFLIGHT_SCHEMA_VERSION
    assert kwargs["expected_integrity_policy_version"] == INTEGRITY_POLICY_VERSION


@patch.object(cecchino_lab, "start_purchasability_v3_replay")
def test_route_start_confirm_false_maps_400(mock_start):
    mock_start.side_effect = CecchinoLabImportError(
        "confirm_required", "no", status_code=400
    )
    res = cecchino_lab.purchasability_v3_replay_start(3, {"confirmed": False}, MagicMock())
    assert res.status_code == 400
    assert res.body
    # confirmed passato come False → service riceve confirmed=False
    assert mock_start.call_args.kwargs["confirmed"] is False


@patch.object(cecchino_lab, "get_purchasability_v3_replay")
def test_route_status(mock_get):
    mock_get.return_value = {"id": 1, "status": "running", "can_cancel": True}
    res = cecchino_lab.purchasability_v3_replay_status(1, MagicMock())
    assert res.status_code == 200


@patch.object(cecchino_lab, "list_purchasability_v3_replays")
def test_route_list(mock_list):
    mock_list.return_value = [{"id": 1}]
    res = cecchino_lab.purchasability_v3_replay_list(3, MagicMock())
    assert res.status_code == 200


@patch.object(cecchino_lab, "cancel_purchasability_v3_replay")
def test_route_cancel(mock_cancel):
    mock_cancel.return_value = {"id": 1, "status": "cancel_requested"}
    res = cecchino_lab.purchasability_v3_replay_cancel(1, MagicMock())
    assert res.status_code == 200


@patch.object(cecchino_lab, "resume_purchasability_v3_replay")
def test_route_resume(mock_resume):
    mock_resume.return_value = {"id": 1, "status": "queued"}
    res = cecchino_lab.purchasability_v3_replay_resume(1, MagicMock())
    assert res.status_code == 202


def test_route_paths_registered():
    admin_paths = {getattr(r, "path", None) for r in cecchino_lab.admin_router.routes}
    pub_paths = {getattr(r, "path", None) for r in cecchino_lab.router.routes}
    assert any(
        p and p.endswith("/historical-scans/{run_id}/purchasability-v3-replays")
        for p in admin_paths
    )
    assert any(
        p and p.endswith("/purchasability-v3-replays/{replay_id}/cancel") for p in admin_paths
    )
    assert any(
        p and p.endswith("/purchasability-v3-replays/{replay_id}/resume") for p in admin_paths
    )
    assert any(
        p and p.endswith("/purchasability-v3-replays/{replay_id}") for p in pub_paths
    )
    assert any(
        p and p.endswith("/historical-scans/{run_id}/purchasability-v3-replays")
        for p in pub_paths
    )


# ---------------------------------------------------------------------------
# Isolation / engine unchanged markers
# ---------------------------------------------------------------------------


def test_v3_markets_eight():
    assert len(V3_MARKET_ORDER) == 8


def test_worker_uses_session_local_pattern():
    import inspect

    src = inspect.getsource(svc.execute_purchasability_v3_replay)
    assert "SessionLocal()" in src
    assert "db.close()" in src
    assert "REPLAY_BATCH_SNAPSHOTS" in src
    assert "heartbeat_at" in src


def test_streaming_constants_and_lean_imports():
    assert svc.REPLAY_BATCH_SNAPSHOTS == 100
    from app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight import (
        MARKET_STREAM_COLS,
        SNAPSHOT_LEAN_COLS,
        HEAVY_JSON_FIELD_NAMES,
    )

    lean_names = {c.key for c in SNAPSHOT_LEAN_COLS}
    assert "input_snapshot_json" not in lean_names
    assert "result_json" not in lean_names
    market_names = {c.key for c in MARKET_STREAM_COLS}
    assert "signal_sources_json" not in market_names
    assert "won" in market_names  # loaded but not forwarded to formula
    for heavy in ("result_json", "input_snapshot_json", "settlement_summary_json"):
        assert heavy in HEAVY_JSON_FIELD_NAMES


def test_process_snapshot_one_formula_call_and_max_eight():
    snap = SimpleNamespace(
        id=1,
        lab_match_id=10,
        competition_name="E0",
        kickoff_at=datetime.now(timezone.utc),
        chronological_order=1,
        pre_match_payload_sha256="a" * 64,
        pre_match_locked_at=datetime.now(timezone.utc),
        historical_eligibility_status="eligible_core",
    )

    def _m(mk, mid):
        return SimpleNamespace(
            id=mid,
            market_key=mk,
            is_real_book_quote=True,
            is_derived_quote=False,
            derivation_method=None,
            quota_book=2.0,
            quota_cecchino=2.2,
            prob_book_raw=0.5,
            prob_book_fair=0.45,
            prob_cecchino=0.5,
            edge_pct=10.0,
            vantaggio_prob=0.05,
            quote_source_type="bet365_closing",
            won=True,
            profit_1u_real=1.0,
            profit_1u_synthetic=None,
            result_reason="won",
            evaluation_status="won",
        )

    markets = [_m(mk, i + 1) for i, mk in enumerate(V3_MARKET_ORDER)]
    items = [
        {
            "market_key": mk,
            "status": "available",
            "score": 50,
            "class": "Media",
            "gate_status": "passed",
            "gate_reason_codes": [],
            "reason_codes": [],
            "warnings": [],
        }
        for mk in V3_MARKET_ORDER
    ]
    counter = [0]
    with patch.object(svc, "calculate_purchasability_v3_batch") as mock_batch, patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight.evaluate_historical_integrity_policy",
        return_value={"integrity_gate": "ok", "reasons": []},
    ):
        mock_batch.return_value = {"items": items}
        rows = svc._process_snapshot(
            replay=_replay_obj(),
            snap=snap,
            markets=markets,
            formula_call_counter=counter,
        )
    assert counter[0] == 1
    assert len(rows) == 8
    assert mock_batch.call_count == 1
    rows_in = mock_batch.call_args.kwargs["kpi_panel"]["rows"]
    assert len(rows_in) <= 8
    for r in rows_in:
        assert "won" not in r
        assert "profit_1u_real" not in r


def test_completed_with_warnings_logic():
    run = _replay_obj(
        results_persisted=64,
        evaluations_total=64,
        scored_count=40,
        gate_failed_count=20,
        unavailable_count=4,
        not_applicable_count=0,
        error_count=0,
        unclassified_count=0,
        real_quote_count=40,
        derived_quote_count=20,
        unavailable_quote_count=4,
        warning_source_count=20,
        non_replayable_source_count=4,
    )
    ok, _ = svc._final_invariants_ok(run)
    assert ok
    has_warnings = (
        int(run.derived_quote_count or 0) > 0
        or int(run.unavailable_quote_count or 0) > 0
        or int(run.non_replayable_source_count or 0) > 0
        or int(run.warning_source_count or 0) > 0
    )
    assert has_warnings
    assert STATUS_COMPLETED_WITH_WARNINGS == "completed_with_warnings"
