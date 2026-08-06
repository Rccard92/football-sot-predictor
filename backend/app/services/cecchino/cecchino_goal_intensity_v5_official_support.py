"""Phase 2D — finalizzazione modulo ufficiale Intensità Goal V5 (supporto contestuale).

Un solo raw score GI_A_STRICT_CORE; teste target-specifiche (GI_A / GI_E) copiate
dal bundle candidate v2.1 senza refit. Nessun blending. Signals blocked.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    BUNDLE_STATUS_ACTIVE,
    BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
    BUNDLE_STATUS_SUPERSEDED,
    PREVIEW_BUNDLE_VERSION,
    CecchinoGoalIntensityV5PreviewBundle,
)
from app.models.cecchino_lab_goal_intensity_benchmark_job import (
    JOB_VERSION as BENCHMARK_JOB_VERSION,
    MODE_FULL,
    MODE_PILOT,
    REQUIRED_BUNDLE_VERSION,
    STATUS_COMPLETED,
    CecchinoLabGoalIntensityBenchmarkJob,
)
from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import (
    ACTIVE_CANDIDATE_IDS as PHASE_2C_ACTIVE_IDS,
    ARCHIVED_CANDIDATE_IDS as PHASE_2C_ARCHIVED_IDS,
    GI_E_ID,
    GI_F_ID,
    TARGET_BUNDLE_VERSION as CANDIDATE_BUNDLE_VERSION,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    PRIMARY_ID,
    _apply_linear,
    _apply_logistic,
    _ecdfs_from_bundle,
    _round,
)
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    _composite_scores,
    _pillar_scores_from_pct,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import safe_float
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_scoring import (
    MAIN_MODEL_IDS,
    validate_frozen_candidate_bundle,
)

# ---------------------------------------------------------------------------
# Canonical versions
# ---------------------------------------------------------------------------

OFFICIAL_MODULE_VERSION = "cecchino_goal_intensity_v5_official_support_v1"
OFFICIAL_BUNDLE_VERSION = "cecchino_goal_intensity_v5_official_support_bundle_v1"
OFFICIAL_SCORING_VERSION = "cecchino_goal_intensity_v5_official_support_scoring_v1"
OFFICIAL_AUDIT_VERSION = "cecchino_goal_intensity_v5_official_support_explanations_v1"
FINALIZATION_VERSION = "cecchino_goal_intensity_v5_phase_2d_finalization_v1"
FREEZE_CONFIRM_TOKEN = "FREEZE_GOAL_INTENSITY_V5_OFFICIAL_SUPPORT_V1"

RAW_INDEX_ID = PRIMARY_ID  # GI_A_STRICT_CORE
OPERATIONAL_CALIBRATION_KEY = "OFFICIAL_SUPPORT"

OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS = (
    "home_goals_scored_avg",
    "home_goals_conceded_avg",
    "away_goals_conceded_avg",
    "total_goals_avg",
    "goals_scored_std_last_10",
)

# Target → calibration source candidate id (coefficients copied, never refit)
TARGET_CALIBRATION_MAPPING: dict[str, str] = {
    "total_goals_ft": GI_E_ID,
    "goals_ge_2": RAW_INDEX_ID,
    "goals_ge_3": GI_E_ID,
    "btts_ft": GI_E_ID,
}

ARCHIVED_FROM_OPERATIONAL = (
    "GI_B_RECENCY",
    GI_F_ID,
    "MT1_LONG_TERM",
    "GI_A_without_volatility",
)

CUTOVER_MODE = "strict_after_official_freeze"
ROLE = "contextual_support_only"
OPERATIONAL_STATUS = "official_support"
SIGNALS_INTEGRATION_STATUS = "blocked"

FEATURE_STATUS_COMPLETE = "official_v5_complete"
FEATURE_STATUS_FALLBACK_V4 = "fallback_v4"
FEATURE_STATUS_UNAVAILABLE = "unavailable"
FALLBACK_REASON_FEATURES_INCOMPLETE = "official_v5_features_incomplete"


def _sha256_canonical(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _copy_cal_head(src: dict[str, Any] | None, *, calibration_source: str) -> dict[str, Any] | None:
    if not isinstance(src, dict):
        return None
    out = copy.deepcopy(src)
    out["calibration_source"] = calibration_source
    out["copied_without_refit"] = True
    return out


def get_bundle_by_version(
    db: Session,
    version: str,
    *,
    require_active: bool | None = None,
) -> CecchinoGoalIntensityV5PreviewBundle | None:
    """Loader esatto per versione (mai usato per reinterpretare snapshot di altri bundle)."""
    q = select(CecchinoGoalIntensityV5PreviewBundle).where(
        CecchinoGoalIntensityV5PreviewBundle.version == version
    )
    if require_active is True:
        q = q.where(
            CecchinoGoalIntensityV5PreviewBundle.is_active.is_(True),
            CecchinoGoalIntensityV5PreviewBundle.status == BUNDLE_STATUS_ACTIVE,
        )
    elif require_active is False:
        q = q.where(CecchinoGoalIntensityV5PreviewBundle.is_active.is_(False))
    return db.scalars(q.order_by(CecchinoGoalIntensityV5PreviewBundle.id.desc())).first()


def get_bundle_by_id(db: Session, bundle_id: int) -> CecchinoGoalIntensityV5PreviewBundle | None:
    return db.get(CecchinoGoalIntensityV5PreviewBundle, int(bundle_id))


def get_candidate_bundle_v2_1(db: Session) -> CecchinoGoalIntensityV5PreviewBundle | None:
    return get_bundle_by_version(db, CANDIDATE_BUNDLE_VERSION)


def get_preview_bundle_v1_1(db: Session) -> CecchinoGoalIntensityV5PreviewBundle | None:
    return get_bundle_by_version(db, PREVIEW_BUNDLE_VERSION)


def is_official_bundle(bundle: CecchinoGoalIntensityV5PreviewBundle | None) -> bool:
    return bool(
        bundle is not None and getattr(bundle, "version", None) == OFFICIAL_BUNDLE_VERSION
    )


def is_legacy_preview_bundle(bundle: CecchinoGoalIntensityV5PreviewBundle | None) -> bool:
    return bool(
        bundle is not None and getattr(bundle, "version", None) == PREVIEW_BUNDLE_VERSION
    )


# ---------------------------------------------------------------------------
# Benchmark job validation (benchmark_job_id is always an explicit argument)
# ---------------------------------------------------------------------------


def validate_benchmark_job_for_finalization(
    db: Session,
    benchmark_job_id: int,
    *,
    candidate_bundle: CecchinoGoalIntensityV5PreviewBundle | None = None,
) -> dict[str, Any]:
    """Verifica Job benchmark per freeze ufficiale. Non hardcodare l'id nel servizio."""
    blocking: list[str] = []
    warnings: list[str] = []

    job = db.get(CecchinoLabGoalIntensityBenchmarkJob, int(benchmark_job_id))
    if job is None:
        return make_json_safe(
            {
                "ok": False,
                "benchmark_job_id": int(benchmark_job_id),
                "blocking_reasons": ["benchmark_job_not_found"],
                "job": None,
            }
        )

    summary = job.summary_json if isinstance(job.summary_json, dict) else {}
    recon = summary.get("reconciliation") if isinstance(summary.get("reconciliation"), dict) else {}
    checks = summary.get("checks") if isinstance(summary.get("checks"), dict) else {}
    scientific_label = summary.get("scientific_label")

    if job.mode == MODE_PILOT:
        blocking.append("pilot_job_rejected")
    if job.mode != MODE_FULL:
        blocking.append("mode_not_full")
    if job.status != STATUS_COMPLETED:
        blocking.append("job_not_completed")
    if job.job_version != BENCHMARK_JOB_VERSION:
        blocking.append("job_version_mismatch")

    if job.independence_status != "external_independent":
        blocking.append("independence_not_external")
    if scientific_label != "external_validation":
        blocking.append("scientific_label_not_external_validation")

    selected = int(job.selected_snapshots or 0)
    processed = int(job.processed_snapshots or 0)
    paired = int(job.paired_complete or 0)
    errors = int(job.errors or 0)
    if processed != selected:
        blocking.append("processed_ne_selected")
    if errors != 0:
        blocking.append("job_has_errors")
    if paired <= 0:
        blocking.append("paired_complete_zero")

    recon_ok = bool(recon.get("ok") is True or summary.get("reconciliation_ok") is True)
    if not recon_ok:
        blocking.append("reconciliation_not_ok")
    if int(recon.get("duplicate_rows") or 0) != 0:
        blocking.append("duplicate_rows_nonzero")
    if recon.get("all_paired_have_five_models") is not True:
        blocking.append("not_all_paired_have_five_models")

    if int(checks.get("external_api_calls") or 0) != 0:
        blocking.append("external_api_calls_nonzero")
    if int(checks.get("base_run_writes") or 0) != 0:
        blocking.append("base_run_writes_nonzero")
    if checks.get("bundle_refit") is True:
        blocking.append("bundle_refit_true")
    if checks.get("result_used_in_prediction") is True:
        blocking.append("result_used_in_prediction")

    models = list(summary.get("models") or [])
    model_metrics = (summary.get("metrics") or {}).get("model_metrics") or {}
    expected_models = list(MAIN_MODEL_IDS)
    missing_models = [m for m in expected_models if m not in models and m not in model_metrics]
    if missing_models:
        blocking.append("summary_models_incomplete")

    candidate = candidate_bundle or get_candidate_bundle_v2_1(db)
    if candidate is None:
        blocking.append("candidate_bundle_missing")
    else:
        try:
            validate_frozen_candidate_bundle(candidate)
        except Exception as exc:
            blocking.append(f"candidate_bundle_invalid:{getattr(exc, 'code', type(exc).__name__)}")
        if job.bundle_id != candidate.id:
            blocking.append("job_bundle_id_mismatch")
        if candidate.version != CANDIDATE_BUNDLE_VERSION or candidate.version != REQUIRED_BUNDLE_VERSION:
            # REQUIRED_BUNDLE_VERSION == CANDIDATE_BUNDLE_VERSION by design
            if candidate.version != CANDIDATE_BUNDLE_VERSION:
                blocking.append("candidate_version_mismatch")
        if job.bundle_definition_hash and job.bundle_definition_hash != candidate.candidate_definition_hash:
            blocking.append("bundle_definition_hash_mismatch")

    return make_json_safe(
        {
            "ok": len(blocking) == 0,
            "benchmark_job_id": int(benchmark_job_id),
            "blocking_reasons": blocking,
            "warnings": warnings,
            "job": {
                "id": job.id,
                "mode": job.mode,
                "status": job.status,
                "job_version": job.job_version,
                "independence_status": job.independence_status,
                "scientific_label": scientific_label,
                "bundle_id": job.bundle_id,
                "bundle_definition_hash": job.bundle_definition_hash,
                "selected_snapshots": selected,
                "processed_snapshots": processed,
                "paired_complete": paired,
                "skipped": int(job.skipped or 0),
                "errors": errors,
                "reconciliation": recon,
                "reconciliation_ok": recon_ok,
                "checks": checks,
                "models": models or list(model_metrics.keys()),
                "historical_run_id": job.historical_run_id,
            },
            "candidate_bundle": (
                {
                    "id": candidate.id,
                    "version": candidate.version,
                    "status": candidate.status,
                    "is_active": candidate.is_active,
                    "definition_hash": candidate.candidate_definition_hash,
                }
                if candidate is not None
                else None
            ),
        }
    )


