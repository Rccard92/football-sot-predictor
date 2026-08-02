"""Job persistente di replay Acquistabilità V3 isolato (STEP 3B.1 / 3B.1.1).

Non modifica Run storico / snapshot / MarketResult.
Invoca la formula V3 in sola lettura.
Worker batch: 1 query mercati per gruppo di snapshot, contatori incrementali.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Iterator

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_lab_historical_market_result import (
    CecchinoLabHistoricalMarketResult,
)
from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.models.cecchino_lab_purchasability_v3_replay_result import (
    CecchinoLabPurchasabilityV3ReplayResult,
)
from app.models.cecchino_lab_purchasability_v3_replay_run import (
    ACTIVE_STATUSES,
    COMPLETED_STATUSES,
    RESUMABLE_STATUSES,
    STATUS_CANCEL_REQUESTED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    CecchinoLabPurchasabilityV3ReplayRun,
)
from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_AUDIT_VERSION,
    PURCHASABILITY_V3_CANDIDATE_VERSION,
    PURCHASABILITY_V3_FORMULA_VERSION,
)
from app.services.cecchino.cecchino_purchasability_v3_candidate import (
    calculate_purchasability_v3_batch,
)
from app.services.cecchino.cecchino_purchasability_v3_opposition import market_family_for
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight import (
    FORBIDDEN_FORMULA_FIELDS,
    FORMULA_PAYLOAD_ALLOWED_FIELDS,
    INTEGRITY_POLICY_VERSION,
    MARKET_STREAM_COLS,
    PREFLIGHT_SCHEMA_VERSION,
    SNAPSHOT_LEAN_COLS,
    V3_MARKET_ORDER,
    build_adapter_panel_row,
    classify_performance,
    classify_quote_quality,
    classify_score_replay,
    map_score_status_to_workload_key,
    run_purchasability_v3_replay_preflight,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

logger = logging.getLogger(__name__)

REPLAY_SCHEMA_VERSION = "cecchino_lab_purchasability_v3_replay_v1"
REPLAY_ENGINE_VERSION = "cecchino_lab_purchasability_v3_replay_engine_v1"
REPLAY_BATCH_SNAPSHOTS = 100
REPLAY_HEARTBEAT_SECONDS = 5
REPLAY_STALE_HEARTBEAT_SECONDS = 120

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}


class ReplayWorkerError(Exception):
    """Errore strutturale del worker (formula mismatch, leakage, …)."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_ns(row: Any) -> SimpleNamespace:
    if isinstance(row, SimpleNamespace):
        return row
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return SimpleNamespace(**dict(mapping))
    if hasattr(row, "_asdict"):
        return SimpleNamespace(**row._asdict())
    return SimpleNamespace(**{c: getattr(row, c) for c in row.keys()})  # type: ignore[attr-defined]


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def build_idempotency_key(
    *,
    source_scan_run_id: int,
    source_scan_version: str | None,
    source_scan_git_commit: str | None,
    formula_version: str,
    replay_schema_version: str,
    integrity_policy_version: str,
) -> str:
    raw = "|".join(
        [
            str(int(source_scan_run_id)),
            str(source_scan_version or ""),
            str(source_scan_git_commit or ""),
            str(formula_version),
            str(replay_schema_version),
            str(integrity_policy_version),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compact_preflight_snapshot(preflight: dict[str, Any]) -> dict[str, Any]:
    """Riepilogo compatto: niente issue_examples / liste lunghe."""
    wl = preflight.get("workload") or {}
    si = preflight.get("source_integrity") or {}
    qq = preflight.get("quote_quality") or {}
    formula = preflight.get("formula") or {}
    run = preflight.get("run") or {}
    anti = preflight.get("anti_leakage") or {}
    return {
        "generated_at": preflight.get("generated_at"),
        "status": preflight.get("status"),
        "schema_version": preflight.get("schema_version"),
        "integrity_policy_version": preflight.get("integrity_policy_version"),
        "versions": {
            "candidate_version": formula.get("candidate_version"),
            "formula_version": formula.get("formula_version"),
            "audit_version": formula.get("audit_version"),
            "preflight_schema_version": preflight.get("schema_version"),
            "integrity_policy_version": preflight.get("integrity_policy_version"),
            "scan_version": run.get("scan_version"),
            "source_git_commit": run.get("source_git_commit"),
        },
        "counts": {
            "snapshots_total": (preflight.get("source_integrity") or {}).get("snapshots_total"),
            "snapshots_eligible_core": si.get("snapshots_eligible_core"),
            "theoretical_evaluations": wl.get("theoretical_evaluations"),
            "classified_evaluations_total": wl.get("classified_evaluations_total"),
            "unclassified_evaluations": wl.get("unclassified_evaluations"),
            "exact_replay_ready": wl.get("exact_replay_ready"),
            "ready_with_warning": wl.get("ready_with_warning"),
            "gate_only_ready": wl.get("gate_only_ready"),
            "not_replayable": wl.get("not_replayable"),
            "invalid_integrity": wl.get("invalid_integrity"),
            "ambiguous_market_join": wl.get("ambiguous_market_join"),
            "real_quotes": qq.get("real"),
            "derived_quotes": qq.get("derived"),
            "unavailable_quotes": qq.get("unavailable"),
            "inconsistent_quotes": qq.get("inconsistent"),
        },
        "integrity": {
            "with_payload_hash": si.get("with_payload_hash") or si.get("with_pre_match_hash"),
            "with_historical_freeze_lock": si.get("with_historical_freeze_lock")
            or si.get("with_pre_match_lock"),
            "integrity_mode_dominant": si.get("integrity_mode_dominant"),
            "score_performance_phase_separation_verified": si.get(
                "score_performance_phase_separation_verified"
            ),
            "formula_input_whitelist_verified": anti.get("formula_input_whitelist_verified"),
            "post_match_fields_excluded": anti.get("post_match_fields_excluded"),
        },
        "blockers": list(preflight.get("blockers") or []),
        "warnings": list(preflight.get("warnings") or [])[:50],
    }


def validate_preflight_for_start(
    preflight: dict[str, Any],
    *,
    expected_formula_version: str | None,
    expected_preflight_schema_version: str | None,
    expected_integrity_policy_version: str | None,
) -> None:
    status = str(preflight.get("status") or "")
    if status not in ("ready", "ready_with_warnings"):
        raise CecchinoLabImportError(
            "preflight_blocked",
            f"Preflight non avviabile: status={status}",
            status_code=409,
            details={"status": status, "blockers": preflight.get("blockers")},
        )

    wl = preflight.get("workload") or {}
    theoretical = int(wl.get("theoretical_evaluations") or 0)
    classified = int(
        wl.get("classified_evaluations_total")
        if wl.get("classified_evaluations_total") is not None
        else (
            int(wl.get("exact_replay_ready") or 0)
            + int(wl.get("ready_with_warning") or 0)
            + int(wl.get("gate_only_ready") or 0)
            + int(wl.get("not_replayable") or 0)
            + int(wl.get("invalid_integrity") or 0)
            + int(wl.get("ambiguous_market_join") or 0)
        )
    )
    unclassified = int(
        wl.get("unclassified_evaluations")
        if wl.get("unclassified_evaluations") is not None
        else max(0, theoretical - classified)
    )
    if unclassified != 0 or classified != theoretical:
        raise CecchinoLabImportError(
            "preflight_unclassified",
            "Preflight con valutazioni non classificate",
            status_code=409,
            details={
                "unclassified": unclassified,
                "classified": classified,
                "theoretical": theoretical,
            },
        )

    invalid = int(wl.get("invalid_integrity") or 0)
    if invalid != 0:
        raise CecchinoLabImportError(
            "preflight_invalid_integrity",
            "Preflight con invalid integrity",
            status_code=409,
            details={"invalid_integrity": invalid},
        )

    ambiguous = int(wl.get("ambiguous_market_join") or 0)
    if ambiguous != 0:
        raise CecchinoLabImportError(
            "preflight_ambiguous_join",
            "Preflight con join ambigui",
            status_code=409,
            details={"ambiguous_market_join": ambiguous},
        )

    blockers = list(preflight.get("blockers") or [])
    if blockers:
        raise CecchinoLabImportError(
            "preflight_blocked",
            "Preflight con blockers",
            status_code=409,
            details={"blockers": blockers},
        )

    si = preflight.get("source_integrity") or {}
    eligible = int(si.get("snapshots_eligible_core") or 0)
    hash_count = int(si.get("with_payload_hash") or si.get("with_pre_match_hash") or 0)
    lock_count = int(
        si.get("with_historical_freeze_lock") or si.get("with_pre_match_lock") or 0
    )
    if eligible > 0 and (hash_count < eligible or lock_count < eligible):
        raise CecchinoLabImportError(
            "preflight_incomplete_freeze",
            "Hash/lock pre-match incompleti",
            status_code=409,
            details={"eligible": eligible, "hash_count": hash_count, "lock_count": lock_count},
        )

    if si.get("score_performance_phase_separation_verified") is False:
        raise CecchinoLabImportError(
            "preflight_phase_separation",
            "Separazione score/performance non verificata",
            status_code=409,
            details={},
        )

    formula = preflight.get("formula") or {}
    actual_formula = str(formula.get("formula_version") or PURCHASABILITY_V3_FORMULA_VERSION)
    actual_preflight = str(preflight.get("schema_version") or PREFLIGHT_SCHEMA_VERSION)
    actual_integrity = str(
        preflight.get("integrity_policy_version") or INTEGRITY_POLICY_VERSION
    )

    if expected_formula_version and expected_formula_version != actual_formula:
        raise CecchinoLabImportError(
            "version_mismatch",
            "formula_version non corrisponde",
            status_code=409,
            details={"expected": expected_formula_version, "actual": actual_formula},
        )
    if (
        expected_preflight_schema_version
        and expected_preflight_schema_version != actual_preflight
    ):
        raise CecchinoLabImportError(
            "version_mismatch",
            "preflight_schema_version non corrisponde",
            status_code=409,
            details={
                "expected": expected_preflight_schema_version,
                "actual": actual_preflight,
            },
        )
    if (
        expected_integrity_policy_version
        and expected_integrity_policy_version != actual_integrity
    ):
        raise CecchinoLabImportError(
            "version_mismatch",
            "integrity_policy_version non corrisponde",
            status_code=409,
            details={
                "expected": expected_integrity_policy_version,
                "actual": actual_integrity,
            },
        )


def effective_status(run: CecchinoLabPurchasabilityV3ReplayRun) -> str:
    status = str(run.status or "")
    if status in (STATUS_RUNNING, STATUS_CANCEL_REQUESTED, STATUS_QUEUED):
        hb = run.heartbeat_at
        if hb is not None:
            age = (_utcnow() - hb).total_seconds()
            if age > REPLAY_STALE_HEARTBEAT_SECONDS:
                return STATUS_INTERRUPTED
        elif status == STATUS_RUNNING and run.started_at is not None:
            age = (_utcnow() - run.started_at).total_seconds()
            if age > REPLAY_STALE_HEARTBEAT_SECONDS:
                return STATUS_INTERRUPTED
    return status


def can_cancel(run: CecchinoLabPurchasabilityV3ReplayRun) -> bool:
    return effective_status(run) in (STATUS_QUEUED, STATUS_RUNNING)


def can_resume(run: CecchinoLabPurchasabilityV3ReplayRun) -> bool:
    eff = effective_status(run)
    return eff in RESUMABLE_STATUSES or (
        eff == STATUS_INTERRUPTED and str(run.status) in (STATUS_RUNNING, STATUS_CANCEL_REQUESTED, STATUS_QUEUED)
    )


def replay_run_to_dict(
    run: CecchinoLabPurchasabilityV3ReplayRun,
    *,
    reused_existing: bool = False,
) -> dict[str, Any]:
    eff = effective_status(run)
    return {
        "id": int(run.id),
        "source_scan_run_id": int(run.source_scan_run_id),
        "status": str(run.status),
        "effective_status": eff,
        "replay_schema_version": run.replay_schema_version,
        "replay_engine_version": run.replay_engine_version,
        "candidate_version": run.candidate_version,
        "formula_version": run.formula_version,
        "audit_version": run.audit_version,
        "preflight_schema_version": run.preflight_schema_version,
        "integrity_policy_version": run.integrity_policy_version,
        "source_scan_git_commit": run.source_scan_git_commit,
        "runtime_git_commit": run.runtime_git_commit,
        "runtime_git_commit_source": run.runtime_git_commit_source,
        "source_scan_version": run.source_scan_version,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "snapshots_total": int(run.snapshots_total or 0),
        "snapshots_processed": int(run.snapshots_processed or 0),
        "evaluations_total": int(run.evaluations_total or 0),
        "evaluations_processed": int(run.evaluations_processed or 0),
        "results_persisted": int(run.results_persisted or 0),
        "progress_pct": float(run.progress_pct) if run.progress_pct is not None else None,
        "current_snapshot_id": run.current_snapshot_id,
        "current_chronological_order": run.current_chronological_order,
        "current_competition": run.current_competition,
        "scored_count": int(run.scored_count or 0),
        "gate_failed_count": int(run.gate_failed_count or 0),
        "unavailable_count": int(run.unavailable_count or 0),
        "not_applicable_count": int(run.not_applicable_count or 0),
        "error_count": int(run.error_count or 0),
        "unclassified_count": int(run.unclassified_count or 0),
        "exact_source_count": int(run.exact_source_count or 0),
        "warning_source_count": int(run.warning_source_count or 0),
        "non_replayable_source_count": int(run.non_replayable_source_count or 0),
        "real_quote_count": int(run.real_quote_count or 0),
        "derived_quote_count": int(run.derived_quote_count or 0),
        "unavailable_quote_count": int(run.unavailable_quote_count or 0),
        "real_performance_ready_count": int(run.real_performance_ready_count or 0),
        "synthetic_performance_ready_count": int(run.synthetic_performance_ready_count or 0),
        "performance_missing_count": int(run.performance_missing_count or 0),
        "cancel_requested": bool(run.cancel_requested),
        "resume_count": int(run.resume_count or 0),
        "attempt_count": int(run.attempt_count or 0),
        "idempotency_key": run.idempotency_key,
        "preflight_snapshot": run.preflight_snapshot_json,
        "summary": run.summary_json,
        "error": run.error_json,
        "can_cancel": can_cancel(run),
        "can_resume": can_resume(run),
        "reused_existing": reused_existing,
    }


def formula_payload_sha256(panel_rows: list[dict[str, Any]]) -> str:
    payload = {"rows": panel_rows}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assert_panel_whitelist(panel_rows: list[dict[str, Any]]) -> None:
    allowed = set(FORMULA_PAYLOAD_ALLOWED_FIELDS)
    forbidden = set(FORBIDDEN_FORMULA_FIELDS)
    for row in panel_rows:
        keys = set(row.keys())
        bad = keys & forbidden
        if bad:
            raise ReplayWorkerError(
                "forbidden_formula_field_detected",
                f"Campo vietato nel payload formula: {sorted(bad)}",
                details={"forbidden_fields": sorted(bad)},
            )
        unexpected = keys - allowed
        if unexpected:
            raise ReplayWorkerError(
                "forbidden_formula_field_detected",
                f"Campo non whitelist nel payload formula: {sorted(unexpected)}",
                details={"unexpected_fields": sorted(unexpected)},
            )


def validate_formula_items(
    *,
    expected_keys: list[str],
    items: list[dict[str, Any]],
) -> None:
    returned_keys = [str(it.get("market_key") or "") for it in items]
    if len(returned_keys) != len(expected_keys):
        raise ReplayWorkerError(
            "formula_item_mismatch",
            "Numero item formula diverso dalle panel rows attese",
            details={"expected": len(expected_keys), "returned": len(returned_keys)},
        )
    if len(set(returned_keys)) != len(returned_keys):
        raise ReplayWorkerError(
            "formula_item_duplicate",
            "Item formula con market_key duplicata",
            details={"keys": returned_keys},
        )
    unexpected = [k for k in returned_keys if k not in expected_keys]
    if unexpected:
        raise ReplayWorkerError(
            "formula_unexpected_market",
            "Market key inattesa dalla formula",
            details={"unexpected": unexpected, "expected": expected_keys},
        )
    missing = [k for k in expected_keys if k not in returned_keys]
    if missing:
        raise ReplayWorkerError(
            "formula_item_mismatch",
            "Market key attese mancanti dalla formula",
            details={"missing": missing},
        )


def _spawn_worker(replay_id: int) -> None:
    with _lock:
        t_existing = _active_threads.get(replay_id)
        if t_existing and t_existing.is_alive():
            return
        t = threading.Thread(
            target=execute_purchasability_v3_replay,
            args=(replay_id,),
            name=f"cecchino-lab-p3-replay-{replay_id}",
            daemon=True,
        )
        _active_threads[replay_id] = t
        t.start()


def start_purchasability_v3_replay(
    db: Session,
    run_id: int,
    *,
    confirmed: bool,
    expected_formula_version: str | None = None,
    expected_preflight_schema_version: str | None = None,
    expected_integrity_policy_version: str | None = None,
    background: bool = True,
) -> dict[str, Any]:
    if confirmed is not True:
        raise CecchinoLabImportError(
            "confirm_required",
            "Conferma richiesta: confirmed deve essere true",
            status_code=400,
        )

    scan = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not scan:
        raise CecchinoLabImportError("run_not_found", "Run storico non trovato", status_code=404)

    preflight = run_purchasability_v3_replay_preflight(db, run_id, include_probe=False)
    validate_preflight_for_start(
        preflight,
        expected_formula_version=expected_formula_version,
        expected_preflight_schema_version=expected_preflight_schema_version,
        expected_integrity_policy_version=expected_integrity_policy_version,
    )

    formula = preflight.get("formula") or {}
    formula_version = str(formula.get("formula_version") or PURCHASABILITY_V3_FORMULA_VERSION)
    candidate_version = str(
        formula.get("candidate_version") or PURCHASABILITY_V3_CANDIDATE_VERSION
    )
    audit_version = str(formula.get("audit_version") or PURCHASABILITY_V3_AUDIT_VERSION)
    preflight_schema = str(preflight.get("schema_version") or PREFLIGHT_SCHEMA_VERSION)
    integrity_policy = str(
        preflight.get("integrity_policy_version") or INTEGRITY_POLICY_VERSION
    )

    key = build_idempotency_key(
        source_scan_run_id=run_id,
        source_scan_version=scan.scan_version,
        source_scan_git_commit=scan.source_git_commit,
        formula_version=formula_version,
        replay_schema_version=REPLAY_SCHEMA_VERSION,
        integrity_policy_version=integrity_policy,
    )

    existing = db.scalars(
        select(CecchinoLabPurchasabilityV3ReplayRun).where(
            CecchinoLabPurchasabilityV3ReplayRun.idempotency_key == key
        )
    ).first()
    if existing:
        if existing.status in COMPLETED_STATUSES:
            return replay_run_to_dict(existing, reused_existing=True)
        if existing.status in ACTIVE_STATUSES:
            _spawn_worker(int(existing.id))
            return replay_run_to_dict(existing, reused_existing=True)
        # failed/cancelled: non duplicare automaticamente
        return replay_run_to_dict(existing, reused_existing=True)

    si = preflight.get("source_integrity") or {}
    wl = preflight.get("workload") or {}
    qq = preflight.get("quote_quality") or {}
    revision = resolve_code_revision()

    replay = CecchinoLabPurchasabilityV3ReplayRun(
        source_scan_run_id=run_id,
        status=STATUS_QUEUED,
        replay_schema_version=REPLAY_SCHEMA_VERSION,
        replay_engine_version=REPLAY_ENGINE_VERSION,
        candidate_version=candidate_version,
        formula_version=formula_version,
        audit_version=audit_version,
        preflight_schema_version=preflight_schema,
        integrity_policy_version=integrity_policy,
        source_scan_git_commit=scan.source_git_commit,
        runtime_git_commit=revision.get("git_commit"),
        runtime_git_commit_source=revision.get("git_commit_source"),
        source_scan_version=scan.scan_version,
        requested_at=_utcnow(),
        snapshots_total=int(si.get("snapshots_eligible_core") or 0),
        evaluations_total=int(wl.get("theoretical_evaluations") or 0),
        exact_source_count=int(wl.get("exact_replay_ready") or 0),
        warning_source_count=int(wl.get("ready_with_warning") or 0),
        non_replayable_source_count=int(wl.get("not_replayable") or 0),
        real_quote_count=0,
        derived_quote_count=0,
        unavailable_quote_count=0,
        cancel_requested=False,
        resume_count=0,
        attempt_count=1,
        idempotency_key=key,
        preflight_snapshot_json=compact_preflight_snapshot(preflight),
    )
    # quote attese da preflight (conteggi sorgente, aggiornati a fine job)
    replay.summary_json = {
        "preflight_quote_quality": {
            "real": qq.get("real"),
            "derived": qq.get("derived"),
            "unavailable": qq.get("unavailable"),
        }
    }
    db.add(replay)
    db.commit()
    db.refresh(replay)

    if background:
        _spawn_worker(int(replay.id))
    else:
        execute_purchasability_v3_replay(int(replay.id))
        db.refresh(replay)

    return replay_run_to_dict(replay, reused_existing=False)


def get_purchasability_v3_replay(db: Session, replay_id: int) -> dict[str, Any]:
    run = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
    if not run:
        raise CecchinoLabImportError("replay_not_found", "Replay non trovato", status_code=404)
    return replay_run_to_dict(run)


def list_purchasability_v3_replays(db: Session, run_id: int) -> list[dict[str, Any]]:
    scan = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not scan:
        raise CecchinoLabImportError("run_not_found", "Run storico non trovato", status_code=404)
    rows = db.scalars(
        select(CecchinoLabPurchasabilityV3ReplayRun)
        .where(CecchinoLabPurchasabilityV3ReplayRun.source_scan_run_id == run_id)
        .order_by(CecchinoLabPurchasabilityV3ReplayRun.id.desc())
    ).all()
    return [replay_run_to_dict(r) for r in rows]


def cancel_purchasability_v3_replay(db: Session, replay_id: int) -> dict[str, Any]:
    run = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
    if not run:
        raise CecchinoLabImportError("replay_not_found", "Replay non trovato", status_code=404)
    run.cancel_requested = True
    if run.status in (STATUS_QUEUED, STATUS_RUNNING):
        run.status = STATUS_CANCEL_REQUESTED
    db.commit()
    db.refresh(run)
    return replay_run_to_dict(run)


def resume_purchasability_v3_replay(
    db: Session,
    replay_id: int,
    *,
    background: bool = True,
) -> dict[str, Any]:
    run = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
    if not run:
        raise CecchinoLabImportError("replay_not_found", "Replay non trovato", status_code=404)

    eff = effective_status(run)
    if run.status in COMPLETED_STATUSES:
        raise CecchinoLabImportError(
            "replay_already_completed",
            "Replay già completato",
            status_code=400,
        )
    if not (
        run.status in (STATUS_FAILED, STATUS_CANCELLED)
        or eff == STATUS_INTERRUPTED
    ):
        if run.status in ACTIVE_STATUSES and eff != STATUS_INTERRUPTED:
            raise CecchinoLabImportError(
                "replay_still_active",
                "Replay ancora attivo",
                status_code=409,
            )
        if not can_resume(run):
            raise CecchinoLabImportError(
                "replay_not_resumable",
                f"Replay non riprendibile (status={run.status}, effective={eff})",
                status_code=400,
            )

    # Un solo active per stessa idempotency key
    other = db.scalars(
        select(CecchinoLabPurchasabilityV3ReplayRun).where(
            CecchinoLabPurchasabilityV3ReplayRun.idempotency_key == run.idempotency_key,
            CecchinoLabPurchasabilityV3ReplayRun.status.in_(tuple(ACTIVE_STATUSES)),
            CecchinoLabPurchasabilityV3ReplayRun.id != replay_id,
        )
    ).first()
    if other:
        raise CecchinoLabImportError(
            "duplicate_active_replay",
            f"Esiste già un replay attivo (id={other.id})",
            status_code=409,
            details={"active_replay_id": int(other.id)},
        )

    run.cancel_requested = False
    run.status = STATUS_QUEUED
    run.resume_count = int(run.resume_count or 0) + 1
    run.attempt_count = int(run.attempt_count or 0) + 1
    run.error_json = None
    run.completed_at = None
    db.commit()

    if background:
        _spawn_worker(replay_id)
    else:
        execute_purchasability_v3_replay(replay_id)
    db.refresh(run)
    return replay_run_to_dict(run)


def _is_cancelled(db: Session, replay_id: int) -> bool:
    run = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
    if not run:
        return True
    return bool(run.cancel_requested) or run.status in (
        STATUS_CANCELLED,
        STATUS_CANCEL_REQUESTED,
    )


def _load_done_snapshot_ids(db: Session, replay_id: int) -> set[int]:
    """Snapshot con tutte le 8 valutazioni già persistite."""
    rows = db.execute(
        select(
            CecchinoLabPurchasabilityV3ReplayResult.source_snapshot_id,
            func.count(),
        )
        .where(CecchinoLabPurchasabilityV3ReplayResult.replay_run_id == replay_id)
        .group_by(CecchinoLabPurchasabilityV3ReplayResult.source_snapshot_id)
    ).all()
    expected = len(V3_MARKET_ORDER)
    return {int(sid) for sid, cnt in rows if int(cnt) >= expected}


def _iter_eligible_snapshots(db: Session, run_id: int) -> Iterator[SimpleNamespace]:
    stmt = (
        select(*SNAPSHOT_LEAN_COLS)
        .where(
            CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
            CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status == ELIGIBLE_CORE,
        )
        .order_by(
            CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc().nulls_last(),
            CecchinoLabHistoricalMatchSnapshot.chronological_order.asc().nulls_last(),
            CecchinoLabHistoricalMatchSnapshot.id.asc(),
        )
        .execution_options(stream_results=True, yield_per=REPLAY_BATCH_SNAPSHOTS)
    )
    result = db.execute(stmt)
    yield_per = getattr(result, "yield_per", None)
    iterator = yield_per(REPLAY_BATCH_SNAPSHOTS) if callable(yield_per) else iter(result)
    for row in iterator:
        yield _row_to_ns(row)


def _iter_eligible_snapshot_batches(
    db: Session,
    source_run_id: int,
    batch_size: int = REPLAY_BATCH_SNAPSHOTS,
) -> Iterator[list[SimpleNamespace]]:
    """Streaming a batch: massimo ``batch_size`` snapshot lean per gruppo."""
    size = max(1, int(batch_size))
    batch: list[SimpleNamespace] = []
    for snap in _iter_eligible_snapshots(db, source_run_id):
        batch.append(snap)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _load_markets_for_snapshots(
    db: Session, run_id: int, snapshot_ids: list[int]
) -> dict[int, list[SimpleNamespace]]:
    """Carica tutte le righe mercati supportati (nessun troncamento silenzioso)."""
    if not snapshot_ids:
        return {}
    stmt = (
        select(*MARKET_STREAM_COLS)
        .where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.match_snapshot_id.in_(snapshot_ids),
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V3_MARKET_ORDER)),
        )
        .order_by(
            CecchinoLabHistoricalMarketResult.match_snapshot_id.asc(),
            CecchinoLabHistoricalMarketResult.market_key.asc(),
            CecchinoLabHistoricalMarketResult.id.asc(),
        )
    )
    out: dict[int, list[SimpleNamespace]] = {sid: [] for sid in snapshot_ids}
    for row in db.execute(stmt).all():
        ns = _row_to_ns(row)
        sid = int(ns.match_snapshot_id)
        if sid in out:
            out[sid].append(ns)
    return out


