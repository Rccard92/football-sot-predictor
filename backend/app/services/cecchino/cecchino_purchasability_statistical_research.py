"""Indice di Acquistabilità — Fase 2A.1 ricerca statistica (read-only).

Versione: cecchino_purchasability_statistical_research_v2a_1
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
    DELTA_AUC_NEGATIVE,
    DELTA_AUC_STABLE,
    DELTA_AUC_UNCERTAIN,
    FOLD_NEUTRAL_ABS,
    MARKET_NEUTRAL_ABS,
    brier,
    calibration_slope_intercept,
    ece_score,
    economic_metrics,
    expanding_fixture_folds,
    fixture_cluster_bootstrap_ci,
    gap_from_payload,
    log_loss_score,
    paired_oof_comparison,
    parse_iso,
    quantile_roi,
    ranking_economic_from_scores,
    roc_auc,
    safe_div,
    sha256_hex,
    spearman_rho,
    stable_seed,
    top_k_roi,
)

STAT_VERSION = "cecchino_purchasability_statistical_research_v2a_1"

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
    # Prespecified Rating diagnostics (no OOF selection of base spec)
    "VALUE_ADVANTAGE_PLUS_RATING": {
        "features": ["model_probability", "probability_advantage", "rating"],
        "role": "rating_diagnostic",
        "allows_rating": True,
        "diagnostic": True,
        "compare_to": "VALUE_ADVANTAGE",
    },
    "VALUE_EDGE_PLUS_RATING": {
        "features": ["model_probability", "edge", "rating"],
        "role": "rating_diagnostic",
        "allows_rating": True,
        "diagnostic": True,
        "compare_to": "VALUE_EDGE",
    },
    "VALUE_SCORE_PLUS_RATING": {
        "features": ["score", "rating"],
        "role": "rating_diagnostic",
        "allows_rating": True,
        "diagnostic": True,
        "compare_to": "VALUE_SCORE",
    },
    "VALUE_ADVANTAGE_CONTEXT_PLUS_RATING": {
        "features": [
            "model_probability",
            "probability_advantage",
            "favourite_intensity_book",
            "favourite_intensity_model",
            "comparator_odds_gap",
            "comparator_model_probability_gap",
            "rating",
        ],
        "categoricals": ["favourite_alignment"],
        "role": "rating_diagnostic",
        "allows_rating": True,
        "diagnostic": True,
        "compare_to": "VALUE_ADVANTAGE_CONTEXT",
    },
    "VALUE_EDGE_CONTEXT_PLUS_RATING": {
        "features": [
            "model_probability",
            "edge",
            "favourite_intensity_book",
            "favourite_intensity_model",
            "comparator_odds_gap",
            "comparator_model_probability_gap",
            "rating",
        ],
        "categoricals": ["favourite_alignment"],
        "role": "rating_diagnostic",
        "allows_rating": True,
        "diagnostic": True,
        "compare_to": "VALUE_EDGE_CONTEXT",
    },
    "VALUE_SCORE_CONTEXT_PLUS_RATING": {
        "features": [
            "score",
            "favourite_intensity_book",
            "favourite_intensity_model",
            "comparator_odds_gap",
            "comparator_model_probability_gap",
            "rating",
        ],
        "categoricals": ["favourite_alignment"],
        "role": "rating_diagnostic",
        "allows_rating": True,
        "diagnostic": True,
        "compare_to": "VALUE_SCORE_CONTEXT",
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
    ranking = ranking_economic_from_scores(profits, scores)
    eco.update(ranking)
    # Explicit alias for clarity in payloads
    eco["cohort_full_coverage_roi"] = eco.get("cohort_full_coverage_roi")

    fids = np.array([rows[i]["today_fixture_id"] for i in eco_idx])
    boot = fixture_cluster_bootstrap_ci(
        fids, profits, iterations=bootstrap_iterations, seed=seed, agg="mean"
    )
    eco["mean_profit_bootstrap"] = boot

    return {"status": "ok", "classification": cls, "economic": eco, "n_oof": int(np.sum(mask))}


def fold_delta_auc_signs(
    rows: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    pred_cand: np.ndarray,
    pred_base: np.ndarray,
) -> dict[str, Any]:
    """Per-fold paired delta AUC on test fixtures (real fold_signs)."""
    fold_deltas: list[dict[str, Any]] = []
    signs: list[int] = []
    for fold in folds:
        test_fids = set(fold["test_fixture_ids"])
        idx = [
            i
            for i, r in enumerate(rows)
            if r["today_fixture_id"] in test_fids
            and np.isfinite(pred_cand[i])
            and np.isfinite(pred_base[i])
            and r.get("y_win") is not None
        ]
        if len(idx) < 4:
            fold_deltas.append({"fold": fold["fold"], "delta_auc": None, "skipped": True})
            continue
        y = np.array([rows[i]["y_win"] for i in idx], dtype=float)
        if len(np.unique(y)) < 2:
            fold_deltas.append({"fold": fold["fold"], "delta_auc": None, "skipped": True})
            continue
        ac = roc_auc(y, pred_cand[idx])
        ab = roc_auc(y, pred_base[idx])
        if ac is None or ab is None:
            fold_deltas.append({"fold": fold["fold"], "delta_auc": None, "skipped": True})
            continue
        d = float(ac - ab)
        if abs(d) < FOLD_NEUTRAL_ABS:
            sign = 0
        else:
            sign = 1 if d > 0 else -1
        signs.append(sign)
        fold_deltas.append({"fold": fold["fold"], "delta_auc": d, "sign": sign, "skipped": False})

    pos = sum(1 for s in signs if s > 0)
    neg = sum(1 for s in signs if s < 0)
    neu = sum(1 for s in signs if s == 0)
    consistency = None
    if signs:
        consistency = max(pos, neg, neu) / len(signs)
    deltas_only = [f["delta_auc"] for f in fold_deltas if f.get("delta_auc") is not None]
    effect_range = None
    if deltas_only:
        effect_range = float(max(deltas_only) - min(deltas_only))
    return {
        "fold_deltas": fold_deltas,
        "fold_signs": signs,
        "positive_folds": pos,
        "negative_folds": neg,
        "neutral_folds": neu,
        "fold_sign_consistency": consistency,
        "fold_effect_range": effect_range,
    }


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
    market_signs: list[int] | None,
    ci: dict[str, Any] | None,
    *,
    cross_market_label: str | None = None,
) -> str:
    """
    Temporal classification from real fold signs + paired CI.

    Thresholds (descriptive):
    - DELTA_AUC_STABLE = 0.01, DELTA_AUC_UNCERTAIN = 0.005, DELTA_AUC_NEGATIVE = -0.01
    - FOLD_NEUTRAL_ABS = 0.002
    market_signs are ignored here when cross_market_label is provided from Pass 2.
    """
    if cross_market_label == "market_specific_signal":
        return "market_specific_signal"
    if delta_auc is None:
        return "insufficient_sample"
    pos_folds = sum(1 for s in fold_signs if s > 0)
    neg_folds = sum(1 for s in fold_signs if s < 0)
    n_signed = pos_folds + neg_folds
    if fold_signs and n_signed >= 2 and pos_folds > 0 and neg_folds > 0 and abs(pos_folds - neg_folds) <= 1:
        return "temporally_unstable"
    ci_low = (ci or {}).get("ci_low")
    ci_high = (ci or {}).get("ci_high")
    majority_pos = (not fold_signs) or (pos_folds > neg_folds)
    if (
        delta_auc > DELTA_AUC_STABLE
        and ci_low is not None
        and ci_low > 0
        and majority_pos
    ):
        return "positive_stable_evidence"
    if delta_auc > DELTA_AUC_UNCERTAIN and (ci_low is None or ci_low <= 0):
        return "positive_but_uncertain"
    if delta_auc > DELTA_AUC_UNCERTAIN and majority_pos:
        return "positive_but_uncertain"
    if abs(delta_auc) < DELTA_AUC_UNCERTAIN and (
        ci_high is None or (ci_low is not None and ci_low <= 0 <= (ci_high or 0))
    ):
        return "redundant_no_incremental_value"
    if delta_auc < DELTA_AUC_NEGATIVE:
        return "negative_incremental_value"
    if abs(delta_auc) < DELTA_AUC_UNCERTAIN:
        return "redundant_no_incremental_value"
    return "positive_but_uncertain"


def classify_cross_market(market_deltas: list[float]) -> dict[str, Any]:
    signs = []
    for d in market_deltas:
        if abs(d) < MARKET_NEUTRAL_ABS:
            signs.append(0)
        else:
            signs.append(1 if d > 0 else -1)
    pos = sum(1 for s in signs if s > 0)
    neg = sum(1 for s in signs if s < 0)
    neu = sum(1 for s in signs if s == 0)
    if len(market_deltas) < 2:
        label = "insufficient_markets"
    elif pos >= 2 and neg == 0:
        label = "cross_market_stable"
    elif pos == 1 and len(market_deltas) >= 2 and neg <= 1:
        label = "market_specific_signal"
    elif pos > 0 and neg > 0 and abs(pos - neg) <= 1:
        label = "cross_market_unstable"
    elif pos >= 2 and neg > 0:
        label = "cross_market_unstable"
    else:
        label = "insufficient_markets"
    dispersion = None
    if market_deltas:
        dispersion = float(np.std(market_deltas))
    consistency = max(pos, neg, neu) / len(signs) if signs else None
    return {
        "market_deltas": market_deltas,
        "markets_positive": pos,
        "markets_negative": neg,
        "markets_neutral": neu,
        "market_sign_consistency": consistency,
        "market_effect_dispersion": dispersion,
        "market_stability": label,
    }


def resolve_spec_features(
    spec_name: str,
    *,
    best_without_rating_feats: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    del best_without_rating_feats  # no longer used (selection optimism removed)
    spec = SPEC_DEFINITIONS[spec_name]
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
    del best_without_rating_feats
    numeric, cats = resolve_spec_features(spec_name)
    issues = validate_spec_features(numeric)
    # Rating+components allowed only on explicit diagnostic specs
    if SPEC_DEFINITIONS.get(spec_name, {}).get("diagnostic"):
        issues = [i for i in issues if i != "rating_with_components"]
    if "odds_and_raw_implied_together" in issues or "score_with_model_and_edge" in issues:
        return {
            "spec": spec_name,
            "status": "invalid_spec",
            "redundancy_issues": issues,
            "features": numeric,
        }

    usable = []
    for f in numeric:
        if any(_num(r.get(f)) is not None for r in rows):
            usable.append(f)
    if not usable and not cats:
        return {"spec": spec_name, "status": "no_features", "features": numeric}

    oof = fit_predict_oof_logistic(rows, folds, usable, cats)
    metrics = score_oof_predictions(
        rows,
        oof["oof_prob"],
        bootstrap_iterations=bootstrap_iterations,
        seed=stable_seed(seed, f"score:{spec_name}"),
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
        "oof_prob": oof["oof_prob"],
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


CORE_SPECS = (
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
)

RATING_DIAGNOSTIC_SPECS = (
    "VALUE_ADVANTAGE_PLUS_RATING",
    "VALUE_EDGE_PLUS_RATING",
    "VALUE_SCORE_PLUS_RATING",
    "VALUE_ADVANTAGE_CONTEXT_PLUS_RATING",
    "VALUE_EDGE_CONTEXT_PLUS_RATING",
    "VALUE_SCORE_CONTEXT_PLUS_RATING",
)

# Prespecified Rating paired comparisons (candidate, baseline)
RATING_PAIRED_COMPARISONS: tuple[tuple[str, str], ...] = (
    ("RATING_BASELINE", "BOOK_BASELINE"),
    ("RATING_BASELINE", "MODEL_BASELINE"),
    ("RATING_CONTEXT", "CONTEXT_ONLY"),
    ("VALUE_ADVANTAGE_PLUS_RATING", "VALUE_ADVANTAGE"),
    ("VALUE_EDGE_PLUS_RATING", "VALUE_EDGE"),
    ("VALUE_SCORE_PLUS_RATING", "VALUE_SCORE"),
    ("VALUE_ADVANTAGE_CONTEXT_PLUS_RATING", "VALUE_ADVANTAGE_CONTEXT"),
    ("VALUE_EDGE_CONTEXT_PLUS_RATING", "VALUE_EDGE_CONTEXT"),
    ("VALUE_SCORE_CONTEXT_PLUS_RATING", "VALUE_SCORE_CONTEXT"),
)


def _build_paired_entry(
    *,
    market: str,
    spec: str,
    vs: str,
    rows: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    pred_cand: np.ndarray,
    pred_base: np.ndarray,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    paired = paired_oof_comparison(
        rows,
        pred_cand,
        pred_base,
        bootstrap_iterations=bootstrap_iterations,
        seed=stable_seed(seed, f"paired:{market}:{spec}:vs:{vs}"),
    )
    fold_info = fold_delta_auc_signs(rows, folds, pred_cand, pred_base)
    ci_auc = (paired.get("confidence_intervals") or {}).get("delta_auc") or {}
    # Pass 1: temporal only (no market_signs)
    temporal_class = classify_marginal(
        paired.get("delta_auc"),
        fold_info.get("fold_signs") or [],
        None,
        ci_auc,
    )
    return {
        "market": market,
        "spec": spec,
        "vs": vs,
        "delta_auc": paired.get("delta_auc"),
        "delta_brier_improvement": paired.get("delta_brier_improvement"),
        "delta_log_loss_improvement": paired.get("delta_log_loss_improvement"),
        "delta_ece_improvement": paired.get("delta_ece_improvement"),
        "delta_roi_top_10pct": paired.get("delta_roi_top_10pct"),
        "delta_roi_top_20pct": paired.get("delta_roi_top_20pct"),
        "delta_roi_top_quintile": paired.get("delta_roi_top_quintile"),
        "delta_top_bottom_roi_spread": paired.get("delta_top_bottom_roi_spread"),
        "confidence_intervals": paired.get("confidence_intervals"),
        "fold_deltas": fold_info.get("fold_deltas"),
        "fold_signs": fold_info.get("fold_signs"),
        "positive_folds": fold_info.get("positive_folds"),
        "negative_folds": fold_info.get("negative_folds"),
        "neutral_folds": fold_info.get("neutral_folds"),
        "fold_sign_consistency": fold_info.get("fold_sign_consistency"),
        "fold_effect_range": fold_info.get("fold_effect_range"),
        "temporal_classification": temporal_class,
        "classification": temporal_class,  # updated in Pass 2
        "n_paired": paired.get("n_paired"),
    }


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

    all_specs = list(CORE_SPECS) + list(RATING_DIAGNOSTIC_SPECS)
    results: dict[str, dict[str, Any]] = {}
    for spec in all_specs:
        results[spec] = run_spec_on_rows(
            market_rows,
            folds,
            spec,
            bootstrap_iterations=bootstrap_iterations,
            seed=seed,
        )

    book = results["BOOK_BASELINE"]
    model = results["MODEL_BASELINE"]
    rating = results["RATING_BASELINE"]

    # Pass 1 paired comparisons (unclassified globally)
    marginal: list[dict[str, Any]] = []
    compare_specs = [
        s
        for s in CORE_SPECS
        if s not in ("BOOK_BASELINE",)
    ]
    for spec in compare_specs:
        r = results[spec]
        if "oof_prob" not in r:
            continue
        for base_name, base in (
            ("BOOK_BASELINE", book),
            ("MODEL_BASELINE", model),
            ("RATING_BASELINE", rating),
        ):
            if spec == base_name:
                continue
            if "oof_prob" not in base:
                continue
            marginal.append(
                _build_paired_entry(
                    market=market,
                    spec=spec,
                    vs=base_name,
                    rows=market_rows,
                    folds=folds,
                    pred_cand=r["oof_prob"],
                    pred_base=base["oof_prob"],
                    bootstrap_iterations=bootstrap_iterations,
                    seed=seed,
                )
            )

    rating_comparisons = []
    for cand_name, base_name in RATING_PAIRED_COMPARISONS:
        cand = results.get(cand_name) or {}
        base = results.get(base_name) or {}
        if "oof_prob" not in cand or "oof_prob" not in base:
            continue
        entry = _build_paired_entry(
            market=market,
            spec=cand_name,
            vs=base_name,
            rows=market_rows,
            folds=folds,
            pred_cand=cand["oof_prob"],
            pred_base=base["oof_prob"],
            bootstrap_iterations=bootstrap_iterations,
            seed=seed,
        )
        rating_comparisons.append(entry)
        marginal.append(entry)

    # Rating decision from prespecified pairs (no best-spec selection)
    rating_decision = _decide_rating_from_pairs(rating_comparisons)

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
            market_rows,
            f,
            bootstrap_iterations=bootstrap_iterations,
            seed=stable_seed(seed, f"uni:{f}"),
        )
        for f in uni_feats
    ]

    won_n = sum(1 for r in market_rows if r.get("y_win") == 1)
    cls_n = sum(1 for r in market_rows if r.get("y_win") is not None)
    profits = [r["profit"] for r in market_rows]
    odds_l = [r["odds"] for r in market_rows]

    # Pick display "best" for market table without using it for Rating add-on
    display_best = None
    display_auc = None
    for s in CORE_SPECS:
        if s.startswith("RATING"):
            continue
        auc = (results[s].get("classification") or {}).get("auc")
        if auc is None:
            continue
        if display_auc is None or auc > display_auc:
            display_auc = auc
            display_best = s

    specs_public = {k: _strip_oof(v) for k, v in results.items()}

    return {
        "market": market,
        "status": "ok",
        "settled_rows": len(market_rows),
        "unique_fixtures": len({r["today_fixture_id"] for r in market_rows}),
        "win_rate": safe_div(won_n, cls_n),
        "cohort_full_coverage_roi": safe_div(sum(profits), len(profits)) if profits else None,
        "roi": safe_div(sum(profits), len(profits)) if profits else None,
        "avg_odds": float(np.mean(odds_l)) if odds_l else None,
        "avg_break_even": float(np.mean([1.0 / o for o in odds_l])) if odds_l else None,
        "limitations": fold_lim,
        "temporal_folds": temporal_folds,
        "candidate_specifications": specs_public,
        "best_spec_without_rating": display_best,
        "best_spec_auc": display_auc,
        "marginal_contribution": marginal,
        "rating_prespecified_comparisons": rating_comparisons,
        "univariate_evidence": univariate,
        "rating_benchmark": {
            "rating_alone_auc": (rating.get("classification") or {}).get("auc"),
            "prespecified_comparisons": [
                {
                    "spec": c["spec"],
                    "vs": c["vs"],
                    "delta_auc": c.get("delta_auc"),
                    "ci": (c.get("confidence_intervals") or {}).get("delta_auc"),
                    "temporal_classification": c.get("temporal_classification"),
                }
                for c in rating_comparisons
            ],
            "decision": rating_decision,
            "note": "Rating pairs are prespecified; no OOF best-spec selection.",
        },
        "baselines": {
            "book": _strip_oof(book),
            "model": _strip_oof(model),
            "rating": _strip_oof(rating),
        },
    }


def _decide_rating_from_pairs(pairs: list[dict[str, Any]]) -> str:
    if not pairs:
        return "insufficient_evidence"
    deltas = [p.get("delta_auc") for p in pairs if p.get("delta_auc") is not None]
    if not deltas:
        return "insufficient_evidence"
    pos = sum(1 for d in deltas if d > DELTA_AUC_UNCERTAIN)
    neg = sum(1 for d in deltas if d < -DELTA_AUC_UNCERTAIN)
    unstable = sum(1 for p in pairs if p.get("temporal_classification") == "temporally_unstable")
    if unstable >= max(1, len(pairs) // 2):
        return "temporally_unstable"
    ci_pos = 0
    for p in pairs:
        ci = (p.get("confidence_intervals") or {}).get("delta_auc") or {}
        if (p.get("delta_auc") or 0) > DELTA_AUC_STABLE and (ci.get("ci_low") or -1) > 0:
            ci_pos += 1
    if ci_pos >= 2 and pos >= 2:
        return "incremental_candidate"
    if pos == 1 and len(deltas) >= 3:
        return "market_specific_benchmark"
    if all(abs(d) < DELTA_AUC_UNCERTAIN for d in deltas):
        return "redundant_exclude"
    if neg > pos:
        return "benchmark_only"
    return "benchmark_only"

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
        limitations.extend(mr.get("limitations") or [])

    pooled = analyze_pooled(cohort, bootstrap_iterations=bootstrap_iterations, seed=seed)
    cv_ms = (time.perf_counter() - t_cv0) * 1000

    # --- Pass 2: cross-market stability on identical (spec, vs) pairs ---
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for m in all_marginal:
        key = (str(m.get("spec")), str(m.get("vs")))
        by_key[key].append(m)

    cross_market_meta: dict[tuple[str, str], dict[str, Any]] = {}
    for key, items in by_key.items():
        deltas = [float(i["delta_auc"]) for i in items if i.get("delta_auc") is not None]
        meta = classify_cross_market(deltas)
        cross_market_meta[key] = meta
        for i in items:
            cm_label = meta["market_stability"]
            i["market_stability"] = cm_label
            i["markets_positive"] = meta["markets_positive"]
            i["markets_negative"] = meta["markets_negative"]
            i["markets_neutral"] = meta["markets_neutral"]
            i["market_sign_consistency"] = meta["market_sign_consistency"]
            i["market_effect_dispersion"] = meta["market_effect_dispersion"]
            i["classification"] = classify_marginal(
                i.get("delta_auc"),
                i.get("fold_signs") or [],
                None,
                (i.get("confidence_intervals") or {}).get("delta_auc"),
                cross_market_label=cm_label if cm_label == "market_specific_signal" else None,
            )
            if cm_label == "cross_market_unstable" and i["classification"] == "positive_stable_evidence":
                i["classification"] = "positive_but_uncertain"
            if cm_label == "cross_market_stable" and i.get("temporal_classification") == "positive_but_uncertain":
                ci = (i.get("confidence_intervals") or {}).get("delta_auc") or {}
                if (i.get("delta_auc") or 0) > DELTA_AUC_STABLE and (ci.get("ci_low") or -1) > 0:
                    i["classification"] = "positive_stable_evidence"

    rating_decisions = [
        (mr.get("rating_benchmark") or {}).get("decision")
        for mr in market_results
        if mr.get("status") == "ok" and (mr.get("rating_benchmark") or {}).get("decision")
    ]
    if not rating_decisions:
        rating_conclusion = "insufficient_evidence"
    elif all(d == "redundant_exclude" for d in rating_decisions):
        rating_conclusion = "redundant_exclude"
    elif all(d == "temporally_unstable" for d in rating_decisions):
        rating_conclusion = "temporally_unstable"
    elif sum(1 for d in rating_decisions if d == "incremental_candidate") >= max(
        1, len(rating_decisions) // 2
    ):
        rating_conclusion = "incremental_candidate"
    elif any(d == "incremental_candidate" for d in rating_decisions):
        rating_conclusion = "market_specific_benchmark"
    elif any(d == "market_specific_benchmark" for d in rating_decisions):
        rating_conclusion = "market_specific_benchmark"
    else:
        rating_conclusion = "benchmark_only"

    uni_agg: dict[str, dict[str, Any]] = {}
    for u in all_uni:
        f = u.get("feature")
        if not f:
            continue
        if f not in uni_agg or (u.get("n") or 0) > (uni_agg[f].get("n") or 0):
            uni_agg[f] = dict(u)

    feature_decisions = decide_features(
        list(uni_agg.values()), all_marginal, rating_conclusion
    )
    for d in feature_decisions:
        related = [
            m
            for m in all_marginal
            if (
                d["feature_name"] == "rating"
                and "RATING" in str(m.get("spec") or "")
            )
            or (
                d["feature_name"] == "probability_advantage"
                and "ADVANTAGE" in str(m.get("spec") or "")
            )
            or (
                d["feature_name"] == "edge" and "EDGE" in str(m.get("spec") or "")
            )
            or (
                d["feature_name"] == "score" and "SCORE" in str(m.get("spec") or "")
            )
            or (
                d["feature_name"] == "model_probability"
                and m.get("spec") in ("MODEL_BASELINE", "VALUE_ADVANTAGE", "VALUE_EDGE")
            )
        ]
        labels = [m.get("classification") for m in related if m.get("classification")]
        mstab = [m.get("market_stability") for m in related if m.get("market_stability")]
        if "market_specific_signal" in mstab:
            d["market_stability"] = "market_specific_signal"
            if d["decision"] not in ("benchmark_only", "redundant_exclude"):
                d["decision"] = "market_specific_candidate"
        elif "cross_market_stable" in mstab:
            d["market_stability"] = "cross_market_stable"
        elif "cross_market_unstable" in mstab:
            d["market_stability"] = "cross_market_unstable"
        if "temporally_unstable" in labels:
            d["temporal_stability"] = "temporally_unstable"
        elif "positive_stable_evidence" in labels:
            d["temporal_stability"] = "stable"
        elif labels:
            d["temporal_stability"] = "uncertain"

    retained = [
        d["feature_name"] for d in feature_decisions if d["decision"] == "retain_candidate"
    ]
    redundant = [
        d["feature_name"] for d in feature_decisions if d["decision"] == "redundant_exclude"
    ]
    unstable = [
        d["feature_name"] for d in feature_decisions if d["decision"] == "unstable_exclude"
    ]
    market_spec_feats = [
        d["feature_name"]
        for d in feature_decisions
        if d["decision"] == "market_specific_candidate"
    ]

    candidate_specs = []
    for spec_name in SPEC_DEFINITIONS:
        aucs, briers, lls, eces = [], [], [], []
        cohort_rois, top10s, top20s, topqs = [], [], [], []
        mkts = []
        for mr in market_results:
            cs = (mr.get("candidate_specifications") or {}).get(spec_name) or {}
            cls = cs.get("classification") or {}
            eco = cs.get("economic") or {}
            if cls.get("auc") is not None:
                aucs.append(cls["auc"])
                mkts.append(mr.get("market"))
            if cls.get("brier") is not None:
                briers.append(cls["brier"])
            if cls.get("log_loss") is not None:
                lls.append(cls["log_loss"])
            if cls.get("ece") is not None:
                eces.append(cls["ece"])
            if eco.get("cohort_full_coverage_roi") is not None:
                cohort_rois.append(eco["cohort_full_coverage_roi"])
            elif eco.get("roi") is not None:
                cohort_rois.append(eco["roi"])
            t10 = eco.get("roi_top_10pct")
            if isinstance(t10, dict):
                t10 = t10.get("roi")
            t20 = eco.get("roi_top_20pct")
            if isinstance(t20, dict):
                t20 = t20.get("roi")
            if t10 is not None:
                top10s.append(t10)
            if t20 is not None:
                top20s.append(t20)
            if eco.get("roi_top_quintile") is not None:
                topqs.append(eco["roi_top_quintile"])

        book_items = [
            m
            for m in all_marginal
            if m.get("spec") == spec_name and m.get("vs") == "BOOK_BASELINE"
        ]
        book_deltas = [m["delta_auc"] for m in book_items if m.get("delta_auc") is not None]
        book_brier = [
            m["delta_brier_improvement"]
            for m in book_items
            if m.get("delta_brier_improvement") is not None
        ]
        temporal_labels = [
            m.get("temporal_classification")
            for m in book_items
            if m.get("temporal_classification")
        ]
        cm = cross_market_meta.get((spec_name, "BOOK_BASELINE")) or {}
        if "temporally_unstable" in temporal_labels:
            tstab = "temporally_unstable"
        elif temporal_labels and all(
            x == "positive_stable_evidence" for x in temporal_labels
        ):
            tstab = "stable"
        elif temporal_labels:
            tstab = "mixed"
        else:
            tstab = "insufficient"
        mstab = cm.get("market_stability") or "insufficient_markets"

        candidate_specs.append(
            {
                "configuration": spec_name,
                "markets": mkts,
                "auc_mean": float(np.mean(aucs)) if aucs else None,
                "brier_mean": float(np.mean(briers)) if briers else None,
                "log_loss_mean": float(np.mean(lls)) if lls else None,
                "ece_mean": float(np.mean(eces)) if eces else None,
                "cohort_full_coverage_roi": (
                    float(np.mean(cohort_rois)) if cohort_rois else None
                ),
                "roi_top_10pct_mean": float(np.mean(top10s)) if top10s else None,
                "roi_top_20pct_mean": float(np.mean(top20s)) if top20s else None,
                "roi_top_quintile_mean": float(np.mean(topqs)) if topqs else None,
                "delta_auc_vs_book_mean": (
                    float(np.mean(book_deltas)) if book_deltas else None
                ),
                "delta_brier_vs_book_mean": (
                    float(np.mean(book_brier)) if book_brier else None
                ),
                "temporal_stability": tstab,
                "market_stability": mstab,
                "markets_positive": cm.get("markets_positive"),
                "markets_negative": cm.get("markets_negative"),
                "status": "ok" if aucs else "insufficient",
            }
        )

    temporal_folds = []
    for mr in market_results:
        if mr.get("temporal_folds"):
            temporal_folds = mr["temporal_folds"]
            break

    markets_ok = [mr["market"] for mr in market_results if mr.get("status") == "ok"]
    blocking = list(quality.get("blocking_issues") or [])
    cohort_valid = len(cohort) > 0 and not blocking
    temporal_done = any(
        (mr.get("temporal_folds") or [])
        for mr in market_results
        if mr.get("status") == "ok"
    )
    fixture_ok = all(
        all(tf.get("fixture_overlap", 0) == 0 for tf in (mr.get("temporal_folds") or []))
        for mr in market_results
        if mr.get("status") == "ok"
    )

    paired_positive = [
        m
        for m in all_marginal
        if m.get("classification") == "positive_stable_evidence"
        and m.get("vs") in ("BOOK_BASELINE", "MODEL_BASELINE")
    ]
    paired_uncertain_ok = [
        m
        for m in all_marginal
        if m.get("delta_auc") is not None
        and m.get("delta_auc") > 0
        and ((m.get("confidence_intervals") or {}).get("delta_auc") or {}).get("ci_low")
        is not None
        and ((m.get("confidence_intervals") or {}).get("delta_auc") or {}).get("ci_low")
        > -0.02
        and (m.get("positive_folds") or 0) > (m.get("negative_folds") or 0)
    ]
    multi_market_ok = False
    for m in paired_positive + paired_uncertain_ok:
        cm = m.get("market_stability")
        if cm == "cross_market_stable" or cm == "market_specific_signal":
            multi_market_ok = True
            break
        if (m.get("markets_positive") or 0) >= 2:
            multi_market_ok = True
            break

    has_paired_evidence = bool(paired_positive) and multi_market_ok

    if blocking:
        next_step = "resolve_data_quality"
    elif not temporal_done or "limited_temporal_span" in limitations:
        next_step = "continue_data_collection"
    elif (
        has_paired_evidence
        and not blocking
        and quality.get("canonical_keys_unique")
        and fixture_ok
    ):
        next_step = "phase_2b_candidate_construction"
    elif paired_uncertain_ok and not paired_positive:
        next_step = "continue_data_collection"
    else:
        next_step = "stop_no_incremental_signal"

    readiness = {
        "cohort_valid": cohort_valid,
        "canonical_keys_unique": bool(quality.get("canonical_keys_unique")),
        "temporal_cv_completed": temporal_done,
        "fixture_grouping_verified": fixture_ok,
        "markets_evaluated": markets_ok,
        "features_with_positive_stable_evidence": retained,
        "market_specific_features": market_spec_feats,
        "features_redundant": redundant,
        "features_unstable": unstable,
        "rating_decision": rating_conclusion,
        "paired_positive_comparisons": len(paired_positive),
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
        "note": (
            "Rating pairs are prespecified (no OOF best-spec selection). "
            "Decision uses paired CI, fold and market stability."
        ),
    }

    total_ms = (time.perf_counter() - t0) * 1000
    payload = {
        "status": "ok",
        "version": STAT_VERSION,
        "dataset_version": DATASET_VERSION,
        "cohort_identity": identity,
        "data_quality": quality,
        "temporal_folds": temporal_folds,
        "market_results": [dict(mr) for mr in market_results],
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
            "thresholds": {
                "delta_auc_stable": DELTA_AUC_STABLE,
                "delta_auc_uncertain": DELTA_AUC_UNCERTAIN,
                "delta_auc_negative": DELTA_AUC_NEGATIVE,
                "fold_neutral_abs": FOLD_NEUTRAL_ABS,
                "market_neutral_abs": MARKET_NEUTRAL_ABS,
            },
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