def build_operational_calibration_payload(
    candidate: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    """Copia coefficienti target-specifici senza refit / blending."""
    cal_all = candidate.calibration_payload or {}
    gi_a = cal_all.get(RAW_INDEX_ID) or {}
    gi_e = cal_all.get(GI_E_ID) or {}
    source_by_target = {
        "total_goals_ft": gi_e.get("total_goals_ft"),
        "goals_ge_2": gi_a.get("goals_ge_2"),
        "goals_ge_3": gi_e.get("goals_ge_3"),
        "btts_ft": gi_e.get("btts_ft"),
    }
    operational: dict[str, Any] = {}
    for target, src_id in TARGET_CALIBRATION_MAPPING.items():
        head = _copy_cal_head(source_by_target.get(target), calibration_source=src_id)
        if head is None:
            raise ValueError(f"missing_calibration_head:{target}:{src_id}")
        operational[target] = head
    return {
        OPERATIONAL_CALIBRATION_KEY: operational,
        # Provenance copies (not used for live scoring heads)
        "_source_calibrations": {
            RAW_INDEX_ID: copy.deepcopy(gi_a),
            GI_E_ID: copy.deepcopy(gi_e),
        },
        "target_calibration_mapping": dict(TARGET_CALIBRATION_MAPPING),
        "no_refit": True,
        "no_blending": True,
    }


def build_official_definition_hash(
    *,
    source_candidate_hash: str,
    operational_calibration: dict[str, Any],
    benchmark_job_id: int,
    benchmark_job_version: str,
    source_git_commit: str | None,
) -> str:
    effective_coefs = {
        target: {
            "calibration_source": (operational_calibration.get(OPERATIONAL_CALIBRATION_KEY) or {})
            .get(target, {})
            .get("calibration_source"),
            "intercept": (operational_calibration.get(OPERATIONAL_CALIBRATION_KEY) or {})
            .get(target, {})
            .get("intercept"),
            "coefficient": (operational_calibration.get(OPERATIONAL_CALIBRATION_KEY) or {})
            .get(target, {})
            .get("coefficient"),
        }
        for target in TARGET_CALIBRATION_MAPPING
    }
    return _sha256_canonical(
        {
            "finalization_version": FINALIZATION_VERSION,
            "module_version": OFFICIAL_MODULE_VERSION,
            "bundle_version": OFFICIAL_BUNDLE_VERSION,
            "scoring_version": OFFICIAL_SCORING_VERSION,
            "source_candidate_bundle_hash": source_candidate_hash,
            "raw_index": {
                "id": RAW_INDEX_ID,
                "components": [
                    "OP1_HOME_LONG_TERM",
                    "DV1_MEAN_CONCEDED",
                    "MT1_LONG_TERM",
                    "OV1_STD",
                ],
                "formula": "mean(OP1, DV1, MT1, OV1)",
            },
            "target_calibration_mapping": dict(TARGET_CALIBRATION_MAPPING),
            "effective_coefficients": effective_coefs,
            "required_feature_keys": list(OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS),
            "benchmark_job_id": int(benchmark_job_id),
            "benchmark_job_version": benchmark_job_version,
            "role": ROLE,
            "signals_integration_status": SIGNALS_INTEGRATION_STATUS,
            "cutover_mode": CUTOVER_MODE,
            "no_refit": True,
            "no_backfill": True,
            "source_git_commit": source_git_commit,
        }
    )


def build_official_bundle_payload(
    *,
    candidate: CecchinoGoalIntensityV5PreviewBundle,
    preview: CecchinoGoalIntensityV5PreviewBundle | None,
    job_validation: dict[str, Any],
    source_git_commit: str | None = None,
) -> dict[str, Any]:
    operational_cal = build_operational_calibration_payload(candidate)
    job_info = job_validation.get("job") or {}
    def_hash = build_official_definition_hash(
        source_candidate_hash=candidate.candidate_definition_hash,
        operational_calibration=operational_cal,
        benchmark_job_id=int(job_info.get("id") or 0),
        benchmark_job_version=str(job_info.get("job_version") or BENCHMARK_JOB_VERSION),
        source_git_commit=source_git_commit,
    )
    now_iso = _utc_now().isoformat()
    norm = copy.deepcopy(candidate.normalization_payload or {})
    # Keep all ECDF distributions for reproducibility; declare only GI_A features required.
    norm["required_feature_keys"] = list(OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS)
    norm["copied_from_candidate_bundle"] = True
    norm["source_candidate_version"] = candidate.version
    norm["no_ecdf_refit"] = True

    definitions = {
        "module_version": OFFICIAL_MODULE_VERSION,
        "scoring_version": OFFICIAL_SCORING_VERSION,
        "audit_version": OFFICIAL_AUDIT_VERSION,
        "finalization_version": FINALIZATION_VERSION,
        "raw_index_definition": {
            "id": RAW_INDEX_ID,
            "components": [
                "OP1_HOME_LONG_TERM",
                "DV1_MEAN_CONCEDED",
                "MT1_LONG_TERM",
                "OV1_STD",
            ],
            "formula": "mean(OP1, DV1, MT1, OV1)",
            "raw_GI_E": "identical_to_GI_A_STRICT_CORE",
        },
        "target_head_mapping": dict(TARGET_CALIBRATION_MAPPING),
        "required_feature_keys": list(OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS),
        "source_candidate_bundle_id": candidate.id,
        "source_candidate_bundle_version": candidate.version,
        "source_candidate_bundle_hash": candidate.candidate_definition_hash,
        "benchmark_job_id": job_info.get("id"),
        "benchmark_job_version": job_info.get("job_version"),
        "benchmark_independence_status": job_info.get("independence_status"),
        "benchmark_scientific_label": job_info.get("scientific_label"),
        "benchmark_paired_count": job_info.get("paired_complete"),
        "benchmark_reconciliation": job_info.get("reconciliation"),
        "selected_candidates": {
            "raw_index": RAW_INDEX_ID,
            "calibration_specialists": {
                "total_goals_ft": GI_E_ID,
                "goals_ge_2": RAW_INDEX_ID,
                "goals_ge_3": GI_E_ID,
                "btts_ft": GI_E_ID,
            },
        },
        "archived_candidates": list(ARCHIVED_FROM_OPERATIONAL),
        "phase_2c_active_ids_preserved_in_source": list(PHASE_2C_ACTIVE_IDS),
        "phase_2c_archived_ids_preserved_in_source": list(PHASE_2C_ARCHIVED_IDS),
        "intended_use": "official_contextual_support",
        "role": ROLE,
        "operational_status": OPERATIONAL_STATUS,
        "signals_integration_status": SIGNALS_INTEGRATION_STATUS,
        "signals_integration_enabled": False,
        "live_scoring_enabled": True,
        "cutover_mode": CUTOVER_MODE,
        "no_backfill": True,
        "no_refit": True,
        "no_blending": True,
        "fallback_policy": {
            "v4_atomic": True,
            "reason_code": FALLBACK_REASON_FEATURES_INCOMPLETE,
            "btts_unavailable_on_fallback": True,
            "no_target_mix": True,
        },
        "preview_parent_bundle_id": preview.id if preview else None,
        "preview_parent_bundle_version": preview.version if preview else PREVIEW_BUNDLE_VERSION,
        "source_git_commit": source_git_commit,
        "cutover_timestamp": now_iso,
        "provenance": {
            "external_validation_job_id": job_info.get("id"),
            "source_candidate_unchanged": True,
            "coefficients_copied_without_modification": True,
            "scientific_evidence": "external_validation_completed",
            "current_decision": "support_module_active",
        },
    }

    return {
        "version": OFFICIAL_BUNDLE_VERSION,
        "candidate_indices_version": OFFICIAL_SCORING_VERSION,
        "candidate_definition_hash": def_hash,
        "fixture_ids_hash": candidate.fixture_ids_hash,
        "targets_hash": candidate.targets_hash,
        "normalization_method": candidate.normalization_method,
        "normalization_payload": norm,
        "calibration_payload": operational_cal,
        "candidate_definitions_payload": definitions,
        "status": BUNDLE_STATUS_ACTIVE,
        "is_active": True,
    }


def build_finalization_dry_run(
    db: Session,
    benchmark_job_id: int,
    *,
    source_git_commit: str | None = None,
) -> dict[str, Any]:
    """Dry-run read-only: mapping, coefficienti, hash, freeze_allowed."""
    preview = get_preview_bundle_v1_1(db)
    # Also accept currently-active preview via status
    active_preview = None
    if preview is not None and preview.is_active and preview.status == BUNDLE_STATUS_ACTIVE:
        active_preview = preview
    else:
        # Prefer active row if still preview
        from app.services.cecchino.cecchino_goal_intensity_v5_preview import get_active_bundle

        current_active = get_active_bundle(db)
        if current_active is not None and current_active.version == PREVIEW_BUNDLE_VERSION:
            active_preview = current_active
            preview = current_active
        elif current_active is not None and current_active.version == OFFICIAL_BUNDLE_VERSION:
            active_preview = None

    candidate = get_candidate_bundle_v2_1(db)
    job_val = validate_benchmark_job_for_finalization(
        db, benchmark_job_id, candidate_bundle=candidate
    )
    blocking = list(job_val.get("blocking_reasons") or [])
    warnings: list[str] = list(job_val.get("warnings") or [])

    if preview is None:
        blocking.append("preview_bundle_missing")
    if candidate is None:
        blocking.append("candidate_bundle_missing")

    existing_official = get_bundle_by_version(db, OFFICIAL_BUNDLE_VERSION)
    payload: dict[str, Any] | None = None
    effective_coefs: dict[str, Any] = {}
    definition_hash = None

    if candidate is not None and job_val.get("ok") and not blocking:
        try:
            payload = build_official_bundle_payload(
                candidate=candidate,
                preview=preview,
                job_validation=job_val,
                source_git_commit=source_git_commit,
            )
            definition_hash = payload["candidate_definition_hash"]
            op = (payload.get("calibration_payload") or {}).get(OPERATIONAL_CALIBRATION_KEY) or {}
            for target, head in op.items():
                effective_coefs[target] = {
                    "calibration_source": head.get("calibration_source"),
                    "intercept": head.get("intercept"),
                    "coefficient": head.get("coefficient"),
                    "calibration_method": head.get("calibration_method") or head.get("method"),
                }
        except ValueError as exc:
            blocking.append(str(exc))

    if existing_official is not None and definition_hash:
        if existing_official.candidate_definition_hash == definition_hash:
            warnings.append("already_frozen_same_definition")
        else:
            warnings.append("official_bundle_exists_different_hash")

    freeze_allowed = len(blocking) == 0 and payload is not None

    return make_json_safe(
        {
            "status": "preview" if freeze_allowed else "blocked",
            "dry_run": True,
            "writes": 0,
            "finalization_version": FINALIZATION_VERSION,
            "module_version": OFFICIAL_MODULE_VERSION,
            "official_bundle_version": OFFICIAL_BUNDLE_VERSION,
            "scoring_version": OFFICIAL_SCORING_VERSION,
            "current_active_bundle": (
                {
                    "id": preview.id if active_preview or preview else None,
                    "version": (active_preview or preview).version if (active_preview or preview) else None,
                    "status": (active_preview or preview).status if (active_preview or preview) else None,
                    "is_active": (active_preview or preview).is_active if (active_preview or preview) else None,
                    "definition_hash": (active_preview or preview).candidate_definition_hash
                    if (active_preview or preview)
                    else None,
                }
                if (active_preview or preview)
                else None
            ),
            "source_candidate_bundle": (
                {
                    "id": candidate.id,
                    "version": candidate.version,
                    "status": candidate.status,
                    "is_active": candidate.is_active,
                    "definition_hash": candidate.candidate_definition_hash,
                }
                if candidate
                else None
            ),
            "benchmark_job": job_val.get("job"),
            "benchmark_validation": {
                "ok": job_val.get("ok"),
                "blocking_reasons": job_val.get("blocking_reasons"),
            },
            "target_calibration_mapping": dict(TARGET_CALIBRATION_MAPPING),
            "effective_coefficients": effective_coefs,
            "raw_score_definition": {
                "id": RAW_INDEX_ID,
                "formula": "mean(OP1, DV1, MT1, OV1)",
                "gi_e_raw": "identical_to_GI_A",
            },
            "required_feature_keys": list(OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS),
            "expected_cutover_behavior": {
                "mode": CUTOVER_MODE,
                "no_backfill": True,
                "legacy_snapshots_unchanged": True,
                "new_snapshots_only_after_frozen_at": True,
            },
            "fallback_policy": {
                "atomic_v4": True,
                "reason": FALLBACK_REASON_FEATURES_INCOMPLETE,
                "btts_unavailable": True,
                "no_mix": True,
            },
            "archived_candidates": list(ARCHIVED_FROM_OPERATIONAL),
            "definition_hash": definition_hash,
            "existing_official_bundle": (
                {
                    "id": existing_official.id,
                    "definition_hash": existing_official.candidate_definition_hash,
                    "is_active": existing_official.is_active,
                    "status": existing_official.status,
                }
                if existing_official
                else None
            ),
            "freeze_allowed": freeze_allowed,
            "blocking_reasons": blocking,
            "warnings": warnings,
            "confirm_token_required": FREEZE_CONFIRM_TOKEN,
            "_bundle_payload": payload,
        }
    )


def freeze_official_support_bundle(
    db: Session,
    benchmark_job_id: int,
    *,
    dry_run: bool = True,
    confirm: str | None = None,
    source_git_commit: str | None = None,
) -> dict[str, Any]:
    """Freeze atomico del bundle ufficiale. NON eseguire in produzione durante lo sviluppo."""
    if not dry_run:
        if confirm != FREEZE_CONFIRM_TOKEN:
            return make_json_safe(
                {
                    "status": "error",
                    "error": "invalid_confirm_token",
                    "freeze_allowed": False,
                    "writes": 0,
                    "dry_run": False,
                }
            )

    preview_state = build_finalization_dry_run(
        db, benchmark_job_id, source_git_commit=source_git_commit
    )
    if dry_run:
        out = dict(preview_state)
        out.pop("_bundle_payload", None)
        out["dry_run"] = True
        out["writes"] = 0
        return make_json_safe(out)

    if not preview_state.get("freeze_allowed"):
        out = dict(preview_state)
        out.pop("_bundle_payload", None)
        out["status"] = "blocked"
        out["dry_run"] = False
        out["writes"] = 0
        return make_json_safe(out)

    payload = preview_state.get("_bundle_payload")
    if not isinstance(payload, dict):
        return make_json_safe(
            {"status": "error", "error": "bundle_payload_missing", "writes": 0, "dry_run": False}
        )

    candidate = get_candidate_bundle_v2_1(db)
    preview = get_preview_bundle_v1_1(db)
    if candidate is None or preview is None:
        return make_json_safe(
            {
                "status": "error",
                "error": "bundles_missing",
                "writes": 0,
                "dry_run": False,
            }
        )

    try:
        # Atomic transaction: lock preview + candidate, re-validate, insert official
        locked_preview = db.scalars(
            select(CecchinoGoalIntensityV5PreviewBundle)
            .where(CecchinoGoalIntensityV5PreviewBundle.id == preview.id)
            .with_for_update()
        ).first()
        locked_candidate = db.scalars(
            select(CecchinoGoalIntensityV5PreviewBundle)
            .where(CecchinoGoalIntensityV5PreviewBundle.id == candidate.id)
            .with_for_update()
        ).first()
        if locked_preview is None or locked_candidate is None:
            db.rollback()
            return make_json_safe(
                {"status": "error", "error": "lock_failed", "writes": 0, "dry_run": False}
            )

        # Re-validate job under lock
        job_val = validate_benchmark_job_for_finalization(
            db, benchmark_job_id, candidate_bundle=locked_candidate
        )
        if not job_val.get("ok"):
            db.rollback()
            return make_json_safe(
                {
                    "status": "blocked",
                    "error": "benchmark_revalidation_failed",
                    "blocking_reasons": job_val.get("blocking_reasons"),
                    "writes": 0,
                    "dry_run": False,
                }
            )

        rebuilt = build_official_bundle_payload(
            candidate=locked_candidate,
            preview=locked_preview,
            job_validation=job_val,
            source_git_commit=source_git_commit,
        )
        if rebuilt["candidate_definition_hash"] != payload["candidate_definition_hash"]:
            db.rollback()
            return make_json_safe(
                {
                    "status": "error",
                    "error": "definition_hash_mismatch_on_rebuild",
                    "writes": 0,
                    "dry_run": False,
                }
            )

        existing = db.scalars(
            select(CecchinoGoalIntensityV5PreviewBundle).where(
                CecchinoGoalIntensityV5PreviewBundle.version == OFFICIAL_BUNDLE_VERSION,
                CecchinoGoalIntensityV5PreviewBundle.candidate_definition_hash
                == rebuilt["candidate_definition_hash"],
            )
        ).first()
        if existing is not None:
            db.rollback()
            return make_json_safe(
                {
                    "status": "already_frozen_same_definition",
                    "existing_bundle_id": existing.id,
                    "bundle_id": existing.id,
                    "version": existing.version,
                    "is_active": existing.is_active,
                    "definition_hash": existing.candidate_definition_hash,
                    "writes": 0,
                    "dry_run": False,
                }
            )

        # Supersede any other active bundles
        other_actives = db.scalars(
            select(CecchinoGoalIntensityV5PreviewBundle)
            .where(CecchinoGoalIntensityV5PreviewBundle.is_active.is_(True))
            .with_for_update()
        ).all()
        for row in other_actives:
            if row.id == locked_candidate.id:
                continue
            row.is_active = False
            if row.version == PREVIEW_BUNDLE_VERSION:
                row.status = BUNDLE_STATUS_SUPERSEDED
            elif row.status == BUNDLE_STATUS_ACTIVE:
                row.status = BUNDLE_STATUS_SUPERSEDED

        locked_preview.is_active = False
        locked_preview.status = BUNDLE_STATUS_SUPERSEDED

        # Candidate v2.1 unchanged status
        locked_candidate.is_active = False
        locked_candidate.status = BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE

        now = _utc_now()
        defs = dict(rebuilt["candidate_definitions_payload"])
        defs["cutover_timestamp"] = now.isoformat()

        official = CecchinoGoalIntensityV5PreviewBundle(
            version=rebuilt["version"],
            candidate_indices_version=rebuilt["candidate_indices_version"],
            candidate_definition_hash=rebuilt["candidate_definition_hash"],
            fixture_ids_hash=rebuilt["fixture_ids_hash"],
            targets_hash=rebuilt["targets_hash"],
            normalization_method=rebuilt["normalization_method"],
            normalization_payload=rebuilt["normalization_payload"],
            calibration_payload=rebuilt["calibration_payload"],
            candidate_definitions_payload=defs,
            retrospective_date_from=locked_preview.retrospective_date_from,
            retrospective_date_to=locked_preview.retrospective_date_to,
            first_prospective_scan_date=locked_preview.first_prospective_scan_date,
            frozen_at=now,
            status=BUNDLE_STATUS_ACTIVE,
            is_active=True,
        )
        db.add(official)
        db.flush()
        db.commit()
        db.refresh(official)

        try:
            from app.services.cecchino.cecchino_goal_intensity_v5_readiness import (
                clear_goal_intensity_v5_readiness_cache,
            )

            clear_goal_intensity_v5_readiness_cache()
        except Exception:
            pass

        return make_json_safe(
            {
                "status": "frozen",
                "bundle_id": official.id,
                "version": official.version,
                "is_active": True,
                "bundle_status": official.status,
                "definition_hash": official.candidate_definition_hash,
                "module_version": OFFICIAL_MODULE_VERSION,
                "scoring_version": OFFICIAL_SCORING_VERSION,
                "finalization_version": FINALIZATION_VERSION,
                "benchmark_job_id": int(benchmark_job_id),
                "preview_bundle": {
                    "id": locked_preview.id,
                    "version": locked_preview.version,
                    "is_active": locked_preview.is_active,
                    "status": locked_preview.status,
                },
                "candidate_bundle": {
                    "id": locked_candidate.id,
                    "version": locked_candidate.version,
                    "is_active": locked_candidate.is_active,
                    "status": locked_candidate.status,
                    "unchanged": True,
                },
                "target_calibration_mapping": dict(TARGET_CALIBRATION_MAPPING),
                "archived_candidates": list(ARCHIVED_FROM_OPERATIONAL),
                "cutover_mode": CUTOVER_MODE,
                "dry_run": False,
                "writes": 1,
                "checks": {
                    "external_api_calls": 0,
                    "base_run_writes": 0,
                    "bundle_refit": False,
                    "result_used_in_prediction": False,
                    "snapshot_writes": 0,
                    "no_backfill": True,
                },
            }
        )
    except Exception as exc:
        db.rollback()
        return make_json_safe(
            {
                "status": "error",
                "error": f"freeze_failed:{type(exc).__name__}",
                "detail": str(exc)[:500],
                "writes": 0,
                "dry_run": False,
                "rolled_back": True,
            }
        )


# ---------------------------------------------------------------------------
# Official scoring (single raw score, target-specific heads)
# ---------------------------------------------------------------------------


def score_official_support_with_bundle(
    features: dict[str, Any],
    bundle: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    """Calcola un solo raw GI_A e applica teste target-specifiche. Nessun GI_B/F/MT1."""
    ecdfs = _ecdfs_from_bundle(bundle)
    pct = {k: ecdf.transform(safe_float(features.get(k))) for k, ecdf in ecdfs.items()}
    pillar = _pillar_scores_from_pct(pct)
    composite = _composite_scores(pillar)
    raw = _round(composite.get(RAW_INDEX_ID))

    cal_root = bundle.calibration_payload or {}
    op = cal_root.get(OPERATIONAL_CALIBRATION_KEY) or {}
    # Backward-compatible: allow nested mapping without operational key
    if not op and isinstance(cal_root.get("total_goals_ft"), dict):
        op = cal_root

    p_ge2 = _apply_logistic(op.get("goals_ge_2"), raw)
    p_ge3 = _apply_logistic(op.get("goals_ge_3"), raw)
    p_btts = _apply_logistic(op.get("btts_ft"), raw)
    expected_total = _apply_linear(op.get("total_goals_ft"), raw)

    def _complement(p: float | None) -> float | None:
        if p is None:
            return None
        return _round(min(1.0 - 1e-6, max(1e-6, 1.0 - float(p))))

    calibrated = {
        OPERATIONAL_CALIBRATION_KEY: {
            "raw_score": raw,
            "raw_index_id": RAW_INDEX_ID,
            "expected_total_goals": expected_total,
            "probability_goals_ge_2": p_ge2,
            "probability_goals_ge_3": p_ge3,
            "probability_btts": p_btts,
            "probability_under_1_5": _complement(p_ge2),
            "probability_under_2_5": _complement(p_ge3),
            "probability_btts_no": _complement(p_btts),
            "calibration_sources": dict(TARGET_CALIBRATION_MAPPING),
            "probability_label": "Stima calibrata del totale gol",
            "uses_score_over_100_as_probability": False,
            "no_blending": True,
            "no_refit": True,
        }
    }
    candidate_scores = {RAW_INDEX_ID: raw}
    hashes = {
        k: ((bundle.normalization_payload or {}).get("features") or {}).get(k, {}).get(
            "distribution_hash"
        )
        for k in OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS
    }
    # Pillars only those needed for GI_A (still expose full pillar dict for audit)
    return {
        "pillar_scores": {k: _round(v) for k, v in pillar.items()},
        "candidate_scores": candidate_scores,
        "calibrated_predictions": calibrated,
        "normalization_hashes": hashes,
        "no_target_used_in_score": True,
        "primary_candidate_score": raw,
        "challenger_candidate_score": None,
        "benchmark_score": None,
        "diagnostic_score": None,
        "raw_index_id": RAW_INDEX_ID,
        "scoring_version": OFFICIAL_SCORING_VERSION,
        "module_version": OFFICIAL_MODULE_VERSION,
    }


def official_features_complete(features: dict[str, Any], *, sample_size: int) -> bool:
    if sample_size < 10:
        return False
    return all(
        safe_float(features.get(k)) is not None for k in OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS
    )


def build_goal_intensity_market_support(
    outputs: dict[str, Any] | None,
    *,
    market: str,
) -> dict[str, Any]:
    """Adapter puro: contesto analitico per mercato. Nessun consiglio / Signals."""
    src = outputs if isinstance(outputs, dict) else {}
    m = str(market or "").upper().replace(" ", "_")
    mapping = {
        "OVER_1_5": ("probability_goals_ge_2", "goals_ge_2", RAW_INDEX_ID),
        "UNDER_1_5": ("probability_under_1_5", "goals_ge_2", RAW_INDEX_ID),
        "OVER_2_5": ("probability_goals_ge_3", "goals_ge_3", GI_E_ID),
        "UNDER_2_5": ("probability_under_2_5", "goals_ge_3", GI_E_ID),
        "BTTS": ("probability_btts", "btts_ft", GI_E_ID),
        "GOL": ("probability_btts", "btts_ft", GI_E_ID),
        "BTTS_YES": ("probability_btts", "btts_ft", GI_E_ID),
        "NO_GOL": ("probability_btts_no", "btts_ft", GI_E_ID),
        "BTTS_NO": ("probability_btts_no", "btts_ft", GI_E_ID),
        "TOTAL_GOALS": ("expected_total_goals", "total_goals_ft", GI_E_ID),
    }
    if m not in mapping:
        return make_json_safe(
            {
                "status": "unsupported_market",
                "market": m,
                "role": ROLE,
                "signals_integration_status": SIGNALS_INTEGRATION_STATUS,
                "advisory": False,
            }
        )
    key, target, cal_src = mapping[m]
    value = src.get(key)
    return make_json_safe(
        {
            "status": "ok" if value is not None else "unavailable",
            "market": m,
            "value": value,
            "target": target,
            "calibration_source": cal_src,
            "raw_index": RAW_INDEX_ID,
            "role": ROLE,
            "signals_integration_status": SIGNALS_INTEGRATION_STATUS,
            "advisory": False,
            "context_only": True,
        }
    )
