"""Phase 2C — sviluppo candidati GI_E / GI_F e freeze bundle benchmark esterno.

Nessuna attivazione live, nessun supersede del parent v1.1, nessuna run 2021/22.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
    PREVIEW_BUNDLE_VERSION,
    CecchinoGoalIntensityV5PreviewBundle,
)
from app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark import (
    BENCHMARK_ID,
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    CHALLENGER_ID,
    DIAGNOSTIC_ID,
    GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
    PRIMARY_ID,
    V4_MODEL_ID,
    _binary_metrics,
    _clip_prob,
    _continuous_metrics,
    _evidence_level,
    _pairwise_error_comparison,
    _preferred_side,
    _round,
    build_goal_intensity_v4_v5_prospective_benchmark,
    load_goal_intensity_prospective_paired_observations,
)
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    _fit_linear_calibration,
    _fit_logistic_calibration,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    VERSION as PARENT_BUNDLE_VERSION,
    _apply_linear,
    _apply_logistic,
    _ensure_utc,
    get_active_bundle,
)


def _get_phase_2c_parent_bundle(db: Session) -> CecchinoGoalIntensityV5PreviewBundle | None:
    """Parent v1.1 esplicito (anche superseded). Evita di usare il bundle ufficiale attivo."""
    from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
        get_preview_bundle_v1_1,
    )

    # Preferisci get_active_bundle se ancora preview (pre-cutover + test monkeypatch).
    active = get_active_bundle(db)
    if active is not None and getattr(active, "version", None) == PREVIEW_BUNDLE_VERSION:
        return active
    # Post-cutover: preview superseded, caricalo per versione
    parent = get_preview_bundle_v1_1(db)
    if parent is not None and getattr(parent, "version", None) == PREVIEW_BUNDLE_VERSION:
        return parent
    return None
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import (
    bootstrap_index_matrix,
    safe_float,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

DEVELOPMENT_PROTOCOL_VERSION = "cecchino_goal_intensity_v5_phase_2c_candidate_development_v1"
TARGET_BUNDLE_VERSION = "cecchino_goal_intensity_v5_candidate_bundle_v2_1"
PHASE_2C_FREEZE_CONFIRM_TOKEN = "FREEZE_GOAL_INTENSITY_V5_CANDIDATE_BUNDLE_V2_1"
CODE_VERSION = "cecchino_goal_intensity_v5_phase_2c_code_v1"

GI_E_ID = "GI_E_PRIMARY_RECALIBRATED"
GI_F_ID = "GI_F_REGULARIZED_PILLARS"

ACTIVE_CANDIDATE_IDS = (PRIMARY_ID, CHALLENGER_ID, GI_E_ID, GI_F_ID)
ARCHIVED_CANDIDATE_IDS = (BENCHMARK_ID, DIAGNOSTIC_ID)

GI_F_PILLARS = (
    "OP1_HOME_LONG_TERM",
    "OP2_HOME_RECENCY",
    "DV1_MEAN_CONCEDED",
    "MT1_LONG_TERM",
    "MT2_LONG_TERM_PLUS_RECENCY",
    "OV1_STD",
)
GI_F_ALPHA_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)

MIN_PAIRED_TOTAL = 500
MIN_SPLIT_N = 100
SPLIT_TARGETS = (0.50, 0.20, 0.30)  # train, validation, holdout

_CACHE_TTL_S = 300.0
_cache_lock = threading.Lock()
_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def clear_goal_intensity_phase_2c_cache() -> None:
    with _cache_lock:
        _cache.clear()


class HoldoutAccessGuard:
    """Conta accessi decisionali all'holdout; freeze richiede count == 1."""

    def __init__(self) -> None:
        self.count = 0
        self._locked = False

    def access(self) -> None:
        if self._locked:
            raise RuntimeError("holdout_reused_for_selection")
        self.count += 1

    def lock(self) -> None:
        self._locked = True


def _sha256_canonical(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _kickoff_utc(obs: dict[str, Any]) -> datetime:
    ko = obs.get("kickoff")
    if isinstance(ko, datetime):
        ensured = _ensure_utc(ko)
        if ensured is not None:
            return ensured
    sd = obs.get("scan_date")
    if isinstance(sd, date):
        return datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _sort_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        observations,
        key=lambda o: (
            _kickoff_utc(o),
            int(o.get("today_fixture_id") or 0),
            int(o.get("snapshot_id") or 0),
        ),
    )


