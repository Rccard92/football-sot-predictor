"""Ricerca Fase 2A.4.1: affidabilità del residuo modello-book, sola lettura."""

from __future__ import annotations

import csv
import io
import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Callable, Iterator

import numpy as np
from sklearn.linear_model import HuberRegressor, LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from app.services.cecchino.cecchino_purchasability_audit import (
    DATASET_VERSION,
    build_purchasability_rows,
    make_json_safe,
)
from app.services.cecchino.cecchino_purchasability_fair_book import (
    DC_SELS,
    PRIMARY_MARKETS,
    SOURCE_1X2,
    SOURCE_DC_DERIVED,
    SOURCE_RAW_SECONDARY,
    SOURCE_TWO_WAY,
    build_cross_market_index,
    cross_market_snapshot_key,
    dc_cross_market_linkable,
    resolve_fair_for_rows,
)
from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
    brier,
    clip_prob,
    ece_score,
    expanding_fixture_folds,
    log_loss_score,
    paired_oof_comparison,
    ranking_economic_from_scores,
    roc_auc,
    safe_div,
    sha256_hex,
    stable_seed,
)
from app.services.cecchino.cecchino_purchasability_statistical_research import (
    order_fixtures,
)

RESIDUAL_RELIABILITY_VERSION = "cecchino_purchasability_residual_reliability_v2a_4_1"
RESIDUAL_VERSION = RESIDUAL_RELIABILITY_VERSION
SOURCE_STATISTICAL_VERSION = "cecchino_purchasability_statistical_research_v2a_2"
EPS = 1e-12
MIN_TEMPORAL_SPAN_DAYS = 90
MIN_CALENDAR_MONTHS = 3
EXPORT_KINDS = (
    "summary", "cohort", "fair-book-audit", "feature-audit", "folds", "markets",
    "binary-results", "residual-results", "paired", "economic", "decisions", "readiness",
)

_CONTEXT_NUMERIC = [
    "book_direction_probability",
    "favourite_intensity_book",
    "favourite_intensity_model",
    "comparator_odds_gap",
    "comparator_model_probability_gap",
    "comparator_book_probability_gap",
    "complement_odds_gap",
    "complement_model_probability_gap",
    "complement_book_probability_gap",
    "market_overround",
    "book_first_second_gap",
    "market_concentration",
]
_CONTEXT_CATS = [
    "canonical_market_family",
    "selection",
    "period",
    "line",
    "competition_id",
    "book_favourite",
    "model_favourite",
    "favourite_alignment",
]

SPECS: dict[str, dict[str, Any]] = {
    "BOOK_DIRECTION_BASELINE": {"numeric": [], "categorical": [], "baseline": True},
    "GAP_ONLY": {
        "numeric": ["book_direction_probability", "absolute_model_book_gap", "gap_direction_code"],
        "categorical": [],
    },
    "PRICE_MARKET_CONTEXT": {
        "numeric": ["book_direction_probability", "fair_book_probability", "market_overround"],
        "categorical": ["canonical_market_family", "selection", "period", "line"],
    },
    "RELIABILITY_CONTEXT_ONLY": {
        "numeric": list(_CONTEXT_NUMERIC),
        "categorical": list(_CONTEXT_CATS),
    },
    "GAP_RELIABILITY_CONTEXT": {
        "numeric": [
            "book_direction_probability",
            "absolute_model_book_gap",
            "gap_direction_code",
            "fair_book_probability",
            *[f for f in _CONTEXT_NUMERIC if f != "book_direction_probability"],
        ],
        "categorical": list(_CONTEXT_CATS),
    },
    "EDGE_RELIABILITY_CONTEXT_DIAGNOSTIC": {
        "numeric": ["book_direction_probability", "edge", *_CONTEXT_NUMERIC[1:]],
        "categorical": list(_CONTEXT_CATS),
        "diagnostic": True,
    },
    "SCORE_RELIABILITY_CONTEXT_DIAGNOSTIC": {
        "numeric": ["book_direction_probability", "score", *_CONTEXT_NUMERIC[1:]],
        "categorical": list(_CONTEXT_CATS),
        "diagnostic": True,
    },
    "RATING_RELIABILITY_CONTEXT_DIAGNOSTIC": {
        "numeric": ["book_direction_probability", "rating", *_CONTEXT_NUMERIC[1:]],
        "categorical": list(_CONTEXT_CATS),
        "diagnostic": True,
    },
}

PAIRED_COMPARISONS: tuple[tuple[str, str], ...] = (
    ("RELIABILITY_CONTEXT_ONLY", "BOOK_DIRECTION_BASELINE"),
    ("GAP_RELIABILITY_CONTEXT", "BOOK_DIRECTION_BASELINE"),
    ("GAP_RELIABILITY_CONTEXT", "GAP_ONLY"),
    ("PRICE_MARKET_CONTEXT", "BOOK_DIRECTION_BASELINE"),
    ("EDGE_RELIABILITY_CONTEXT_DIAGNOSTIC", "GAP_ONLY"),
    ("SCORE_RELIABILITY_CONTEXT_DIAGNOSTIC", "GAP_ONLY"),
    ("RATING_RELIABILITY_CONTEXT_DIAGNOSTIC", "GAP_ONLY"),
)

ECONOMIC_PAIRED: tuple[tuple[str, str], ...] = (
    ("GAP_RELIABILITY_CONTEXT", "GAP_ONLY"),
    ("RELIABILITY_CONTEXT_ONLY", "BOOK_DIRECTION_BASELINE"),
)

FEATURE_ROLES = {
    "absolute_model_book_gap": "magnitude_benchmark",
    "gap_direction_code": "magnitude_benchmark",
    "book_direction_probability": "magnitude_benchmark",
    "fair_book_probability": "reliability_candidate",
    "market_overround": "reliability_candidate",
    "favourite_intensity_book": "reliability_candidate",
    "favourite_intensity_model": "reliability_candidate",
    "comparator_odds_gap": "reliability_candidate",
    "comparator_model_probability_gap": "reliability_candidate",
    "comparator_book_probability_gap": "reliability_candidate",
    "complement_odds_gap": "reliability_candidate",
    "complement_model_probability_gap": "reliability_candidate",
    "complement_book_probability_gap": "reliability_candidate",
    "book_first_second_gap": "reliability_candidate",
    "market_concentration": "reliability_candidate",
    "edge": "diagnostic_benchmark",
    "score": "diagnostic_benchmark",
    "rating": "diagnostic_benchmark",
}


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _payload_gap(row: dict[str, Any], key: str, own: float | None, complement: str | None = None) -> float | None:
    payload = row.get(key)
    if not isinstance(payload, dict) or own is None:
        return None
    values = [payload.get(complement)] if complement and complement in payload else payload.values()
    for value in values:
        other = _num(value)
        if other is not None:
            return own - other
    return None


