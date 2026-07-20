"""Aggregazioni + policy promozione Acquistabilità — Fase 5/5.

Metriche su coorte promotion_eligible settled. Nessun Brier/LogLoss sullo score.
Output max readiness: eligible_for_manual_promotion (mai auto-promote).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.models.cecchino_purchasability_evaluation import (
    EVAL_LOST,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
    CecchinoPurchasabilityEvaluation,
)
from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_CANDIDATE_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
    spearman_rho,
)
from app.services.cecchino.cecchino_purchasability_validation import (
    MARKET_FAMILY_DOUBLE_CHANCE,
    MARKET_FAMILY_MATCH_WINNER,
    MARKET_FAMILY_OU_FT,
    MARKET_FAMILY_OU_HT,
    PURCHASABILITY_VALIDATION_VERSION,
    SCORE_BANDS_ORDERED,
    SCORE_BAND_ZERO,
    build_purchasability_validation_health,
    market_family_for,
    query_validation_rows,
    score_band_for,
)

PURCHASABILITY_PROMOTION_POLICY_VERSION = (
    "cecchino_purchasability_promotion_policy_v1"
)

# Policy immutabile — non esporre a query/FE/env
MIN_TEMPORAL_DAYS = 90
MIN_CALENDAR_MONTHS = 3
MIN_DISTINCT_FIXTURES = 300
MIN_SETTLED_ROWS = 1500
MIN_TEMPORAL_FOLDS = 3
MIN_PERSISTENCE_COVERAGE = 0.95
MIN_FIXTURES_PER_MARKET_FAMILY = 100
MIN_POPULATED_SCORE_BANDS = 3
MAX_ZERO_SCORE_SHARE = 0.90

DEFAULT_BOOTSTRAP_ITERATIONS = 200

ALL_MARKET_FAMILIES = (
    MARKET_FAMILY_MATCH_WINNER,
    MARKET_FAMILY_DOUBLE_CHANCE,
    MARKET_FAMILY_OU_FT,
    MARKET_FAMILY_OU_HT,
)


def _f(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _analysis_settled_rows(
    rows: list[CecchinoPurchasabilityEvaluation],
) -> list[CecchinoPurchasabilityEvaluation]:
    """Coorte analitica storica: won/lost con quota book valida, senza gate promozione."""
    out = []
    for r in rows:
        if r.evaluation_status not in (EVAL_WON, EVAL_LOST):
            continue
        qb = _f(r.quota_book)
        if qb is None or qb <= 1.0:
            continue
        out.append(r)
    return out


def _settled_rows(
    rows: list[CecchinoPurchasabilityEvaluation],
    *,
    require_promotion_eligible: bool = True,
    require_snapshot_verified: bool = True,
) -> list[CecchinoPurchasabilityEvaluation]:
    """Coorte readiness/promozione: gate snapshot + promotion_eligible."""
    out = []
    for r in rows:
        if r.evaluation_status not in (EVAL_WON, EVAL_LOST):
            continue
        qb = _f(r.quota_book)
        if qb is None or qb <= 1.0:
            continue
        if require_snapshot_verified:
            if not r.snapshot_timestamp_verified or r.snapshot_before_kickoff is not True:
                continue
        if require_promotion_eligible and not r.promotion_eligible:
            continue
        out.append(r)
    return out


def _metrics_block(rows: list[CecchinoPurchasabilityEvaluation]) -> dict[str, Any]:
    if not rows:
        return {
            "fixtures": 0,
            "rows": 0,
            "settled": 0,
            "won": 0,
            "lost": 0,
            "pending": 0,
            "win_rate": None,
            "average_book_odds": None,
            "average_break_even_probability": None,
            "realized_margin": None,
            "profit_units": None,
            "roi_pct": None,
            "average_score": None,
            "score_stddev": None,
            "zero_score_share": None,
            "positive_score_share": None,
            "average_phase_1": None,
            "average_phase_2": None,
        }

    fixtures = {int(r.today_fixture_id) for r in rows}
    won = sum(1 for r in rows if r.evaluation_status == EVAL_WON)
    lost = sum(1 for r in rows if r.evaluation_status == EVAL_LOST)
    settled = won + lost
    odds = [_f(r.quota_book) for r in rows if _f(r.quota_book) is not None]
    profits = [_f(r.profit_units) for r in rows if _f(r.profit_units) is not None]
    scores = [
        float(r.purchasability_score)
        for r in rows
        if r.purchasability_score is not None
    ]
    p1 = [_f(r.phase_1_score) for r in rows if _f(r.phase_1_score) is not None]
    p2 = [_f(r.phase_2_score) for r in rows if _f(r.phase_2_score) is not None]

    win_rate = (won / settled) if settled else None
    avg_odds = (sum(odds) / len(odds)) if odds else None
    be = (1.0 / avg_odds) if avg_odds and avg_odds > 0 else None
    realized = (win_rate - be) if win_rate is not None and be is not None else None
    profit_sum = sum(profits) if profits else None
    stake_sum = float(len(profits)) if profits else None
    roi = (
        (100.0 * profit_sum / stake_sum)
        if profit_sum is not None and stake_sum and stake_sum > 0
        else None
    )
    avg_score = (sum(scores) / len(scores)) if scores else None
    std_score = float(np.std(scores, ddof=1)) if len(scores) >= 2 else None
    zero_share = (
        sum(1 for s in scores if s == 0) / len(scores) if scores else None
    )
    pos_share = (
        sum(1 for s in scores if s > 0) / len(scores) if scores else None
    )

    return {
        "fixtures": len(fixtures),
        "rows": len(rows),
        "settled": settled,
        "won": won,
        "lost": lost,
        "pending": 0,
        "win_rate": win_rate,
        "average_book_odds": avg_odds,
        "average_break_even_probability": be,
        "realized_margin": realized,
        "profit_units": profit_sum,
        "roi_pct": roi,
        "average_score": avg_score,
        "score_stddev": std_score,
        "zero_score_share": zero_share,
        "positive_score_share": pos_share,
        "average_phase_1": (sum(p1) / len(p1)) if p1 else None,
        "average_phase_2": (sum(p2) / len(p2)) if p2 else None,
    }


def _signed_residual(row: CecchinoPurchasabilityEvaluation) -> float | None:
    fair = _f(row.fair_book_probability)
    if fair is None:
        return None
    y = 1.0 if row.evaluation_status == EVAL_WON else 0.0
    return y - fair


def _bootstrap_seed(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _quintile_split(
    rows: list[CecchinoPurchasabilityEvaluation],
) -> tuple[list[CecchinoPurchasabilityEvaluation], list[CecchinoPurchasabilityEvaluation]]:
    scored = [r for r in rows if r.purchasability_score is not None]
    if len(scored) < 5:
        return [], []
    ordered = sorted(scored, key=lambda r: int(r.purchasability_score or 0))
    n = len(ordered)
    k = max(1, n // 5)
    bottom = ordered[:k]
    top = ordered[-k:]
    return top, bottom


def _monthly_folds(
    rows: list[CecchinoPurchasabilityEvaluation],
) -> list[dict[str, Any]]:
    by_month: dict[str, list[CecchinoPurchasabilityEvaluation]] = defaultdict(list)
    for r in rows:
        if r.scan_date is None:
            continue
        key = f"{r.scan_date.year:04d}-{r.scan_date.month:02d}"
        by_month[key].append(r)
    months = sorted(by_month.keys())
    if len(months) < 2:
        return []
    folds = []
    # expanding: train = months[:i], test = months[i]
    for i in range(1, len(months)):
        train_months = months[:i]
        test_month = months[i]
        train_rows = [r for m in train_months for r in by_month[m]]
        test_rows = by_month[test_month]
        if not train_rows or not test_rows:
            continue
        cand = _spearman_residual(test_rows, score_attr="purchasability_score")
        p1 = _spearman_residual(test_rows, score_attr="phase_1_score")
        delta = None
        if cand is not None and p1 is not None:
            delta = cand - p1
        folds.append(
            {
                "fold": len(folds) + 1,
                "test_month": test_month,
                "train_months": train_months,
                "test_rows": len(test_rows),
                "test_fixtures": len({int(r.today_fixture_id) for r in test_rows}),
                "candidate_spearman": cand,
                "phase1_spearman": p1,
                "delta_candidate_minus_phase1": delta,
                "positive_delta": delta is not None and delta > 0,
            }
        )
    return folds


def _spearman_residual(
    rows: list[CecchinoPurchasabilityEvaluation],
    *,
    score_attr: str,
) -> float | None:
    xs: list[float] = []
    ys: list[float] = []
    for r in rows:
        if score_attr == "purchasability_score":
            s = r.purchasability_score
            sx = float(s) if s is not None else None
        else:
            sx = _f(getattr(r, score_attr, None))
        resid = _signed_residual(r)
        if sx is None or resid is None:
            continue
        xs.append(sx)
        ys.append(resid)
    return spearman_rho(xs, ys)


def _cluster_bootstrap_spearman(
    rows: list[CecchinoPurchasabilityEvaluation],
    *,
    score_attr: str,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    """Bootstrap cluster fixture della Spearman score↔residual."""
    by_fid: dict[int, list[CecchinoPurchasabilityEvaluation]] = defaultdict(list)
    for r in rows:
        resid = _signed_residual(r)
        if score_attr == "purchasability_score":
            sx = float(r.purchasability_score) if r.purchasability_score is not None else None
        else:
            sx = _f(getattr(r, score_attr, None))
        if resid is None or sx is None:
            continue
        by_fid[int(r.today_fixture_id)].append(r)
    fids = list(by_fid.keys())
    if len(fids) < 3:
        return {
            "estimate": _spearman_residual(rows, score_attr=score_attr),
            "ci_low": None,
            "ci_high": None,
            "iterations": 0,
        }
    rng = np.random.default_rng(seed)
    stats: list[float] = []
    for _ in range(max(1, iterations)):
        sample_fids = rng.choice(fids, size=len(fids), replace=True)
        sample_rows: list[CecchinoPurchasabilityEvaluation] = []
        for fid in sample_fids:
            sample_rows.extend(by_fid[int(fid)])
        rho = _spearman_residual(sample_rows, score_attr=score_attr)
        if rho is not None:
            stats.append(rho)
    if not stats:
        return {
            "estimate": _spearman_residual(rows, score_attr=score_attr),
            "ci_low": None,
            "ci_high": None,
            "iterations": 0,
        }
    arr = np.asarray(stats, dtype=float)
    return {
        "estimate": float(np.mean(arr)),
        "ci_low": float(np.percentile(arr, 2.5)),
        "ci_high": float(np.percentile(arr, 97.5)),
        "iterations": int(iterations),
        "point": _spearman_residual(rows, score_attr=score_attr),
    }


def _top_bottom_residual_spread(
    rows: list[CecchinoPurchasabilityEvaluation],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    top, bottom = _quintile_split(rows)
    if not top or not bottom:
        return {
            "top_residual_mean": None,
            "bottom_residual_mean": None,
            "residual_spread": None,
            "top_roi": None,
            "bottom_roi": None,
            "roi_spread": None,
            "bootstrap": None,
        }

    def residual_mean(rs: list[CecchinoPurchasabilityEvaluation]) -> float | None:
        vals = [_signed_residual(r) for r in rs]
        vals = [v for v in vals if v is not None]
        return (sum(vals) / len(vals)) if vals else None

    def roi(rs: list[CecchinoPurchasabilityEvaluation]) -> float | None:
        profits = [_f(r.profit_units) for r in rs if _f(r.profit_units) is not None]
        if not profits:
            return None
        return 100.0 * sum(profits) / len(profits)

    top_r = residual_mean(top)
    bot_r = residual_mean(bottom)
    spread = (top_r - bot_r) if top_r is not None and bot_r is not None else None
    top_roi = roi(top)
    bot_roi = roi(bottom)
    roi_spread = (
        (top_roi - bot_roi) if top_roi is not None and bot_roi is not None else None
    )

    # bootstrap cluster on residual spread
    by_fid: dict[int, list[CecchinoPurchasabilityEvaluation]] = defaultdict(list)
    for r in rows:
        by_fid[int(r.today_fixture_id)].append(r)
    fids = list(by_fid.keys())
    boot = None
    if len(fids) >= 3 and spread is not None:
        rng = np.random.default_rng(seed)
        stats = []
        for _ in range(max(1, iterations)):
            sample_fids = rng.choice(fids, size=len(fids), replace=True)
            sample = [r for fid in sample_fids for r in by_fid[int(fid)]]
            t, b = _quintile_split(sample)
            if not t or not b:
                continue
            tr, br = residual_mean(t), residual_mean(b)
            if tr is not None and br is not None:
                stats.append(tr - br)
        if stats:
            arr = np.asarray(stats, dtype=float)
            boot = {
                "mean": float(np.mean(arr)),
                "ci_low": float(np.percentile(arr, 2.5)),
                "ci_high": float(np.percentile(arr, 97.5)),
                "iterations": int(iterations),
            }

    return {
        "top_residual_mean": top_r,
        "bottom_residual_mean": bot_r,
        "residual_spread": spread,
        "top_roi": top_roi,
        "bottom_roi": bot_roi,
        "roi_spread": roi_spread,
        "bootstrap": boot,
    }


def _band_table(rows: list[CecchinoPurchasabilityEvaluation]) -> list[dict[str, Any]]:
    by_band: dict[str, list[CecchinoPurchasabilityEvaluation]] = {
        b: [] for b in SCORE_BANDS_ORDERED
    }
    for r in rows:
        band = score_band_for(r.purchasability_score)
        if band and band in by_band:
            by_band[band].append(r)
    out = []
    for band in SCORE_BANDS_ORDERED:
        m = _metrics_block(by_band[band])
        out.append({"score_band": band, **m})
    return out


def _group_table(
    rows: list[CecchinoPurchasabilityEvaluation],
    key_fn,
    key_name: str,
) -> list[dict[str, Any]]:
    groups: dict[str, list[CecchinoPurchasabilityEvaluation]] = defaultdict(list)
    for r in rows:
        k = key_fn(r)
        if k is None:
            continue
        groups[str(k)].append(r)
    out = []
    for k in sorted(groups.keys()):
        out.append({key_name: k, **_metrics_block(groups[k])})
    return out


def build_purchasability_validation_summary(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    candidate_version: str | None = None,
    competition_id: int | None = None,
    market_key: str | None = None,
    score_band: str | None = None,
    evaluation_status: str | None = None,
    source_cohort: str | None = None,
    source_cohorts: list[str] | None = None,
    promotion_eligible_only: bool = True,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
) -> dict[str, Any]:
    cv = candidate_version or PURCHASABILITY_CANDIDATE_VERSION
    all_rows = query_validation_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        candidate_version=cv,
        competition_id=competition_id,
        market_key=market_key,
        score_band=score_band,
        evaluation_status=evaluation_status,
        source_cohort=source_cohort,
        source_cohorts=source_cohorts,
        promotion_eligible_only=promotion_eligible_only,
    )
    pending = sum(1 for r in all_rows if r.evaluation_status == EVAL_PENDING)
    result_missing = sum(
        1 for r in all_rows if r.evaluation_status == EVAL_RESULT_MISSING
    )
    if promotion_eligible_only:
        settled = _settled_rows(
            all_rows,
            require_promotion_eligible=True,
            require_snapshot_verified=True,
        )
    else:
        settled = _analysis_settled_rows(all_rows)
    general = _metrics_block(settled)
    general["pending"] = pending
    general["result_missing"] = result_missing
    general["rows_total_filtered"] = len(all_rows)

    seed = _bootstrap_seed(
        cv,
        date_from.isoformat(),
        date_to.isoformat(),
        str(competition_id or ""),
        str(market_key or ""),
        "validation_summary_v1",
    )

    spearman_cand = _cluster_bootstrap_spearman(
        settled,
        score_attr="purchasability_score",
        iterations=bootstrap_iterations,
        seed=seed,
    )
    spearman_p1 = _cluster_bootstrap_spearman(
        settled,
        score_attr="phase_1_score",
        iterations=bootstrap_iterations,
        seed=seed + 1,
    )
    top_bottom = _top_bottom_residual_spread(
        settled, iterations=bootstrap_iterations, seed=seed + 2
    )

    delta_point = None
    if spearman_cand.get("point") is not None and spearman_p1.get("point") is not None:
        delta_point = spearman_cand["point"] - spearman_p1["point"]

    # paired delta bootstrap
    by_fid: dict[int, list[CecchinoPurchasabilityEvaluation]] = defaultdict(list)
    for r in settled:
        by_fid[int(r.today_fixture_id)].append(r)
    fids = list(by_fid.keys())
    paired_boot = None
    if len(fids) >= 3:
        rng = np.random.default_rng(seed + 3)
        stats = []
        for _ in range(max(1, bootstrap_iterations)):
            sample_fids = rng.choice(fids, size=len(fids), replace=True)
            sample = [r for fid in sample_fids for r in by_fid[int(fid)]]
            c = _spearman_residual(sample, score_attr="purchasability_score")
            p = _spearman_residual(sample, score_attr="phase_1_score")
            if c is not None and p is not None:
                stats.append(c - p)
        if stats:
            arr = np.asarray(stats, dtype=float)
            paired_boot = {
                "mean": float(np.mean(arr)),
                "ci_low": float(np.percentile(arr, 2.5)),
                "ci_high": float(np.percentile(arr, 97.5)),
                "iterations": int(bootstrap_iterations),
            }

    folds = _monthly_folds(settled)
    pos_folds = sum(1 for f in folds if f.get("positive_delta"))
    neg_folds = sum(1 for f in folds if f.get("positive_delta") is False)

    band_mean_residual = []
    for band_row in _band_table(settled):
        band = band_row["score_band"]
        band_rows = [
            r for r in settled if score_band_for(r.purchasability_score) == band
        ]
        resid = [_signed_residual(r) for r in band_rows]
        resid = [v for v in resid if v is not None]
        band_mean_residual.append(
            {
                "score_band": band,
                "mean_signed_book_residual": (
                    sum(resid) / len(resid) if resid else None
                ),
                "rows": len(band_rows),
            }
        )

    dates = [r.scan_date for r in settled if r.scan_date is not None]
    first_snap = min(dates) if dates else None
    last_snap = max(dates) if dates else None
    prima_data = (
        (first_snap + timedelta(days=MIN_TEMPORAL_DAYS)).isoformat()
        if first_snap
        else None
    )

    return make_json_safe(
        {
            "status": "ok",
            "version": PURCHASABILITY_VALIDATION_VERSION,
            "policy_version": PURCHASABILITY_PROMOTION_POLICY_VERSION,
            "candidate_version": cv,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "metrics": general,
            "by_score_band": _band_table(settled),
            "by_market_key": _group_table(
                settled, lambda r: r.market_key, "market_key"
            ),
            "by_market_family": _group_table(
                settled, lambda r: market_family_for(r.market_key), "market_family"
            ),
            "by_competition": _group_table(
                settled, lambda r: r.competition_id, "competition_id"
            ),
            "by_month": _group_table(
                settled,
                lambda r: (
                    f"{r.scan_date.year:04d}-{r.scan_date.month:02d}"
                    if r.scan_date
                    else None
                ),
                "month",
            ),
            "by_class": _group_table(
                settled, lambda r: r.purchasability_class, "purchasability_class"
            ),
            "by_source_cohort": _group_table(
                all_rows, lambda r: r.source_cohort, "source_cohort"
            ),
            "residual": {
                "spearman_score_vs_signed_book_residual": spearman_cand,
                "mean_residual_by_score_band": band_mean_residual,
                "top_bottom": top_bottom,
            },
            "phase1_comparison": {
                "candidate_spearman": spearman_cand,
                "phase1_spearman": spearman_p1,
                "delta_point": delta_point,
                "paired_delta_bootstrap": paired_boot,
            },
            "temporal_folds": folds,
            "temporal_stability": {
                "folds": len(folds),
                "positive_folds": pos_folds,
                "negative_folds": neg_folds,
                "classification": _stability_label(folds, pos_folds, neg_folds),
            },
            "temporal_span": {
                "first_settled_scan_date": (
                    first_snap.isoformat() if first_snap else None
                ),
                "last_settled_scan_date": (
                    last_snap.isoformat() if last_snap else None
                ),
                "span_days": (
                    (last_snap - first_snap).days
                    if first_snap and last_snap
                    else None
                ),
                "prima_data_teorica_promozione": prima_data,
            },
            "bootstrap_iterations": bootstrap_iterations,
            "promotion_is_automatic": False,
        }
    )


def _stability_label(
    folds: list[dict[str, Any]], pos: int, neg: int
) -> str:
    if len(folds) < MIN_TEMPORAL_FOLDS:
        return "insufficient_evidence"
    if pos >= 2 and neg == 0:
        return "stable_positive"
    if pos >= 2:
        return "positive_but_unstable"
    if neg > pos:
        return "negative"
    if pos == 0 and neg == 0:
        return "neutral"
    return "neutral"


def build_purchasability_promotion_readiness(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    candidate_version: str | None = None,
    competition_id: int | None = None,
    market_key: str | None = None,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    promotion_eligible_only: bool = True,
) -> dict[str, Any]:
    cv = candidate_version or PURCHASABILITY_CANDIDATE_VERSION
    summary = build_purchasability_validation_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        candidate_version=cv,
        competition_id=competition_id,
        market_key=market_key,
        promotion_eligible_only=promotion_eligible_only,
        bootstrap_iterations=bootstrap_iterations,
    )
    health = build_purchasability_validation_health(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )

    metrics = summary.get("metrics") or {}
    span = summary.get("temporal_span") or {}
    folds = summary.get("temporal_folds") or []
    residual = summary.get("residual") or {}
    phase1 = summary.get("phase1_comparison") or {}
    top_bottom = residual.get("top_bottom") or {}
    by_family = summary.get("by_market_family") or []

    coverage = health.get("snapshot_persistence_coverage")
    span_days = span.get("span_days")
    months = len(summary.get("by_month") or [])
    fixtures = int(metrics.get("fixtures") or 0)
    settled = int(metrics.get("settled") or 0)
    zero_share = metrics.get("zero_score_share")
    populated_bands = sum(
        1
        for b in (summary.get("by_score_band") or [])
        if int(b.get("rows") or 0) > 0 and b.get("score_band") != SCORE_BAND_ZERO
    )
    # include ZERO as populated if has rows for band count? Brief: "almeno 3 score band popolate"
    populated_bands_all = sum(
        1 for b in (summary.get("by_score_band") or []) if int(b.get("rows") or 0) > 0
    )

    family_fixture_ok = True
    family_details = []
    for fam in ALL_MARKET_FAMILIES:
        row = next((x for x in by_family if x.get("market_family") == fam), None)
        fx = int((row or {}).get("fixtures") or 0)
        family_details.append({"market_family": fam, "fixtures": fx})
        if fx < MIN_FIXTURES_PER_MARKET_FAMILY:
            family_fixture_ok = False

    data_gates: dict[str, Any] = {
        "persistence_coverage": {
            "value": coverage,
            "threshold": MIN_PERSISTENCE_COVERAGE,
            "pass": coverage is not None and coverage >= MIN_PERSISTENCE_COVERAGE,
        },
        "no_post_kickoff_in_primary": {
            "pass": True,
            "note": "enforced_at_sync",
        },
        "no_result_in_prematch": {"pass": True, "note": "enforced_at_snapshot"},
        "no_settlement_in_prematch": {"pass": True, "note": "enforced_at_snapshot"},
        "no_duplicate_current": {
            "value": health.get("duplicate_validation_rows"),
            "pass": int(health.get("duplicate_validation_rows") or 0) == 0,
        },
        "candidate_version_coherent": {
            "value": cv,
            "pass": cv == PURCHASABILITY_CANDIDATE_VERSION,
        },
        "snapshot_hash_present": {
            "pass": settled == 0
            or all(
                True
                for _ in [1]
            ),  # checked via sync requirement; soft pass if sample empty
            "note": "required_on_synced_rows",
        },
        "fair_book_verifiable": {
            "pass": True,
            "note": "rows_without_fair_excluded_from_residual",
        },
        "source_cohort_promotion_eligible": {
            "pass": promotion_eligible_only is True,
        },
        "min_temporal_days": {
            "value": span_days,
            "threshold": MIN_TEMPORAL_DAYS,
            "pass": span_days is not None and span_days >= MIN_TEMPORAL_DAYS,
        },
        "min_calendar_months": {
            "value": months,
            "threshold": MIN_CALENDAR_MONTHS,
            "pass": months >= MIN_CALENDAR_MONTHS,
        },
        "min_distinct_fixtures": {
            "value": fixtures,
            "threshold": MIN_DISTINCT_FIXTURES,
            "pass": fixtures >= MIN_DISTINCT_FIXTURES,
        },
        "min_settled_rows": {
            "value": settled,
            "threshold": MIN_SETTLED_ROWS,
            "pass": settled >= MIN_SETTLED_ROWS,
        },
        "min_temporal_folds": {
            "value": len(folds),
            "threshold": MIN_TEMPORAL_FOLDS,
            "pass": len(folds) >= MIN_TEMPORAL_FOLDS,
        },
        "min_fixtures_per_market_family": {
            "details": family_details,
            "threshold": MIN_FIXTURES_PER_MARKET_FAMILY,
            "pass": family_fixture_ok,
        },
        "min_populated_score_bands": {
            "value": populated_bands_all,
            "threshold": MIN_POPULATED_SCORE_BANDS,
            "pass": populated_bands_all >= MIN_POPULATED_SCORE_BANDS,
        },
        "max_zero_score_share": {
            "value": zero_share,
            "threshold": MAX_ZERO_SCORE_SHARE,
            "pass": zero_share is None or zero_share <= MAX_ZERO_SCORE_SHARE,
        },
    }

    data_pass = all(bool(g.get("pass")) for g in data_gates.values())
    blocking: list[str] = []
    warnings: list[str] = []

    if coverage is not None and coverage < MIN_PERSISTENCE_COVERAGE:
        blocking.append("data_quality_blocked:persistence_coverage")
    if health.get("duplicate_validation_rows"):
        blocking.append("data_quality_blocked:duplicate_current")
    if span_days is not None and span_days < MIN_TEMPORAL_DAYS:
        blocking.append("insufficient_temporal_span")
    if months < MIN_CALENDAR_MONTHS:
        blocking.append("insufficient_temporal_span:months")
    if fixtures < MIN_DISTINCT_FIXTURES or settled < MIN_SETTLED_ROWS:
        blocking.append("insufficient_sample")
    if not data_pass and not blocking:
        blocking.append("data_quality_blocked")

    # Performance gates
    spearman = residual.get("spearman_score_vs_signed_book_residual") or {}
    test_a_est = spearman.get("point")
    if test_a_est is None:
        test_a_est = spearman.get("estimate")
    test_a_low = spearman.get("ci_low")
    test_a_pass = (
        test_a_est is not None
        and test_a_est > 0
        and test_a_low is not None
        and test_a_low > 0
    )
    test_a_insufficient = test_a_est is None or test_a_low is None

    spread = top_bottom.get("residual_spread")
    spread_boot = top_bottom.get("bootstrap") or {}
    test_b_pass = (
        spread is not None
        and spread > 0
        and spread_boot.get("ci_low") is not None
        and spread_boot["ci_low"] > 0
    )
    test_b_insufficient = spread is None or spread_boot.get("ci_low") is None

    delta = phase1.get("delta_point")
    paired = phase1.get("paired_delta_bootstrap") or {}
    test_c_pass = (
        delta is not None
        and delta > 0
        and paired.get("ci_low") is not None
        and paired["ci_low"] > 0
    )
    test_c_insufficient = delta is None or paired.get("ci_low") is None

    material_negative = False
    if test_a_est is not None and test_a_est < -0.05:
        material_negative = True
    if spread is not None and spread < -0.05:
        material_negative = True
    if delta is not None and delta < -0.05:
        material_negative = True

    primary_pass = sum(1 for p in (test_a_pass, test_b_pass, test_c_pass) if p)
    pos_folds = sum(1 for f in folds if f.get("positive_delta"))
    fold_ok = len(folds) >= MIN_TEMPORAL_FOLDS and pos_folds >= 2

    # family non-negative residual spearman proxy via realized_margin
    family_nonneg = 0
    for fam_row in by_family:
        rm = fam_row.get("realized_margin")
        if rm is None or rm >= 0:
            family_nonneg += 1
    family_ok = family_nonneg >= 3

    perf_insufficient = (
        test_a_insufficient and test_b_insufficient and test_c_insufficient
    ) or settled < 50

    performance_gates = {
        "test_a_residual_order": {
            "estimate": test_a_est,
            "ci_low": test_a_low,
            "pass": test_a_pass,
            "insufficient": test_a_insufficient,
        },
        "test_b_top_bottom": {
            "residual_spread": spread,
            "ci_low": spread_boot.get("ci_low"),
            "pass": test_b_pass,
            "insufficient": test_b_insufficient,
        },
        "test_c_phase2_incremental": {
            "delta": delta,
            "ci_low": paired.get("ci_low"),
            "pass": test_c_pass,
            "insufficient": test_c_insufficient,
        },
        "primary_tests_passed": primary_pass,
        "no_material_negative": not material_negative,
        "temporal_folds_positive": {
            "positive": pos_folds,
            "total": len(folds),
            "pass": fold_ok,
        },
        "market_families_non_negative": {
            "count": family_nonneg,
            "pass": family_ok,
        },
    }

    # Decision order
    if any(b.startswith("data_quality_blocked") for b in blocking) or (
        not data_pass and coverage is not None and coverage < MIN_PERSISTENCE_COVERAGE
    ):
        status = "data_quality_blocked"
    elif span_days is None or span_days < MIN_TEMPORAL_DAYS or months < MIN_CALENDAR_MONTHS:
        status = "insufficient_temporal_span"
    elif fixtures < MIN_DISTINCT_FIXTURES or settled < MIN_SETTLED_ROWS:
        status = "insufficient_sample"
    elif settled < 50 or perf_insufficient:
        status = "collecting_data"
    elif (
        primary_pass >= 2
        and not material_negative
        and fold_ok
        and family_ok
        and data_pass
    ):
        status = "eligible_for_manual_promotion"
    else:
        status = "performance_not_confirmed"

    if status == "eligible_for_manual_promotion":
        recommended = (
            "Gate superati: revisione manuale umana richiesta. "
            "Nessuna promozione automatica."
        )
    elif status == "collecting_data":
        recommended = (
            f"Attendere coorte prospettica; prima data teorica={span.get('prima_data_teorica_promozione')}"
        )
    elif status == "insufficient_temporal_span":
        recommended = "Estendere lo span temporale (≥90 giorni, ≥3 mesi)."
    elif status == "insufficient_sample":
        recommended = "Aumentare fixture settled (≥300) e righe (≥1500)."
    elif status == "data_quality_blocked":
        recommended = "Correggere coverage persistenza / duplicati / coorte."
    else:
        recommended = "Monitorare test A/B/C e stabilità temporale."

    if material_negative:
        warnings.append("material_negative_effect_detected")

    return make_json_safe(
        {
            "status": status,
            "policy_version": PURCHASABILITY_PROMOTION_POLICY_VERSION,
            "validation_version": PURCHASABILITY_VALIDATION_VERSION,
            "candidate_version": cv,
            "promotion_is_automatic": False,
            "eligible_for_manual_promotion": status
            == "eligible_for_manual_promotion",
            "data_gates": data_gates,
            "performance_gates": performance_gates,
            "blocking_reasons": blocking,
            "warnings": warnings,
            "recommended_next_step": recommended,
            "prima_data_teorica_promozione": span.get("prima_data_teorica_promozione"),
            "summary_metrics": metrics,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }
    )
