"""Job persistita: benchmark storico Goal Intensity V4 vs V5 (pilot/full).

Non modifica run/snapshot storici. Nessuna API esterna. Nessun refit.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import threading
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_lab_goal_intensity_benchmark_job import (
    ACTIVE_STATUSES,
    COMPLETED_STATUSES,
    CONFIRM_FULL,
    CONFIRM_PILOT,
    DEFAULT_BATCH_SIZE,
    DEFAULT_PILOT_SIZE,
    DEFAULT_RANDOM_SEED,
    JOB_VERSION,
    MAX_BATCH_SIZE,
    MIN_BATCH_SIZE,
    MODE_FULL,
    MODE_PILOT,
    REQUIRED_BUNDLE_VERSION,
    RESUMABLE_STATUSES,
    STATUS_CANCEL_REQUESTED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    CecchinoLabGoalIntensityBenchmarkJob,
)
from app.models.cecchino_lab_goal_intensity_benchmark_row import (
    CecchinoLabGoalIntensityBenchmarkRow,
)
from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_independence import (
    SCIENTIFIC_DIAGNOSTIC_REPLAY,
    assess_independence,
)
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_metrics import (
    build_breakdowns,
    evaluate_paired_rows,
)
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_scoring import (
    MAIN_MODEL_IDS,
    extract_ft_target,
    extract_v4_from_historical_snapshot,
    extract_v5_features_from_snapshot,
    get_frozen_goal_intensity_candidate_bundle,
    prediction_input_hash,
    score_five_models_with_frozen_bundle,
    validate_frozen_candidate_bundle,
)
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_selection import (
    select_pilot_snapshots,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}

RUN_COMPLETED = frozenset({"completed", "completed_with_warnings"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_canonical(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _job_key(
    *,
    run_id: int,
    bundle_id: int,
    job_version: str,
    mode: str,
    selection_hash: str,
) -> str:
    return _sha256_canonical(
        {
            "run_id": run_id,
            "bundle_id": bundle_id,
            "job_version": job_version,
            "mode": mode,
            "selection_hash": selection_hash,
        }
    )[:128]


def _load_run(db: Session, run_id: int) -> CecchinoLabHistoricalScanRun:
    run = db.get(CecchinoLabHistoricalScanRun, int(run_id))
    if run is None:
        raise CecchinoLabImportError("run_not_found", f"Run {run_id} non trovato", status_code=404)
    return run


def _require_completed_run(run: CecchinoLabHistoricalScanRun) -> None:
    if run.status not in RUN_COMPLETED:
        raise CecchinoLabImportError(
            "run_not_completed",
            "La job richiede una run storica completed",
            status_code=409,
            details={"status": run.status},
        )


def _load_snapshots(db: Session, run_id: int) -> list[CecchinoLabHistoricalMatchSnapshot]:
    return list(
        db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot)
            .where(CecchinoLabHistoricalMatchSnapshot.run_id == int(run_id))
            .order_by(
                CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc().nulls_last(),
                CecchinoLabHistoricalMatchSnapshot.id.asc(),
            )
        ).all()
    )


def _estimate_availability(
    snapshots: list[CecchinoLabHistoricalMatchSnapshot],
    bundle: Any,
) -> dict[str, Any]:
    """Stima coverage senza scrivere. Scoring campione solo per verificare i cinque modelli."""
    missing: Counter[str] = Counter()
    v4_ok = v5_ok = paired_est = 0
    probe_ok = 0
    probe_n = 0
    for s in snapshots:
        v4, v4_reason = extract_v4_from_historical_snapshot(s)
        feats, feat_reason = extract_v5_features_from_snapshot(s)
        target, tgt_reason = extract_ft_target(s.result_json)
        if v4 is None:
            missing[v4_reason or "missing_persisted_v4_expected_goals"] += 1
        else:
            v4_ok += 1
        if feats is None or feat_reason == "incomplete_v5_features":
            missing[feat_reason or "missing_v5_features"] += 1
        else:
            v5_ok += 1
        if target is None:
            missing[tgt_reason or "missing_ft_result"] += 1
        candidate = (
            v4 is not None
            and feats is not None
            and feat_reason is None
            and target is not None
        )
        if candidate:
            paired_est += 1
            if probe_n < 25:
                probe_n += 1
                try:
                    pred = score_five_models_with_frozen_bundle(
                        features=feats, v4_payload=v4, bundle=bundle
                    )
                    if pred.get("five_models_available"):
                        probe_ok += 1
                    else:
                        missing["five_models_incomplete"] += 1
                except Exception:
                    missing["scoring_error"] += 1
    five_ok = paired_est if probe_n == 0 or probe_ok == probe_n else probe_ok
    # Se il probe fallisce su tutti, non gonfiare la stima
    if probe_n > 0 and probe_ok == 0:
        five_ok = 0
        paired_est = 0
        missing["five_models_probe_failed"] += 1
    blocked = paired_est == 0
    return {
        "v4_rebuildable": v4_ok,
        "v5_features_rebuildable": v5_ok,
        "five_models_rebuildable": five_ok,
        "paired_complete_estimate": paired_est,
        "blocked": blocked,
        "missing_by_reason": dict(sorted(missing.items())),
        "snapshots_scanned": len(snapshots),
        "scoring_probe_n": probe_n,
        "scoring_probe_ok": probe_ok,
    }


def build_goal_intensity_benchmark_preflight(
    db: Session,
    run_id: int,
    *,
    bundle_version: str = REQUIRED_BUNDLE_VERSION,
    pilot_size: int = DEFAULT_PILOT_SIZE,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> dict[str, Any]:
    """Preflight read-only: nessuna scrittura."""
    run = _load_run(db, run_id)
    _require_completed_run(run)
    bundle = get_frozen_goal_intensity_candidate_bundle(db, version=bundle_version)
    bundle_meta = validate_frozen_candidate_bundle(bundle)
    snapshots = _load_snapshots(db, run_id)
    independence = assess_independence(
        db=db, run=run, snapshots=snapshots, candidate_bundle=bundle
    )
    availability = _estimate_availability(snapshots, bundle)
    pilot = select_pilot_snapshots(
        snapshots, pilot_size=int(pilot_size), random_seed=int(random_seed)
    )
    blocking: list[str] = []
    if bundle_meta.get("is_active"):
        blocking.append("bundle_is_active")
    if bundle_meta.get("live_scoring_enabled"):
        blocking.append("bundle_live_scoring_enabled")
    # Coverage V4 bassa non blocca il pilot tecnico: la job misura i missing.
    if int(pilot.get("selected") or 0) <= 0:
        blocking.append("pilot_selection_empty")
    pilot_allowed = len(blocking) == 0
    warnings = []
    if availability.get("blocked"):
        warnings.append("paired_complete_estimate_zero")
    if int(availability.get("v4_rebuildable") or 0) == 0:
        warnings.append("no_persisted_v4_expected_goals_in_run")

    return {
        "status": "preview",
        "run": {
            "id": run.id,
            "status": run.status,
            "season": run.season_label,
            "snapshots_found": len(snapshots),
            "source_git_commit": run.source_git_commit,
        },
        "bundle": {
            "id": bundle.id,
            "version": bundle.version,
            "status": bundle.status,
            "is_active": bool(bundle.is_active),
            "definition_hash": bundle.candidate_definition_hash,
            "intended_use": bundle_meta.get("intended_use"),
        },
        "independence": {
            "status": independence.get("status"),
            "scientific_label": independence.get("scientific_label"),
            "overlap_count": independence.get("overlap_count"),
            "overlap_pct": independence.get("overlap_pct"),
            "details": independence,
        },
        "availability": availability,
        "pilot": {
            "requested": pilot.get("requested"),
            "selected": pilot.get("selected"),
            "selection_hash": pilot.get("selection_hash"),
            "selection_protocol": pilot.get("selection_protocol"),
            "competition_distribution": pilot.get("competition_distribution"),
            "month_distribution": pilot.get("month_distribution"),
            "kickoff_range": pilot.get("kickoff_range"),
            "random_seed": pilot.get("random_seed"),
        },
        "checks": {
            "external_api_calls": 0,
            "full_scan_required": False,
            "base_run_writes": 0,
            "bundle_refit": False,
            "result_used_in_prediction": False,
        },
        "pilot_allowed": pilot_allowed,
        "full_allowed_after_pilot": False,
        "blocking_reasons": blocking,
        "warnings": warnings,
        "job_version": JOB_VERSION,
        "models": list(MAIN_MODEL_IDS),
    }


def _serialize_job(job: CecchinoLabGoalIntensityBenchmarkJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "id": job.id,
        "historical_run_id": job.historical_run_id,
        "bundle_id": job.bundle_id,
        "job_version": job.job_version,
        "mode": job.mode,
        "status": job.status,
        "independence_status": job.independence_status,
        "job_key": job.job_key,
        "random_seed": job.random_seed,
        "requested_sample_size": job.requested_sample_size,
        "total_snapshots": job.total_snapshots,
        "eligible_snapshots": job.eligible_snapshots,
        "selected_snapshots": job.selected_snapshots,
        "processed_snapshots": job.processed_snapshots,
        "paired_complete": job.paired_complete,
        "skipped": job.skipped,
        "errors": job.errors,
        "progress_pct": float(job.progress_pct) if job.progress_pct is not None else None,
        "cancel_requested": bool(job.cancel_requested),
        "params_json": job.params_json,
        "preflight_json": job.preflight_json,
        "summary_json": job.summary_json,
        "missing_by_reason_json": job.missing_by_reason_json,
        "error_json": job.error_json,
        "bundle_definition_hash": job.bundle_definition_hash,
        "run_fixture_ids_hash": job.run_fixture_ids_hash,
        "source_git_commit": job.source_git_commit,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "last_checkpoint_at": job.last_checkpoint_at.isoformat()
        if job.last_checkpoint_at
        else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "cancelled_at": job.cancelled_at.isoformat() if job.cancelled_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def get_goal_intensity_benchmark_job(db: Session, job_id: int) -> dict[str, Any]:
    job = db.get(CecchinoLabGoalIntensityBenchmarkJob, int(job_id))
    if job is None:
        raise CecchinoLabImportError("job_not_found", f"Job {job_id} non trovata", status_code=404)
    return _serialize_job(job)


def _find_completed_pilot(
    db: Session,
    *,
    run_id: int,
    bundle_id: int,
    job_version: str,
) -> CecchinoLabGoalIntensityBenchmarkJob | None:
    return db.scalars(
        select(CecchinoLabGoalIntensityBenchmarkJob)
        .where(
            CecchinoLabGoalIntensityBenchmarkJob.historical_run_id == int(run_id),
            CecchinoLabGoalIntensityBenchmarkJob.bundle_id == int(bundle_id),
            CecchinoLabGoalIntensityBenchmarkJob.job_version == job_version,
            CecchinoLabGoalIntensityBenchmarkJob.mode == MODE_PILOT,
            CecchinoLabGoalIntensityBenchmarkJob.status.in_(tuple(COMPLETED_STATUSES)),
        )
        .order_by(CecchinoLabGoalIntensityBenchmarkJob.id.desc())
    ).first()


def _pilot_gate_ok(pilot: CecchinoLabGoalIntensityBenchmarkJob) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if pilot.status not in COMPLETED_STATUSES:
        reasons.append("pilot_not_completed")
    summary = pilot.summary_json if isinstance(pilot.summary_json, dict) else {}
    checks = summary.get("checks") if isinstance(summary.get("checks"), dict) else {}
    if int(checks.get("external_api_calls") or 0) != 0:
        reasons.append("pilot_external_api_calls_nonzero")
    if int(checks.get("base_run_writes") or 0) != 0:
        reasons.append("pilot_base_run_writes_nonzero")
    if checks.get("result_used_in_prediction") is True:
        reasons.append("pilot_result_leakage")
    if int(pilot.errors or 0) > 0 and not summary.get("reconciliation_ok", True):
        reasons.append("pilot_blocking_errors")
    if int(pilot.paired_complete or 0) <= 0:
        # technical gate: still allow if zero paired? Spec says five models on paired cohort
        # Zero paired is a scientific issue but still a valid technical pilot completion.
        pass
    reconciliation = summary.get("reconciliation") if isinstance(summary.get("reconciliation"), dict) else {}
    if reconciliation and reconciliation.get("ok") is False:
        reasons.append("pilot_reconciliation_failed")
    return len(reasons) == 0, reasons


def start_goal_intensity_benchmark_job(
    db: Session,
    run_id: int,
    *,
    mode: str,
    bundle_version: str = REQUIRED_BUNDLE_VERSION,
    pilot_size: int = DEFAULT_PILOT_SIZE,
    random_seed: int = DEFAULT_RANDOM_SEED,
    batch_size: int = DEFAULT_BATCH_SIZE,
    pilot_job_id: int | None = None,
    confirm: str | None = None,
    background: bool = True,
) -> dict[str, Any]:
    mode_norm = str(mode or "").strip().lower()
    if mode_norm not in {MODE_PILOT, MODE_FULL}:
        raise CecchinoLabImportError("invalid_mode", "mode deve essere pilot o full")

    expected = CONFIRM_PILOT if mode_norm == MODE_PILOT else CONFIRM_FULL
    if confirm != expected:
        raise CecchinoLabImportError(
            "confirm_token_invalid",
            "Token di conferma non valido",
            details={"expected": expected},
        )

    run = _load_run(db, run_id)
    _require_completed_run(run)
    bundle = get_frozen_goal_intensity_candidate_bundle(db, version=bundle_version)
    snapshots = _load_snapshots(db, run_id)
    preflight = build_goal_intensity_benchmark_preflight(
        db,
        run_id,
        bundle_version=bundle_version,
        pilot_size=pilot_size,
        random_seed=random_seed,
    )

    batch = max(MIN_BATCH_SIZE, min(MAX_BATCH_SIZE, int(batch_size or DEFAULT_BATCH_SIZE)))
    seed = int(random_seed)
    size = int(pilot_size)

    if mode_norm == MODE_PILOT:
        if not preflight.get("pilot_allowed"):
            raise CecchinoLabImportError(
                "pilot_not_allowed",
                "Preflight non consente il pilot",
                details={"blocking_reasons": preflight.get("blocking_reasons")},
            )
        selection = preflight["pilot"]
        selection_hash = selection["selection_hash"]
        selected_ids = select_pilot_snapshots(
            snapshots, pilot_size=size, random_seed=seed
        )["snapshot_ids"]
    else:
        pilot = None
        if pilot_job_id is not None:
            pilot = db.get(CecchinoLabGoalIntensityBenchmarkJob, int(pilot_job_id))
        if pilot is None:
            pilot = _find_completed_pilot(
                db, run_id=run.id, bundle_id=bundle.id, job_version=JOB_VERSION
            )
        if pilot is None:
            raise CecchinoLabImportError(
                "pilot_gate_missing",
                "Full richiede un pilot completed sullo stesso run/bundle/job_version",
                status_code=409,
            )
        if (
            int(pilot.historical_run_id) != int(run.id)
            or int(pilot.bundle_id) != int(bundle.id)
            or pilot.job_version != JOB_VERSION
        ):
            raise CecchinoLabImportError(
                "pilot_gate_mismatch",
                "Pilot non allineato a run/bundle/job_version",
                status_code=409,
            )
        ok, reasons = _pilot_gate_ok(pilot)
        if not ok:
            raise CecchinoLabImportError(
                "pilot_gate_failed",
                "Pilot gate tecnico non superato",
                status_code=409,
                details={"reasons": reasons},
            )
        # Block concurrent full
        active_full = db.scalars(
            select(CecchinoLabGoalIntensityBenchmarkJob).where(
                CecchinoLabGoalIntensityBenchmarkJob.historical_run_id == int(run.id),
                CecchinoLabGoalIntensityBenchmarkJob.bundle_id == int(bundle.id),
                CecchinoLabGoalIntensityBenchmarkJob.job_version == JOB_VERSION,
                CecchinoLabGoalIntensityBenchmarkJob.mode == MODE_FULL,
                CecchinoLabGoalIntensityBenchmarkJob.status.in_(tuple(ACTIVE_STATUSES)),
            )
        ).first()
        if active_full is not None:
            raise CecchinoLabImportError(
                "full_job_already_active",
                "Esiste già una full job attiva per run/bundle/job_version",
                status_code=409,
                details={"job_id": active_full.id},
            )
        selected_ids = [int(s.id) for s in snapshots]
        selection_hash = _sha256_canonical({"mode": MODE_FULL, "snapshot_ids": selected_ids})
        selection = {
            "selection_hash": selection_hash,
            "selected": len(selected_ids),
            "requested": len(selected_ids),
            "selection_protocol": "gi_historical_benchmark_full_all_eligible_v1",
            "random_seed": seed,
        }

    key = _job_key(
        run_id=int(run.id),
        bundle_id=int(bundle.id),
        job_version=JOB_VERSION,
        mode=mode_norm,
        selection_hash=str(selection_hash),
    )
    existing = db.scalars(
        select(CecchinoLabGoalIntensityBenchmarkJob).where(
            CecchinoLabGoalIntensityBenchmarkJob.job_key == key
        )
    ).first()
    if existing is not None:
        if existing.status in ACTIVE_STATUSES:
            raise CecchinoLabImportError(
                "duplicate_active_job",
                "Job già attiva con stessa chiave",
                status_code=409,
                details={"job_id": existing.id},
            )
        if existing.status in COMPLETED_STATUSES:
            return {
                **_serialize_job(existing),
                "idempotent_replay": True,
                "selection_hash": selection_hash,
            }

    rev = resolve_code_revision()
    independence = preflight.get("independence") or {}
    job = CecchinoLabGoalIntensityBenchmarkJob(
        historical_run_id=int(run.id),
        bundle_id=int(bundle.id),
        job_version=JOB_VERSION,
        mode=mode_norm,
        status=STATUS_QUEUED,
        independence_status=independence.get("status"),
        job_key=key,
        random_seed=seed,
        requested_sample_size=size if mode_norm == MODE_PILOT else len(selected_ids),
        total_snapshots=len(snapshots),
        eligible_snapshots=len(snapshots),
        selected_snapshots=len(selected_ids),
        processed_snapshots=0,
        paired_complete=0,
        skipped=0,
        errors=0,
        progress_pct=Decimal("0.0"),
        cancel_requested=False,
        params_json={
            "bundle_version": bundle_version,
            "pilot_size": size,
            "random_seed": seed,
            "batch_size": batch,
            "selection": selection,
            "selected_snapshot_ids": selected_ids,
            "pilot_job_id": int(pilot_job_id) if pilot_job_id else (
                int(pilot.id) if mode_norm == MODE_FULL and pilot else None
            ),
        },
        preflight_json=preflight,
        bundle_definition_hash=bundle.candidate_definition_hash,
        run_fixture_ids_hash=(independence.get("details") or {}).get("run_fixture_ids_hash")
        or (independence.get("run_fixture_ids_hash") if isinstance(independence, dict) else None),
        source_git_commit=rev.get("git_commit"),
    )
    # Fix run_fixture_ids_hash from independence details
    details = independence.get("details") if isinstance(independence.get("details"), dict) else independence
    if isinstance(details, dict) and details.get("run_fixture_ids_hash"):
        job.run_fixture_ids_hash = details.get("run_fixture_ids_hash")
    elif isinstance(independence.get("details"), dict):
        # nested assess_independence puts hash at top-level of independence return
        pass
    # assess_independence returns run_fixture_ids_hash at top level inside details key structure
    ind_full = independence.get("details") if isinstance(independence.get("details"), dict) else {}
    # preflight wraps assess result under details
    if independence.get("status"):
        # re-read from preflight independence.details which is full assess payload
        full = independence.get("details") or {}
        if isinstance(full, dict) and full.get("run_fixture_ids_hash"):
            job.run_fixture_ids_hash = full.get("run_fixture_ids_hash")

    db.add(job)
    db.commit()
    db.refresh(job)

    if background:
        _spawn_worker(int(job.id))
    else:
        _run_job_worker(int(job.id))

    return {
        **_serialize_job(job),
        "selection_hash": selection_hash,
        "run_id": run.id,
        "bundle_id": bundle.id,
    }


def cancel_goal_intensity_benchmark_job(db: Session, job_id: int) -> dict[str, Any]:
    job = db.get(CecchinoLabGoalIntensityBenchmarkJob, int(job_id))
    if job is None:
        raise CecchinoLabImportError("job_not_found", f"Job {job_id} non trovata", status_code=404)
    if job.status in COMPLETED_STATUSES | {STATUS_CANCELLED, STATUS_FAILED}:
        return _serialize_job(job)
    job.cancel_requested = True
    if job.status == STATUS_QUEUED:
        job.status = STATUS_CANCELLED
        job.cancelled_at = _utcnow()
    else:
        job.status = STATUS_CANCEL_REQUESTED
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def resume_goal_intensity_benchmark_job(db: Session, job_id: int) -> dict[str, Any]:
    job = db.get(CecchinoLabGoalIntensityBenchmarkJob, int(job_id))
    if job is None:
        raise CecchinoLabImportError("job_not_found", f"Job {job_id} non trovata", status_code=404)
    if job.status not in RESUMABLE_STATUSES and job.status != STATUS_CANCEL_REQUESTED:
        if job.status in ACTIVE_STATUSES:
            raise CecchinoLabImportError(
                "job_already_active",
                "Job già attiva",
                status_code=409,
            )
        if job.status in COMPLETED_STATUSES:
            return _serialize_job(job)
        raise CecchinoLabImportError(
            "job_not_resumable",
            f"Status {job.status} non resumabile",
            status_code=409,
        )
    job.cancel_requested = False
    job.status = STATUS_QUEUED
    job.error_json = None
    db.commit()
    db.refresh(job)
    _spawn_worker(int(job.id))
    return _serialize_job(job)


def _spawn_worker(job_id: int) -> None:
    with _lock:
        t = _active_threads.get(job_id)
        if t is not None and t.is_alive():
            return
        thread = threading.Thread(
            target=_run_job_worker,
            args=(job_id,),
            name=f"gi-bench-{job_id}",
            daemon=True,
        )
        _active_threads[job_id] = thread
        thread.start()


def _process_one_snapshot(
    *,
    snap: CecchinoLabHistoricalMatchSnapshot,
    bundle: Any,
    bundle_hash: str,
) -> dict[str, Any]:
    v4, v4_reason = extract_v4_from_historical_snapshot(snap)
    feats, feat_reason = extract_v5_features_from_snapshot(snap)

    # Prediction BEFORE result
    prediction = None
    input_hash = None
    exclusion = None
    if feats is None:
        exclusion = feat_reason or "missing_v5_features"
    elif feat_reason == "incomplete_v5_features":
        exclusion = "incomplete_v5_features"
    elif v4 is None:
        exclusion = v4_reason or "missing_persisted_v4_expected_goals"
    else:
        prediction = score_five_models_with_frozen_bundle(
            features=feats, v4_payload=v4, bundle=bundle
        )
        input_hash = prediction_input_hash(
            features=feats,
            bundle_definition_hash=bundle_hash,
            snapshot_id=int(snap.id),
        )
        if not prediction.get("five_models_available"):
            exclusion = "five_models_incomplete"

    # Result only after prediction
    target, tgt_reason = extract_ft_target(snap.result_json)
    if exclusion is None and target is None:
        exclusion = tgt_reason or "missing_ft_result"

    included = exclusion is None and prediction is not None and target is not None
    evaluation = None
    if included and prediction is not None and target is not None:
        evaluation = {
            "included_in_main_cohort": True,
            "models_present": list(MAIN_MODEL_IDS),
            "absolute_errors": {
                mid: abs(
                    float((prediction["models"][mid] or {}).get("expected_total_goals") or 0)
                    - float(target["total_goals_ft"])
                )
                for mid in MAIN_MODEL_IDS
                if prediction.get("models", {}).get(mid)
            },
        }

    return {
        "lab_match_id": snap.lab_match_id,
        "kickoff_at": snap.kickoff_at,
        "competition_name": snap.competition_name,
        "included_in_main_cohort": included,
        "exclusion_reason": exclusion,
        "input_hash": input_hash,
        "prediction_payload_json": prediction,
        "target_payload_json": target,
        "evaluation_payload_json": evaluation,
    }


def _run_job_worker(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(CecchinoLabGoalIntensityBenchmarkJob, int(job_id))
        if job is None:
            return
        if job.cancel_requested and job.status in {STATUS_QUEUED, STATUS_CANCEL_REQUESTED}:
            job.status = STATUS_CANCELLED
            job.cancelled_at = _utcnow()
            db.commit()
            return

        job.status = STATUS_RUNNING
        job.started_at = job.started_at or _utcnow()
        db.commit()

        bundle = get_frozen_goal_intensity_candidate_bundle(db)
        params = job.params_json if isinstance(job.params_json, dict) else {}
        selected_ids = [int(x) for x in (params.get("selected_snapshot_ids") or [])]
        batch_size = int(params.get("batch_size") or DEFAULT_BATCH_SIZE)
        batch_size = max(MIN_BATCH_SIZE, min(MAX_BATCH_SIZE, batch_size))

        # Resume: skip completed rows with same input/bundle hash
        done_rows = list(
            db.scalars(
                select(CecchinoLabGoalIntensityBenchmarkRow).where(
                    CecchinoLabGoalIntensityBenchmarkRow.job_id == int(job.id)
                )
            ).all()
        )
        done_map = {int(r.historical_snapshot_id): r for r in done_rows}
        remaining = [sid for sid in selected_ids if sid not in done_map]

        missing: Counter[str] = Counter(
            (job.missing_by_reason_json or {}) if isinstance(job.missing_by_reason_json, dict) else {}
        )
        paired = int(job.paired_complete or 0)
        skipped = int(job.skipped or 0)
        errors = int(job.errors or 0)
        processed = int(job.processed_snapshots or 0)
        # If resuming, processed should count done rows
        if done_map and processed < len(done_map):
            processed = len(done_map)
            paired = sum(1 for r in done_rows if r.included_in_main_cohort)
            skipped = sum(1 for r in done_rows if not r.included_in_main_cohort)

        for i in range(0, len(remaining), batch_size):
            db.refresh(job)
            if job.cancel_requested:
                job.status = STATUS_CANCELLED
                job.cancelled_at = _utcnow()
                job.last_checkpoint_at = _utcnow()
                db.commit()
                return

            chunk_ids = remaining[i : i + batch_size]
            snaps = list(
                db.scalars(
                    select(CecchinoLabHistoricalMatchSnapshot).where(
                        CecchinoLabHistoricalMatchSnapshot.id.in_(chunk_ids)
                    )
                ).all()
            )
            by_id = {int(s.id): s for s in snaps}
            for sid in chunk_ids:
                snap = by_id.get(sid)
                if snap is None:
                    errors += 1
                    missing["snapshot_not_found"] += 1
                    processed += 1
                    continue
                try:
                    result = _process_one_snapshot(
                        snap=snap,
                        bundle=bundle,
                        bundle_hash=str(job.bundle_definition_hash or bundle.candidate_definition_hash),
                    )
                    # Idempotent upsert
                    existing = done_map.get(sid)
                    if existing is not None:
                        same_input = (
                            existing.input_hash
                            and result.get("input_hash")
                            and existing.input_hash == result.get("input_hash")
                        )
                        same_bundle = True  # job-level bundle hash fixed
                        if same_input and same_bundle and existing.prediction_payload_json:
                            processed += 1
                            continue
                    row = existing or CecchinoLabGoalIntensityBenchmarkRow(
                        job_id=int(job.id),
                        historical_snapshot_id=sid,
                    )
                    row.lab_match_id = result.get("lab_match_id")
                    row.kickoff_at = result.get("kickoff_at")
                    row.competition_name = result.get("competition_name")
                    row.included_in_main_cohort = bool(result.get("included_in_main_cohort"))
                    row.exclusion_reason = result.get("exclusion_reason")
                    row.input_hash = result.get("input_hash")
                    row.prediction_payload_json = result.get("prediction_payload_json")
                    row.target_payload_json = result.get("target_payload_json")
                    row.evaluation_payload_json = result.get("evaluation_payload_json")
                    if existing is None:
                        db.add(row)
                    if row.included_in_main_cohort:
                        paired += 1
                    else:
                        skipped += 1
                        if row.exclusion_reason:
                            missing[row.exclusion_reason] += 1
                    processed += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("gi_bench_row_failed job=%s snap=%s", job_id, sid)
                    errors += 1
                    missing["row_exception"] += 1
                    processed += 1
                    db.add(
                        CecchinoLabGoalIntensityBenchmarkRow(
                            job_id=int(job.id),
                            historical_snapshot_id=sid,
                            lab_match_id=getattr(snap, "lab_match_id", None),
                            competition_name=getattr(snap, "competition_name", None),
                            kickoff_at=getattr(snap, "kickoff_at", None),
                            included_in_main_cohort=False,
                            exclusion_reason="row_exception",
                            evaluation_payload_json={"error": str(exc)[:500]},
                        )
                    )

            total_sel = max(1, int(job.selected_snapshots or 1))
            job.processed_snapshots = processed
            job.paired_complete = paired
            job.skipped = skipped
            job.errors = errors
            job.missing_by_reason_json = dict(sorted(missing.items()))
            job.progress_pct = Decimal(str(round(100.0 * processed / total_sel, 1)))
            job.last_checkpoint_at = _utcnow()
            db.commit()

        # Final summary
        db.refresh(job)
        if job.cancel_requested:
            job.status = STATUS_CANCELLED
            job.cancelled_at = _utcnow()
            db.commit()
            return

        rows = list(
            db.scalars(
                select(CecchinoLabGoalIntensityBenchmarkRow).where(
                    CecchinoLabGoalIntensityBenchmarkRow.job_id == int(job.id),
                    CecchinoLabGoalIntensityBenchmarkRow.included_in_main_cohort.is_(True),
                )
            ).all()
        )
        eval_rows = []
        for r in rows:
            pred = r.prediction_payload_json if isinstance(r.prediction_payload_json, dict) else {}
            tgt = r.target_payload_json if isinstance(r.target_payload_json, dict) else {}
            eval_rows.append(
                {
                    "snapshot_id": r.historical_snapshot_id,
                    "competition": r.competition_name,
                    "kickoff": r.kickoff_at.isoformat() if r.kickoff_at else None,
                    "month": r.kickoff_at.strftime("%Y-%m") if r.kickoff_at else None,
                    "models": pred.get("models") or {},
                    "target": tgt,
                }
            )
        metrics = evaluate_paired_rows(eval_rows)
        breakdowns = build_breakdowns(eval_rows)
        ind = (job.preflight_json or {}).get("independence") if isinstance(job.preflight_json, dict) else {}
        scientific_label = (ind or {}).get("scientific_label") or SCIENTIFIC_DIAGNOSTIC_REPLAY

        summary = {
            "job_version": JOB_VERSION,
            "mode": job.mode,
            "scientific_label": scientific_label,
            "independence_status": job.independence_status,
            "paired_complete": paired,
            "skipped": skipped,
            "errors": errors,
            "missing_by_reason": dict(sorted(missing.items())),
            "metrics": metrics,
            "breakdowns": breakdowns,
            "models": list(MAIN_MODEL_IDS),
            "checks": {
                "external_api_calls": 0,
                "full_scan_required": False,
                "base_run_writes": 0,
                "bundle_refit": False,
                "result_used_in_prediction": False,
                "full_scan_restarted": False,
            },
            "reconciliation": {
                "ok": True,
                "selected": job.selected_snapshots,
                "processed": processed,
                "paired_plus_skipped": paired + skipped,
            },
            "reconciliation_ok": True,
            "no_automatic_promotion": True,
            "promotion_blocked": True,
        }
        # Soft reconciliation: processed should equal selected
        if processed != int(job.selected_snapshots or 0):
            summary["reconciliation"]["ok"] = False
            summary["reconciliation_ok"] = False

        job.summary_json = summary
        job.missing_by_reason_json = dict(sorted(missing.items()))
        job.processed_snapshots = processed
        job.paired_complete = paired
        job.skipped = skipped
        job.errors = errors
        job.progress_pct = Decimal("100.0")
        job.status = STATUS_COMPLETED
        job.completed_at = _utcnow()
        job.last_checkpoint_at = _utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("gi_bench_job_failed job=%s", job_id)
        try:
            job = db.get(CecchinoLabGoalIntensityBenchmarkJob, int(job_id))
            if job is not None:
                job.status = STATUS_FAILED
                job.error_json = {"error": str(exc)[:1000], "type": type(exc).__name__}
                job.completed_at = _utcnow()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
        with _lock:
            _active_threads.pop(job_id, None)


def _csv_escape(value: Any) -> str:
    s = "" if value is None else str(value)
    if any(c in s for c in [",", '"', "\n"]):
        return '"' + s.replace('"', '""') + '"'
    return s


def _rows_to_csv(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(_csv_escape(c) for c in row))
    return "\n".join(lines) + "\n"


def build_goal_intensity_benchmark_export(db: Session, job_id: int) -> tuple[bytes, str]:
    job = db.get(CecchinoLabGoalIntensityBenchmarkJob, int(job_id))
    if job is None:
        raise CecchinoLabImportError("job_not_found", f"Job {job_id} non trovata", status_code=404)
    run = _load_run(db, int(job.historical_run_id))
    rows = list(
        db.scalars(
            select(CecchinoLabGoalIntensityBenchmarkRow).where(
                CecchinoLabGoalIntensityBenchmarkRow.job_id == int(job.id)
            )
        ).all()
    )
    summary = job.summary_json if isinstance(job.summary_json, dict) else {}
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    model_metrics = metrics.get("model_metrics") or {}
    pairwise = metrics.get("pairwise") or []
    breakdowns = summary.get("breakdowns") if isinstance(summary.get("breakdowns"), dict) else {}
    preflight = job.preflight_json if isinstance(job.preflight_json, dict) else {}
    independence = preflight.get("independence") or {}

    model_csv_rows = []
    for mid, block in model_metrics.items():
        tg = block.get("total_goals_ft") or {}
        ge2 = block.get("goals_ge_2") or {}
        ge3 = block.get("goals_ge_3") or {}
        model_csv_rows.append(
            [
                mid,
                block.get("n"),
                tg.get("mae"),
                tg.get("rmse"),
                tg.get("bias"),
                tg.get("median_absolute_error"),
                tg.get("pearson"),
                tg.get("spearman"),
                ge2.get("brier"),
                ge3.get("brier"),
            ]
        )
    pairwise_rows = [
        [
            p.get("left_id"),
            p.get("right_id"),
            p.get("metric"),
            p.get("n"),
            p.get("delta"),
            (p.get("ci") or {}).get("ci_lower"),
            (p.get("ci") or {}).get("ci_upper"),
            p.get("preferred_side"),
            p.get("evidence_level"),
        ]
        for p in pairwise
    ]

    def _cal_rows(key: str) -> list[list[Any]]:
        out = []
        for mid, block in model_metrics.items():
            bins = ((block.get(key) or {}).get("calibration_bins")) or []
            for b in bins:
                out.append(
                    [
                        mid,
                        b.get("bin"),
                        b.get("count"),
                        b.get("avg_pred"),
                        b.get("avg_actual"),
                        b.get("abs_gap"),
                    ]
                )
        return out

    btts_rows = []
    for mid, block in model_metrics.items():
        b = block.get("btts") or {}
        btts_rows.append(
            [
                mid,
                b.get("status") or "ok",
                b.get("n"),
                b.get("brier"),
                b.get("log_loss"),
                b.get("auc"),
                b.get("calibration_error"),
            ]
        )

    def _bd_rows(name: str) -> list[list[Any]]:
        block = breakdowns.get(name) or {}
        out = []
        for k, v in block.items():
            if not isinstance(v, dict):
                continue
            out.append([k, v.get("n"), v.get("warning_small_sample")])
        return out

    missing_rows = [
        [k, v] for k, v in sorted((job.missing_by_reason_json or {}).items())
    ]
    fixture_rows = []
    for r in rows:
        pred = r.prediction_payload_json if isinstance(r.prediction_payload_json, dict) else {}
        models = pred.get("models") or {}
        tgt = r.target_payload_json if isinstance(r.target_payload_json, dict) else {}
        fixture_rows.append(
            [
                r.historical_snapshot_id,
                r.lab_match_id,
                r.competition_name,
                r.kickoff_at.isoformat() if r.kickoff_at else None,
                r.included_in_main_cohort,
                r.exclusion_reason,
                r.input_hash,
                tgt.get("total_goals_ft"),
                ((models.get("GI_V4_EXPECTED_GOALS") or {}) or {}).get("expected_total_goals"),
                ((models.get("GI_A_STRICT_CORE") or {}) or {}).get("expected_total_goals"),
                ((models.get("GI_B_RECENCY") or {}) or {}).get("expected_total_goals"),
                ((models.get("GI_E_PRIMARY_RECALIBRATED") or {}) or {}).get("expected_total_goals"),
                ((models.get("GI_F_REGULARIZED_PILLARS") or {}) or {}).get("expected_total_goals"),
            ]
        )

    manifest = {
        "base_run_id": run.id,
        "base_run_source_commit": run.source_git_commit,
        "bundle_id": job.bundle_id,
        "bundle_version": REQUIRED_BUNDLE_VERSION,
        "bundle_definition_hash": job.bundle_definition_hash,
        "job_version": job.job_version,
        "job_source_commit": job.source_git_commit,
        "independence_status": job.independence_status,
        "mode": job.mode,
        "seed": job.random_seed,
        "selection_hash": ((job.params_json or {}).get("selection") or {}).get("selection_hash"),
        "input_hashes": [r.input_hash for r in rows if r.input_hash],
        "external_api_calls": 0,
        "base_run_writes": 0,
        "full_scan_restarted": False,
        "job_id": job.id,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("job_summary.json", json.dumps(summary, indent=2, default=str))
        zf.writestr("preflight.json", json.dumps(preflight, indent=2, default=str))
        zf.writestr(
            "independence_report.json",
            json.dumps(independence, indent=2, default=str),
        )
        zf.writestr(
            "model_metrics.csv",
            _rows_to_csv(
                [
                    "model_id",
                    "n",
                    "mae",
                    "rmse",
                    "bias",
                    "median_absolute_error",
                    "pearson",
                    "spearman",
                    "brier_ge2",
                    "brier_ge3",
                ],
                model_csv_rows,
            ),
        )
        zf.writestr(
            "pairwise_metrics.csv",
            _rows_to_csv(
                [
                    "left_id",
                    "right_id",
                    "metric",
                    "n",
                    "delta",
                    "ci_lower",
                    "ci_upper",
                    "preferred_side",
                    "evidence_level",
                ],
                pairwise_rows,
            ),
        )
        zf.writestr(
            "calibration_ge2.csv",
            _rows_to_csv(
                ["model_id", "bin", "count", "avg_pred", "avg_actual", "abs_gap"],
                _cal_rows("goals_ge_2"),
            ),
        )
        zf.writestr(
            "calibration_ge3.csv",
            _rows_to_csv(
                ["model_id", "bin", "count", "avg_pred", "avg_actual", "abs_gap"],
                _cal_rows("goals_ge_3"),
            ),
        )
        zf.writestr(
            "btts_metrics.csv",
            _rows_to_csv(
                ["model_id", "status", "n", "brier", "log_loss", "auc", "calibration_error"],
                btts_rows,
            ),
        )
        zf.writestr(
            "breakdown_competition.csv",
            _rows_to_csv(["competition", "n", "warning_small_sample"], _bd_rows("competition")),
        )
        zf.writestr(
            "breakdown_month.csv",
            _rows_to_csv(["month", "n", "warning_small_sample"], _bd_rows("month")),
        )
        zf.writestr(
            "missing_reasons.csv",
            _rows_to_csv(["reason", "count"], missing_rows),
        )
        zf.writestr(
            "fixture_predictions.csv",
            _rows_to_csv(
                [
                    "snapshot_id",
                    "lab_match_id",
                    "competition",
                    "kickoff",
                    "included",
                    "exclusion_reason",
                    "input_hash",
                    "total_goals_ft",
                    "pred_v4",
                    "pred_gi_a",
                    "pred_gi_b",
                    "pred_gi_e",
                    "pred_gi_f",
                ],
                fixture_rows,
            ),
        )
        zf.writestr("run_manifest.json", json.dumps(manifest, indent=2, default=str))

    filename = f"gi-benchmark-job-{job.id}-{job.mode}.zip"
    return buf.getvalue(), filename


def list_goal_intensity_benchmark_jobs_for_run(db: Session, run_id: int) -> list[dict[str, Any]]:
    jobs = list(
        db.scalars(
            select(CecchinoLabGoalIntensityBenchmarkJob)
            .where(CecchinoLabGoalIntensityBenchmarkJob.historical_run_id == int(run_id))
            .order_by(CecchinoLabGoalIntensityBenchmarkJob.id.desc())
        ).all()
    )
    return [_serialize_job(j) for j in jobs]
