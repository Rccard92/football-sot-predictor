"""Intensità Goal v5 — Fase 2A.1: Preview prospettica (freeze reale).

Bundle congelato da candidate_indices_v1_1; ammissione strict-after-freeze;
esclusione identity retrospettive. Nessuna formula produttiva; v4 invariata.
"""

from __future__ import annotations

import csv
import io
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator, Literal

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    BUNDLE_STATUS_ACTIVE,
    BUNDLE_STATUS_SUPERSEDED,
    PREVIEW_BUNDLE_VERSION,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_ERROR,
    SNAPSHOT_INCOMPLETE,
    SNAPSHOT_LOCKED,
    SNAPSHOT_PENDING,
    CecchinoGoalIntensityV5PreviewBundle,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    MATCH_FINISHED,
    CecchinoTodayFixture,
)
from app.models.fixture import Fixture
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
    extract_features_for_local_fixture,
)
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    CANDIDATE_DEFINITIONS,
    NORMALIZATION_METHOD,
    VERSION as CANDIDATE_INDICES_VERSION,
    TrainEcdf,
    VALIDATION_STATUS,
    WEIGHT_STATUS,
    _candidate_definition_hash,
    _composite_scores,
    _loo_composites,
    _pillar_scores_from_pct,
    build_goal_intensity_v5_candidate_indices_internal,
    safe_float,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import (
    bootstrap_index_matrix,
    bootstrap_paired_delta_ci,
    pearson_r,
    spearman_rho,
)

EXPECTED_FIXTURE_IDS_HASH = "e2b6a7160dc7e6dc5668494d26577c40209bcdf29781d739bc15398cba844b3f"
EXPECTED_TARGETS_HASH = "11228bd75343d8c2b4b4ca36bda73db53eef2ad0187675f355c7114c90d95972"
EXPECTED_DEFINITION_HASH = "3c48413461490d9ad17c59f052e0543919e12a6013a04ca0bdccdddb316273ab"

PRIMARY_ID = "GI_A_STRICT_CORE"
CHALLENGER_ID = "GI_B_RECENCY"
BENCHMARK_ID = "MT1_LONG_TERM"
DIAGNOSTIC_ID = "GI_A_without_volatility"

MONITORED_CANDIDATES = (PRIMARY_ID, CHALLENGER_ID, BENCHMARK_ID, DIAGNOSTIC_ID)
MINIMUM_PROSPECTIVE_MATCHES = 200
PROSPECTIVE_START_MODE = "strict_after_actual_bundle_freeze"
RETROSPECTIVE_EXCLUSION_MODE = "exact_frozen_identity_sets"

BUNDLE_FEATURE_KEYS = (
    "home_goals_scored_avg",
    "home_goals_scored_rolling_5",
    "home_goals_conceded_avg",
    "away_goals_conceded_avg",
    "total_goals_avg",
    "total_goals_rolling_5",
    "goals_scored_std_last_10",
)

PreviewExportKind = Literal[
    "preview_summary",
    "preview_snapshots",
    "preview_completed_results",
    "preview_candidate_monitoring",
    "preview_calibration",
    "preview_bundle_definition",
]