def _empty_resource_profile() -> dict[str, Any]:
    return {
        "replay_batch_snapshots": REPLAY_BATCH_SNAPSHOTS,
        "snapshot_batches_processed": 0,
        "market_batch_queries": 0,
        "formula_invocations": 0,
        "max_snapshots_held_in_memory": 0,
        "max_market_rows_held_in_memory": 0,
        "count_reconciliations": 0,
        "incremental_counter_updates": 0,
        "duration_ms": None,
        "completed_at": None,
    }


def _get_resource_profile(replay: CecchinoLabPurchasabilityV3ReplayRun) -> dict[str, Any]:
    summary = dict(replay.summary_json or {})
    rp = dict(summary.get("resource_profile") or {})
    base = _empty_resource_profile()
    base.update(rp)
    return base


def _set_resource_profile(
    replay: CecchinoLabPurchasabilityV3ReplayRun, profile: dict[str, Any]
) -> None:
    summary = dict(replay.summary_json or {})
    summary["resource_profile"] = profile
    replay.summary_json = summary


def _progress_pct_incremental(evaluations_processed: int, evaluations_total: int) -> Decimal:
    """Progress durante il job: mai 100% prima di reconcile finale + invarianti."""
    total = int(evaluations_total or 0) or 1
    processed = max(0, int(evaluations_processed or 0))
    raw = round(100.0 * processed / total, 1)
    if processed >= total:
        return Decimal("99.9")
    return Decimal(str(min(99.9, raw)))


