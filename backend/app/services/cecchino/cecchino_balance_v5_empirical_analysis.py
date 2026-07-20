"""Analisi empirica Balance v5 — Fase 2/3 Step 2B.

Sola lettura su cecchino_balance_v5_evaluations.
Nessun ricalcolo Balance, nessuna API esterna, nessuna scrittura DB.
Nessun score aggregato / ranking pilastri / ROI / promozione.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_balance_v5_evaluation import (
    EVAL_CANCELLED,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_POSTPONED,
    EVAL_RESULT_MISSING,
    EVAL_SETTLED,
    OUTCOME_AWAY,
    OUTCOME_DRAW,
    OUTCOME_HOME,
    CecchinoBalanceV5Evaluation,
)
from app.services.cecchino.cecchino_balance_v5_empirical import (
    BALANCE_EMPIRICAL_DATASET_VERSION,
)
from app.services.cecchino.cecchino_balance_v5_empirical_analysis_stats import (
    brier_score,
    bootstrap_ci,
    benjamini_hochberg,
    chi_square_independence,
    classify_drift,
    clamp_prob,
    deterministic_seed_int,
    expected_calibration_error,
    jensen_shannon,
    kruskal_wallis,
    log_loss,
    mean,
    median,
    odds_ratio,
    population_stability_index,
    proportion_block,
    rate_pct,
    roc_pr_auc,
    spearman_safe,
)
from app.services.cecchino.cecchino_balance_v5_empirical_registry import (
    PILLAR_META,
    build_class_registry_payload,
    resolve_class,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_FILTER_ALL,
    COHORT_HISTORICAL_DIAGNOSTIC,
    COHORT_PROSPECTIVE,
    parse_export_cohort_filter,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

logger = logging.getLogger(__name__)

BALANCE_EMPIRICAL_ANALYSIS_VERSION = "cecchino_balance_v5_empirical_analysis_v1"
BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION = (
    "cecchino_balance_v5_statistical_policy_v1"
)

MIN_SETTLED_GLOBAL = 300
MIN_ROWS_DESCRIPTIVE_CLASS = 20
MIN_ROWS_COMPARISON_CLASS = 40
MIN_ROWS_CALIBRATION_BIN = 30
MIN_ROWS_COMPETITION = 30
MIN_ROWS_MONTH = 30
BOOTSTRAP_ITERATIONS_DEFAULT = 2000
BOOTSTRAP_ITERATIONS_MIN = 500
BOOTSTRAP_ITERATIONS_MAX = 10000
CONFIDENCE_LEVEL = 0.95
CALIBRATION_BINS = 10
PROB_SUM_TOLERANCE = 0.02

EVIDENCE_STATUSES = frozenset(
    {
        "analysis_not_run",
        "insufficient_data",
        "descriptive_only",
        "exploratory_evidence",
        "evidence_emerging",
        "evidence_inconsistent",
        "not_evaluable",
    }
)

_CACHE_TTL_S = 300.0
_cache_lock = threading.Lock()
_analysis_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def build_statistical_policy_payload() -> dict[str, Any]:
    return {
        "version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
        "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
        "MIN_SETTLED_GLOBAL": MIN_SETTLED_GLOBAL,
        "MIN_ROWS_DESCRIPTIVE_CLASS": MIN_ROWS_DESCRIPTIVE_CLASS,
        "MIN_ROWS_COMPARISON_CLASS": MIN_ROWS_COMPARISON_CLASS,
        "MIN_ROWS_CALIBRATION_BIN": MIN_ROWS_CALIBRATION_BIN,
        "MIN_ROWS_COMPETITION": MIN_ROWS_COMPETITION,
        "MIN_ROWS_MONTH": MIN_ROWS_MONTH,
        "BOOTSTRAP_ITERATIONS_DEFAULT": BOOTSTRAP_ITERATIONS_DEFAULT,
        "BOOTSTRAP_ITERATIONS_MIN": BOOTSTRAP_ITERATIONS_MIN,
        "BOOTSTRAP_ITERATIONS_MAX": BOOTSTRAP_ITERATIONS_MAX,
        "CONFIDENCE_LEVEL": CONFIDENCE_LEVEL,
        "CALIBRATION_BINS": CALIBRATION_BINS,
        "PROB_SUM_TOLERANCE": PROB_SUM_TOLERANCE,
        "immutable": True,
        "notes": [
            "Parametri non modificabili da FE/query/env",
            "Cambio richiede nuova policy version",
        ],
    }


def normalize_analysis_filters(
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    source_cohort: str | None = "all",
    country_name: str | None = None,
    f36_class: str | None = None,
    dominance_class: str | None = None,
    dominance_selection: str | None = None,
    draw_credibility_class: str | None = None,
    gap_class: str | None = None,
) -> dict[str, Any]:
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "competition_id": competition_id,
        "source_cohort": parse_export_cohort_filter(source_cohort or COHORT_FILTER_ALL),
        "country_name": country_name,
        "f36_class": f36_class,
        "dominance_class": dominance_class,
        "dominance_selection": dominance_selection,
        "draw_credibility_class": draw_credibility_class,
        "gap_class": gap_class,
    }


def _cache_get(key: tuple[Any, ...]) -> dict[str, Any] | None:
    with _cache_lock:
        hit = _analysis_cache.get(key)
        if not hit:
            return None
        ts, payload = hit
        if time.monotonic() - ts > _CACHE_TTL_S:
            _analysis_cache.pop(key, None)
            return None
        return payload


def _cache_set(key: tuple[Any, ...], payload: dict[str, Any]) -> None:
    with _cache_lock:
        if len(_analysis_cache) > 64:
            oldest = sorted(_analysis_cache.items(), key=lambda kv: kv[1][0])[:16]
            for k, _ in oldest:
                _analysis_cache.pop(k, None)
        _analysis_cache[key] = (time.monotonic(), payload)


def clear_balance_analysis_cache() -> None:
    with _cache_lock:
        _analysis_cache.clear()


def _max_updated_at(db: Session) -> str | None:
    try:
        val = db.scalar(select(func.max(CecchinoBalanceV5Evaluation.updated_at)))
        return val.isoformat() if val is not None else None
    except Exception:
        return None


def _query_rows(
    db: Session,
    filters: dict[str, Any],
    *,
    only_current: bool = True,
) -> list[CecchinoBalanceV5Evaluation]:
    q = select(CecchinoBalanceV5Evaluation).where(
        CecchinoBalanceV5Evaluation.scan_date >= date.fromisoformat(filters["date_from"]),
        CecchinoBalanceV5Evaluation.scan_date <= date.fromisoformat(filters["date_to"]),
    )
    if only_current:
        q = q.where(CecchinoBalanceV5Evaluation.is_current.is_(True))
    if filters.get("competition_id") is not None:
        q = q.where(
            CecchinoBalanceV5Evaluation.competition_id == int(filters["competition_id"])
        )
    cohort = filters.get("source_cohort") or COHORT_FILTER_ALL
    if cohort != COHORT_FILTER_ALL:
        q = q.where(CecchinoBalanceV5Evaluation.source_cohort == cohort)
    if filters.get("country_name"):
        q = q.where(CecchinoBalanceV5Evaluation.country_name == filters["country_name"])
    if filters.get("f36_class"):
        q = q.where(CecchinoBalanceV5Evaluation.f36_class == filters["f36_class"])
    if filters.get("dominance_class"):
        q = q.where(
            CecchinoBalanceV5Evaluation.dominance_class == filters["dominance_class"]
        )
    if filters.get("dominance_selection"):
        q = q.where(
            CecchinoBalanceV5Evaluation.dominance_selection
            == filters["dominance_selection"]
        )
    if filters.get("draw_credibility_class"):
        q = q.where(
            CecchinoBalanceV5Evaluation.draw_credibility_class
            == filters["draw_credibility_class"]
        )
    if filters.get("gap_class"):
        q = q.where(CecchinoBalanceV5Evaluation.gap_class == filters["gap_class"])
    return list(db.scalars(q).all())


def _is_settled_valid(r: CecchinoBalanceV5Evaluation) -> bool:
    return (
        r.evaluation_status == EVAL_SETTLED
        and r.ft_home is not None
        and r.ft_away is not None
        and r.outcome_1x2 in {OUTCOME_HOME, OUTCOME_DRAW, OUTCOME_AWAY}
    )


def _sample_counts(rows: list[CecchinoBalanceV5Evaluation]) -> dict[str, Any]:
    by_status = Counter(r.evaluation_status for r in rows)
    by_cohort = Counter(r.source_cohort for r in rows)
    settled = [r for r in rows if _is_settled_valid(r)]
    return {
        "rows_total": len(rows),
        "distinct_fixtures": len({int(r.today_fixture_id) for r in rows}),
        "settled": len(settled),
        "pending": by_status.get(EVAL_PENDING, 0),
        "result_missing": by_status.get(EVAL_RESULT_MISSING, 0),
        "not_evaluable": by_status.get(EVAL_NOT_EVALUABLE, 0)
        + by_status.get(EVAL_CANCELLED, 0)
        + by_status.get(EVAL_POSTPONED, 0),
        "analysis_eligible": sum(1 for r in rows if r.analysis_eligible),
        "promotion_eligible": sum(1 for r in rows if r.promotion_eligible),
        "historical_diagnostic": by_cohort.get(COHORT_HISTORICAL_DIAGNOSTIC, 0),
        "prospective_persisted": by_cohort.get(COHORT_PROSPECTIVE, 0),
        "verified_historical": sum(
            1
            for r in rows
            if r.source_cohort
            not in {COHORT_HISTORICAL_DIAGNOSTIC, COHORT_PROSPECTIVE}
            and r.pre_match_verified is True
        ),
        "by_evaluation_status": dict(by_status),
        "by_source_cohort": dict(by_cohort),
        "timestamp_verified": sum(1 for r in rows if r.pre_match_verified is True),
        "timestamp_unverified": sum(1 for r in rows if r.pre_match_verified is not True),
        "book_verified": sum(1 for r in rows if r.book_verified is True),
    }


def _evidence_scope(rows: list[CecchinoBalanceV5Evaluation]) -> str:
    cohorts = {r.source_cohort for r in rows}
    if cohorts == {COHORT_PROSPECTIVE}:
        return COHORT_PROSPECTIVE
    if COHORT_PROSPECTIVE in cohorts:
        return "mixed"
    if cohorts == {COHORT_HISTORICAL_DIAGNOSTIC} or COHORT_HISTORICAL_DIAGNOSTIC in cohorts:
        return COHORT_HISTORICAL_DIAGNOSTIC
    return "mixed"


def _group_outcome_stats(
    rows: list[CecchinoBalanceV5Evaluation],
    *,
    filters: dict[str, Any],
    pillar: str,
    group_key: str,
    bootstrap_iterations: int,
) -> dict[str, Any]:
    n = len(rows)
    homes = sum(1 for r in rows if r.outcome_1x2 == OUTCOME_HOME)
    draws = sum(1 for r in rows if r.outcome_1x2 == OUTCOME_DRAW)
    aways = sum(1 for r in rows if r.outcome_1x2 == OUTCOME_AWAY)
    goals = [float(r.total_goals) for r in rows if r.total_goals is not None]
    diffs = [
        float(r.absolute_goal_difference)
        for r in rows
        if r.absolute_goal_difference is not None
    ]
    hits = [r for r in rows if r.dominance_selection_hit is True]
    misses = [r for r in rows if r.dominance_selection_hit is False]
    seed_mean = deterministic_seed_int(
        analysis_version=BALANCE_EMPIRICAL_ANALYSIS_VERSION,
        policy_version=BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
        filters=filters,
        pillar=pillar,
        metric="avg_total_goals",
        group_key=group_key,
    )
    seed_med = deterministic_seed_int(
        analysis_version=BALANCE_EMPIRICAL_ANALYSIS_VERSION,
        policy_version=BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
        filters=filters,
        pillar=pillar,
        metric="median_total_goals",
        group_key=group_key,
    )
    data_status = (
        "ok"
        if n >= MIN_ROWS_COMPARISON_CLASS
        else ("descriptive" if n >= MIN_ROWS_DESCRIPTIVE_CLASS else "insufficient_data")
    )
    return {
        "rows": n,
        "distinct_fixtures": len({int(r.today_fixture_id) for r in rows}),
        "share_pct": None,
        "outcome_HOME": homes,
        "outcome_DRAW": draws,
        "outcome_AWAY": aways,
        "home_rate": proportion_block(homes, n),
        "draw_rate": proportion_block(draws, n),
        "away_rate": proportion_block(aways, n),
        "average_total_goals": mean(goals),
        "median_total_goals": median(goals),
        "average_absolute_goal_difference": mean(diffs),
        "median_absolute_goal_difference": median(diffs),
        "total_goals_ci": bootstrap_ci(
            goals, seed=seed_mean, iterations=bootstrap_iterations, confidence=CONFIDENCE_LEVEL
        ),
        "median_total_goals_ci": bootstrap_ci(
            goals,
            seed=seed_med,
            iterations=bootstrap_iterations,
            confidence=CONFIDENCE_LEVEL,
            statistic="median",
        ),
        "dominance_hit": proportion_block(len(hits), len(hits) + len(misses)),
        "data_status": data_status,
    }


def _expected_dom_prob(r: CecchinoBalanceV5Evaluation) -> float | None:
    sel = (r.dominance_selection or "").strip().upper()
    mapping = {"1": r.prob_1_norm, "X": r.prob_x_norm, "2": r.prob_2_norm}
    v = mapping.get(sel)
    if v is None:
        return None
    # probs may be 0-1 or 0-100
    fv = float(v)
    if fv > 1.5:
        fv = fv / 100.0
    return clamp_prob(fv)


def _upset(r: CecchinoBalanceV5Evaluation) -> bool | None:
    sel = (r.dominance_selection or "").strip().upper()
    if sel not in {"1", "2"}:
        return None
    if r.outcome_1x2 == OUTCOME_DRAW:
        return False  # pareggio conteggiato separatamente
    if sel == "1":
        return r.outcome_1x2 == OUTCOME_AWAY
    return r.outcome_1x2 == OUTCOME_HOME


def build_balance_pillar_evidence_status(
    *,
    pillar: str,
    sample_size: int,
    evidence_scope: str,
    primary_metric: dict[str, Any] | None,
    supporting_metrics: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    inconsistent: bool = False,
    descriptive_structure: bool = False,
    analysis_not_run: bool = False,
) -> dict[str, Any]:
    """Priorità: not_run → insufficient → inconsistent → descriptive → cap historical → exploratory."""
    warns = list(warnings or [])
    blocking = list(blocking_reasons or [])
    if analysis_not_run:
        return make_json_safe(
            {
                "pillar": pillar,
                "evidence_scope": evidence_scope,
                "status": "analysis_not_run",
                "sample_size": sample_size,
                "primary_metric": primary_metric or {},
                "supporting_metrics": supporting_metrics or [],
                "blocking_reasons": blocking,
                "warnings": warns,
                "formula_change_recommended": False,
                "promotion_eligible": False,
            }
        )

    status = "descriptive_only"
    if sample_size < MIN_ROWS_DESCRIPTIVE_CLASS:
        status = "insufficient_data"
        blocking.append("sample_below_descriptive_minimum")
    elif inconsistent:
        status = "evidence_inconsistent"
    elif descriptive_structure or sample_size < MIN_SETTLED_GLOBAL:
        status = "descriptive_only"
        if sample_size < MIN_SETTLED_GLOBAL and not descriptive_structure:
            warns.append("below_MIN_SETTLED_GLOBAL")
    elif evidence_scope == COHORT_HISTORICAL_DIAGNOSTIC:
        status = "exploratory_evidence"
        warns.append("historical_diagnostic_caps_status_at_exploratory_evidence")
    elif evidence_scope == COHORT_PROSPECTIVE:
        status = "evidence_emerging"
    else:
        status = "exploratory_evidence"

    if status not in EVIDENCE_STATUSES:
        status = "not_evaluable"

    return make_json_safe(
        {
            "pillar": pillar,
            "evidence_scope": evidence_scope,
            "status": status,
            "sample_size": sample_size,
            "primary_metric": primary_metric or {},
            "supporting_metrics": supporting_metrics or [],
            "blocking_reasons": blocking,
            "warnings": list(dict.fromkeys(warns)),
            "formula_change_recommended": False,
            "promotion_eligible": False,
        }
    )


def build_balance_full_pillar_evidence_status(
    *,
    f36_analysis: dict[str, Any],
    dominance_analysis: dict[str, Any],
    draw_credibility_analysis: dict[str, Any],
    gap_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Mappa canonica: usa esclusivamente analysis['evidence'] dei quattro pilastri completi."""

    def _ev(payload: dict[str, Any], key: str) -> dict[str, Any]:
        ev = payload.get("evidence") if isinstance(payload, dict) else None
        if isinstance(ev, dict) and ev.get("status"):
            return make_json_safe(dict(ev))
        return make_json_safe(
            {
                "pillar": key,
                "status": "not_evaluable",
                "warnings": ["evidence_missing_from_pillar_payload"],
                "formula_change_recommended": False,
                "promotion_eligible": False,
            }
        )

    return make_json_safe(
        {
            "f36": _ev(f36_analysis, "f36"),
            "dominance": _ev(dominance_analysis, "dominance"),
            "draw_credibility": _ev(draw_credibility_analysis, "draw_credibility"),
            "gap": _ev(gap_analysis, "gap"),
        }
    )