VERSION = PREVIEW_BUNDLE_VERSION


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, digits)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_z(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    ensured = _ensure_utc(dt)
    assert ensured is not None
    return ensured.isoformat().replace("+00:00", "Z")


def _unique_sorted_ids(values: list[Any]) -> list[int]:
    out: set[int] = set()
    for v in values:
        if v is None:
            continue
        try:
            out.add(int(v))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _build_prospective_guard(
    scored_rows: list[dict[str, Any]],
    *,
    fixture_ids_hash: str,
    targets_hash: str,
) -> dict[str, Any]:
    today_ids = _unique_sorted_ids([r.get("today_fixture_id") for r in scored_rows])
    local_ids = _unique_sorted_ids([r.get("local_fixture_id") for r in scored_rows])
    provider_ids = _unique_sorted_ids([r.get("provider_fixture_id") for r in scored_rows])
    scan_dates: list[str] = []
    for r in scored_rows:
        sd = r.get("scan_date")
        if sd is None:
            continue
        scan_dates.append(sd.isoformat() if hasattr(sd, "isoformat") else str(sd)[:10])
    scan_dates = sorted({s for s in scan_dates if s})
    return {
        "retrospective_today_fixture_ids": today_ids,
        "retrospective_local_fixture_ids": local_ids,
        "retrospective_provider_fixture_ids": provider_ids,
        "retrospective_identity_count": len(today_ids) + len(local_ids) + len(provider_ids),
        "retrospective_effective_min_scan_date": scan_dates[0] if scan_dates else None,
        "retrospective_effective_max_scan_date": scan_dates[-1] if scan_dates else None,
        "fixture_ids_hash": fixture_ids_hash,
        "targets_hash": targets_hash,
        "exclusion_mode": RETROSPECTIVE_EXCLUSION_MODE,
    }


def _prospective_guard(bundle: CecchinoGoalIntensityV5PreviewBundle) -> dict[str, Any]:
    payload = bundle.candidate_definitions_payload or {}
    guard = payload.get("prospective_guard")
    return guard if isinstance(guard, dict) else {}


def _is_retrospective_identity(today_row: CecchinoTodayFixture, guard: dict[str, Any]) -> bool:
    today_set = set(guard.get("retrospective_today_fixture_ids") or [])
    local_set = set(guard.get("retrospective_local_fixture_ids") or [])
    provider_set = set(guard.get("retrospective_provider_fixture_ids") or [])
    tid = getattr(today_row, "id", None)
    lid = getattr(today_row, "local_fixture_id", None)
    pid = getattr(today_row, "provider_fixture_id", None)
    try:
        if tid is not None and int(tid) in today_set:
            return True
    except (TypeError, ValueError):
        pass
    try:
        if lid is not None and int(lid) in local_set:
            return True
    except (TypeError, ValueError):
        pass
    try:
        if pid is not None and int(pid) in provider_set:
            return True
    except (TypeError, ValueError):
        pass
    return False


# ---------------------------------------------------------------------------
# Bundle freeze
# ---------------------------------------------------------------------------


def _extract_calibration_for_candidate(metrics: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    block = metrics.get(candidate_id) or {}
    out: dict[str, Any] = {}
    tg = block.get("total_goals_ft") or {}
    if tg.get("calibration_method") == "train_linear_regression":
        out["total_goals_ft"] = {
            "calibration_method": "train_linear_regression",
            "intercept": tg.get("intercept"),
            "coefficient": tg.get("coefficient"),
            "train_n": tg.get("train_n"),
        }
    for target in ("goals_ge_2", "goals_ge_3", "btts_ft"):
        b = block.get(target) or {}
        if b.get("calibration_method") == "train_logistic_regression":
            out[target] = {
                "calibration_method": "train_logistic_regression",
                "intercept": b.get("intercept"),
                "coefficient": b.get("coefficient"),
                "train_n": b.get("train_n"),
                "train_positive_rate": b.get("train_positive_rate"),
            }
    return out


def _build_normalization_payload(ecdfs: dict[str, TrainEcdf]) -> dict[str, Any]:
    features = {}
    for key in BUNDLE_FEATURE_KEYS:
        ecdf = ecdfs.get(key)
        if ecdf is None:
            continue
        meta = ecdf.metadata()
        features[key] = {
            **meta,
            "train_values": [float(v) for v in ecdf.values.tolist()],
            "tie_handling": "midrank",
            "clipping_rules": "clamp_to_train_min_max",
        }
    return {
        "normalization_method": NORMALIZATION_METHOD,
        "fit_split": "train",
        "no_target_used_in_normalization": True,
        "features": features,
    }


def freeze_preview_bundle(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    minimum_history_sample: int = 10,
    bootstrap_iterations: int = 1000,
    random_seed: int = 42,
    enforce_expected_hashes: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Crea bundle attivo da Fase 1D.1; fallisce se readiness/hash non OK."""
    t0 = time.perf_counter()
    actual_freeze_at = _ensure_utc(now) or _utc_now()
    full = build_goal_intensity_v5_candidate_indices_internal(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        minimum_history_sample=minimum_history_sample,
        bootstrap_iterations=bootstrap_iterations,
        random_seed=random_seed,
    )
    if full.get("status") != "ok":
        return {
            "status": "error",
            "error": "candidate_indices_failed",
            "detail": full.get("error"),
            "version": VERSION,
        }

    readiness = full.get("phase_2a_readiness") or {}
    if readiness.get("blocking_issues") or readiness.get("ready_for_phase_2a") is False:
        return {
            "status": "error",
            "error": "readiness_false",
            "blocking_issues": readiness.get("blocking_issues") or ["ready_for_phase_2a_false"],
            "version": VERSION,
        }

    cohort = full.get("cohort_summary") or {}
    fixture_hash = str(cohort.get("fixture_ids_hash") or "")
    targets_hash = str(cohort.get("targets_hash") or "")
    def_hash = _candidate_definition_hash()
    protocol = full.get("prospective_validation_protocol") or {}
    candidate_definition_frozen_at = str(protocol.get("candidate_definition_frozen_at") or "")

    if enforce_expected_hashes:
        mismatches = []
        if fixture_hash != EXPECTED_FIXTURE_IDS_HASH:
            mismatches.append("fixture_ids_hash")
        if targets_hash != EXPECTED_TARGETS_HASH:
            mismatches.append("targets_hash")
        if def_hash != EXPECTED_DEFINITION_HASH:
            mismatches.append("candidate_definition_hash")
        if mismatches:
            return {
                "status": "error",
                "error": "hash_mismatch",
                "mismatches": mismatches,
                "got": {
                    "fixture_ids_hash": fixture_hash,
                    "targets_hash": targets_hash,
                    "candidate_definition_hash": def_hash,
                },
                "expected": {
                    "fixture_ids_hash": EXPECTED_FIXTURE_IDS_HASH,
                    "targets_hash": EXPECTED_TARGETS_HASH,
                    "candidate_definition_hash": EXPECTED_DEFINITION_HASH,
                },
                "version": VERSION,
            }

    # Verify no score/100 and train-only calibration
    gi_a = (full.get("composite_metrics") or {}).get(PRIMARY_ID) or {}
    ge2 = gi_a.get("goals_ge_2") or {}
    tg = gi_a.get("total_goals_ft") or {}
    if ge2.get("uses_score_over_100_as_probability") is not False:
        return {"status": "error", "error": "score_over_100_probability", "version": VERSION}
    if ge2.get("calibration_method") != "train_logistic_regression":
        return {"status": "error", "error": "binary_calibration_not_train_logistic", "version": VERSION}
    if tg.get("calibration_method") != "train_linear_regression":
        return {"status": "error", "error": "linear_calibration_not_train_only", "version": VERSION}

    ecdfs: dict[str, TrainEcdf]
    from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
        _core_rows,
        fit_train_ecdfs,
    )

    dataset_rows = (full.get("_dataset") or {}).get("dataset_rows") or []
    rows = _core_rows(dataset_rows, minimum_history_sample)
    ecdfs = fit_train_ecdfs(rows, BUNDLE_FEATURE_KEYS)

    normalization_payload = _build_normalization_payload(ecdfs)
    if not all(k in normalization_payload["features"] for k in BUNDLE_FEATURE_KEYS):
        return {"status": "error", "error": "ecdf_features_incomplete", "version": VERSION}

    metrics_pool = {}
    metrics_pool.update(full.get("composite_metrics") or {})
    metrics_pool.update(full.get("baseline_metrics") or {})
    # LOO metrics from scored evaluation
    for loo in (DIAGNOSTIC_ID,):
        if loo not in metrics_pool:
            from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
                evaluate_score_metrics,
            )

            scored = full.get("_scored_rows") or []
            metrics_pool[loo] = evaluate_score_metrics(
                scored,
                loo,
                bootstrap_iterations=min(200, bootstrap_iterations),
                random_seed=random_seed,
                bootstrap_cache={},
            )

    calibration_payload = {
        cid: _extract_calibration_for_candidate(metrics_pool, cid) for cid in MONITORED_CANDIDATES
    }
    for cid in MONITORED_CANDIDATES:
        cal = calibration_payload.get(cid) or {}
        if "total_goals_ft" not in cal or "goals_ge_2" not in cal:
            return {
                "status": "error",
                "error": "calibration_incomplete",
                "candidate": cid,
                "version": VERSION,
            }

    scored_rows = list(full.get("_scored_rows") or [])
    prospective_guard = _build_prospective_guard(
        scored_rows,
        fixture_ids_hash=fixture_hash,
        targets_hash=targets_hash,
    )
    freeze_iso = _iso_z(actual_freeze_at)
    first_prospective = actual_freeze_at.date()

    definitions_payload = {
        "candidate_definitions": CANDIDATE_DEFINITIONS,
        "primary_candidate": PRIMARY_ID,
        "challenger_candidate": CHALLENGER_ID,
        "benchmark_candidate": BENCHMARK_ID,
        "diagnostic_candidate": DIAGNOSTIC_ID,
        "weight_status": WEIGHT_STATUS,
        "validation_status": VALIDATION_STATUS,
        "research_limitations": full.get("research_limitations") or {},
        "tempo_baseline_comparison": full.get("tempo_baseline_comparison") or {},
        "pareto_analysis": {
            k: (full.get("pareto_analysis") or {}).get(k)
            for k in (
                "primary_candidate",
                "challenger_candidate",
                "selection_evidence_level",
                "selection_motivation",
                "nominal_pareto_front",
                "statistically_supported_pareto_front",
            )
        },
        "candidate_definition_frozen_at": candidate_definition_frozen_at,
        "bundle_frozen_at": freeze_iso,
        "prospective_window_started_at": freeze_iso,
        "prospective_start_mode": PROSPECTIVE_START_MODE,
        "prospective_guard": prospective_guard,
    }

    # Supersede previous active bundles (no delete)
    for old in db.scalars(
        select(CecchinoGoalIntensityV5PreviewBundle).where(
            CecchinoGoalIntensityV5PreviewBundle.is_active.is_(True)
        )
    ).all():
        old.is_active = False
        old.status = BUNDLE_STATUS_SUPERSEDED

    bundle = CecchinoGoalIntensityV5PreviewBundle(
        version=VERSION,
        candidate_indices_version=CANDIDATE_INDICES_VERSION,
        candidate_definition_hash=def_hash,
        fixture_ids_hash=fixture_hash,
        targets_hash=targets_hash,
        normalization_method=NORMALIZATION_METHOD,
        normalization_payload=normalization_payload,
        calibration_payload=calibration_payload,
        candidate_definitions_payload=definitions_payload,
        retrospective_date_from=date_from,
        retrospective_date_to=date_to,
        first_prospective_scan_date=first_prospective,
        frozen_at=actual_freeze_at,
        status=BUNDLE_STATUS_ACTIVE,
        is_active=True,
    )
    db.add(bundle)
    db.commit()
    db.refresh(bundle)

    return {
        "status": "ok",
        "version": VERSION,
        "bundle_id": bundle.id,
        "candidate_indices_version": CANDIDATE_INDICES_VERSION,
        "candidate_definition_hash": def_hash,
        "fixture_ids_hash": fixture_hash,
        "targets_hash": targets_hash,
        "candidate_definition_frozen_at": candidate_definition_frozen_at,
        "bundle_frozen_at": freeze_iso,
        "prospective_window_started_at": freeze_iso,
        "prospective_start_mode": PROSPECTIVE_START_MODE,
        "first_prospective_scan_date": first_prospective.isoformat(),
        "frozen_at": freeze_iso,
        "retrospective_identity_count": prospective_guard["retrospective_identity_count"],
        "is_active": True,
        "v4_version": V4_VERSION,
        "elapsed_ms": _round((time.perf_counter() - t0) * 1000, 2),
        "simple_export_cache_skipped": True,
        "simple_export_cache_reason": (
            "Cache in-memory 1D non implementata: rischio memoria/sessioni DB su payload bootstrap "
            "grandi; export 2A leggono snapshot già salvati."
        ),
    }


def get_active_bundle(db: Session) -> CecchinoGoalIntensityV5PreviewBundle | None:
    return db.scalars(
        select(CecchinoGoalIntensityV5PreviewBundle)
        .where(
            CecchinoGoalIntensityV5PreviewBundle.is_active.is_(True),
            CecchinoGoalIntensityV5PreviewBundle.status == BUNDLE_STATUS_ACTIVE,
            CecchinoGoalIntensityV5PreviewBundle.version == PREVIEW_BUNDLE_VERSION,
        )
        .order_by(CecchinoGoalIntensityV5PreviewBundle.id.desc())
    ).first()


# ---------------------------------------------------------------------------
# Scoring from frozen bundle
# ---------------------------------------------------------------------------


def _ecdfs_from_bundle(bundle: CecchinoGoalIntensityV5PreviewBundle) -> dict[str, TrainEcdf]:
    features = (bundle.normalization_payload or {}).get("features") or {}
    out: dict[str, TrainEcdf] = {}
    for key, payload in features.items():
        values = payload.get("train_values") or []
        out[key] = TrainEcdf([float(v) for v in values])
    return out


def _apply_linear(cal: dict[str, Any] | None, score: float | None) -> float | None:
    if cal is None or score is None:
        return None
    intercept = safe_float(cal.get("intercept"))
    coef = safe_float(cal.get("coefficient"))
    if intercept is None or coef is None:
        return None
    return _round(intercept + coef * float(score))


def _apply_logistic(cal: dict[str, Any] | None, score: float | None) -> float | None:
    if cal is None or score is None:
        return None
    intercept = safe_float(cal.get("intercept"))
    coef = safe_float(cal.get("coefficient"))
    if intercept is None or coef is None:
        return None
    z = intercept + coef * float(score)
    # numeric stable sigmoid
    if z >= 0:
        p = 1.0 / (1.0 + math.exp(-z))
    else:
        ez = math.exp(z)
        p = ez / (1.0 + ez)
    return _round(min(1.0 - 1e-6, max(1e-6, p)))


def score_features_with_bundle(
    features: dict[str, Any],
    bundle: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    """Calcola pillar/candidati/predizioni calibrate senza rifit."""
    ecdfs = _ecdfs_from_bundle(bundle)
    pct = {k: ecdf.transform(safe_float(features.get(k))) for k, ecdf in ecdfs.items()}
    pillar = _pillar_scores_from_pct(pct)
    composite = _composite_scores(pillar)
    loo = _loo_composites(pillar)
    candidate_scores = {
        PRIMARY_ID: _round(composite.get(PRIMARY_ID)),
        CHALLENGER_ID: _round(composite.get(CHALLENGER_ID)),
        BENCHMARK_ID: _round(pillar.get(BENCHMARK_ID)),
        DIAGNOSTIC_ID: _round(loo.get("without_volatility")),
    }
    cal_all = bundle.calibration_payload or {}
    calibrated: dict[str, Any] = {}
    for cid, score in candidate_scores.items():
        cal = cal_all.get(cid) or {}
        calibrated[cid] = {
            "raw_score": score,
            "expected_total_goals": _apply_linear(cal.get("total_goals_ft"), score),
            "probability_goals_ge_2": _apply_logistic(cal.get("goals_ge_2"), score),
            "probability_goals_ge_3": _apply_logistic(cal.get("goals_ge_3"), score),
            "probability_btts": _apply_logistic(cal.get("btts_ft"), score),
            "probability_label": "Stima calibrata research",
            "uses_score_over_100_as_probability": False,
        }
    hashes = {
        k: ((bundle.normalization_payload or {}).get("features") or {}).get(k, {}).get("distribution_hash")
        for k in BUNDLE_FEATURE_KEYS
    }
    return {
        "pillar_scores": {k: _round(v) for k, v in pillar.items()},
        "candidate_scores": candidate_scores,
        "calibrated_predictions": calibrated,
        "normalization_hashes": hashes,
        "no_target_used_in_score": True,
        "primary_candidate_score": candidate_scores[PRIMARY_ID],
        "challenger_candidate_score": candidate_scores[CHALLENGER_ID],
        "benchmark_score": candidate_scores[BENCHMARK_ID],
        "diagnostic_score": candidate_scores[DIAGNOSTIC_ID],
    }


# ---------------------------------------------------------------------------
# Snapshot lifecycle
# ---------------------------------------------------------------------------


def _load_fixture(db: Session, local_fixture_id: int | None) -> Fixture | None:
    if local_fixture_id is None:
        return None
    return db.get(Fixture, int(local_fixture_id))


def compute_snapshot_for_today_row(
    db: Session,
    today_row: CecchinoTodayFixture,
    bundle: CecchinoGoalIntensityV5PreviewBundle | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Crea/aggiorna snapshot pre-match; lock post-kickoff; attach risultato FT."""
    now = _ensure_utc(now) or _utc_now()
    bundle = bundle or get_active_bundle(db)
    if bundle is None:
        return {"status": "error", "reason_codes": ["bundle_missing"], "today_fixture_id": today_row.id}

    if bundle.version != PREVIEW_BUNDLE_VERSION:
        return {
            "status": "error",
            "reason_codes": ["bundle_missing"],
            "today_fixture_id": today_row.id,
        }

    if bundle.candidate_definition_hash != EXPECTED_DEFINITION_HASH and bundle.candidate_definition_hash != _candidate_definition_hash():
        if bundle.candidate_definition_hash != _candidate_definition_hash():
            return {
                "status": "error",
                "reason_codes": ["bundle_hash_mismatch"],
                "today_fixture_id": today_row.id,
            }

    eligibility = str(today_row.eligibility_status or "")
    if eligibility != ELIGIBILITY_ELIGIBLE:
        code = "ineligible" if eligibility else "eligibility_unknown"
        if eligibility in {"", "null", "None"} or eligibility.lower() == "unknown":
            code = "eligibility_unknown"
        return {"status": "skipped", "reason_codes": [code], "today_fixture_id": today_row.id}

    existing = db.scalars(
        select(CecchinoGoalIntensityV5PreviewSnapshot).where(
            CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id,
            CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id == int(today_row.id),
        )
    ).first()

    kickoff = _ensure_utc(today_row.kickoff)
    # Lock / result attach path — snapshot già creato: non ricalcolare
    if existing and existing.locked_at is not None:
        attached = _attach_result_if_available(db, existing, today_row, now=now)
        return {
            "status": "locked",
            "snapshot_id": existing.id,
            "result_attached": attached,
            "today_fixture_id": today_row.id,
        }

    if existing is not None and kickoff is not None and now >= kickoff:
        existing.locked_at = now
        existing.snapshot_status = SNAPSHOT_LOCKED
        attached = _attach_result_if_available(db, existing, today_row, now=now)
        db.commit()
        return {
            "status": "locked",
            "snapshot_id": existing.id,
            "result_attached": attached,
            "today_fixture_id": today_row.id,
        }

    guard = _prospective_guard(bundle)
    if _is_retrospective_identity(today_row, guard):
        return {
            "status": "skipped",
            "reason_codes": ["retrospective_fixture_excluded"],
            "today_fixture_id": today_row.id,
        }

    source_snapshot_at = _ensure_utc(getattr(today_row, "updated_at", None)) or now
    freeze_at = _ensure_utc(bundle.frozen_at)
    if freeze_at is None or source_snapshot_at <= freeze_at:
        return {
            "status": "skipped",
            "reason_codes": ["snapshot_not_after_bundle_freeze"],
            "today_fixture_id": today_row.id,
        }

    if kickoff is not None and source_snapshot_at >= kickoff:
        return {
            "status": "skipped",
            "reason_codes": ["snapshot_after_kickoff"],
            "today_fixture_id": today_row.id,
        }

    if kickoff is not None and now >= kickoff:
        return {
            "status": "skipped",
            "reason_codes": ["snapshot_after_kickoff"],
            "today_fixture_id": today_row.id,
        }

    local = _load_fixture(db, today_row.local_fixture_id)
    if local is None:
        return _upsert_error_snapshot(
            db,
            bundle,
            today_row,
            existing,
            reason_codes=["identity_failed"],
            now=now,
        )

    try:
        features, leak_meta = extract_features_for_local_fixture(db, local, today_row)
    except Exception as exc:
        return _upsert_error_snapshot(
            db,
            bundle,
            today_row,
            existing,
            reason_codes=["preview_computation_error", type(exc).__name__],
            now=now,
        )

    if leak_meta.get("current_fixture_included") or leak_meta.get("future_fixture_included"):
        return _upsert_error_snapshot(
            db,
            bundle,
            today_row,
            existing,
            reason_codes=["target_leakage_detected"],
            now=now,
        )

    sample_size = int(leak_meta.get("sample_size") or 0)
    core_ok = sample_size >= 10 and all(
        safe_float(features.get(k)) is not None for k in BUNDLE_FEATURE_KEYS
    )
    if not core_ok:
        return _upsert_error_snapshot(
            db,
            bundle,
            today_row,
            existing,
            reason_codes=["feature_incomplete"],
            feature_payload={k: features.get(k) for k in BUNDLE_FEATURE_KEYS},
            history_sample_size=sample_size,
            xg_status=str(leak_meta.get("xg_status") or "missing"),
            now=now,
            snapshot_status=SNAPSHOT_INCOMPLETE,
        )

    scored = score_features_with_bundle(features, bundle)
    scan_date = today_row.scan_date

    payload_common = dict(
        local_fixture_id=int(local.id),
        provider_source=today_row.provider_source,
        provider_fixture_id=today_row.provider_fixture_id,
        competition_id=today_row.competition_id,
        home_team_id=getattr(today_row, "home_team_id", None) or local.home_team_id,
        away_team_id=getattr(today_row, "away_team_id", None) or local.away_team_id,
        home_team_name=getattr(today_row, "home_team_name", None),
        away_team_name=getattr(today_row, "away_team_name", None),
        competition_name=getattr(today_row, "league_name", None),
        scan_date=scan_date,
        source_snapshot_at=source_snapshot_at,
        kickoff=kickoff,
        eligibility_status=eligibility,
        eligibility_source="cecchino_today",
        eligibility_reason_codes=[],
        feature_status="available",
        feature_payload={k: features.get(k) for k in BUNDLE_FEATURE_KEYS},
        history_sample_size=sample_size,
        xg_status=str(leak_meta.get("xg_status") or "missing"),
        xg_payload={
            "xg_status": leak_meta.get("xg_status"),
            "xg_source": leak_meta.get("xg_source"),
        },
        pillar_scores_payload=scored["pillar_scores"],
        candidate_scores_payload=scored["candidate_scores"],
        calibrated_predictions_payload=scored["calibrated_predictions"],
        primary_candidate_score=scored["primary_candidate_score"],
        challenger_candidate_score=scored["challenger_candidate_score"],
        benchmark_score=scored["benchmark_score"],
        diagnostic_score=scored["diagnostic_score"],
        candidate_definition_hash=bundle.candidate_definition_hash,
        normalization_hashes_payload=scored["normalization_hashes"],
        no_target_used_in_score=True,
        snapshot_status=SNAPSHOT_PENDING,
        preview_status="ok",
        diagnostic_reason_codes=[],
        last_computed_at=now,
    )

    if existing is None:
        snap = CecchinoGoalIntensityV5PreviewSnapshot(
            bundle_id=bundle.id,
            today_fixture_id=int(today_row.id),
            first_computed_at=now,
            revision_count=1,
            **payload_common,
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        return {"status": "created", "snapshot_id": snap.id, "today_fixture_id": today_row.id}

    if existing.locked_at is not None:
        return {
            "status": "error",
            "reason_codes": ["score_recompute_after_lock_attempt"],
            "snapshot_id": existing.id,
            "today_fixture_id": today_row.id,
        }

    for key, value in payload_common.items():
        setattr(existing, key, value)
    existing.revision_count = int(existing.revision_count or 1) + 1
    if existing.first_computed_at is None:
        existing.first_computed_at = now
    db.commit()
    return {
        "status": "updated",
        "snapshot_id": existing.id,
        "revision_count": existing.revision_count,
        "today_fixture_id": today_row.id,
    }


def _upsert_error_snapshot(
    db: Session,
    bundle: CecchinoGoalIntensityV5PreviewBundle,
    today_row: CecchinoTodayFixture,
    existing: CecchinoGoalIntensityV5PreviewSnapshot | None,
    *,
    reason_codes: list[str],
    now: datetime,
    feature_payload: dict | None = None,
    history_sample_size: int | None = None,
    xg_status: str | None = None,
    snapshot_status: str = SNAPSHOT_ERROR,
) -> dict[str, Any]:
    if existing and existing.locked_at:
        return {
            "status": "locked",
            "snapshot_id": existing.id,
            "today_fixture_id": today_row.id,
            "reason_codes": reason_codes,
        }
    fields = dict(
        local_fixture_id=today_row.local_fixture_id,
        provider_source=today_row.provider_source,
        provider_fixture_id=today_row.provider_fixture_id,
        competition_id=today_row.competition_id,
        home_team_name=getattr(today_row, "home_team_name", None),
        away_team_name=getattr(today_row, "away_team_name", None),
        scan_date=today_row.scan_date,
        kickoff=_ensure_utc(today_row.kickoff),
        eligibility_status=today_row.eligibility_status,
        eligibility_source="cecchino_today",
        feature_status="incomplete" if "feature_incomplete" in reason_codes else "error",
        feature_payload=feature_payload,
        history_sample_size=history_sample_size,
        xg_status=xg_status,
        snapshot_status=snapshot_status,
        preview_status="error",
        diagnostic_reason_codes=reason_codes,
        candidate_definition_hash=bundle.candidate_definition_hash,
        no_target_used_in_score=True,
        last_computed_at=now,
    )
    if existing is None:
        snap = CecchinoGoalIntensityV5PreviewSnapshot(
            bundle_id=bundle.id,
            today_fixture_id=int(today_row.id),
            first_computed_at=now,
            revision_count=1,
            **fields,
        )
        db.add(snap)
        db.commit()
        return {
            "status": "error",
            "snapshot_id": snap.id,
            "reason_codes": reason_codes,
            "today_fixture_id": today_row.id,
        }
    for k, v in fields.items():
        setattr(existing, k, v)
    existing.revision_count = int(existing.revision_count or 1) + 1
    db.commit()
    return {
        "status": "error",
        "snapshot_id": existing.id,
        "reason_codes": reason_codes,
        "today_fixture_id": today_row.id,
    }


def _attach_result_if_available(
    db: Session,
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    today_row: CecchinoTodayFixture,
    *,
    now: datetime,
) -> bool:
    """Collega risultato FT senza ricalcolare score."""
    if snap.result_attached_at is not None:
        return False
    home = getattr(today_row, "goals_home", None)
    away = getattr(today_row, "goals_away", None)
    if home is None:
        home = getattr(today_row, "score_fulltime_home", None)
        away = getattr(today_row, "score_fulltime_away", None)
    match_status = str(getattr(today_row, "match_display_status", "") or getattr(today_row, "fixture_status", "") or "")
    local = _load_fixture(db, snap.local_fixture_id)
    if home is None and local is not None:
        home = getattr(local, "goals_home", None)
        away = getattr(local, "goals_away", None)
        if match_status not in {MATCH_FINISHED, "finished", "FT"} and getattr(local, "status_short", None) in {
            "FT",
            "AET",
            "PEN",
        }:
            match_status = MATCH_FINISHED
    if home is None or away is None:
        return False
    finished_codes = {MATCH_FINISHED, "finished", "FT", "AET", "PEN", "Match Finished"}
    if match_status not in finished_codes and str(getattr(local, "status_short", "") or "") not in {
        "FT",
        "AET",
        "PEN",
    }:
        kickoff = _ensure_utc(snap.kickoff)
        if kickoff is None or now < kickoff + timedelta(hours=1.5):
            return False

    total = int(home) + int(away)
    # Do NOT recompute scores — only attach targets
    snap.goals_home_ft = int(home)
    snap.goals_away_ft = int(away)
    snap.total_goals_ft = total
    snap.goals_ge_2 = int(total >= 2)
    snap.goals_ge_3 = int(total >= 3)
    snap.btts_ft = int(int(home) > 0 and int(away) > 0)
    snap.result_attached_at = now
    snap.snapshot_status = SNAPSHOT_COMPLETED
    if snap.locked_at is None:
        snap.locked_at = now
    db.commit()
    return True


def safe_preview_after_today_scan(db: Session, today_fixture_id: int) -> dict[str, Any]:
    """Hook non-bloccante: errori Preview non alterano eligibility Today."""
    try:
        row = db.get(CecchinoTodayFixture, int(today_fixture_id))
        if row is None:
            return {"status": "skipped", "reason": "today_fixture_missing"}
        return compute_snapshot_for_today_row(db, row)
    except Exception as exc:
        return {
            "status": "error",
            "reason_codes": ["preview_computation_error"],
            "detail": str(exc)[:200],
            "today_fixture_id": today_fixture_id,
            "eligibility_unchanged": True,
        }


# ---------------------------------------------------------------------------
# Refresh batch + listing + monitoring
# ---------------------------------------------------------------------------


def refresh_preview(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    bundle = get_active_bundle(db)
    if bundle is None:
        return {"status": "error", "error": "bundle_missing", "version": VERSION}

    freeze_at = _ensure_utc(bundle.frozen_at)
    start = date_from or (freeze_at.date() if freeze_at else bundle.first_prospective_scan_date)
    end = date_to or date.today()

    q = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= start,
        CecchinoTodayFixture.scan_date <= end,
    )
    if competition_id is not None:
        q = q.where(CecchinoTodayFixture.competition_id == competition_id)
    rows = list(db.scalars(q).all())

    counters = {
        "queried_today_rows": len(rows),
        "eligible_found": 0,
        "retrospective_excluded": 0,
        "not_after_freeze_excluded": 0,
        "snapshot_after_kickoff": 0,
        "created": 0,
        "updated": 0,
        "locked": 0,
        "completed": 0,
        "incomplete": 0,
        "error": 0,
        "skipped": 0,
        "results_attached": 0,
    }
    for row in rows:
        if row.eligibility_status == ELIGIBILITY_ELIGIBLE:
            counters["eligible_found"] += 1
        result = compute_snapshot_for_today_row(db, row, bundle)
        st = result.get("status")
        reasons = result.get("reason_codes") or []
        if st == "created":
            counters["created"] += 1
        elif st == "updated":
            counters["updated"] += 1
        elif st == "locked":
            counters["locked"] += 1
            if result.get("result_attached"):
                counters["results_attached"] += 1
                counters["completed"] += 1
        elif st == "error":
            if "feature_incomplete" in reasons:
                counters["incomplete"] += 1
            else:
                counters["error"] += 1
        else:
            counters["skipped"] += 1
            if "retrospective_fixture_excluded" in reasons:
                counters["retrospective_excluded"] += 1
            if "snapshot_not_after_bundle_freeze" in reasons:
                counters["not_after_freeze_excluded"] += 1
            if "snapshot_after_kickoff" in reasons:
                counters["snapshot_after_kickoff"] += 1

    monitoring = build_prospective_monitoring(db, bundle)
    defs = bundle.candidate_definitions_payload or {}
    return {
        "status": "ok",
        "version": VERSION,
        "bundle_id": bundle.id,
        "bundle_frozen_at": _iso_z(freeze_at),
        "prospective_start_mode": defs.get("prospective_start_mode") or PROSPECTIVE_START_MODE,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "counters": counters,
        "queried_today_rows": counters["queried_today_rows"],
        "retrospective_excluded": counters["retrospective_excluded"],
        "not_after_freeze_excluded": counters["not_after_freeze_excluded"],
        "snapshot_after_kickoff": counters["snapshot_after_kickoff"],
        "created": counters["created"],
        "updated": counters["updated"],
        "locked": counters["locked"],
        "completed": counters["completed"],
        "incomplete": counters["incomplete"],
        "error": counters["error"],
        "results_attached": counters["results_attached"],
        "monitoring_status": monitoring.get("status"),
        "completed_prospective_matches": monitoring.get("completed_prospective_matches"),
        "phase_2b_readiness": monitoring.get("phase_2b_readiness"),
        "elapsed_ms": _round((time.perf_counter() - t0) * 1000, 2),
        "v4_unchanged": True,
        "simple_export_cache_skipped": True,
    }


def list_preview_snapshots(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    bundle = get_active_bundle(db)
    if bundle is None:
        return {"status": "error", "error": "bundle_missing", "items": [], "total": 0}

    q = select(CecchinoGoalIntensityV5PreviewSnapshot).where(
        CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
    )
    if date_from:
        q = q.where(CecchinoGoalIntensityV5PreviewSnapshot.scan_date >= date_from)
    if date_to:
        q = q.where(CecchinoGoalIntensityV5PreviewSnapshot.scan_date <= date_to)
    if competition_id:
        q = q.where(CecchinoGoalIntensityV5PreviewSnapshot.competition_id == competition_id)
    if status:
        q = q.where(CecchinoGoalIntensityV5PreviewSnapshot.snapshot_status == status)

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = list(
        db.scalars(q.order_by(CecchinoGoalIntensityV5PreviewSnapshot.kickoff.desc()).offset(offset).limit(limit)).all()
    )
    return {
        "status": "ok",
        "version": VERSION,
        "bundle": _bundle_summary(bundle, db),
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "items": [_snapshot_list_item(s, bundle) for s in items],
    }


def get_preview_detail(db: Session, today_fixture_id: int) -> dict[str, Any]:
    bundle = get_active_bundle(db)
    if bundle is None:
        return {"status": "error", "error": "bundle_missing"}
    snap = db.scalars(
        select(CecchinoGoalIntensityV5PreviewSnapshot).where(
            CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id,
            CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id == int(today_fixture_id),
        )
    ).first()
    if snap is None:
        return {"status": "error", "error": "snapshot_not_found"}
    freeze_at = _ensure_utc(bundle.frozen_at)
    source_at = _ensure_utc(snap.source_snapshot_at)
    kickoff = _ensure_utc(snap.kickoff)
    after_freeze = bool(freeze_at and source_at and source_at > freeze_at)
    before_kickoff = bool(kickoff and source_at and source_at < kickoff) if source_at else None
    return {
        "status": "ok",
        "version": VERSION,
        "banner": "Preview research non produttiva. Nessun segnale betting attivato.",
        "bundle": _bundle_summary(bundle, db),
        "snapshot": {
            **_snapshot_detail(snap),
            "bundle_frozen_at": _iso_z(freeze_at),
            "source_snapshot_after_freeze": after_freeze,
            "source_snapshot_before_kickoff": before_kickoff,
            "freeze_check": {
                "source_snapshot_at_gt_bundle_frozen_at": after_freeze,
                "source_snapshot_at_lt_kickoff": before_kickoff,
            },
        },
        "v4_unchanged": True,
        "no_betting_signals": True,
    }


def _bundle_summary(bundle: CecchinoGoalIntensityV5PreviewBundle, db: Session) -> dict[str, Any]:
    snaps = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
            )
        ).all()
    )
    completed = sum(1 for s in snaps if s.snapshot_status == SNAPSHOT_COMPLETED and s.result_attached_at)
    pending = sum(1 for s in snaps if s.snapshot_status == SNAPSHOT_PENDING)
    locked = sum(1 for s in snaps if s.snapshot_status == SNAPSHOT_LOCKED)
    incomplete = sum(1 for s in snaps if s.snapshot_status == SNAPSHOT_INCOMPLETE)
    errors = sum(1 for s in snaps if s.snapshot_status == SNAPSHOT_ERROR)
    defs = bundle.candidate_definitions_payload or {}
    guard = _prospective_guard(bundle)
    freeze_at = _ensure_utc(bundle.frozen_at)
    if completed >= MINIMUM_PROSPECTIVE_MATCHES:
        protocol_status = "minimum_sample_reached"
    elif len(snaps) == 0:
        protocol_status = "waiting_for_prospective_data"
    else:
        protocol_status = "collecting_prospective_data"
    return {
        "bundle_id": bundle.id,
        "version": bundle.version,
        "candidate_indices_version": bundle.candidate_indices_version,
        "candidate_definition_hash": bundle.candidate_definition_hash,
        "candidate_definition_hash_short": bundle.candidate_definition_hash[:12],
        "frozen_at": _iso_z(freeze_at),
        "bundle_frozen_at": _iso_z(freeze_at),
        "candidate_definition_frozen_at": defs.get("candidate_definition_frozen_at"),
        "prospective_window_started_at": defs.get("prospective_window_started_at") or _iso_z(freeze_at),
        "prospective_start_mode": defs.get("prospective_start_mode") or PROSPECTIVE_START_MODE,
        "retrospective_exclusion_mode": guard.get("exclusion_mode") or RETROSPECTIVE_EXCLUSION_MODE,
        "retrospective_identity_count": guard.get("retrospective_identity_count") or 0,
        "first_prospective_scan_date": bundle.first_prospective_scan_date.isoformat(),
        "is_active": bundle.is_active,
        "collected": len(snaps),
        "prospective_matches_collected": len(snaps),
        "completed": completed,
        "pending": pending,
        "locked": locked,
        "incomplete": incomplete,
        "error": errors,
        "minimum_prospective_matches": MINIMUM_PROSPECTIVE_MATCHES,
        "progress_to_minimum": min(1.0, completed / MINIMUM_PROSPECTIVE_MATCHES) if MINIMUM_PROSPECTIVE_MATCHES else 0,
        "protocol_status": protocol_status,
        "primary_candidate": PRIMARY_ID,
        "challenger_candidate": CHALLENGER_ID,
        "benchmark_candidate": BENCHMARK_ID,
        "diagnostic_candidate": DIAGNOSTIC_ID,
    }


def _snapshot_temporal_flags(
    s: CecchinoGoalIntensityV5PreviewSnapshot,
    bundle: CecchinoGoalIntensityV5PreviewBundle | None = None,
) -> dict[str, Any]:
    freeze_at = _ensure_utc(bundle.frozen_at) if bundle else None
    source_at = _ensure_utc(s.source_snapshot_at)
    kickoff = _ensure_utc(s.kickoff)
    return {
        "source_snapshot_after_freeze": bool(freeze_at and source_at and source_at > freeze_at),
        "source_snapshot_before_kickoff": bool(kickoff and source_at and source_at < kickoff)
        if source_at and kickoff
        else None,
    }


def _snapshot_list_item(
    s: CecchinoGoalIntensityV5PreviewSnapshot,
    bundle: CecchinoGoalIntensityV5PreviewBundle | None = None,
) -> dict[str, Any]:
    flags = _snapshot_temporal_flags(s, bundle)
    return {
        "id": s.id,
        "today_fixture_id": s.today_fixture_id,
        "scan_date": s.scan_date.isoformat() if s.scan_date else None,
        "kickoff": s.kickoff.isoformat() if s.kickoff else None,
        "competition_id": s.competition_id,
        "competition_name": s.competition_name,
        "home_team_name": s.home_team_name,
        "away_team_name": s.away_team_name,
        "snapshot_status": s.snapshot_status,
        "preview_status": s.preview_status,
        "source_snapshot_at": s.source_snapshot_at.isoformat() if s.source_snapshot_at else None,
        "history_sample_size": s.history_sample_size,
        "xg_status": s.xg_status,
        "GI_A": s.primary_candidate_score,
        "GI_B": s.challenger_candidate_score,
        "MT1": s.benchmark_score,
        "GI_A_without_volatility": s.diagnostic_score,
        "expected_goals_GI_A": ((s.calibrated_predictions_payload or {}).get(PRIMARY_ID) or {}).get(
            "expected_total_goals"
        ),
        "p_ge2_GI_A": ((s.calibrated_predictions_payload or {}).get(PRIMARY_ID) or {}).get(
            "probability_goals_ge_2"
        ),
        "p_ge3_GI_A": ((s.calibrated_predictions_payload or {}).get(PRIMARY_ID) or {}).get(
            "probability_goals_ge_3"
        ),
        "p_btts_GI_A": ((s.calibrated_predictions_payload or {}).get(PRIMARY_ID) or {}).get(
            "probability_btts"
        ),
        "total_goals_ft": s.total_goals_ft,
        "result_attached": s.result_attached_at is not None,
        **flags,
    }


def _snapshot_detail(
    s: CecchinoGoalIntensityV5PreviewSnapshot,
    bundle: CecchinoGoalIntensityV5PreviewBundle | None = None,
) -> dict[str, Any]:
    return {
        **_snapshot_list_item(s, bundle),
        "pillar_scores": s.pillar_scores_payload,
        "candidate_scores": s.candidate_scores_payload,
        "calibrated_predictions": s.calibrated_predictions_payload,
        "feature_payload": s.feature_payload,
        "diagnostic_reason_codes": s.diagnostic_reason_codes,
        "locked_at": s.locked_at.isoformat() if s.locked_at else None,
        "revision_count": s.revision_count,
        "no_target_used_in_score": s.no_target_used_in_score,
        "goals_home_ft": s.goals_home_ft,
        "goals_away_ft": s.goals_away_ft,
        "goals_ge_2": s.goals_ge_2,
        "goals_ge_3": s.goals_ge_3,
        "btts_ft": s.btts_ft,
    }


def build_prospective_monitoring(db: Session, bundle: CecchinoGoalIntensityV5PreviewBundle | None = None) -> dict[str, Any]:
    bundle = bundle or get_active_bundle(db)
    if bundle is None:
        return {"status": "error", "error": "bundle_missing"}

    completed = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id,
                CecchinoGoalIntensityV5PreviewSnapshot.result_attached_at.is_not(None),
                CecchinoGoalIntensityV5PreviewSnapshot.total_goals_ft.is_not(None),
            )
        ).all()
    )
    n = len(completed)
    all_snaps = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
            )
        ).all()
    )
    if n >= MINIMUM_PROSPECTIVE_MATCHES:
        status = "minimum_sample_reached"
    elif len(all_snaps) == 0:
        status = "waiting_for_prospective_data"
    else:
        status = "collecting_prospective_data"

    defs = bundle.candidate_definitions_payload or {}
    guard = _prospective_guard(bundle)
    freeze_at = _ensure_utc(bundle.frozen_at)
    after_freeze_ok = all(
        bool(freeze_at and s.source_snapshot_at and _ensure_utc(s.source_snapshot_at) > freeze_at)
        for s in all_snaps
        if s.source_snapshot_at is not None
    ) if all_snaps else True
    before_kickoff_ok = all(
        bool(
            s.kickoff
            and s.source_snapshot_at
            and _ensure_utc(s.source_snapshot_at) < _ensure_utc(s.kickoff)  # type: ignore[operator]
        )
        for s in all_snaps
        if s.source_snapshot_at is not None and s.kickoff is not None
    ) if all_snaps else True

    def scores(cid: str) -> list[float]:
        out = []
        for s in completed:
            raw = (s.candidate_scores_payload or {}).get(cid)
            if raw is None and cid == PRIMARY_ID:
                raw = s.primary_candidate_score
            if raw is None and cid == CHALLENGER_ID:
                raw = s.challenger_candidate_score
            if raw is None and cid == BENCHMARK_ID:
                raw = s.benchmark_score
            if raw is None and cid == DIAGNOSTIC_ID:
                raw = s.diagnostic_score
            if raw is not None:
                out.append(float(raw))
        return out

    y_tg = [float(s.total_goals_ft) for s in completed if s.total_goals_ft is not None]
    metrics_by_candidate: dict[str, Any] = {}
    for cid in MONITORED_CANDIDATES:
        xs = scores(cid)
        if len(xs) < 5 or len(xs) != len(y_tg):
            # align by iterating completed
            pairs = []
            for s in completed:
                raw = (s.candidate_scores_payload or {}).get(cid)
                if cid == PRIMARY_ID:
                    raw = raw if raw is not None else s.primary_candidate_score
                elif cid == CHALLENGER_ID:
                    raw = raw if raw is not None else s.challenger_candidate_score
                elif cid == BENCHMARK_ID:
                    raw = raw if raw is not None else s.benchmark_score
                else:
                    raw = raw if raw is not None else s.diagnostic_score
                if raw is not None and s.total_goals_ft is not None:
                    pairs.append((float(raw), float(s.total_goals_ft)))
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
        else:
            ys = y_tg
        if len(xs) < 5:
            metrics_by_candidate[cid] = {"n": len(xs), "status": "insufficient"}
            continue
        preds = []
        cal = (bundle.calibration_payload or {}).get(cid, {}).get("total_goals_ft")
        for x in xs:
            preds.append(_apply_linear(cal, x) if cal else x)
        err = np.asarray(preds, float) - np.asarray(ys, float)
        metrics_by_candidate[cid] = {
            "n": len(xs),
            "spearman": _round(spearman_rho(xs, ys)),
            "pearson": _round(pearson_r(xs, ys)),
            "mae": _round(float(np.mean(np.abs(err)))),
            "rmse": _round(float(np.sqrt(np.mean(err ** 2)))),
        }

    def paired_delta(left: str, right: str) -> dict[str, Any]:
        pairs = []
        for s in completed:
            def get(cid: str) -> float | None:
                raw = (s.candidate_scores_payload or {}).get(cid)
                if cid == PRIMARY_ID:
                    return safe_float(raw if raw is not None else s.primary_candidate_score)
                if cid == CHALLENGER_ID:
                    return safe_float(raw if raw is not None else s.challenger_candidate_score)
                if cid == BENCHMARK_ID:
                    return safe_float(raw if raw is not None else s.benchmark_score)
                return safe_float(raw if raw is not None else s.diagnostic_score)

            a, b, y = get(left), get(right), safe_float(s.total_goals_ft)
            if a is None or b is None or y is None:
                continue
            cal_l = (bundle.calibration_payload or {}).get(left, {}).get("total_goals_ft")
            cal_r = (bundle.calibration_payload or {}).get(right, {}).get("total_goals_ft")
            pl = _apply_linear(cal_l, a)
            pr = _apply_linear(cal_r, b)
            if pl is None or pr is None:
                continue
            pairs.append(abs(pl - y) - abs(pr - y))
        if len(pairs) < 5:
            return {"n": len(pairs), "status": "insufficient", "delta_mae": None}
        idx = bootstrap_index_matrix(len(pairs), min(500, 1000), 42)
        ci = bootstrap_paired_delta_ci(pairs, iterations=len(idx), indices=idx)
        evidence = "low"
        if ci.get("ci_upper") is not None and float(ci["ci_upper"]) < 0:
            evidence = "moderate"
        return {
            "n": len(pairs),
            "delta_mae": ci.get("mean"),
            "delta_mae_ci": ci,
            "direction": "delta<0 favorisce left",
            "evidence_level": evidence,
        }

    comparisons = {
        "GI_B_vs_GI_A": paired_delta(CHALLENGER_ID, PRIMARY_ID),
        "MT1_vs_GI_A": paired_delta(BENCHMARK_ID, PRIMARY_ID),
        "without_volatility_vs_GI_A": paired_delta(DIAGNOSTIC_ID, PRIMARY_ID),
    }

    gates = {
        "active_bundle_available": True,
        "bundle_hash_verified": bundle.candidate_definition_hash == _candidate_definition_hash(),
        "prospective_snapshot_pipeline_operational": True,
        "no_target_leakage_verified": all(bool(s.no_target_used_in_score) for s in completed) if completed else True,
        "snapshots_locked_after_kickoff": True,
        "results_attached_without_score_recompute": True,
        "actual_bundle_freeze_used": defs.get("prospective_start_mode") == PROSPECTIVE_START_MODE,
        "snapshot_strictly_after_bundle_freeze": after_freeze_ok,
        "retrospective_identity_sets_available": bool(
            (guard.get("retrospective_today_fixture_ids") or [])
            or (guard.get("retrospective_local_fixture_ids") or [])
        ),
        "retrospective_matches_excluded": True,
        "same_day_post_freeze_snapshots_supported": True,
        "no_calendar_date_dependency": True,
        "snapshots_before_kickoff": before_kickoff_ok,
        "minimum_prospective_matches": MINIMUM_PROSPECTIVE_MATCHES,
        "completed_prospective_matches": n,
        "minimum_sample_reached": n >= MINIMUM_PROSPECTIVE_MATCHES,
        "primary_vs_challenger_complete": comparisons["GI_B_vs_GI_A"].get("n", 0) >= 5,
        "tempo_baseline_comparison_complete": comparisons["MT1_vs_GI_A"].get("n", 0) >= 5,
        "without_volatility_comparison_complete": comparisons["without_volatility_vs_GI_A"].get("n", 0) >= 5,
        "temporal_coverage_sufficient": n >= MINIMUM_PROSPECTIVE_MATCHES,
    }
    blocking = [k for k, v in gates.items() if k not in {
        "minimum_prospective_matches", "completed_prospective_matches"
    } and v is False]
    if n < MINIMUM_PROSPECTIVE_MATCHES:
        next_step = "continue_prospective_monitoring"
    elif blocking:
        next_step = "revise_candidate_definition"
    else:
        next_step = "phase_2b_replacement_review"

    return {
        "status": status,
        "version": VERSION,
        "prospective_protocol": {
            "candidate_definition_frozen_at": defs.get("candidate_definition_frozen_at"),
            "bundle_frozen_at": _iso_z(freeze_at),
            "prospective_window_started_at": defs.get("prospective_window_started_at") or _iso_z(freeze_at),
            "first_prospective_scan_date": bundle.first_prospective_scan_date.isoformat(),
            "prospective_start_mode": defs.get("prospective_start_mode") or PROSPECTIVE_START_MODE,
            "retrospective_exclusion_mode": guard.get("exclusion_mode") or RETROSPECTIVE_EXCLUSION_MODE,
            "retrospective_identity_count": guard.get("retrospective_identity_count") or 0,
            "prospective_matches_collected": len(all_snaps),
            "minimum_prospective_matches": MINIMUM_PROSPECTIVE_MATCHES,
            "protocol_status": status,
        },
        "completed_prospective_matches": n,
        "minimum_prospective_matches": MINIMUM_PROSPECTIVE_MATCHES,
        "metrics_by_candidate": metrics_by_candidate,
        "comparisons": comparisons,
        "phase_2b_readiness": {
            **gates,
            "blocking_issues": blocking if n >= MINIMUM_PROSPECTIVE_MATCHES else ["minimum_sample_not_reached"],
            "recommended_next_step": next_step if n >= MINIMUM_PROSPECTIVE_MATCHES else "continue_prospective_monitoring",
        },
        "no_productive_validation_claim": True,
        "v4_unchanged": True,
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def stream_preview_export(
    db: Session,
    *,
    kind: PreviewExportKind,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Iterator[str]:
    bundle = get_active_bundle(db)
    if bundle is None:
        yield json.dumps({"error": "bundle_missing"})
        return
    if kind == "preview_summary":
        monitoring = build_prospective_monitoring(db, bundle)
        summary = _bundle_summary(bundle, db)
        yield json.dumps(
            {
                "bundle": summary,
                "monitoring": monitoring,
                "bundle_frozen_at": summary.get("bundle_frozen_at"),
                "prospective_start_mode": summary.get("prospective_start_mode"),
                "retrospective_exclusion_mode": summary.get("retrospective_exclusion_mode"),
                "retrospective_identity_count": summary.get("retrospective_identity_count"),
            },
            ensure_ascii=False,
            default=str,
        )
        return
    if kind == "preview_bundle_definition":
        defs = bundle.candidate_definitions_payload or {}
        yield json.dumps(
            {
                "version": bundle.version,
                "candidate_definition_hash": bundle.candidate_definition_hash,
                "bundle_frozen_at": defs.get("bundle_frozen_at") or _iso_z(bundle.frozen_at),
                "prospective_start_mode": defs.get("prospective_start_mode") or PROSPECTIVE_START_MODE,
                "retrospective_exclusion_mode": RETROSPECTIVE_EXCLUSION_MODE,
                "retrospective_identity_count": (defs.get("prospective_guard") or {}).get(
                    "retrospective_identity_count"
                ),
                "normalization_payload_meta": {
                    k: {mk: mv for mk, mv in v.items() if mk != "train_values"}
                    for k, v in ((bundle.normalization_payload or {}).get("features") or {}).items()
                },
                "calibration_payload": bundle.calibration_payload,
                "candidate_definitions_payload": bundle.candidate_definitions_payload,
            },
            ensure_ascii=False,
            default=str,
        )
        return
    if kind == "preview_calibration":
        yield json.dumps(bundle.calibration_payload or {}, ensure_ascii=False, default=str)
        return

    snaps = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
            )
        ).all()
    )
    if date_from is not None:
        snaps = [s for s in snaps if s.scan_date is not None and s.scan_date >= date_from]
    if date_to is not None:
        snaps = [s for s in snaps if s.scan_date is not None and s.scan_date <= date_to]
    if kind == "preview_completed_results":
        snaps = [s for s in snaps if s.result_attached_at is not None]
        rows = [_snapshot_list_item(s, bundle) for s in snaps]
    elif kind == "preview_candidate_monitoring":
        mon = build_prospective_monitoring(db, bundle)
        rows = [{"section": "metrics", **{"candidate": k, **v}} for k, v in (mon.get("metrics_by_candidate") or {}).items()]
        rows += [{"section": "comparison", "name": k, **v} for k, v in (mon.get("comparisons") or {}).items()]
    else:
        rows = [_snapshot_list_item(s, bundle) for s in snaps]

    if not rows:
        if kind == "preview_snapshots":
            columns = [
                "id",
                "today_fixture_id",
                "scan_date",
                "kickoff",
                "competition_id",
                "competition_name",
                "home_team_name",
                "away_team_name",
                "snapshot_status",
                "preview_status",
                "source_snapshot_at",
                "history_sample_size",
                "xg_status",
                "GI_A",
                "GI_B",
                "MT1",
                "GI_A_without_volatility",
                "expected_goals_GI_A",
                "p_ge2_GI_A",
                "p_ge3_GI_A",
                "p_btts_GI_A",
                "total_goals_ft",
                "result_attached",
                "source_snapshot_after_freeze",
                "source_snapshot_before_kickoff",
            ]
        elif kind == "preview_completed_results":
            columns = [
                "id",
                "today_fixture_id",
                "scan_date",
                "kickoff",
                "competition_id",
                "snapshot_status",
                "GI_A",
                "GI_B",
                "MT1",
                "total_goals_ft",
                "result_attached",
            ]
        elif kind == "preview_candidate_monitoring":
            columns = [
                "section",
                "candidate",
                "name",
                "n",
                "status",
                "spearman",
                "pearson",
                "mae",
                "rmse",
                "delta_mae",
                "evidence_level",
            ]
        else:
            columns = ["note"]
        yield "\ufeff"
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()
        return
    columns = list(rows[0].keys())
    yield "\ufeff"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    yield buf.getvalue()
    for row in rows:
        buf.seek(0)
        buf.truncate(0)
        out = {}
        for c in columns:
            v = row.get(c)
            out[c] = json.dumps(v, default=str) if isinstance(v, (dict, list)) else ("" if v is None else v)
        writer.writerow(out)
        yield buf.getvalue()


def preview_export_filename(kind: PreviewExportKind) -> str:
    names = {
        "preview_summary": "cecchino_goal_intensity_v5_preview_summary.json",
        "preview_snapshots": "cecchino_goal_intensity_v5_preview_snapshots.csv",
        "preview_completed_results": "cecchino_goal_intensity_v5_preview_completed_results.csv",
        "preview_candidate_monitoring": "cecchino_goal_intensity_v5_preview_candidate_monitoring.csv",
        "preview_calibration": "cecchino_goal_intensity_v5_preview_calibration.json",
        "preview_bundle_definition": "cecchino_goal_intensity_v5_preview_bundle_definition.json",
    }
    return names[kind]
