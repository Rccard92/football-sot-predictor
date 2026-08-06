"""Metriche, pairwise e breakdown per benchmark storico GI."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark import (
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    CHALLENGER_ID,
    PRIMARY_ID,
    V4_MODEL_ID,
    _binary_metrics,
    _continuous_metrics,
    _pairwise_error_comparison,
    _round,
)
from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import (
    GI_E_ID,
    GI_F_ID,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import (
    bootstrap_index_matrix,
    safe_float,
)
from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_scoring import (
    MAIN_MODEL_IDS,
)

PAIRWISE_PAIRS = (
    (PRIMARY_ID, V4_MODEL_ID),
    (CHALLENGER_ID, V4_MODEL_ID),
    (GI_E_ID, V4_MODEL_ID),
    (GI_F_ID, V4_MODEL_ID),
    (GI_E_ID, PRIMARY_ID),
    (GI_F_ID, PRIMARY_ID),
    (GI_E_ID, CHALLENGER_ID),
    (GI_F_ID, CHALLENGER_ID),
    (GI_E_ID, GI_F_ID),
)

SMALL_SAMPLE_N = 30


def _abs_errs(preds: list[float], actuals: list[float]) -> list[float]:
    return [abs(p - a) for p, a in zip(preds, actuals)]


def _sq_errs(preds: list[float], actuals: list[float]) -> list[float]:
    return [(p - a) ** 2 for p, a in zip(preds, actuals)]


def evaluate_paired_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows: each has models{id->{eg,p2,p3,btts}} and target{total,ge2,ge3,btts}."""
    model_series: dict[str, dict[str, list]] = {
        mid: {"eg": [], "ge2": [], "ge3": [], "btts": [], "y_btts": []}
        for mid in MAIN_MODEL_IDS
    }
    y_total: list[float] = []
    y_ge2: list[int] = []
    y_ge3: list[int] = []

    for row in rows:
        models = row.get("models") or {}
        target = row.get("target") or {}
        yt = safe_float(target.get("total_goals_ft"))
        if yt is None:
            continue
        # require all five
        packed = {}
        ok = True
        for mid in MAIN_MODEL_IDS:
            m = models.get(mid)
            if not isinstance(m, dict):
                ok = False
                break
            eg = safe_float(m.get("expected_total_goals"))
            p2 = safe_float(m.get("probability_goals_ge_2"))
            p3 = safe_float(m.get("probability_goals_ge_3"))
            if mid == V4_MODEL_ID:
                if eg is None or p2 is None or p3 is None:
                    ok = False
                    break
                packed[mid] = {"eg": eg, "ge2": p2, "ge3": p3, "btts": None}
            else:
                pb = safe_float(m.get("probability_btts"))
                if eg is None or p2 is None or p3 is None or pb is None:
                    ok = False
                    break
                packed[mid] = {"eg": eg, "ge2": p2, "ge3": p3, "btts": pb}
        if not ok:
            continue
        y_total.append(float(yt))
        y_ge2.append(int(target.get("goals_ge_2") or 0))
        y_ge3.append(int(target.get("goals_ge_3") or 0))
        yb = target.get("btts_ft")
        for mid in MAIN_MODEL_IDS:
            model_series[mid]["eg"].append(packed[mid]["eg"])
            model_series[mid]["ge2"].append(packed[mid]["ge2"])
            model_series[mid]["ge3"].append(packed[mid]["ge3"])
            if mid != V4_MODEL_ID and yb is not None and packed[mid]["btts"] is not None:
                model_series[mid]["btts"].append(packed[mid]["btts"])
                model_series[mid]["y_btts"].append(int(yb))

    n = len(y_total)
    metrics: dict[str, Any] = {}
    for mid in MAIN_MODEL_IDS:
        cont = _continuous_metrics(model_series[mid]["eg"], y_total)
        cont["bias"] = cont.pop("mean_error", None)
        ge2 = _binary_metrics(model_series[mid]["ge2"], y_ge2)
        ge3 = _binary_metrics(model_series[mid]["ge3"], y_ge3)
        if mid == V4_MODEL_ID:
            btts = {"n": 0, "status": "not_comparable"}
        else:
            btts = (
                _binary_metrics(model_series[mid]["btts"], model_series[mid]["y_btts"])
                if model_series[mid]["btts"]
                else {"n": 0, "status": "insufficient_data"}
            )
        metrics[mid] = {
            "n": n,
            "total_goals_ft": cont,
            "goals_ge_2": ge2,
            "goals_ge_3": ge3,
            "btts": btts,
        }

    # Pairwise bootstrap: MAE total_goals_ft + Brier ge2/ge3 (+ BTTS only V5↔V5)
    indices = bootstrap_index_matrix(n, BOOTSTRAP_ITERATIONS, BOOTSTRAP_SEED) if n else None
    pairwise = []
    for left_id, right_id in PAIRWISE_PAIRS:
        pairwise.append(
            _pairwise_error_comparison(
                _abs_errs(model_series[left_id]["eg"], y_total),
                _abs_errs(model_series[right_id]["eg"], y_total),
                left_id=left_id,
                right_id=right_id,
                metric="mae",
                indices=indices,
            )
        )
    for left_id, right_id in PAIRWISE_PAIRS:
        pairwise.append(
            _pairwise_error_comparison(
                _sq_errs(model_series[left_id]["ge2"], y_ge2),
                _sq_errs(model_series[right_id]["ge2"], y_ge2),
                left_id=left_id,
                right_id=right_id,
                metric="brier_goals_ge_2",
                indices=indices,
            )
        )
    for left_id, right_id in PAIRWISE_PAIRS:
        pairwise.append(
            _pairwise_error_comparison(
                _sq_errs(model_series[left_id]["ge3"], y_ge3),
                _sq_errs(model_series[right_id]["ge3"], y_ge3),
                left_id=left_id,
                right_id=right_id,
                metric="brier_goals_ge_3",
                indices=indices,
            )
        )
    # BTTS: only among V5 models (no invented V4 probabilities)
    btts_n = 0
    for mid in MAIN_MODEL_IDS:
        if mid == V4_MODEL_ID:
            continue
        btts_n = len(model_series[mid]["btts"])
        break
    btts_indices = (
        bootstrap_index_matrix(btts_n, BOOTSTRAP_ITERATIONS, BOOTSTRAP_SEED) if btts_n else None
    )
    for left_id, right_id in PAIRWISE_PAIRS:
        if left_id == V4_MODEL_ID or right_id == V4_MODEL_ID:
            continue
        left_btts = model_series[left_id]["btts"]
        right_btts = model_series[right_id]["btts"]
        y_btts = model_series[left_id]["y_btts"]
        if not left_btts or not right_btts or len(left_btts) != len(right_btts):
            pairwise.append(
                _pairwise_error_comparison(
                    [],
                    [],
                    left_id=left_id,
                    right_id=right_id,
                    metric="brier_btts",
                    indices=None,
                )
            )
            continue
        pairwise.append(
            _pairwise_error_comparison(
                _sq_errs(left_btts, y_btts),
                _sq_errs(right_btts, y_btts),
                left_id=left_id,
                right_id=right_id,
                metric="brier_btts",
                indices=btts_indices,
            )
        )

    return {
        "paired_n": n,
        "model_metrics": metrics,
        "pairwise": pairwise,
        "bootstrap": {"seed": BOOTSTRAP_SEED, "iterations": BOOTSTRAP_ITERATIONS, "ci": 0.95},
    }