def _profit(row: dict[str, Any], y: int, odds: float) -> float:
    value = _num(row.get("unit_stake_profit"))
    return value if value is not None else (odds - 1.0 if y else -1.0)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_key(row: dict[str, Any]) -> str:
    return str(row.get("canonical_row_key") or f"{row.get('today_fixture_id')}:{row.get('selection')}:{row.get('snapshot_at')}")


def build_oof_evaluation_mask(rows: list[dict[str, Any]], folds: list[dict[str, Any]]) -> np.ndarray:
    """True solo per fixture presenti in almeno un test fold."""
    test_ids: set[Any] = set()
    for fold in folds:
        test_ids.update(fold.get("test_fixture_ids") or [])
    return np.array([r.get("today_fixture_id") in test_ids for r in rows], dtype=bool)


def _oof_evaluation_identity(
    rows: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    mask: np.ndarray,
) -> dict[str, Any]:
    oof_rows = [rows[i] for i, ok in enumerate(mask) if ok]
    oof_keys = sorted(_row_key(r) for r in oof_rows)
    oof_fids = sorted({str(r["today_fixture_id"]) for r in oof_rows})
    train_only = int((~mask).sum()) if len(mask) else 0
    union_fids = set()
    for fold in folds:
        union_fids.update(str(x) for x in (fold.get("test_fixture_ids") or []))
    return {
        "source_residual_rows": len(rows),
        "train_only_initial_rows": train_only,
        "oof_evaluable_rows": len(oof_rows),
        "oof_evaluable_fixtures": len(oof_fids),
        "oof_row_key_hash": sha256_hex(oof_keys)[:32] if oof_keys else None,
        "oof_fixture_hash": sha256_hex(oof_fids)[:32] if oof_fids else None,
        "fold_test_union_verified": set(oof_fids) == union_fids if folds else False,
    }


