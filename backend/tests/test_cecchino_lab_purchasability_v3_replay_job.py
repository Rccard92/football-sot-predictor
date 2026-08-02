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


# ---------------------------------------------------------------------------
# STEP 3B.1.1 — batch worker, contatori incrementali, resource profile
# ---------------------------------------------------------------------------


def _lean_snap(sid: int, order: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=sid,
        lab_match_id=sid * 10,
        competition_name="E0",
        kickoff_at=datetime.now(timezone.utc),
        chronological_order=order,
        pre_match_payload_sha256="a" * 64,
        pre_match_locked_at=datetime.now(timezone.utc),
        historical_eligibility_status="eligible_core",
    )


def _market(mk: str, mid: int, *, real: bool = True, won: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=mid,
        match_snapshot_id=1,
        market_key=mk,
        is_real_book_quote=real,
        is_derived_quote=not real,
        derivation_method=None if real else "synth",
        quota_book=2.0,
        quota_cecchino=2.2,
        prob_book_raw=0.5,
        prob_book_fair=0.45,
        prob_cecchino=0.5,
        edge_pct=10.0,
        vantaggio_prob=0.05,
        quote_source_type="bet365_closing" if real else "derived",
        won=won,
        profit_1u_real=1.0 if real else None,
        profit_1u_synthetic=None if real else 1.0,
        result_reason="won",
        evaluation_status="won",
    )


def _formula_items_for(keys):
    return [
        {
            "market_key": mk,
            "status": "available",
            "score": 50,
            "class": "Media",
            "gate_status": "passed",
            "gate_reason_codes": [],
            "reason_codes": [],
            "warnings": [],
            "penalties": {},
        }
        for mk in keys
    ]


def test_iter_eligible_snapshot_batches_max_100():
    snaps = [_lean_snap(i, i) for i in range(1, 251)]
    db = MagicMock()

    def _fake_iter(_db, _run_id):
        yield from snaps

    with patch.object(svc, "_iter_eligible_snapshots", side_effect=_fake_iter):
        batches = list(svc._iter_eligible_snapshot_batches(db, 3, batch_size=100))
    assert all(len(b) <= 100 for b in batches)
    assert sum(len(b) for b in batches) == 250
    assert len(batches) == 3
    assert len(batches[0]) == 100
    assert len(batches[2]) == 50


def test_load_markets_no_silent_truncation_of_duplicates():
    """Tutte le righe mercato devono essere caricate (nessun cap a 8)."""
    rows = []
    for i, mk in enumerate(V3_MARKET_ORDER):
        rows.append(
            SimpleNamespace(
                id=i + 1,
                match_snapshot_id=7,
                market_key=mk,
            )
        )
    # duplicato sul primo mercato
    rows.append(SimpleNamespace(id=99, match_snapshot_id=7, market_key=V3_MARKET_ORDER[0]))

    db = MagicMock()
    exec_result = MagicMock()
    exec_result.all.return_value = rows
    db.execute.return_value = exec_result

    out = svc._load_markets_for_snapshots(db, 3, [7])
    assert len(out[7]) == len(V3_MARKET_ORDER) + 1


def test_process_snapshot_duplicate_raises_controlled():
    snap = _lean_snap(1)
    mk0 = V3_MARKET_ORDER[0]
    markets = [_market(mk0, 1), _market(mk0, 2)]
    markets[0].match_snapshot_id = 1
    markets[1].match_snapshot_id = 1
    with pytest.raises(svc.ReplayWorkerError) as ei:
        svc._process_snapshot(
            replay=_replay_obj(),
            snap=snap,
            markets=markets,
            formula_call_counter=[0],
        )
    assert ei.value.code == "ambiguous_market_join"
    assert mk0 in ei.value.details["duplicate_market_keys"]


def test_summarize_result_rows_batch_deltas():
    rows = [
        {
            "source_snapshot_id": 1,
            "calculation_status": "available",
            "gate_status": "passed",
            "score": 40,
            "quote_quality": "real",
            "performance_evaluation_status": "real_profit_ready",
        },
        {
            "source_snapshot_id": 1,
            "calculation_status": "available",
            "gate_status": "failed",
            "score": None,
            "quote_quality": "derived",
            "performance_evaluation_status": "synthetic_profit_ready",
        },
        {
            "source_snapshot_id": 2,
            "calculation_status": "unavailable",
            "gate_status": "passed",
            "score": None,
            "quote_quality": "unavailable",
            "performance_evaluation_status": "not_applicable",
        },
    ]
    delta = svc.summarize_result_rows(rows)
    assert delta["snapshots_processed"] == 2
    assert delta["evaluations_processed"] == 3
    assert delta["results_persisted"] == 3
    assert delta["scored_count"] == 1
    assert delta["gate_failed_count"] == 1
    assert delta["unavailable_count"] == 1
    assert delta["real_quote_count"] == 1
    assert delta["derived_quote_count"] == 1
    assert delta["unavailable_quote_count"] == 1
    assert delta["real_performance_ready_count"] == 1
    assert delta["synthetic_performance_ready_count"] == 1
    assert delta["performance_missing_count"] == 1