def _penalty_points(item: dict[str, Any], key: str) -> Decimal | None:
    penalties = item.get("penalties") or {}
    block = penalties.get(key) or {}
    pts = block.get("penalty_points")
    return _dec(pts)


def _build_result_row(
    *,
    replay: CecchinoLabPurchasabilityV3ReplayRun,
    snap: SimpleNamespace,
    market_key: str,
    market: SimpleNamespace | None,
    item: dict[str, Any] | None,
    score_status: str,
    score_reasons: list[str],
    formula_sha: str | None,
    panel_fields: list[str],
) -> dict[str, Any]:
    quote_class, _ = ("unavailable", [])
    perf_type = "not_applicable"
    if market is not None:
        quote_class, _ = classify_quote_quality(market)
        perf_type = classify_performance(market, quote_class)

    calculation_status: str | None
    if score_status in ("not_replayable", "not_replayable_missing_inputs"):
        calculation_status = "source_not_replayable"
    elif item is not None:
        calculation_status = str(item.get("status") or "unavailable")
    else:
        calculation_status = "unavailable"

    gate_status = None
    score = None
    raw_score = None
    score_class = None
    value_score = None
    quality_score = None
    total_penalty = None
    gate_reasons: list[Any] = list(score_reasons)
    reason_codes: list[Any] = list(score_reasons)
    warnings: list[Any] = []
    calc_quality = None
    opp_key = None
    opp_fair = None
    is_leader = None
    edge_gap = None
    p_risk = p_opp = p_div = p_fam = p_quote = None

    if item is not None and calculation_status != "source_not_replayable":
        gate_status = item.get("gate_status")
        gate_reasons = list(item.get("gate_reason_codes") or gate_reasons)
        score = _as_int(item.get("score"))
        raw_score = _dec(item.get("raw_score"))
        score_class = item.get("class")
        value_score = _dec(item.get("value_score"))
        quality_score = _dec(item.get("quality_score"))
        total_penalty = _dec(item.get("total_penalty"))
        calc_quality = item.get("calculation_quality")
        reason_codes = list(item.get("reason_codes") or reason_codes)
        warnings = list(item.get("warnings") or [])
        opp_key = item.get("opposite_market_key")
        opp_fair = _dec(item.get("opposite_fair_probability"))
        is_leader = item.get("selected_is_family_edge_leader")
        edge_gap = _dec(item.get("edge_gap_or_deficit"))
        p_risk = _penalty_points(item, "probability_risk")
        p_opp = _penalty_points(item, "opposite_market_pressure")
        p_div = _penalty_points(item, "extreme_divergence")
        p_fam = _penalty_points(item, "family_ambiguity")
        p_quote = _penalty_points(item, "quote_quality")
        if calculation_status == "source_not_replayable":
            score = None
            score_class = None

    if calculation_status == "source_not_replayable":
        score = None
        score_class = None
        raw_score = None
        value_score = None
        quality_score = None
        if "source_not_replayable" not in reason_codes:
            reason_codes.append("source_not_replayable")

    # Performance collegata DOPO lo score
    won = None
    profit_real = None
    profit_synth = None
    result_reason = None
    if market is not None:
        won = getattr(market, "won", None)
        result_reason = getattr(market, "result_reason", None)
        if quote_class == "real":
            profit_real = _dec(getattr(market, "profit_1u_real", None))
            profit_synth = None
        elif quote_class == "derived":
            profit_synth = _dec(getattr(market, "profit_1u_synthetic", None))
            profit_real = None
        else:
            profit_real = None
            profit_synth = None

    return {
        "replay_run_id": int(replay.id),
        "source_scan_run_id": int(replay.source_scan_run_id),
        "source_snapshot_id": int(snap.id),
        "source_market_result_id": int(market.id) if market is not None else None,
        "lab_match_id": getattr(snap, "lab_match_id", None),
        "competition_name": getattr(snap, "competition_name", None),
        "kickoff_at": getattr(snap, "kickoff_at", None),
        "chronological_order": getattr(snap, "chronological_order", None),
        "market_key": market_key,
        "market_family": market_family_for(market_key),
        "quote_source": getattr(market, "quote_source_type", None) if market else None,
        "quote_quality": quote_class,
        "performance_type": perf_type,
        "is_real_book_quote": bool(getattr(market, "is_real_book_quote", False)) if market else False,
        "is_derived_quote": bool(getattr(market, "is_derived_quote", False)) if market else False,
        "derivation_method": getattr(market, "derivation_method", None) if market else None,
        "quota_book": _dec(getattr(market, "quota_book", None)) if market else None,
        "quota_cecchino": _dec(getattr(market, "quota_cecchino", None)) if market else None,
        "prob_book_raw": _dec(getattr(market, "prob_book_raw", None)) if market else None,
        "prob_book_fair": _dec(getattr(market, "prob_book_fair", None)) if market else None,
        "prob_cecchino": _dec(getattr(market, "prob_cecchino", None)) if market else None,
        "edge_pct": _dec(getattr(market, "edge_pct", None)) if market else None,
        "vantaggio_prob": _dec(getattr(market, "vantaggio_prob", None)) if market else None,
        "calculation_status": calculation_status,
        "gate_status": gate_status,
        "gate_reason_codes_json": gate_reasons,
        "score": score,
        "raw_score": raw_score,
        "score_class": score_class,
        "value_score": value_score,
        "quality_score": quality_score,
        "total_penalty": total_penalty,
        "probability_risk_penalty": p_risk,
        "opposite_market_pressure_penalty": p_opp,
        "extreme_divergence_penalty": p_div,
        "family_ambiguity_penalty": p_fam,
        "quote_quality_penalty": p_quote,
        "opposite_market_key": opp_key,
        "opposite_fair_probability": opp_fair,
        "selected_is_family_edge_leader": is_leader,
        "family_edge_gap_or_deficit": edge_gap,
        "calculation_quality": calc_quality,
        "reason_codes_json": reason_codes,
        "warnings_json": warnings,
        "performance_evaluation_status": perf_type,
        "won": won,
        "profit_1u_real": profit_real,
        "profit_1u_synthetic": profit_synth,
        "result_reason": result_reason,
        "source_pre_match_payload_sha256": getattr(snap, "pre_match_payload_sha256", None),
        "source_pre_match_locked_at": getattr(snap, "pre_match_locked_at", None),
        "formula_payload_sha256": formula_sha,
        "formula_payload_fields_json": panel_fields,
        "pre_match_only": True,
        "post_match_fields_excluded": True,
    }


