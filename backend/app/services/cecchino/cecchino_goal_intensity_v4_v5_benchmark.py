"""Benchmark prospettico paired Goal Intensity V4 vs V5 (Phase 2B).

Read-only: usa snapshot V5 completed e lambda V4 persistita in Today.goal_markets.
Nessuna scrittura DB, nessuna API esterna, nessun ricalcolo bundle/score.
"""

from __future__ import annotations

import math
import statistics
import threading
import time
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    SNAPSHOT_COMPLETED,
    SNAPSHOT_ERROR,
    SNAPSHOT_INCOMPLETE,
    SNAPSHOT_PENDING,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_intensity_analysis import (
    VERSION as V4_VERSION,
    _lambda_from_goal_markets,
    build_cecchino_goal_intensity_analysis_from_expected_goals,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    BENCHMARK_ID,
    CHALLENGER_ID,
    DIAGNOSTIC_ID,
    MINIMUM_PROSPECTIVE_MATCHES,
    MONITORED_CANDIDATES,
    PRIMARY_ID,
    VERSION as V5_BUNDLE_VERSION,
    _ensure_utc,
    _prospective_guard,
    get_active_bundle,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import (
    bootstrap_index_matrix,
    bootstrap_paired_delta_ci,
    safe_float,
)
from app.services.cecchino.cecchino_draw_credibility_statistics_helpers import (
    auc_mann_whitney,
    pearson_r,
    spearman_rho,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION = (
    "cecchino_goal_intensity_v4_v5_prospective_benchmark_v1"
)
V4_MODEL_ID = "GI_V4_EXPECTED_GOALS"
BOOTSTRAP_SEED = 42
BOOTSTRAP_ITERATIONS = 500
MIN_PAIRED_N = 5
PROB_CLIP = 1e-6

MODEL_META: dict[str, dict[str, str]] = {
    PRIMARY_ID: {"role": "primary", "label": "Primary V5", "family": "v5"},
    CHALLENGER_ID: {"role": "challenger", "label": "Challenger V5", "family": "v5"},
    BENCHMARK_ID: {"role": "benchmark_internal", "label": "Benchmark interno V5", "family": "v5"},
    DIAGNOSTIC_ID: {"role": "diagnostic", "label": "Senza volatilità V5", "family": "v5"},
    V4_MODEL_ID: {"role": "v4", "label": "V4", "family": "v4"},
}

PAIRWISE_SPECS: tuple[tuple[str, str], ...] = (
    (PRIMARY_ID, V4_MODEL_ID),
    (CHALLENGER_ID, V4_MODEL_ID),
    (BENCHMARK_ID, V4_MODEL_ID),
    (DIAGNOSTIC_ID, V4_MODEL_ID),
    (PRIMARY_ID, CHALLENGER_ID),
    (PRIMARY_ID, BENCHMARK_ID),
    (PRIMARY_ID, DIAGNOSTIC_ID),
)

_CACHE_TTL_S = 300.0
_cache_lock = threading.Lock()
_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def clear_goal_intensity_v4_v5_benchmark_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _round(v: float | None, nd: int = 6) -> float | None:
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return round(float(v), nd)


def _clip_prob(p: float) -> float:
    return min(1.0 - PROB_CLIP, max(PROB_CLIP, float(p)))


def _is_finite(v: Any) -> bool:
    f = safe_float(v)
    return f is not None


def _ci_includes_zero(ci: dict[str, Any] | None) -> bool:
    if not ci:
        return True
    lo, hi = ci.get("ci_lower"), ci.get("ci_upper")
    if lo is None or hi is None:
        return True
    return float(lo) <= 0.0 <= float(hi)


def _evidence_level(*, n: int, ci: dict[str, Any] | None, delta: float | None) -> str:
    if n < MIN_PAIRED_N or delta is None or not ci or ci.get("ci_lower") is None:
        return "insufficient_sample"
    if _ci_includes_zero(ci):
        return "low"
    # CI entirely on one side of zero
    lo = float(ci["ci_lower"])
    hi = float(ci["ci_upper"])
    width = abs(hi - lo)
    mag = abs(float(delta))
    if width > 0 and mag / width >= 0.5:
        return "supported"
    return "directional"


def _preferred_side(delta: float | None, ci: dict[str, Any] | None) -> str:
    if delta is None or _ci_includes_zero(ci):
        return "none"
    if float(delta) < 0:
        return "left"
    if float(delta) > 0:
        return "right"
    return "none"


def _mae(preds: list[float], actuals: list[float]) -> float | None:
    if not preds:
        return None
    return float(np.mean([abs(p - y) for p, y in zip(preds, actuals)]))


def _rmse(preds: list[float], actuals: list[float]) -> float | None:
    if not preds:
        return None
    return float(math.sqrt(np.mean([(p - y) ** 2 for p, y in zip(preds, actuals)])))


def _bias(preds: list[float], actuals: list[float]) -> float | None:
    if not preds:
        return None
    return float(np.mean([p - y for p, y in zip(preds, actuals)]))


def _medae(preds: list[float], actuals: list[float]) -> float | None:
    if not preds:
        return None
    return float(statistics.median([abs(p - y) for p, y in zip(preds, actuals)]))


def _brier(probs: list[float], ys: list[int]) -> float | None:
    if not probs:
        return None
    return float(np.mean([(_clip_prob(p) - y) ** 2 for p, y in zip(probs, ys)]))


def _log_loss(probs: list[float], ys: list[int]) -> float | None:
    if not probs:
        return None
    total = 0.0
    for p, y in zip(probs, ys):
        pc = _clip_prob(p)
        total += -(y * math.log(pc) + (1 - y) * math.log(1 - pc))
    return total / len(probs)


def _calibration_bins(
    probs: list[float],
    ys: list[int],
    *,
    n_bins: int = 10,
) -> tuple[float | None, list[dict[str, Any]]]:
    if len(probs) < 2:
        return None, []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict[str, Any]] = []
    ece = 0.0
    n = len(probs)
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        idxs = [
            j
            for j, p in enumerate(probs)
            if (p >= lo and p < hi) or (i == n_bins - 1 and p <= hi and p >= lo)
        ]
        if not idxs:
            bins.append(
                {
                    "bin": i,
                    "lo": _round(lo),
                    "hi": _round(hi),
                    "n": 0,
                    "mean_pred": None,
                    "mean_actual": None,
                    "abs_gap": None,
                }
            )
            continue
        mean_pred = float(np.mean([probs[j] for j in idxs]))
        mean_act = float(np.mean([ys[j] for j in idxs]))
        gap = abs(mean_pred - mean_act)
        ece += gap * (len(idxs) / n)
        bins.append(
            {
                "bin": i,
                "lo": _round(lo),
                "hi": _round(hi),
                "n": len(idxs),
                "mean_pred": _round(mean_pred),
                "mean_actual": _round(mean_act),
                "abs_gap": _round(gap),
            }
        )
    return _round(ece), bins


def extract_v4_from_persisted_today(
    today_row: CecchinoTodayFixture | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Estrae V4 solo da payload/lambda persistiti. Nessun fallback DB."""
    if today_row is None:
        return None, "missing_today_fixture"
    output = today_row.cecchino_output_json if isinstance(today_row.cecchino_output_json, dict) else {}
    # Path A: payload V4 già persistito
    for key in ("goal_intensity_analysis", "goal_intensity_v4"):
        block = output.get(key)
        if isinstance(block, dict) and block.get("status") == "available":
            eg = safe_float(block.get("expected_goals_total"))
            if eg is not None and eg > 0:
                payload = build_cecchino_goal_intensity_analysis_from_expected_goals(eg)
                # Preferisci probabilità già nel payload se presenti e finite
                thresholds = block.get("thresholds") if isinstance(block.get("thresholds"), dict) else None
                if thresholds:
                    payload = dict(payload)
                    payload["thresholds"] = thresholds
                    payload["expected_goals_total"] = eg
                return payload, None
    # Path B: lambda in goal_markets
    goal_markets = output.get("goal_markets") if isinstance(output.get("goal_markets"), dict) else None
    lam = _lambda_from_goal_markets(goal_markets)
    if lam is None or lam <= 0:
        return None, "missing_persisted_v4_expected_goals"
    return build_cecchino_goal_intensity_analysis_from_expected_goals(lam), None


def extract_v5_calibrated(
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    candidate_id: str,
) -> dict[str, float | None] | None:
    cal = (snap.calibrated_predictions_payload or {}).get(candidate_id)
    if not isinstance(cal, dict):
        return None
    eg = safe_float(cal.get("expected_total_goals"))
    p2 = safe_float(cal.get("probability_goals_ge_2"))
    p3 = safe_float(cal.get("probability_goals_ge_3"))
    pb = safe_float(cal.get("probability_btts"))
    if eg is None and p2 is None and p3 is None:
        return None
    return {
        "expected_total_goals": eg,
        "probability_goals_ge_2": p2,
        "probability_goals_ge_3": p3,
        "probability_btts": pb,
    }


def _v4_over_prob(v4_payload: dict[str, Any], key: str) -> float | None:
    thresholds = v4_payload.get("thresholds") if isinstance(v4_payload.get("thresholds"), dict) else {}
    block = thresholds.get(key) if isinstance(thresholds, dict) else None
    if isinstance(block, dict):
        return safe_float(block.get("probability"))
    return None


def _snapshot_prospective_ok(
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    *,
    freeze_at: datetime | None,
    guard: dict[str, Any],
) -> tuple[bool, str | None]:
    if snap.snapshot_status == SNAPSHOT_PENDING:
        return False, "pending_snapshot"
    if snap.snapshot_status == SNAPSHOT_INCOMPLETE:
        return False, "incomplete_snapshot"
    if snap.snapshot_status == SNAPSHOT_ERROR:
        return False, "error_snapshot"
    if snap.result_attached_at is None or snap.total_goals_ft is None:
        return False, "missing_ft_result"
    if snap.total_goals_ft is not None and float(snap.total_goals_ft) < 0:
        return False, "invalid_ft_result"
    # retrospective identity
    retro_today = set(guard.get("retrospective_today_fixture_ids") or [])
    retro_local = set(guard.get("retrospective_local_fixture_ids") or [])
    if snap.today_fixture_id in retro_today:
        return False, "retrospective_identity"
    if snap.local_fixture_id is not None and int(snap.local_fixture_id) in {
        int(x) for x in retro_local if x is not None
    }:
        return False, "retrospective_identity"
    if freeze_at is not None and snap.source_snapshot_at is not None:
        src = _ensure_utc(snap.source_snapshot_at)
        if (
            src is not None
            and isinstance(src, datetime)
            and isinstance(freeze_at, datetime)
            and src <= freeze_at
        ):
            return False, "snapshot_pre_freeze"
    if snap.kickoff is not None and snap.source_snapshot_at is not None:
        src = _ensure_utc(snap.source_snapshot_at)
        ko = _ensure_utc(snap.kickoff)
        if (
            src is not None
            and ko is not None
            and isinstance(src, datetime)
            and isinstance(ko, datetime)
            and src >= ko
        ):
            return False, "snapshot_post_kickoff"
    if snap.no_target_used_in_score is False:
        return False, "target_leakage_flag"
    return True, None


def _filter_by_date_comp(
    snaps: list[CecchinoGoalIntensityV5PreviewSnapshot],
    *,
    date_from: date | None,
    date_to: date | None,
    competition_id: int | None,
) -> list[CecchinoGoalIntensityV5PreviewSnapshot]:
    out = []
    for s in snaps:
        if date_from and s.scan_date and s.scan_date < date_from:
            continue
        if date_to and s.scan_date and s.scan_date > date_to:
            continue
        if competition_id is not None and s.competition_id != competition_id:
            continue
        out.append(s)
    return out


def _dedupe_by_fixture(
    snaps: list[CecchinoGoalIntensityV5PreviewSnapshot],
) -> list[CecchinoGoalIntensityV5PreviewSnapshot]:
    """Una riga per fixture: preferisci result_attached più recente, poi id più alto."""
    best: dict[Any, CecchinoGoalIntensityV5PreviewSnapshot] = {}
    for s in snaps:
        key = s.local_fixture_id if s.local_fixture_id is not None else ("today", s.today_fixture_id)
        prev = best.get(key)
        if prev is None:
            best[key] = s
            continue
        prev_ts = prev.result_attached_at or prev.source_snapshot_at
        cur_ts = s.result_attached_at or s.source_snapshot_at
        if cur_ts and (prev_ts is None or cur_ts > prev_ts):
            best[key] = s
        elif cur_ts == prev_ts and (s.id or 0) > (prev.id or 0):
            best[key] = s
    return list(best.values())


def _continuous_metrics(preds: list[float], actuals: list[float]) -> dict[str, Any]:
    n = len(preds)
    if n == 0:
        return {
            "n": 0,
            "mae": None,
            "rmse": None,
            "mean_error": None,
            "median_absolute_error": None,
            "pearson": None,
            "spearman": None,
        }
    return {
        "n": n,
        "mae": _round(_mae(preds, actuals)),
        "rmse": _round(_rmse(preds, actuals)),
        "mean_error": _round(_bias(preds, actuals)),
        "median_absolute_error": _round(_medae(preds, actuals)),
        "pearson": _round(pearson_r(preds, actuals)),
        "spearman": _round(spearman_rho(preds, actuals)),
    }


def _binary_metrics(probs: list[float], ys: list[int]) -> dict[str, Any]:
    n = len(probs)
    if n == 0:
        return {
            "n": 0,
            "brier": None,
            "log_loss": None,
            "auc": None,
            "calibration_error": None,
            "calibration_bins": [],
        }
    clipped = [_clip_prob(p) for p in probs]
    ece, bins = _calibration_bins(clipped, ys)
    classes = set(ys)
    auc = auc_mann_whitney(ys, clipped) if len(classes) >= 2 else None
    return {
        "n": n,
        "brier": _round(_brier(clipped, ys)),
        "log_loss": _round(_log_loss(clipped, ys)),
        "auc": _round(auc),
        "calibration_error": ece,
        "calibration_bins": bins,
    }


def _pairwise_error_comparison(
    left_errs: list[float],
    right_errs: list[float],
    *,
    left_id: str,
    right_id: str,
    metric: str,
    indices: np.ndarray | None,
) -> dict[str, Any]:
    n = min(len(left_errs), len(right_errs))
    if n == 0:
        return {
            "left_id": left_id,
            "right_id": right_id,
            "metric": metric,
            "n": 0,
            "delta": None,
            "delta_definition": "left_metric - right_metric; delta<0 favors left",
            "ci": {"mean": None, "ci_lower": None, "ci_upper": None, "valid_bootstrap_iterations": 0},
            "preferred_side": "none",
            "evidence_level": "insufficient_sample",
            "bootstrap_iterations_valid": 0,
        }
    deltas = [left_errs[i] - right_errs[i] for i in range(n)]
    idx = indices if indices is not None and len(indices) > 0 and indices.shape[1] == n else None
    ci = bootstrap_paired_delta_ci(
        deltas,
        iterations=min(BOOTSTRAP_ITERATIONS, max(n * 2, 50)),
        seed=BOOTSTRAP_SEED,
        indices=idx,
    )
    delta = ci.get("mean")
    return {
        "left_id": left_id,
        "right_id": right_id,
        "metric": metric,
        "n": n,
        "delta": delta,
        "delta_definition": "left_metric - right_metric; delta<0 favors left",
        "ci": ci,
        "preferred_side": _preferred_side(delta if isinstance(delta, (int, float)) else None, ci),
        "evidence_level": _evidence_level(
            n=n,
            ci=ci,
            delta=float(delta) if delta is not None else None,
        ),
        "bootstrap_iterations_valid": ci.get("valid_bootstrap_iterations") or 0,
    }


def _scientific_interpretation(
    *,
    paired_n: int,
    primary_vs_v4_mae: dict[str, Any] | None,
) -> dict[str, Any]:
    if paired_n < MIN_PAIRED_N:
        status = "paired_coverage_insufficient" if paired_n > 0 else "benchmark_unavailable"
        return {
            "status": status,
            "summary_it": (
                "Copertura paired insufficiente per un confronto conclusivo."
                if status == "paired_coverage_insufficient"
                else "Benchmark non disponibile: coorte paired vuota."
            ),
            "promotes_signals": False,
            "claims_productive_validation": False,
        }
    if not primary_vs_v4_mae:
        return {
            "status": "benchmark_unavailable",
            "summary_it": "Confronto Primary V5 vs V4 non disponibile.",
            "promotes_signals": False,
            "claims_productive_validation": False,
        }
    evidence = primary_vs_v4_mae.get("evidence_level")
    preferred = primary_vs_v4_mae.get("preferred_side")
    if evidence == "supported" and preferred == "left":
        status = "v5_primary_supported_over_v4"
        summary = (
            "Evidenza paired supporta errore inferiore del Primary V5 rispetto a V4 "
            "(CI non include zero). Non autorizza integrazione Signals."
        )
    elif evidence == "supported" and preferred == "right":
        status = "v4_supported_over_v5_primary"
        summary = (
            "Evidenza paired supporta errore inferiore di V4 rispetto al Primary V5 "
            "(CI non include zero). Non autorizza integrazione Signals."
        )
    else:
        status = "no_clear_difference"
        summary = (
            "Nessuna differenza conclusiva Primary V5 vs V4: "
            "intervallo di confidenza include zero oppure evidenza insufficiente."
        )
    return {
        "status": status,
        "summary_it": summary,
        "primary_vs_v4_mae_evidence": evidence,
        "promotes_signals": False,
        "claims_productive_validation": False,
    }


def build_goal_intensity_v4_v5_prospective_benchmark(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    source_cohort: str | None = None,
) -> dict[str, Any]:
    """Costruisce il benchmark paired prospettico V4–V5 (read-only)."""
    bundle = get_active_bundle(db)
    if bundle is None:
        return make_json_safe(
            {
                "status": "error",
                "error": "bundle_missing",
                "version": GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
                "v4_version": V4_VERSION,
                "v5_bundle_version": V5_BUNDLE_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    freeze_at = _ensure_utc(bundle.frozen_at)
    guard = _prospective_guard(bundle)
    definition_hash = bundle.candidate_definition_hash

    all_snaps = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
            )
        ).all()
    )
    filtered = _filter_by_date_comp(
        all_snaps,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )

    # Completed V5 candidates for cohort (pre-dedupe diagnostics)
    completed_raw = [
        s
        for s in filtered
        if s.snapshot_status == SNAPSHOT_COMPLETED
        and s.result_attached_at is not None
        and s.total_goals_ft is not None
    ]
    completed_v5_total = len(completed_raw)

    max_result_ts = None
    for s in completed_raw:
        if s.result_attached_at and (max_result_ts is None or s.result_attached_at > max_result_ts):
            max_result_ts = s.result_attached_at

    cache_key = (
        GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
        date_from,
        date_to,
        competition_id,
        source_cohort or "all",
        bundle.version,
        definition_hash,
        max_result_ts.isoformat() if max_result_ts else None,
        completed_v5_total,
    )
    with _cache_lock:
        hit = _cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < _CACHE_TTL_S:
            out = dict(hit[1])
            out["cache_hit"] = True
            return out

    today_ids = {s.today_fixture_id for s in completed_raw if s.today_fixture_id is not None}
    today_by_id: dict[int, CecchinoTodayFixture] = {}
    if today_ids:
        rows = list(
            db.scalars(
                select(CecchinoTodayFixture).where(CecchinoTodayFixture.id.in_(today_ids))
            ).all()
        )
        today_by_id = {int(r.id): r for r in rows}

    missing_reasons: Counter[str] = Counter()
    eligible: list[CecchinoGoalIntensityV5PreviewSnapshot] = []
    for s in completed_raw:
        ok, reason = _snapshot_prospective_ok(s, freeze_at=freeze_at, guard=guard)
        if not ok:
            missing_reasons[reason or "excluded"] += 1
            continue
        eligible.append(s)

    eligible = _dedupe_by_fixture(eligible)

    # Build paired observations
    observations: list[dict[str, Any]] = []
    v4_available = 0
    cand_available = {cid: 0 for cid in MONITORED_CANDIDATES}
    all_v5_available = 0

    for s in eligible:
        today = today_by_id.get(int(s.today_fixture_id)) if s.today_fixture_id is not None else None
        v4_payload, v4_reason = extract_v4_from_persisted_today(today)
        v5_by_cand: dict[str, dict[str, float | None]] = {}
        missing_cand = False
        for cid in MONITORED_CANDIDATES:
            pred = extract_v5_calibrated(s, cid)
            if pred is None or pred.get("expected_total_goals") is None:
                missing_cand = True
                missing_reasons[f"missing_v5_candidate_{cid}"] += 1
            else:
                cand_available[cid] += 1
                v5_by_cand[cid] = pred
                # binary may still be missing — track separately for paired_complete
                if pred.get("probability_goals_ge_2") is None:
                    missing_reasons[f"missing_v5_ge2_{cid}"] += 1
                if pred.get("probability_goals_ge_3") is None:
                    missing_reasons[f"missing_v5_ge3_{cid}"] += 1

        if len(v5_by_cand) == len(MONITORED_CANDIDATES):
            all_v5_available += 1

        if v4_payload is None:
            missing_reasons[v4_reason or "missing_persisted_v4_expected_goals"] += 1
            continue
        v4_available += 1
        v4_eg = safe_float(v4_payload.get("expected_goals_total"))
        if v4_eg is None or v4_eg <= 0:
            missing_reasons["missing_persisted_v4_expected_goals"] += 1
            continue

        if missing_cand or len(v5_by_cand) < len(MONITORED_CANDIDATES):
            continue

        # Require binary probs for full paired row used in ranking tables
        binary_ok = True
        for cid in MONITORED_CANDIDATES:
            p = v5_by_cand[cid]
            if p.get("probability_goals_ge_2") is None or p.get("probability_goals_ge_3") is None:
                binary_ok = False
                break
        p_ge2 = _v4_over_prob(v4_payload, "over_1_5")
        p_ge3 = _v4_over_prob(v4_payload, "over_2_5")
        if p_ge2 is None or p_ge3 is None:
            missing_reasons["missing_v4_over_probabilities"] += 1
            continue
        if not binary_ok:
            continue

        y = float(s.total_goals_ft)  # type: ignore[arg-type]
        ge2 = 1 if y >= 2 else 0
        ge3 = 1 if y >= 3 else 0
        btts = None
        if s.btts_ft is not None:
            btts = 1 if bool(s.btts_ft) else 0
        elif s.goals_home_ft is not None and s.goals_away_ft is not None:
            btts = 1 if int(s.goals_home_ft) > 0 and int(s.goals_away_ft) > 0 else 0

        observations.append(
            {
                "snapshot_id": s.id,
                "today_fixture_id": s.today_fixture_id,
                "local_fixture_id": s.local_fixture_id,
                "y_total": y,
                "y_ge2": ge2,
                "y_ge3": ge3,
                "y_btts": btts,
                "v4_eg": float(v4_eg),
                "v4_p_ge2": float(p_ge2),
                "v4_p_ge3": float(p_ge3),
                "v5": v5_by_cand,
            }
        )

    paired_complete_n = len(observations)
    excluded_n = max(0, completed_v5_total - paired_complete_n)
    paired_coverage_pct = (
        _round(100.0 * paired_complete_n / completed_v5_total, 2) if completed_v5_total else 0.0
    )

    # Metrics by model on paired complete
    y_total = [o["y_total"] for o in observations]
    y_ge2 = [o["y_ge2"] for o in observations]
    y_ge3 = [o["y_ge3"] for o in observations]

    continuous_by_model: dict[str, Any] = {}
    ge2_by_model: dict[str, Any] = {}
    ge3_by_model: dict[str, Any] = {}
    abs_err: dict[str, list[float]] = {}
    sq_err: dict[str, list[float]] = {}
    brier_ge2_comp: dict[str, list[float]] = {}
    brier_ge3_comp: dict[str, list[float]] = {}

    # V4
    v4_preds = [o["v4_eg"] for o in observations]
    v4_p2 = [o["v4_p_ge2"] for o in observations]
    v4_p3 = [o["v4_p_ge3"] for o in observations]
    continuous_by_model[V4_MODEL_ID] = {
        **MODEL_META[V4_MODEL_ID],
        "model_id": V4_MODEL_ID,
        **_continuous_metrics(v4_preds, y_total),
    }
    ge2_by_model[V4_MODEL_ID] = {
        **MODEL_META[V4_MODEL_ID],
        "model_id": V4_MODEL_ID,
        **_binary_metrics(v4_p2, y_ge2),
    }
    ge3_by_model[V4_MODEL_ID] = {
        **MODEL_META[V4_MODEL_ID],
        "model_id": V4_MODEL_ID,
        **_binary_metrics(v4_p3, y_ge3),
    }
    abs_err[V4_MODEL_ID] = [abs(p - y) for p, y in zip(v4_preds, y_total)]
    sq_err[V4_MODEL_ID] = [(p - y) ** 2 for p, y in zip(v4_preds, y_total)]
    brier_ge2_comp[V4_MODEL_ID] = [(_clip_prob(p) - y) ** 2 for p, y in zip(v4_p2, y_ge2)]
    brier_ge3_comp[V4_MODEL_ID] = [(_clip_prob(p) - y) ** 2 for p, y in zip(v4_p3, y_ge3)]

    btts_v5: dict[str, Any] = {}
    for cid in MONITORED_CANDIDATES:
        preds = [float(o["v5"][cid]["expected_total_goals"]) for o in observations]  # type: ignore[index]
        p2 = [float(o["v5"][cid]["probability_goals_ge_2"]) for o in observations]  # type: ignore[index]
        p3 = [float(o["v5"][cid]["probability_goals_ge_3"]) for o in observations]  # type: ignore[index]
        continuous_by_model[cid] = {
            **MODEL_META[cid],
            "model_id": cid,
            **_continuous_metrics(preds, y_total),
        }
        ge2_by_model[cid] = {
            **MODEL_META[cid],
            "model_id": cid,
            **_binary_metrics(p2, y_ge2),
        }
        ge3_by_model[cid] = {
            **MODEL_META[cid],
            "model_id": cid,
            **_binary_metrics(p3, y_ge3),
        }
        abs_err[cid] = [abs(p - y) for p, y in zip(preds, y_total)]
        sq_err[cid] = [(p - y) ** 2 for p, y in zip(preds, y_total)]
        brier_ge2_comp[cid] = [(_clip_prob(p) - y) ** 2 for p, y in zip(p2, y_ge2)]
        brier_ge3_comp[cid] = [(_clip_prob(p) - y) ** 2 for p, y in zip(p3, y_ge3)]

        btts_pairs = [
            (float(o["v5"][cid]["probability_btts"]), int(o["y_btts"]))  # type: ignore[index]
            for o in observations
            if o["y_btts"] is not None and o["v5"][cid].get("probability_btts") is not None
        ]
        if btts_pairs:
            bp = [a for a, _ in btts_pairs]
            by = [b for _, b in btts_pairs]
            btts_v5[cid] = {
                **MODEL_META[cid],
                "model_id": cid,
                **_binary_metrics(bp, by),
            }
        else:
            btts_v5[cid] = {
                **MODEL_META[cid],
                "model_id": cid,
                "n": 0,
                "status": "insufficient_data",
            }

    idx_matrix = (
        bootstrap_index_matrix(paired_complete_n, BOOTSTRAP_ITERATIONS, BOOTSTRAP_SEED)
        if paired_complete_n > 0
        else np.empty((0, 0), dtype=np.intp)
    )

    def _comps(err_map: dict[str, list[float]], metric: str) -> list[dict[str, Any]]:
        out_list = []
        for left, right in PAIRWISE_SPECS:
            out_list.append(
                _pairwise_error_comparison(
                    err_map[left],
                    err_map[right],
                    left_id=left,
                    right_id=right,
                    metric=metric,
                    indices=idx_matrix,
                )
            )
        return out_list

    continuous_comparisons = _comps(abs_err, "mae") + _comps(sq_err, "mse_for_rmse")
    # Also expose RMSE delta as sqrt not paired — keep MAE primary; add rmse pairwise on abs? Task asks MAE and RMSE deltas.
    # For RMSE, paired bootstrap on squared-error mean difference is standard; report metric "rmse_via_mse_delta".
    ge2_comparisons = _comps(brier_ge2_comp, "brier")
    ge3_comparisons = _comps(brier_ge3_comp, "brier")

    primary_vs_v4_mae = next(
        (
            c
            for c in continuous_comparisons
            if c["left_id"] == PRIMARY_ID and c["right_id"] == V4_MODEL_ID and c["metric"] == "mae"
        ),
        None,
    )
    interpretation = _scientific_interpretation(
        paired_n=paired_complete_n,
        primary_vs_v4_mae=primary_vs_v4_mae,
    )

    warnings: list[str] = []
    if paired_complete_n < MINIMUM_PROSPECTIVE_MATCHES:
        warnings.append("paired_complete_below_historical_minimum_context")
    if paired_complete_n < MIN_PAIRED_N:
        warnings.append("paired_n_below_min_comparison")

    out = make_json_safe(
        {
            "status": "ok",
            "version": GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
            "v4_version": V4_VERSION,
            "v5_bundle_version": bundle.version,
            "definition_hash": definition_hash,
            "filters": {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "competition_id": competition_id,
                "source_cohort": source_cohort or "all",
            },
            "cohort": {
                "completed_v5_total": completed_v5_total,
                "v4_available": v4_available,
                "primary_available": cand_available[PRIMARY_ID],
                "challenger_available": cand_available[CHALLENGER_ID],
                "benchmark_available": cand_available[BENCHMARK_ID],
                "diagnostic_available": cand_available[DIAGNOSTIC_ID],
                "all_v5_candidates_available": all_v5_available,
                "paired_complete_n": paired_complete_n,
                "excluded_n": excluded_n,
                "paired_coverage_pct": paired_coverage_pct,
                "missing_by_reason": dict(sorted(missing_reasons.items())),
            },
            "continuous_total_goals": {
                "metrics_by_model": continuous_by_model,
                "comparisons": continuous_comparisons,
            },
            "goals_ge_2": {
                "metrics_by_model": ge2_by_model,
                "comparisons": ge2_comparisons,
            },
            "goals_ge_3": {
                "metrics_by_model": ge3_by_model,
                "comparisons": ge3_comparisons,
            },
            "btts": {
                "v4_status": "not_comparable",
                "v4_reason": "v4_total_lambda_has_no_team_split_btts_probability",
                "v5_metrics_by_candidate": btts_v5,
            },
            "quality_checks": {
                "target_leakage_check": "passed_no_target_used_in_score",
                "snapshot_pre_kickoff_check": "enforced",
                "external_api_calls": 0,
                "historical_run_used": False,
                "v4_builder": "build_cecchino_goal_intensity_analysis_from_expected_goals",
                "v4_db_fallback_used": False,
                "bundle_recomputed": False,
            },
            "scientific_interpretation": interpretation,
            "warnings": warnings,
            "cache_hit": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    with _cache_lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[cache_key] = (time.monotonic(), dict(out))
    return out


def build_phase_2b_benchmark_summary(benchmark: dict[str, Any]) -> dict[str, Any]:
    """Sezione informativa readiness: non altera Signals/policy."""
    if benchmark.get("status") != "ok":
        return {
            "status": "unavailable",
            "benchmark_version": GOAL_INTENSITY_V4_V5_PROSPECTIVE_BENCHMARK_VERSION,
            "paired_complete_n": 0,
            "paired_coverage_pct": 0,
            "v4_available": 0,
            "blocking_reasons": [str(benchmark.get("error") or "benchmark_unavailable")],
            "recommended_next_step": "phase_2b_replacement_review",
        }
    cohort = benchmark.get("cohort") or {}
    comps = (benchmark.get("continuous_total_goals") or {}).get("comparisons") or []

    def _pick(left: str) -> dict[str, Any] | None:
        for c in comps:
            if c.get("left_id") == left and c.get("right_id") == V4_MODEL_ID and c.get("metric") == "mae":
                return c
        return None

    return {
        "status": "available",
        "benchmark_version": benchmark.get("version"),
        "paired_complete_n": cohort.get("paired_complete_n"),
        "paired_coverage_pct": cohort.get("paired_coverage_pct"),
        "v4_available": cohort.get("v4_available"),
        "primary_vs_v4": _pick(PRIMARY_ID),
        "challenger_vs_v4": _pick(CHALLENGER_ID),
        "benchmark_internal_vs_v4": _pick(BENCHMARK_ID),
        "diagnostic_vs_v4": _pick(DIAGNOSTIC_ID),
        "scientific_interpretation": benchmark.get("scientific_interpretation"),
        "blocking_reasons": [],
        "recommended_next_step": "phase_2b_replacement_review",
    }