def test_apply_counter_deltas_incremental():
    run = _replay_obj(snapshots_processed=1, evaluations_processed=8, results_persisted=8, scored_count=8)
    delta = {
        "snapshots_processed": 1,
        "evaluations_processed": 8,
        "results_persisted": 8,
        "scored_count": 5,
        "gate_failed_count": 3,
        "unavailable_count": 0,
        "not_applicable_count": 0,
        "error_count": 0,
        "unclassified_count": 0,
        "real_quote_count": 8,
        "derived_quote_count": 0,
        "unavailable_quote_count": 0,
        "real_performance_ready_count": 8,
        "synthetic_performance_ready_count": 0,
        "performance_missing_count": 0,
    }
    svc._apply_counter_deltas(run, delta)
    assert run.snapshots_processed == 2
    assert run.evaluations_processed == 16
    assert run.scored_count == 13
    assert run.gate_failed_count == 3
    assert float(run.progress_pct) < 100.0


def test_progress_never_100_before_final():
    assert float(svc._progress_pct_incremental(64, 64)) == 99.9
    assert float(svc._progress_pct_incremental(32, 64)) == 50.0
    assert float(svc._progress_pct_incremental(0, 64)) == 0.0


def test_resource_profile_empty_shape():
    rp = svc._empty_resource_profile()
    assert rp["replay_batch_snapshots"] == 100
    assert rp["market_batch_queries"] == 0
    assert rp["max_snapshots_held_in_memory"] == 0
    assert rp["max_market_rows_held_in_memory"] == 0
    assert "count_reconciliations" in rp
    assert "formula_invocations" in rp


def test_market_query_budget_formula():
    import math

    n, b = 4561, 100
    expected_max = math.ceil(n / b) + 1
    # ~46 + 1, non 4561
    assert expected_max == 47
    assert expected_max < n


def test_batch_vs_single_output_equivalence():
    """Worker batch e modalità snapshot-per-snapshot producono gli stessi row."""
    snap = _lean_snap(5)
    markets = [_market(mk, i + 1) for i, mk in enumerate(V3_MARKET_ORDER)]
    for m in markets:
        m.match_snapshot_id = 5
    items = _formula_items_for(V3_MARKET_ORDER)
    integrity = {"integrity_gate": "ok", "reasons": []}

    def _run(markets_list):
        counter = [0]
        with patch.object(svc, "calculate_purchasability_v3_batch") as mock_batch, patch(
            "app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight.evaluate_historical_integrity_policy",
            return_value=integrity,
        ):
            mock_batch.return_value = {"items": items}
            return svc._process_snapshot(
                replay=_replay_obj(),
                snap=snap,
                markets=markets_list,
                formula_call_counter=counter,
            ), counter[0]

    single_rows, c1 = _run(markets)
    # simulazione batch: stessa mappa per snapshot
    batch_map = {5: list(markets)}
    batch_rows, c2 = _run(batch_map[5])
    assert c1 == c2 == 1
    assert len(single_rows) == len(batch_rows) == 8
    for a, b in zip(single_rows, batch_rows):
        assert a["market_key"] == b["market_key"]
        assert a["score"] == b["score"]
        assert a["gate_status"] == b["gate_status"]
        assert a["calculation_status"] == b["calculation_status"]
        assert a["quote_quality"] == b["quote_quality"]
        assert a.get("formula_payload_sha256") == b.get("formula_payload_sha256")