def _spearman_abs(block: dict[str, Any] | None) -> float:
    if not block or not isinstance(block, dict):
        return 0.0
    rho = block.get("rho")
    if rho is None:
        return 0.0
    try:
        return abs(float(rho))
    except (TypeError, ValueError):
        return 0.0


def _f36_evidence_flags(tests: dict[str, Any]) -> dict[str, bool]:
    """Regole scientifiche F36 (descriptive_structure)."""
    chi = tests.get("class_vs_outcome_1x2") or {}
    p_out = chi.get("p_value_adjusted")
    if p_out is None:
        p_out = chi.get("p_value")
    try:
        p_out_f = float(p_out) if p_out is not None else 1.0
    except (TypeError, ValueError):
        p_out_f = 1.0
    try:
        cramers_v = float(chi.get("cramers_v") or 0.0)
    except (TypeError, ValueError):
        cramers_v = 0.0

    kw_g = tests.get("class_vs_total_goals") or {}
    kw_d = tests.get("class_vs_absolute_goal_difference") or {}
    p_g = kw_g.get("p_value_adjusted", kw_g.get("p_value"))
    p_d = kw_d.get("p_value_adjusted", kw_d.get("p_value"))
    try:
        p_g_f = float(p_g) if p_g is not None else 1.0
    except (TypeError, ValueError):
        p_g_f = 1.0
    try:
        p_d_f = float(p_d) if p_d is not None else 1.0
    except (TypeError, ValueError):
        p_d_f = 1.0

    spearman = tests.get("spearman_index") or {}
    rhos = [
        _spearman_abs(spearman.get("vs_is_draw")),
        _spearman_abs(spearman.get("vs_total_goals")),
        _spearman_abs(spearman.get("vs_absolute_goal_difference")),
    ]
    all_rho_small = all(r < 0.10 for r in rhos)
    null_effects = (
        p_out_f > 0.05
        and cramers_v < 0.10
        and p_g_f > 0.05
        and p_d_f > 0.05
        and all_rho_small
    )
    outcome_signal = p_out_f <= 0.05 and cramers_v >= 0.10
    numeric_signal = (p_g_f <= 0.05 or p_d_f <= 0.05) and not all_rho_small
    conflicting = bool(
        (outcome_signal and not numeric_signal and (p_g_f > 0.05 and p_d_f > 0.05))
        or (numeric_signal and not outcome_signal)
    )
    coherent = (outcome_signal or numeric_signal) and not conflicting and not null_effects
    return {
        "null_effects": null_effects,
        "conflicting": conflicting,
        "coherent": coherent,
    }