def _bucket_metrics(subset: list[dict[str, Any]]) -> dict[str, Any]:
    ev = evaluate_paired_rows(subset)
    n = int(ev.get("paired_n") or 0)
    return {
        "n": n,
        "coverage": n,
        "warning_small_sample": n < SMALL_SAMPLE_N,
        "model_metrics": ev.get("model_metrics") or {},
    }


def build_breakdowns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_comp: dict[str, list] = defaultdict(list)
    by_month: dict[str, list] = defaultdict(list)
    by_eg_band: dict[str, list] = defaultdict(list)
    by_decile_a: dict[str, list] = defaultdict(list)
    by_decile_f: dict[str, list] = defaultdict(list)
    by_season_third: dict[str, list] = defaultdict(list)

    # Precompute deciles on GI_A / GI_F raw/score
    a_scores = []
    f_scores = []
    for r in rows:
        models = r.get("models") or {}
        a = safe_float((models.get(PRIMARY_ID) or {}).get("raw_score"))
        f = safe_float((models.get(GI_F_ID) or {}).get("raw_score"))
        if a is not None:
            a_scores.append(a)
        if f is not None:
            f_scores.append(f)
    a_edges = np.percentile(a_scores, np.arange(10, 100, 10)).tolist() if len(a_scores) >= 10 else []
    f_edges = np.percentile(f_scores, np.arange(10, 100, 10)).tolist() if len(f_scores) >= 10 else []

    def _decile(val: float | None, edges: list[float]) -> str:
        if val is None or not edges:
            return "unknown"
        d = 1
        for e in edges:
            if val > e:
                d += 1
            else:
                break
        return f"D{d}"

    def _eg_band(eg: float | None) -> str:
        if eg is None:
            return "unknown"
        if eg < 1.5:
            return "lt_1_5"
        if eg < 2.5:
            return "1_5_to_2_5"
        if eg < 3.5:
            return "2_5_to_3_5"
        return "ge_3_5"

    ordered = sorted(rows, key=lambda r: (r.get("kickoff") or "", r.get("snapshot_id") or 0))
    n_all = len(ordered)
    for idx, r in enumerate(ordered):
        models = r.get("models") or {}
        by_comp[str(r.get("competition") or "unknown")].append(r)
        month = str(r.get("month") or "unknown")
        by_month[month].append(r)
        eg_a = safe_float((models.get(PRIMARY_ID) or {}).get("expected_total_goals"))
        by_eg_band[_eg_band(eg_a)].append(r)
        by_decile_a[
            _decile(safe_float((models.get(PRIMARY_ID) or {}).get("raw_score")), a_edges)
        ].append(r)
        by_decile_f[
            _decile(safe_float((models.get(GI_F_ID) or {}).get("raw_score")), f_edges)
        ].append(r)
        if n_all <= 0:
            third = "unknown"
        elif idx < n_all / 3:
            third = "early"
        elif idx < 2 * n_all / 3:
            third = "mid"
        else:
            third = "late"
        by_season_third[third].append(r)

    def _map(d: dict[str, list]) -> dict[str, Any]:
        return {k: _bucket_metrics(v) for k, v in sorted(d.items())}

    return {
        "competition": _map(by_comp),
        "month": _map(by_month),
        "total_goals_prediction_band": _map(by_eg_band),
        "gi_a_score_decile": _map(by_decile_a),
        "gi_f_score_decile": _map(by_decile_f),
        "season_third": _map(by_season_third),
        "small_sample_threshold": SMALL_SAMPLE_N,
        "note": "Nessuna conclusione automatica su campioni sotto soglia.",
    }