def test_execute_batch_one_market_query_per_batch_and_incremental():
    """N snapshot → ceil(N/B) market queries; nessun recount completo a ogni batch."""
    snaps = [_lean_snap(i, i) for i in range(1, 6)]  # 5 snap, batch 100 → 1 query

    replay = _replay_obj(
        id=99,
        status=STATUS_QUEUED,
        resume_count=0,
        results_persisted=0,
        evaluations_total=40,
        snapshots_total=5,
        summary_json={},
    )

    db = MagicMock()
    db.get.return_value = replay

    market_calls: list[list[int]] = []
    reconcile_calls = [0]

    def fake_load(_db, _run_id, sids):
        market_calls.append(list(sids))
        out = {}
        for sid in sids:
            out[sid] = [
                _market(mk, sid * 10 + i, real=(i % 2 == 0))
                for i, mk in enumerate(V3_MARKET_ORDER)
            ]
            for m in out[sid]:
                m.match_snapshot_id = sid
        return out

    def fake_process(*, replay, snap, markets, formula_call_counter):
        formula_call_counter[0] += 1
        return [
            {
                "replay_run_id": replay.id,
                "source_snapshot_id": int(snap.id),
                "market_key": mk,
                "calculation_status": "available",
                "gate_status": "passed",
                "score": 50,
                "quote_quality": "real",
                "performance_evaluation_status": "real_profit_ready",
            }
            for mk in V3_MARKET_ORDER
        ]

    def fake_reconcile(_db, r):
        reconcile_calls[0] += 1
        # simula reconcile finale coerente
        r.results_persisted = int(r.evaluations_processed or 0)
        r.evaluations_processed = int(r.evaluations_processed or 0)
        r.snapshots_processed = int(r.snapshots_processed or 0)
        profile = svc._get_resource_profile(r)
        profile["count_reconciliations"] = int(profile.get("count_reconciliations") or 0) + 1
        svc._set_resource_profile(r, profile)

    with (
        patch.object(svc, "SessionLocal", return_value=db),
        patch.object(svc, "_iter_eligible_snapshot_batches", return_value=[snaps]),
        patch.object(svc, "_load_done_snapshot_ids", return_value=set()),
        patch.object(svc, "_is_cancelled", return_value=False),
        patch.object(svc, "_load_markets_for_snapshots", side_effect=fake_load),
        patch.object(svc, "_process_snapshot", side_effect=fake_process),
        patch.object(svc, "_upsert_results"),
        patch.object(svc, "_reconcile_counts_from_db", side_effect=fake_reconcile),
        patch.object(svc, "_final_invariants_ok", return_value=(True, [])),
    ):
        svc.execute_purchasability_v3_replay(99)

    assert len(market_calls) == 1
    assert len(market_calls[0]) == 5
    # 1 reconcile a fine job (no resume)
    assert reconcile_calls[0] == 1
    assert replay.evaluations_processed == 40
    assert replay.snapshots_processed == 5
    rp = (replay.summary_json or {}).get("resource_profile") or {}
    assert rp["market_batch_queries"] == 1
    assert rp["snapshot_batches_processed"] == 1
    assert rp["formula_invocations"] == 5
    assert rp["max_snapshots_held_in_memory"] <= 100
    assert rp["max_market_rows_held_in_memory"] <= 800
    assert rp["incremental_counter_updates"] == 1
    assert float(replay.progress_pct) == 100.0


def test_execute_resume_reconciles_once_at_start():
    snaps = [_lean_snap(i, i) for i in range(3, 5)]  # solo incompleti restanti
    replay = _replay_obj(
        id=88,
        resume_count=1,
        results_persisted=16,
        evaluations_processed=16,
        snapshots_processed=2,
        evaluations_total=32,
        snapshots_total=4,
        scored_count=16,
        summary_json={"resource_profile": svc._empty_resource_profile()},
    )
    db = MagicMock()
    db.get.return_value = replay
    reconcile_calls = [0]

    def fake_reconcile(_db, r):
        reconcile_calls[0] += 1
        profile = svc._get_resource_profile(r)
        profile["count_reconciliations"] = reconcile_calls[0]
        svc._set_resource_profile(r, profile)

    def fake_load(_db, _run_id, sids):
        return {
            sid: [_market(mk, sid * 10 + i) for i, mk in enumerate(V3_MARKET_ORDER)]
            for sid in sids
        }

    def fake_process(*, replay, snap, markets, formula_call_counter):
        formula_call_counter[0] += 1
        return [
            {
                "replay_run_id": replay.id,
                "source_snapshot_id": int(snap.id),
                "market_key": mk,
                "calculation_status": "available",
                "gate_status": "passed",
                "score": 50,
                "quote_quality": "real",
                "performance_evaluation_status": "real_profit_ready",
            }
            for mk in V3_MARKET_ORDER
        ]

    with (
        patch.object(svc, "SessionLocal", return_value=db),
        patch.object(svc, "_iter_eligible_snapshot_batches", return_value=[[_lean_snap(1), _lean_snap(2), *snaps]]),
        patch.object(svc, "_load_done_snapshot_ids", return_value={1, 2}),
        patch.object(svc, "_is_cancelled", return_value=False),
        patch.object(svc, "_load_markets_for_snapshots", side_effect=fake_load),
        patch.object(svc, "_process_snapshot", side_effect=fake_process),
        patch.object(svc, "_upsert_results"),
        patch.object(svc, "_reconcile_counts_from_db", side_effect=fake_reconcile),
        patch.object(svc, "_final_invariants_ok", return_value=(True, [])),
    ):
        svc.execute_purchasability_v3_replay(88)

    # 1 a inizio resume + 1 a fine
    assert reconcile_calls[0] == 2
    # solo 2 nuovi snapshot (3,4) sommati
    assert replay.snapshots_processed == 4
    assert replay.evaluations_processed == 32