def _temporal_span(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dates: list[date] = []
    for r in rows:
        dt = _parse_dt(r.get("kickoff")) or _parse_dt(r.get("snapshot_at"))
        if dt is not None:
            dates.append(dt.date())
    if not dates:
        return {
            "temporal_date_min": None,
            "temporal_date_max": None,
            "temporal_span_days": 0,
            "unique_calendar_months": 0,
            "unique_match_days": 0,
            "limited_temporal_span": True,
            "min_temporal_span_days": MIN_TEMPORAL_SPAN_DAYS,
            "min_calendar_months": MIN_CALENDAR_MONTHS,
        }
    dmin, dmax = min(dates), max(dates)
    span_days = (dmax - dmin).days
    months = {(d.year, d.month) for d in dates}
    limited = span_days < MIN_TEMPORAL_SPAN_DAYS or len(months) < MIN_CALENDAR_MONTHS
    return {
        "temporal_date_min": dmin.isoformat(),
        "temporal_date_max": dmax.isoformat(),
        "temporal_span_days": span_days,
        "unique_calendar_months": len(months),
        "unique_match_days": len(set(dates)),
        "limited_temporal_span": limited,
        "min_temporal_span_days": MIN_TEMPORAL_SPAN_DAYS,
        "min_calendar_months": MIN_CALENDAR_MONTHS,
    }


def _residual_row(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Costruisce una riga analitica soltanto da osservazioni verificabili."""
    if not row.get("is_settled_core"):
        return None, "not_settled_core"
    status = row.get("settlement_status")
    if status == "void" or bool(row.get("selection_void")):
        return None, "void"
    if status not in ("won", "lost"):
        return None, "unsettled"
    if not row.get("snapshot_timestamp_verified") or not row.get("snapshot_before_kickoff"):
        return None, "snapshot_not_verified_pre_match"
    if not row.get("no_post_match_data_in_features") or row.get("leakage_status") == "excluded_leakage":
        return None, "leakage_or_post_match_feature"
    if not row.get("fair_book_probability_verified"):
        return None, "fair_book_not_verified"
    model, fair, odds = _num(row.get("model_probability")), _num(row.get("fair_book_probability")), _num(row.get("odds"))
    if model is None or fair is None:
        return None, "missing_probability"
    if odds is None or odds <= 1.0:
        return None, "invalid_odds"
    if not (0.0 <= model <= 1.0 and 0.0 <= fair <= 1.0):
        return None, "probability_out_of_range"
    gap = model - fair
    direction = 1 if gap > EPS else (-1 if gap < -EPS else 0)
    y = 1 if status == "won" or bool(row.get("selection_won")) else 0
    complement = row.get("complement_selection")
    comp_odds = _payload_gap(row, "comparator_odds_payload", odds)
    comp_model = _payload_gap(row, "comparator_model_probability_payload", model)
    comp_book = _payload_gap(row, "comparator_book_probability_payload", fair)
    c_odds = _payload_gap(row, "comparator_odds_payload", odds, complement)
    c_model = _payload_gap(row, "comparator_model_probability_payload", model, complement)
    c_book = _payload_gap(row, "comparator_book_probability_payload", fair, complement)
    norm = row.get("normalization_payload") or {}
    overround = _num(row.get("market_overround"))
    if overround is None and isinstance(norm, dict):
        overround = _num(norm.get("overround") if "overround" in norm else norm.get("overround_1x2"))
    book_dir = fair if direction > 0 else (1.0 - fair if direction < 0 else None)
    return {
        "today_fixture_id": row.get("today_fixture_id"),
        "canonical_row_key": row.get("canonical_row_key"),
        "selection": row.get("raw_market_code") or row.get("selection"),
        "canonical_market_family": row.get("canonical_market_family"),
        "period": row.get("period"),
        "line": row.get("line"),
        "competition_id": row.get("competition_id"),
        "snapshot_at": row.get("snapshot_at"),
        "kickoff": row.get("kickoff"),
        "odds": odds,
        "profit": _profit(row, y, odds),
        "y_win": y,
        "model_probability": model,
        "fair_book_probability": fair,
        "fair_book_probability_source": row.get("fair_book_probability_source"),
        "model_book_gap": gap,
        "absolute_model_book_gap": abs(gap),
        "gap_direction": "positive" if direction > 0 else ("negative" if direction < 0 else "neutral"),
        "gap_direction_code": direction,
        "book_residual": y - fair,
        "signed_book_residual": None if not direction else direction * (y - fair),
        "direction_correct": None if not direction else int((y == 1) == (direction > 0)),
        "book_direction_probability": book_dir,
        "positive_value_row": direction > 0,
        "negative_value_row": direction < 0,
        "market_overround": overround,
        "favourite_intensity_book": _num(row.get("favourite_intensity_book")),
        "favourite_intensity_model": _num(row.get("favourite_intensity_model")),
        "book_favourite": row.get("book_favourite"),
        "model_favourite": row.get("model_favourite"),
        "favourite_alignment": row.get("favourite_alignment") or "unknown",
        "comparator_odds_gap": comp_odds,
        "comparator_model_probability_gap": comp_model,
        "comparator_book_probability_gap": comp_book,
        "complement_odds_gap": c_odds,
        "complement_model_probability_gap": c_model,
        "complement_book_probability_gap": c_book,
        "book_first_second_gap": abs(comp_book) if comp_book is not None else None,
        "market_concentration": _num(row.get("market_concentration")) or _num(row.get("favourite_intensity_book")),
        "edge": _num(row.get("edge")),
        "score": _num(row.get("score")),
        "rating": _num(row.get("rating")),
    }, None


def _cohort_identity(rows: list[dict[str, Any]], exclusions: Counter[str]) -> dict[str, Any]:
    return {
        "residual_rows": len(rows),
        "fixtures": len({r["today_fixture_id"] for r in rows}),
        "markets": sorted({str(r.get("selection")) for r in rows if r.get("selection")}),
        "primary_markets_present": sorted({r.get("selection") for r in rows if r.get("selection") in PRIMARY_MARKETS}),
        "non_zero_gap_rows": sum(r["gap_direction_code"] != 0 for r in rows),
        "sensitivity_abs_gap_ge_0_005": sum(r["absolute_model_book_gap"] >= .005 for r in rows),
        "sensitivity_abs_gap_ge_0_01": sum(r["absolute_model_book_gap"] >= .01 for r in rows),
        "exclusions": dict(exclusions),
        "canonical_keys_unique": len({r.get("canonical_row_key") for r in rows if r.get("canonical_row_key")}) == len(
            [r for r in rows if r.get("canonical_row_key")]
        ),
    }


def _is_settled(row: dict[str, Any]) -> bool:
    return bool(row.get("is_settled_core")) and row.get("settlement_status") in ("won", "lost", "void")


def _market_sel(row: dict[str, Any]) -> str:
    return str(row.get("raw_market_code") or row.get("selection") or "")


def _source_count_block(
    enriched: list[dict[str, Any]],
    residuals: list[dict[str, Any]],
    *,
    settled_only: bool = False,
) -> list[dict[str, Any]]:
    residual_keys = {_row_key(r) for r in residuals}
    # residual rows lose some fields; match by selection+fixture+snapshot when possible
    residual_identity = {
        (r.get("today_fixture_id"), r.get("selection"), r.get("snapshot_at")) for r in residuals
    }
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in enriched:
        if settled_only and not _is_settled(r):
            continue
        src = str(r.get("fair_book_probability_source") or "missing")
        by_source[src].append(r)
    out = []
    for src in sorted(by_source.keys()):
        group = by_source[src]
        settled = [r for r in group if _is_settled(r)]
        verified_settled = [r for r in settled if r.get("fair_book_probability_verified")]
        residual_n = sum(
            1
            for r in group
            if (r.get("today_fixture_id"), _market_sel(r), r.get("snapshot_at")) in residual_identity
            or _row_key(r) in residual_keys
        )
        out.append({
            "source": src,
            "observed_rows": len(group) if not settled_only else len(settled),
            "settled_rows": len(settled),
            "verified_settled_rows": len(verified_settled),
            "residual_rows": residual_n,
            "verified_coverage_settled": safe_div(len(verified_settled), len(settled)),
        })
    return out


def _dc_audit(enriched: list[dict[str, Any]], residuals: list[dict[str, Any]]) -> dict[str, Any]:
    cross_idx = build_cross_market_index(enriched)
    dc_rows = [r for r in enriched if _market_sel(r) in DC_SELS]
    dc_settled = [r for r in dc_rows if _is_settled(r)]
    linkable = 0
    derived = 0
    missing_1x2 = 0
    snap_mm = 0
    book_mm = 0
    prov_mm = 0
    for r in dc_settled:
        siblings = cross_idx.get(cross_market_snapshot_key(r), [])
        if dc_cross_market_linkable(r, siblings):
            linkable += 1
        reason = str(r.get("exclusion_reason") or "")
        if r.get("fair_book_probability_source") == SOURCE_DC_DERIVED and r.get("fair_book_probability_verified"):
            derived += 1
        elif "snapshot" in reason:
            snap_mm += 1
        elif "bookmaker" in reason:
            book_mm += 1
        elif "provider" in reason:
            prov_mm += 1
        else:
            missing_1x2 += 1
    dc_residual = [r for r in residuals if r.get("selection") in DC_SELS]
    by_market = {}
    for m in sorted(DC_SELS):
        inp = [r for r in dc_rows if _market_sel(r) == m]
        sett = [r for r in inp if _is_settled(r)]
        ver = [r for r in sett if r.get("fair_book_probability_verified")]
        res = [r for r in dc_residual if r.get("selection") == m]
        by_market[m] = {
            "input_rows": len(inp),
            "settled_rows": len(sett),
            "derived_verified_rows": len(ver),
            "residual_rows": len(res),
        }
    linkage_failed = linkable > 0 and derived == 0 and len(dc_settled) > 0
    return {
        "dc_input_rows": len(dc_rows),
        "dc_settled_rows": len(dc_settled),
        "dc_cross_market_linkable_rows": linkable,
        "dc_derived_verified_rows": derived,
        "dc_residual_rows": len(dc_residual),
        "dc_missing_1x2_rows": missing_1x2,
        "dc_snapshot_mismatch_rows": snap_mm,
        "dc_bookmaker_mismatch_rows": book_mm,
        "dc_provider_mismatch_rows": prov_mm,
        "coverage_by_dc_market": by_market,
        "linkage_status": "failed" if linkage_failed else ("ok" if derived > 0 else "no_derived"),
        "dc_fair_probability_linkage_failed": linkage_failed,
    }


def _markets_status(enriched: list[dict[str, Any]], residuals: list[dict[str, Any]]) -> dict[str, Any]:
    available = sorted({_market_sel(r) for r in enriched if _market_sel(r) in PRIMARY_MARKETS})
    verified = sorted({
        _market_sel(r) for r in enriched
        if _market_sel(r) in PRIMARY_MARKETS and r.get("fair_book_probability_verified")
    })
    residual_mk = sorted({r.get("selection") for r in residuals if r.get("selection") in PRIMARY_MARKETS})
    missing = [m for m in PRIMARY_MARKETS if m not in residual_mk]
    reasons: dict[str, str] = {}
    for m in PRIMARY_MARKETS:
        src = [r for r in enriched if _market_sel(r) == m]
        if not src:
            reasons[m] = "no_source_rows"
        elif not any(r.get("fair_book_probability_verified") for r in src):
            reasons[m] = "missing_fair_probability"
        elif m not in residual_mk:
            reasons[m] = "insufficient_sample"
        else:
            reasons[m] = "evaluated"
    return {
        "markets_available": available,
        "markets_with_verified_fair_probability": verified,
        "markets_residual_evaluated": residual_mk,
        "markets_missing": missing,
        "missing_reason_by_market": reasons,
        "all_expected_markets_evaluated": len(missing) == 0,
        "expected_markets": list(PRIMARY_MARKETS),
    }


def _fair_audit(enriched: list[dict[str, Any]], residuals: list[dict[str, Any]], exclusions: Counter[str]) -> dict[str, Any]:
    mk = _markets_status(enriched, residuals)
    markets: dict[str, dict[str, Any]] = {}
    for market in PRIMARY_MARKETS:
        all_rows = [r for r in enriched if _market_sel(r) == market]
        settled = [r for r in all_rows if _is_settled(r)]
        valid = [r for r in residuals if r.get("selection") == market]
        markets[market] = {
            "input_rows": len(all_rows),
            "settled_rows": len(settled),
            "verified_fair_rows": sum(bool(r.get("fair_book_probability_verified")) for r in all_rows),
            "verified_settled_rows": sum(bool(r.get("fair_book_probability_verified")) for r in settled),
            "residual_rows": len(valid),
            "verified_coverage": safe_div(sum(bool(r.get("fair_book_probability_verified")) for r in all_rows), len(all_rows)),
            "verified_coverage_settled": safe_div(
                sum(bool(r.get("fair_book_probability_verified")) for r in settled), len(settled)
            ),
            "status": (mk.get("missing_reason_by_market") or {}).get(market),
        }
    observed = _source_count_block(enriched, residuals, settled_only=False)
    settled_counts = _source_count_block(enriched, residuals, settled_only=True)
    residual_by_src = Counter(str(r.get("fair_book_probability_source") or "missing") for r in residuals)
    residual_counts = [
        {
            "source": k,
            "observed_rows": next((x["observed_rows"] for x in observed if x["source"] == k), 0),
            "settled_rows": next((x["settled_rows"] for x in settled_counts if x["source"] == k), 0),
            "verified_settled_rows": next((x["verified_settled_rows"] for x in settled_counts if x["source"] == k), 0),
            "residual_rows": residual_by_src.get(k, 0),
            "verified_coverage_settled": next(
                (x["verified_coverage_settled"] for x in settled_counts if x["source"] == k), None
            ),
        }
        for k in sorted(set(list(residual_by_src) + [x["source"] for x in observed]))
    ]
    # legacy compact sources list
    sources_legacy = [
        {
            "source": x["source"],
            "rows": x["observed_rows"],
            "verified_rows": x["verified_settled_rows"],
            "observed_rows": x["observed_rows"],
            "settled_rows": x["settled_rows"],
            "verified_settled_rows": x["verified_settled_rows"],
            "residual_rows": x["residual_rows"],
            "verified_coverage_settled": x["verified_coverage_settled"],
        }
        for x in observed
    ]
    dc = _dc_audit(enriched, residuals)
    return {
        "sources": sources_legacy,
        "all_observed_source_counts": observed,
        "settled_source_counts": settled_counts,
        "residual_source_counts": residual_counts,
        "source_definitions": [SOURCE_1X2, SOURCE_TWO_WAY, SOURCE_DC_DERIVED, SOURCE_RAW_SECONDARY],
        "residual_exclusions": dict(exclusions),
        "coverage_by_market": markets,
        "double_chance": dc,
        **mk,
    }


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    try:
        rx = np.argsort(np.argsort(np.asarray(xs, dtype=float))).astype(float)
        ry = np.argsort(np.argsort(np.asarray(ys, dtype=float))).astype(float)
        return float(np.corrcoef(rx, ry)[0, 1]) if np.std(rx) and np.std(ry) else None
    except Exception:  # noqa: BLE001
        return None


def _feature_audit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for feature, role in FEATURE_ROLES.items():
        pairs = [(float(r[feature]), r["absolute_model_book_gap"], r["fair_book_probability"]) for r in rows if _num(r.get(feature)) is not None]
        values = [x[0] for x in pairs]
        result.append({
            "feature": feature, "role": role, "coverage": safe_div(len(pairs), len(rows)),
            "n_available": len(pairs),
            "spearman_with_absolute_gap": _spearman(values, [x[1] for x in pairs]),
            "spearman_with_fair_book": _spearman(values, [x[2] for x in pairs]),
            "status": "available" if pairs else "unavailable",
        })
    return result


def _matrix(train: list[dict[str, Any]], test: list[dict[str, Any]], numeric: list[str], categorical: list[str]) -> tuple[np.ndarray, np.ndarray]:
    def numeric_values(source: list[dict[str, Any]]) -> np.ndarray:
        return np.array([[_num(r.get(f)) if _num(r.get(f)) is not None else np.nan for f in numeric] for r in source], dtype=float)
    a, b = numeric_values(train), numeric_values(test)
    if numeric:
        means = np.array(
            [
                float(np.mean(column[np.isfinite(column)]))
                if np.any(np.isfinite(column))
                else 0.0
                for column in a.T
            ],
            dtype=float,
        )
        a = np.where(np.isfinite(a), a, means)
        b = np.where(np.isfinite(b), b, means)
        scaler = StandardScaler()
        a, b = scaler.fit_transform(a), scaler.transform(b)
    else:
        a, b = np.empty((len(train), 0)), np.empty((len(test), 0))
    for feature in categorical:
        levels = sorted({str(r.get(feature)) for r in train if r.get(feature) is not None})
        if not levels:
            continue
        index = {value: i for i, value in enumerate(levels)}
        def one_hot(source: list[dict[str, Any]]) -> np.ndarray:
            out = np.zeros((len(source), len(index)), dtype=float)
            for i, row in enumerate(source):
                j = index.get(str(row.get(feature)))
                if j is not None:
                    out[i, j] = 1.0
            return out
        a, b = np.hstack((a, one_hot(train))), np.hstack((b, one_hot(test)))
    return a, b


def _fit_oof(rows: list[dict[str, Any]], folds: list[dict[str, Any]], spec: dict[str, Any], *, residual: bool = False, huber: bool = False) -> tuple[np.ndarray, list[dict[str, Any]]]:
    pred, reports = np.full(len(rows), np.nan), []
    for fold in folds:
        train_ids, test_ids = set(fold["train_fixture_ids"]), set(fold["test_fixture_ids"])
        train_idx = [i for i, r in enumerate(rows) if r["today_fixture_id"] in train_ids]
        test_idx = [i for i, r in enumerate(rows) if r["today_fixture_id"] in test_ids]
        target = "signed_book_residual" if residual else "direction_correct"
        train_idx = [i for i in train_idx if rows[i].get(target) is not None]
        test_idx = [i for i in test_idx if rows[i].get(target) is not None]
        report = {"fold": fold["fold"], "train_fixtures": len(train_ids), "test_fixtures": len(test_ids), "train_rows": len(train_idx), "test_rows": len(test_idx), "fixture_overlap": len(train_ids & test_ids)}
        if len(train_idx) < 8 or not test_idx:
            report["skipped"] = True; reports.append(report); continue
        y = np.asarray([rows[i][target] for i in train_idx], dtype=float)
        if not residual and len(np.unique(y)) < 2:
            report["skipped"] = True; report["reason"] = "single_class_train"; reports.append(report); continue
        try:
            Xtr, Xte = _matrix([rows[i] for i in train_idx], [rows[i] for i in test_idx], spec["numeric"], spec["categorical"])
            model = (HuberRegressor() if huber else Ridge(alpha=1.0)) if residual else LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
            model.fit(Xtr, y)
            values = model.predict(Xte) if residual else model.predict_proba(Xte)[:, 1]
            pred[test_idx] = values
            report["skipped"] = False
        except Exception as exc:  # noqa: BLE001
            report["skipped"] = True; report["reason"] = str(exc)[:160]
        reports.append(report)
    return pred, reports


def _binary_metrics(rows: list[dict[str, Any]], pred: np.ndarray, *, oof_mask: np.ndarray | None = None) -> dict[str, Any]:
    n_source = len(rows)
    if oof_mask is not None and len(oof_mask) == len(rows):
        eligible = [i for i, ok in enumerate(oof_mask) if ok and rows[i].get("direction_correct") is not None]
    else:
        eligible = [i for i, r in enumerate(rows) if r.get("direction_correct") is not None]
    idx = [i for i in eligible if np.isfinite(pred[i])]
    missing = len(eligible) - len(idx)
    keys = sorted(_row_key(rows[i]) for i in idx)
    if not idx:
        return {
            "status": "no_oof",
            "n_source": n_source,
            "n_oof": 0,
            "oof_coverage": 0.0,
            "missing_prediction_rows": missing,
            "evaluation_row_key_hash": None,
        }
    y, p = np.array([rows[i]["direction_correct"] for i in idx]), np.clip(pred[idx], 1e-6, 1 - 1e-6)
    return {
        "status": "ok",
        "n_source": n_source,
        "n_oof": len(idx),
        "oof_coverage": safe_div(len(idx), n_source),
        "missing_prediction_rows": missing,
        "evaluation_row_key_hash": sha256_hex(keys)[:32],
        "auc": roc_auc(y, p),
        "brier": brier(y, p),
        "log_loss": log_loss_score(y, p),
        "ece": ece_score(y, p),
        "accuracy": float(np.mean((p >= .5) == y)),
    }


def _residual_metrics(rows: list[dict[str, Any]], pred: np.ndarray) -> dict[str, Any]:
    idx = [i for i, r in enumerate(rows) if r.get("signed_book_residual") is not None and np.isfinite(pred[i])]
    if not idx:
        return {"status": "no_oof", "n_oof": 0}
    y, p = np.array([rows[i]["signed_book_residual"] for i in idx]), pred[idx]
    return {"status": "ok", "n_oof": len(idx), "mae": float(np.mean(abs(y - p))), "rmse": float(np.sqrt(np.mean((y - p) ** 2))), "correlation": float(np.corrcoef(y, p)[0, 1]) if len(y) > 2 and np.std(y) and np.std(p) else None}


def _baseline_prediction(rows: list[dict[str, Any]], oof_mask: np.ndarray) -> np.ndarray:
    """Baseline densa solo sulla maschera OOF; fuori → NaN."""
    pred = np.full(len(rows), np.nan)
    for i, r in enumerate(rows):
        if not oof_mask[i]:
            continue
        if r.get("book_direction_probability") is not None:
            pred[i] = clip_prob(r["book_direction_probability"])
    return pred


def _economic(
    rows: list[dict[str, Any]],
    predictions: dict[str, np.ndarray],
    oof_mask: np.ndarray,
    *,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    source_pos = [i for i, r in enumerate(rows) if r.get("positive_value_row")]
    oof_pos = [i for i in source_pos if oof_mask[i]]
    out: dict[str, Any] = {
        "positive_value_rows": len(source_pos),
        "source_positive_rows": len(source_pos),
        "oof_positive_rows": len(oof_pos),
        "oof_coverage": safe_div(len(oof_pos), len(source_pos)),
        "stake": 1,
        "by_specification": {},
        "paired_comparisons": {},
    }
    for name, pred in predictions.items():
        valid = [i for i in oof_pos if np.isfinite(pred[i])]
        block = ranking_economic_from_scores(
            np.array([rows[i]["profit"] for i in valid], dtype=float),
            pred[valid],
        ) if valid else {}
        block.update({
            "source_positive_rows": len(source_pos),
            "oof_positive_rows": len(valid),
            "oof_coverage": safe_div(len(valid), len(source_pos)),
        })
        out["by_specification"][name] = block

    for cand, base in ECONOMIC_PAIRED:
        if cand not in predictions or base not in predictions:
            continue
        pc, pb = predictions[cand], predictions[base]
        paired_idx = [
            i for i in oof_pos
            if np.isfinite(pc[i]) and np.isfinite(pb[i])
        ]
        keys = sorted(_row_key(rows[i]) for i in paired_idx)
        if not paired_idx:
            out["paired_comparisons"][f"{cand}_vs_{base}"] = {
                "status": "no_paired_rows",
                "paired_rows": 0,
                "same_evaluation_cohort": True,
            }
            continue
        profits = np.array([rows[i]["profit"] for i in paired_idx], dtype=float)
        sc = pc[paired_idx]
        sb = pb[paired_idx]
        fids = np.array([rows[i]["today_fixture_id"] for i in paired_idx])
        eco_c = ranking_economic_from_scores(profits, sc)
        eco_b = ranking_economic_from_scores(profits, sb)

        def _delta(a: Any, b: Any) -> float | None:
            if a is None or b is None:
                return None
            return float(a) - float(b)

        # fixture-clustered CI on ROI top 10% delta via bootstrap of per-fixture contribution proxy
        # Use score-rank ROI difference recomputed each bootstrap sample
        rng = np.random.default_rng(stable_seed(seed, f"eco:{cand}:{base}"))
        groups: dict[Any, list[int]] = defaultdict(list)
        for local_i, fid in enumerate(fids):
            groups[fid].append(local_i)
        uniq = list(groups.keys())
        boot10: list[float] = []
        boot20: list[float] = []
        boot_q: list[float] = []
        for _ in range(max(1, bootstrap_iterations)):
            sample = rng.choice(uniq, size=len(uniq), replace=True)
            idx = np.concatenate([np.asarray(groups[f], dtype=int) for f in sample])
            rc = ranking_economic_from_scores(profits[idx], sc[idx])
            rb = ranking_economic_from_scores(profits[idx], sb[idx])
            d10 = _delta(rc.get("roi_top_10pct"), rb.get("roi_top_10pct"))
            d20 = _delta(rc.get("roi_top_20pct"), rb.get("roi_top_20pct"))
            dq = _delta(rc.get("roi_top_quintile"), rb.get("roi_top_quintile"))
            if d10 is not None:
                boot10.append(d10)
            if d20 is not None:
                boot20.append(d20)
            if dq is not None:
                boot_q.append(dq)

        def _ci(vals: list[float], est: float | None) -> dict[str, Any]:
            if not vals:
                return {"estimate": est, "ci_low": None, "ci_high": None, "iterations": bootstrap_iterations}
            arr = np.asarray(vals, dtype=float)
            return {
                "estimate": est if est is not None else float(np.mean(arr)),
                "ci_low": float(np.percentile(arr, 2.5)),
                "ci_high": float(np.percentile(arr, 97.5)),
                "iterations": bootstrap_iterations,
            }

        d10 = _delta(eco_c.get("roi_top_10pct"), eco_b.get("roi_top_10pct"))
        d20 = _delta(eco_c.get("roi_top_20pct"), eco_b.get("roi_top_20pct"))
        dq = _delta(eco_c.get("roi_top_quintile"), eco_b.get("roi_top_quintile"))
        out["paired_comparisons"][f"{cand}_vs_{base}"] = {
            "status": "ok",
            "paired_rows": len(paired_idx),
            "paired_row_key_hash": sha256_hex(keys)[:32],
            "same_evaluation_cohort": True,
            "delta_roi_top_10pct": d10,
            "delta_roi_top_20pct": d20,
            "delta_roi_top_quintile": dq,
            "ci_delta_roi_top_10pct": _ci(boot10, d10),
            "ci_delta_roi_top_20pct": _ci(boot20, d20),
            "ci_delta_roi_top_quintile": _ci(boot_q, dq),
        }
    return out


def _paired_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**r, "y_win": r.get("direction_correct")} for r in rows]


def _enrich_paired(paired: dict[str, Any], rows: list[dict[str, Any]], predictions: dict[str, np.ndarray]) -> dict[str, Any]:
    out = {}
    for key, val in paired.items():
        block = dict(val)
        parts = key.split("_vs_")
        if len(parts) == 2 and parts[0] in predictions and parts[1] in predictions:
            pc, pb = predictions[parts[0]], predictions[parts[1]]
            idx = [i for i in range(len(rows)) if np.isfinite(pc[i]) and np.isfinite(pb[i])]
            keys = sorted(_row_key(rows[i]) for i in idx)
            block["paired_n"] = len(idx)
            block["paired_row_key_hash"] = sha256_hex(keys)[:32] if keys else None
            block["same_evaluation_cohort"] = True
        out[key] = block
    return out


def _readiness(
    rows: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    binary: dict[str, Any],
    paired: dict[str, Any],
    limitations: list[str],
    temporal: dict[str, Any],
    markets_info: dict[str, Any],
    dc_audit: dict[str, Any],
    *,
    fair_verified: bool,
    canonical_keys_unique: bool,
    blocking_extra: list[str] | None = None,
) -> dict[str, Any]:
    del binary
    decisive = paired.get("GAP_RELIABILITY_CONTEXT_vs_GAP_ONLY") or {}
    context = paired.get("GAP_RELIABILITY_CONTEXT_vs_BOOK_DIRECTION_BASELINE") or {}
    rating_vs_gap = paired.get("RATING_RELIABILITY_CONTEXT_DIAGNOSTIC_vs_GAP_ONLY") or {}
    better_gap = (decisive.get("delta_auc") or 0) > 0 and (
        (decisive.get("delta_brier_improvement") or 0) >= -1e-9
    )
    better_book = (context.get("delta_auc") or 0) > 0
    rating_only = (rating_vs_gap.get("delta_auc") or 0) > 0 and not better_gap
    markets = {r["selection"] for r in rows if r.get("selection") in PRIMARY_MARKETS}
    blocking: list[str] = list(blocking_extra or [])
    if not rows:
        blocking.append("empty_cohort")
    if not fair_verified:
        blocking.append("fair_book_probability_unverified")
    if not canonical_keys_unique:
        blocking.append("duplicated_canonical_row_key")
    if dc_audit.get("dc_fair_probability_linkage_failed"):
        blocking.append("dc_fair_probability_linkage_failed")
    limited = bool(temporal.get("limited_temporal_span"))
    if limited and "limited_temporal_span" not in limitations:
        limitations.append("limited_temporal_span")
    context_specs_vs_book = []
    context_specs_vs_gap = []
    for key, val in paired.items():
        if (val.get("delta_auc") or 0) <= 0:
            continue
        if key.endswith("_vs_BOOK_DIRECTION_BASELINE") and "DIAGNOSTIC" not in key:
            context_specs_vs_book.append(key.split("_vs_")[0])
        if key.endswith("_vs_GAP_ONLY") and "DIAGNOSTIC" not in key:
            context_specs_vs_gap.append(key.split("_vs_")[0])

    reason_codes: list[str] = []
    span_days = int(temporal.get("temporal_span_days") or 0)
    if limited:
        reason_codes.append(f"limited_temporal_span_{span_days}_days")
    if not markets_info.get("all_expected_markets_evaluated"):
        missing_dc = [m for m in DC_SELS if m in (markets_info.get("markets_missing") or [])]
        if missing_dc:
            reason_codes.append("double_chance_not_evaluated")
    if markets_info.get("all_expected_markets_evaluated"):
        reason_codes.append("all_primary_markets_evaluated")
    if not better_gap:
        reason_codes.append("context_negative_vs_gap")
    reason_codes.append("no_positive_economic_ranking")

    # Ordine readiness §10
    if blocking:
        next_step = "resolve_data_quality"
    elif (
        better_gap
        and better_book
        and len(markets) >= 2
        and len(folds) >= 2
        and not rating_only
        and not limited
    ):
        next_step = "phase_2b_reliability_candidate_construction"
    elif better_book and better_gap and len(markets) == 1 and not limited:
        next_step = "phase_2b_market_specific_reliability_candidate"
    elif limited or len(rows) < 30 or len(folds) < 2:
        next_step = "continue_data_collection"
    else:
        next_step = "stop_context_no_incremental_reliability"

    return {
        "cohort_valid": bool(rows) and not blocking,
        "fair_book_probability_verified": fair_verified,
        "canonical_keys_unique": canonical_keys_unique,
        "fixture_grouping_verified": all(
            (f.get("fixture_overlap") or 0) == 0 for f in folds
        ) if folds else False,
        "temporal_cv_completed": bool(folds),
        "limited_temporal_span": limited,
        "temporal_span_days": span_days,
        "unique_calendar_months": temporal.get("unique_calendar_months"),
        "residual_core_rows": len(rows),
        "unique_fixtures": len({r["today_fixture_id"] for r in rows}),
        "markets_evaluated": sorted(markets),
        "markets_expected": list(PRIMARY_MARKETS),
        "all_expected_markets_evaluated": markets_info.get("all_expected_markets_evaluated"),
        "context_specs_positive_vs_book": context_specs_vs_book,
        "context_specs_positive_vs_gap_only": context_specs_vs_gap,
        "market_specific_context_specs": context_specs_vs_gap if len(markets) == 1 else [],
        "features_retained": [],
        "features_market_specific": [],
        "features_redundant_with_gap": [],
        "features_unstable": [],
        "economic_ranking_positive": False,
        "residual_ranking_positive": False,
        "blocking_issues": blocking,
        "limitations": list(limitations),
        "readiness_reason_codes": reason_codes,
        "context_beats_book": better_book,
        "context_beats_gap_only_or_residual_add": better_gap,
        "rating_alone_does_not_authorize": True,
        "recommended_next_step": next_step,
    }


def _decisions(audit: list[dict[str, Any]], paired: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisive = paired.get("GAP_RELIABILITY_CONTEXT_vs_GAP_ONLY") or {}
    positive = (decisive.get("delta_auc") or 0) > 0
    output = []
    for item in audit:
        feature, role = item["feature"], item["role"]
        if item["status"] == "unavailable":
            decision = "unavailable"
        elif role == "diagnostic_benchmark":
            decision = "diagnostic_benchmark_only"
        elif feature in ("absolute_model_book_gap", "gap_direction_code", "book_direction_probability"):
            decision = "gap_magnitude_benchmark_only"
        elif item["coverage"] < .5:
            decision = "insufficient_evidence"
        elif abs(item.get("spearman_with_absolute_gap") or 0) > .98:
            decision = "redundant_with_gap"
        elif positive and len({r["selection"] for r in rows}) >= 2:
            decision = "retain_reliability_candidate"
        else:
            decision = "insufficient_evidence"
        output.append({"feature": feature, "role": role, "decision": decision, "coverage": item["coverage"]})
    return output


def build_residual_summary_payload(full: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "status", "version", "dataset_version", "source_statistical_version",
        "cohort_identity", "oof_evaluation_identity", "temporal_span",
        "fair_book_probability_audit", "phase_2b_residual_readiness",
        "limitations", "filters", "elapsed_ms", "research_banner",
        "no_db_writes", "no_purchasability_formula",
    )
    return {key: full.get(key) for key in keys}


def build_purchasability_residual_reliability(
    db, *, date_from: date | None = None, date_to: date | None = None, competition_id: int | None = None,
    market_family: str | None = None, selection: str | None = None, bootstrap_iterations: int = 200,
    seed: int = 42, rows: list[dict[str, Any]] | None = None,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def progress(stage: str, meta: dict[str, Any] | None = None) -> None:
        if progress_callback:
            try: progress_callback(stage, dict(meta or {}))
            except Exception: pass
    started = time.perf_counter()
    progress("loading_dataset", {"bootstrap_iterations": bootstrap_iterations})
    raw = rows if rows is not None else build_purchasability_rows(db, date_from=date_from, date_to=date_to, competition_id=competition_id, market_family=market_family)
    progress("resolving_fair_book_probability", {"rows": len(raw)})
    fair_rows = resolve_fair_for_rows(raw)
    progress("building_residual_targets", {})
    exclusions: Counter[str] = Counter()
    residuals = []
    for row in fair_rows:
        item, reason = _residual_row(row)
        if item is None:
            exclusions[reason or "unknown"] += 1
        elif item["gap_direction_code"] == 0:
            exclusions["neutral_model_book_gap"] += 1
        else:
            residuals.append(item)
    if selection:
        residuals = [r for r in residuals if r.get("selection") == selection]
    identity = _cohort_identity(residuals, exclusions)
    fair_audit = _fair_audit(fair_rows, residuals, exclusions)
    temporal = _temporal_span(residuals)
    limitations: list[str] = []
    if temporal.get("limited_temporal_span"):
        limitations.append("limited_temporal_span")
    progress("feature_audit", {"residual_rows": len(residuals)})
    audit = _feature_audit(residuals)
    progress("temporal_cv", {})
    fixtures = order_fixtures(residuals) if residuals else []
    folds, fold_limitations = expanding_fixture_folds(fixtures)
    for lim in fold_limitations:
        if lim not in limitations:
            limitations.append(lim)
    oof_mask = build_oof_evaluation_mask(residuals, folds) if residuals else np.array([], dtype=bool)
    oof_identity = _oof_evaluation_identity(residuals, folds, oof_mask)
    binary_results: dict[str, Any] = {}
    residual_results: dict[str, Any] = {}
    predictions: dict[str, np.ndarray] = {}
    fold_reports: dict[str, list[dict[str, Any]]] = {}
    for name, spec in SPECS.items():
        if name == "BOOK_DIRECTION_BASELINE":
            pred = _baseline_prediction(residuals, oof_mask)
            reports = [{"fold": f["fold"], "baseline": True, "skipped": False, "oof_masked": True} for f in folds]
        else:
            pred, reports = _fit_oof(residuals, folds, spec)
        predictions[name] = pred
        fold_reports[name] = reports
        binary_results[name] = {
            **_binary_metrics(residuals, pred, oof_mask=oof_mask),
            "diagnostic_only": bool(spec.get("diagnostic")),
        }
        if name != "BOOK_DIRECTION_BASELINE":
            ridge, _ = _fit_oof(residuals, folds, spec, residual=True)
            huber, _ = _fit_oof(residuals, folds, spec, residual=True, huber=True)
            residual_results[name] = {"ridge": _residual_metrics(residuals, ridge), "huber_diagnostic": _residual_metrics(residuals, huber)}
    progress("paired_bootstrap", {})
    paired: dict[str, Any] = {}
    mapped = _paired_rows(residuals)
    for candidate, baseline in PAIRED_COMPARISONS:
        if candidate not in predictions or baseline not in predictions:
            continue
        paired[f"{candidate}_vs_{baseline}"] = paired_oof_comparison(
            mapped,
            predictions[candidate],
            predictions[baseline],
            bootstrap_iterations=max(1, int(bootstrap_iterations)),
            seed=stable_seed(seed, f"{candidate}:{baseline}"),
        )
    paired = _enrich_paired(paired, residuals, predictions)
    progress("economic_diagnostics", {})
    economic = _economic(
        residuals, predictions, oof_mask,
        bootstrap_iterations=max(1, int(bootstrap_iterations)),
        seed=seed,
    )
    decisions = _decisions(audit, paired, residuals)
    markets_info = {
        "markets_available": fair_audit.get("markets_available"),
        "markets_with_verified_fair_probability": fair_audit.get("markets_with_verified_fair_probability"),
        "markets_residual_evaluated": fair_audit.get("markets_residual_evaluated"),
        "markets_missing": fair_audit.get("markets_missing"),
        "missing_reason_by_market": fair_audit.get("missing_reason_by_market"),
        "all_expected_markets_evaluated": fair_audit.get("all_expected_markets_evaluated"),
    }
    readiness = _readiness(
        residuals,
        folds,
        binary_results,
        paired,
        limitations,
        temporal,
        markets_info,
        fair_audit.get("double_chance") or {},
        fair_verified=bool(residuals),
        canonical_keys_unique=bool(identity.get("canonical_keys_unique")),
    )
    settled_source = sum(1 for r in fair_rows if _is_settled(r))
    progress("building_payload", {})
    market_results = []
    for market in PRIMARY_MARKETS:
        n = sum(r.get("selection") == market for r in residuals)
        status = (fair_audit.get("missing_reason_by_market") or {}).get(market, "no_source_rows")
        market_results.append({
            "market": market,
            "rows": n,
            "fixtures": len({r["today_fixture_id"] for r in residuals if r.get("selection") == market}),
            "status": status if n == 0 else "evaluated",
        })
    payload = {
        "status": "ok",
        "version": RESIDUAL_RELIABILITY_VERSION,
        "dataset_version": DATASET_VERSION,
        "source_statistical_version": SOURCE_STATISTICAL_VERSION,
        "source_settled_rows": settled_source,
        "cohort_identity": identity,
        "oof_evaluation_identity": oof_identity,
        "temporal_span": temporal,
        "fair_book_probability_audit": fair_audit,
        "residual_feature_audit": audit,
        "temporal_folds": folds,
        "fold_reports": fold_reports,
        "market_results": market_results,
        "binary_results": binary_results,
        "residual_results": residual_results,
        "paired_comparisons": paired,
        "economic_diagnostics": economic,
        "feature_decisions": decisions,
        "phase_2b_residual_readiness": readiness,
        "limitations": limitations,
        "filters": {
            "date_from": str(date_from) if date_from else None,
            "date_to": str(date_to) if date_to else None,
            "competition_id": competition_id,
            "market_family": market_family,
            "selection": selection,
            "bootstrap_iterations": bootstrap_iterations,
            "seed": seed,
        },
        "research_banner": (
            "Questa fase studia l’affidabilità del disaccordo tra Cecchino e Book. "
            "Non calcola ancora l’Indice di Acquistabilità e non influenza i Segnali."
        ),
        "no_db_writes": True,
        "no_purchasability_formula": True,
        "elapsed_ms": {"total": round((time.perf_counter() - started) * 1000, 2)},
    }
    if not residuals:
        payload["limitations"].append("empty_residual_cohort")
        payload["phase_2b_residual_readiness"] = {
            "cohort_valid": False,
            "fair_book_probability_verified": False,
            "canonical_keys_unique": True,
            "fixture_grouping_verified": False,
            "temporal_cv_completed": False,
            "limited_temporal_span": True,
            "residual_core_rows": 0,
            "unique_fixtures": 0,
            "markets_evaluated": [],
            "blocking_issues": ["empty_cohort"],
            "limitations": ["empty_residual_cohort"],
            "readiness_reason_codes": ["limited_temporal_span_0_days"],
            "recommended_next_step": "continue_data_collection",
        }
    progress("serializing_result", {})
    output = make_json_safe(payload)
    json.dumps(output, allow_nan=False)
    progress("completed", {"status": output["status"]})
    return output


def _csv(rows: list[dict[str, Any]]) -> str:
    flat = [{k: json.dumps(make_json_safe(v), ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows]
    if not flat:
        return ""
    fields = sorted({key for row in flat for key in row})
    out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader(); writer.writerows(flat)
    return out.getvalue()


def stream_residual_export(db, kind: str, **kwargs: Any) -> Iterator[str]:
    if kind not in EXPORT_KINDS:
        yield json.dumps({"status": "error", "error": "unknown_export_kind", "kind": kind}, allow_nan=False); return
    full = build_purchasability_residual_reliability(db, **kwargs)
    json_exports = {
        "summary": lambda: build_residual_summary_payload(full), "cohort": lambda: full.get("cohort_identity", {}),
        "fair-book-audit": lambda: full.get("fair_book_probability_audit", {}),
        "readiness": lambda: full.get("phase_2b_residual_readiness", {}),
        "economic": lambda: full.get("economic_diagnostics", {}),
    }
    csv_exports = {
        "feature-audit": lambda: full.get("residual_feature_audit", []), "folds": lambda: full.get("temporal_folds", []),
        "markets": lambda: full.get("market_results", []),
        "binary-results": lambda: [{"specification": k, **v} for k, v in (full.get("binary_results") or {}).items()],
        "residual-results": lambda: [{"specification": k, **v} for k, v in (full.get("residual_results") or {}).items()],
        "paired": lambda: [{"comparison": k, **v} for k, v in (full.get("paired_comparisons") or {}).items()],
        "decisions": lambda: full.get("feature_decisions", []),
    }
    if kind in json_exports:
        yield json.dumps(make_json_safe(json_exports[kind]()), ensure_ascii=False, allow_nan=False, indent=2)
    else:
        yield _csv(make_json_safe(csv_exports[kind]()))


def residual_export_filename(kind: str) -> str:
    extension = "json" if kind in {"summary", "cohort", "fair-book-audit", "economic", "readiness"} else "csv"
    return f"purchasability_residual_reliability_v2a_4_1_{kind}.{extension}"
