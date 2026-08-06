"""Loader e scoring frozen per benchmark storico GI V4 vs V5 (no fit)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
    CecchinoGoalIntensityV5PreviewBundle,
)
from app.models.cecchino_lab_goal_intensity_benchmark_job import REQUIRED_BUNDLE_VERSION
from app.services.cecchino.cecchino_goal_intensity_analysis import (
    VERSION as V4_FORMULA_VERSION,
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
    apply_calibrations,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    BUNDLE_FEATURE_KEYS,
    CHALLENGER_ID,
    PRIMARY_ID,
    _ecdfs_from_bundle,
    _round,
    score_features_with_bundle,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import safe_float
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.goal_intensity_historical_v4_reconstruction import (
    CompetitionProxyCache,
    RECONSTRUCTION_VERSION,
    extract_v4_certified,
)

MAIN_MODEL_IDS = (
    V4_MODEL_ID,
    PRIMARY_ID,
    CHALLENGER_ID,
    GI_E_ID,
    GI_F_ID,
)

RAW_EQUALITY_TOLERANCE = 1e-9


def _sha256_canonical(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_frozen_goal_intensity_candidate_bundle(
    db: Session,
    *,
    version: str = REQUIRED_BUNDLE_VERSION,
) -> CecchinoGoalIntensityV5PreviewBundle:
    """Carica esclusivamente il bundle frozen v2.1 (mai l'active v1.1)."""
    if version != TARGET_BUNDLE_VERSION and version != REQUIRED_BUNDLE_VERSION:
        raise CecchinoLabImportError(
            "bundle_version_not_allowed",
            f"Versione bundle non ammessa: {version}",
            details={"required": REQUIRED_BUNDLE_VERSION, "got": version},
        )
    row = db.scalars(
        select(CecchinoGoalIntensityV5PreviewBundle)
        .where(CecchinoGoalIntensityV5PreviewBundle.version == TARGET_BUNDLE_VERSION)
        .order_by(CecchinoGoalIntensityV5PreviewBundle.id.desc())
    ).first()
    if row is None:
        raise CecchinoLabImportError(
            "frozen_candidate_bundle_not_found",
            f"Bundle {TARGET_BUNDLE_VERSION} non trovato",
        )
    validate_frozen_candidate_bundle(row)
    return row


def validate_frozen_candidate_bundle(bundle: CecchinoGoalIntensityV5PreviewBundle) -> dict[str, Any]:
    """Verifica vincoli frozen; solleva se il bundle non è idoneo."""
    defs = bundle.candidate_definitions_payload or {}
    cal = bundle.calibration_payload or {}
    errors: list[str] = []

    if bundle.version != TARGET_BUNDLE_VERSION:
        errors.append("version_mismatch")
    if bundle.status != BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE:
        errors.append("status_not_frozen_external_benchmark_candidate")
    if bundle.is_active is True:
        errors.append("bundle_is_active_rejected")
    if defs.get("intended_use") != "historical_external_benchmark_only":
        errors.append("intended_use_mismatch")
    if defs.get("development_protocol_version") != DEVELOPMENT_PROTOCOL_VERSION:
        errors.append("protocol_version_mismatch")
    active_ids = list(defs.get("active_candidate_ids") or [])
    if active_ids != list(ACTIVE_CANDIDATE_IDS):
        errors.append("active_candidate_ids_mismatch")
    archived = list(defs.get("archived_candidate_ids") or [])
    if set(archived) != set(ARCHIVED_CANDIDATE_IDS):
        errors.append("archived_candidate_ids_mismatch")
    for cid in ACTIVE_CANDIDATE_IDS:
        if cid not in cal or not isinstance(cal.get(cid), dict):
            errors.append(f"missing_calibration_{cid}")
    gi_f_def = defs.get(GI_F_ID) or {}
    weights = defs.get("gi_f_weights") or gi_f_def.get("weights")
    alpha = defs.get("selected_alpha")
    if alpha is None:
        alpha = gi_f_def.get("selected_alpha")
    if not isinstance(weights, dict) or not weights:
        errors.append("missing_gi_f_weights")
    else:
        for p in GI_F_PILLARS:
            if p not in weights:
                errors.append(f"missing_gi_f_weight_{p}")
    if alpha is None:
        errors.append("missing_selected_alpha")
    if not bundle.candidate_definition_hash:
        errors.append("missing_candidate_definition_hash")
    if not defs.get("parent_bundle_id") and not defs.get("parent_bundle_version"):
        errors.append("missing_parent_bundle")
    holdout = defs.get("holdout_access_count")
    if holdout is None:
        holdout = (defs.get("holdout_metrics") or {}).get("holdout_access_count")
    try:
        holdout_n = int(holdout) if holdout is not None else 1
    except (TypeError, ValueError):
        holdout_n = None
        errors.append("holdout_access_count_invalid")
    if holdout_n is not None and holdout_n != 1:
        errors.append("holdout_access_count_not_1")
    if not bundle.fixture_ids_hash:
        errors.append("missing_fixture_ids_hash")

    if errors:
        raise CecchinoLabImportError(
            "frozen_candidate_bundle_invalid",
            "Bundle frozen non valida per historical benchmark",
            details={"errors": errors, "bundle_id": bundle.id, "version": bundle.version},
        )
    return {
        "id": bundle.id,
        "version": bundle.version,
        "status": bundle.status,
        "is_active": bool(bundle.is_active),
        "definition_hash": bundle.candidate_definition_hash,
        "fixture_ids_hash": bundle.fixture_ids_hash,
        "targets_hash": bundle.targets_hash,
        "parent_bundle_id": defs.get("parent_bundle_id"),
        "parent_bundle_version": defs.get("parent_bundle_version"),
        "protocol_version": defs.get("development_protocol_version"),
        "active_candidate_ids": active_ids,
        "archived_candidate_ids": archived,
        "selected_alpha": alpha,
        "gi_f_weights": weights,
        "intended_use": defs.get("intended_use"),
        "holdout_access_count": holdout_n if holdout_n is not None else 1,
        "live_scoring_enabled": bool(defs.get("live_scoring_enabled")),
        "signals_integration_enabled": bool(defs.get("signals_integration_enabled")),
    }


def sanitize_prematch_features(raw: dict[str, Any] | None) -> dict[str, float | None]:
    """Payload feature pre-match senza risultati/quote/target."""
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, float | None] = {}
    for k in BUNDLE_FEATURE_KEYS:
        out[k] = safe_float(src.get(k))
    return out