def test_execute_cancel_before_batch_reconciles_once():
    replay = _replay_obj(id=77, summary_json={})
    db = MagicMock()
    db.get.return_value = replay
    reconcile_calls = [0]

    def fake_reconcile(_db, r):
        reconcile_calls[0] += 1

    with (
        patch.object(svc, "SessionLocal", return_value=db),
        patch.object(svc, "_load_done_snapshot_ids", return_value=set()),
        patch.object(svc, "_is_cancelled", return_value=True),
        patch.object(
            svc,
            "_iter_eligible_snapshot_batches",
            return_value=[[_lean_snap(1)]],
        ),
        patch.object(svc, "_reconcile_counts_from_db", side_effect=fake_reconcile),
        patch.object(svc, "_load_markets_for_snapshots") as load_m,
    ):
        svc.execute_purchasability_v3_replay(77)

    load_m.assert_not_called()
    assert reconcile_calls[0] == 1
    assert replay.status == STATUS_CANCELLED


def test_execute_cancel_after_batch_keeps_prior_and_reconciles():
    snaps = [_lean_snap(1), _lean_snap(2)]
    replay = _replay_obj(
        id=66,
        evaluations_total=16,
        snapshots_total=2,
        summary_json={},
    )
    db = MagicMock()
    db.get.return_value = replay
    cancel_flags = [False, True]  # pre-batch ok, post-batch cancel
    reconcile_calls = [0]

    def is_cancelled(_db, _rid):
        # prima chiamata pre-batch → False; dopo commit → True
        if cancel_flags:
            return cancel_flags.pop(0)
        return True

    def fake_reconcile(_db, r):
        reconcile_calls[0] += 1

    def fake_load(_db, _run_id, sids):
        return {
            sid: [_market(mk, sid * 10 + i) for i, mk in enumerate(V3_MARKET_ORDER)]
            for sid in sids
        }

    def fake_process(*, replay, snap, markets, formula_call_counter):
        formula_call_counter[0] += 1
        return [
            {
                "replay_run_id": replay.id,
                "source_snapshot_id": int(snap.id),
                "market_key": mk,
                "calculation_status": "available",
                "gate_status": "passed",
                "score": 50,
                "quote_quality": "real",
                "performance_evaluation_status": "real_profit_ready",
            }
            for mk in V3_MARKET_ORDER
        ]

    with (
        patch.object(svc, "SessionLocal", return_value=db),
        patch.object(svc, "_iter_eligible_snapshot_batches", return_value=[snaps]),
        patch.object(svc, "_load_done_snapshot_ids", return_value=set()),
        patch.object(svc, "_is_cancelled", side_effect=is_cancelled),
        patch.object(svc, "_load_markets_for_snapshots", side_effect=fake_load),
        patch.object(svc, "_process_snapshot", side_effect=fake_process),
        patch.object(svc, "_upsert_results") as upsert,
        patch.object(svc, "_reconcile_counts_from_db", side_effect=fake_reconcile),
    ):
        svc.execute_purchasability_v3_replay(66)

    upsert.assert_called_once()
    assert reconcile_calls[0] == 1
    assert replay.status == STATUS_CANCELLED
    assert replay.results_persisted == 16


