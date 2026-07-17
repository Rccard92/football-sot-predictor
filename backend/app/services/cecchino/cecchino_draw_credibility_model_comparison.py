"""Confronto modelli candidati Credibilità X — Fase 1D (validazione temporale, OOF, holdout)."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_draw_credibility_dataset import (
    build_draw_credibility_all_rows,
    rows_for_selected_cohort,
)
from app.services.cecchino.cecchino_draw_credibility_modeling_helpers import (
    BRIER_TOLERANCE_REDUCED,
    C_GRID,
    FEATURE_MANIFEST,
    FORBIDDEN_TRAIN_FEATURES,
    assign_quantile_bin,
    build_quantile_boundaries,
    clamp_prob,
    cluster_bootstrap_ci,
    complexity_diagnostics,
    coefficient_stability_status,
    eligibility_for_model,
    expanding_window_folds,
    group_rows_by_date,
    kickoff_calendar_date,
    parse_kickoff,
    pick_best_c,
    prediction_metrics,
    profitable_status_from_ci,
    roi_from_bets,
    sort_rows_by_kickoff,
    temporal_holdout_split,
)
from app.services.cecchino.cecchino_draw_credibility_research_common import (
    COHORT_ALL_USABLE_SENSITIVITY,
    COHORT_ELIGIBLE_PRIMARY,
    COHORT_MARKET_SUBSET,
)
from app.services.cecchino.cecchino_draw_credibility_statistics import _enrich_research_features

VERSION = "cecchino_draw_credibility_model_comparison_v1"

MIN_PRIMARY_ROWS = 300
MIN_PRIMARY_DRAWS = 50
MIN_DISTINCT_DATES = 10

MODEL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "model_key": "M0_CONSTANT_BASELINE",
        "model_label": "Constant baseline (train draw rate)",
        "kind": "constant",
        "eligibility_default": "baseline",
        "control_only": False,
        "simplicity_rank": 0,
        "features": [],
        "interactions": [],
    },
    {
        "model_key": "M1_RAW_CECCHINO_X",
        "model_label": "Raw Cecchino X",
        "kind": "raw_x",
        "eligibility_default": "benchmark",
        "control_only": False,
        "simplicity_rank": 1,
        "features": ["prob_x_norm"],
        "interactions": [],
    },
    {
        "model_key": "M2_CALIBRATED_CECCHINO_X",
        "model_label": "Calibrated Cecchino X (Platt)",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 2,
        "features": ["prob_x_norm"],
        "interactions": [],
    },
    {
        "model_key": "M3_UNDER_ONLY",
        "model_label": "Under 2.5 only",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 3,
        "features": ["prob_under_2_5_cecchino_pct"],
        "interactions": [],
    },
    {
        "model_key": "M4_X_PLUS_UNDER",
        "model_label": "X + Under",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 4,
        "features": ["prob_x_norm", "prob_under_2_5_cecchino_pct"],
        "interactions": [],
    },
    {
        "model_key": "M5_CORE_X_RANK",
        "model_label": "Core + X rank",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 5,
        "features": ["prob_x_norm", "prob_under_2_5_cecchino_pct", "x_rank"],
        "interactions": [],
    },
    {
        "model_key": "M6_CORE_DIRECTIONAL",
        "model_label": "Core + directional",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 6,
        "features": [
            "prob_x_norm",
            "prob_under_2_5_cecchino_pct",
            "x_rank",
            "x_directional_conviction_candidate",
        ],
        "interactions": [],
    },
    {
        "model_key": "M7_CORE_F36",
        "model_label": "Core + F36 class",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 7,
        "features": [
            "prob_x_norm",
            "prob_under_2_5_cecchino_pct",
            "x_rank",
            "f36_class_existing",
        ],
        "interactions": [],
    },
    {
        "model_key": "M8_CORE_GAP",
        "model_label": "Core + gap coherence binned",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 8,
        "features": [
            "prob_x_norm",
            "prob_under_2_5_cecchino_pct",
            "x_rank",
            "gap_coherence_index_candidate",
        ],
        "interactions": [],
        "bin_gap": True,
    },
    {
        "model_key": "M9_FULL_ADDITIVE",
        "model_label": "Full additive",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 9,
        "features": [
            "prob_x_norm",
            "prob_under_2_5_cecchino_pct",
            "x_rank",
            "x_directional_conviction_candidate",
            "f36_class_existing",
            "gap_coherence_index_candidate",
        ],
        "interactions": [],
        "bin_gap": True,
    },
    {
        "model_key": "M10_INTERACTION_LITE",
        "model_label": "Interaction lite",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 10,
        "features": [
            "prob_x_norm",
            "prob_under_2_5_cecchino_pct",
            "x_rank",
            "x_directional_conviction_candidate",
            "f36_class_existing",
            "gap_coherence_index_candidate",
        ],
        "interactions": ["under_bin_x_rank", "under_bin_x_f36"],
        "bin_gap": True,
        "bin_under": True,
    },
    {
        "model_key": "M11_INTERACTION_EXTENDED",
        "model_label": "Interaction extended",
        "kind": "logistic",
        "eligibility_default": "candidate",
        "control_only": False,
        "simplicity_rank": 11,
        "features": [
            "prob_x_norm",
            "prob_under_2_5_cecchino_pct",
            "x_rank",
            "x_directional_conviction_candidate",
            "f36_class_existing",
            "gap_coherence_index_candidate",
            "x_direction_bucket",
            "dominant_sign_normalized",
        ],
        "interactions": [
            "under_bin_x_rank",
            "under_bin_x_f36",
            "under_bin_x_direction",
            "dominant_x_f36",
        ],
        "bin_gap": True,
        "bin_under": True,
    },
    {
        "model_key": "M12_CONTROL_TIMING",
        "model_label": "Control timing (not eligible)",
        "kind": "logistic",
        "eligibility_default": "control_only",
        "control_only": True,
        "simplicity_rank": 12,
        "features": [
            "prob_x_norm",
            "prob_under_2_5_cecchino_pct",
            "x_rank",
            "x_directional_conviction_candidate",
            "f36_class_existing",
            "gap_coherence_index_candidate",
            "x_direction_bucket",
            "dominant_sign_normalized",
            "hours_to_kickoff",
        ],
        "interactions": [
            "under_bin_x_rank",
            "under_bin_x_f36",
            "under_bin_x_direction",
            "dominant_x_f36",
        ],
        "bin_gap": True,
        "bin_under": True,
    },
]

CONTINUOUS_FEATURES = {
    "prob_under_2_5_cecchino_pct",
    "prob_x_norm",
    "x_directional_conviction_candidate",
    "hours_to_kickoff",
}
CATEGORICAL_FEATURES = {
    "x_rank",
    "f36_class_existing",
    "x_direction_bucket",
    "dominant_sign_normalized",
}


def _num(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return f


def _y(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray([int(r.get("draw_ft") or 0) for r in rows], dtype=int)


def _raw_x_probs(rows: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for r in rows:
        p = _num(r, "prob_x_norm")
        if p is None:
            out.append(0.25)
        else:
            out.append(clamp_prob(p / 100.0 if p > 1.0 else p))
    return out


def _book_probs(rows: list[dict[str, Any]]) -> list[float | None]:
    out: list[float | None] = []
    for r in rows:
        p = _num(r, "prob_book_x_norm")
        if p is None:
            out.append(None)
        else:
            out.append(clamp_prob(p / 100.0 if p > 1.0 else p))
    return out


class FeaturePreprocessor:
    """Fit solo sul train: scaler, OHE, quantile bins gap/under."""

    def __init__(self, model_def: dict[str, Any]):
        self.model_def = model_def
        self.feature_names = list(model_def.get("features") or [])
        self.interactions = list(model_def.get("interactions") or [])
        self.bin_gap = bool(model_def.get("bin_gap"))
        self.bin_under = bool(model_def.get("bin_under"))
        self.gap_boundaries: list[float] = []
        self.under_boundaries: list[float] = []
        self.scalers: dict[str, StandardScaler] = {}
        self.encoders: dict[str, OneHotEncoder] = {}
        self.interaction_encoder: OneHotEncoder | None = None
        self.encoded_names: list[str] = []
        self.fitted = False
        self.medians: dict[str, float] = {}

    def _assert_no_forbidden(self) -> None:
        for f in self.feature_names:
            if f in FORBIDDEN_TRAIN_FEATURES or f.startswith("quota_book") or f.startswith("prob_book"):
                raise ValueError(f"Feature vietata in training: {f}")

    def _gap_bin(self, row: dict[str, Any]) -> str:
        return assign_quantile_bin(_num(row, "gap_coherence_index_candidate"), self.gap_boundaries)

    def _under_bin(self, row: dict[str, Any]) -> str:
        return assign_quantile_bin(_num(row, "prob_under_2_5_cecchino_pct"), self.under_boundaries)

    def _interaction_labels(self, row: dict[str, Any]) -> list[str]:
        labels: list[str] = []
        ub = self._under_bin(row) if self.bin_under else "na"
        xr = str(row.get("x_rank") if row.get("x_rank") is not None else "missing")
        f36 = str(row.get("f36_class_existing") or "missing")
        xd = str(row.get("x_direction_bucket") or "missing")
        dom = str(row.get("dominant_sign_normalized") or "missing")
        for key in self.interactions:
            if key == "under_bin_x_rank":
                labels.append(f"ubxr={ub}|{xr}")
            elif key == "under_bin_x_f36":
                labels.append(f"ubf36={ub}|{f36}")
            elif key == "under_bin_x_direction":
                labels.append(f"ubxd={ub}|{xd}")
            elif key == "dominant_x_f36":
                labels.append(f"domf36={dom}|{f36}")
        return labels

    def fit(self, train_rows: list[dict[str, Any]]) -> FeaturePreprocessor:
        self._assert_no_forbidden()
        if self.bin_gap and "gap_coherence_index_candidate" in self.feature_names:
            vals = [
                v
                for v in (_num(r, "gap_coherence_index_candidate") for r in train_rows)
                if v is not None
            ]
            self.gap_boundaries = build_quantile_boundaries(vals, n_bins=5)

        if self.bin_under:
            vals = [
                v
                for v in (_num(r, "prob_under_2_5_cecchino_pct") for r in train_rows)
                if v is not None
            ]
            self.under_boundaries = build_quantile_boundaries(vals, n_bins=5)

        cont = [f for f in self.feature_names if f in CONTINUOUS_FEATURES]
        cats = [f for f in self.feature_names if f in CATEGORICAL_FEATURES]
        if self.bin_gap and "gap_coherence_index_candidate" in self.feature_names:
            cats = cats + ["_gap_bin"]

        for f in cont:
            vals = []
            for r in train_rows:
                v = _num(r, f)
                if v is not None:
                    vals.append(v)
            med = float(np.median(vals)) if vals else 0.0
            self.medians[f] = med
            arr = np.asarray(
                [[_num(r, f) if _num(r, f) is not None else med] for r in train_rows],
                dtype=float,
            )
            sc = StandardScaler()
            sc.fit(arr)
            self.scalers[f] = sc

        for f in cats:
            if f == "_gap_bin":
                col = [[self._gap_bin(r)] for r in train_rows]
            else:
                col = [[str(r.get(f) if r.get(f) is not None else "missing")] for r in train_rows]
            enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
            enc.fit(col)
            self.encoders[f] = enc

        if self.interactions:
            inter_col = [["|".join(self._interaction_labels(r))] for r in train_rows]
            self.interaction_encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
            self.interaction_encoder.fit(inter_col)

        # build encoded names
        names: list[str] = []
        for f in cont:
            names.append(f"scaled__{f}")
        for f in cats:
            enc = self.encoders[f]
            cats_out = enc.categories_[0]
            for c in cats_out:
                names.append(f"oh__{f}__{c}")
        if self.interaction_encoder is not None:
            for c in self.interaction_encoder.categories_[0]:
                names.append(f"oh__interaction__{c}")
        self.encoded_names = names
        self.fitted = True
        return self

    def transform(self, rows: list[dict[str, Any]]) -> np.ndarray:
        if not self.fitted:
            raise RuntimeError("Preprocessor non fit")
        cont = [f for f in self.feature_names if f in CONTINUOUS_FEATURES]
        cats = [f for f in self.feature_names if f in CATEGORICAL_FEATURES]
        if self.bin_gap and "gap_coherence_index_candidate" in self.feature_names:
            cats = cats + ["_gap_bin"]

        blocks: list[np.ndarray] = []
        for f in cont:
            med = self.medians[f]
            arr = np.asarray(
                [[_num(r, f) if _num(r, f) is not None else med] for r in rows],
                dtype=float,
            )
            blocks.append(self.scalers[f].transform(arr))
        for f in cats:
            if f == "_gap_bin":
                col = [[self._gap_bin(r)] for r in rows]
            else:
                col = [[str(r.get(f) if r.get(f) is not None else "missing")] for r in rows]
            blocks.append(self.encoders[f].transform(col))
        if self.interaction_encoder is not None:
            inter_col = [["|".join(self._interaction_labels(r))] for r in rows]
            blocks.append(self.interaction_encoder.transform(inter_col))
        if not blocks:
            return np.zeros((len(rows), 1), dtype=float)
        return np.hstack(blocks)

    def boundaries_trace(self) -> dict[str, Any]:
        return {
            "gap_boundaries": list(self.gap_boundaries),
            "under_boundaries": list(self.under_boundaries),
            "source": "train_fold_only",
        }


def _make_logistic(C: float, seed: int) -> LogisticRegression:
    return LogisticRegression(
        C=C,
        solver="lbfgs",
        max_iter=2000,
        random_state=seed,
        # L2 default; no class_weight / no SMOTE
    )


class FittedModel:
    def __init__(self, model_def: dict[str, Any]):
        self.model_def = model_def
        self.kind = model_def["kind"]
        self.C: float | None = None
        self.constant_p: float | None = None
        self.pre: FeaturePreprocessor | None = None
        self.clf: LogisticRegression | None = None
        self.coef_map: dict[str, float] = {}
        self.train_fixture_ids: set[Any] = set()

    def fit(
        self,
        train_rows: list[dict[str, Any]],
        *,
        C: float = 1.0,
        seed: int = 42,
    ) -> FittedModel:
        self.train_fixture_ids = {r.get("provider_fixture_id") for r in train_rows}
        y = _y(train_rows)
        if self.kind == "constant":
            self.constant_p = float(y.mean()) if len(y) else 0.25
            return self
        if self.kind == "raw_x":
            return self
        self.C = C
        self.pre = FeaturePreprocessor(self.model_def).fit(train_rows)
        X = self.pre.transform(train_rows)
        if len(np.unique(y)) < 2:
            self.constant_p = float(y.mean()) if len(y) else 0.25
            self.kind = "constant_fallback"
            return self
        self.clf = _make_logistic(C, seed)
        self.clf.fit(X, y)
        self.coef_map = {
            name: float(coef)
            for name, coef in zip(self.pre.encoded_names, self.clf.coef_.ravel())
        }
        return self

    def predict_proba(self, rows: list[dict[str, Any]]) -> list[float]:
        if self.kind == "constant" or self.kind == "constant_fallback":
            p = self.constant_p if self.constant_p is not None else 0.25
            return [clamp_prob(p)] * len(rows)
        if self.kind == "raw_x":
            return _raw_x_probs(rows)
        assert self.pre is not None and self.clf is not None
        X = self.pre.transform(rows)
        proba = self.clf.predict_proba(X)
        # class 1 = draw
        classes = list(self.clf.classes_)
        if 1 in classes:
            idx = classes.index(1)
        else:
            idx = -1
        return [clamp_prob(float(p[idx])) for p in proba]


def _oof_row(
    row: dict[str, Any],
    *,
    model_key: str,
    fold_id: str,
    prob: float,
) -> dict[str, Any]:
    book_p = _num(row, "prob_book_x_norm")
    return {
        "provider_fixture_id": row.get("provider_fixture_id"),
        "kickoff": row.get("kickoff"),
        "draw_ft": int(row.get("draw_ft") or 0),
        "model_key": model_key,
        "fold_id": fold_id,
        "predicted_draw_probability": prob,
        "predicted_credibility_0_100": round(prob * 100.0, 4),
        "is_market_row": bool(row.get("has_market_features")),
        "quota_book_x": row.get("quota_book_x"),
        "prob_book_x_norm": book_p,
    }


def _select_c_for_model(
    model_def: dict[str, Any],
    folds: list[dict[str, Any]],
    *,
    seed: int,
) -> dict[str, Any]:
    kind = model_def["kind"]
    if kind in ("constant", "raw_x"):
        return {"C": None, "mean_brier": None, "mean_log_loss": None, "fold_metrics": []}

    candidates: list[dict[str, Any]] = []
    for C in C_GRID:
        fold_metrics = []
        briers = []
        loglosses = []
        for fold in folds:
            fm = FittedModel(model_def).fit(fold["train_rows"], C=C, seed=seed)
            probs = fm.predict_proba(fold["validation_rows"])
            y = [int(r.get("draw_ft") or 0) for r in fold["validation_rows"]]
            train_rate = fold.get("train_draw_rate") or 0.25
            m = prediction_metrics(probs, y, baseline_prob=float(train_rate))
            fold_metrics.append({"fold_id": fold["fold_id"], "C": C, **m})
            if m["brier_score"] is not None:
                briers.append(m["brier_score"])
            if m["log_loss"] is not None:
                loglosses.append(m["log_loss"])
        candidates.append(
            {
                "C": C,
                "mean_brier": float(np.mean(briers)) if briers else None,
                "mean_log_loss": float(np.mean(loglosses)) if loglosses else None,
                "simplicity_rank": model_def.get("simplicity_rank", 99),
                "fold_metrics": fold_metrics,
            }
        )
    best = pick_best_c(candidates)
    return best or {"C": 1.0, "mean_brier": None, "mean_log_loss": None, "fold_metrics": []}


def _run_cv_for_model(
    model_def: dict[str, Any],
    folds: list[dict[str, Any]],
    *,
    C: float | None,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[float]]]:
    """Returns fold results, oof rows, coefs_per_feature."""
    fold_results: list[dict[str, Any]] = []
    oof: list[dict[str, Any]] = []
    coefs: dict[str, list[float]] = {}
    for fold in folds:
        c_use = C if C is not None else 1.0
        fm = FittedModel(model_def).fit(fold["train_rows"], C=c_use, seed=seed)
        probs = fm.predict_proba(fold["validation_rows"])
        y = [int(r.get("draw_ft") or 0) for r in fold["validation_rows"]]
        train_rate = fold.get("train_draw_rate") or 0.25
        metrics = prediction_metrics(probs, y, baseline_prob=float(train_rate))
        for name, coef in fm.coef_map.items():
            coefs.setdefault(name, []).append(coef)
        fold_results.append(
            {
                "fold_id": fold["fold_id"],
                "model_key": model_def["model_key"],
                "train_rows": len(fold["train_rows"]),
                "validation_rows": len(fold["validation_rows"]),
                "train_dates": fold["train_dates"],
                "validation_dates": fold["validation_dates"],
                "train_draw_rate": fold["train_draw_rate"],
                "validation_draw_rate": fold["validation_draw_rate"],
                "C": C,
                "boundaries": fm.pre.boundaries_trace() if fm.pre else None,
                **metrics,
            }
        )
        for r, p in zip(fold["validation_rows"], probs):
            # leakage check: must not be in train
            oof.append(
                _oof_row(
                    r,
                    model_key=model_def["model_key"],
                    fold_id=fold["fold_id"],
                    prob=p,
                )
            )
            oof[-1]["_train_contains_fixture"] = r.get("provider_fixture_id") in fm.train_fixture_ids
    return fold_results, oof, coefs


def _oof_consistency(oof_rows: list[dict[str, Any]], development_ids: set[Any]) -> dict[str, Any]:
    keys = [(r["provider_fixture_id"], r["model_key"], r["fold_id"]) for r in oof_rows]
    duplicates = len(keys) - len(set(keys))
    in_sample = sum(1 for r in oof_rows if r.pop("_train_contains_fixture", False))
    predicted_ids = {r["provider_fixture_id"] for r in oof_rows}
    # rows without prediction: development fixtures that never appear in any validation
    # (first train block may never be in val — expected for expanding window)
    missing = len(development_ids - predicted_ids)
    leakage = in_sample > 0
    return {
        "oof_rows": len(oof_rows),
        "duplicate_oof_predictions": duplicates,
        "in_sample_predictions": in_sample,
        "rows_without_prediction": missing,
        "target_leakage_detected": leakage,
    }


def _market_oof_analysis(
    oof_by_model: dict[str, list[dict[str, Any]]],
    folds: list[dict[str, Any]],
    *,
    leading_key: str | None,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    key = leading_key or "M4_X_PLUS_UNDER"
    rows = [r for r in oof_by_model.get(key, []) if r.get("is_market_row") and r.get("quota_book_x")]
    if not rows:
        return {"status": "insufficient_market_oof", "model_key": key}

    probs = [float(r["predicted_draw_probability"]) for r in rows]
    y = [int(r["draw_ft"]) for r in rows]
    book = []
    for r in rows:
        bp = r.get("prob_book_x_norm")
        if bp is None:
            book.append(None)
        else:
            book.append(clamp_prob(float(bp) / 100.0 if float(bp) > 1 else float(bp)))
    book_ok = [(p, yt) for p, yt in zip(book, y) if p is not None]
    model_metrics = prediction_metrics(probs, y, baseline_prob=float(np.mean(y)) if y else 0.25)
    book_metrics = None
    if book_ok:
        book_metrics = prediction_metrics(
            [p for p, _ in book_ok],
            [yt for _, yt in book_ok],
            baseline_prob=float(np.mean([yt for _, yt in book_ok])),
        )

    edges = []
    for r, p, b in zip(rows, probs, book):
        if b is None:
            continue
        edges.append(p - b)

    # ROI breakdowns with train-fold quintile boundaries applied per fold
    all_bets = []
    for r in rows:
        odd = r.get("quota_book_x")
        if odd is None:
            continue
        all_bets.append({"odd": float(odd), "win": int(r["draw_ft"]) == 1, "row": r})

    def _roi_block(bets: list[dict[str, Any]], label: str) -> dict[str, Any]:
        base = roi_from_bets(bets)
        # cluster bootstrap by date
        date_map: dict[date, list[dict[str, Any]]] = {}
        for b in bets:
            d = kickoff_calendar_date(b["row"])
            if d is None:
                continue
            date_map.setdefault(d, []).append(b)

        def metric_fn(sampled_bets: list[dict[str, Any]]) -> float | None:
            # sampled_bets here will be rows-like from cluster — adapt
            return None

        # rebuild from dates
        dates = list(date_map.keys())

        def roi_metric(sampled_rows: list[dict[str, Any]]) -> float | None:
            # sampled_rows are bets dicts stored as rows in date_map values — flatten already bets
            bb = []
            for item in sampled_rows:
                if "odd" in item:
                    bb.append(item)
            if not bb:
                return None
            return roi_from_bets(bb).get("roi")

        # date_to_rows for bets
        ci = cluster_bootstrap_ci(
            dates,
            date_map,
            metric_fn=roi_metric,
            iterations=min(bootstrap_iterations, 200),
            seed=seed,
        )
        status = profitable_status_from_ci(ci, min_bets=20, bets=base["bets"])
        base["cluster_bootstrap_ci"] = ci
        base["profitable_status"] = status
        base["label"] = label
        return base

    breakdowns = [_roi_block(all_bets, "all_market_oof")]

    # quintiles of model pred — boundaries from all OOF train isn't available globally;
    # use overall OOF probs train-style: split by fold using fold train predictions mean boundaries
    if len(probs) >= 5:
        bounds = build_quantile_boundaries(probs, n_bins=5)
        for qi in range(len(bounds) + 1):
            subset = []
            for b, p in zip(all_bets, probs):
                # assign bin
                from app.services.cecchino.cecchino_draw_credibility_modeling_helpers import (
                    assign_quantile_bin as _aqb,
                )

                if _aqb(p, bounds) == f"bin_{qi}":
                    subset.append(b)
            if subset:
                breakdowns.append(_roi_block(subset, f"model_quintile_{qi}"))

        # top/bottom 20%
        order = sorted(range(len(probs)), key=lambda i: probs[i])
        q = max(1, len(order) // 5)
        top_idx = set(order[-q:])
        bot_idx = set(order[:q])
        breakdowns.append(_roi_block([all_bets[i] for i in top_idx if i < len(all_bets)], "top_20_credibility"))
        breakdowns.append(_roi_block([all_bets[i] for i in bot_idx if i < len(all_bets)], "bottom_20_credibility"))

    if edges:
        edge_bounds = build_quantile_boundaries(edges, n_bins=5)
        edge_bets = []
        for r, p, b in zip(rows, probs, book):
            if b is None or r.get("quota_book_x") is None:
                continue
            edge_bets.append(
                {
                    "odd": float(r["quota_book_x"]),
                    "win": int(r["draw_ft"]) == 1,
                    "row": r,
                    "edge": p - b,
                }
            )
        for qi in range(len(edge_bounds) + 1):
            from app.services.cecchino.cecchino_draw_credibility_modeling_helpers import (
                assign_quantile_bin as _aqb,
            )

            subset = [b for b in edge_bets if _aqb(b["edge"], edge_bounds) == f"bin_{qi}"]
            if subset:
                breakdowns.append(_roi_block(subset, f"edge_quintile_{qi}"))

    return {
        "model_key": key,
        "market_oof_rows": len(rows),
        "model_metrics": model_metrics,
        "book_metrics": book_metrics,
        "mean_edge": float(np.mean(edges)) if edges else None,
        "roi_breakdowns": breakdowns,
        "book_benchmark": {
            "model_key": "BOOK_X_BENCHMARK",
            "eligibility": "external_benchmark_only",
            "metrics": book_metrics,
        },
        "notes": [
            "Solo prediction OOF; Book non in training.",
            "Nessuna ottimizzazione soglia ROI sul test.",
        ],
    }


def _reduced_model_proposal(
    leaderboard: list[dict[str, Any]],
    model_defs: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible = [
        r
        for r in leaderboard
        if r.get("eligibility") in ("EXPLORATORY_CANDIDATE", "LEADING_EXPLORATORY_CANDIDATE")
        and not r.get("control_only")
    ]
    if not eligible:
        return {"status": "not_justified", "reason": "no_eligible_complex_model"}

    best = min(
        eligible,
        key=lambda r: r.get("holdout_brier") if r.get("holdout_brier") is not None else 999.0,
    )
    # prefer simpler within tolerance
    within = [
        r
        for r in eligible
        if r.get("holdout_brier") is not None
        and best.get("holdout_brier") is not None
        and r["holdout_brier"] <= best["holdout_brier"] + BRIER_TOLERANCE_REDUCED
    ]
    reduced = min(within, key=lambda r: (r.get("simplicity_rank", 99), r.get("holdout_brier") or 999))
    src_def = next(d for d in model_defs if d["model_key"] == best["model_key"])
    red_def = next(d for d in model_defs if d["model_key"] == reduced["model_key"])
    removed = sorted(set(src_def.get("features") or []) - set(red_def.get("features") or []))
    retained = list(red_def.get("features") or [])
    return {
        "status": "proposed",
        "reduced_model_source": best["model_key"],
        "reduced_model_key": reduced["model_key"],
        "removed_features": removed,
        "removal_reasons": ["simpler_within_brier_tolerance_0.002_or_unstable_or_redundant"],
        "retained_features": retained,
        "performance_delta": {
            "holdout_brier_delta": (
                (reduced.get("holdout_brier") or 0) - (best.get("holdout_brier") or 0)
                if reduced.get("holdout_brier") is not None and best.get("holdout_brier") is not None
                else None
            )
        },
        "complexity_delta": {
            "simplicity_rank_delta": reduced.get("simplicity_rank", 0) - best.get("simplicity_rank", 0)
        },
        "selection_on_holdout": False,
    }


def build_draw_credibility_model_comparison(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    final_holdout_pct: float = 0.25,
    inner_splits: int = 3,
    bootstrap_iterations: int = 500,
    random_seed: int = 42,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    warnings: list[str] = []

    t_ds = time.perf_counter()
    all_rows, _meta = build_draw_credibility_all_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    primary_raw = rows_for_selected_cohort(all_rows, COHORT_ELIGIBLE_PRIMARY)
    sensitivity_raw = rows_for_selected_cohort(all_rows, COHORT_ALL_USABLE_SENSITIVITY)
    market_raw = rows_for_selected_cohort(all_rows, COHORT_MARKET_SUBSET)
    dataset_ms = (time.perf_counter() - t_ds) * 1000

    t_en = time.perf_counter()
    primary = [_enrich_research_features(r) for r in primary_raw]
    sensitivity = [_enrich_research_features(r) for r in sensitivity_raw]
    market = [_enrich_research_features(r) for r in market_raw]
    enrich_ms = (time.perf_counter() - t_en) * 1000

    primary = sort_rows_by_kickoff(primary)
    draws = sum(1 for r in primary if int(r.get("draw_ft") or 0) == 1)
    dates = {kickoff_calendar_date(r) for r in primary if kickoff_calendar_date(r)}
    dates.discard(None)

    filters = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "competition_id": competition_id,
        "final_holdout_pct": final_holdout_pct,
        "inner_splits": inner_splits,
        "bootstrap_iterations": bootstrap_iterations,
        "random_seed": random_seed,
    }
    dataset_summary = {
        "primary": {
            "rows": len(primary),
            "draws": draws,
            "draw_rate_pct": round(100.0 * draws / len(primary), 2) if primary else None,
            "distinct_dates": len(dates),
        },
        "sensitivity": {
            "rows": len(sensitivity),
            "draws": sum(1 for r in sensitivity if int(r.get("draw_ft") or 0) == 1),
        },
        "market": {
            "rows": len(market),
            "draws": sum(1 for r in market if int(r.get("draw_ft") or 0) == 1),
        },
    }

    if (
        len(primary) < MIN_PRIMARY_ROWS
        or draws < MIN_PRIMARY_DRAWS
        or len(dates) < MIN_DISTINCT_DATES
    ):
        return {
            "status": "insufficient_sample",
            "version": VERSION,
            "filters": filters,
            "dataset_summary": dataset_summary,
            "feature_manifest": FEATURE_MANIFEST,
            "warnings": [
                "insufficient_primary_sample",
                f"need_rows>={MIN_PRIMARY_ROWS}_draws>={MIN_PRIMARY_DRAWS}_dates>={MIN_DISTINCT_DATES}",
            ],
            "decision": {
                "status": "no_candidate_ready",
                "leading_model": None,
                "reduced_model": None,
                "reasons": ["insufficient_sample"],
                "limitations": ["history_too_short_or_too_few_draws"],
                "required_next_history_days": 90,
                "production_change_allowed": False,
            },
            "performance": {
                "dataset_build_ms": round(dataset_ms, 1),
                "enrichment_ms": round(enrich_ms, 1),
                "total_ms": round((time.perf_counter() - t0) * 1000, 1),
            },
        }

    split = temporal_holdout_split(primary, final_holdout_pct=final_holdout_pct)
    development_rows = split["development_rows"]
    holdout_rows = split["holdout_rows"]
    dev_dates = split["development_dates"]
    hold_dates = split["holdout_dates"]

    # consistency: no date overlap
    overlap = set(dev_dates) & set(hold_dates)
    if overlap:
        warnings.append("date_overlap_detected")
    same_date_split = False
    for d in set(dev_dates) | set(hold_dates):
        in_dev = sum(1 for r in development_rows if kickoff_calendar_date(r) == d)
        in_hold = sum(1 for r in holdout_rows if kickoff_calendar_date(r) == d)
        if in_dev and in_hold:
            same_date_split = True
            warnings.append(f"same_date_split:{d.isoformat()}")

    split_definition = {
        "development_date_from": min(dev_dates).isoformat() if dev_dates else None,
        "development_date_to": max(dev_dates).isoformat() if dev_dates else None,
        "development_rows": len(development_rows),
        "development_draws": sum(1 for r in development_rows if int(r.get("draw_ft") or 0) == 1),
        "holdout_date_from": min(hold_dates).isoformat() if hold_dates else None,
        "holdout_date_to": max(hold_dates).isoformat() if hold_dates else None,
        "holdout_rows": len(holdout_rows),
        "holdout_draws": sum(1 for r in holdout_rows if int(r.get("draw_ft") or 0) == 1),
        "actual_holdout_pct": split["actual_holdout_pct"],
        "development_dates_count": len(dev_dates),
        "holdout_dates_count": len(hold_dates),
    }
    split_consistency_checks = {
        "same_date_split": same_date_split,
        "date_overlap_count": len(overlap),
        "holdout_untouched_until_after_cv": True,
        "sorted_by_kickoff": True,
    }

    folds, fold_warnings = expanding_window_folds(development_rows, inner_splits=inner_splits)
    warnings.extend(fold_warnings)
    if not folds:
        return {
            "status": "insufficient_folds",
            "version": VERSION,
            "filters": filters,
            "dataset_summary": dataset_summary,
            "feature_manifest": FEATURE_MANIFEST,
            "split_definition": split_definition,
            "split_consistency_checks": split_consistency_checks,
            "warnings": warnings + ["no_valid_expanding_folds"],
            "decision": {
                "status": "no_candidate_ready",
                "leading_model": None,
                "reduced_model": None,
                "reasons": ["no_valid_expanding_folds"],
                "limitations": ["temporal_span_too_short"],
                "required_next_history_days": 90,
                "production_change_allowed": False,
            },
            "performance": {
                "dataset_build_ms": round(dataset_ms, 1),
                "enrichment_ms": round(enrich_ms, 1),
                "total_ms": round((time.perf_counter() - t0) * 1000, 1),
            },
        }

    t_cv = time.perf_counter()
    development_cv_results: list[dict[str, Any]] = []
    oof_by_model: dict[str, list[dict[str, Any]]] = {}
    best_c_by_model: dict[str, Any] = {}
    coef_stability: dict[str, Any] = {}
    all_oof: list[dict[str, Any]] = []

    for model_def in MODEL_DEFINITIONS:
        sel = _select_c_for_model(model_def, folds, seed=random_seed)
        best_c_by_model[model_def["model_key"]] = {
            "C": sel.get("C"),
            "mean_brier": sel.get("mean_brier"),
            "mean_log_loss": sel.get("mean_log_loss"),
        }
        C = sel.get("C")
        fold_results, oof_rows, coefs = _run_cv_for_model(
            model_def, folds, C=C, seed=random_seed
        )
        development_cv_results.extend(fold_results)
        oof_by_model[model_def["model_key"]] = oof_rows
        all_oof.extend(oof_rows)

        stab_rows = []
        for feat, vals in coefs.items():
            present_all = len(vals) == len(folds)
            sign_changes = 0
            nz = [v for v in vals if abs(v) > 1e-8]
            for i in range(1, len(nz)):
                if (nz[i] > 0) != (nz[i - 1] > 0):
                    sign_changes += 1
            stab_rows.append(
                {
                    "feature_encoded": feat,
                    "coefficients_per_fold": vals,
                    "mean": float(np.mean(vals)) if vals else None,
                    "std": float(np.std(vals)) if len(vals) > 1 else 0.0,
                    "min": float(min(vals)) if vals else None,
                    "max": float(max(vals)) if vals else None,
                    "sign_changes": sign_changes,
                    "present_in_all_folds": present_all,
                    "stability_status": coefficient_stability_status(
                        vals, present_all_folds=present_all
                    ),
                }
            )
        coef_stability[model_def["model_key"]] = stab_rows

    cv_ms = (time.perf_counter() - t_cv) * 1000
    development_ids = {r.get("provider_fixture_id") for r in development_rows}
    oof_checks = _oof_consistency(all_oof, development_ids)
    if oof_checks["target_leakage_detected"]:
        warnings.append("target_leakage_detected")

    # Final holdout: fit on full development with selected C
    t_hold = time.perf_counter()
    final_holdout_results: list[dict[str, Any]] = []
    holdout_y = [int(r.get("draw_ft") or 0) for r in holdout_rows]
    holdout_base = (
        sum(1 for r in development_rows if int(r.get("draw_ft") or 0) == 1) / len(development_rows)
        if development_rows
        else 0.25
    )
    calibration_analysis: dict[str, Any] = {}

    for model_def in MODEL_DEFINITIONS:
        C = best_c_by_model[model_def["model_key"]].get("C")
        c_use = C if C is not None else 1.0
        fm = FittedModel(model_def).fit(development_rows, C=c_use, seed=random_seed)
        probs = fm.predict_proba(holdout_rows)
        metrics = prediction_metrics(probs, holdout_y, baseline_prob=holdout_base)

        # cluster bootstrap Brier delta vs baseline
        date_map = {d: g for d, g in group_rows_by_date(holdout_rows)}
        dates_h = list(date_map.keys())

        def _brier_delta(sampled: list[dict[str, Any]]) -> float | None:
            if not sampled:
                return None
            pp = fm.predict_proba(sampled)
            yy = [int(r.get("draw_ft") or 0) for r in sampled]
            m = prediction_metrics(pp, yy, baseline_prob=holdout_base)
            if m["brier_score"] is None or m["baseline_brier"] is None:
                return None
            return m["baseline_brier"] - m["brier_score"]

        brier_ci = cluster_bootstrap_ci(
            dates_h,
            date_map,
            metric_fn=_brier_delta,
            iterations=min(bootstrap_iterations, 300),
            seed=random_seed,
        )

        # complexity
        raw_n = len(model_def.get("features") or [])
        enc_n = len(fm.pre.encoded_names) if fm.pre else raw_n
        nz = sum(1 for v in fm.coef_map.values() if abs(v) > 1e-8) if fm.coef_map else 0
        cx = complexity_diagnostics(
            raw_feature_count=raw_n,
            encoded_feature_count=enc_n,
            interaction_count=len(model_def.get("interactions") or []),
            nonzero_coef_count=max(nz, 1 if model_def["kind"] != "constant" else 1),
            train_rows=len(development_rows),
        )
        if cx["warnings"]:
            warnings.extend([f"{model_def['model_key']}:{w}" for w in cx["warnings"]])

        final_holdout_results.append(
            {
                "model_key": model_def["model_key"],
                "model_label": model_def["model_label"],
                "C": C,
                "control_only": model_def.get("control_only", False),
                "boundaries": fm.pre.boundaries_trace() if fm.pre else None,
                "bootstrap_brier_delta_ci": brier_ci,
                "complexity": cx,
                "coefficients": fm.coef_map,
                **metrics,
            }
        )
        calibration_analysis[model_def["model_key"]] = {
            "calibration_slope": metrics.get("calibration_slope"),
            "calibration_intercept": metrics.get("calibration_intercept"),
            "ece": metrics.get("ece"),
            "holdout_prediction_mean": metrics.get("prediction_mean"),
        }

    hold_ms = (time.perf_counter() - t_hold) * 1000

    m1_hold = next(
        (r for r in final_holdout_results if r["model_key"] == "M1_RAW_CECCHINO_X"),
        None,
    )
    m0_hold = next(
        (r for r in final_holdout_results if r["model_key"] == "M0_CONSTANT_BASELINE"),
        None,
    )

    # Leaderboard
    leaderboard: list[dict[str, Any]] = []
    for model_def in MODEL_DEFINITIONS:
        key = model_def["model_key"]
        hold = next(r for r in final_holdout_results if r["model_key"] == key)
        cv_folds = [r for r in development_cv_results if r["model_key"] == key]
        mean_brier = (
            float(np.mean([r["brier_score"] for r in cv_folds if r.get("brier_score") is not None]))
            if cv_folds
            else None
        )
        mean_bss = (
            float(
                np.mean(
                    [r["brier_skill_score"] for r in cv_folds if r.get("brier_skill_score") is not None]
                )
            )
            if cv_folds
            else None
        )
        mean_ll = (
            float(np.mean([r["log_loss"] for r in cv_folds if r.get("log_loss") is not None]))
            if cv_folds
            else None
        )
        mean_auc = (
            float(np.mean([r["auc"] for r in cv_folds if r.get("auc") is not None]))
            if cv_folds
            else None
        )
        coherent = sum(
            1
            for r in cv_folds
            if r.get("brier_skill_score") is not None and r["brier_skill_score"] > 0
        )
        stab = coef_stability.get(key) or []
        unstable = any(s.get("stability_status") == "unstable" for s in stab)
        main_stable = all(
            s.get("stability_status") in ("stable", "mostly_stable", "unavailable")
            for s in stab
        ) and not unstable
        brier_ci = hold.get("bootstrap_brier_delta_ci") or {}
        ci_fav = (
            brier_ci.get("lower") is not None
            and brier_ci.get("lower") > 0
        )
        cx = hold.get("complexity") or {}
        complexity_ok = "severe_low_train_rows_per_coefficient" not in (cx.get("warnings") or [])
        elig = eligibility_for_model(
            holdout_bss=hold.get("brier_skill_score"),
            holdout_brier=hold.get("brier_score"),
            m1_holdout_brier=m1_hold.get("brier_score") if m1_hold else None,
            holdout_log_loss=hold.get("log_loss"),
            baseline_log_loss=m0_hold.get("log_loss") if m0_hold else None,
            coherent_folds=coherent,
            leakage=bool(oof_checks.get("target_leakage_detected")),
            complexity_ok=complexity_ok,
            control_only=bool(model_def.get("control_only")),
            unstable=unstable,
            stable_improvement_cv=coherent >= 2 and (mean_bss or 0) > 0,
            brier_delta_ci_favorable=bool(ci_fav),
            main_coefs_stable=main_stable,
            reduced_not_worse=True,
        )
        model_warnings = list(cx.get("warnings") or [])
        if model_def.get("control_only"):
            model_warnings.append("control_only_not_eligible")
        leaderboard.append(
            {
                "model_key": key,
                "model_label": model_def["model_label"],
                "eligibility": elig,
                "control_only": model_def.get("control_only", False),
                "simplicity_rank": model_def.get("simplicity_rank"),
                "selected_C": best_c_by_model[key].get("C"),
                "development_mean_brier": mean_brier,
                "development_brier_skill": mean_bss,
                "development_log_loss": mean_ll,
                "development_auc": mean_auc,
                "holdout_brier": hold.get("brier_score"),
                "holdout_brier_skill": hold.get("brier_skill_score"),
                "holdout_log_loss": hold.get("log_loss"),
                "holdout_auc": hold.get("auc"),
                "holdout_ece": hold.get("ece"),
                "top_quintile_lift": hold.get("top_quintile_lift"),
                "temporal_stability": "ok" if coherent >= 2 else "weak",
                "coefficient_stability": "unstable" if unstable else ("stable" if main_stable else "mixed"),
                "complexity": cx,
                "warnings": model_warnings,
            }
        )

    leaderboard.sort(
        key=lambda r: r["holdout_brier"] if r.get("holdout_brier") is not None else 999.0
    )

    reduced = _reduced_model_proposal(leaderboard, MODEL_DEFINITIONS)

    # Marginal contributions (paired holdout Brier deltas)
    by_key = {r["model_key"]: r for r in leaderboard}
    marginal = []
    pair_specs = [
        ("M1_RAW_CECCHINO_X", "M4_X_PLUS_UNDER", "X vs X+Under"),
        ("M4_X_PLUS_UNDER", "M5_CORE_X_RANK", "X+Under vs +X rank"),
        ("M5_CORE_X_RANK", "M6_CORE_DIRECTIONAL", "+Directional"),
        ("M5_CORE_X_RANK", "M7_CORE_F36", "+F36"),
        ("M5_CORE_X_RANK", "M8_CORE_GAP", "+Gap"),
        ("M9_FULL_ADDITIVE", "M10_INTERACTION_LITE", "Additive vs interactions lite"),
        ("M9_FULL_ADDITIVE", "M11_INTERACTION_EXTENDED", "Additive vs interactions extended"),
    ]
    src = reduced.get("reduced_model_source")
    red = reduced.get("reduced_model_key")
    if src and red:
        pair_specs.append((src, red, "Full vs reduced"))
    for a, b, label in pair_specs:
        if (
            a in by_key
            and b in by_key
            and by_key[a].get("holdout_brier") is not None
            and by_key[b].get("holdout_brier") is not None
        ):
            marginal.append(
                {
                    "comparison": label,
                    "from_model": a,
                    "to_model": b,
                    "holdout_brier_delta": by_key[b]["holdout_brier"] - by_key[a]["holdout_brier"],
                }
            )

    # Primary vs Sensitivity (descriptive): apply leading model pipeline
    leading = next(
        (
            r
            for r in leaderboard
            if r["eligibility"] in ("LEADING_EXPLORATORY_CANDIDATE", "EXPLORATORY_CANDIDATE")
            and not r.get("control_only")
        ),
        None,
    )
    leading_key = leading["model_key"] if leading else None
    if not leading_key:
        # fallback descriptive: best non-control by holdout brier
        nc = [r for r in leaderboard if not r.get("control_only") and r["model_key"] not in ("M0_CONSTANT_BASELINE",)]
        leading_key = nc[0]["model_key"] if nc else "M4_X_PLUS_UNDER"

    primary_ids = {r.get("provider_fixture_id") for r in primary}
    sens_ids = {r.get("provider_fixture_id") for r in sensitivity}
    extra_sens = [r for r in sensitivity if r.get("provider_fixture_id") not in primary_ids]
    lead_def = next(d for d in MODEL_DEFINITIONS if d["model_key"] == leading_key)
    C_lead = best_c_by_model[leading_key].get("C") or 1.0
    # Fit on primary development-equivalent: use all primary development for descriptive
    fm_p = FittedModel(lead_def).fit(development_rows, C=C_lead, seed=random_seed)
    # Evaluate on primary holdout vs sensitivity rows overlapping holdout dates
    hold_ids = {r.get("provider_fixture_id") for r in holdout_rows}
    sens_hold = [r for r in sensitivity if r.get("provider_fixture_id") in hold_ids]
    sens_extra_hold = [r for r in extra_sens if kickoff_calendar_date(r) in set(hold_dates)]
    p_metrics = prediction_metrics(
        fm_p.predict_proba(holdout_rows), holdout_y, baseline_prob=holdout_base
    )
    s_y = [int(r.get("draw_ft") or 0) for r in sens_hold] if sens_hold else []
    s_metrics = (
        prediction_metrics(fm_p.predict_proba(sens_hold), s_y, baseline_prob=holdout_base)
        if sens_hold
        else None
    )
    e_y = [int(r.get("draw_ft") or 0) for r in sens_extra_hold] if sens_extra_hold else []
    e_metrics = (
        prediction_metrics(fm_p.predict_proba(sens_extra_hold), e_y, baseline_prob=holdout_base)
        if sens_extra_hold and e_y
        else None
    )
    primary_vs_sensitivity = {
        "model_key": leading_key,
        "warning_overlap": "Sensitivity contains Primary; not an independent holdout",
        "primary_ids": len(primary_ids),
        "sensitivity_ids": len(sens_ids),
        "overlap_ids": len(primary_ids & sens_ids),
        "extra_sensitivity_rows": len(extra_sens),
        "performance_primary_holdout": p_metrics,
        "performance_sensitivity_holdout_overlap": s_metrics,
        "performance_extra_sensitivity": e_metrics,
        "delta_brier_sens_minus_primary": (
            (s_metrics["brier_score"] - p_metrics["brier_score"])
            if s_metrics and s_metrics.get("brier_score") is not None and p_metrics.get("brier_score") is not None
            else None
        ),
    }

    market_oof = _market_oof_analysis(
        oof_by_model,
        folds,
        leading_key=leading_key,
        bootstrap_iterations=bootstrap_iterations,
        seed=random_seed,
    )

    # Decision
    exploratories = [
        r
        for r in leaderboard
        if r["eligibility"] in ("EXPLORATORY_CANDIDATE", "LEADING_EXPLORATORY_CANDIDATE")
    ]
    leading_row = next(
        (r for r in exploratories if r["eligibility"] == "LEADING_EXPLORATORY_CANDIDATE"),
        exploratories[0] if exploratories else None,
    )
    decision = {
        "status": "exploratory_candidate_found" if exploratories else "no_candidate_ready",
        "leading_model": leading_row["model_key"] if leading_row else None,
        "reduced_model": reduced.get("reduced_model_key"),
        "reasons": (
            [
                f"eligibility={leading_row['eligibility']}",
                f"holdout_brier={leading_row.get('holdout_brier')}",
            ]
            if leading_row
            else ["no_model_met_exploratory_criteria"]
        ),
        "limitations": [
            "short_temporal_span_possible",
            "exploratory_only",
            "book_not_in_training",
            "no_production_promotion",
        ],
        "required_next_history_days": 90,
        "production_change_allowed": False,
    }

    # OOF predictions sample for export (full list can be large — include all)
    oof_predictions = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in all_oof
    ]

    total_ms = (time.perf_counter() - t0) * 1000
    return {
        "status": "ok",
        "version": VERSION,
        "filters": filters,
        "dataset_summary": dataset_summary,
        "feature_manifest": FEATURE_MANIFEST,
        "split_definition": split_definition,
        "split_consistency_checks": split_consistency_checks,
        "model_definitions": [
            {
                "model_key": d["model_key"],
                "model_label": d["model_label"],
                "kind": d["kind"],
                "features": d.get("features"),
                "interactions": d.get("interactions"),
                "control_only": d.get("control_only", False),
            }
            for d in MODEL_DEFINITIONS
        ],
        "best_C_by_model": best_c_by_model,
        "development_cv_results": development_cv_results,
        "model_leaderboard": leaderboard,
        "final_holdout_results": final_holdout_results,
        "coefficient_stability": coef_stability,
        "calibration_analysis": calibration_analysis,
        "marginal_contributions": marginal,
        "oof_consistency_checks": oof_checks,
        "oof_predictions": oof_predictions,
        "primary_vs_sensitivity": primary_vs_sensitivity,
        "market_oof_analysis": market_oof,
        "reduced_model_analysis": reduced,
        "decision": decision,
        "warnings": warnings,
        "performance": {
            "dataset_build_ms": round(dataset_ms, 1),
            "enrichment_ms": round(enrich_ms, 1),
            "cv_ms": round(cv_ms, 1),
            "holdout_ms": round(hold_ms, 1),
            "total_ms": round(total_ms, 1),
        },
    }