def extract_v5_features_from_snapshot(snapshot_like: Any) -> tuple[dict[str, float | None] | None, str | None]:
    """Estrae le 7 feature core da payload già persistiti nello snapshot Lab."""
    gi = getattr(snapshot_like, "goal_intensity_compatibility_json", None)
    if not isinstance(gi, dict):
        gi = {}
    inputs = gi.get("inputs") if isinstance(gi.get("inputs"), dict) else {}
    features = inputs.get("bundle_features")
    if not isinstance(features, dict):
        # fallback feature_row_for_profile
        fr = gi.get("feature_row_for_profile") if isinstance(gi.get("feature_row_for_profile"), dict) else {}
        features = fr.get("features") if isinstance(fr.get("features"), dict) else None
    if not isinstance(features, dict):
        return None, "missing_v5_features"
    sanitized = sanitize_prematch_features(features)
    if any(sanitized.get(k) is None for k in BUNDLE_FEATURE_KEYS):
        return sanitized, "incomplete_v5_features"
    return sanitized, None


def extract_v4_from_historical_snapshot(
    snapshot_like: Any,
    *,
    proxy_cache: CompetitionProxyCache | None = None,
    source_code_commit: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Compat: restituisce (payload, reason). Usa extract_v4_certified (A→B→C→D)."""
    result = extract_v4_certified(
        snapshot_like,
        proxy_cache=proxy_cache,
        source_code_commit=source_code_commit,
    )
    return result.get("v4_payload"), result.get("reason")


def extract_v4_with_provenance(
    snapshot_like: Any,
    *,
    proxy_cache: CompetitionProxyCache | None = None,
    source_code_commit: str | None = None,
) -> dict[str, Any]:
    """Estrazione V4 certificata con provenienza (unica per preflight/pilot/full/resume)."""
    return extract_v4_certified(
        snapshot_like,
        proxy_cache=proxy_cache,
        source_code_commit=source_code_commit,
    )


def extract_ft_target(result_json: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(result_json, dict):
        return None, "missing_ft_result"
    ft = result_json.get("fulltime") if isinstance(result_json.get("fulltime"), dict) else {}
    home = ft.get("home")
    away = ft.get("away")
    if home is None or away is None:
        # alternate shapes
        home = result_json.get("ft_home_goals", result_json.get("home"))
        away = result_json.get("ft_away_goals", result_json.get("away"))
    try:
        gh = int(home)
        ga = int(away)
    except (TypeError, ValueError):
        return None, "invalid_ft_result"
    if gh < 0 or ga < 0:
        return None, "invalid_ft_result"
    total = gh + ga
    return {
        "goals_home_ft": gh,
        "goals_away_ft": ga,
        "total_goals_ft": total,
        "goals_ge_2": int(total >= 2),
        "goals_ge_3": int(total >= 3),
        "btts_ft": int(gh > 0 and ga > 0),
    }, None


def _gi_f_raw_from_pillars(
    pillars: dict[str, Any],
    weights: dict[str, Any],
) -> float | None:
    total = 0.0
    for pid in GI_F_PILLARS:
        w = safe_float(weights.get(pid))
        p = safe_float(pillars.get(pid))
        if w is None or p is None:
            return None
        total += float(w) * (float(p) / 100.0)
    return _round(100.0 * total)


def score_five_models_with_frozen_bundle(
    *,
    features: dict[str, float | None],
    v4_payload: dict[str, Any] | None,
    bundle: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    """Calcola predizioni V4 + GI_A/B/E/F senza fit. features non deve contenere risultati."""
    # Guard: features keys only
    clean = sanitize_prematch_features(features)
    for forbidden in ("total_goals_ft", "goals_home_ft", "goals_away_ft", "btts_ft", "result"):
        if forbidden in features:
            raise CecchinoLabImportError(
                "result_leakage_in_features",
                f"Campo risultato presente nello scoring: {forbidden}",
            )

    parent_scored = score_features_with_bundle(clean, bundle)
    pillars = parent_scored.get("pillar_scores") or {}
    defs = bundle.candidate_definitions_payload or {}
    cal_all = bundle.calibration_payload or {}

    gi_a_raw = safe_float((parent_scored.get("candidate_scores") or {}).get(PRIMARY_ID))
    gi_b_raw = safe_float((parent_scored.get("candidate_scores") or {}).get(CHALLENGER_ID))

    # Prefer calibrations from candidate bundle payload for A/B
    cal_a = cal_all.get(PRIMARY_ID) or {}
    cal_b = cal_all.get(CHALLENGER_ID) or {}
    cal_e = cal_all.get(GI_E_ID) or {}
    cal_f = cal_all.get(GI_F_ID) or {}

    pred_a = apply_calibrations(float(gi_a_raw), cal_a) if gi_a_raw is not None else None
    pred_b = apply_calibrations(float(gi_b_raw), cal_b) if gi_b_raw is not None else None

    # GI_E: raw identical to GI_A
    gi_e_raw = gi_a_raw
    pred_e = apply_calibrations(float(gi_e_raw), cal_e) if gi_e_raw is not None else None
    if gi_a_raw is not None and gi_e_raw is not None:
        if abs(float(gi_e_raw) - float(gi_a_raw)) > RAW_EQUALITY_TOLERANCE:
            raise CecchinoLabImportError(
                "gi_e_raw_mismatch",
                "raw_GI_E deve essere identico a raw_GI_A",
                details={"gi_a": gi_a_raw, "gi_e": gi_e_raw},
            )

    weights = defs.get("gi_f_weights") or ((defs.get(GI_F_ID) or {}).get("weights")) or {}
    selected_alpha = defs.get("selected_alpha")
    if selected_alpha is None:
        selected_alpha = (defs.get(GI_F_ID) or {}).get("selected_alpha")
    gi_f_raw = _gi_f_raw_from_pillars(pillars, weights) if weights else None
    pred_f = apply_calibrations(float(gi_f_raw), cal_f) if gi_f_raw is not None else None

    v4_pred = None
    if isinstance(v4_payload, dict) and v4_payload.get("status") == "available":
        eg = safe_float(v4_payload.get("expected_goals_total"))
        thresholds = v4_payload.get("thresholds") if isinstance(v4_payload.get("thresholds"), dict) else {}
        p2 = None
        p3 = None
        for key, out_key in (("over_1_5", "p2"), ("over_2_5", "p3")):
            block = thresholds.get(key) if isinstance(thresholds, dict) else None
            if isinstance(block, dict):
                val = safe_float(block.get("probability"))
                if out_key == "p2":
                    p2 = val
                else:
                    p3 = val
        v4_pred = {
            "model_id": V4_MODEL_ID,
            "raw_score": None,
            "expected_total_goals": eg,
            "probability_goals_ge_2": p2,
            "probability_goals_ge_3": p3,
            "probability_btts": None,
            "btts_status": "not_comparable",
        }

    def _pack(model_id: str, raw: float | None, applied: dict[str, Any] | None) -> dict[str, Any] | None:
        if applied is None or raw is None:
            return None
        return {
            "model_id": model_id,
            "raw_score": raw,
            "expected_total_goals": applied.get("expected_total_goals"),
            "probability_goals_ge_2": applied.get("probability_goals_ge_2"),
            "probability_goals_ge_3": applied.get("probability_goals_ge_3"),
            "probability_btts": applied.get("probability_btts"),
        }

    models = {
        V4_MODEL_ID: v4_pred,
        PRIMARY_ID: _pack(PRIMARY_ID, gi_a_raw, pred_a),
        CHALLENGER_ID: _pack(CHALLENGER_ID, gi_b_raw, pred_b),
        GI_E_ID: _pack(GI_E_ID, gi_e_raw, pred_e),
        GI_F_ID: _pack(GI_F_ID, gi_f_raw, pred_f),
    }
    five_ok = all(models.get(mid) is not None for mid in MAIN_MODEL_IDS)
    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "bundle_id": bundle.id,
        "bundle_definition_hash": bundle.candidate_definition_hash,
        "features_used": clean,
        "pillar_scores": pillars,
        "models": models,
        "gi_e_raw_equals_gi_a": True,
        "gi_f_selected_alpha": selected_alpha,
        "gi_f_weights_frozen": weights,
        "archived_not_selected": {
            mid: "archived_not_selected" for mid in ARCHIVED_CANDIDATE_IDS
        },
        "five_models_available": five_ok,
        "no_target_used_in_score": True,
        "no_refit": True,
        "ecdf_source": "frozen_bundle_normalization",
    }


def prediction_input_hash(
    *,
    features: dict[str, Any],
    bundle_definition_hash: str,
    snapshot_id: int,
    v4_source: str | None = None,
    reconstruction_version: str | None = None,
    v4_formula_version: str | None = None,
    reconstruction_input_hash: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "features": sanitize_prematch_features(features),
        "bundle_definition_hash": bundle_definition_hash,
        "snapshot_id": snapshot_id,
        "v4_formula_version": v4_formula_version or V4_FORMULA_VERSION,
    }
    if v4_source:
        payload["v4_source"] = v4_source
    if reconstruction_version:
        payload["reconstruction_version"] = reconstruction_version
    elif v4_source == "reconstructed_current_v4_from_frozen_historical_inputs":
        payload["reconstruction_version"] = RECONSTRUCTION_VERSION
    if reconstruction_input_hash:
        payload["reconstruction_input_hash"] = reconstruction_input_hash
    return _sha256_canonical(payload)
