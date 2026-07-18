"""Indice di Acquistabilità — Fase 2A ricerca statistica (read-only).

Versione: cecchino_purchasability_statistical_research_v2a
Dataset sorgente: cecchino_purchasability_dataset_v1_1 (non modificato).

Nessuna formula 0–100, nessuna scrittura DB, nessuna modifica Rating/KPI/Segnali.
"""

from __future__ import annotations

import csv
import io
import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterator

import numpy as np
from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_market_opposition import (
    FAMILY_DOUBLE_CHANCE,
    OPPOSITION_SUPPORTED,
)
from app.services.cecchino.cecchino_purchasability_audit import (
    DATASET_VERSION,
    build_purchasability_rows,
    make_json_safe,
)
from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
    brier,
    calibration_slope_intercept,
    clip_prob,
    ece_score,
    economic_metrics,
    expanding_fixture_folds,
    fixture_cluster_bootstrap_ci,
    gap_from_payload,
    log_loss_score,
    parse_iso,
    quantile_roi,
    roc_auc,
    safe_div,
    sha256_hex,
    spearman_rho,
    top_k_roi,
)

STAT_VERSION = "cecchino_purchasability_statistical_research_v2a"

PRIMARY_MARKETS = (
    "HOME",
    "DRAW",
    "AWAY",
    "ONE_X",
    "X_TWO",
    "ONE_TWO",
    "OVER_2_5",
    "UNDER_2_5",
    "OVER_PT_1_5",
    "UNDER_PT_1_5",
)

# Spec → feature keys (numeric + categoricals handled separately)
SPEC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "BOOK_BASELINE": {
        "features": ["book_prob"],
        "role": "baseline",
        "allows_rating": False,
    },
    "MODEL_BASELINE": {
        "features": ["model_probability"],
        "role": "baseline",
        "allows_rating": False,
    },
    "RATING_BASELINE": {
        "features": ["rating"],
        "role": "baseline",
        "allows_rating": True,
    },
    "VALUE_ADVANTAGE": {
        "features": ["model_probability", "probability_advantage"],
        "role": "value",
        "allows_rating": False,
    },
    "VALUE_EDGE": {
        "features": ["model_probability", "edge"],
        "role": "value",
        "allows_rating": False,
    },
    "VALUE_SCORE": {
        "features": ["score"],
        "role": "value",
        "allows_rating": False,
    },
    "CONTEXT_ONLY": {
        "features": [
            "favourite_intensity_book",
            "favourite_intensity_model",
            "comparator_odds_gap",
            "comparator_model_probability_gap",
            "complement_odds_gap",
            "complement_model_probability_gap",
        ],
        "categoricals": ["favourite_alignment"],
        "role": "context",
        "allows_rating": False,
    },
    "VALUE_ADVANTAGE_CONTEXT": {
        "features": [
            "model_probability",
            "probability_advantage",
            "favourite_intensity_book",
            "favourite_intensity_model",
            "comparator_odds_gap",
            "comparator_model_probability_gap",
        ],
        "categoricals": ["favourite_alignment"],
        "role": "value_context",
        "allows_rating": False,
    },
    "VALUE_EDGE_CONTEXT": {
        "features": [
            "model_probability",
            "edge",
            "favourite_intensity_book",
            "favourite_intensity_model",
            "comparator_odds_gap",
            "comparator_model_probability_gap",
        ],
        "categoricals": ["favourite_alignment"],
        "role": "value_context",
        "allows_rating": False,
    },
    "VALUE_SCORE_CONTEXT": {
        "features": [
            "score",
            "favourite_intensity_book",
            "favourite_intensity_model",
            "comparator_odds_gap",
            "comparator_model_probability_gap",
        ],
        "categoricals": ["favourite_alignment"],
        "role": "value_context",
        "allows_rating": False,
    },
    "RATING_CONTEXT": {
        "features": [
            "rating",
            "favourite_intensity_book",
            "favourite_intensity_model",
            "comparator_odds_gap",
            "comparator_model_probability_gap",
        ],
        "categoricals": ["favourite_alignment"],
        "role": "rating_context",
        "allows_rating": True,
    },
    "RATING_MARGINAL_DIAGNOSTIC": {
        "features": [],  # filled dynamically: best_without_rating + rating
        "role": "rating_marginal",
        "allows_rating": True,
        "diagnostic": True,
    },
}

FORBIDDEN_PAIRS = (
    frozenset({"odds", "raw_book_implied_probability"}),
    frozenset({"odds", "raw_implied"}),
)

TARGET_KEYS = frozenset(
    {
        "selection_won",
        "selection_lost",
        "selection_void",
        "unit_stake_profit",
        "settlement_status",
        "realized_probability_residual",
        "normalized_probability_residual",
        "y_win",
        "profit",
    }
)

DEFAULT_BOOTSTRAP_FE = 200
DEFAULT_BOOTSTRAP_BENCH = 1000
DEFAULT_SEED = 42