READING_F36_NULL = (
    "Nel campione osservato le classi F36 descrivono configurazioni diverse "
    "delle quote, ma non emergono differenze statisticamente rilevanti negli "
    "esiti, nei goal o nella differenza reti."
)


def _deterministic_reading_f36(
    by_class: list[dict[str, Any]],
    n: int,
    *,
    evidence_flags: dict[str, bool] | None = None,
) -> str:
    if n < MIN_ROWS_DESCRIPTIVE_CLASS:
        return (
            "Campione insufficiente per descrivere differenze strutturali tra le classi F36."
        )
    flags = evidence_flags or {}
    if flags.get("null_effects") or flags.get("conflicting") or not flags.get("coherent"):
        return READING_F36_NULL
    best = None
    best_lat = -1.0
    for row in by_class:
        if int(row.get("rows") or 0) < MIN_ROWS_DESCRIPTIVE_CLASS:
            continue
        lat = (row.get("home_rate") or {}).get("rate") or 0.0
        lat += (row.get("away_rate") or {}).get("rate") or 0.0
        if lat > best_lat:
            best_lat = lat
            best = row
    if best is None:
        return READING_F36_NULL
    label = best.get("label_it") or best.get("class")
    return (
        f"Nel campione storico diagnostico le fixture «{label}» mostrano una "
        "configurazione laterale relativamente più frequente; l’effetto resta "
        "esplorativo e F36 non seleziona automaticamente un esito."
    )


