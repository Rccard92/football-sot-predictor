"""Audit diagnostico Goal Intensity v5 — dimensioni e candidati (read-only).

Fonte di verità: snapshot preview persistito collegato alla fixture.
Ricalcolo solo in memoria sul bundle esatto dello snapshot (mai refit/rebuild).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    CecchinoGoalIntensityV5PreviewBundle,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    NORMALIZATION_METHOD,
    TrainEcdf,
    WEIGHT_STATUS,
    _composite_scores,
    _loo_composites,
    _pillar_scores_from_pct,
    safe_float,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    BENCHMARK_ID,
    BUNDLE_FEATURE_KEYS,
    CHALLENGER_ID,
    DIAGNOSTIC_ID,
    PREVIEW_BUNDLE_VERSION,
    PRIMARY_ID,
    _apply_linear,
    _apply_logistic,
    _ecdfs_from_bundle,
    _ensure_utc,
    _iso_z,
    _round,
    get_active_bundle,
    score_features_with_bundle,
)

AUDIT_VERSION = "cecchino_goal_intensity_v5_explanations_v1"
MODULE = "goal_intensity_v5"
SOURCE_MODE = "persisted_goal_intensity_v5_preview_snapshot"

UI_CANDIDATE_IDS = (PRIMARY_ID, CHALLENGER_ID, BENCHMARK_ID, DIAGNOSTIC_ID)

CANDIDATE_ROLES = {
    PRIMARY_ID: "Primary",
    CHALLENGER_ID: "Challenger",
    BENCHMARK_ID: "Benchmark",
    DIAGNOSTIC_ID: "Diagnostico",
}

CANDIDATE_COMPONENT_KEYS = {
    PRIMARY_ID: ("OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM", "OV1_STD"),
    CHALLENGER_ID: ("OP2_HOME_RECENCY", "DV1_MEAN_CONCEDED", "MT2_LONG_TERM_PLUS_RECENCY", "OV1_STD"),
    BENCHMARK_ID: ("MT1_LONG_TERM",),
    DIAGNOSTIC_ID: ("OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM"),
}

COMPONENT_ROLES = {
    "OP1_HOME_LONG_TERM": "Produzione offensiva long-term",
    "OP2_HOME_RECENCY": "Produzione offensiva con recency",
    "DV1_MEAN_CONCEDED": "Vulnerabilità difensiva media",
    "DV2_WEAKEST_DEFENCE": "Vulnerabilità difensiva massima",
    "MT1_LONG_TERM": "Ritmo partita long-term",
    "MT2_LONG_TERM_PLUS_RECENCY": "Ritmo partita con recency",
    "OV1_STD": "Volatilità offensiva",
}

METRIC_USED_BY: dict[str, tuple[str, ...]] = {
    "OP1_HOME_LONG_TERM": (PRIMARY_ID, "GI_D_WEAKEST_DEFENCE", DIAGNOSTIC_ID),
    "OP2_HOME_RECENCY": (CHALLENGER_ID,),
    "DV1_MEAN_CONCEDED": (PRIMARY_ID, CHALLENGER_ID, DIAGNOSTIC_ID, "GI_C_SYMMETRIC_DIAGNOSTIC"),
    "DV2_WEAKEST_DEFENCE": ("GI_D_WEAKEST_DEFENCE",),
    "MT1_LONG_TERM": (PRIMARY_ID, BENCHMARK_ID, DIAGNOSTIC_ID),
    "MT2_LONG_TERM_PLUS_RECENCY": (CHALLENGER_ID,),
    "OV1_STD": (PRIMARY_ID, CHALLENGER_ID),
}


def _fmt_it(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}".replace(".", ",")


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _consistency(
    stored: Any,
    audit: Any,
    *,
    abs_tol: float = 1e-6,
    rounding_tol: float = 0.015,
) -> dict[str, Any]:
    if stored is None and audit is None:
        return {"status": "unavailable", "delta": None}
    if stored is None or audit is None:
        return {"status": "not_verifiable", "delta": None}
    try:
        s = float(stored)
        a = float(audit)
    except (TypeError, ValueError):
        if stored == audit:
            return {"status": "match", "delta": 0}
        return {"status": "mismatch", "delta": None}
    if not math.isfinite(s) or not math.isfinite(a):
        return {"status": "not_verifiable", "delta": None}
    delta = a - s
    if abs(delta) <= abs_tol:
        return {"status": "match", "delta": round(delta, 10)}
    if abs(delta) <= rounding_tol:
        return {"status": "rounding_match", "delta": round(delta, 10)}
    return {"status": "mismatch", "delta": round(delta, 10)}


def _stored_vs_recomputed(
    stored: Any,
    recomputed: Any,
    *,
    abs_tol: float = 1e-6,
    rounding_tol: float = 0.015,
) -> dict[str, Any]:
    """Confronto esplicito stored snapshot vs ricalcolo scorer canonico."""
    s = safe_float(stored) if stored is not None else None
    if s is None and stored is not None:
        s = stored
    r = safe_float(recomputed) if recomputed is not None else None
    if r is None and recomputed is not None:
        r = recomputed
    cons = _consistency(s, r, abs_tol=abs_tol, rounding_tol=rounding_tol)
    status = cons["status"]
    if status == "not_verifiable":
        status = "unavailable"
    return {
        "stored": s,
        "recomputed": r,
        "delta": cons.get("delta"),
        "tolerance": {"abs": abs_tol, "rounding": rounding_tol},
        "consistency_status": status,
    }


def _aggregate_consistency_status(statuses: list[str]) -> str:
    """match solo se tutti match; rounding_match se solo match/rounding; altrimenti mismatch/unavailable."""
    if not statuses:
        return "unavailable"
    if any(s == "mismatch" for s in statuses):
        return "mismatch"
    if any(s in {"unavailable", "not_verifiable"} for s in statuses):
        return "unavailable"
    if any(s == "rounding_match" for s in statuses):
        return "rounding_match"
    if all(s == "match" for s in statuses):
        return "match"
    return "unavailable"


def _present_candidates(snap: CecchinoGoalIntensityV5PreviewSnapshot) -> set[str]:
    scores = snap.candidate_scores_payload or {}
    present = {str(k) for k in scores.keys()}
    for cid, attr in (
        (PRIMARY_ID, snap.primary_candidate_score),
        (CHALLENGER_ID, snap.challenger_candidate_score),
        (BENCHMARK_ID, snap.benchmark_score),
        (DIAGNOSTIC_ID, snap.diagnostic_score),
    ):
        if attr is not None or cid in scores:
            present.add(cid)
    # Also include any calibrated keys
    for cid in (snap.calibrated_predictions_payload or {}):
        present.add(str(cid))
    return present


def _filter_used_by(metric_key: str, present: set[str]) -> list[str]:
    return [c for c in METRIC_USED_BY.get(metric_key, ()) if c in present]


def _ecdf_transform_detail(ecdf: TrainEcdf, raw: float | None) -> dict[str, Any]:
    """Audit ECDF compatto: nessuna distribuzione train completa."""
    meta_base = {
        "train_n": ecdf.n,
        "train_min": _round(ecdf.train_min),
        "train_max": _round(ecdf.train_max),
        "train_median": _round(ecdf.train_median),
        "quantiles": {k: _round(v) for k, v in (ecdf.quantiles or {}).items()},
        "distribution_hash": ecdf.distribution_hash,
        "normalization_method": NORMALIZATION_METHOD,
        "tie_handling": "midrank",
        "clipping_rules": "clamp_to_train_min_max",
        "raw_value": _round(raw) if raw is not None else None,
        "clipped_value": None,
        "clipping_applied": False,
        "lower_count": None,
        "equal_count": None,
        "midrank": None,
        "percentile_result": None,
    }
    if raw is None or ecdf.n == 0:
        return meta_base
    try:
        xf = float(raw)
    except (TypeError, ValueError):
        return meta_base
    if not np.isfinite(xf):
        return meta_base
    clipped = False
    if ecdf.train_min is not None and xf < ecdf.train_min:
        xf = float(ecdf.train_min)
        clipped = True
    if ecdf.train_max is not None and xf > ecdf.train_max:
        xf = float(ecdf.train_max)
        clipped = True
    lower = int(np.searchsorted(ecdf.values, xf, side="left"))
    equal = int(np.searchsorted(ecdf.values, xf, side="right") - lower)
    midrank = lower + 0.5 * equal
    percentile = 100.0 * midrank / ecdf.n
    percentile = float(min(100.0, max(0.0, percentile)))
    meta_base.update(
        {
            "clipped_value": _round(xf),
            "clipping_applied": clipped,
            "lower_count": lower,
            "equal_count": equal,
            "midrank": _round(midrank),
            "percentile_result": _round(percentile),
        }
    )
    return meta_base


def _feature_ecdf_audit(
    ecdfs: dict[str, TrainEcdf],
    features: dict[str, Any],
    feature_key: str,
    bundle: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    ecdf = ecdfs.get(feature_key)
    raw = safe_float(features.get(feature_key))
    if ecdf is None:
        stored_meta = ((bundle.normalization_payload or {}).get("features") or {}).get(feature_key) or {}
        return {
            "feature_key": feature_key,
            "train_n": stored_meta.get("train_n"),
            "train_min": stored_meta.get("train_min"),
            "train_max": stored_meta.get("train_max"),
            "train_median": stored_meta.get("train_median"),
            "quantiles": stored_meta.get("quantiles") or {},
            "distribution_hash": stored_meta.get("distribution_hash"),
            "normalization_method": stored_meta.get("normalization_method") or NORMALIZATION_METHOD,
            "tie_handling": stored_meta.get("tie_handling") or "midrank",
            "clipping_rules": stored_meta.get("clipping_rules") or "clamp_to_train_min_max",
            "raw_value": _round(raw) if raw is not None else None,
            "clipped_value": None,
            "clipping_applied": False,
            "lower_count": None,
            "equal_count": None,
            "midrank": None,
            "percentile_result": None,
            "status": "unavailable",
        }
    detail = _ecdf_transform_detail(ecdf, raw)
    detail["feature_key"] = feature_key
    detail["status"] = "available" if detail.get("percentile_result") is not None else "unavailable"
    return detail


def _mean_formula_steps(values: list[tuple[str, float | None]], result: float | None) -> list[str]:
    present = [(k, v) for k, v in values if v is not None]
    if not present:
        return ["nessun componente disponibile"]
    parts = " + ".join(_fmt_it(v) for _, v in present)
    total = sum(v for _, v in present)
    n = len(present)
    steps = [
        f"({parts}) / {n}",
        f"{_fmt_it(total)} / {n}",
        _fmt_it(result) if result is not None else "—",
    ]
    return steps


def _build_metric(
    *,
    metric_key: str,
    label: str,
    formula_symbolic: str,
    formula_applied: list[str],
    raw_features: list[dict[str, Any]],
    normalization: dict[str, Any] | list[dict[str, Any]] | None,
    stored_result: float | None,
    audit_result: float | None,
    used_by: list[str],
    description: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    cons = _consistency(stored_result, audit_result)
    return {
        "metric_key": metric_key,
        "label": label,
        "description": description,
        "formula_symbolic": formula_symbolic,
        "formula_applied": formula_applied,
        "raw_features": raw_features,
        "normalization": normalization or {},
        "stored_result": _round(stored_result) if stored_result is not None else None,
        "audit_result": _round(audit_result) if audit_result is not None else None,
        "consistency": cons,
        "used_by_candidates": used_by,
        "warnings": warnings or [],
    }


def _build_dimensions(
    *,
    features: dict[str, Any],
    stored_pillars: dict[str, Any],
    audit_pillars: dict[str, Any],
    ecdfs: dict[str, TrainEcdf],
    bundle: CecchinoGoalIntensityV5PreviewBundle,
    present: set[str],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    consistency_statuses: list[str] = []

    def feat_audit(key: str) -> dict[str, Any]:
        return _feature_ecdf_audit(ecdfs, features, key, bundle)

    # --- OP1 / OP2 ---
    home_lt = feat_audit("home_goals_scored_avg")
    home_r5 = feat_audit("home_goals_scored_rolling_5")
    op1_audit = audit_pillars.get("OP1_HOME_LONG_TERM")
    op1_stored = safe_float(stored_pillars.get("OP1_HOME_LONG_TERM"))
    op1_steps = [
        f"lower={home_lt.get('lower_count')}, equal={home_lt.get('equal_count')}, train_n={home_lt.get('train_n')}",
        (
            f"100 × ({home_lt.get('lower_count')} + 0,5 × {home_lt.get('equal_count')}) "
            f"/ {home_lt.get('train_n')} = {_fmt_it(op1_audit)}"
            if home_lt.get("train_n")
            else "ECDF non disponibile"
        ),
    ]
    op2_audit = audit_pillars.get("OP2_HOME_RECENCY")
    op2_stored = safe_float(stored_pillars.get("OP2_HOME_RECENCY"))
    p_lt = home_lt.get("percentile_result")
    p_r5 = home_r5.get("percentile_result")
    op2_steps = _mean_formula_steps(
        [("pct_long_term", safe_float(p_lt)), ("pct_rolling_5", safe_float(p_r5))],
        safe_float(op2_audit),
    )

    op1_m = _build_metric(
        metric_key="OP1_HOME_LONG_TERM",
        label="OP1 long-term",
        formula_symbolic="ECDF(home_goals_scored_avg)",
        formula_applied=op1_steps,
        raw_features=[
            {
                "key": "home_goals_scored_avg",
                "label": "Media gol segnati casa (long-term)",
                "value": home_lt.get("raw_value"),
                "source_path": "snapshot.feature_payload.home_goals_scored_avg",
            }
        ],
        normalization=home_lt,
        stored_result=op1_stored,
        audit_result=safe_float(op1_audit),
        used_by=_filter_used_by("OP1_HOME_LONG_TERM", present),
        description="Percentile ECDF train-only della media gol segnati dalla squadra di casa.",
    )
    consistency_statuses.append(op1_m["consistency"]["status"])

    op2_m = _build_metric(
        metric_key="OP2_HOME_RECENCY",
        label="OP2 con recency",
        formula_symbolic="mean(ECDF(home_goals_scored_avg), ECDF(home_goals_scored_rolling_5))",
        formula_applied=op2_steps,
        raw_features=[
            {
                "key": "home_goals_scored_avg",
                "label": "Media gol casa long-term",
                "value": home_lt.get("raw_value"),
                "source_path": "snapshot.feature_payload.home_goals_scored_avg",
            },
            {
                "key": "home_goals_scored_rolling_5",
                "label": "Media gol casa ultime 5",
                "value": home_r5.get("raw_value"),
                "source_path": "snapshot.feature_payload.home_goals_scored_rolling_5",
            },
        ],
        normalization={"home_goals_scored_avg": home_lt, "home_goals_scored_rolling_5": home_r5},
        stored_result=op2_stored,
        audit_result=safe_float(op2_audit),
        used_by=_filter_used_by("OP2_HOME_RECENCY", present),
        description="Media dei percentili long-term e rolling-5 della produzione offensiva casa.",
    )
    consistency_statuses.append(op2_m["consistency"]["status"])

    dim_op = {
        "dimension_key": "offensive_production",
        "dimension_number": 1,
        "title": "Produzione offensiva",
        "status": "available" if op1_audit is not None or op2_audit is not None else "unavailable",
        "description": (
            "Misura la capacità offensiva della squadra di casa, in versione long-term (OP1) "
            "e con componente di recency (OP2)."
        ),
        "purpose": "Alimentare i candidati Primary/Diagnostico (OP1) e Challenger (OP2).",
        "direction": "Valori alti indicano maggiore produzione offensiva relativa alla coorte train.",
        "metrics": [op1_m, op2_m],
        "display_transformations": [],
        "reason_summary": (
            f"OP1={_fmt_it(op1_stored)} (long-term); OP2={_fmt_it(op2_stored)} (con recency)."
        ),
        "data_origin": {
            "feature_payload_keys": ["home_goals_scored_avg", "home_goals_scored_rolling_5"],
            "bundle_id": bundle.id,
            "source_path": "snapshot.feature_payload + bundle.normalization_payload",
            "distribution_hashes": {
                "home_goals_scored_avg": home_lt.get("distribution_hash"),
                "home_goals_scored_rolling_5": home_r5.get("distribution_hash"),
            },
        },
        "warnings": [],
    }

    # --- DV1 / display / DV2 ---
    home_c = feat_audit("home_goals_conceded_avg")
    away_c = feat_audit("away_goals_conceded_avg")
    dv1_audit = audit_pillars.get("DV1_MEAN_CONCEDED")
    dv1_stored = safe_float(stored_pillars.get("DV1_MEAN_CONCEDED"))
    dv1_steps = _mean_formula_steps(
        [
            ("pct_home_conceded", safe_float(home_c.get("percentile_result"))),
            ("pct_away_conceded", safe_float(away_c.get("percentile_result"))),
        ],
        safe_float(dv1_audit),
    )
    solidity_audit = audit_pillars.get("defensive_solidity_display")
    if solidity_audit is None and dv1_audit is not None:
        solidity_audit = _round(100.0 - float(dv1_audit))
    solidity_stored = safe_float(stored_pillars.get("defensive_solidity_display"))
    if solidity_stored is None and dv1_stored is not None:
        solidity_stored = _round(100.0 - float(dv1_stored))

    display_msg = (
        "Il candidato Goal Intensity utilizza la vulnerabilità DV1. "
        "La “Solidità” mostrata nella card è la rappresentazione inversa, "
        "usata esclusivamente per rendere la lettura più intuitiva."
    )
    dv1_m = _build_metric(
        metric_key="DV1_MEAN_CONCEDED",
        label="DV1 vulnerabilità media",
        formula_symbolic="mean(ECDF(home_goals_conceded_avg), ECDF(away_goals_conceded_avg))",
        formula_applied=dv1_steps,
        raw_features=[
            {
                "key": "home_goals_conceded_avg",
                "label": "Gol subiti casa (media)",
                "value": home_c.get("raw_value"),
                "source_path": "snapshot.feature_payload.home_goals_conceded_avg",
            },
            {
                "key": "away_goals_conceded_avg",
                "label": "Gol subiti trasferta (media)",
                "value": away_c.get("raw_value"),
                "source_path": "snapshot.feature_payload.away_goals_conceded_avg",
            },
        ],
        normalization={"home_goals_conceded_avg": home_c, "away_goals_conceded_avg": away_c},
        stored_result=dv1_stored,
        audit_result=safe_float(dv1_audit),
        used_by=_filter_used_by("DV1_MEAN_CONCEDED", present),
        description=(
            "Vulnerabilità difensiva media. Alto DV1 = maggiore vulnerabilità = "
            "maggiore contributo allo score di intensità."
        ),
        warnings=[display_msg],
    )
    consistency_statuses.append(dv1_m["consistency"]["status"])

    solidity_m = _build_metric(
        metric_key="defensive_solidity_display",
        label="Solidità visualizzata",
        formula_symbolic="100 − DV1_MEAN_CONCEDED",
        formula_applied=[
            f"100 − {_fmt_it(dv1_audit if dv1_audit is not None else dv1_stored)}",
            _fmt_it(solidity_audit if solidity_audit is not None else solidity_stored),
        ],
        raw_features=[],
        normalization={},
        stored_result=solidity_stored,
        audit_result=safe_float(solidity_audit),
        used_by=[],
        description="Trasformazione di sola visualizzazione: non entra nei candidati.",
        warnings=[display_msg],
    )
    consistency_statuses.append(solidity_m["consistency"]["status"])

    metrics_def = [dv1_m, solidity_m]
    display_transforms = [
        {
            "key": "defensive_solidity_display",
            "formula_symbolic": "100 − DV1_MEAN_CONCEDED",
            "mathematical_value_key": "DV1_MEAN_CONCEDED",
            "mathematical_value": _round(dv1_stored) if dv1_stored is not None else None,
            "display_value": _round(solidity_stored) if solidity_stored is not None else None,
            "message": display_msg,
            "used_by_candidates": False,
        }
    ]

    dv2_stored = safe_float(stored_pillars.get("DV2_WEAKEST_DEFENCE"))
    dv2_audit = audit_pillars.get("DV2_WEAKEST_DEFENCE")
    if dv2_stored is not None or dv2_audit is not None or "GI_D_WEAKEST_DEFENCE" in present:
        p_h = safe_float(home_c.get("percentile_result"))
        p_a = safe_float(away_c.get("percentile_result"))
        dv2_steps = [
            f"max({_fmt_it(p_h)}, {_fmt_it(p_a)})",
            _fmt_it(dv2_audit),
        ]
        dv2_m = _build_metric(
            metric_key="DV2_WEAKEST_DEFENCE",
            label="DV2 difesa più debole",
            formula_symbolic="max(ECDF(home_goals_conceded_avg), ECDF(away_goals_conceded_avg))",
            formula_applied=dv2_steps,
            raw_features=[],
            normalization={"home_goals_conceded_avg": home_c, "away_goals_conceded_avg": away_c},
            stored_result=dv2_stored,
            audit_result=safe_float(dv2_audit),
            used_by=_filter_used_by("DV2_WEAKEST_DEFENCE", present),
            description="Massima vulnerabilità tra le due squadre (percentile).",
        )
        metrics_def.append(dv2_m)
        consistency_statuses.append(dv2_m["consistency"]["status"])

    dim_dv = {
        "dimension_key": "defensive_solidity",
        "dimension_number": 2,
        "title": "Solidità difensiva",
        "status": "available" if dv1_audit is not None else "unavailable",
        "description": (
            "La card mostra la solidità visualizzata (100−DV1), ma i candidati usano "
            "la vulnerabilità DV1."
        ),
        "purpose": "Quantificare quanto le difese concedono, in chiave di intensità gol.",
        "direction": "DV1 alto = più vulnerabilità = più contributo allo score intensità.",
        "metrics": metrics_def,
        "display_transformations": display_transforms,
        "mandatory_message": display_msg,
        "reason_summary": (
            f"DV1 (vulnerabilità)={_fmt_it(dv1_stored)}; "
            f"solidità visualizzata={_fmt_it(solidity_stored)}."
        ),
        "data_origin": {
            "feature_payload_keys": ["home_goals_conceded_avg", "away_goals_conceded_avg"],
            "bundle_id": bundle.id,
            "source_path": "snapshot.feature_payload + bundle.normalization_payload",
            "distribution_hashes": {
                "home_goals_conceded_avg": home_c.get("distribution_hash"),
                "away_goals_conceded_avg": away_c.get("distribution_hash"),
            },
        },
        "warnings": [display_msg],
    }

    # --- MT1 / MT2 ---
    tot_lt = feat_audit("total_goals_avg")
    tot_r5 = feat_audit("total_goals_rolling_5")
    mt1_audit = audit_pillars.get("MT1_LONG_TERM")
    mt1_stored = safe_float(stored_pillars.get("MT1_LONG_TERM"))
    mt1_steps = [
        f"lower={tot_lt.get('lower_count')}, equal={tot_lt.get('equal_count')}, train_n={tot_lt.get('train_n')}",
        (
            f"100 × ({tot_lt.get('lower_count')} + 0,5 × {tot_lt.get('equal_count')}) "
            f"/ {tot_lt.get('train_n')} = {_fmt_it(mt1_audit)}"
            if tot_lt.get("train_n")
            else "ECDF non disponibile"
        ),
    ]
    mt2_audit = audit_pillars.get("MT2_LONG_TERM_PLUS_RECENCY")
    mt2_stored = safe_float(stored_pillars.get("MT2_LONG_TERM_PLUS_RECENCY"))
    mt2_steps = _mean_formula_steps(
        [
            ("pct_total_lt", safe_float(tot_lt.get("percentile_result"))),
            ("pct_total_r5", safe_float(tot_r5.get("percentile_result"))),
        ],
        safe_float(mt2_audit),
    )
    mt1_m = _build_metric(
        metric_key="MT1_LONG_TERM",
        label="MT1 long-term",
        formula_symbolic="ECDF(total_goals_avg)",
        formula_applied=mt1_steps,
        raw_features=[
            {
                "key": "total_goals_avg",
                "label": "Media gol totali long-term",
                "value": tot_lt.get("raw_value"),
                "source_path": "snapshot.feature_payload.total_goals_avg",
            }
        ],
        normalization=tot_lt,
        stored_result=mt1_stored,
        audit_result=safe_float(mt1_audit),
        used_by=_filter_used_by("MT1_LONG_TERM", present),
        description="Percentile del ritmo storico della partita; è anche il Benchmark in tabella.",
    )
    consistency_statuses.append(mt1_m["consistency"]["status"])
    mt2_m = _build_metric(
        metric_key="MT2_LONG_TERM_PLUS_RECENCY",
        label="MT2 long-term + recency",
        formula_symbolic="mean(ECDF(total_goals_avg), ECDF(total_goals_rolling_5))",
        formula_applied=mt2_steps,
        raw_features=[
            {
                "key": "total_goals_avg",
                "label": "Media gol totali long-term",
                "value": tot_lt.get("raw_value"),
                "source_path": "snapshot.feature_payload.total_goals_avg",
            },
            {
                "key": "total_goals_rolling_5",
                "label": "Media gol totali ultime 5",
                "value": tot_r5.get("raw_value"),
                "source_path": "snapshot.feature_payload.total_goals_rolling_5",
            },
        ],
        normalization={"total_goals_avg": tot_lt, "total_goals_rolling_5": tot_r5},
        stored_result=mt2_stored,
        audit_result=safe_float(mt2_audit),
        used_by=_filter_used_by("MT2_LONG_TERM_PLUS_RECENCY", present),
        description="Ritmo partita che include la recency; alimenta il Challenger.",
    )
    consistency_statuses.append(mt2_m["consistency"]["status"])

    dim_mt = {
        "dimension_key": "match_tempo",
        "dimension_number": 3,
        "title": "Ritmo partita",
        "status": "available" if mt1_audit is not None or mt2_audit is not None else "unavailable",
        "description": "Misura il ritmo gol atteso della partita (long-term e con recency).",
        "purpose": "MT1 alimenta Primary, Benchmark e Diagnostico; MT2 alimenta Challenger.",
        "direction": "Valori alti indicano un ritmo gol storicamente più elevato.",
        "metrics": [mt1_m, mt2_m],
        "display_transformations": [],
        "reason_summary": f"MT1={_fmt_it(mt1_stored)}; MT2={_fmt_it(mt2_stored)}.",
        "data_origin": {
            "feature_payload_keys": ["total_goals_avg", "total_goals_rolling_5"],
            "bundle_id": bundle.id,
            "source_path": "snapshot.feature_payload + bundle.normalization_payload",
            "distribution_hashes": {
                "total_goals_avg": tot_lt.get("distribution_hash"),
                "total_goals_rolling_5": tot_r5.get("distribution_hash"),
            },
        },
        "warnings": [],
    }

    # --- OV1 / stability ---
    std_f = feat_audit("goals_scored_std_last_10")
    ov1_audit = audit_pillars.get("OV1_STD")
    ov1_stored = safe_float(stored_pillars.get("OV1_STD"))
    ov1_steps = [
        f"lower={std_f.get('lower_count')}, equal={std_f.get('equal_count')}, train_n={std_f.get('train_n')}",
        (
            f"100 × ({std_f.get('lower_count')} + 0,5 × {std_f.get('equal_count')}) "
            f"/ {std_f.get('train_n')} = {_fmt_it(ov1_audit)}"
            if std_f.get("train_n")
            else "ECDF non disponibile"
        ),
    ]
    stab_audit = audit_pillars.get("offensive_stability_display")
    if stab_audit is None and ov1_audit is not None:
        stab_audit = _round(100.0 - float(ov1_audit))
    stab_stored = safe_float(stored_pillars.get("offensive_stability_display"))
    if stab_stored is None and ov1_stored is not None:
        stab_stored = _round(100.0 - float(ov1_stored))

    stab_msg = (
        "Il candidato Goal Intensity utilizza la volatilità OV1. "
        "La “Stabilità” visualizzata è il valore inverso e serve soltanto "
        "a rendere il dato più intuitivo."
    )
    ov1_m = _build_metric(
        metric_key="OV1_STD",
        label="OV1 volatilità",
        formula_symbolic="ECDF(goals_scored_std_last_10)",
        formula_applied=ov1_steps,
        raw_features=[
            {
                "key": "goals_scored_std_last_10",
                "label": "Deviazione standard gol segnati (ultime 10)",
                "value": std_f.get("raw_value"),
                "source_path": "snapshot.feature_payload.goals_scored_std_last_10",
            }
        ],
        normalization=std_f,
        stored_result=ov1_stored,
        audit_result=safe_float(ov1_audit),
        used_by=_filter_used_by("OV1_STD", present),
        description="Volatilità offensiva: alto OV1 = maggiore instabilità della produzione gol.",
        warnings=[stab_msg],
    )
    consistency_statuses.append(ov1_m["consistency"]["status"])
    stab_m = _build_metric(
        metric_key="offensive_stability_display",
        label="Stabilità visualizzata",
        formula_symbolic="100 − OV1_STD",
        formula_applied=[
            f"100 − {_fmt_it(ov1_audit if ov1_audit is not None else ov1_stored)}",
            _fmt_it(stab_audit if stab_audit is not None else stab_stored),
        ],
        raw_features=[],
        normalization={},
        stored_result=stab_stored,
        audit_result=safe_float(stab_audit),
        used_by=[],
        description="Trasformazione di sola visualizzazione: non è un componente del Primary.",
        warnings=[stab_msg],
    )
    consistency_statuses.append(stab_m["consistency"]["status"])

    dim_ov = {
        "dimension_key": "offensive_stability",
        "dimension_number": 4,
        "title": "Stabilità offensiva",
        "status": "available" if ov1_audit is not None else "unavailable",
        "description": (
            "La card mostra la stabilità visualizzata (100−OV1), ma i candidati usano "
            "la volatilità OV1."
        ),
        "purpose": "Quantificare la volatilità della produzione offensiva nel compositi Primary/Challenger.",
        "direction": "OV1 alto = più volatilità = più contributo allo score intensità.",
        "metrics": [ov1_m, stab_m],
        "display_transformations": [
            {
                "key": "offensive_stability_display",
                "formula_symbolic": "100 − OV1_STD",
                "mathematical_value_key": "OV1_STD",
                "mathematical_value": _round(ov1_stored) if ov1_stored is not None else None,
                "display_value": _round(stab_stored) if stab_stored is not None else None,
                "message": stab_msg,
                "used_by_candidates": False,
            }
        ],
        "mandatory_message": stab_msg,
        "reason_summary": (
            f"OV1 (volatilità)={_fmt_it(ov1_stored)}; "
            f"stabilità visualizzata={_fmt_it(stab_stored)}."
        ),
        "data_origin": {
            "feature_payload_keys": ["goals_scored_std_last_10"],
            "bundle_id": bundle.id,
            "source_path": "snapshot.feature_payload + bundle.normalization_payload",
            "distribution_hashes": {
                "goals_scored_std_last_10": std_f.get("distribution_hash"),
            },
        },
        "warnings": [stab_msg],
    }

    dimensions = {
        "offensive_production": dim_op,
        "defensive_solidity": dim_dv,
        "match_tempo": dim_mt,
        "offensive_stability": dim_ov,
    }
    for dim in dimensions.values():
        for m in dim.get("metrics") or []:
            if m.get("consistency", {}).get("status") == "mismatch":
                warnings.append(f"Mismatch su metrica {m.get('metric_key')}")
            if m.get("status") == "unavailable" or m.get("audit_result") is None:
                if m.get("metric_key") not in (
                    "defensive_solidity_display",
                    "offensive_stability_display",
                    "DV2_WEAKEST_DEFENCE",
                ):
                    pass
    return dimensions, consistency_statuses


def _stored_candidate_score(snap: CecchinoGoalIntensityV5PreviewSnapshot, cid: str) -> float | None:
    scores = snap.candidate_scores_payload or {}
    if cid in scores and scores[cid] is not None:
        return safe_float(scores[cid])
    if cid == PRIMARY_ID:
        return safe_float(snap.primary_candidate_score)
    if cid == CHALLENGER_ID:
        return safe_float(snap.challenger_candidate_score)
    if cid == BENCHMARK_ID:
        return safe_float(snap.benchmark_score)
    if cid == DIAGNOSTIC_ID:
        return safe_float(snap.diagnostic_score)
    return None


def _explain_linear_calibration(
    *,
    score: float | None,
    cal: dict[str, Any] | None,
    stored: float | None,
) -> dict[str, Any]:
    cal = cal or {}
    intercept = safe_float(cal.get("intercept"))
    coef = safe_float(cal.get("coefficient"))
    audit = _apply_linear(cal, score) if score is not None else None
    product = None
    if coef is not None and score is not None:
        product = coef * float(score)
    steps: list[str] = []
    if intercept is not None and coef is not None and score is not None:
        steps = [
            f"{_fmt_it(intercept)} + {_fmt_it(coef)} × {_fmt_it(score)}",
            f"{_fmt_it(intercept)} + {_fmt_it(product)}",
            _fmt_it(audit),
        ]
    return {
        "target": "expected_total_goals",
        "calibration_method": cal.get("calibration_method") or "train_linear_regression",
        "formula_symbolic": "intercept + coefficient × candidate_score",
        "formula_applied": steps,
        "score": _round(score) if score is not None else None,
        "intercept": intercept,
        "coefficient": coef,
        "product": _round(product) if product is not None else None,
        "raw_result": audit,
        "stored_result": _round(stored) if stored is not None else None,
        "audit_result": audit,
        "consistency": _consistency(stored, audit),
        "train_n": cal.get("train_n"),
        "rounding": "bundle_preview_round",
    }


def _explain_logistic_calibration(
    *,
    score: float | None,
    cal: dict[str, Any] | None,
    stored: float | None,
    target: str,
) -> dict[str, Any]:
    cal = cal or {}
    intercept = safe_float(cal.get("intercept"))
    coef = safe_float(cal.get("coefficient"))
    audit = _apply_logistic(cal, score) if score is not None else None
    z = None
    if intercept is not None and coef is not None and score is not None:
        z = intercept + coef * float(score)
    steps: list[str] = []
    if z is not None:
        steps = [
            f"z = {_fmt_it(intercept)} + {_fmt_it(coef)} × {_fmt_it(score)} = {_fmt_it(z)}",
            f"P = 1 / (1 + exp(−z)) = {_fmt_it(audit, 6)}",
            f"percentuale ≈ {_fmt_it((audit or 0) * 100, 1)}%",
        ]
    return {
        "target": target,
        "calibration_method": cal.get("calibration_method") or "train_logistic_regression",
        "formula_symbolic": "sigmoid(intercept + coefficient × candidate_score)",
        "formula_applied": steps,
        "score": _round(score) if score is not None else None,
        "intercept": intercept,
        "coefficient": coef,
        "z": _round(z) if z is not None else None,
        "raw_probability": audit,
        "probability_percent": _round((audit or 0) * 100) if audit is not None else None,
        "stored_result": _round(stored) if stored is not None else None,
        "audit_result": audit,
        "consistency": _consistency(stored, audit, rounding_tol=0.0005),
        "train_n": cal.get("train_n"),
        "train_positive_rate": cal.get("train_positive_rate"),
    }


def _candidate_reason(cid: str, components: list[dict[str, Any]], primary_score: float | None, score: float | None) -> str:
    if cid == PRIMARY_ID:
        return (
            "Primary: baseline composito strict core a pesi uguali su produzione, "
            "vulnerabilità, ritmo e volatilità. Preview monitorata, non formula produttiva."
        )
    if cid == CHALLENGER_ID:
        return (
            "Il Challenger sostituisce produzione e ritmo long-term "
            "con le rispettive versioni che includono la recency."
        )
    if cid == BENCHMARK_ID:
        return (
            "Questo candidato usa soltanto il ritmo storico della partita "
            "e costituisce un riferimento semplice rispetto ai compositi."
        )
    if cid == DIAGNOSTIC_ID:
        delta = None
        if primary_score is not None and score is not None:
            delta = primary_score - score
        base = (
            "Questo candidato misura come cambia lo score Primary "
            "quando viene rimossa la componente di volatilità."
        )
        if delta is not None:
            return f"{base} Delta Primary − Diagnostico = {_fmt_it(delta)}."
        return base
    return "Candidato research aggiuntivo presente nello snapshot."


def _build_candidate(
    *,
    cid: str,
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    audit_pillars: dict[str, Any],
    audit_scores: dict[str, Any],
    bundle: CecchinoGoalIntensityV5PreviewBundle,
    primary_stored: float | None,
) -> dict[str, Any]:
    role = CANDIDATE_ROLES.get(cid, "Research")
    keys = CANDIDATE_COMPONENT_KEYS.get(cid, ())
    components: list[dict[str, Any]] = []
    for k in keys:
        val = safe_float(audit_pillars.get(k))
        components.append(
            {
                "key": k,
                "label": COMPONENT_ROLES.get(k, k),
                "role": COMPONENT_ROLES.get(k, k),
                "value": _round(val) if val is not None else None,
                "contribution": _round(val) if val is not None else None,
                "weight": 1.0 / len(keys) if keys else None,
            }
        )

    if cid == BENCHMARK_ID:
        formula_symbolic = "MT1_LONG_TERM"
        audit_score = safe_float(audit_scores.get(cid) or audit_pillars.get("MT1_LONG_TERM"))
        formula_applied = [_fmt_it(audit_score)]
        excluded = ["OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "OV1_STD", "OP2_HOME_RECENCY", "MT2_LONG_TERM_PLUS_RECENCY"]
    elif cid == DIAGNOSTIC_ID:
        formula_symbolic = "mean(OP1, DV1, MT1)"
        audit_score = safe_float(audit_scores.get(cid))
        formula_applied = _mean_formula_steps(
            [(c["key"], c["value"]) for c in components],
            audit_score,
        )
        excluded = ["OV1_STD"]
    elif cid == CHALLENGER_ID:
        formula_symbolic = "mean(OP2, DV1, MT2, OV1)"
        audit_score = safe_float(audit_scores.get(cid))
        formula_applied = _mean_formula_steps(
            [(c["key"], c["value"]) for c in components],
            audit_score,
        )
        excluded = ["OP1_HOME_LONG_TERM", "MT1_LONG_TERM"]
    else:
        formula_symbolic = "mean(OP1, DV1, MT1, OV1)"
        audit_score = safe_float(audit_scores.get(cid))
        formula_applied = _mean_formula_steps(
            [(c["key"], c["value"]) for c in components],
            audit_score,
        )
        excluded = []

    stored_score = _stored_candidate_score(snap, cid)
    cons = _consistency(stored_score, audit_score)

    stored_cal = (snap.calibrated_predictions_payload or {}).get(cid) or {}
    # Coefficienti esclusivamente dal bundle dello snapshot
    bundle_cal = (bundle.calibration_payload or {}).get(cid) or {}

    cal_block = {
        "expected_total_goals": _explain_linear_calibration(
            score=stored_score if stored_score is not None else audit_score,
            cal=bundle_cal.get("total_goals_ft"),
            stored=safe_float(stored_cal.get("expected_total_goals")),
        ),
        "probability_goals_ge_2": _explain_logistic_calibration(
            score=stored_score if stored_score is not None else audit_score,
            cal=bundle_cal.get("goals_ge_2"),
            stored=safe_float(stored_cal.get("probability_goals_ge_2")),
            target="probability_goals_ge_2",
        ),
        "probability_goals_ge_3": _explain_logistic_calibration(
            score=stored_score if stored_score is not None else audit_score,
            cal=bundle_cal.get("goals_ge_3"),
            stored=safe_float(stored_cal.get("probability_goals_ge_3")),
            target="probability_goals_ge_3",
        ),
        "probability_btts": _explain_logistic_calibration(
            score=stored_score if stored_score is not None else audit_score,
            cal=bundle_cal.get("btts_ft"),
            stored=safe_float(stored_cal.get("probability_btts")),
            target="probability_btts",
        ),
    }

    status = "available" if stored_score is not None or audit_score is not None else "unavailable"
    diff_vs_primary = None
    if cid != PRIMARY_ID and primary_stored is not None and stored_score is not None:
        diff_vs_primary = _round(stored_score - primary_stored)

    return {
        "candidate_id": cid,
        "role": role,
        "status": status,
        "description": {
            PRIMARY_ID: "Baseline composito strict core a pesi uguali (research preview).",
            CHALLENGER_ID: "Variante con produzione e ritmo che includono la recency.",
            BENCHMARK_ID: "Riferimento semplice: solo ritmo long-term (MT1).",
            DIAGNOSTIC_ID: "Primary senza componente di volatilità OV1.",
        }.get(cid, "Candidato research."),
        "purpose": {
            PRIMARY_ID: "Primary — baseline composito strict core",
            CHALLENGER_ID: "Challenger — confronto con recency",
            BENCHMARK_ID: "Benchmark — riferimento ritmo storico",
            DIAGNOSTIC_ID: "Diagnostico — impatto della volatilità",
        }.get(cid, "Research"),
        "research_status": {
            "preview_monitored": True,
            "not_linked_to_signals": True,
            "no_productive_formula": True,
            "labels": [
                "Preview monitorata",
                "Non collegato ai Segnali",
                "Nessuna formula produttiva",
            ],
        },
        "formula_symbolic": formula_symbolic,
        "formula_applied": formula_applied,
        "components": components,
        "excluded_components": excluded,
        "weight_status": WEIGHT_STATUS,
        "stored_score": _round(stored_score) if stored_score is not None else None,
        "audit_score": _round(audit_score) if audit_score is not None else None,
        "consistency": cons,
        "difference_vs_primary": diff_vs_primary,
        "calibrated_predictions": cal_block,
        "reason_summary": _candidate_reason(cid, components, primary_stored, stored_score),
        "quality": {
            "bundle_id": bundle.id,
            "bundle_version": bundle.version,
            "candidate_indices_version": bundle.candidate_indices_version,
            "candidate_definition_hash": bundle.candidate_definition_hash,
            "bundle_frozen_at": _iso_z(_ensure_utc(bundle.frozen_at)),
            "source_snapshot_at": _iso_z(_ensure_utc(snap.source_snapshot_at)),
            "snapshot_status": snap.snapshot_status,
            "diagnostic_reason_codes": snap.diagnostic_reason_codes,
            "calibration_from_bundle_id": bundle.id,
        },
        "warnings": [],
    }


def _build_additional_candidates(
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    audit_pillars: dict[str, Any],
    present: set[str],
) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    composites = _composite_scores(audit_pillars)
    for cid in ("GI_C_SYMMETRIC_DIAGNOSTIC", "GI_D_WEAKEST_DEFENCE"):
        if cid not in present and safe_float((snap.candidate_scores_payload or {}).get(cid)) is None:
            continue
        stored = safe_float((snap.candidate_scores_payload or {}).get(cid))
        audit = safe_float(composites.get(cid))
        extra[cid] = {
            "candidate_id": cid,
            "role": "Research aggiuntivo",
            "status": "available" if stored is not None or audit is not None else "unavailable",
            "stored_score": _round(stored) if stored is not None else None,
            "audit_score": _round(audit) if audit is not None else None,
            "consistency": _consistency(stored, audit),
            "note": "Presente nello snapshot; non mostrato come riga cliccabile nella UI principale.",
        }
    return extra


def build_goal_intensity_v5_explanations(
    row: CecchinoTodayFixture,
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    bundle: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
        is_official_bundle,
    )

    if is_official_bundle(bundle):
        return _build_official_support_explanations(row, snap, bundle)
    return _build_legacy_preview_explanations(row, snap, bundle)


def _build_official_support_explanations(
    row: CecchinoTodayFixture,
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    bundle: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    """Audit operativo: unica fonte = score_official_support_with_bundle. Nessun candidato archiviato."""
    from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
        OFFICIAL_AUDIT_VERSION,
        OFFICIAL_MODULE_VERSION,
        OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS,
        OPERATIONAL_CALIBRATION_KEY,
        RAW_INDEX_ID,
        ROLE,
        SIGNALS_INTEGRATION_STATUS,
        TARGET_CALIBRATION_MAPPING,
        score_official_support_with_bundle,
    )

    warnings: list[str] = []
    features = dict(snap.feature_payload or {})
    for k in OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS:
        features.setdefault(k, None)
    missing = [k for k in OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS if safe_float(features.get(k)) is None]
    if missing:
        warnings.append(f"Feature mancanti: {', '.join(missing)}")

    # UNICA fonte di verità operativa: scorer ufficiale canonico
    audit = score_official_support_with_bundle(features, bundle)
    audit_scores = audit.get("candidate_scores") or {}
    audit_pillars = audit.get("pillar_scores") or {}
    raw_recomputed = safe_float(audit_scores.get(RAW_INDEX_ID))
    if raw_recomputed is None:
        raw_recomputed = safe_float(audit.get("primary_candidate_score"))

    stored_op = (snap.calibrated_predictions_payload or {}).get(OPERATIONAL_CALIBRATION_KEY) or {}
    audit_op = (audit.get("calibrated_predictions") or {}).get(OPERATIONAL_CALIBRATION_KEY) or {}

    raw_stored = safe_float(stored_op.get("raw_score"))
    if raw_stored is None:
        raw_stored = safe_float((snap.candidate_scores_payload or {}).get(RAW_INDEX_ID))
    if raw_stored is None:
        raw_stored = safe_float(snap.primary_candidate_score)

    raw_cmp = _stored_vs_recomputed(raw_stored, raw_recomputed)

    cal_root = bundle.calibration_payload or {}
    op_cal = cal_root.get(OPERATIONAL_CALIBRATION_KEY) or {}

    head_defs = [
        ("expected_total_goals", "total_goals_ft", "linear", "Stima totale gol"),
        ("probability_goals_ge_2", "goals_ge_2", "logistic", "Over 1.5"),
        ("probability_goals_ge_3", "goals_ge_3", "logistic", "Over 2.5"),
        ("probability_btts", "btts_ft", "logistic", "Gol (BTTS)"),
    ]
    target_heads: dict[str, Any] = {}
    head_statuses: list[str] = []
    for out_key, target, transform, label in head_defs:
        cal = op_cal.get(target) or {}
        intercept = safe_float(cal.get("intercept"))
        coef = safe_float(cal.get("coefficient"))
        stored_v = safe_float(stored_op.get(out_key))
        recomputed_v = safe_float(audit_op.get(out_key))
        cmp = _stored_vs_recomputed(stored_v, recomputed_v)
        head_statuses.append(cmp["consistency_status"])
        target_heads[out_key] = {
            "label_it": label,
            "target": target,
            "raw_score": raw_recomputed,
            "raw_index_id": RAW_INDEX_ID,
            "intercept": intercept,
            "coefficient": coef,
            "transform": transform,
            "result_stored": stored_v,
            "result_audit": recomputed_v,
            "stored": cmp["stored"],
            "recomputed": cmp["recomputed"],
            "delta": cmp["delta"],
            "tolerance": cmp["tolerance"],
            "consistency_status": cmp["consistency_status"],
            "calibration_source": TARGET_CALIBRATION_MAPPING.get(target),
            "bundle_version": bundle.version,
            "consistency": {
                "status": cmp["consistency_status"],
                "stored_vs_audit": cmp["consistency_status"] in {"match", "rounding_match"},
                "delta": cmp["delta"],
            },
        }

    all_statuses = [raw_cmp["consistency_status"], *head_statuses]
    consistency_status = _aggregate_consistency_status(all_statuses)
    if consistency_status == "mismatch":
        warnings.append(
            "Mismatch stored vs audit: valori persistiti e ricalcolo scorer divergono. "
            "Nessuna correzione automatica dello snapshot."
        )
    elif consistency_status == "unavailable":
        warnings.append("Consistency non verificabile per uno o più valori (stored o recomputed assenti).")

    audit_status = "ok"
    if missing or consistency_status in {"mismatch", "unavailable"}:
        audit_status = "partial"

    defs = bundle.candidate_definitions_payload or {}
    freeze_at = _ensure_utc(bundle.frozen_at)
    source_at = _ensure_utc(snap.source_snapshot_at)
    definition_hash = snap.candidate_definition_hash or bundle.candidate_definition_hash

    source_identity = {
        "today_fixture_id": int(row.id),
        "snapshot_id": snap.id,
        "bundle_id": snap.bundle_id,
        "bundle_version": bundle.version,
        "candidate_definition_hash": definition_hash,
    }

    return _json_safe(
        {
            "status": audit_status,
            "consistency_status": consistency_status,
            "audit_version": OFFICIAL_AUDIT_VERSION,
            "module": MODULE,
            "module_version": OFFICIAL_MODULE_VERSION,
            "presentation": "official_support",
            "role": ROLE,
            "signals_integration_status": SIGNALS_INTEGRATION_STATUS,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "no_operational_recalculation": True,
            "diagnostic_re_evaluation_only": True,
            "source_mode": "persisted_goal_intensity_v5_official_snapshot",
            "source_identity": source_identity,
            "fixture": {
                "today_fixture_id": int(row.id),
                "home_team": row.home_team_name,
                "away_team": row.away_team_name,
                "kickoff": _iso_z(_ensure_utc(row.kickoff)) if row.kickoff else None,
            },
            "snapshot": {
                "snapshot_id": snap.id,
                "bundle_id": snap.bundle_id,
                "bundle_version": bundle.version,
                "candidate_definition_hash": definition_hash,
                "source_snapshot_at": _iso_z(source_at),
                "bundle_frozen_at": _iso_z(freeze_at),
                "feature_status": snap.feature_status,
            },
            "index": {
                "id": RAW_INDEX_ID,
                "score_stored": raw_stored,
                "score_audit": raw_recomputed,
                "stored": raw_cmp["stored"],
                "recomputed": raw_cmp["recomputed"],
                "delta": raw_cmp["delta"],
                "tolerance": raw_cmp["tolerance"],
                "consistency_status": raw_cmp["consistency_status"],
                "formula": "mean(OP1, DV1, MT1, OV1)",
                "components": {
                    "OP1_HOME_LONG_TERM": safe_float(audit_pillars.get("OP1_HOME_LONG_TERM")),
                    "DV1_MEAN_CONCEDED": safe_float(audit_pillars.get("DV1_MEAN_CONCEDED")),
                    "MT1_LONG_TERM": safe_float(audit_pillars.get("MT1_LONG_TERM")),
                    "OV1_STD": safe_float(audit_pillars.get("OV1_STD")),
                },
                "features_raw": {k: features.get(k) for k in OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS},
                "consistency": {
                    "status": raw_cmp["consistency_status"],
                    "delta": raw_cmp["delta"],
                },
            },
            "target_heads": target_heads,
            "benchmark_provenance": {
                "benchmark_job_id": defs.get("benchmark_job_id"),
                "source_candidate_bundle_version": defs.get("source_candidate_bundle_version"),
                "scientific_evidence": (defs.get("provenance") or {}).get("scientific_evidence"),
            },
            "candidates": None,
            "archived_candidates_hidden": True,
            "warnings": warnings,
            "metadata": {
                "weight_status": WEIGHT_STATUS,
                "normalization_method": NORMALIZATION_METHOD,
                "bundle_id_used_for_audit": bundle.id,
                "active_bundle_not_used_for_coefficients": True,
                "canonical_scorer": "score_official_support_with_bundle",
                "no_parallel_raw_recompute": True,
                "no_blending": True,
                "no_refit": True,
            },
        }
    )


def _build_legacy_preview_explanations(
    row: CecchinoTodayFixture,
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    bundle: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    warnings: list[str] = []
    features = dict(snap.feature_payload or {})
    # Solo feature del bundle; nessun extract esterno
    for k in BUNDLE_FEATURE_KEYS:
        features.setdefault(k, None)

    missing_features = [k for k in BUNDLE_FEATURE_KEYS if safe_float(features.get(k)) is None]
    if missing_features:
        warnings.append(f"Feature mancanti nello snapshot: {', '.join(missing_features)}")

    # Audit diagnostico in-memory sul bundle esatto dello snapshot
    audit = score_features_with_bundle(features, bundle)
    audit_pillars = audit.get("pillar_scores") or {}
    # score_features arrotonda; ricalcola pillar grezzi per formule dettagliate
    ecdfs = _ecdfs_from_bundle(bundle)
    pct = {k: ecdf.transform(safe_float(features.get(k))) for k, ecdf in ecdfs.items()}
    full_pillars = _pillar_scores_from_pct(pct)
    # Preferisci full_pillars (con DV2/display) per audit metriche
    for k, v in full_pillars.items():
        if k not in audit_pillars or audit_pillars.get(k) is None:
            audit_pillars[k] = _round(v) if v is not None else None
        else:
            # keep rounded from score_features for consistency with stored rounding
            pass
    # Merge display / DV2 from full
    for k in (
        "DV2_WEAKEST_DEFENCE",
        "defensive_solidity_display",
        "offensive_stability_display",
        "OP3_SYMMETRIC_LONG_TERM_DIAGNOSTIC",
        "OP4_SYMMETRIC_RECENCY_DIAGNOSTIC",
    ):
        if full_pillars.get(k) is not None:
            audit_pillars[k] = _round(full_pillars[k])

    composite = _composite_scores(full_pillars)
    loo = _loo_composites(full_pillars)
    audit_scores = {
        PRIMARY_ID: _round(composite.get(PRIMARY_ID)),
        CHALLENGER_ID: _round(composite.get(CHALLENGER_ID)),
        BENCHMARK_ID: _round(full_pillars.get(BENCHMARK_ID)),
        DIAGNOSTIC_ID: _round(loo.get("without_volatility")),
    }

    stored_pillars = dict(snap.pillar_scores_payload or {})
    present = _present_candidates(snap)

    dimensions, dim_statuses = _build_dimensions(
        features=features,
        stored_pillars=stored_pillars,
        audit_pillars=audit_pillars,
        ecdfs=ecdfs,
        bundle=bundle,
        present=present,
    )

    primary_stored = _stored_candidate_score(snap, PRIMARY_ID)
    candidates: dict[str, Any] = {}
    cand_statuses: list[str] = []
    for cid in UI_CANDIDATE_IDS:
        expl = _build_candidate(
            cid=cid,
            snap=snap,
            audit_pillars=audit_pillars,
            audit_scores=audit_scores,
            bundle=bundle,
            primary_stored=primary_stored,
        )
        candidates[cid] = expl
        cand_statuses.append(expl["consistency"]["status"])
        for pred in (expl.get("calibrated_predictions") or {}).values():
            cand_statuses.append((pred.get("consistency") or {}).get("status") or "unavailable")

    additional = _build_additional_candidates(snap, full_pillars, present)

    freeze_at = _ensure_utc(bundle.frozen_at)
    source_at = _ensure_utc(snap.source_snapshot_at)
    kickoff = _ensure_utc(snap.kickoff)
    after_freeze = bool(freeze_at and source_at and source_at > freeze_at)
    before_kickoff = bool(kickoff and source_at and source_at < kickoff) if source_at and kickoff else None

    all_statuses = dim_statuses + cand_statuses
    top_status = "ok"
    if missing_features:
        top_status = "partial"
    elif any(s == "mismatch" for s in all_statuses):
        top_status = "partial"
    elif any(s in ("not_verifiable", "unavailable") for s in all_statuses):
        # display-only or optional gaps may be fine; only partial if core metrics broken
        core_bad = any(
            (m.get("consistency") or {}).get("status") in ("mismatch", "not_verifiable")
            for dim in dimensions.values()
            for m in dim.get("metrics") or []
            if m.get("metric_key")
            in (
                "OP1_HOME_LONG_TERM",
                "OP2_HOME_RECENCY",
                "DV1_MEAN_CONCEDED",
                "MT1_LONG_TERM",
                "MT2_LONG_TERM_PLUS_RECENCY",
                "OV1_STD",
            )
        ) or any(
            (candidates[c].get("consistency") or {}).get("status") in ("mismatch", "not_verifiable")
            for c in UI_CANDIDATE_IDS
        )
        if core_bad:
            top_status = "partial"

    # Verify no train_values leaked
    payload = {
        "status": top_status,
        "audit_version": AUDIT_VERSION,
        "module": MODULE,
        "presentation": "legacy_preview",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "no_operational_recalculation": True,
        "diagnostic_re_evaluation_only": True,
        "source_mode": SOURCE_MODE,
        "fixture": {
            "today_fixture_id": int(row.id),
            "local_fixture_id": row.local_fixture_id,
            "provider_fixture_id": row.provider_fixture_id,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": _iso_z(_ensure_utc(row.kickoff)) if row.kickoff else None,
            "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        },
        "snapshot": {
            "snapshot_id": snap.id,
            "bundle_id": snap.bundle_id,
            "bundle_version": bundle.version,
            "candidate_version": bundle.candidate_indices_version,
            "candidate_definition_hash": snap.candidate_definition_hash or bundle.candidate_definition_hash,
            "source_snapshot_at": _iso_z(source_at),
            "bundle_frozen_at": _iso_z(freeze_at),
            "snapshot_status": snap.snapshot_status,
            "preview_status": snap.preview_status,
            "reason_codes": snap.diagnostic_reason_codes,
            "freeze_check": {
                "source_snapshot_at_gt_bundle_frozen_at": after_freeze,
                "source_snapshot_at_lt_kickoff": before_kickoff,
            },
        },
        "dimensions": dimensions,
        "candidates": candidates,
        "additional_candidates": additional,
        "warnings": warnings,
        "metadata": {
            "ui_candidate_ids": list(UI_CANDIDATE_IDS),
            "weight_status": WEIGHT_STATUS,
            "normalization_method": NORMALIZATION_METHOD,
            "bundle_id_used_for_audit": bundle.id,
            "active_bundle_not_used_for_coefficients": True,
        },
    }
    return _json_safe(payload)


def get_goal_intensity_v5_explanations(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
            "no_operational_recalculation": True,
            "diagnostic_re_evaluation_only": True,
            "source_mode": SOURCE_MODE,
        }

    from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
        get_preview_bundle_v1_1,
        is_official_bundle,
    )

    # Stessa risoluzione del pannello Today: snapshot sul bundle attivo, legacy come archivio
    active = get_active_bundle(db)
    snap: CecchinoGoalIntensityV5PreviewSnapshot | None = None
    if active is not None:
        snap = db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == active.id,
                CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id == int(today_fixture_id),
            )
        ).first()

    if snap is None and active is not None and is_official_bundle(active):
        legacy = get_preview_bundle_v1_1(db)
        if legacy is not None and getattr(legacy, "version", None) == PREVIEW_BUNDLE_VERSION:
            snap = db.scalars(
                select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                    CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == legacy.id,
                    CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id
                    == int(today_fixture_id),
                )
            ).first()

    if snap is None:
        return {
            "status": "error",
            "code": "goal_intensity_v5_not_available",
            "message": "Snapshot Goal Intensity v5 non disponibile",
            "no_operational_recalculation": True,
            "diagnostic_re_evaluation_only": True,
            "source_mode": SOURCE_MODE,
        }

    # Bundle esatto collegato allo snapshot (non un altro bundle attivo)
    bundle = db.get(CecchinoGoalIntensityV5PreviewBundle, snap.bundle_id)
    if bundle is None:
        return {
            "status": "error",
            "code": "goal_intensity_v5_bundle_missing",
            "message": "Bundle collegato allo snapshot non trovato",
            "no_operational_recalculation": True,
            "diagnostic_re_evaluation_only": True,
            "source_mode": SOURCE_MODE,
        }

    return build_goal_intensity_v5_explanations(row, snap, bundle)