def _classify_calc_bucket(row: dict[str, Any]) -> str:
    status = str(row.get("calculation_status") or "")
    gate = str(row.get("gate_status") or "")
    if status == "source_not_replayable" or status == "unavailable":
        return "unavailable"
    if status == "not_applicable":
        return "not_applicable"
    if status == "error":
        return "error"
    if gate and gate != "passed" and row.get("score") is None:
        return "gate_failed"
    if row.get("score") is not None:
        return "scored"
    if status == "available" or status == "partial":
        if row.get("score") is not None:
            return "scored"
        return "unavailable"
    return "unclassified"


def _upsert_results(db: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    table = CecchinoLabPurchasabilityV3ReplayResult.__table__
    stmt = pg_insert(table).values(rows)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in table.columns
        if c.name
        not in (
            "id",
            "replay_run_id",
            "source_snapshot_id",
            "market_key",
            "created_at",
        )
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_cecchino_lab_p3_replay_res_run_snap_mkt",
        set_=update_cols,
    )
    db.execute(stmt)


def _process_snapshot(
    *,
    replay: CecchinoLabPurchasabilityV3ReplayRun,
    snap: SimpleNamespace,
    markets: list[SimpleNamespace],
    formula_call_counter: list[int],
) -> list[dict[str, Any]]:
    by_mk: dict[str, SimpleNamespace] = {}
    duplicates: set[str] = set()
    for m in markets:
        mk = str(m.market_key)
        if mk in by_mk:
            duplicates.add(mk)
        else:
            by_mk[mk] = m

    if duplicates:
        raise ReplayWorkerError(
            "ambiguous_market_join",
            "Join mercato ambiguo: market_key duplicati nello snapshot",
            details={
                "snapshot_id": int(getattr(snap, "id", 0) or 0),
                "duplicate_market_keys": sorted(duplicates),
            },
        )

    from app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight import (
        evaluate_historical_integrity_policy,
    )

    policy = evaluate_historical_integrity_policy(snap)
    gate = str(policy.get("integrity_gate") or "invalid")
    integrity_reasons = list(policy.get("reasons") or [])
    if gate == "ok":
        integrity = "ok"
    elif gate == "incomplete":
        integrity = "missing"
    else:
        integrity = "invalid"

    score_statuses: dict[str, tuple[str, list[str]]] = {}
    for mk in V3_MARKET_ORDER:
        score_statuses[mk] = classify_score_replay(
            market_key=mk,
            m=by_mk.get(mk),
            by_mk=by_mk,
            integrity=integrity,
            integrity_reasons=integrity_reasons,
            duplicate=False,
        )

    # Panel solo per mercati presenti e replayable (o gate/warning)
    panel_markets: list[SimpleNamespace] = []
    panel_keys: list[str] = []
    for mk in V3_MARKET_ORDER:
        st, _ = score_statuses[mk]
        wl = map_score_status_to_workload_key(st)
        if wl in ("not_replayable", "invalid_integrity", "ambiguous_market_join"):
            continue
        m = by_mk.get(mk)
        if m is None:
            continue
        panel_markets.append(m)
        panel_keys.append(mk)

    items_by_mk: dict[str, dict[str, Any]] = {}
    formula_sha: str | None = None
    panel_fields = list(FORMULA_PAYLOAD_ALLOWED_FIELDS)

    if panel_markets:
        panel_rows = [build_adapter_panel_row(m) for m in panel_markets]
        assert_panel_whitelist(panel_rows)
        formula_sha = formula_payload_sha256(panel_rows)
        formula_call_counter[0] += 1
        batch = calculate_purchasability_v3_batch(
            kpi_panel={"rows": panel_rows},
            fixture_meta={
                "today_fixture_id": getattr(snap, "lab_match_id", None),
                "snapshot_at": getattr(snap, "pre_match_locked_at", None),
            },
        )
        items = list(batch.get("items") or [])
        validate_formula_items(expected_keys=panel_keys, items=items)
        for it in items:
            items_by_mk[str(it.get("market_key"))] = it

    results: list[dict[str, Any]] = []
    for mk in V3_MARKET_ORDER:
        st, reasons = score_statuses[mk]
        wl = map_score_status_to_workload_key(st) or st
        market = by_mk.get(mk)
        item = items_by_mk.get(mk)
        if wl in ("not_replayable",) or st.startswith("not_replayable"):
            item = None
        row = _build_result_row(
            replay=replay,
            snap=snap,
            market_key=mk,
            market=market,
            item=item,
            score_status=wl if wl else st,
            score_reasons=reasons,
            formula_sha=formula_sha if item is not None else None,
            panel_fields=panel_fields if item is not None else list(FORMULA_PAYLOAD_ALLOWED_FIELDS),
        )
        results.append(row)
    return results