def temporal_split(
    observations: list[dict[str, Any]],
    *,
    train_frac: float = 0.50,
    val_frac: float = 0.20,
) -> dict[str, Any]:
    """Split cronologico 50/20/30 senza spezzare la stessa data UTC."""
    ordered = _sort_observations(observations)
    n = len(ordered)
    if n == 0:
        return {
            "status": "blocked",
            "reason": "empty_cohort",
            "train": [],
            "validation": [],
            "holdout": [],
            "meta": {},
        }

    # Group by UTC date
    by_date: list[tuple[date, list[dict[str, Any]]]] = []
    for o in ordered:
        d = _kickoff_utc(o).date()
        if not by_date or by_date[-1][0] != d:
            by_date.append((d, [o]))
        else:
            by_date[-1][1].append(o)

    target_train = int(round(n * train_frac))
    target_val = int(round(n * val_frac))

    train: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []

    # Fill train until closest to target without splitting a day
    i = 0
    while i < len(by_date):
        day_rows = by_date[i][1]
        if train and abs(len(train) - target_train) <= abs(len(train) + len(day_rows) - target_train):
            if len(train) >= target_train:
                break
            # if adding moves closer or equal and still under holdout budget, continue only if under
        if not train or abs(len(train) + len(day_rows) - target_train) <= abs(len(train) - target_train):
            if len(train) < target_train or not train:
                train.extend(day_rows)
                i += 1
                continue
        break

    # Validation
    while i < len(by_date):
        day_rows = by_date[i][1]
        if validation and abs(len(validation) - target_val) <= abs(
            len(validation) + len(day_rows) - target_val
        ):
            if len(validation) >= target_val:
                break
        if not validation or abs(len(validation) + len(day_rows) - target_val) <= abs(
            len(validation) - target_val
        ):
            if len(validation) < target_val or not validation:
                validation.extend(day_rows)
                i += 1
                continue
        break

    while i < len(by_date):
        holdout.extend(by_date[i][1])
        i += 1

    # Safety: if holdout empty, move last validation days (shouldn't happen with enough data)
    if not holdout and validation:
        # move last date group from validation
        last_d = _kickoff_utc(validation[-1]).date()
        move = [o for o in validation if _kickoff_utc(o).date() == last_d]
        validation = [o for o in validation if _kickoff_utc(o).date() != last_d]
        holdout = move

    def _split_meta(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
        if not rows:
            return {
                "name": name,
                "n": 0,
                "date_min": None,
                "date_max": None,
                "kickoff_min": None,
                "kickoff_max": None,
                "fixture_ids_hash": _sha256_canonical([]),
                "targets_hash": _sha256_canonical([]),
                "competition_distribution": {},
                "result_distribution": {},
                "target_rates": {},
            }
        kicks = [_kickoff_utc(o) for o in rows]
        dates = [k.date().isoformat() for k in kicks]
        comps = Counter(str(o.get("competition_id") or "unknown") for o in rows)
        totals = [float(o["y_total"]) for o in rows]
        ge2 = [int(o["y_ge2"]) for o in rows]
        ge3 = [int(o["y_ge3"]) for o in rows]
        btts = [int(o["y_btts"]) for o in rows if o.get("y_btts") is not None]
        fixture_ids = sorted(
            {
                int(o["local_fixture_id"])
                if o.get("local_fixture_id") is not None
                else int(o["today_fixture_id"] or 0)
                for o in rows
            }
        )
        targets = [
            {
                "fixture": fid,
                "y_total": float(o["y_total"]),
                "y_ge2": int(o["y_ge2"]),
                "y_ge3": int(o["y_ge3"]),
                "y_btts": o.get("y_btts"),
            }
            for fid, o in zip(
                [
                    int(o["local_fixture_id"])
                    if o.get("local_fixture_id") is not None
                    else int(o["today_fixture_id"] or 0)
                    for o in rows
                ],
                rows,
            )
        ]
        return {
            "name": name,
            "n": len(rows),
            "date_min": min(dates),
            "date_max": max(dates),
            "kickoff_min": min(kicks).isoformat(),
            "kickoff_max": max(kicks).isoformat(),
            "fixture_ids_hash": _sha256_canonical(fixture_ids),
            "targets_hash": _sha256_canonical(targets),
            "competition_distribution": dict(sorted(comps.items())),
            "result_distribution": {
                "mean_total_goals": _round(float(np.mean(totals))),
                "ge2_rate": _round(float(np.mean(ge2))),
                "ge3_rate": _round(float(np.mean(ge3))),
            },
            "target_rates": {
                "goals_ge_2": _round(float(np.mean(ge2))),
                "goals_ge_3": _round(float(np.mean(ge3))),
                "btts_ft": _round(float(np.mean(btts))) if btts else None,
            },
        }

    train_ids = {
        o.get("local_fixture_id") or ("t", o.get("today_fixture_id")) for o in train
    }
    val_ids = {
        o.get("local_fixture_id") or ("t", o.get("today_fixture_id")) for o in validation
    }
    hold_ids = {
        o.get("local_fixture_id") or ("t", o.get("today_fixture_id")) for o in holdout
    }
    overlap = (train_ids & val_ids) | (train_ids & hold_ids) | (val_ids & hold_ids)

    train_dates = {_kickoff_utc(o).date() for o in train}
    val_dates = {_kickoff_utc(o).date() for o in validation}
    hold_dates = {_kickoff_utc(o).date() for o in holdout}
    date_overlap = (train_dates & val_dates) | (train_dates & hold_dates) | (val_dates & hold_dates)

    blocking: list[str] = []
    if n < MIN_PAIRED_TOTAL:
        blocking.append("paired_total_below_minimum")
    if len(train) < MIN_SPLIT_N:
        blocking.append("train_below_minimum")
    if len(validation) < MIN_SPLIT_N:
        blocking.append("validation_below_minimum")
    if len(holdout) < MIN_SPLIT_N:
        blocking.append("holdout_below_minimum")
    if overlap:
        blocking.append("fixture_overlap_across_splits")
    if date_overlap:
        blocking.append("utc_date_split_across_splits")
    if train and validation:
        if max(_kickoff_utc(o) for o in train) > min(_kickoff_utc(o) for o in validation):
            blocking.append("validation_not_after_train")
    if validation and holdout:
        if max(_kickoff_utc(o) for o in validation) > min(_kickoff_utc(o) for o in holdout):
            blocking.append("holdout_not_after_validation")

    status = "ok" if not blocking else "blocked"
    train_meta = _split_meta(train, "train")
    val_meta = _split_meta(validation, "validation")
    hold_meta = _split_meta(holdout, "holdout")

    return {
        "status": status,
        "blocking_reasons": blocking,
        "train": train,
        "validation": validation,
        "holdout": holdout,
        "meta": {
            "train": train_meta,
            "validation": val_meta,
            "holdout": hold_meta,
            "protocol": {
                "train_frac": train_frac,
                "validation_frac": val_frac,
                "holdout_frac": round(1.0 - train_frac - val_frac, 4),
                "no_shuffle": True,
                "no_stratified_random": True,
                "date_aware": True,
            },
            "kickoff_boundary": {
                "train_end": train_meta.get("kickoff_max"),
                "validation_end": val_meta.get("kickoff_max"),
                "holdout_start": hold_meta.get("kickoff_min"),
            },
        },
    }


def _serialize_cal(cal: dict[str, Any] | None, *, train_validation_n: int | None = None) -> dict[str, Any] | None:
    if not cal:
        return None
    out = {
        "method": cal.get("calibration_method"),
        "calibration_method": cal.get("calibration_method"),
        "intercept": cal.get("intercept"),
        "coefficient": cal.get("coefficient"),
        "train_n": cal.get("train_n"),
        "train_validation_n": train_validation_n if train_validation_n is not None else cal.get("train_n"),
        "positive_rate": cal.get("train_positive_rate"),
        "convergence_status": "ok",
        "prediction_min": None,
        "prediction_max": None,
        "clipping_policy": "prob_clip_1e-6" if "logistic" in str(cal.get("calibration_method") or "") else "none",
    }
    return out


def fit_calibrations_for_scores(
    scores: list[float],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    y_total = [float(o["y_total"]) for o in observations]
    y_ge2 = [float(o["y_ge2"]) for o in observations]
    y_ge3 = [float(o["y_ge3"]) for o in observations]
    btts_pairs = [
        (scores[i], float(o["y_btts"]))
        for i, o in enumerate(observations)
        if o.get("y_btts") is not None
    ]
    linear = _fit_linear_calibration(scores, y_total)
    ge2 = _fit_logistic_calibration(scores, y_ge2)
    ge3 = _fit_logistic_calibration(scores, y_ge3)
    btts = None
    if len(btts_pairs) >= 5:
        btts = _fit_logistic_calibration(
            [a for a, _ in btts_pairs],
            [b for _, b in btts_pairs],
        )
    payload = {
        "total_goals_ft": _serialize_cal(linear, train_validation_n=len(scores)),
        "goals_ge_2": _serialize_cal(ge2, train_validation_n=len(scores)),
        "goals_ge_3": _serialize_cal(ge3, train_validation_n=len(scores)),
        "btts_ft": _serialize_cal(btts, train_validation_n=len(btts_pairs) if btts else 0),
    }
    # attach private predictors for evaluation within process
    payload["_linear"] = linear
    payload["_ge2"] = ge2
    payload["_ge3"] = ge3
    payload["_btts"] = btts
    # prediction ranges on train
    if linear and linear.get("_predict") and payload.get("total_goals_ft"):
        preds = list(linear["_predict"](scores))
        payload["total_goals_ft"]["prediction_min"] = _round(float(min(preds)))
        payload["total_goals_ft"]["prediction_max"] = _round(float(max(preds)))
        payload["total_goals_ft"]["calibration_hash"] = _sha256_canonical(
            {"i": linear.get("intercept"), "c": linear.get("coefficient"), "n": linear.get("train_n")}
        )
    private_map = {"goals_ge_2": ge2, "goals_ge_3": ge3, "btts_ft": btts}
    for key, cal in private_map.items():
        if cal and cal.get("_predict_proba") and payload.get(key):
            sc = scores if key != "btts_ft" else [a for a, _ in btts_pairs]
            probs = list(cal["_predict_proba"](sc))
            payload[key]["prediction_min"] = _round(float(min(probs)))
            payload[key]["prediction_max"] = _round(float(max(probs)))
            payload[key]["calibration_hash"] = _sha256_canonical(
                {
                    "i": cal.get("intercept"),
                    "c": cal.get("coefficient"),
                    "n": cal.get("train_n"),
                }
            )
    return payload


def apply_calibrations(score: float, cal_payload: dict[str, Any]) -> dict[str, float | None]:
    return {
        "raw_score": score,
        "expected_total_goals": _apply_linear(cal_payload.get("total_goals_ft"), score),
        "probability_goals_ge_2": _apply_logistic(cal_payload.get("goals_ge_2"), score),
        "probability_goals_ge_3": _apply_logistic(cal_payload.get("goals_ge_3"), score),
        "probability_btts": _apply_logistic(cal_payload.get("btts_ft"), score),
    }


def evaluate_candidate(
    observations: list[dict[str, Any]],
    scores: list[float],
    cal_payload: dict[str, Any],
    *,
    model_id: str,
) -> dict[str, Any]:
    preds = []
    p2 = []
    p3 = []
    for sc in scores:
        applied = apply_calibrations(float(sc), cal_payload)
        preds.append(float(applied["expected_total_goals"] or 0.0))
        p2.append(float(applied["probability_goals_ge_2"] or 0.0))
        p3.append(float(applied["probability_goals_ge_3"] or 0.0))
    y_total = [float(o["y_total"]) for o in observations]
    y_ge2 = [int(o["y_ge2"]) for o in observations]
    y_ge3 = [int(o["y_ge3"]) for o in observations]
    continuous = _continuous_metrics(preds, y_total)
    # rename bias
    continuous["bias"] = continuous.pop("mean_error", None)
    ge2 = _binary_metrics(p2, y_ge2)
    ge3 = _binary_metrics(p3, y_ge3)
    btts_pairs = []
    for o, sc in zip(observations, scores):
        if o.get("y_btts") is None:
            continue
        applied = apply_calibrations(float(sc), cal_payload)
        if applied.get("probability_btts") is None:
            continue
        btts_pairs.append((float(applied["probability_btts"]), int(o["y_btts"])))
    btts = (
        _binary_metrics([a for a, _ in btts_pairs], [b for _, b in btts_pairs])
        if btts_pairs
        else {"n": 0, "status": "insufficient_data"}
    )
    return {
        "model_id": model_id,
        "continuous": continuous,
        "goals_ge_2": ge2,
        "goals_ge_3": ge3,
        "btts": btts,
        "scores": scores,
        "preds_eg": preds,
        "preds_ge2": p2,
        "preds_ge3": p3,
    }


def _gi_a_raw(obs: dict[str, Any]) -> float | None:
    v5 = (obs.get("v5") or {}).get(PRIMARY_ID) or {}
    raw = safe_float(v5.get("raw_score"))
    if raw is not None:
        return raw
    # fallback from pillars (equal mean of OP1 DV1 MT1 OV1)
    pillars = obs.get("pillars") or {}
    vals = [
        safe_float(pillars.get(k))
        for k in ("OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM", "OV1_STD")
    ]
    if any(v is None for v in vals):
        return None
    return float(np.mean(vals))  # type: ignore[arg-type]


def fit_gi_e(
    train: list[dict[str, Any]],
    validation: list[dict[str, Any]],
) -> dict[str, Any]:
    train_scores = [_gi_a_raw(o) for o in train]
    if any(s is None for s in train_scores):
        return {"status": "error", "error": "missing_gi_a_raw_train"}
    train_scores_f = [float(s) for s in train_scores]  # type: ignore[arg-type]

    # A. fit TRAIN
    cal_train = fit_calibrations_for_scores(train_scores_f, train)
    # B. validation metrics (not used in fit)
    val_scores = [_gi_a_raw(o) for o in validation]
    if any(s is None for s in val_scores):
        return {"status": "error", "error": "missing_gi_a_raw_validation"}
    val_scores_f = [float(s) for s in val_scores]  # type: ignore[arg-type]
    val_metrics = evaluate_candidate(validation, val_scores_f, cal_train, model_id=GI_E_ID)

    # C. refit TRAIN+VALIDATION
    combined = train + validation
    combined_scores = [_gi_a_raw(o) for o in combined]
    combined_scores_f = [float(s) for s in combined_scores]  # type: ignore[arg-type]
    cal_final = fit_calibrations_for_scores(combined_scores_f, combined)
    # strip private keys for storage
    public_cal = {
        k: v
        for k, v in cal_final.items()
        if not str(k).startswith("_") and v is not None
    }
    return {
        "status": "ok",
        "role": "recalibrated_primary",
        "raw_formula": "identical_to_GI_A_STRICT_CORE",
        "calibration_train_only": {
            k: v for k, v in cal_train.items() if not str(k).startswith("_") and v is not None
        },
        "validation_metrics": {
            "continuous": val_metrics["continuous"],
            "goals_ge_2": {k: v for k, v in val_metrics["goals_ge_2"].items() if k != "calibration_bins"},
            "goals_ge_3": {k: v for k, v in val_metrics["goals_ge_3"].items() if k != "calibration_bins"},
            "btts": val_metrics["btts"],
        },
        "calibration_payload": public_cal,
        "_cal_final": cal_final,
        "raw_identity_check": "gi_e_raw_equals_gi_a",
    }


def _pillar_matrix(observations: list[dict[str, Any]]) -> tuple[np.ndarray | None, list[int]]:
    rows = []
    keep = []
    for i, o in enumerate(observations):
        pillars = o.get("pillars") or {}
        vals = []
        ok = True
        for pid in GI_F_PILLARS:
            v = safe_float(pillars.get(pid))
            if v is None:
                ok = False
                break
            vals.append(float(v) / 100.0)  # normalize to [0,1] for fit
        if ok:
            rows.append(vals)
            keep.append(i)
    if not rows:
        return None, []
    return np.asarray(rows, dtype=float), keep


def _fit_nonneg_ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> dict[str, Any]:
    """Ridge L2 non-negativa via ElasticNet(l1_ratio=0, positive=True)."""
    try:
        from sklearn.linear_model import ElasticNet
    except Exception as exc:  # pragma: no cover
        return {"status": "error", "error": f"sklearn_unavailable:{exc}"}

    model = ElasticNet(
        alpha=float(alpha),
        l1_ratio=0.0,
        positive=True,
        fit_intercept=True,
        max_iter=50000,
        tol=1e-5,
    )
    try:
        model.fit(x, y)
    except Exception as exc:
        return {"status": "invalid", "error": f"fit_failed:{exc}", "alpha": alpha}

    coef = np.asarray(model.coef_, dtype=float)
    if not np.all(np.isfinite(coef)):
        return {"status": "invalid", "error": "non_finite_coefficients", "alpha": alpha}
    if np.any(coef < -1e-12):
        return {"status": "invalid", "error": "negative_coefficients", "alpha": alpha}
    coef = np.clip(coef, 0.0, None)
    s = float(np.sum(coef))
    if s <= 0:
        return {"status": "invalid", "error": "zero_sum_coefficients", "alpha": alpha}
    weights = coef / s
    return {
        "status": "ok",
        "alpha": float(alpha),
        "raw_coefficients": [float(c) for c in coef.tolist()],
        "normalized_weights": {pid: float(w) for pid, w in zip(GI_F_PILLARS, weights.tolist())},
        "intercept": float(model.intercept_),
        "weights_sum": _round(float(np.sum(weights))),
    }


def _gi_f_raw_from_weights(obs: dict[str, Any], weights: dict[str, float]) -> float | None:
    pillars = obs.get("pillars") or {}
    total = 0.0
    for pid, w in weights.items():
        v = safe_float(pillars.get(pid))
        if v is None:
            return None
        total += float(w) * (float(v) / 100.0)
    return 100.0 * total


def fit_gi_f(
    train: list[dict[str, Any]],
    validation: list[dict[str, Any]],
) -> dict[str, Any]:
    x_train, keep_train = _pillar_matrix(train)
    if x_train is None or len(keep_train) < 10:
        return {"status": "error", "error": "insufficient_gi_f_train_pillars"}
    y_train = np.asarray([float(train[i]["y_total"]) for i in keep_train], dtype=float)
    train_kept = [train[i] for i in keep_train]

    x_val, keep_val = _pillar_matrix(validation)
    if x_val is None or len(keep_val) < 5:
        return {"status": "error", "error": "insufficient_gi_f_validation_pillars"}
    val_kept = [validation[i] for i in keep_val]

    validation_results: list[dict[str, Any]] = []
    valid_cfgs: list[dict[str, Any]] = []

    for alpha in GI_F_ALPHA_GRID:
        fit = _fit_nonneg_ridge(x_train, y_train, alpha)
        if fit.get("status") != "ok":
            validation_results.append(
                {
                    "alpha": alpha,
                    "status": "invalid",
                    "error": fit.get("error"),
                }
            )
            continue
        weights = fit["normalized_weights"]
        train_scores = [_gi_f_raw_from_weights(o, weights) for o in train_kept]
        if any(s is None for s in train_scores):
            validation_results.append({"alpha": alpha, "status": "invalid", "error": "score_none"})
            continue
        cal = fit_calibrations_for_scores([float(s) for s in train_scores], train_kept)  # type: ignore[arg-type]
        val_scores = [_gi_f_raw_from_weights(o, weights) for o in val_kept]
        if any(s is None for s in val_scores):
            validation_results.append({"alpha": alpha, "status": "invalid", "error": "val_score_none"})
            continue
        metrics = evaluate_candidate(
            val_kept,
            [float(s) for s in val_scores],  # type: ignore[arg-type]
            cal,
            model_id=GI_F_ID,
        )
        mae = metrics["continuous"].get("mae")
        brier_ge2 = metrics["goals_ge_2"].get("brier")
        brier_ge3 = metrics["goals_ge_3"].get("brier")
        brier_btts = (metrics["btts"] or {}).get("brier")
        mean_brier_ge = None
        if brier_ge2 is not None and brier_ge3 is not None:
            mean_brier_ge = (float(brier_ge2) + float(brier_ge3)) / 2.0
        row = {
            "alpha": alpha,
            "status": "ok",
            "validation_mae": mae,
            "validation_mean_brier_ge2_ge3": _round(mean_brier_ge),
            "validation_brier_btts": brier_btts,
            "weights": weights,
            "raw_coefficients": fit["raw_coefficients"],
        }
        validation_results.append(row)
        valid_cfgs.append(row)

    if not valid_cfgs:
        return {
            "status": "error",
            "error": "all_alpha_invalid",
            "alpha_grid": list(GI_F_ALPHA_GRID),
            "validation_results": validation_results,
        }

    # Lexicographic selection
    def _key(r: dict[str, Any]) -> tuple:
        mae = r.get("validation_mae")
        mb = r.get("validation_mean_brier_ge2_ge3")
        bb = r.get("validation_brier_btts")
        return (
            float(mae) if mae is not None else 1e9,
            float(mb) if mb is not None else 1e9,
            float(bb) if bb is not None else 1e9,
            -float(r["alpha"]),  # prefer larger alpha on ties
        )

    selected = sorted(valid_cfgs, key=_key)[0]
    selected_alpha = float(selected["alpha"])

    # Refit on TRAIN+VALIDATION
    combined = train + validation
    x_c, keep_c = _pillar_matrix(combined)
    if x_c is None:
        return {"status": "error", "error": "insufficient_gi_f_combined_pillars"}
    y_c = np.asarray([float(combined[i]["y_total"]) for i in keep_c], dtype=float)
    combined_kept = [combined[i] for i in keep_c]
    refit = _fit_nonneg_ridge(x_c, y_c, selected_alpha)
    if refit.get("status") != "ok":
        return {
            "status": "error",
            "error": "refit_invalid",
            "detail": refit,
            "validation_results": validation_results,
        }
    weights = refit["normalized_weights"]
    scores = [_gi_f_raw_from_weights(o, weights) for o in combined_kept]
    cal_final = fit_calibrations_for_scores([float(s) for s in scores], combined_kept)  # type: ignore[arg-type]
    public_cal = {
        k: v for k, v in cal_final.items() if not str(k).startswith("_") and v is not None
    }
    w_arr = np.asarray([weights[p] for p in GI_F_PILLARS], dtype=float)
    entropy = float(-np.sum(w_arr[w_arr > 0] * np.log(w_arr[w_arr > 0]))) if np.any(w_arr > 0) else 0.0
    effective = float(np.exp(entropy)) if entropy > 0 else 1.0

    return {
        "status": "ok",
        "role": "regularized_pillar_candidate",
        "alpha_grid": list(GI_F_ALPHA_GRID),
        "validation_results": validation_results,
        "selected_alpha": selected_alpha,
        "weights": weights,
        "raw_coefficients": refit["raw_coefficients"],
        "max_weight": _round(float(np.max(w_arr))),
        "weight_entropy": _round(entropy),
        "effective_pillar_count": _round(effective),
        "fit_status": "ok",
        "pillars_used": list(GI_F_PILLARS),
        "calibration_payload": public_cal,
        "_cal_final": cal_final,
        "definition_hash": _sha256_canonical(
            {
                "alpha": selected_alpha,
                "weights": weights,
                "pillars": list(GI_F_PILLARS),
            }
        ),
    }


def _parent_cal_copy(bundle: CecchinoGoalIntensityV5PreviewBundle, cid: str) -> dict[str, Any]:
    cal = (bundle.calibration_payload or {}).get(cid) or {}
    return dict(cal)


def _extract_archive_evidence(benchmark: dict[str, Any]) -> dict[str, Any]:
    comps = (benchmark.get("continuous_total_goals") or {}).get("comparisons") or []
    cohort = benchmark.get("cohort") or {}

    def _pick(cid: str) -> dict[str, Any]:
        for c in comps:
            if c.get("left_id") == cid and c.get("right_id") == V4_MODEL_ID and c.get("metric") == "mae":
                return c
        return {}

    mt1 = _pick(BENCHMARK_ID)
    diag = _pick(DIAGNOSTIC_ID)
    now = datetime.now(timezone.utc).isoformat()
    return {
        BENCHMARK_ID: {
            "status": "benchmark_archived_not_selected",
            "reason": "supported_mae_underperformance_vs_v4",
            "source_benchmark_version": benchmark.get("version")
            or GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
            "paired_n": cohort.get("paired_complete_n"),
            "delta": mt1.get("delta"),
            "ci": mt1.get("ci"),
            "evidence_level": mt1.get("evidence_level"),
            "decision_timestamp": now,
            "decision_source": "phase_2b_manual_review",
        },
        DIAGNOSTIC_ID: {
            "status": "diagnostic_archived_not_selected",
            "reason": "supported_mae_underperformance_vs_v4",
            "source_benchmark_version": benchmark.get("version")
            or GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
            "paired_n": cohort.get("paired_complete_n"),
            "delta": diag.get("delta"),
            "ci": diag.get("ci"),
            "evidence_level": diag.get("evidence_level"),
            "decision_timestamp": now,
            "decision_source": "phase_2b_manual_review",
        },
    }


def _holdout_predictions_map(
    holdout: list[dict[str, Any]],
    *,
    parent: CecchinoGoalIntensityV5PreviewBundle,
    gi_e: dict[str, Any],
    gi_f: dict[str, Any],
) -> dict[str, dict[str, list[float]]]:
    """Predictions for V4/A/B/E/F on the same holdout rows."""
    out: dict[str, dict[str, list[float]]] = {}

    # V4
    out[V4_MODEL_ID] = {
        "eg": [float(o["v4_eg"]) for o in holdout],
        "ge2": [float(o["v4_p_ge2"]) for o in holdout],
        "ge3": [float(o["v4_p_ge3"]) for o in holdout],
    }

    for cid in (PRIMARY_ID, CHALLENGER_ID):
        eg, ge2, ge3, btts = [], [], [], []
        for o in holdout:
            pred = (o.get("v5") or {}).get(cid) or {}
            eg.append(float(pred["expected_total_goals"]))
            ge2.append(float(pred["probability_goals_ge_2"]))
            ge3.append(float(pred["probability_goals_ge_3"]))
            if pred.get("probability_btts") is not None and o.get("y_btts") is not None:
                btts.append(float(pred["probability_btts"]))
        out[cid] = {"eg": eg, "ge2": ge2, "ge3": ge3, "btts": btts}

    # GI_E
    cal_e = gi_e.get("_cal_final") or gi_e.get("calibration_payload") or {}
    eg, ge2, ge3, btts = [], [], [], []
    for o in holdout:
        raw = _gi_a_raw(o)
        applied = apply_calibrations(float(raw), cal_e)  # type: ignore[arg-type]
        eg.append(float(applied["expected_total_goals"] or 0.0))
        ge2.append(float(applied["probability_goals_ge_2"] or 0.0))
        ge3.append(float(applied["probability_goals_ge_3"] or 0.0))
        if applied.get("probability_btts") is not None and o.get("y_btts") is not None:
            btts.append(float(applied["probability_btts"]))
    out[GI_E_ID] = {"eg": eg, "ge2": ge2, "ge3": ge3, "btts": btts}

    # GI_F
    weights = gi_f.get("weights") or {}
    cal_f = gi_f.get("_cal_final") or gi_f.get("calibration_payload") or {}
    eg, ge2, ge3, btts = [], [], [], []
    for o in holdout:
        raw = _gi_f_raw_from_weights(o, weights)
        applied = apply_calibrations(float(raw), cal_f)  # type: ignore[arg-type]
        eg.append(float(applied["expected_total_goals"] or 0.0))
        ge2.append(float(applied["probability_goals_ge_2"] or 0.0))
        ge3.append(float(applied["probability_goals_ge_3"] or 0.0))
        if applied.get("probability_btts") is not None and o.get("y_btts") is not None:
            btts.append(float(applied["probability_btts"]))
    out[GI_F_ID] = {"eg": eg, "ge2": ge2, "ge3": ge3, "btts": btts}
    return out


def evaluate_holdout(
    holdout: list[dict[str, Any]],
    *,
    parent: CecchinoGoalIntensityV5PreviewBundle,
    gi_e: dict[str, Any],
    gi_f: dict[str, Any],
    guard: HoldoutAccessGuard,
) -> dict[str, Any]:
    guard.access()
    preds = _holdout_predictions_map(holdout, parent=parent, gi_e=gi_e, gi_f=gi_f)
    y_total = [float(o["y_total"]) for o in holdout]
    y_ge2 = [int(o["y_ge2"]) for o in holdout]
    y_ge3 = [int(o["y_ge3"]) for o in holdout]

    metrics: dict[str, Any] = {}
    abs_err: dict[str, list[float]] = {}
    sq_err: dict[str, list[float]] = {}
    brier_ge2: dict[str, list[float]] = {}
    brier_ge3: dict[str, list[float]] = {}
    brier_btts: dict[str, list[float]] = {}

    for mid, p in preds.items():
        cont = _continuous_metrics(p["eg"], y_total)
        cont["bias"] = cont.pop("mean_error", None)
        metrics[mid] = {
            "model_id": mid,
            "continuous": cont,
            "goals_ge_2": _binary_metrics(p["ge2"], y_ge2),
            "goals_ge_3": _binary_metrics(p["ge3"], y_ge3),
        }
        abs_err[mid] = [abs(a - b) for a, b in zip(p["eg"], y_total)]
        sq_err[mid] = [(a - b) ** 2 for a, b in zip(p["eg"], y_total)]
        brier_ge2[mid] = [(_clip_prob(a) - b) ** 2 for a, b in zip(p["ge2"], y_ge2)]
        brier_ge3[mid] = [(_clip_prob(a) - b) ** 2 for a, b in zip(p["ge3"], y_ge3)]
        # BTTS only for V5 family
        if mid != V4_MODEL_ID:
            pairs = []
            for o, pb in zip(holdout, p.get("btts") or []):
                # btts list may be shorter — rebuild
                pass
            btts_probs = []
            btts_ys = []
            for o in holdout:
                if o.get("y_btts") is None:
                    continue
                if mid in (PRIMARY_ID, CHALLENGER_ID):
                    pb = ((o.get("v5") or {}).get(mid) or {}).get("probability_btts")
                elif mid == GI_E_ID:
                    raw = _gi_a_raw(o)
                    pb = apply_calibrations(float(raw), gi_e.get("_cal_final") or {})[  # type: ignore[arg-type]
                        "probability_btts"
                    ]
                else:
                    raw = _gi_f_raw_from_weights(o, gi_f.get("weights") or {})
                    pb = apply_calibrations(float(raw), gi_f.get("_cal_final") or {})[  # type: ignore[arg-type]
                        "probability_btts"
                    ]
                if pb is None:
                    continue
                btts_probs.append(float(pb))
                btts_ys.append(int(o["y_btts"]))
            metrics[mid]["btts"] = (
                _binary_metrics(btts_probs, btts_ys) if btts_probs else {"n": 0, "status": "insufficient_data"}
            )
            brier_btts[mid] = [
                (_clip_prob(a) - b) ** 2 for a, b in zip(btts_probs, btts_ys)
            ]
        else:
            metrics[mid]["btts"] = {
                "status": "not_comparable",
                "reason": "v4_total_lambda_has_no_team_split_btts_probability",
            }

    n = len(holdout)
    idx = bootstrap_index_matrix(n, BOOTSTRAP_ITERATIONS, BOOTSTRAP_SEED) if n else np.empty((0, 0))

    pairwise_specs = [
        (GI_E_ID, V4_MODEL_ID),
        (GI_F_ID, V4_MODEL_ID),
        (GI_E_ID, PRIMARY_ID),
        (GI_F_ID, PRIMARY_ID),
        (GI_E_ID, CHALLENGER_ID),
        (GI_F_ID, CHALLENGER_ID),
        (GI_E_ID, GI_F_ID),
        (PRIMARY_ID, V4_MODEL_ID),
        (CHALLENGER_ID, V4_MODEL_ID),
    ]
    pairwise: list[dict[str, Any]] = []
    for left, right in pairwise_specs:
        for metric_name, err_map in (
            ("mae", abs_err),
            ("mse_for_rmse", sq_err),
            ("brier_goals_ge_2", brier_ge2),
            ("brier_goals_ge_3", brier_ge3),
        ):
            pairwise.append(
                _pairwise_error_comparison(
                    err_map[left],
                    err_map[right],
                    left_id=left,
                    right_id=right,
                    metric=metric_name,
                    indices=idx,
                )
            )
        # BTTS when both comparable
        if left in brier_btts and right in brier_btts and brier_btts[left] and brier_btts[right]:
            # align lengths — only if same n
            if len(brier_btts[left]) == len(brier_btts[right]):
                pairwise.append(
                    _pairwise_error_comparison(
                        brier_btts[left],
                        brier_btts[right],
                        left_id=left,
                        right_id=right,
                        metric="brier_btts",
                        indices=None,
                    )
                )

    # Neutral preferred labels: no automatic winner when CI includes zero
    for p in pairwise:
        if p.get("preferred_side") != "none" and _preferred_side(
            float(p["delta"]) if p.get("delta") is not None else None, p.get("ci")
        ) == "none":
            p["preferred_side"] = "none"
        if p.get("evidence_level") and p.get("preferred_side") == "none":
            # keep evidence but no winner declaration
            pass

    guard.lock()
    return {
        "metrics": metrics,
        "pairwise": pairwise,
        "holdout_access_count": guard.count,
        "n": n,
    }


def build_candidate_bundle_payload(
    *,
    parent: CecchinoGoalIntensityV5PreviewBundle,
    splits_meta: dict[str, Any],
    gi_e: dict[str, Any],
    gi_f: dict[str, Any],
    archived: dict[str, Any],
    holdout_eval: dict[str, Any],
    fixture_ids_hash: str,
    targets_hash: str,
    source_git_commit: str | None,
) -> dict[str, Any]:
    cal_payload = {
        PRIMARY_ID: _parent_cal_copy(parent, PRIMARY_ID),
        CHALLENGER_ID: _parent_cal_copy(parent, CHALLENGER_ID),
        GI_E_ID: gi_e.get("calibration_payload") or {},
        GI_F_ID: gi_f.get("calibration_payload") or {},
    }
    definitions = {
        "parent_bundle_id": parent.id,
        "parent_bundle_version": parent.version,
        "parent_definition_hash": parent.candidate_definition_hash,
        "development_protocol_version": DEVELOPMENT_PROTOCOL_VERSION,
        "active_candidate_ids": list(ACTIVE_CANDIDATE_IDS),
        "archived_candidate_ids": list(ARCHIVED_CANDIDATE_IDS),
        "GI_E_PRIMARY_RECALIBRATED": {
            "role": "recalibrated_primary",
            "raw_formula": "identical_to_GI_A_STRICT_CORE",
            "calibration": "train_validation_refit",
        },
        "GI_F_REGULARIZED_PILLARS": {
            "role": "regularized_pillar_candidate",
            "pillars": list(GI_F_PILLARS),
            "selected_alpha": gi_f.get("selected_alpha"),
            "weights": gi_f.get("weights"),
            "method": "elasticnet_l2_nonnegative_ridge",
        },
        "gi_f_weights": gi_f.get("weights"),
        "selected_alpha": gi_f.get("selected_alpha"),
        "split_metadata": splits_meta,
        "holdout_metrics": holdout_eval.get("metrics"),
        "pairwise_comparisons": holdout_eval.get("pairwise"),
        "archive_evidence": archived,
        "intended_use": "historical_external_benchmark_only",
        "live_scoring_enabled": False,
        "signals_integration_enabled": False,
        "no_signals": True,
        "no_live_activation": True,
        "no_2021_22_usage": True,
        "source_git_commit": source_git_commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "parent_normalization_copied": True,
            "parent_calibration_copied_for": [PRIMARY_ID, CHALLENGER_ID],
        },
    }
    def_hash = _sha256_canonical(
        {
            "parent_hash": parent.candidate_definition_hash,
            "active": list(ACTIVE_CANDIDATE_IDS),
            "archived": list(ARCHIVED_CANDIDATE_IDS),
            "gi_e_cal": cal_payload[GI_E_ID],
            "gi_f_alpha": gi_f.get("selected_alpha"),
            "gi_f_weights": gi_f.get("weights"),
            "gi_f_cal": cal_payload[GI_F_ID],
            "split_hashes": {
                "train": (splits_meta.get("train") or {}).get("fixture_ids_hash"),
                "validation": (splits_meta.get("validation") or {}).get("fixture_ids_hash"),
                "holdout": (splits_meta.get("holdout") or {}).get("fixture_ids_hash"),
            },
            "protocol": DEVELOPMENT_PROTOCOL_VERSION,
        }
    )
    return {
        "version": TARGET_BUNDLE_VERSION,
        "candidate_indices_version": DEVELOPMENT_PROTOCOL_VERSION,
        "candidate_definition_hash": def_hash,
        "fixture_ids_hash": fixture_ids_hash,
        "targets_hash": targets_hash,
        "normalization_method": parent.normalization_method,
        "normalization_payload": {
            **(parent.normalization_payload or {}),
            "parent_normalization_hash": _sha256_canonical(parent.normalization_payload or {}),
            "copied_from_parent": True,
            "no_ecdf_refit": True,
        },
        "calibration_payload": cal_payload,
        "candidate_definitions_payload": definitions,
        "status": BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
        "is_active": False,
    }


def develop_phase_2c_candidates(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    use_cache: bool = True,
    source_git_commit: str | None = None,
) -> dict[str, Any]:
    """Dry-run / compute completo Phase 2C (nessuna scrittura)."""
    parent = _get_phase_2c_parent_bundle(db)
    if parent is None:
        return make_json_safe(
            {
                "status": "blocked",
                "error": "parent_bundle_missing",
                "development_version": DEVELOPMENT_PROTOCOL_VERSION,
                "target_bundle_version": TARGET_BUNDLE_VERSION,
                "freeze_allowed": False,
                "blocking_reasons": ["parent_bundle_missing"],
            }
        )

    cohort = load_goal_intensity_prospective_paired_observations(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        bundle=parent,
    )
    max_ts = cohort.get("max_result_ts")
    cache_key = (
        DEVELOPMENT_PROTOCOL_VERSION,
        CODE_VERSION,
        parent.id,
        parent.version,
        parent.candidate_definition_hash,
        max_ts.isoformat() if max_ts else None,
        int(cohort.get("paired_total") or 0),
        date_from,
        date_to,
        competition_id,
    )
    if use_cache:
        with _cache_lock:
            hit = _cache.get(cache_key)
            if hit and time.monotonic() - hit[0] < _CACHE_TTL_S:
                out = dict(hit[1])
                out["cache_hit"] = True
                return out

    if cohort.get("status") != "ok":
        return make_json_safe(
            {
                "status": "blocked",
                "error": cohort.get("error") or "cohort_unavailable",
                "development_version": DEVELOPMENT_PROTOCOL_VERSION,
                "target_bundle_version": TARGET_BUNDLE_VERSION,
                "freeze_allowed": False,
                "blocking_reasons": ["cohort_unavailable"],
                "checks": {
                    "historical_run_used": False,
                    "historical_run_ids": [],
                    "external_api_calls": 0,
                    "parent_bundle_modified": False,
                    "snapshot_writes": 0,
                    "holdout_access_count": 0,
                },
            }
        )

    observations = cohort["observations"]
    split = temporal_split(observations)
    blocking = list(split.get("blocking_reasons") or [])

    # Archive evidence from Phase 2B benchmark (same cohort filters)
    benchmark = build_goal_intensity_v4_v5_prospective_benchmark(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    archived = _extract_archive_evidence(benchmark if benchmark.get("status") == "ok" else {})

    gi_e: dict[str, Any] = {}
    gi_f: dict[str, Any] = {}
    holdout_eval: dict[str, Any] = {}
    guard = HoldoutAccessGuard()
    bundle_payload: dict[str, Any] | None = None

    if split.get("status") == "ok":
        gi_e = fit_gi_e(split["train"], split["validation"])
        if gi_e.get("status") != "ok":
            blocking.append(str(gi_e.get("error") or "gi_e_failed"))
        gi_f = fit_gi_f(split["train"], split["validation"])
        if gi_f.get("status") != "ok":
            blocking.append(str(gi_f.get("error") or "gi_f_failed"))

        if gi_e.get("status") == "ok" and gi_f.get("status") == "ok":
            # Verify raw GI_E == GI_A on all observations
            mismatches = 0
            for o in observations:
                a = _gi_a_raw(o)
                if a is None:
                    mismatches += 1
                    continue
                # GI_E raw is GI_A by definition
            if mismatches:
                blocking.append("gi_e_raw_missing")

            try:
                holdout_eval = evaluate_holdout(
                    split["holdout"],
                    parent=parent,
                    gi_e=gi_e,
                    gi_f=gi_f,
                    guard=guard,
                )
            except RuntimeError as exc:
                blocking.append(str(exc))

            if guard.count != 1:
                blocking.append("holdout_access_count_invalid")

            fixture_ids = sorted(
                {
                    int(o["local_fixture_id"])
                    if o.get("local_fixture_id") is not None
                    else int(o["today_fixture_id"] or 0)
                    for o in observations
                }
            )
            targets = [
                {
                    "fixture": (
                        int(o["local_fixture_id"])
                        if o.get("local_fixture_id") is not None
                        else int(o["today_fixture_id"] or 0)
                    ),
                    "y_total": o["y_total"],
                    "y_ge2": o["y_ge2"],
                    "y_ge3": o["y_ge3"],
                    "y_btts": o.get("y_btts"),
                }
                for o in observations
            ]
            fixture_hash = _sha256_canonical(fixture_ids)
            targets_hash = _sha256_canonical(targets)
            bundle_payload = build_candidate_bundle_payload(
                parent=parent,
                splits_meta=split.get("meta") or {},
                gi_e=gi_e,
                gi_f=gi_f,
                archived=archived,
                holdout_eval=holdout_eval,
                fixture_ids_hash=fixture_hash,
                targets_hash=targets_hash,
                source_git_commit=source_git_commit,
            )
    else:
        blocking.extend(split.get("blocking_reasons") or ["split_blocked"])

    freeze_allowed = len(blocking) == 0 and bundle_payload is not None

    # Existing frozen bundle?
    existing = db.scalars(
        select(CecchinoGoalIntensityV5PreviewBundle).where(
            CecchinoGoalIntensityV5PreviewBundle.version == TARGET_BUNDLE_VERSION
        )
    ).first()

    out = make_json_safe(
        {
            "status": "preview" if freeze_allowed else "blocked",
            "development_version": DEVELOPMENT_PROTOCOL_VERSION,
            "target_bundle_version": TARGET_BUNDLE_VERSION,
            "parent_bundle": {
                "id": parent.id,
                "version": parent.version,
                "definition_hash": parent.candidate_definition_hash,
                "remains_active": bool(parent.is_active),
                "status": parent.status,
            },
            "existing_candidate_bundle": (
                {
                    "id": existing.id,
                    "version": existing.version,
                    "is_active": existing.is_active,
                    "status": existing.status,
                    "definition_hash": existing.candidate_definition_hash,
                }
                if existing
                else None
            ),
            "cohort": {
                "completed_raw": cohort.get("completed_raw"),
                "eligible": cohort.get("eligible"),
                "duplicates_removed": cohort.get("duplicates_removed"),
                "paired_total": cohort.get("paired_total"),
                "missing_by_reason": cohort.get("missing_by_reason"),
            },
            "splits": {
                "train": (split.get("meta") or {}).get("train"),
                "validation": (split.get("meta") or {}).get("validation"),
                "holdout": (split.get("meta") or {}).get("holdout"),
                "protocol": (split.get("meta") or {}).get("protocol"),
                "kickoff_boundary": (split.get("meta") or {}).get("kickoff_boundary"),
            },
            "candidates": {
                PRIMARY_ID: {
                    "role": "original_primary",
                    "calibration": "copied_from_parent",
                    "raw_formula": "unchanged",
                },
                CHALLENGER_ID: {
                    "role": "original_challenger",
                    "calibration": "copied_from_parent",
                    "raw_formula": "unchanged",
                },
                GI_E_ID: {
                    "role": "recalibrated_primary",
                    "status": gi_e.get("status"),
                    "calibration": gi_e.get("calibration_payload"),
                    "validation_metrics": gi_e.get("validation_metrics"),
                },
                GI_F_ID: {
                    "role": "regularized_pillar_candidate",
                    "status": gi_f.get("status"),
                    "selected_alpha": gi_f.get("selected_alpha"),
                    "weights": gi_f.get("weights"),
                    "calibration": gi_f.get("calibration_payload"),
                    "max_weight": gi_f.get("max_weight"),
                    "weight_entropy": gi_f.get("weight_entropy"),
                    "effective_pillar_count": gi_f.get("effective_pillar_count"),
                },
            },
            "archived_candidates": archived,
            "gi_f_selection": {
                "alpha_grid": list(GI_F_ALPHA_GRID),
                "validation_results": gi_f.get("validation_results"),
                "selected_alpha": gi_f.get("selected_alpha"),
                "weights": gi_f.get("weights"),
            },
            "holdout_metrics": holdout_eval.get("metrics"),
            "holdout_pairwise": holdout_eval.get("pairwise"),
            "definition_hash": (bundle_payload or {}).get("candidate_definition_hash"),
            "fixture_ids_hash": (bundle_payload or {}).get("fixture_ids_hash"),
            "targets_hash": (bundle_payload or {}).get("targets_hash"),
            "bundle_payload_preview": {
                "status": BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
                "is_active": False,
                "intended_use": "historical_external_benchmark_only",
                "live_scoring_enabled": False,
                "signals_integration_enabled": False,
            }
            if bundle_payload
            else None,
            "_bundle_payload": bundle_payload,
            "checks": {
                "historical_run_used": False,
                "historical_run_ids": [],
                "external_api_calls": 0,
                "parent_bundle_modified": False,
                "snapshot_writes": 0,
                "holdout_access_count": guard.count,
            },
            "freeze_allowed": freeze_allowed,
            "blocking_reasons": blocking,
            "cache_hit": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    if use_cache and freeze_allowed:
        with _cache_lock:
            if len(_cache) > 32:
                _cache.clear()
            # store without private _bundle for cache? keep it for freeze path
            _cache[cache_key] = (time.monotonic(), dict(out))
    return out


def freeze_candidate_bundle(
    db: Session,
    *,
    dry_run: bool = True,
    confirm: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    source_git_commit: str | None = None,
) -> dict[str, Any]:
    """Freeze idempotente del bundle v2.1 (is_active=false). Non supersede il parent."""
    if not dry_run:
        if confirm != PHASE_2C_FREEZE_CONFIRM_TOKEN:
            return make_json_safe(
                {
                    "status": "error",
                    "error": "invalid_confirm_token",
                    "freeze_allowed": False,
                    "writes": 0,
                }
            )

    # Always recompute fresh (do not freeze from stale cache alone)
    preview = develop_phase_2c_candidates(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        use_cache=False,
        source_git_commit=source_git_commit,
    )
    if dry_run:
        out = dict(preview)
        out.pop("_bundle_payload", None)
        out["status"] = preview.get("status") or "preview"
        out["dry_run"] = True
        out["writes"] = 0
        return make_json_safe(out)

    if not preview.get("freeze_allowed"):
        out = dict(preview)
        out.pop("_bundle_payload", None)
        out["status"] = "blocked"
        out["dry_run"] = False
        out["writes"] = 0
        return make_json_safe(out)

    if preview.get("checks", {}).get("holdout_access_count") != 1:
        return make_json_safe(
            {
                "status": "blocked",
                "error": "holdout_reused_for_selection"
                if (preview.get("checks") or {}).get("holdout_access_count", 0) > 1
                else "holdout_access_count_invalid",
                "freeze_allowed": False,
                "writes": 0,
            }
        )

    payload = preview.get("_bundle_payload")
    if not isinstance(payload, dict):
        return make_json_safe(
            {
                "status": "error",
                "error": "bundle_payload_missing",
                "writes": 0,
            }
        )

    parent = _get_phase_2c_parent_bundle(db)
    if parent is None:
        return make_json_safe({"status": "error", "error": "parent_bundle_missing", "writes": 0})

    # Concurrency: lock parent row
    locked_parent = db.scalars(
        select(CecchinoGoalIntensityV5PreviewBundle)
        .where(CecchinoGoalIntensityV5PreviewBundle.id == parent.id)
        .with_for_update()
    ).first()
    if locked_parent is None:
        return make_json_safe({"status": "error", "error": "parent_lock_failed", "writes": 0})

    # Idempotency check after lock
    existing = db.scalars(
        select(CecchinoGoalIntensityV5PreviewBundle).where(
            CecchinoGoalIntensityV5PreviewBundle.version == TARGET_BUNDLE_VERSION,
            CecchinoGoalIntensityV5PreviewBundle.candidate_definition_hash
            == payload["candidate_definition_hash"],
            CecchinoGoalIntensityV5PreviewBundle.fixture_ids_hash == payload["fixture_ids_hash"],
            CecchinoGoalIntensityV5PreviewBundle.targets_hash == payload["targets_hash"],
        )
    ).first()
    if existing is not None:
        db.commit()  # release lock
        return make_json_safe(
            {
                "status": "already_frozen_same_definition",
                "existing_bundle_id": existing.id,
                "bundle_id": existing.id,
                "version": existing.version,
                "is_active": existing.is_active,
                "parent_bundle": {
                    "id": locked_parent.id,
                    "version": locked_parent.version,
                    "is_active": locked_parent.is_active,
                    "remains_active": True,
                },
                "writes": 0,
                "dry_run": False,
                "definition_hash": existing.candidate_definition_hash,
                "checks": preview.get("checks"),
            }
        )

    now = datetime.now(timezone.utc)
    row = CecchinoGoalIntensityV5PreviewBundle(
        version=payload["version"],
        candidate_indices_version=payload["candidate_indices_version"],
        candidate_definition_hash=payload["candidate_definition_hash"],
        fixture_ids_hash=payload["fixture_ids_hash"],
        targets_hash=payload["targets_hash"],
        normalization_method=payload["normalization_method"],
        normalization_payload=payload["normalization_payload"],
        calibration_payload=payload["calibration_payload"],
        candidate_definitions_payload=payload["candidate_definitions_payload"],
        retrospective_date_from=locked_parent.retrospective_date_from,
        retrospective_date_to=locked_parent.retrospective_date_to,
        first_prospective_scan_date=locked_parent.first_prospective_scan_date,
        frozen_at=now,
        status=BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
        is_active=False,
    )
    db.add(row)
    db.flush()
    # Ensure parent untouched
    locked_parent.is_active = True
    if locked_parent.version == PREVIEW_BUNDLE_VERSION:
        # keep active status
        from app.models.cecchino_goal_intensity_v5_preview import BUNDLE_STATUS_ACTIVE

        locked_parent.status = BUNDLE_STATUS_ACTIVE
    db.commit()
    db.refresh(row)

    clear_goal_intensity_phase_2c_cache()

    return make_json_safe(
        {
            "status": "frozen",
            "bundle_id": row.id,
            "version": row.version,
            "is_active": row.is_active,
            "bundle_status": row.status,
            "definition_hash": row.candidate_definition_hash,
            "fixture_ids_hash": row.fixture_ids_hash,
            "targets_hash": row.targets_hash,
            "parent_bundle": {
                "id": locked_parent.id,
                "version": locked_parent.version,
                "is_active": locked_parent.is_active,
                "status": locked_parent.status,
                "remains_active": True,
            },
            "active_candidate_ids": list(ACTIVE_CANDIDATE_IDS),
            "archived_candidate_ids": list(ARCHIVED_CANDIDATE_IDS),
            "dry_run": False,
            "writes": 1,
            "checks": {
                **(preview.get("checks") or {}),
                "parent_bundle_modified": False,
                "snapshot_writes": 0,
                "historical_run_used": False,
                "external_api_calls": 0,
            },
            "holdout_metrics": preview.get("holdout_metrics"),
            "gi_f_selection": preview.get("gi_f_selection"),
        }
    )