EXPORT_KINDS = (
    "summary",
    "cohort_identity",
    "temporal_folds",
    "market_results",
    "univariate_evidence",
    "candidate_comparison",
    "marginal_contribution",
    "feature_decisions",
    "rating_benchmark",
    "readiness",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return f


def engineer_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Derive research features from a settled_core dataset row. No targets in features."""
    if not row.get("is_settled_core"):
        return None
    if row.get("settlement_status") not in ("won", "lost", "void"):
        return None
    if not row.get("snapshot_timestamp_verified"):
        return None
    if not row.get("snapshot_before_kickoff"):
        return None
    if not row.get("no_post_match_data_in_features"):
        return None
    if row.get("leakage_status") == "excluded_leakage":
        return None
    if row.get("opposition_status") != OPPOSITION_SUPPORTED:
        return None
    odds = _num(row.get("odds"))
    if odds is None or odds <= 1.0:
        return None

    raw_implied = _num(row.get("raw_book_implied_probability"))
    if raw_implied is None and odds > 0:
        raw_implied = 1.0 / odds
    norm_prob = _num(row.get("normalized_book_probability"))
    family = row.get("canonical_market_family")
    is_dc = family == FAMILY_DOUBLE_CHANCE
    # book_prob: normalized when applicable, else raw
    if is_dc or norm_prob is None:
        book_prob = raw_implied
    else:
        book_prob = norm_prob

    status = row.get("settlement_status")
    is_void = status == "void" or bool(row.get("selection_void"))
    won = bool(row.get("selection_won")) and not is_void
    lost = bool(row.get("selection_lost")) and not is_void
    profit = _num(row.get("unit_stake_profit"))
    if profit is None:
        if is_void:
            profit = 0.0
        elif won:
            profit = odds - 1.0
        elif lost:
            profit = -1.0
        else:
            return None

    y_win: int | None = None if is_void else (1 if won else 0)

    eng: dict[str, Any] = {
        "today_fixture_id": int(row["today_fixture_id"]),
        "canonical_row_key": row.get("canonical_row_key"),
        "raw_market_code": row.get("raw_market_code") or row.get("selection"),
        "selection": row.get("selection") or row.get("raw_market_code"),
        "canonical_market_family": family,
        "scan_date": row.get("scan_date"),
        "snapshot_at": row.get("snapshot_at"),
        "kickoff": row.get("kickoff"),
        "competition_id": row.get("competition_id"),
        "odds": odds,
        "raw_book_implied_probability": raw_implied,
        "normalized_book_probability": None if is_dc else norm_prob,
        "book_prob": book_prob,
        "market_overround": None if is_dc else _num(row.get("market_overround")),
        "model_probability": _num(row.get("model_probability")),
        "probability_advantage": _num(row.get("probability_advantage")),
        "edge": _num(row.get("edge")),
        "score": _num(row.get("score")),
        "rating": _num(row.get("rating")),
        "favourite_alignment": row.get("favourite_alignment") or "unknown",
        "favourite_intensity_book": _num(row.get("favourite_intensity_book")),
        "favourite_intensity_model": _num(row.get("favourite_intensity_model")),
        "book_favourite": row.get("book_favourite"),
        "model_favourite": row.get("model_favourite"),
        "comparator_odds_gap": gap_from_payload(row, "comparator_odds_payload", odds),
        "comparator_model_probability_gap": gap_from_payload(
            row, "comparator_model_probability_payload", _num(row.get("model_probability"))
        ),
        "comparator_book_probability_gap": gap_from_payload(
            row, "comparator_book_probability_payload", raw_implied
        ),
        "complement_odds_gap": None,
        "complement_model_probability_gap": None,
        "complement_book_probability_gap": None,
        "settlement_status": status,
        "selection_void": is_void,
        "y_win": y_win,
        "profit": float(profit),
        "realized_probability_residual": (
            None if y_win is None or raw_implied is None else float(y_win) - float(raw_implied)
        ),
        "normalized_probability_residual": (
            None
            if is_dc or y_win is None or norm_prob is None
            else float(y_win) - float(norm_prob)
        ),
        "is_double_chance": is_dc,
    }

    # complement gaps from first key in comparator that equals complement_selection
    complement = row.get("complement_selection")
    if complement:
        for payload_key, own in (
            ("comparator_odds_payload", odds),
            ("comparator_model_probability_payload", _num(row.get("model_probability"))),
            ("comparator_book_probability_payload", raw_implied),
        ):
            payload = row.get(payload_key) or {}
            if isinstance(payload, dict) and complement in payload:
                try:
                    cv = float(payload[complement])
                    gap_name = {
                        "comparator_odds_payload": "complement_odds_gap",
                        "comparator_model_probability_payload": "complement_model_probability_gap",
                        "comparator_book_probability_payload": "complement_book_probability_gap",
                    }[payload_key]
                    eng[gap_name] = float(own) - cv if own is not None else None
                except (TypeError, ValueError):
                    pass

    return eng


def filter_settled_cohort(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    engineered: list[dict[str, Any]] = []
    key_counts: Counter[str] = Counter()
    for r in rows:
        e = engineer_row(r)
        if e is None:
            continue
        ck = e.get("canonical_row_key") or ""
        key_counts[ck] += 1
        engineered.append(e)

    dup_keys = {k for k, c in key_counts.items() if k and c > 1}
    blocking: list[str] = []
    if dup_keys:
        blocking.append("duplicated_observation_canonical_row_key")
        # exclude all rows with duplicated keys
        engineered = [e for e in engineered if e.get("canonical_row_key") not in dup_keys]

    quality = {
        "settled_core_input_rows": sum(1 for r in rows if r.get("is_settled_core")),
        "engineered_rows": len(engineered),
        "duplicated_observation_keys": sorted(dup_keys)[:50],
        "duplicated_observation_count": len(dup_keys),
        "blocking_issues": blocking,
        "canonical_keys_unique": len(dup_keys) == 0,
    }
    return engineered, quality


def validate_spec_features(feature_names: list[str]) -> list[str]:
    """Return hard redundancy violations."""
    s = set(feature_names)
    issues = []
    if "odds" in s and (
        "raw_book_implied_probability" in s or "raw_implied" in s or "book_prob" in s
    ):
        # book_prob is derived from implied; odds+book_prob also forbidden as deterministic
        if "odds" in s and ("raw_book_implied_probability" in s or "raw_implied" in s):
            issues.append("odds_and_raw_implied_together")
    if "score" in s and "model_probability" in s and "edge" in s:
        issues.append("score_with_model_and_edge")
    if "rating" in s and (
        {"probability_advantage", "edge", "score", "model_probability"} & s
    ):
        # only allowed in RATING_MARGINAL_DIAGNOSTIC — caller checks
        issues.append("rating_with_components")
    return issues


def _fixture_time_key(rows_by_fid: dict[Any, list[dict[str, Any]]], fid: Any) -> tuple:
    rs = rows_by_fid[fid]
    snaps = [parse_iso(r.get("snapshot_at")) for r in rs]
    kicks = [parse_iso(r.get("kickoff")) for r in rs]
    snap = min((s for s in snaps if s), default=None)
    kick = min((k for k in kicks if k), default=None)
    return (snap or datetime.min.replace(tzinfo=timezone.utc), kick or datetime.min.replace(tzinfo=timezone.utc), fid)


def order_fixtures(rows: list[dict[str, Any]]) -> list[Any]:
    by_fid: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_fid[r["today_fixture_id"]].append(r)
    return sorted(by_fid.keys(), key=lambda fid: _fixture_time_key(by_fid, fid))


def _impute_train_means(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    means = np.nanmean(X, axis=0)
    means = np.where(np.isfinite(means), means, 0.0)
    out = X.copy()
    inds = np.where(~np.isfinite(out))
    out[inds] = np.take(means, inds[1])
    return out, means


def _apply_impute(X: np.ndarray, means: np.ndarray) -> np.ndarray:
    out = X.copy()
    inds = np.where(~np.isfinite(out))
    out[inds] = np.take(means, inds[1])
    return out


def _encode_categorical_train(
    values: list[Any],
) -> tuple[np.ndarray, dict[str, int]]:
    uniq = sorted({str(v) for v in values if v is not None})
    mapping = {u: i for i, u in enumerate(uniq)}
    # one-hot without drop
    n = len(values)
    k = max(1, len(mapping))
    mat = np.zeros((n, k), dtype=float)
    for i, v in enumerate(values):
        key = str(v) if v is not None else "__null__"
        if key in mapping:
            mat[i, mapping[key]] = 1.0
    return mat, mapping


def _encode_categorical_apply(values: list[Any], mapping: dict[str, int]) -> np.ndarray:
    n = len(values)
    k = max(1, len(mapping))
    mat = np.zeros((n, k), dtype=float)
    for i, v in enumerate(values):
        key = str(v) if v is not None else "__null__"
        if key in mapping:
            mat[i, mapping[key]] = 1.0
    return mat


def build_matrix(
    rows: list[dict[str, Any]],
    numeric_feats: list[str],
    categorical_feats: list[str],
    *,
    train_state: dict[str, Any] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Build design matrix. If train_state is None, fit; else apply."""
    n = len(rows)
    num = np.full((n, len(numeric_feats)), np.nan, dtype=float)
    for j, f in enumerate(numeric_feats):
        for i, r in enumerate(rows):
            v = _num(r.get(f))
            if v is not None:
                num[i, j] = v

    if train_state is None:
        num_imp, means = _impute_train_means(num)
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        if num_imp.shape[1] > 0 and n > 0:
            num_scaled = scaler.fit_transform(num_imp)
        else:
            num_scaled = num_imp
        cat_parts = []
        cat_maps: dict[str, dict[str, int]] = {}
        for cf in categorical_feats:
            vals = [r.get(cf) for r in rows]
            mat, mapping = _encode_categorical_train(vals)
            cat_parts.append(mat)
            cat_maps[cf] = mapping
        state = {"means": means, "scaler": scaler, "cat_maps": cat_maps, "numeric_feats": numeric_feats}
        if cat_parts:
            X = np.hstack([num_scaled] + cat_parts) if num_scaled.size else np.hstack(cat_parts)
        else:
            X = num_scaled
        return X, state

    means = train_state["means"]
    scaler = train_state["scaler"]
    num_imp = _apply_impute(num, means)
    num_scaled = scaler.transform(num_imp) if num_imp.shape[1] > 0 and n > 0 else num_imp
    cat_parts = []
    for cf in categorical_feats:
        vals = [r.get(cf) for r in rows]
        cat_parts.append(_encode_categorical_apply(vals, train_state["cat_maps"].get(cf, {})))
    if cat_parts:
        X = np.hstack([num_scaled] + cat_parts) if num_scaled.size else np.hstack(cat_parts)
    else:
        X = num_scaled
    return X, train_state


def fit_predict_oof_logistic(
    rows: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    numeric_feats: list[str],
    categorical_feats: list[str] | None = None,
) -> dict[str, Any]:
    """Expanding CV OOF probabilities for classification (void excluded from fit)."""
    categorical_feats = categorical_feats or []
    n = len(rows)
    oof_prob = np.full(n, np.nan)
    fold_reports = []
    row_fid = np.array([r["today_fixture_id"] for r in rows])
    idx_by_fid: dict[Any, list[int]] = defaultdict(list)
    for i, fid in enumerate(row_fid):
        idx_by_fid[int(fid)].append(i)

    from sklearn.linear_model import LogisticRegression

    for fold in folds:
        train_fids = set(fold["train_fixture_ids"])
        test_fids = set(fold["test_fixture_ids"])
        assert train_fids.isdisjoint(test_fids)
        train_idx = [i for i, r in enumerate(rows) if r["today_fixture_id"] in train_fids]
        test_idx = [i for i, r in enumerate(rows) if r["today_fixture_id"] in test_fids]
        # classification: drop void
        train_cls = [i for i in train_idx if rows[i].get("y_win") is not None]
        test_cls = [i for i in test_idx if rows[i].get("y_win") is not None]
        train_rows = [rows[i] for i in train_cls]
        test_rows = [rows[i] for i in test_idx]  # predict all test incl void for ROI
        y_train = np.array([rows[i]["y_win"] for i in train_cls], dtype=float)

        fold_meta = {
            "fold": fold["fold"],
            "train_fixtures": len(train_fids),
            "test_fixtures": len(test_fids),
            "train_rows": len(train_idx),
            "test_rows": len(test_idx),
            "train_classification_rows": len(train_cls),
            "fixture_overlap": len(train_fids & test_fids),
            "class_balance_train": float(np.mean(y_train)) if len(y_train) else None,
            "void_test": sum(1 for i in test_idx if rows[i].get("selection_void")),
        }

        if len(train_cls) < 8 or len(np.unique(y_train)) < 2 or not test_rows:
            fold_meta["skipped"] = True
            fold_reports.append(fold_meta)
            continue

        X_train, state = build_matrix(train_rows, numeric_feats, categorical_feats)
        X_test, _ = build_matrix(test_rows, numeric_feats, categorical_feats, train_state=state)
        model = LogisticRegression(
            C=1.0,
            solver="lbfgs",
            max_iter=500,
        )
        try:
            model.fit(X_train, y_train)
            probs = model.predict_proba(X_test)[:, 1]
        except Exception as exc:  # noqa: BLE001
            fold_meta["skipped"] = True
            fold_meta["error"] = str(exc)[:200]
            fold_reports.append(fold_meta)
            continue

        for j, i in enumerate(test_idx):
            oof_prob[i] = float(probs[j])
        fold_meta["skipped"] = False
        fold_reports.append(fold_meta)

    return {"oof_prob": oof_prob, "fold_reports": fold_reports}


def score_oof_predictions(
    rows: list[dict[str, Any]],
    oof_prob: np.ndarray,
    *,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    mask = np.isfinite(oof_prob)
    if not np.any(mask):
        return {"status": "no_oof", "classification": {}, "economic": {}}

    # classification subset
    cls_idx = [
        i
        for i in range(len(rows))
        if mask[i] and rows[i].get("y_win") is not None
    ]
    y = np.array([rows[i]["y_win"] for i in cls_idx], dtype=float)
    p = oof_prob[cls_idx]
    cal = calibration_slope_intercept(y, p)
    cls = {
        "n": len(cls_idx),
        "auc": roc_auc(y, p),
        "brier": brier(y, p),
        "log_loss": log_loss_score(y, p),
        "accuracy": float(np.mean((p >= 0.5) == y)) if len(y) else None,
        "calibration_intercept": cal["intercept"],
        "calibration_slope": cal["slope"],
        "ece": ece_score(y, p),
    }

    # economic: all OOF rows with profit
    eco_idx = [i for i in range(len(rows)) if mask[i]]
    profits = np.array([rows[i]["profit"] for i in eco_idx], dtype=float)
    won = np.array(
        [0 if rows[i].get("selection_void") else (1 if rows[i].get("y_win") == 1 else 0) for i in eco_idx],
        dtype=float,
    )
    void_mask = np.array([bool(rows[i].get("selection_void")) for i in eco_idx], dtype=bool)
    odds = np.array([rows[i]["odds"] for i in eco_idx], dtype=float)
    scores = oof_prob[eco_idx]
    eco = economic_metrics(profits, won, odds, void_mask=void_mask)
    eco["roi_by_quintile"] = quantile_roi(profits, scores, 5)
    eco["roi_top_10pct"] = top_k_roi(profits, scores, 0.10)
    eco["roi_top_20pct"] = top_k_roi(profits, scores, 0.20)

    fids = np.array([rows[i]["today_fixture_id"] for i in eco_idx])
    boot = fixture_cluster_bootstrap_ci(
        fids, profits, iterations=bootstrap_iterations, seed=seed, agg="mean"
    )
    eco["mean_profit_bootstrap"] = boot

    return {"status": "ok", "classification": cls, "economic": eco, "n_oof": int(np.sum(mask))}


def univariate_feature_analysis(
    rows: list[dict[str, Any]],
    feature: str,
    *,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    vals = []
    profits = []
    ywins = []
    fids = []
    for r in rows:
        v = _num(r.get(feature))
        if v is None:
            continue
        if r.get("y_win") is None and feature:  # still include for ROI with void
            pass
        vals.append(v)
        profits.append(r["profit"])
        ywins.append(r.get("y_win"))
        fids.append(r["today_fixture_id"])
    coverage = safe_div(len(vals), len(rows)) if rows else 0.0
    if len(vals) < 10:
        return {
            "feature": feature,
            "coverage": coverage,
            "n": len(vals),
            "status": "insufficient_sample",
        }
    arr = np.asarray(vals, dtype=float)
    pr = np.asarray(profits, dtype=float)
    # AUC on non-void
    mask_cls = [i for i, y in enumerate(ywins) if y is not None]
    auc = None
    if len(mask_cls) >= 10:
        y = np.array([ywins[i] for i in mask_cls], dtype=float)
        s = arr[mask_cls]
        auc = roc_auc(y, s)
    spearman = spearman_rho(list(arr), list(pr))
    boot = fixture_cluster_bootstrap_ci(
        np.asarray(fids), pr, iterations=bootstrap_iterations, seed=seed
    )
    return {
        "feature": feature,
        "coverage": coverage,
        "n": len(vals),
        "auc_univariate": auc,
        "spearman_profit": spearman,
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "profit_bootstrap": boot,
        "status": "ok",
    }


def classify_marginal(
    delta_auc: float | None,
    fold_signs: list[int],
    market_signs: list[int],
    ci: dict[str, Any] | None,
) -> str:
    if delta_auc is None:
        return "insufficient_sample"
    pos_folds = sum(1 for s in fold_signs if s > 0)
    neg_folds = sum(1 for s in fold_signs if s < 0)
    if fold_signs and pos_folds > 0 and neg_folds > 0 and abs(pos_folds - neg_folds) <= 1:
        return "temporally_unstable"
    if market_signs and sum(1 for s in market_signs if s > 0) == 1 and len(market_signs) >= 3:
        return "market_specific_signal"
    ci_low = (ci or {}).get("ci_low")
    if delta_auc > 0.01 and ci_low is not None and ci_low > 0:
        return "positive_stable_evidence"
    if delta_auc > 0.005:
        return "positive_but_uncertain"
    if abs(delta_auc) < 0.005:
        return "redundant_no_incremental_value"
    if delta_auc < -0.01:
        return "negative_incremental_value"
    return "positive_but_uncertain"


def resolve_spec_features(
    spec_name: str,
    *,
    best_without_rating_feats: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    spec = SPEC_DEFINITIONS[spec_name]
    if spec_name == "RATING_MARGINAL_DIAGNOSTIC":
        base = list(best_without_rating_feats or ["model_probability", "probability_advantage"])
        if "rating" not in base:
            base = base + ["rating"]
        return base, list(spec.get("categoricals") or [])
    return list(spec.get("features") or []), list(spec.get("categoricals") or [])


def run_spec_on_rows(
    rows: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    spec_name: str,
    *,
    bootstrap_iterations: int,
    seed: int,
    best_without_rating_feats: list[str] | None = None,
) -> dict[str, Any]:
    numeric, cats = resolve_spec_features(
        spec_name, best_without_rating_feats=best_without_rating_feats
    )
    # Hard redundancy checks (diagnostic may include rating+components)
    issues = validate_spec_features(numeric)
    if spec_name == "RATING_MARGINAL_DIAGNOSTIC":
        issues = [i for i in issues if i != "rating_with_components"]
    if "odds_and_raw_implied_together" in issues or "score_with_model_and_edge" in issues:
        return {
            "spec": spec_name,
            "status": "invalid_spec",
            "redundancy_issues": issues,
            "features": numeric,
        }

    # Drop features with zero coverage
    usable = []
    for f in numeric:
        if any(_num(r.get(f)) is not None for r in rows):
            usable.append(f)
    if not usable and not cats:
        return {"spec": spec_name, "status": "no_features", "features": numeric}

    oof = fit_predict_oof_logistic(rows, folds, usable, cats)
    metrics = score_oof_predictions(
        rows, oof["oof_prob"], bootstrap_iterations=bootstrap_iterations, seed=seed
    )
    return {
        "spec": spec_name,
        "status": metrics.get("status", "ok"),
        "features": usable,
        "categoricals": cats,
        "redundancy_issues": issues,
        "classification": metrics.get("classification") or {},
        "economic": metrics.get("economic") or {},
        "fold_reports": oof["fold_reports"],
        "n_oof": metrics.get("n_oof"),
        "oof_prob": oof["oof_prob"],  # internal; stripped before JSON
    }


def _strip_oof(result: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in result.items() if k != "oof_prob"}
    return out


def build_cohort_identity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted(str(r.get("canonical_row_key") or "") for r in rows)
    fids = sorted({str(r["today_fixture_id"]) for r in rows})
    targets = sorted(
        f"{r.get('canonical_row_key')}:{r.get('y_win')}:{r.get('profit')}" for r in rows
    )
    dates = [str(r.get("scan_date")) for r in rows if r.get("scan_date")]
    markets = sorted({str(r.get("raw_market_code")) for r in rows})
    return {
        "canonical_row_key_hash": sha256_hex(keys)[:32],
        "fixture_identity_hash": sha256_hex(fids)[:32],
        "target_hash": sha256_hex(targets)[:32],
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "settled_rows": len(rows),
        "unique_fixtures": len(fids),
        "markets": markets,
        "dataset_version": DATASET_VERSION,
        "generated_at": _utc_now_iso(),
    }


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def decide_features(
    univariate: list[dict[str, Any]],
    marginal: list[dict[str, Any]],
    rating_conclusion: str,
) -> list[dict[str, Any]]:
    uni_map = {u["feature"]: u for u in univariate}
    marg_by_feat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in marginal:
        feat = m.get("feature")
        if feat:
            marg_by_feat[feat].append(m)

    feature_catalog = [
        ("odds", "book", ["raw_book_implied_probability"], "benchmark_only"),
        ("raw_book_implied_probability", "book", ["odds"], "benchmark_only"),
        ("normalized_book_probability", "book", ["odds"], "benchmark_only"),
        ("model_probability", "model", [], None),
        ("probability_advantage", "value", ["model_probability", "raw_book_implied_probability"], None),
        ("edge", "value", ["model_probability", "odds"], None),
        ("score", "value", ["model_probability", "edge"], None),
        ("rating", "benchmark", ["model_probability", "probability_advantage", "edge"], "benchmark_only"),
        ("favourite_alignment", "context", [], None),
        ("favourite_intensity_book", "context", [], None),
        ("favourite_intensity_model", "context", [], None),
        ("comparator_odds_gap", "context", [], None),
        ("comparator_model_probability_gap", "context", [], None),
        ("complement_odds_gap", "context", [], None),
        ("complement_model_probability_gap", "context", [], None),
    ]

    decisions = []
    for name, source, deps, forced in feature_catalog:
        u = uni_map.get(name) or uni_map.get("book_prob" if name.startswith("raw") else name) or {}
        mlist = marg_by_feat.get(name) or []
        labels = [m.get("classification") for m in mlist if m.get("classification")]
        decision = forced
        reason = "default_policy"
        if name == "rating":
            decision = (
                "benchmark_only"
                if rating_conclusion in ("benchmark_only", "redundant_exclude", "insufficient_evidence")
                else (
                    "retain_candidate"
                    if rating_conclusion == "incremental_candidate"
                    else (
                        "market_specific_candidate"
                        if rating_conclusion == "market_specific_benchmark"
                        else "benchmark_only"
                    )
                )
            )
            reason = f"rating_conclusion={rating_conclusion}"
        elif forced:
            decision = forced
            reason = "deterministic_book_or_benchmark"
        elif "redundant_no_incremental_value" in labels and not any(
            x == "positive_stable_evidence" for x in labels
        ):
            decision = "redundant_exclude"
            reason = "no_incremental_vs_baselines"
        elif "temporally_unstable" in labels:
            decision = "unstable_exclude"
            reason = "sign_unstable_across_folds"
        elif "market_specific_signal" in labels:
            decision = "market_specific_candidate"
            reason = "effect_concentrated_in_subset_of_markets"
        elif "positive_stable_evidence" in labels:
            decision = "retain_candidate"
            reason = "stable_marginal_gain"
        elif u.get("status") == "insufficient_sample" or not u:
            decision = "insufficient_evidence"
            reason = "low_coverage_or_sample"
        else:
            decision = "insufficient_evidence"
            reason = "effect_uncertain"

        decisions.append(
            {
                "feature_name": name,
                "source": source,
                "deterministic_dependencies": deps,
                "coverage": u.get("coverage"),
                "markets_available": PRIMARY_MARKETS,
                "univariate_effect": {
                    "auc": u.get("auc_univariate"),
                    "spearman_profit": u.get("spearman_profit"),
                },
                "marginal_effect": labels[:5],
                "temporal_stability": "unstable" if "temporally_unstable" in labels else "unknown",
                "market_stability": "market_specific" if "market_specific_signal" in labels else "unknown",
                "leakage_status": "safe",
                "explainability": "high",
                "decision": decision,
                "decision_reason": reason,
            }
        )
    return decisions


def analyze_market(
    market_rows: list[dict[str, Any]],
    market: str,
    *,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    if len(market_rows) < 12:
        return {
            "market": market,
            "status": "insufficient_sample",
            "settled_rows": len(market_rows),
            "unique_fixtures": len({r["today_fixture_id"] for r in market_rows}),
        }

    fixtures = order_fixtures(market_rows)
    folds, fold_lim = expanding_fixture_folds(fixtures)
    # enrich fold date ranges
    temporal_folds = []
    for f in folds:
        tr = [r for r in market_rows if r["today_fixture_id"] in set(f["train_fixture_ids"])]
        te = [r for r in market_rows if r["today_fixture_id"] in set(f["test_fixture_ids"])]
        temporal_folds.append(
            {
                "fold": f["fold"],
                "train_fixture_ids": f["train_fixture_ids"],
                "test_fixture_ids": f["test_fixture_ids"],
                "train_rows": len(tr),
                "test_rows": len(te),
                "train_date_min": min((r.get("scan_date") or "") for r in tr) if tr else None,
                "train_date_max": max((r.get("scan_date") or "") for r in tr) if tr else None,
                "test_date_min": min((r.get("scan_date") or "") for r in te) if te else None,
                "test_date_max": max((r.get("scan_date") or "") for r in te) if te else None,
                "fixture_overlap": 0,
                "markets": [market],
            }
        )

    spec_order = [
        "BOOK_BASELINE",
        "MODEL_BASELINE",
        "RATING_BASELINE",
        "VALUE_ADVANTAGE",
        "VALUE_EDGE",
        "VALUE_SCORE",
        "CONTEXT_ONLY",
        "VALUE_ADVANTAGE_CONTEXT",
        "VALUE_EDGE_CONTEXT",
        "VALUE_SCORE_CONTEXT",
        "RATING_CONTEXT",
    ]
    results: dict[str, dict[str, Any]] = {}
    for spec in spec_order:
        results[spec] = run_spec_on_rows(
            market_rows,
            folds,
            spec,
            bootstrap_iterations=bootstrap_iterations,
            seed=seed,
        )

    # pick best without rating by AUC
    candidates_no_rating = [
        s
        for s in spec_order
        if s not in ("RATING_BASELINE", "RATING_CONTEXT")
        and results[s].get("classification", {}).get("auc") is not None
    ]
    best_no_rating = None
    if candidates_no_rating:
        best_no_rating = max(
            candidates_no_rating,
            key=lambda s: results[s]["classification"].get("auc") or -1.0,
        )
    best_feats = results[best_no_rating]["features"] if best_no_rating else ["model_probability"]

    results["RATING_MARGINAL_DIAGNOSTIC"] = run_spec_on_rows(
        market_rows,
        folds,
        "RATING_MARGINAL_DIAGNOSTIC",
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
        best_without_rating_feats=best_feats,
    )

    book = results["BOOK_BASELINE"]
    model = results["MODEL_BASELINE"]
    rating = results["RATING_BASELINE"]

    marginal = []
    for spec in spec_order + ["RATING_MARGINAL_DIAGNOSTIC"]:
        r = results[spec]
        auc = (r.get("classification") or {}).get("auc")
        for base_name, base in (
            ("BOOK_BASELINE", book),
            ("MODEL_BASELINE", model),
            ("RATING_BASELINE", rating),
        ):
            ba = (base.get("classification") or {}).get("auc")
            d_auc = _delta(auc, ba)
            marginal.append(
                {
                    "market": market,
                    "spec": spec,
                    "vs": base_name,
                    "delta_auc": d_auc,
                    "delta_brier": _delta(
                        (r.get("classification") or {}).get("brier"),
                        (base.get("classification") or {}).get("brier"),
                    ),
                    "delta_log_loss": _delta(
                        (r.get("classification") or {}).get("log_loss"),
                        (base.get("classification") or {}).get("log_loss"),
                    ),
                    "delta_roi": _delta(
                        (r.get("economic") or {}).get("roi"),
                        (base.get("economic") or {}).get("roi"),
                    ),
                    "classification": classify_marginal(
                        d_auc,
                        [],
                        [],
                        (r.get("economic") or {}).get("mean_profit_bootstrap"),
                    ),
                }
            )

    # rating marginal vs best without
    rating_marg = results["RATING_MARGINAL_DIAGNOSTIC"]
    d_rating = _delta(
        (rating_marg.get("classification") or {}).get("auc"),
        (results[best_no_rating].get("classification") or {}).get("auc") if best_no_rating else None,
    )
    if d_rating is None:
        rating_decision = "insufficient_evidence"
    elif d_rating > 0.01:
        rating_decision = "incremental_candidate"
    elif abs(d_rating) < 0.005:
        rating_decision = "redundant_exclude" if best_no_rating else "benchmark_only"
    else:
        rating_decision = "benchmark_only"

    # univariate
    uni_feats = [
        "book_prob",
        "model_probability",
        "probability_advantage",
        "edge",
        "score",
        "rating",
        "favourite_intensity_book",
        "favourite_intensity_model",
        "comparator_odds_gap",
        "comparator_model_probability_gap",
    ]
    univariate = [
        univariate_feature_analysis(
            market_rows, f, bootstrap_iterations=bootstrap_iterations, seed=seed + hash(f) % 1000
        )
        for f in uni_feats
    ]

    won_n = sum(1 for r in market_rows if r.get("y_win") == 1)
    cls_n = sum(1 for r in market_rows if r.get("y_win") is not None)
    profits = [r["profit"] for r in market_rows]
    odds = [r["odds"] for r in market_rows]

    specs_public = {k: _strip_oof(v) for k, v in results.items()}

    return {
        "market": market,
        "status": "ok",
        "settled_rows": len(market_rows),
        "unique_fixtures": len({r["today_fixture_id"] for r in market_rows}),
        "win_rate": safe_div(won_n, cls_n),
        "roi": safe_div(sum(profits), len(profits)) if profits else None,
        "avg_odds": float(np.mean(odds)) if odds else None,
        "avg_break_even": float(np.mean([1.0 / o for o in odds])) if odds else None,
        "limitations": fold_lim,
        "temporal_folds": temporal_folds,
        "candidate_specifications": specs_public,
        "best_spec_without_rating": best_no_rating,
        "best_spec_auc": (
            (results[best_no_rating].get("classification") or {}).get("auc")
            if best_no_rating
            else None
        ),
        "marginal_contribution": marginal,
        "univariate_evidence": univariate,
        "rating_benchmark": {
            "rating_alone_auc": (rating.get("classification") or {}).get("auc"),
            "best_without_rating": best_no_rating,
            "best_without_rating_auc": (
                (results[best_no_rating].get("classification") or {}).get("auc")
                if best_no_rating
                else None
            ),
            "with_rating_auc": (rating_marg.get("classification") or {}).get("auc"),
            "delta_auc_adding_rating": d_rating,
            "decision": rating_decision,
        },
        "baselines": {
            "book": _strip_oof(book),
            "model": _strip_oof(model),
            "rating": _strip_oof(rating),
        },
    }


def analyze_pooled(
    rows: list[dict[str, Any]],
    *,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    if len(rows) < 20:
        return {"status": "insufficient_sample", "settled_rows": len(rows)}
    fixtures = order_fixtures(rows)
    folds, lim = expanding_fixture_folds(fixtures)
    # use VALUE_ADVANTAGE as representative + market one-hot via selection categorical
    numeric = ["model_probability", "probability_advantage"]
    cats = ["raw_market_code"]
    res = run_spec_on_rows(
        [{**r, "raw_market_code": r.get("raw_market_code")} for r in rows],
        folds,
        "VALUE_ADVANTAGE",
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    # override: re-run with market control
    oof = fit_predict_oof_logistic(rows, folds, numeric, cats)
    metrics = score_oof_predictions(
        rows, oof["oof_prob"], bootstrap_iterations=bootstrap_iterations, seed=seed
    )

    # fixture-equal-weighted ROI: mean of per-fixture mean profits
    by_fid: dict[Any, list[float]] = defaultdict(list)
    for r in rows:
        by_fid[r["today_fixture_id"]].append(r["profit"])
    fixture_means = [float(np.mean(v)) for v in by_fid.values()]
    row_roi = safe_div(sum(r["profit"] for r in rows), len(rows))
    fixture_eq_roi = float(np.mean(fixture_means)) if fixture_means else None

    return {
        "status": "ok",
        "settled_rows": len(rows),
        "unique_fixtures": len(by_fid),
        "limitations": lim + ["pooled_is_research_only_not_a_betting_strategy"],
        "row_weighted_roi": row_roi,
        "fixture_equal_weighted_roi": fixture_eq_roi,
        "classification": metrics.get("classification"),
        "economic": metrics.get("economic"),
        "note": "Pooled metrics are research-only; not a multi-selection betting strategy.",
        "spec_probe": _strip_oof(res),
    }


def build_purchasability_statistical_research(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    market_family: str | None = None,
    selection: str | None = None,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_FE,
    seed: int = DEFAULT_SEED,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    t_load0 = time.perf_counter()
    if rows is None:
        raw_rows = build_purchasability_rows(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_family=market_family,
        )
    else:
        raw_rows = rows
    load_ms = (time.perf_counter() - t_load0) * 1000

    t_eng0 = time.perf_counter()
    cohort, quality = filter_settled_cohort(raw_rows)
    if selection:
        cohort = [
            r
            for r in cohort
            if r.get("raw_market_code") == selection or r.get("selection") == selection
        ]
    eng_ms = (time.perf_counter() - t_eng0) * 1000

    identity = build_cohort_identity(cohort)
    limitations: list[str] = list(quality.get("blocking_issues") or [])

    if not cohort:
        payload = {
            "status": "empty_cohort",
            "version": STAT_VERSION,
            "dataset_version": DATASET_VERSION,
            "cohort_identity": identity,
            "data_quality": quality,
            "temporal_folds": [],
            "market_results": [],
            "pooled_results": {},
            "univariate_evidence": [],
            "candidate_specifications": [],
            "marginal_contribution": [],
            "rating_benchmark": {"decision": "insufficient_evidence"},
            "context_feature_evidence": {},
            "stability": {},
            "feature_decisions": [],
            "phase_2b_readiness": {
                "cohort_valid": False,
                "canonical_keys_unique": quality.get("canonical_keys_unique", False),
                "temporal_cv_completed": False,
                "fixture_grouping_verified": False,
                "markets_evaluated": [],
                "features_with_positive_stable_evidence": [],
                "market_specific_features": [],
                "features_redundant": [],
                "features_unstable": [],
                "rating_decision": "insufficient_evidence",
                "limitations": ["empty_settled_core_cohort"],
                "blocking_issues": quality.get("blocking_issues") or ["empty_cohort"],
                "recommended_next_step": "continue_data_collection",
            },
            "limitations": ["empty_settled_core_cohort"],
            "filters": {
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "competition_id": competition_id,
                "market_family": market_family,
                "selection": selection,
                "bootstrap_iterations": bootstrap_iterations,
                "seed": seed,
            },
            "elapsed_ms": {
                "load_dataset": round(load_ms, 2),
                "feature_engineering": round(eng_ms, 2),
                "temporal_cv": 0.0,
                "bootstrap": 0.0,
                "total": round((time.perf_counter() - t0) * 1000, 2),
            },
            "no_db_writes": True,
            "no_purchasability_formula": True,
        }
        return make_json_safe(payload)

    t_cv0 = time.perf_counter()
    market_results = []
    all_marginal = []
    all_uni = []
    rating_decisions = []

    markets = [m for m in PRIMARY_MARKETS]
    for mkt in markets:
        mrows = [r for r in cohort if r.get("raw_market_code") == mkt]
        if not mrows:
            market_results.append(
                {
                    "market": mkt,
                    "status": "no_rows",
                    "settled_rows": 0,
                    "unique_fixtures": 0,
                }
            )
            continue
        mr = analyze_market(
            mrows, mkt, bootstrap_iterations=bootstrap_iterations, seed=seed
        )
        market_results.append(mr)
        all_marginal.extend(mr.get("marginal_contribution") or [])
        all_uni.extend(mr.get("univariate_evidence") or [])
        rb = mr.get("rating_benchmark") or {}
        if rb.get("decision"):
            rating_decisions.append(rb["decision"])
        limitations.extend(mr.get("limitations") or [])

    pooled = analyze_pooled(cohort, bootstrap_iterations=bootstrap_iterations, seed=seed)
    cv_ms = (time.perf_counter() - t_cv0) * 1000

    # aggregate rating decision
    if not rating_decisions:
        rating_conclusion = "insufficient_evidence"
    elif all(d == "redundant_exclude" for d in rating_decisions):
        rating_conclusion = "redundant_exclude"
    elif any(d == "incremental_candidate" for d in rating_decisions) and all(
        d in ("incremental_candidate", "benchmark_only", "insufficient_evidence")
        for d in rating_decisions
    ):
        # only incremental if majority
        if sum(1 for d in rating_decisions if d == "incremental_candidate") >= max(
            1, len(rating_decisions) // 2
        ):
            rating_conclusion = "incremental_candidate"
        else:
            rating_conclusion = "market_specific_benchmark"
    elif any(d == "incremental_candidate" for d in rating_decisions):
        rating_conclusion = "market_specific_benchmark"
    else:
        rating_conclusion = "benchmark_only"

    # collapse univariate by feature name (mean AUC)
    uni_agg: dict[str, dict[str, Any]] = {}
    for u in all_uni:
        f = u.get("feature")
        if not f:
            continue
        if f not in uni_agg:
            uni_agg[f] = dict(u)
        else:
            # keep max n
            if (u.get("n") or 0) > (uni_agg[f].get("n") or 0):
                uni_agg[f] = dict(u)

    feature_decisions = decide_features(
        list(uni_agg.values()), all_marginal, rating_conclusion
    )

    retained = [d["feature_name"] for d in feature_decisions if d["decision"] == "retain_candidate"]
    redundant = [d["feature_name"] for d in feature_decisions if d["decision"] == "redundant_exclude"]
    unstable = [d["feature_name"] for d in feature_decisions if d["decision"] == "unstable_exclude"]
    market_spec = [
        d["feature_name"] for d in feature_decisions if d["decision"] == "market_specific_candidate"
    ]

    # candidate specs summary across markets
    candidate_specs = []
    for spec_name in SPEC_DEFINITIONS:
        aucs = []
        rois = []
        mkts = []
        for mr in market_results:
            cs = (mr.get("candidate_specifications") or {}).get(spec_name) or {}
            auc = (cs.get("classification") or {}).get("auc")
            roi = (cs.get("economic") or {}).get("roi")
            if auc is not None:
                aucs.append(auc)
                mkts.append(mr.get("market"))
            if roi is not None:
                rois.append(roi)
        book_deltas = [
            m["delta_auc"]
            for m in all_marginal
            if m.get("spec") == spec_name and m.get("vs") == "BOOK_BASELINE" and m.get("delta_auc") is not None
        ]
        candidate_specs.append(
            {
                "configuration": spec_name,
                "markets": mkts,
                "auc_mean": float(np.mean(aucs)) if aucs else None,
                "brier_mean": None,
                "roi_mean": float(np.mean(rois)) if rois else None,
                "delta_vs_book_mean": float(np.mean(book_deltas)) if book_deltas else None,
                "stability": "unknown",
                "status": "ok" if aucs else "insufficient",
            }
        )

    # temporal folds from first market with folds
    temporal_folds = []
    for mr in market_results:
        if mr.get("temporal_folds"):
            temporal_folds = mr["temporal_folds"]
            break

    markets_ok = [
        mr["market"]
        for mr in market_results
        if mr.get("status") == "ok"
    ]
    blocking = list(quality.get("blocking_issues") or [])
    cohort_valid = len(cohort) > 0 and not blocking
    temporal_done = any(
        (mr.get("temporal_folds") or []) for mr in market_results if mr.get("status") == "ok"
    )
    fixture_ok = all(
        all(tf.get("fixture_overlap", 0) == 0 for tf in (mr.get("temporal_folds") or []))
        for mr in market_results
        if mr.get("status") == "ok"
    )

    if blocking:
        next_step = "resolve_data_quality"
    elif not temporal_done or "limited_temporal_span" in limitations:
        next_step = "continue_data_collection"
    elif retained:
        next_step = "phase_2b_candidate_construction"
    else:
        next_step = "stop_no_incremental_signal"

    readiness = {
        "cohort_valid": cohort_valid,
        "canonical_keys_unique": bool(quality.get("canonical_keys_unique")),
        "temporal_cv_completed": temporal_done,
        "fixture_grouping_verified": fixture_ok,
        "markets_evaluated": markets_ok,
        "features_with_positive_stable_evidence": retained,
        "market_specific_features": market_spec,
        "features_redundant": redundant,
        "features_unstable": unstable,
        "rating_decision": rating_conclusion,
        "limitations": sorted(set(limitations)),
        "blocking_issues": blocking,
        "recommended_next_step": next_step,
    }

    rating_benchmark = {
        "conclusion": rating_conclusion,
        "per_market": [
            {
                "market": mr.get("market"),
                **(mr.get("rating_benchmark") or {}),
            }
            for mr in market_results
            if mr.get("status") == "ok"
        ],
        "note": "Rating remains benchmark_candidate unless incremental OOF evidence is stable.",
    }

    total_ms = (time.perf_counter() - t0) * 1000
    payload = {
        "status": "ok",
        "version": STAT_VERSION,
        "dataset_version": DATASET_VERSION,
        "cohort_identity": identity,
        "data_quality": quality,
        "temporal_folds": temporal_folds,
        "market_results": [
            {k: v for k, v in mr.items() if k != "candidate_specifications" or True}
            for mr in market_results
        ],
        "pooled_results": pooled,
        "univariate_evidence": list(uni_agg.values()),
        "candidate_specifications": candidate_specs,
        "marginal_contribution": all_marginal,
        "rating_benchmark": rating_benchmark,
        "context_feature_evidence": {
            "features": [
                "favourite_alignment",
                "favourite_intensity_book",
                "favourite_intensity_model",
                "comparator_odds_gap",
                "comparator_model_probability_gap",
                "complement_odds_gap",
            ],
            "note": "Gaps derived only from pre-match comparator/complement payloads.",
        },
        "stability": {
            "limited_temporal_span": "limited_temporal_span" in limitations,
            "markets_with_ok_status": markets_ok,
        },
        "feature_decisions": feature_decisions,
        "phase_2b_readiness": readiness,
        "limitations": sorted(set(limitations)),
        "filters": {
            "date_from": str(date_from) if date_from else None,
            "date_to": str(date_to) if date_to else None,
            "competition_id": competition_id,
            "market_family": market_family,
            "selection": selection,
            "bootstrap_iterations": bootstrap_iterations,
            "seed": seed,
        },
        "elapsed_ms": {
            "load_dataset": round(load_ms, 2),
            "feature_engineering": round(eng_ms, 2),
            "temporal_cv": round(cv_ms, 2),
            "bootstrap": bootstrap_iterations,
            "total": round(total_ms, 2),
        },
        "no_db_writes": True,
        "no_purchasability_formula": True,
        "research_banner": (
            "Fase di ricerca statistica. Nessun Indice di Acquistabilità produttivo. "
            "Nessuna influenza sui Segnali Cecchino."
        ),
    }
    return make_json_safe(payload)


def build_statistical_markets_payload(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    bootstrap_iterations: int = 50,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    full = build_purchasability_statistical_research(
        db,
        date_from=date_from,
        date_to=date_to,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    return make_json_safe(
        {
            "version": STAT_VERSION,
            "markets": full.get("market_results") or [],
            "phase_2b_readiness": full.get("phase_2b_readiness"),
        }
    )


def build_statistical_features_payload(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    bootstrap_iterations: int = 50,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    full = build_purchasability_statistical_research(
        db,
        date_from=date_from,
        date_to=date_to,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    return make_json_safe(
        {
            "version": STAT_VERSION,
            "feature_decisions": full.get("feature_decisions") or [],
            "univariate_evidence": full.get("univariate_evidence") or [],
            "marginal_contribution": full.get("marginal_contribution") or [],
        }
    )


def build_statistical_candidates_payload(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    bootstrap_iterations: int = 50,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    full = build_purchasability_statistical_research(
        db,
        date_from=date_from,
        date_to=date_to,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    return make_json_safe(
        {
            "version": STAT_VERSION,
            "candidate_specifications": full.get("candidate_specifications") or [],
            "rating_benchmark": full.get("rating_benchmark") or {},
        }
    )


def _csv_from_dicts(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    # flatten simple keys
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys and not isinstance(r[k], (dict, list)):
                keys.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k) for k in keys})
    return buf.getvalue()


def stream_statistical_export(
    db: Session,
    kind: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    market_family: str | None = None,
    selection: str | None = None,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_FE,
    seed: int = DEFAULT_SEED,
) -> Iterator[str]:
    if kind not in EXPORT_KINDS:
        yield json.dumps({"status": "error", "error": "unknown_export_kind", "kind": kind})
        return

    full = build_purchasability_statistical_research(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        selection=selection,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )

    json_kinds = {
        "summary": lambda: {
            "version": full.get("version"),
            "dataset_version": full.get("dataset_version"),
            "cohort_identity": full.get("cohort_identity"),
            "phase_2b_readiness": full.get("phase_2b_readiness"),
            "limitations": full.get("limitations"),
            "elapsed_ms": full.get("elapsed_ms"),
            "status": full.get("status"),
        },
        "cohort_identity": lambda: full.get("cohort_identity") or {},
        "rating_benchmark": lambda: full.get("rating_benchmark") or {},
        "readiness": lambda: full.get("phase_2b_readiness") or {},
    }
    csv_kinds = {
        "temporal_folds": lambda: full.get("temporal_folds") or [],
        "market_results": lambda: [
            {
                "market": m.get("market"),
                "status": m.get("status"),
                "settled_rows": m.get("settled_rows"),
                "unique_fixtures": m.get("unique_fixtures"),
                "win_rate": m.get("win_rate"),
                "roi": m.get("roi"),
                "avg_odds": m.get("avg_odds"),
                "best_spec_without_rating": m.get("best_spec_without_rating"),
                "best_spec_auc": m.get("best_spec_auc"),
            }
            for m in (full.get("market_results") or [])
        ],
        "univariate_evidence": lambda: full.get("univariate_evidence") or [],
        "candidate_comparison": lambda: full.get("candidate_specifications") or [],
        "marginal_contribution": lambda: full.get("marginal_contribution") or [],
        "feature_decisions": lambda: full.get("feature_decisions") or [],
    }

    if kind in json_kinds:
        payload = make_json_safe(json_kinds[kind]())
        yield json.dumps(payload, allow_nan=False, indent=2)
        return

    rows = make_json_safe(csv_kinds[kind]())
    assert isinstance(rows, list)
    yield _csv_from_dicts(rows)


def statistical_export_filename(kind: str) -> str:
    mapping = {
        "summary": "purchasability_phase2a_summary.json",
        "cohort_identity": "purchasability_phase2a_cohort_identity.json",
        "temporal_folds": "purchasability_phase2a_temporal_folds.csv",
        "market_results": "purchasability_phase2a_market_results.csv",
        "univariate_evidence": "purchasability_phase2a_univariate_evidence.csv",
        "candidate_comparison": "purchasability_phase2a_candidate_comparison.csv",
        "marginal_contribution": "purchasability_phase2a_marginal_contribution.csv",
        "feature_decisions": "purchasability_phase2a_feature_decisions.csv",
        "rating_benchmark": "purchasability_phase2a_rating_benchmark.json",
        "readiness": "purchasability_phase2a_readiness.json",
    }
    return mapping.get(kind, f"purchasability_phase2a_{kind}.txt")