def build_f36_empirical_analysis(
    db: Session,
    *,
    filters: dict[str, Any],
    bootstrap_iterations: int = BOOTSTRAP_ITERATIONS_DEFAULT,
) -> dict[str, Any]:
    rows = _query_rows(db, filters)
    settled = [
        r
        for r in rows
        if _is_settled_valid(r) and r.analysis_eligible and r.f36_class is not None
    ]
    scope = _evidence_scope(settled or rows)
    warnings: list[str] = []
    unknown = 0
    by_raw: dict[str, list[CecchinoBalanceV5Evaluation]] = defaultdict(list)
    for r in settled:
        resolved = resolve_class("f36", r.f36_class)
        if not resolved.get("is_registered"):
            unknown += 1
            warnings.append(f"unregistered_f36_class:{r.f36_class}")
        by_raw[str(r.f36_class)].append(r)

    class_rows: list[dict[str, Any]] = []
    total = len(settled) or 1
    for raw, group in sorted(by_raw.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        resolved = resolve_class("f36", raw)
        stats = _group_outcome_stats(
            group,
            filters=filters,
            pillar="f36",
            group_key=raw,
            bootstrap_iterations=bootstrap_iterations,
        )
        stats["share_pct"] = round(100.0 * len(group) / total, 2)
        stats["class"] = raw
        stats["label_it"] = resolved["label_it"]
        stats["canonical_key"] = resolved["canonical_key"]
        stats["order"] = resolved["order"]
        stats["is_registered"] = resolved.get("is_registered", False)
        class_rows.append(stats)

    # contingency class x outcome
    labels = [c["class"] for c in class_rows]
    table = []
    for lab in labels:
        g = by_raw[lab]
        table.append(
            [
                sum(1 for r in g if r.outcome_1x2 == OUTCOME_HOME),
                sum(1 for r in g if r.outcome_1x2 == OUTCOME_DRAW),
                sum(1 for r in g if r.outcome_1x2 == OUTCOME_AWAY),
            ]
        )
    chi = chi_square_independence(table) if len(labels) >= 2 else {
        "status": "insufficient_data",
        "chi2": None,
        "p_value": None,
        "cramers_v": None,
    }

    goals_by_class = [
        [float(r.total_goals) for r in by_raw[lab] if r.total_goals is not None]
        for lab in labels
    ]
    diffs_by_class = [
        [
            float(r.absolute_goal_difference)
            for r in by_raw[lab]
            if r.absolute_goal_difference is not None
        ]
        for lab in labels
    ]
    kw_goals = kruskal_wallis(goals_by_class)
    kw_diff = kruskal_wallis(diffs_by_class)

    idx = [float(r.f36_index) for r in settled if r.f36_index is not None]
    is_draw = [1 if r.is_draw else 0 for r in settled if r.f36_index is not None]
    tot_g = [float(r.total_goals or 0) for r in settled if r.f36_index is not None]
    abs_d = [
        float(r.absolute_goal_difference or 0) for r in settled if r.f36_index is not None
    ]
    spearman_block = {
        "vs_is_draw": spearman_safe(idx, [float(x) for x in is_draw]),
        "vs_total_goals": spearman_safe(idx, tot_g),
        "vs_absolute_goal_difference": spearman_safe(idx, abs_d),
    }

    p_raw = [chi.get("p_value"), kw_goals.get("p_value"), kw_diff.get("p_value")]
    p_adj = benjamini_hochberg(p_raw)

    tests = {
        "class_vs_outcome_1x2": {**chi, "p_value_adjusted": p_adj[0]},
        "class_vs_total_goals": {**kw_goals, "p_value_adjusted": p_adj[1]},
        "class_vs_absolute_goal_difference": {
            **kw_diff,
            "p_value_adjusted": p_adj[2],
        },
        "spearman_index": spearman_block,
    }
    flags = _f36_evidence_flags(tests)
    evidence = build_balance_pillar_evidence_status(
        pillar="f36",
        sample_size=len(settled),
        evidence_scope=scope,
        primary_metric={"chi_square_outcome": chi, "cramers_v": chi.get("cramers_v")},
        supporting_metrics=[
            {"kruskal_total_goals": kw_goals},
            {"kruskal_abs_diff": kw_diff},
            {"spearman": spearman_block},
        ],
        warnings=list(dict.fromkeys(warnings)),
        inconsistent=bool(flags.get("conflicting")),
        descriptive_structure=bool(flags.get("null_effects")),
    )

    return make_json_safe(
        {
            "status": "ok",
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "bootstrap_iterations": int(bootstrap_iterations),
            "pillar": "f36",
            "role": PILLAR_META["f36"]["role"],
            "role_label": PILLAR_META["f36"]["meaning"],
            "filters": filters,
            "sample": _sample_counts(rows),
            "analytical_sample": {
                "settled_with_class": len(settled),
                "unknown_classes": unknown,
                "note": "pending esclusi dalle metriche prestazionali",
            },
            "by_class": class_rows,
            "tests": tests,
            "reading": _deterministic_reading_f36(
                class_rows, len(settled), evidence_flags=flags
            ),
            "evidence": evidence,
            "forbidden_interpretations": [
                "f36_is_direct_betting_signal",
                "f36_selects_outcome_automatically",
            ],
        }
    )


def build_dominance_empirical_analysis(
    db: Session,
    *,
    filters: dict[str, Any],
    bootstrap_iterations: int = BOOTSTRAP_ITERATIONS_DEFAULT,
) -> dict[str, Any]:
    rows = _query_rows(db, filters)
    settled = [
        r
        for r in rows
        if _is_settled_valid(r)
        and r.analysis_eligible
        and r.dominance_selection_hit is not None
    ]
    scope = _evidence_scope(settled or rows)
    hits = sum(1 for r in settled if r.dominance_selection_hit is True)
    n = len(settled)
    expected = [_expected_dom_prob(r) for r in settled]
    expected_ok = [e for e in expected if e is not None]
    y = [1 if r.dominance_selection_hit else 0 for r in settled]
    p = [e if e is not None else 0.5 for e in expected]
    obs_minus_exp = None
    if expected_ok and n:
        obs_minus_exp = round((hits / n) - float(np_mean(expected_ok)), 4)

    by_class: dict[str, list] = defaultdict(list)
    by_sel: dict[str, list] = defaultdict(list)
    for r in settled:
        by_class[str(r.dominance_class or "missing")].append(r)
        by_sel[str(r.dominance_selection or "missing")].append(r)

    class_stats = []
    for raw, g in sorted(by_class.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        resolved = resolve_class("dominance", raw)
        h = sum(1 for r in g if r.dominance_selection_hit)
        class_stats.append(
            {
                "class": raw,
                "label_it": resolved["label_it"],
                "canonical_key": resolved["canonical_key"],
                "is_registered": resolved.get("is_registered", False),
                "rows": len(g),
                "hit_rate": proportion_block(h, len(g)),
                "expected_mean": mean(
                    [e for e in (_expected_dom_prob(r) for r in g) if e is not None]
                ),
            }
        )

    sel_stats = []
    for raw, g in sorted(by_sel.items()):
        h = sum(1 for r in g if r.dominance_selection_hit)
        sel_stats.append(
            {
                "selection": raw,
                "rows": len(g),
                "hit_rate": proportion_block(h, len(g)),
                "expected_mean": mean(
                    [e for e in (_expected_dom_prob(r) for r in g) if e is not None]
                ),
            }
        )

    # class x selection heatmap
    heatmap = []
    for c_raw, cg in by_class.items():
        for s_raw in sorted({str(r.dominance_selection or "missing") for r in settled}):
            g = [r for r in cg if str(r.dominance_selection or "missing") == s_raw]
            if not g:
                continue
            h = sum(1 for r in g if r.dominance_selection_hit)
            heatmap.append(
                {
                    "dominance_class": c_raw,
                    "selection": s_raw,
                    "rows": len(g),
                    "hit_rate": proportion_block(h, len(g)),
                }
            )

    ece = expected_calibration_error(y, p, n_bins=CALIBRATION_BINS)
    brier = brier_score(y, p)
    ll = log_loss(y, p)
    idx = [float(r.dominance_index) for r in settled if r.dominance_index is not None]
    hit_f = [
        1.0 if r.dominance_selection_hit else 0.0
        for r in settled
        if r.dominance_index is not None
    ]
    trend = spearman_safe(idx, hit_f)

    dom_warns: list[str] = ["hit_rate_is_not_roi"]
    if obs_minus_exp is not None and obs_minus_exp < 0:
        dom_warns.append("overall_observed_below_expected")
    for s in sel_stats:
        sel = str(s.get("selection") or "").upper()
        hr = (s.get("hit_rate") or {}).get("rate")
        exp_m = s.get("expected_mean")
        if hr is None or exp_m is None:
            continue
        try:
            if float(hr) + 1e-9 < float(exp_m):
                if sel in {"2", "AWAY"}:
                    dom_warns.append("selection_away_underperforms_expected")
                elif sel in {"X", "DRAW"}:
                    dom_warns.append("selection_draw_underperforms_expected")
        except (TypeError, ValueError):
            pass
    for c in class_stats:
        key = str(c.get("canonical_key") or c.get("class") or "").lower()
        rows_c = int(c.get("rows") or 0)
        if "very_strong" in key and rows_c < MIN_ROWS_DESCRIPTIVE_CLASS:
            dom_warns.append("very_strong_sample_insufficient")

    evidence = build_balance_pillar_evidence_status(
        pillar="dominance",
        sample_size=n,
        evidence_scope=scope,
        primary_metric={
            "hit_rate": proportion_block(hits, n),
            "brier": brier,
            "ece": ece.get("ece"),
        },
        supporting_metrics=[{"spearman_index_vs_hit": trend}],
        warnings=list(dict.fromkeys(dom_warns)),
    )

    return make_json_safe(
        {
            "status": "ok",
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "bootstrap_iterations": int(bootstrap_iterations),
            "pillar": "dominance",
            "role": PILLAR_META["dominance"]["role"],
            "role_label": PILLAR_META["dominance"]["meaning"],
            "filters": filters,
            "sample": _sample_counts(rows),
            "analytical_sample": {"settled_with_hit": n},
            "global": {
                "hit_rate": proportion_block(hits, n),
                "miss": n - hits,
                "expected_probability_mean": mean(expected_ok),
                "observed_minus_expected": obs_minus_exp,
                "brier": brier,
                "log_loss": ll,
                "ece": ece.get("ece"),
                "note": "hit rate non equivale a ROI",
            },
            "by_class": class_stats,
            "by_selection": sel_stats,
            "class_x_selection": heatmap,
            "calibration": ece,
            "trend": trend,
            "evidence": evidence,
        }
    )


def np_mean(xs: list[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0


def build_draw_credibility_empirical_analysis(
    db: Session,
    *,
    filters: dict[str, Any],
    bootstrap_iterations: int = BOOTSTRAP_ITERATIONS_DEFAULT,
) -> dict[str, Any]:
    rows = _query_rows(db, filters)
    settled = [
        r
        for r in rows
        if _is_settled_valid(r)
        and r.analysis_eligible
        and r.is_draw is not None
        and r.draw_credibility_class is not None
    ]
    scope = _evidence_scope(settled or rows)
    n = len(settled)
    draws = sum(1 for r in settled if r.is_draw)
    y = [1 if r.is_draw else 0 for r in settled]
    p = []
    for r in settled:
        px = r.prob_x_norm
        if px is None:
            p.append(0.5)
            continue
        fv = float(px)
        if fv > 1.5:
            fv /= 100.0
        p.append(clamp_prob(fv))

    by_class: dict[str, list] = defaultdict(list)
    for r in settled:
        by_class[str(r.draw_credibility_class)].append(r)

    class_stats = []
    ordered_rates: list[tuple[int, float, str]] = []
    for raw, g in by_class.items():
        resolved = resolve_class("draw_credibility", raw)
        d = sum(1 for r in g if r.is_draw)
        yg = [1 if r.is_draw else 0 for r in g]
        pg = []
        for r in g:
            px = r.prob_x_norm
            fv = 0.5 if px is None else float(px)
            if fv > 1.5:
                fv /= 100.0
            pg.append(clamp_prob(fv))
        rate = d / len(g) if g else 0.0
        ordered_rates.append((resolved["order"], rate, raw))
        class_stats.append(
            {
                "class": raw,
                "label_it": resolved["label_it"],
                "order": resolved["order"],
                "is_registered": resolved.get("is_registered", False),
                "rows": len(g),
                "draw": d,
                "non_draw": len(g) - d,
                "draw_rate": proportion_block(d, len(g)),
                "prob_x_norm_mean": mean(pg),
                "calibration_gap": round(rate - (mean(pg) or 0.0), 4),
                "brier": brier_score(yg, pg),
                "log_loss": log_loss(yg, pg),
            }
        )
    class_stats.sort(key=lambda x: x.get("order", 999))

    # monotonicity by registry order
    ordered_rates.sort(key=lambda t: t[0])
    rates_only = [t[1] for t in ordered_rates if t[0] < 9000]
    transitions = max(0, len(rates_only) - 1)
    violations = sum(
        1 for i in range(1, len(rates_only)) if rates_only[i] + 1e-9 < rates_only[i - 1]
    )
    if len(rates_only) < 2:
        mono_status = "insufficient_data"
    elif violations == 0:
        mono_status = "monotonic"
    elif violations <= max(1, transitions // 3):
        mono_status = "mostly_monotonic"
    else:
        mono_status = "inconsistent"

    ece = expected_calibration_error(y, p, n_bins=CALIBRATION_BINS)
    brier = brier_score(y, p)
    baseline = draws / n if n else 0.0
    baseline_brier = brier_score(y, [baseline] * n) if n else None
    skill = None
    if brier is not None and baseline_brier and baseline_brier > 0:
        skill = round(1.0 - (brier / baseline_brier), 4)
    disc = roc_pr_auc(y, p)
    idx = [
        float(r.draw_credibility_index)
        for r in settled
        if r.draw_credibility_index is not None
    ]
    y_idx = [
        1.0 if r.is_draw else 0.0
        for r in settled
        if r.draw_credibility_index is not None
    ]

    roc_auc = None
    if isinstance(disc, dict):
        roc_auc = disc.get("roc_auc")
    try:
        roc_auc_f = float(roc_auc) if roc_auc is not None else 0.5
    except (TypeError, ValueError):
        roc_auc_f = 0.5

    # Class ordering / monotonicità (stessa segnale — conta una sola volta)
    ordering_violated = mono_status == "inconsistent"
    # High bands overestimate: top half by order with negative calibration_gap (predicted > observed)
    high_over = 0
    high_n = 0
    for row in class_stats:
        if int(row.get("rows") or 0) < MIN_ROWS_DESCRIPTIVE_CLASS:
            continue
        order = int(row.get("order") or 0)
        if order < 9000 and order >= 3:  # fasce alte tipiche
            high_n += 1
            gap_c = row.get("calibration_gap")
            try:
                if gap_c is not None and float(gap_c) < -0.05:
                    high_over += 1
            except (TypeError, ValueError):
                pass
    high_bands_overestimated = high_n > 0 and high_over >= max(1, high_n // 2)

    inconsistency_votes = 0
    if skill is not None and skill < 0:
        inconsistency_votes += 1
    if mono_status == "inconsistent" or ordering_violated:
        inconsistency_votes += 1
    if roc_auc_f < 0.55:
        inconsistency_votes += 1
    if high_bands_overestimated:
        inconsistency_votes += 1
    draw_inconsistent = inconsistency_votes >= 2

    draw_reading = None
    if draw_inconsistent:
        draw_reading = (
            "Nel campione storico diagnostico la probabilità della X non mostra una "
            "calibrazione stabile: le classi non risultano monotone e le probabilità "
            "più alte tendono a essere sovrastimate."
        )

    evidence = build_balance_pillar_evidence_status(
        pillar="draw_credibility",
        sample_size=n,
        evidence_scope=scope,
        primary_metric={
            "draw_rate": proportion_block(draws, n),
            "brier": brier,
            "brier_skill": skill,
        },
        supporting_metrics=[{"discrimination": disc, "monotonicity": mono_status}],
        inconsistent=draw_inconsistent,
        warnings=["roc_auc_is_diagnostic_only"],
    )

    out = {
        "status": "ok",
        "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
        "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
        "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
        "bootstrap_iterations": int(bootstrap_iterations),
        "pillar": "draw_credibility",
        "role": PILLAR_META["draw_credibility"]["role"],
        "role_label": PILLAR_META["draw_credibility"]["meaning"],
        "filters": filters,
        "sample": _sample_counts(rows),
        "analytical_sample": {"settled_with_class": n},
        "global": {
            "draw_rate": proportion_block(draws, n),
            "predicted_x_mean": mean(p),
            "brier": brier,
            "baseline_brier": baseline_brier,
            "brier_skill_score": skill,
            "ece": ece.get("ece"),
            "discrimination": disc,
        },
        "by_class": class_stats,
        "calibration": ece,
        "monotonicity": {
            "status": mono_status,
            "transitions": transitions,
            "violations": violations,
        },
        "spearman_index_vs_draw": spearman_safe(idx, y_idx),
        "evidence": evidence,
    }
    if draw_reading:
        out["reading"] = draw_reading
    return make_json_safe(out)


def build_gap_empirical_analysis(
    db: Session,
    *,
    filters: dict[str, Any],
    bootstrap_iterations: int = BOOTSTRAP_ITERATIONS_DEFAULT,
) -> dict[str, Any]:
    rows = _query_rows(db, filters)
    settled = [
        r
        for r in rows
        if _is_settled_valid(r) and r.analysis_eligible and r.gap_class is not None
    ]
    scope = _evidence_scope(settled or rows)
    by_class: dict[str, list] = defaultdict(list)
    for r in settled:
        by_class[str(r.gap_class)].append(r)

    class_stats = []
    for raw, g in sorted(by_class.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        resolved = resolve_class("gap", raw)
        hits = [r for r in g if r.dominance_selection_hit is True]
        miss = [r for r in g if r.dominance_selection_hit is False]
        draws = sum(1 for r in g if r.is_draw)
        upsets = [r for r in g if _upset(r) is True]
        lateral = [
            r
            for r in g
            if (r.dominance_selection or "").upper() in {"1", "2"}
            and r.outcome_1x2 != OUTCOME_DRAW
        ]
        class_stats.append(
            {
                "class": raw,
                "label_it": resolved["label_it"],
                "is_registered": resolved.get("is_registered", False),
                "rows": len(g),
                "dominance_hit": proportion_block(len(hits), len(hits) + len(miss)),
                "draw_rate": proportion_block(draws, len(g)),
                "upset_rate": proportion_block(len(upsets), len(lateral) if lateral else 0),
                "average_absolute_goal_difference": mean(
                    [
                        float(r.absolute_goal_difference)
                        for r in g
                        if r.absolute_goal_difference is not None
                    ]
                ),
                "average_total_goals": mean(
                    [float(r.total_goals) for r in g if r.total_goals is not None]
                ),
            }
        )

    heat_dom = []
    heat_f36 = []
    for g_raw, gg in by_class.items():
        for d_raw in sorted({str(r.dominance_class or "missing") for r in settled}):
            g = [r for r in gg if str(r.dominance_class or "missing") == d_raw]
            if len(g) < MIN_ROWS_DESCRIPTIVE_CLASS:
                continue
            h = sum(1 for r in g if r.dominance_selection_hit)
            m = sum(1 for r in g if r.dominance_selection_hit is False)
            heat_dom.append(
                {
                    "gap_class": g_raw,
                    "dominance_class": d_raw,
                    "rows": len(g),
                    "dominance_hit": proportion_block(h, h + m),
                }
            )
        for f_raw in sorted({str(r.f36_class or "missing") for r in settled}):
            g = [r for r in gg if str(r.f36_class or "missing") == f_raw]
            if len(g) < MIN_ROWS_DESCRIPTIVE_CLASS:
                continue
            heat_f36.append(
                {
                    "gap_class": g_raw,
                    "f36_class": f_raw,
                    "rows": len(g),
                    "draw_rate": proportion_block(sum(1 for r in g if r.is_draw), len(g)),
                }
            )

    idx = [float(r.gap_index) for r in settled if r.gap_index is not None]
    hit_f = [
        1.0 if r.dominance_selection_hit else 0.0
        for r in settled
        if r.gap_index is not None and r.dominance_selection_hit is not None
    ]
    idx_hit = [
        float(r.gap_index)
        for r in settled
        if r.gap_index is not None and r.dominance_selection_hit is not None
    ]
    diffs = [
        float(r.absolute_goal_difference or 0)
        for r in settled
        if r.gap_index is not None
    ]
    draws_f = [1.0 if r.is_draw else 0.0 for r in settled if r.gap_index is not None]

    sp_hit = spearman_safe(idx_hit, hit_f)
    sp_diff = spearman_safe(idx, diffs)
    sp_draw = spearman_safe(idx, draws_f)
    rhos_g = [_spearman_abs(sp_hit), _spearman_abs(sp_diff), _spearman_abs(sp_draw)]
    adequate = [c for c in class_stats if int(c.get("rows") or 0) >= MIN_ROWS_DESCRIPTIVE_CLASS]
    total_rows = sum(int(c.get("rows") or 0) for c in class_stats) or 1
    top2 = sorted((int(c.get("rows") or 0) for c in class_stats), reverse=True)[:2]
    top2_share = (sum(top2) / total_rows) if top2 else 0.0
    concentrated = top2_share >= 0.90
    limited_classes = len(adequate) < 3
    rho_null = all(r < 0.10 for r in rhos_g)
    hit_rates = []
    for c in adequate:
        hr = (c.get("dominance_hit") or {}).get("rate")
        if hr is not None:
            try:
                hit_rates.append(float(hr))
            except (TypeError, ValueError):
                pass
    limited_diff = True
    if len(hit_rates) >= 2:
        limited_diff = (max(hit_rates) - min(hit_rates)) < 0.10

    gap_descriptive = limited_classes or concentrated or (rho_null and limited_diff)
    gap_warns = ["gap_is_not_autonomous_betting_signal"]
    if concentrated:
        gap_warns.append("class_distribution_concentrated")
    if gap_descriptive:
        gap_warns.append("limited_discriminative_evidence")

    evidence = build_balance_pillar_evidence_status(
        pillar="gap",
        sample_size=len(settled),
        evidence_scope=scope,
        primary_metric={"by_class_count": len(class_stats)},
        supporting_metrics=[
            {"spearman_vs_hit": sp_hit},
            {"spearman_vs_abs_diff": sp_diff},
            {"spearman_vs_draw": sp_draw},
        ],
        warnings=gap_warns,
        descriptive_structure=gap_descriptive,
    )

    return make_json_safe(
        {
            "status": "ok",
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "bootstrap_iterations": int(bootstrap_iterations),
            "pillar": "gap",
            "role": PILLAR_META["gap"]["role"],
            "role_label": PILLAR_META["gap"]["meaning"],
            "banner": (
                "Gap descrive coerenza matematica e non costituisce un segnale autonomo."
            ),
            "filters": filters,
            "sample": _sample_counts(rows),
            "analytical_sample": {"settled_with_class": len(settled)},
            "by_class": class_stats,
            "heatmap_gap_x_dominance": heat_dom,
            "heatmap_gap_x_f36": heat_f36,
            "trends": {
                "gap_index_vs_dominance_hit": sp_hit,
                "gap_index_vs_abs_diff": sp_diff,
                "gap_index_vs_is_draw": sp_draw,
            },
            "evidence": evidence,
        }
    )


def build_balance_empirical_dependency_analysis(
    db: Session,
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        r
        for r in _query_rows(db, filters)
        if _is_settled_valid(r) and r.analysis_eligible
    ]
    fields = {
        "f36": "f36_index",
        "dominance": "dominance_index",
        "draw_credibility": "draw_credibility_index",
        "gap": "gap_index",
    }
    matrix = {}
    for a, fa in fields.items():
        matrix[a] = {}
        for b, fb in fields.items():
            xa, yb = [], []
            for r in rows:
                va = getattr(r, fa)
                vb = getattr(r, fb)
                if va is None or vb is None:
                    continue
                xa.append(float(va))
                yb.append(float(vb))
            matrix[a][b] = spearman_safe(xa, yb)

    class_fields = {
        "f36": "f36_class",
        "dominance": "dominance_class",
        "draw_credibility": "draw_credibility_class",
        "gap": "gap_class",
    }
    cramers = {}
    keys = list(class_fields)
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            pairs = [
                (getattr(r, class_fields[a]), getattr(r, class_fields[b]))
                for r in rows
                if getattr(r, class_fields[a]) and getattr(r, class_fields[b])
            ]
            a_levels = sorted({p[0] for p in pairs})
            b_levels = sorted({p[1] for p in pairs})
            table = [
                [sum(1 for x, y in pairs if x == al and y == bl) for bl in b_levels]
                for al in a_levels
            ]
            cramers[f"{a}__{b}"] = chi_square_independence(table)

    return make_json_safe(
        {
            "status": "ok",
            "report": "pillar_dependency",
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "note": (
                "Diagnostica di dipendenza interna — non misura di qualità né base "
                "per score aggregato"
            ),
            "spearman_index_matrix": matrix,
            "cramers_v_classes": cramers,
            "sample_size": len(rows),
            "filters": filters,
        }
    )


def build_balance_empirical_stability_analysis(
    db: Session,
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        r
        for r in _query_rows(db, filters)
        if _is_settled_valid(r) and r.analysis_eligible
    ]
    by_month: dict[str, list] = defaultdict(list)
    for r in rows:
        if r.scan_date:
            by_month[r.scan_date.strftime("%Y-%m")].append(r)
    months = sorted(by_month)
    monthly = []
    prev_dist = None
    drift_status = "insufficient_data"
    for m in months:
        g = by_month[m]
        dist = Counter(str(r.f36_class or "missing") for r in g)
        hits = sum(1 for r in g if r.dominance_selection_hit is True)
        hit_n = sum(1 for r in g if r.dominance_selection_hit is not None)
        draws = sum(1 for r in g if r.is_draw)
        y = [1 if r.is_draw else 0 for r in g]
        p = []
        for r in g:
            px = r.prob_x_norm
            fv = 0.5 if px is None else float(px)
            if fv > 1.5:
                fv /= 100.0
            p.append(clamp_prob(fv))
        keys = sorted(set(dist) | (set(prev_dist) if prev_dist else set()))
        cur_vec = [dist.get(k, 0) for k in keys]
        psi = None
        js = None
        if prev_dist is not None and len(g) >= MIN_ROWS_MONTH:
            prev_vec = [prev_dist.get(k, 0) for k in keys]
            psi = population_stability_index(prev_vec, cur_vec)
            js = jensen_shannon(prev_vec, cur_vec)
            drift_status = classify_drift(psi)
        monthly.append(
            {
                "month": m,
                "rows": len(g),
                "data_status": (
                    "ok" if len(g) >= MIN_ROWS_MONTH else "insufficient_data"
                ),
                "f36_class_distribution": dict(dist),
                "dominance_hit": proportion_block(hits, hit_n),
                "draw_rate": proportion_block(draws, len(g)),
                "draw_brier": brier_score(y, p),
                "psi_vs_previous": psi,
                "js_vs_previous": js,
                "drift_status": drift_status if prev_dist else "insufficient_data",
            }
        )
        prev_dist = dist

    by_comp: dict[int, list] = defaultdict(list)
    for r in rows:
        if r.competition_id is not None:
            by_comp[int(r.competition_id)].append(r)
    competitions = []
    for cid, g in sorted(by_comp.items(), key=lambda kv: -len(kv[1])):
        if len(g) < MIN_ROWS_COMPETITION:
            continue
        hits = sum(1 for r in g if r.dominance_selection_hit is True)
        hit_n = sum(1 for r in g if r.dominance_selection_hit is not None)
        draws = sum(1 for r in g if r.is_draw)
        y = [1 if r.is_draw else 0 for r in g]
        p = []
        for r in g:
            px = r.prob_x_norm
            fv = 0.5 if px is None else float(px)
            if fv > 1.5:
                fv /= 100.0
            p.append(clamp_prob(fv))
        competitions.append(
            {
                "competition_id": cid,
                "rows": len(g),
                "dominance_hit": proportion_block(hits, hit_n),
                "draw_rate": proportion_block(draws, len(g)),
                "draw_brier": brier_score(y, p),
                "f36_class_distribution": dict(
                    Counter(str(r.f36_class or "missing") for r in g)
                ),
            }
        )

    return make_json_safe(
        {
            "status": "ok",
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
            "filters": filters,
            "sample": _sample_counts(rows),
            "months_observed": len(months),
            "competitions_compared": len(competitions),
            "by_month": monthly,
            "by_competition": competitions,
            "note": "Nessun random split; confronti solo con campione sufficiente",
        }
    )


def build_balance_empirical_data_health_analysis(
    db: Session,
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    rows = _query_rows(db, filters)
    sample = _sample_counts(rows)
    missing = {}
    cols = [
        "f36_class",
        "f36_index",
        "dominance_class",
        "dominance_index",
        "dominance_selection",
        "draw_credibility_class",
        "draw_credibility_index",
        "gap_class",
        "gap_index",
        "prob_1_norm",
        "prob_x_norm",
        "prob_2_norm",
        "outcome_1x2",
        "source_snapshot_at",
    ]
    for c in cols:
        missing[c] = sum(1 for r in rows if getattr(r, c) is None)

    unknown_classes = Counter()
    for r in rows:
        for pillar, field in (
            ("f36", "f36_class"),
            ("dominance", "dominance_class"),
            ("draw_credibility", "draw_credibility_class"),
            ("gap", "gap_class"),
        ):
            raw = getattr(r, field)
            if raw and not resolve_class(pillar, raw).get("is_registered"):
                unknown_classes[f"{pillar}:{raw}"] += 1

    invalid_probs = 0
    sum_out = 0
    for r in rows:
        probs = [r.prob_1_norm, r.prob_x_norm, r.prob_2_norm]
        if any(p is None for p in probs):
            continue
        vals = []
        for p in probs:
            fv = float(p)
            if fv > 1.5:
                fv /= 100.0
            if fv < 0 or fv > 1:
                invalid_probs += 1
            vals.append(fv)
        if abs(sum(vals) - 1.0) > PROB_SUM_TOLERANCE:
            sum_out += 1

    hash_dup = Counter((r.today_fixture_id, r.balance_version, r.snapshot_hash) for r in rows)
    fixture_ver_dup = Counter((r.today_fixture_id, r.balance_version) for r in rows if r.is_current)
    impossible = sum(
        1
        for r in rows
        if r.ft_home is not None and r.ft_away is not None and (r.ft_home < 0 or r.ft_away < 0)
    )

    return make_json_safe(
        {
            "status": "ok",
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "filters": filters,
            "cardinality": sample,
            "missingness": missing,
            "unknown_classes": dict(unknown_classes),
            "duplicate_hashes": sum(1 for _, c in hash_dup.items() if c > 1),
            "duplicate_current_fixture_version": sum(
                1 for _, c in fixture_ver_dup.items() if c > 1
            ),
            "invalid_probabilities": invalid_probs,
            "probabilities_sum_outside_tolerance": sum_out,
            "prob_sum_tolerance": PROB_SUM_TOLERANCE,
            "dominance_selection_missing": sum(
                1 for r in rows if not r.dominance_selection
            ),
            "outcome_missing": sum(
                1 for r in rows if r.evaluation_status == EVAL_SETTLED and not r.outcome_1x2
            ),
            "impossible_scores": impossible,
            "note": "Report diagnostico — dati originali non modificati né rinormalizzati",
        }
    )


def build_balance_empirical_analysis_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    source_cohort: str = "all",
) -> dict[str, Any]:
    filters = normalize_analysis_filters(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
    )
    rows = _query_rows(db, filters)
    settled = [r for r in rows if _is_settled_valid(r) and r.analysis_eligible]
    scope = _evidence_scope(settled or rows)
    evidence = {
        p: build_balance_pillar_evidence_status(
            pillar=p,
            sample_size=len(settled),
            evidence_scope=scope,
            primary_metric={"settled": len(settled)},
            warnings=["full_pillar_analysis_required_for_definitive_status"],
            analysis_not_run=True,
        )
        for p in ("f36", "dominance", "draw_credibility", "gap")
    }
    return make_json_safe(
        {
            "status": "ok",
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "filters": filters,
            "sample": _sample_counts(rows),
            "evidence_scope": scope,
            "class_registry": build_class_registry_payload(),
            "policy": build_statistical_policy_payload(),
            "pillar_evidence_status": evidence,
            "notes": [
                "Status pilastri definitivi solo dopo analisi completa / job",
                "Analisi descrittiva/esplorativa — historical_diagnostic non promuove",
                "Nessun score aggregato dei quattro pilastri",
                "pending esclusi dalle metriche prestazionali",
            ],
        }
    )


def build_balance_empirical_full_analysis(
    db: Session,
    *,
    filters: dict[str, Any],
    bootstrap_iterations: int = BOOTSTRAP_ITERATIONS_DEFAULT,
) -> dict[str, Any]:
    iters = int(bootstrap_iterations)
    if iters < BOOTSTRAP_ITERATIONS_MIN or iters > BOOTSTRAP_ITERATIONS_MAX:
        raise ValueError(
            f"bootstrap_iterations must be in "
            f"[{BOOTSTRAP_ITERATIONS_MIN}, {BOOTSTRAP_ITERATIONS_MAX}]"
        )
    overview = build_balance_empirical_analysis_overview(
        db,
        date_from=date.fromisoformat(filters["date_from"]),
        date_to=date.fromisoformat(filters["date_to"]),
        competition_id=filters.get("competition_id"),
        source_cohort=filters.get("source_cohort") or "all",
    )
    f36 = build_f36_empirical_analysis(
        db, filters=filters, bootstrap_iterations=iters
    )
    dominance = build_dominance_empirical_analysis(
        db, filters=filters, bootstrap_iterations=iters
    )
    draw_credibility = build_draw_credibility_empirical_analysis(
        db, filters=filters, bootstrap_iterations=iters
    )
    gap = build_gap_empirical_analysis(
        db, filters=filters, bootstrap_iterations=iters
    )
    pillar_evidence = build_balance_full_pillar_evidence_status(
        f36_analysis=f36,
        dominance_analysis=dominance,
        draw_credibility_analysis=draw_credibility,
        gap_analysis=gap,
    )
    overview = dict(overview)
    overview["pillar_evidence_status"] = pillar_evidence
    overview["notes"] = [
        n
        for n in (overview.get("notes") or [])
        if "overview_only" not in str(n).lower()
        and "full_pillar_analysis_required" not in str(n).lower()
    ] + ["pillar_evidence_status from full pillar analyses"]

    return make_json_safe(
        {
            "status": "ok",
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "bootstrap_iterations": iters,
            "bootstrap_iterations_requested": iters,
            "bootstrap_iterations_effective": iters,
            "filters": filters,
            "overview": overview,
            "pillar_evidence_status": pillar_evidence,
            "f36": f36,
            "dominance": dominance,
            "draw_credibility": draw_credibility,
            "gap": gap,
            "dependency": build_balance_empirical_dependency_analysis(
                db, filters=filters
            ),
            "stability": build_balance_empirical_stability_analysis(
                db, filters=filters
            ),
            "data_health": build_balance_empirical_data_health_analysis(
                db, filters=filters
            ),
        }
    )


def _cached_build(
    db: Session,
    *,
    pillar: str,
    filters: dict[str, Any],
    bootstrap_iterations: int,
    builder,
) -> dict[str, Any]:
    key = (
        BALANCE_EMPIRICAL_ANALYSIS_VERSION,
        BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
        BALANCE_EMPIRICAL_DATASET_VERSION,
        pillar,
        tuple(sorted(filters.items())),
        int(bootstrap_iterations),
        _max_updated_at(db),
    )
    hit = _cache_get(key)
    if hit is not None:
        out = dict(hit)
        out["cache_hit"] = True
        return out
    payload = builder()
    _cache_set(key, payload)
    out = dict(payload)
    out["cache_hit"] = False
    return out


# Convenience wrappers with cache for API
def get_f36_analysis(db: Session, **kwargs) -> dict[str, Any]:
    filters = kwargs.pop("filters")
    boot = kwargs.get("bootstrap_iterations", BOOTSTRAP_ITERATIONS_DEFAULT)
    return _cached_build(
        db,
        pillar="f36",
        filters=filters,
        bootstrap_iterations=boot,
        builder=lambda: build_f36_empirical_analysis(
            db, filters=filters, bootstrap_iterations=boot
        ),
    )


def get_dominance_analysis(db: Session, **kwargs) -> dict[str, Any]:
    filters = kwargs.pop("filters")
    boot = kwargs.get("bootstrap_iterations", BOOTSTRAP_ITERATIONS_DEFAULT)
    return _cached_build(
        db,
        pillar="dominance",
        filters=filters,
        bootstrap_iterations=boot,
        builder=lambda: build_dominance_empirical_analysis(
            db, filters=filters, bootstrap_iterations=boot
        ),
    )


def get_draw_credibility_analysis(db: Session, **kwargs) -> dict[str, Any]:
    filters = kwargs.pop("filters")
    boot = kwargs.get("bootstrap_iterations", BOOTSTRAP_ITERATIONS_DEFAULT)
    return _cached_build(
        db,
        pillar="draw_credibility",
        filters=filters,
        bootstrap_iterations=boot,
        builder=lambda: build_draw_credibility_empirical_analysis(
            db, filters=filters, bootstrap_iterations=boot
        ),
    )


def get_gap_analysis(db: Session, **kwargs) -> dict[str, Any]:
    filters = kwargs.pop("filters")
    boot = kwargs.get("bootstrap_iterations", BOOTSTRAP_ITERATIONS_DEFAULT)
    return _cached_build(
        db,
        pillar="gap",
        filters=filters,
        bootstrap_iterations=boot,
        builder=lambda: build_gap_empirical_analysis(
            db, filters=filters, bootstrap_iterations=boot
        ),
    )