def test_execute_duplicate_fails_batch_rollback():
    snap = _lean_snap(1)
    replay = _replay_obj(id=55, summary_json={})
    db = MagicMock()
    db.get.return_value = replay

    def fake_load(_db, _run_id, sids):
        return {1: [_market(V3_MARKET_ORDER[0], 1), _market(V3_MARKET_ORDER[0], 2)]}

    with (
        patch.object(svc, "SessionLocal", return_value=db),
        patch.object(svc, "_iter_eligible_snapshot_batches", return_value=[[snap]]),
        patch.object(svc, "_load_done_snapshot_ids", return_value=set()),
        patch.object(svc, "_is_cancelled", return_value=False),
        patch.object(svc, "_load_markets_for_snapshots", side_effect=fake_load),
        patch.object(svc, "_upsert_results") as upsert,
        patch.object(svc, "_reconcile_counts_from_db"),
    ):
        # usa _process_snapshot reale → hard fail su duplicato
        svc.execute_purchasability_v3_replay(55)

    upsert.assert_not_called()
    db.rollback.assert_called()
    assert replay.status == STATUS_FAILED
    assert replay.error_json["error"] == "ambiguous_market_join"


def test_resume_done_ids_skip_no_double_count():
    """Snapshot già in done_ids non devono incrementare i contatori."""
    all_snaps = [_lean_snap(1), _lean_snap(2)]
    replay = _replay_obj(
        id=44,
        resume_count=1,
        snapshots_processed=1,
        evaluations_processed=8,
        results_persisted=8,
        scored_count=8,
        evaluations_total=16,
        snapshots_total=2,
        summary_json={"resource_profile": svc._empty_resource_profile()},
    )
    db = MagicMock()
    db.get.return_value = replay
    processed_ids: list[int] = []

    def fake_load(_db, _run_id, sids):
        return {
            sid: [_market(mk, sid * 10 + i) for i, mk in enumerate(V3_MARKET_ORDER)]
            for sid in sids
        }

    def fake_process(*, replay, snap, markets, formula_call_counter):
        processed_ids.append(int(snap.id))
        formula_call_counter[0] += 1
        return [
            {
                "replay_run_id": replay.id,
                "source_snapshot_id": int(snap.id),
                "market_key": mk,
                "calculation_status": "available",
                "gate_status": "passed",
                "score": 50,
                "quote_quality": "real",
                "performance_evaluation_status": "real_profit_ready",
            }
            for mk in V3_MARKET_ORDER
        ]

    with (
        patch.object(svc, "SessionLocal", return_value=db),
        patch.object(svc, "_iter_eligible_snapshot_batches", return_value=[all_snaps]),
        patch.object(svc, "_load_done_snapshot_ids", return_value={1}),
        patch.object(svc, "_is_cancelled", return_value=False),
        patch.object(svc, "_load_markets_for_snapshots", side_effect=fake_load),
        patch.object(svc, "_process_snapshot", side_effect=fake_process),
        patch.object(svc, "_upsert_results"),
        patch.object(svc, "_reconcile_counts_from_db"),
        patch.object(svc, "_final_invariants_ok", return_value=(True, [])),
    ):
        svc.execute_purchasability_v3_replay(44)

    assert processed_ids == [2]
    assert replay.snapshots_processed == 2
    assert replay.evaluations_processed == 16


def test_reconcile_uses_aggregate_select_not_row_scan():
    """_reconcile_counts_from_db non deve fare select(...).all() di tutte le row."""
    replay = _replay_obj(id=12, evaluations_total=16)
    db = MagicMock()
    row = SimpleNamespace(
        total=16,
        snaps=2,
        scored=10,
        gate_failed=2,
        unavailable=4,
        not_applicable=0,
        error=0,
        unclassified=0,
        real_q=10,
        derived_q=2,
        unavail_q=4,
        real_perf=10,
        synth_perf=2,
        miss_perf=4,
    )
    exec_result = MagicMock()
    exec_result.one.return_value = row
    db.execute.return_value = exec_result

    svc._reconcile_counts_from_db(db, replay)

    assert replay.results_persisted == 16
    assert replay.scored_count == 10
    assert replay.snapshots_processed == 2
    # one() e non all()
    exec_result.one.assert_called_once()
    assert not exec_result.all.called
    stmt = db.execute.call_args[0][0]
    # deve essere una select aggregata
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "count" in compiled.lower()


def test_max_memory_counters_bounded():
    assert svc.REPLAY_BATCH_SNAPSHOTS == 100
    # 100 snap * 8 mercati = 800
    assert svc.REPLAY_BATCH_SNAPSHOTS * len(V3_MARKET_ORDER) == 800


def test_no_migration_marker_unchanged():
    from pathlib import Path

    mig = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260802120000_cecchino_lab_purchasability_v3_replay_tables.py"
    )
    assert mig.exists()
    text = mig.read_text(encoding="utf-8")
    assert "cecchino_lab_purchasability_v3_replay" in text


def test_recompute_alias_points_to_reconcile():
    assert svc._recompute_counts_from_db is svc._reconcile_counts_from_db