def summarize_result_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Delta contatori puro da righe risultato di un batch (senza I/O)."""
    scored = gate_failed = unavailable = not_applicable = error = unclassified = 0
    real_q = derived_q = unavail_q = 0
    real_perf = synth_perf = miss_perf = 0
    snaps: set[int] = set()

    for row in rows:
        sid = row.get("source_snapshot_id")
        if sid is not None:
            snaps.add(int(sid))
        bucket = _classify_calc_bucket(row)
        if bucket == "scored":
            scored += 1
        elif bucket == "gate_failed":
            gate_failed += 1
        elif bucket == "unavailable":
            unavailable += 1
        elif bucket == "not_applicable":
            not_applicable += 1
        elif bucket == "error":
            error += 1
        else:
            unclassified += 1

        qq = row.get("quote_quality")
        if qq == "real":
            real_q += 1
        elif qq == "derived":
            derived_q += 1
        else:
            unavail_q += 1

        perf = row.get("performance_evaluation_status")
        if perf == "real_profit_ready":
            real_perf += 1
        elif perf == "synthetic_profit_ready":
            synth_perf += 1
        else:
            miss_perf += 1

    return {
        "snapshots_processed": len(snaps),
        "evaluations_processed": len(rows),
        "results_persisted": len(rows),
        "scored_count": scored,
        "gate_failed_count": gate_failed,
        "unavailable_count": unavailable,
        "not_applicable_count": not_applicable,
        "error_count": error,
        "unclassified_count": unclassified,
        "real_quote_count": real_q,
        "derived_quote_count": derived_q,
        "unavailable_quote_count": unavail_q,
        "real_performance_ready_count": real_perf,
        "synthetic_performance_ready_count": synth_perf,
        "performance_missing_count": miss_perf,
    }


def _apply_counter_deltas(
    replay: CecchinoLabPurchasabilityV3ReplayRun, delta: dict[str, int]
) -> None:
    replay.snapshots_processed = int(replay.snapshots_processed or 0) + int(
        delta.get("snapshots_processed") or 0
    )
    replay.evaluations_processed = int(replay.evaluations_processed or 0) + int(
        delta.get("evaluations_processed") or 0
    )
    replay.results_persisted = int(replay.results_persisted or 0) + int(
        delta.get("results_persisted") or 0
    )
    replay.scored_count = int(replay.scored_count or 0) + int(delta.get("scored_count") or 0)
    replay.gate_failed_count = int(replay.gate_failed_count or 0) + int(
        delta.get("gate_failed_count") or 0
    )
    replay.unavailable_count = int(replay.unavailable_count or 0) + int(
        delta.get("unavailable_count") or 0
    )
    replay.not_applicable_count = int(replay.not_applicable_count or 0) + int(
        delta.get("not_applicable_count") or 0
    )
    replay.error_count = int(replay.error_count or 0) + int(delta.get("error_count") or 0)
    replay.unclassified_count = int(replay.unclassified_count or 0) + int(
        delta.get("unclassified_count") or 0
    )
    replay.real_quote_count = int(replay.real_quote_count or 0) + int(
        delta.get("real_quote_count") or 0
    )
    replay.derived_quote_count = int(replay.derived_quote_count or 0) + int(
        delta.get("derived_quote_count") or 0
    )
    replay.unavailable_quote_count = int(replay.unavailable_quote_count or 0) + int(
        delta.get("unavailable_quote_count") or 0
    )
    replay.real_performance_ready_count = int(replay.real_performance_ready_count or 0) + int(
        delta.get("real_performance_ready_count") or 0
    )
    replay.synthetic_performance_ready_count = int(
        replay.synthetic_performance_ready_count or 0
    ) + int(delta.get("synthetic_performance_ready_count") or 0)
    replay.performance_missing_count = int(replay.performance_missing_count or 0) + int(
        delta.get("performance_missing_count") or 0
    )
    replay.progress_pct = _progress_pct_incremental(
        int(replay.evaluations_processed or 0),
        int(replay.evaluations_total or 0),
    )


def _calc_bucket_sql_expr():
    """Espressione SQL equivalente a ``_classify_calc_bucket``."""
    R = CecchinoLabPurchasabilityV3ReplayResult
    calc = R.calculation_status
    gate = R.gate_status
    score = R.score
    return case(
        (calc.in_(("source_not_replayable", "unavailable")), "unavailable"),
        (calc == "not_applicable", "not_applicable"),
        (calc == "error", "error"),
        (
            (gate.isnot(None))
            & (gate != "")
            & (gate != "passed")
            & (score.is_(None)),
            "gate_failed",
        ),
        (score.isnot(None), "scored"),
        (calc.in_(("available", "partial")), "unavailable"),
        else_="unclassified",
    )


def _reconcile_counts_from_db(db: Session, replay: CecchinoLabPurchasabilityV3ReplayRun) -> None:
    """Riconciliazione aggregata SQL (nessun carico di tutte le row in Python)."""
    R = CecchinoLabPurchasabilityV3ReplayResult
    bucket = _calc_bucket_sql_expr()
    qq = R.quote_quality
    perf = R.performance_evaluation_status

    stmt = select(
        func.count().label("total"),
        func.count(func.distinct(R.source_snapshot_id)).label("snaps"),
        func.coalesce(func.sum(case((bucket == "scored", 1), else_=0)), 0).label("scored"),
        func.coalesce(func.sum(case((bucket == "gate_failed", 1), else_=0)), 0).label(
            "gate_failed"
        ),
        func.coalesce(func.sum(case((bucket == "unavailable", 1), else_=0)), 0).label(
            "unavailable"
        ),
        func.coalesce(func.sum(case((bucket == "not_applicable", 1), else_=0)), 0).label(
            "not_applicable"
        ),
        func.coalesce(func.sum(case((bucket == "error", 1), else_=0)), 0).label("error"),
        func.coalesce(func.sum(case((bucket == "unclassified", 1), else_=0)), 0).label(
            "unclassified"
        ),
        func.coalesce(func.sum(case((qq == "real", 1), else_=0)), 0).label("real_q"),
        func.coalesce(func.sum(case((qq == "derived", 1), else_=0)), 0).label("derived_q"),
        func.coalesce(
            func.sum(
                case(
                    ((qq.is_(None)) | (~qq.in_(("real", "derived"))), 1),
                    else_=0,
                )
            ),
            0,
        ).label("unavail_q"),
        func.coalesce(
            func.sum(case((perf == "real_profit_ready", 1), else_=0)), 0
        ).label("real_perf"),
        func.coalesce(
            func.sum(case((perf == "synthetic_profit_ready", 1), else_=0)), 0
        ).label("synth_perf"),
        func.coalesce(
            func.sum(
                case(
                    (
                        (perf.is_(None))
                        | (
                            ~perf.in_(
                                ("real_profit_ready", "synthetic_profit_ready")
                            )
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("miss_perf"),
    ).where(R.replay_run_id == int(replay.id))

    row = db.execute(stmt).one()
    total = int(row.total or 0)
    replay.results_persisted = total
    replay.evaluations_processed = total
    replay.snapshots_processed = int(row.snaps or 0)
    replay.scored_count = int(row.scored or 0)
    replay.gate_failed_count = int(row.gate_failed or 0)
    replay.unavailable_count = int(row.unavailable or 0)
    replay.not_applicable_count = int(row.not_applicable or 0)
    replay.error_count = int(row.error or 0)
    replay.unclassified_count = int(row.unclassified or 0)
    replay.real_quote_count = int(row.real_q or 0)
    replay.derived_quote_count = int(row.derived_q or 0)
    replay.unavailable_quote_count = int(row.unavail_q or 0)
    replay.real_performance_ready_count = int(row.real_perf or 0)
    replay.synthetic_performance_ready_count = int(row.synth_perf or 0)
    replay.performance_missing_count = int(row.miss_perf or 0)
    replay.progress_pct = _progress_pct_incremental(
        total, int(replay.evaluations_total or 0)
    )

    profile = _get_resource_profile(replay)
    profile["count_reconciliations"] = int(profile.get("count_reconciliations") or 0) + 1
    _set_resource_profile(replay, profile)


# Alias retrocompatibile per test/import esistenti
_recompute_counts_from_db = _reconcile_counts_from_db


def _final_invariants_ok(replay: CecchinoLabPurchasabilityV3ReplayRun) -> tuple[bool, list[str]]:
    errors: list[str] = []
    persisted = int(replay.results_persisted or 0)
    total = int(replay.evaluations_total or 0)
    if persisted != total:
        errors.append(f"results_persisted({persisted}) != evaluations_total({total})")
    bucket_sum = (
        int(replay.scored_count or 0)
        + int(replay.gate_failed_count or 0)
        + int(replay.unavailable_count or 0)
        + int(replay.not_applicable_count or 0)
        + int(replay.error_count or 0)
        + int(replay.unclassified_count or 0)
    )
    if bucket_sum != persisted:
        errors.append(f"status_buckets({bucket_sum}) != results_persisted({persisted})")
    quote_sum = (
        int(replay.real_quote_count or 0)
        + int(replay.derived_quote_count or 0)
        + int(replay.unavailable_quote_count or 0)
    )
    if quote_sum != persisted:
        errors.append(f"quote_buckets({quote_sum}) != results_persisted({persisted})")
    if int(replay.unclassified_count or 0) != 0:
        errors.append("unclassified_count != 0")
    if int(replay.error_count or 0) != 0:
        errors.append("error_count != 0")
    return len(errors) == 0, errors


def _mark_cancelled(
    db: Session, replay: CecchinoLabPurchasabilityV3ReplayRun, *, reconcile: bool
) -> None:
    if reconcile:
        _reconcile_counts_from_db(db, replay)
    replay.status = STATUS_CANCELLED
    replay.completed_at = _utcnow()
    profile = _get_resource_profile(replay)
    profile["completed_at"] = replay.completed_at.isoformat()
    _set_resource_profile(replay, profile)
    db.commit()


def execute_purchasability_v3_replay(replay_id: int) -> None:
    db = SessionLocal()
    formula_calls = [0]
    started_mono = time.monotonic()
    last_cancel_check = 0.0
    market_queries = 0
    batches_processed = 0
    incremental_updates = 0
    max_snaps_mem = 0
    max_market_rows_mem = 0
    try:
        replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
        if not replay:
            return
        if replay.cancel_requested:
            replay.status = STATUS_CANCELLED
            replay.completed_at = _utcnow()
            db.commit()
            return

        replay.status = STATUS_RUNNING
        replay.started_at = replay.started_at or _utcnow()
        replay.heartbeat_at = _utcnow()
        if not (replay.summary_json or {}).get("resource_profile"):
            _set_resource_profile(replay, _empty_resource_profile())
        db.commit()

        done_ids = _load_done_snapshot_ids(db, replay_id)
        is_resume = int(replay.resume_count or 0) > 0 or bool(done_ids)
        if is_resume:
            _reconcile_counts_from_db(db, replay)
            db.commit()

        source_run_id = int(replay.source_scan_run_id)

        for snap_batch in _iter_eligible_snapshot_batches(
            db, source_run_id, REPLAY_BATCH_SNAPSHOTS
        ):
            if _is_cancelled(db, replay_id):
                replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
                if replay:
                    _mark_cancelled(db, replay, reconcile=True)
                return
            last_cancel_check = time.monotonic()

            pending = [s for s in snap_batch if int(s.id) not in done_ids]
            if not pending:
                continue

            max_snaps_mem = max(max_snaps_mem, len(pending))
            batch_ids = [int(s.id) for s in pending]
            markets_map = _load_markets_for_snapshots(db, source_run_id, batch_ids)
            market_queries += 1
            market_rows_held = sum(len(v) for v in markets_map.values())
            max_market_rows_mem = max(max_market_rows_mem, market_rows_held)

            replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
            if not replay:
                return

            batch_rows: list[dict[str, Any]] = []
            last_snap: SimpleNamespace | None = None
            try:
                for snap in pending:
                    now = time.monotonic()
                    if (now - last_cancel_check) >= REPLAY_HEARTBEAT_SECONDS:
                        if _is_cancelled(db, replay_id):
                            db.rollback()
                            replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
                            if replay:
                                _mark_cancelled(db, replay, reconcile=True)
                            return
                        last_cancel_check = now
                        replay.heartbeat_at = _utcnow()

                    sid = int(snap.id)
                    markets = markets_map.get(sid, [])
                    replay.current_snapshot_id = sid
                    replay.current_chronological_order = getattr(
                        snap, "chronological_order", None
                    )
                    replay.current_competition = getattr(snap, "competition_name", None)
                    rows = _process_snapshot(
                        replay=replay,
                        snap=snap,
                        markets=markets,
                        formula_call_counter=formula_calls,
                    )
                    batch_rows.extend(rows)
                    last_snap = snap
            except ReplayWorkerError as exc:
                db.rollback()
                replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
                if replay:
                    replay.status = STATUS_FAILED
                    replay.error_json = {
                        "error": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                        "snapshot_id": (exc.details or {}).get("snapshot_id"),
                    }
                    replay.completed_at = _utcnow()
                    try:
                        _reconcile_counts_from_db(db, replay)
                    except Exception:
                        logger.exception(
                            "purchasability_v3_replay_reconcile_after_error replay_id=%s",
                            replay_id,
                        )
                    db.commit()
                return

            # Batch atomico: upsert + contatori incrementali + heartbeat + commit
            try:
                _upsert_results(db, batch_rows)
                delta = summarize_result_rows(batch_rows)
                _apply_counter_deltas(replay, delta)
                incremental_updates += 1
                for sid in batch_ids:
                    done_ids.add(sid)

                batches_processed += 1
                profile = _get_resource_profile(replay)
                profile["snapshot_batches_processed"] = batches_processed
                profile["market_batch_queries"] = market_queries
                profile["formula_invocations"] = formula_calls[0]
                profile["max_snapshots_held_in_memory"] = max_snaps_mem
                profile["max_market_rows_held_in_memory"] = max_market_rows_mem
                profile["incremental_counter_updates"] = incremental_updates
                profile["replay_batch_snapshots"] = REPLAY_BATCH_SNAPSHOTS
                _set_resource_profile(replay, profile)

                if last_snap is not None:
                    replay.current_snapshot_id = int(last_snap.id)
                    replay.current_chronological_order = getattr(
                        last_snap, "chronological_order", None
                    )
                    replay.current_competition = getattr(
                        last_snap, "competition_name", None
                    )
                replay.heartbeat_at = _utcnow()
                db.commit()
            except Exception:
                db.rollback()
                replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
                if replay:
                    replay.status = STATUS_FAILED
                    replay.error_json = {
                        "error": "batch_persist_failed",
                        "message": "Fallimento persistenza batch atomico",
                    }
                    replay.completed_at = _utcnow()
                    try:
                        _reconcile_counts_from_db(db, replay)
                    except Exception:
                        pass
                    db.commit()
                raise

            # libera mappa mercati del batch
            del markets_map
            batch_rows = []

            if _is_cancelled(db, replay_id):
                replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
                if replay:
                    _mark_cancelled(db, replay, reconcile=True)
                return

        replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
        if not replay:
            return
        if _is_cancelled(db, replay_id):
            _mark_cancelled(db, replay, reconcile=True)
            return

        _reconcile_counts_from_db(db, replay)
        ok, inv_errors = _final_invariants_ok(replay)
        if not ok:
            replay.status = STATUS_FAILED
            replay.error_json = {
                "error": "final_invariants_failed",
                "message": "Invarianti finali non soddisfatti",
                "details": {"errors": inv_errors},
            }
            replay.completed_at = _utcnow()
            db.commit()
            return

        has_warnings = (
            int(replay.derived_quote_count or 0) > 0
            or int(replay.unavailable_quote_count or 0) > 0
            or int(replay.non_replayable_source_count or 0) > 0
            or int(replay.warning_source_count or 0) > 0
        )
        replay.status = (
            STATUS_COMPLETED_WITH_WARNINGS if has_warnings else STATUS_COMPLETED
        )
        replay.completed_at = _utcnow()
        replay.progress_pct = Decimal("100.0")
        duration_ms = int((time.monotonic() - started_mono) * 1000)
        profile = _get_resource_profile(replay)
        profile["snapshot_batches_processed"] = batches_processed
        profile["market_batch_queries"] = market_queries
        profile["formula_invocations"] = formula_calls[0]
        profile["max_snapshots_held_in_memory"] = max_snaps_mem
        profile["max_market_rows_held_in_memory"] = max_market_rows_mem
        profile["incremental_counter_updates"] = incremental_updates
        profile["replay_batch_snapshots"] = REPLAY_BATCH_SNAPSHOTS
        profile["duration_ms"] = duration_ms
        profile["completed_at"] = replay.completed_at.isoformat()
        summary = dict(replay.summary_json or {})
        summary["resource_profile"] = profile
        summary["formula_invocations"] = formula_calls[0]
        summary["final_status"] = replay.status
        summary["invariants_ok"] = True
        replay.summary_json = summary
        replay.error_json = None
        db.commit()
    except Exception as exc:
        logger.exception("purchasability_v3_replay_failed replay_id=%s", replay_id)
        try:
            replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
            if replay and replay.status not in (
                STATUS_FAILED,
                STATUS_CANCELLED,
                STATUS_COMPLETED,
                STATUS_COMPLETED_WITH_WARNINGS,
            ):
                replay.status = STATUS_FAILED
                replay.error_json = {
                    "error": "replay_worker_exception",
                    "message": str(exc)[:500],
                }
                replay.completed_at = _utcnow()
                db.commit()
        except Exception:
            logger.exception("purchasability_v3_replay_fail_persist replay_id=%s", replay_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(replay_id, None)
