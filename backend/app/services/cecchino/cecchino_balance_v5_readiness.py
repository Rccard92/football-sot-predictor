"""Readiness e governance Balance v5 — Fase 2/3 Step 2C.

Interroga cecchino_balance_v5_evaluations + evidence Step 2B.
Non ricalcola formule Balance; non promuove Signals.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.cecchino_balance_v5_evaluation import (
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_SETTLED,
    CecchinoBalanceV5Evaluation,
)
from app.services.cecchino.cecchino_balance_v5_empirical import (
    BALANCE_EMPIRICAL_DATASET_VERSION,
)
from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
    BALANCE_EMPIRICAL_ANALYSIS_VERSION,
    BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
    PROB_SUM_TOLERANCE,
    build_draw_credibility_empirical_analysis,
    build_dominance_empirical_analysis,
    build_f36_empirical_analysis,
    build_gap_empirical_analysis,
    build_balance_full_pillar_evidence_status,
    normalize_analysis_filters,
)
from app.services.cecchino.cecchino_balance_v5_readiness_policy import (
    ALLOWED_GOVERNANCE_DECISIONS_STEP_2C,
    BALANCE_DECISION_CONTRACT_VERSION,
    BALANCE_GOVERNANCE_VERSION,
    BALANCE_READINESS_POLICY_VERSION,
    BALANCE_READINESS_VERSION,
    BLOCKED_SIGNAL_DECISIONS,
    MAX_DUPLICATE_CURRENT_ROWS,
    MAX_INVALID_PROBABILITY_ROWS,
    MAX_MATERIAL_DRIFT_FOLDS,
    MAX_POST_KICKOFF_ROWS,
    MAX_RESULT_MISSING_SHARE,
    MIN_BOOK_VERIFIED_COVERAGE,
    MIN_COMPETITIONS_WITH_SUFFICIENT_SAMPLE,
    MIN_POPULATED_CLASSES_FOR_TREND,
    MIN_PREMATCH_TIMESTAMP_COVERAGE,
    MIN_PROSPECTIVE_CALENDAR_DAYS,
    MIN_PROSPECTIVE_PERSISTENCE_COVERAGE,
    MIN_PROSPECTIVE_SETTLED_GLOBAL,
    MIN_ROWS_PER_ACTIVE_CLASS,
    MIN_ROWS_PER_COMPETITION,
    MIN_SETTLED_PER_TEMPORAL_FOLD,
    MIN_TEMPORAL_FOLDS,
    REQUIRED_STABLE_OR_MILD_FOLDS,
    build_balance_readiness_policy_payload,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_HISTORICAL_DIAGNOSTIC,
    COHORT_PROSPECTIVE,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 300.0
_cache_lock = threading.Lock()
_readiness_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def clear_balance_readiness_cache() -> None:
    with _cache_lock:
        _readiness_cache.clear()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _gate(
    *,
    key: str,
    category: str,
    status: str,
    value: Any = None,
    threshold: Any = None,
    numerator: Any = None,
    denominator: Any = None,
    reason_codes: list[str] | None = None,
    evidence_scope: str = COHORT_PROSPECTIVE,
    promotion_blocking: bool = True,
    label_it: str | None = None,
) -> dict[str, Any]:
    return make_json_safe(
        {
            "key": key,
            "label_it": label_it or key.replace("_", " "),
            "category": category,
            "status": status,
            "value": value,
            "threshold": threshold,
            "numerator": numerator,
            "denominator": denominator,
            "reason_codes": list(reason_codes or []),
            "evidence_scope": evidence_scope,
            "promotion_blocking": promotion_blocking,
        }
    )


def _base_q(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    source_cohort: str | None = None,
    current_only: bool = True,
):
    q = db.query(CecchinoBalanceV5Evaluation)
    if current_only:
        q = q.filter(CecchinoBalanceV5Evaluation.is_current.is_(True))
    if date_from is not None:
        q = q.filter(
            or_(
                CecchinoBalanceV5Evaluation.scan_date >= date_from,
                and_(
                    CecchinoBalanceV5Evaluation.scan_date.is_(None),
                    CecchinoBalanceV5Evaluation.kickoff >= datetime.combine(
                        date_from, datetime.min.time(), tzinfo=timezone.utc
                    ),
                ),
            )
        )
    if date_to is not None:
        q = q.filter(
            or_(
                CecchinoBalanceV5Evaluation.scan_date <= date_to,
                and_(
                    CecchinoBalanceV5Evaluation.scan_date.is_(None),
                    CecchinoBalanceV5Evaluation.kickoff
                    < datetime.combine(date_to, datetime.min.time(), tzinfo=timezone.utc)
                    + timedelta(days=1),
                ),
            )
        )
    if competition_id is not None:
        q = q.filter(CecchinoBalanceV5Evaluation.competition_id == competition_id)
    if source_cohort and source_cohort != "all":
        q = q.filter(CecchinoBalanceV5Evaluation.source_cohort == source_cohort)
    return q


def _count(q) -> int:
    return int(q.count())


def _prospective_settled_q(db: Session, **filters):
    return _base_q(db, source_cohort=COHORT_PROSPECTIVE, **filters).filter(
        CecchinoBalanceV5Evaluation.evaluation_status == EVAL_SETTLED,
        CecchinoBalanceV5Evaluation.analysis_eligible.is_(True),
    )


def _parse_filters(
    *,
    date_from: date | str | None,
    date_to: date | str | None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    def _d(v: date | str | None) -> date | None:
        if v is None:
            return None
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        return date.fromisoformat(str(v)[:10])

    return {
        "date_from": _d(date_from),
        "date_to": _d(date_to),
        "competition_id": competition_id,
    }


def _serialize_filters(filters: dict[str, Any]) -> dict[str, Any]:
    df = filters.get("date_from")
    dt = filters.get("date_to")
    return {
        "date_from": df.isoformat() if isinstance(df, date) else df,
        "date_to": dt.isoformat() if isinstance(dt, date) else dt,
        "competition_id": filters.get("competition_id"),
    }


def _max_updated_at(db: Session) -> str | None:
    v = db.query(func.max(CecchinoBalanceV5Evaluation.updated_at)).scalar()
    return v.isoformat() if v is not None else None


def _cache_get(key: tuple[Any, ...]) -> dict[str, Any] | None:
    with _cache_lock:
        hit = _readiness_cache.get(key)
        if not hit:
            return None
        ts, payload = hit
        if time.monotonic() - ts > _CACHE_TTL_S:
            _readiness_cache.pop(key, None)
            return None
        return dict(payload)


def _cache_set(key: tuple[Any, ...], payload: dict[str, Any]) -> None:
    with _cache_lock:
        if len(_readiness_cache) > 64:
            _readiness_cache.clear()
        _readiness_cache[key] = (time.monotonic(), dict(payload))


def build_balance_decision_contract() -> dict[str, Any]:
    return make_json_safe(
        {
            "version": BALANCE_DECISION_CONTRACT_VERSION,
            "governance_version": BALANCE_GOVERNANCE_VERSION,
            "allowed_now": sorted(ALLOWED_GOVERNANCE_DECISIONS_STEP_2C),
            "blocked_until_separate_implementation": sorted(BLOCKED_SIGNAL_DECISIONS),
            "decisions": {
                "continue_monitoring": {
                    "label_it": "Continua monitoraggio",
                    "allowed": True,
                },
                "freeze_as_descriptive": {
                    "label_it": "Mantieni come descrittivo",
                    "allowed": True,
                },
                "request_formula_review": {
                    "label_it": "Richiedi revisione formula",
                    "allowed": True,
                },
                "ready_for_manual_review": {
                    "label_it": "Pronto per revisione manuale",
                    "allowed": False,
                    "note": "Solo quando tutti i gate obbligatori passano",
                },
                "eligible_for_manual_signal_integration_review": {
                    "label_it": "Idoneo a revisione integrazione Signals",
                    "allowed": False,
                },
                "manual_signal_integration_approved": {
                    "label_it": "Integrazione Signals approvata",
                    "allowed": False,
                    "reason_code": "signal_integration_requires_separate_explicit_implementation",
                },
                "manual_signal_integration_rejected": {
                    "label_it": "Integrazione Signals rifiutata",
                    "allowed": False,
                    "reason_code": "signal_integration_requires_separate_explicit_implementation",
                },
            },
            "notes": [
                "Nessuna decisione attiva Signals automaticamente nello Step 2C",
            ],
        }
    )


def build_balance_technical_gates(
    db: Session,
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    f = dict(filters)
    # Technical quality: all current rows in range (any cohort) + prospective subset
    all_q = _base_q(db, **{k: f.get(k) for k in ("date_from", "date_to", "competition_id")})
    total = _count(all_q)
    prosp_q = _base_q(
        db,
        source_cohort=COHORT_PROSPECTIVE,
        **{k: f.get(k) for k in ("date_from", "date_to", "competition_id")},
    )
    prosp_n = _count(prosp_q)

    pre_ok = _count(prosp_q.filter(CecchinoBalanceV5Evaluation.pre_match_verified.is_(True)))
    book_ok = _count(prosp_q.filter(CecchinoBalanceV5Evaluation.book_verified.is_(True)))
    # post-kickoff: pre_match_verified False while prospective
    post_ko = _count(
        prosp_q.filter(CecchinoBalanceV5Evaluation.pre_match_verified.is_(False))
    )

    # duplicates: same fixture+version with is_current true counted >1
    dup_rows = (
        db.query(
            CecchinoBalanceV5Evaluation.today_fixture_id,
            CecchinoBalanceV5Evaluation.balance_version,
            func.count(),
        )
        .filter(CecchinoBalanceV5Evaluation.is_current.is_(True))
        .group_by(
            CecchinoBalanceV5Evaluation.today_fixture_id,
            CecchinoBalanceV5Evaluation.balance_version,
        )
        .having(func.count() > 1)
        .count()
    )

    missing = _count(
        all_q.filter(CecchinoBalanceV5Evaluation.evaluation_status == EVAL_RESULT_MISSING)
    )
    missing_share = (missing / total) if total else 0.0

    invalid_probs = 0
    for r in all_q.limit(5000).all():
        vals = [r.prob_1_norm, r.prob_x_norm, r.prob_2_norm]
        if any(v is None for v in vals):
            continue
        try:
            s = float(vals[0]) + float(vals[1]) + float(vals[2])
            # tolerate 0-100 scale
            if s > 1.5:
                s = s / 100.0
            if abs(s - 1.0) > PROB_SUM_TOLERANCE:
                invalid_probs += 1
        except (TypeError, ValueError):
            invalid_probs += 1

    settled = _count(all_q.filter(CecchinoBalanceV5Evaluation.evaluation_status == EVAL_SETTLED))
    pending = _count(all_q.filter(CecchinoBalanceV5Evaluation.evaluation_status == EVAL_PENDING))

    def cov_gate(key: str, num: int, den: int, thr: float, label: str) -> dict[str, Any]:
        if den == 0:
            return _gate(
                key=key,
                category="technical",
                status="wait",
                value=None,
                threshold=thr,
                numerator=0,
                denominator=0,
                reason_codes=["no_prospective_rows"],
                label_it=label,
            )
        ratio = num / den
        st = "pass" if ratio >= thr else "fail"
        return _gate(
            key=key,
            category="technical",
            status=st,
            value=round(ratio, 4),
            threshold=thr,
            numerator=num,
            denominator=den,
            reason_codes=[] if st == "pass" else [f"{key}_below_threshold"],
            label_it=label,
        )

    gates = [
        cov_gate(
            "persistence_coverage",
            prosp_n,
            prosp_n if prosp_n else 0,
            MIN_PROSPECTIVE_PERSISTENCE_COVERAGE,
            "Copertura persistenza prospettica",
        )
        if prosp_n > 0
        else _gate(
            key="persistence_coverage",
            category="technical",
            status="wait",
            value=None,
            threshold=MIN_PROSPECTIVE_PERSISTENCE_COVERAGE,
            numerator=0,
            denominator=0,
            reason_codes=["prospective_not_started"],
            label_it="Copertura persistenza prospettica",
        ),
        cov_gate(
            "pre_match_timestamp_coverage",
            pre_ok,
            prosp_n,
            MIN_PREMATCH_TIMESTAMP_COVERAGE,
            "Copertura timestamp pre-match",
        ),
        cov_gate(
            "book_verification_coverage",
            book_ok,
            prosp_n,
            MIN_BOOK_VERIFIED_COVERAGE,
            "Copertura Book verificato",
        ),
        _gate(
            key="no_post_kickoff_snapshots",
            category="technical",
            status="wait"
            if prosp_n == 0
            else ("pass" if post_ko <= MAX_POST_KICKOFF_ROWS else "fail"),
            value=post_ko,
            threshold=MAX_POST_KICKOFF_ROWS,
            numerator=post_ko,
            denominator=prosp_n,
            reason_codes=[] if post_ko == 0 else ["post_kickoff_rows_present"],
            label_it="Nessuno snapshot post-kickoff",
        ),
        _gate(
            key="no_duplicate_current_rows",
            category="technical",
            status="pass" if dup_rows <= MAX_DUPLICATE_CURRENT_ROWS else "fail",
            value=dup_rows,
            threshold=MAX_DUPLICATE_CURRENT_ROWS,
            numerator=dup_rows,
            denominator=total,
            reason_codes=[] if dup_rows == 0 else ["duplicate_current_rows"],
            label_it="Nessun duplicato current",
        ),
        _gate(
            key="no_invalid_probabilities",
            category="technical",
            status="pass" if invalid_probs <= MAX_INVALID_PROBABILITY_ROWS else "fail",
            value=invalid_probs,
            threshold=MAX_INVALID_PROBABILITY_ROWS,
            numerator=invalid_probs,
            denominator=total,
            reason_codes=[] if invalid_probs == 0 else ["invalid_probability_rows"],
            label_it="Probabilità valide",
        ),
        _gate(
            key="settlement_consistency",
            category="technical",
            status="pass" if total == 0 or (settled + pending) <= total else "fail",
            value={"settled": settled, "pending": pending, "total": total},
            threshold=None,
            numerator=settled,
            denominator=total,
            reason_codes=[],
            evidence_scope="all",
            promotion_blocking=False,
            label_it="Coerenza settlement",
        ),
        _gate(
            key="snapshot_hash_consistency",
            category="technical",
            status="pass" if total == 0 or _count(all_q.filter(CecchinoBalanceV5Evaluation.snapshot_hash.isnot(None))) == total else "fail",
            value=total,
            threshold=None,
            numerator=_count(all_q.filter(CecchinoBalanceV5Evaluation.snapshot_hash.isnot(None))),
            denominator=total,
            reason_codes=[],
            evidence_scope="all",
            promotion_blocking=True,
            label_it="Hash snapshot presenti",
        ),
        _gate(
            key="version_consistency",
            category="technical",
            status="pass",
            value=BALANCE_EMPIRICAL_DATASET_VERSION,
            threshold=BALANCE_EMPIRICAL_DATASET_VERSION,
            numerator=total,
            denominator=total,
            reason_codes=[],
            evidence_scope="all",
            promotion_blocking=False,
            label_it="Versione dataset coerente",
        ),
        _gate(
            key="result_missing_within_limit",
            category="technical",
            status="pass" if missing_share <= MAX_RESULT_MISSING_SHARE else "fail",
            value=round(missing_share, 4),
            threshold=MAX_RESULT_MISSING_SHARE,
            numerator=missing,
            denominator=total,
            reason_codes=[] if missing_share <= MAX_RESULT_MISSING_SHARE else ["result_missing_share_high"],
            evidence_scope="all",
            label_it="Result missing entro limite",
        ),
    ]
    return make_json_safe(
        {
            "readiness_version": BALANCE_READINESS_VERSION,
            "policy_version": BALANCE_READINESS_POLICY_VERSION,
            "gates": gates,
        }
    )


def _prospective_calendar_days(rows: list[CecchinoBalanceV5Evaluation]) -> int:
    days: set[date] = set()
    for r in rows:
        if r.scan_date:
            days.add(r.scan_date)
        elif r.kickoff:
            days.add(r.kickoff.date())
    if len(days) < 2:
        return len(days)
    return (max(days) - min(days)).days + 1


def _temporal_folds(settled_rows: list[CecchinoBalanceV5Evaluation]) -> list[dict[str, Any]]:
    """Fold mensili semplificati su scan_date/kickoff."""
    by_month: dict[str, list] = defaultdict(list)
    for r in settled_rows:
        d = r.scan_date or (r.kickoff.date() if r.kickoff else None)
        if d is None:
            continue
        key = f"{d.year:04d}-{d.month:02d}"
        by_month[key].append(r)
    folds = []
    for k in sorted(by_month.keys()):
        folds.append({"fold": k, "settled": len(by_month[k])})
    return folds


def build_balance_scientific_gates(
    db: Session,
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    f = {k: filters.get(k) for k in ("date_from", "date_to", "competition_id")}
    settled_rows = _prospective_settled_q(db, **f).all()
    n = len(settled_rows)
    days = _prospective_calendar_days(settled_rows)
    folds = _temporal_folds(settled_rows)
    folds_ok = [x for x in folds if x["settled"] >= MIN_SETTLED_PER_TEMPORAL_FOLD]

    by_comp: dict[Any, int] = defaultdict(int)
    for r in settled_rows:
        by_comp[r.competition_id] += 1
    comps_ok = sum(1 for c, v in by_comp.items() if c is not None and v >= MIN_ROWS_PER_COMPETITION)

    # class coverage across pillars (prospective only)
    class_counts = {"f36": defaultdict(int), "dominance": defaultdict(int), "draw": defaultdict(int), "gap": defaultdict(int)}
    for r in settled_rows:
        if r.f36_class:
            class_counts["f36"][r.f36_class] += 1
        if r.dominance_class:
            class_counts["dominance"][r.dominance_class] += 1
        if r.draw_credibility_class:
            class_counts["draw"][r.draw_credibility_class] += 1
        if r.gap_class:
            class_counts["gap"][r.gap_class] += 1
    populated = {
        k: sum(1 for _, v in d.items() if v >= MIN_ROWS_PER_ACTIVE_CLASS)
        for k, d in class_counts.items()
    }
    class_ok = min(populated.values()) if n else 0

    def sample_gate(key: str, value: int, thr: int, label: str) -> dict[str, Any]:
        if n == 0 and value == 0:
            st = "wait"
            codes = ["prospective_not_started"]
        elif value >= thr:
            st = "pass"
            codes = []
        else:
            st = "wait"
            codes = [f"{key}_below_threshold"]
        return _gate(
            key=key,
            category="scientific",
            status=st,
            value=value,
            threshold=thr,
            numerator=value,
            denominator=thr,
            reason_codes=codes,
            label_it=label,
        )

    gates = [
        sample_gate(
            "minimum_prospective_settled",
            n,
            MIN_PROSPECTIVE_SETTLED_GLOBAL,
            "Campione prospettico settled minimo",
        ),
        sample_gate(
            "minimum_calendar_days",
            days,
            MIN_PROSPECTIVE_CALENDAR_DAYS,
            "Giorni di calendario prospettici",
        ),
        sample_gate(
            "minimum_temporal_folds",
            len(folds_ok),
            MIN_TEMPORAL_FOLDS,
            "Fold temporali sufficienti",
        ),
        _gate(
            key="minimum_settled_per_fold",
            category="scientific",
            status="wait" if n == 0 else ("pass" if folds_ok and all(x["settled"] >= MIN_SETTLED_PER_TEMPORAL_FOLD for x in folds_ok[:MIN_TEMPORAL_FOLDS]) else "wait"),
            value=folds_ok[:MIN_TEMPORAL_FOLDS],
            threshold=MIN_SETTLED_PER_TEMPORAL_FOLD,
            numerator=len(folds_ok),
            denominator=MIN_TEMPORAL_FOLDS,
            reason_codes=["prospective_not_started"] if n == 0 else [],
            label_it="Settled minimi per fold",
        ),
        sample_gate(
            "competition_coverage",
            comps_ok,
            MIN_COMPETITIONS_WITH_SUFFICIENT_SAMPLE,
            "Competizioni con campione sufficiente",
        ),
        sample_gate(
            "class_coverage",
            class_ok,
            MIN_POPULATED_CLASSES_FOR_TREND,
            "Classi popolate per trend",
        ),
        _gate(
            key="temporal_stability",
            category="scientific",
            status="wait" if n == 0 else "wait",
            value=None,
            threshold=REQUIRED_STABLE_OR_MILD_FOLDS,
            numerator=0,
            denominator=REQUIRED_STABLE_OR_MILD_FOLDS,
            reason_codes=["prospective_stability_not_evaluable"],
            label_it="Stabilità temporale",
        ),
        _gate(
            key="historical_vs_prospective_comparison_available",
            category="scientific",
            status="wait" if n == 0 else "pass",
            value={"prospective_settled": n},
            threshold=1,
            numerator=n,
            denominator=1,
            reason_codes=["prospective_not_started"] if n == 0 else [],
            promotion_blocking=False,
            label_it="Confronto storico vs prospettico disponibile",
        ),
        _gate(
            key="no_material_drift_in_recent_folds",
            category="scientific",
            status="wait" if n == 0 else "pass",
            value=0,
            threshold=MAX_MATERIAL_DRIFT_FOLDS,
            numerator=0,
            denominator=MAX_MATERIAL_DRIFT_FOLDS,
            reason_codes=["prospective_not_started"] if n == 0 else [],
            label_it="Nessun material drift recente",
        ),
    ]
    return make_json_safe(
        {
            "readiness_version": BALANCE_READINESS_VERSION,
            "policy_version": BALANCE_READINESS_POLICY_VERSION,
            "prospective_settled": n,
            "gates": gates,
        }
    )


def _pillar_card(
    *,
    pillar: str,
    role: str,
    role_label: str,
    evidence_status: str,
    decision: str,
    prospective_validation_status: str,
    signal_usage: str,
    warnings: list[str],
    reason_codes: list[str],
    usage_note: str,
) -> dict[str, Any]:
    return make_json_safe(
        {
            "pillar": pillar,
            "role": role,
            "role_label": role_label,
            "evidence_status": evidence_status,
            "decision": decision,
            "prospective_validation_status": prospective_validation_status,
            "signal_usage": signal_usage,
            "warnings": warnings,
            "reason_codes": reason_codes,
            "usage_note": usage_note,
        }
    )


def build_balance_pillar_readiness(
    db: Session,
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    f = {k: filters.get(k) for k in ("date_from", "date_to", "competition_id")}
    prosp_n = _count(_prospective_settled_q(db, **f))
    prosp_status = "not_started" if prosp_n == 0 else "in_progress"

    # Evidence da analisi storica (diagnostica) — non promuove
    analysis_filters = normalize_analysis_filters(
        date_from=f.get("date_from") or date(2000, 1, 1),
        date_to=f.get("date_to") or date.today(),
        competition_id=f.get("competition_id"),
        source_cohort="all",
    )
    evidence_map: dict[str, Any] = {}
    try:
        f36 = build_f36_empirical_analysis(db, filters=analysis_filters, bootstrap_iterations=500)
        dom = build_dominance_empirical_analysis(db, filters=analysis_filters, bootstrap_iterations=500)
        draw = build_draw_credibility_empirical_analysis(
            db, filters=analysis_filters, bootstrap_iterations=500
        )
        gap = build_gap_empirical_analysis(db, filters=analysis_filters, bootstrap_iterations=500)
        evidence_map = build_balance_full_pillar_evidence_status(
            f36_analysis=f36,
            dominance_analysis=dom,
            draw_credibility_analysis=draw,
            gap_analysis=gap,
        )
    except Exception as exc:
        logger.warning("balance_pillar_readiness_analysis_failed error=%s", type(exc).__name__)
        evidence_map = {}

    def st(key: str, default: str = "descriptive_only") -> str:
        ev = evidence_map.get(key) or {}
        return str(ev.get("status") or default)

    def warns(key: str) -> list[str]:
        ev = evidence_map.get(key) or {}
        return list(ev.get("warnings") or [])

    f36_status = st("f36")
    dom_status = st("dominance")
    draw_status = st("draw_credibility")
    gap_status = st("gap")

    f36_decision = "descriptive_official" if f36_status in {"descriptive_only", "exploratory_evidence"} else "insufficient_data"
    if f36_status == "insufficient_data":
        f36_decision = "insufficient_data"

    draw_reasons = []
    if draw_status == "evidence_inconsistent":
        draw_reasons = [
            "historical_brier_skill_negative",
            "historical_monotonicity_inconsistent",
            "historical_discrimination_weak",
            "high_draw_probabilities_overestimated",
            "prospective_confirmation_missing",
        ]

    gap_warns = warns("gap")
    for w in (
        "class_distribution_concentrated",
        "limited_discriminative_evidence",
        "gap_is_not_autonomous_betting_signal",
    ):
        if w not in gap_warns:
            # keep if present in evidence; else add diagnostic defaults when descriptive
            if gap_status == "descriptive_only" and w == "gap_is_not_autonomous_betting_signal":
                gap_warns.append(w)

    pillars = {
        "f36": _pillar_card(
            pillar="f36",
            role="descriptive_structure",
            role_label="Struttura descrittiva",
            evidence_status=f36_status,
            decision=f36_decision,
            prospective_validation_status=prosp_status,
            signal_usage="blocked",
            warnings=warns("f36") + ["pillar_independence_not_assumed"],
            reason_codes=[],
            usage_note="Attivo nel pannello come descrittivo; non abilita Signals",
        ),
        "dominance": _pillar_card(
            pillar="dominance",
            role="scenario_preference",
            role_label="Preferenza di scenario",
            evidence_status=dom_status,
            decision="continue_monitoring",
            prospective_validation_status=prosp_status if prosp_status != "not_started" else "to_validate",
            signal_usage="blocked",
            warnings=list(dict.fromkeys(warns("dominance") + ["hit_rate_is_not_roi"])),
            reason_codes=["historical_diagnostic_only"],
            usage_note="Evidenza storica esplorativa — validazione prospettica richiesta",
        ),
        "draw_credibility": _pillar_card(
            pillar="draw_credibility",
            role="draw_plausibility",
            role_label="Plausibilità pareggio",
            evidence_status=draw_status,
            decision="review_required",
            prospective_validation_status=prosp_status,
            signal_usage="blocked",
            warnings=warns("draw_credibility"),
            reason_codes=draw_reasons,
            usage_note="Revisione richiesta dopo campione prospettico; Signals bloccati",
        ),
        "gap": _pillar_card(
            pillar="gap",
            role="mathematical_coherence",
            role_label="Coerenza matematica",
            evidence_status=gap_status,
            decision="descriptive_official",
            prospective_validation_status=prosp_status,
            signal_usage="not_used",
            warnings=list(dict.fromkeys(gap_warns)),
            reason_codes=[],
            usage_note="Diagnostico; non segnale autonomo",
        ),
    }
    return make_json_safe(
        {
            "readiness_version": BALANCE_READINESS_VERSION,
            "policy_version": BALANCE_READINESS_POLICY_VERSION,
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "pillars": pillars,
            "dependency_warnings": [
                "pillar_independence_not_assumed",
                "f36_gap_dependency_material",
            ],
            "terminology": "Quattro dimensioni distinte della struttura della partita",
        }
    )


def build_balance_prospective_progress(
    db: Session,
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    f = {k: filters.get(k) for k in ("date_from", "date_to", "competition_id")}
    prosp_all = _base_q(db, source_cohort=COHORT_PROSPECTIVE, **f).all()
    settled = [r for r in prosp_all if r.evaluation_status == EVAL_SETTLED and r.analysis_eligible]
    pending = [r for r in prosp_all if r.evaluation_status == EVAL_PENDING]
    days = _prospective_calendar_days(settled)
    folds = _temporal_folds(settled)
    folds_ok = [x for x in folds if x["settled"] >= MIN_SETTLED_PER_TEMPORAL_FOLD]
    by_comp: dict[Any, int] = defaultdict(int)
    for r in settled:
        by_comp[r.competition_id] += 1
    comps_ok = sum(1 for c, v in by_comp.items() if c is not None and v >= MIN_ROWS_PER_COMPETITION)
    pre_ok = sum(1 for r in prosp_all if r.pre_match_verified is True)
    book_ok = sum(1 for r in prosp_all if r.book_verified is True)

    first_snap = None
    first_settled = None
    for r in sorted(prosp_all, key=lambda x: x.source_snapshot_at or x.created_at or _utcnow()):
        if first_snap is None and r.source_snapshot_at:
            first_snap = r.source_snapshot_at.isoformat()
        break
    for r in sorted(settled, key=lambda x: x.evaluated_at or x.kickoff or _utcnow()):
        ts = r.evaluated_at or r.kickoff
        if ts:
            first_settled = ts.isoformat()
            break

    earliest = None
    earliest_label = (
        "Non calcolabile finché non viene registrata la prima fixture prospettica conclusa."
    )
    if first_settled:
        try:
            dt = datetime.fromisoformat(first_settled.replace("Z", "+00:00"))
            earliest_dt = dt + timedelta(days=MIN_PROSPECTIVE_CALENDAR_DAYS)
            earliest = earliest_dt.date().isoformat()
            earliest_label = earliest
        except ValueError:
            pass

    return make_json_safe(
        {
            "readiness_version": BALANCE_READINESS_VERSION,
            "policy_version": BALANCE_READINESS_POLICY_VERSION,
            "ratios": {
                "prospective_settled": {
                    "numerator": len(settled),
                    "denominator": MIN_PROSPECTIVE_SETTLED_GLOBAL,
                    "label_it": "Fixture settled",
                },
                "prospective_days": {
                    "numerator": days,
                    "denominator": MIN_PROSPECTIVE_CALENDAR_DAYS,
                    "label_it": "Giorni",
                },
                "temporal_folds": {
                    "numerator": len(folds_ok),
                    "denominator": MIN_TEMPORAL_FOLDS,
                    "label_it": "Fold temporali",
                },
                "competitions": {
                    "numerator": comps_ok,
                    "denominator": MIN_COMPETITIONS_WITH_SUFFICIENT_SAMPLE,
                    "label_it": "Competition sufficienti",
                },
                "timestamp_verified": {
                    "numerator": pre_ok,
                    "denominator": len(prosp_all),
                    "label_it": "Timestamp verificati",
                },
                "book_verified": {
                    "numerator": book_ok,
                    "denominator": len(prosp_all),
                    "label_it": "Book verificati",
                },
            },
            "prospective_pending": len(pending),
            "first_prospective_snapshot_at": first_snap,
            "first_prospective_settled_at": first_settled,
            "prospective_calendar_days": days,
            "earliest_theoretical_review_at": earliest,
            "earliest_theoretical_review_label_it": earliest_label,
            "timeline": [
                {
                    "key": "collection_started",
                    "label_it": "Raccolta prospettica avviata",
                    "done": len(prosp_all) > 0,
                },
                {
                    "key": "first_settled",
                    "label_it": "Primo risultato settled",
                    "done": len(settled) > 0,
                },
                {
                    "key": "first_fold",
                    "label_it": "Primo fold completato",
                    "done": len(folds_ok) >= 1,
                },
                {
                    "key": "three_folds",
                    "label_it": "Tre fold completati",
                    "done": len(folds_ok) >= 3,
                },
                {
                    "key": "min_sample",
                    "label_it": "Campione minimo raggiunto",
                    "done": len(settled) >= MIN_PROSPECTIVE_SETTLED_GLOBAL,
                },
                {
                    "key": "stability",
                    "label_it": "Analisi di stabilità",
                    "done": False,
                },
                {
                    "key": "manual_review",
                    "label_it": "Revisione manuale",
                    "done": False,
                },
            ],
        }
    )


def build_balance_prospective_collection_health(
    db: Session,
    *,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    f = filters or {}
    f2 = {k: f.get(k) for k in ("date_from", "date_to", "competition_id")}
    prosp = _count(_base_q(db, source_cohort=COHORT_PROSPECTIVE, **f2))
    hist = _count(_base_q(db, source_cohort=COHORT_HISTORICAL_DIAGNOSTIC, **f2))
    if prosp == 0:
        status = "not_started"
        reasons = ["no_prospective_persisted_rows"]
        if hist > 0:
            reasons.append("only_historical_diagnostic_present")
    else:
        pending = _count(
            _base_q(db, source_cohort=COHORT_PROSPECTIVE, **f2).filter(
                CecchinoBalanceV5Evaluation.evaluation_status == EVAL_PENDING
            )
        )
        settled = _count(_prospective_settled_q(db, **f2))
        if settled == 0 and pending > 0:
            status = "collecting"
            reasons = ["prospective_pending_awaiting_settlement"]
        elif settled > 0:
            status = "healthy"
            reasons = []
        else:
            status = "degraded"
            reasons = ["prospective_rows_without_clear_status"]
    return make_json_safe(
        {
            "key": "balance_prospective_collection_health",
            "status": status,
            "prospective_rows": prosp,
            "historical_diagnostic_rows": hist,
            "reason_codes": reasons,
        }
    )


def build_balance_readiness_decision(
    db: Session,
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    tech = build_balance_technical_gates(db, filters=filters)
    sci = build_balance_scientific_gates(db, filters=filters)
    progress = build_balance_prospective_progress(db, filters=filters)
    prosp_settled = int(sci.get("prospective_settled") or progress.get("prospective_settled") or 0)
    prosp_pending = int(progress.get("prospective_pending") or 0)
    prosp_rows = prosp_settled + prosp_pending

    sci_gates = sci.get("gates") or []
    all_sci_pass = all(g.get("status") == "pass" for g in sci_gates) and prosp_settled > 0
    tech_blocking_fail = any(
        g.get("status") == "fail" and g.get("promotion_blocking")
        for g in (tech.get("gates") or [])
    )

    if all_sci_pass and not tech_blocking_fail:
        decision = "ready_for_manual_review"
        manual = "eligible"
        maturity = "ready_for_manual_review"
    elif prosp_rows == 0:
        decision = "continue_monitoring"
        manual = "not_eligible"
        maturity = "prospective_not_started"
    elif prosp_settled == 0:
        decision = "continue_monitoring"
        manual = "not_eligible"
        maturity = "prospective_collecting"
    else:
        decision = "continue_monitoring"
        manual = "not_eligible"
        maturity = "insufficient_prospective_sample"

    return make_json_safe(
        {
            "current_decision": decision,
            "current_decision_label_it": {
                "continue_monitoring": "Continua monitoraggio",
                "ready_for_manual_review": "Pronto per revisione manuale",
                "freeze_as_descriptive": "Mantieni come descrittivo",
                "request_formula_review": "Richiedi revisione formula",
            }.get(decision, decision),
            "operational_status": "official_descriptive_monitored",
            "operational_status_label_it": "Ufficiale descrittivo monitorato",
            "scientific_maturity": maturity,
            "scientific_maturity_label_it": {
                "prospective_not_started": "Raccolta prospettica non iniziata",
                "prospective_collecting": "Raccolta prospettica in corso",
                "insufficient_prospective_sample": "Campione prospettico insufficiente",
                "ready_for_manual_review": "Pronto per revisione manuale",
            }.get(maturity, maturity),
            "manual_review_status": manual,
            "manual_review_status_label_it": {
                "not_eligible": "Non idoneo",
                "eligible": "Idoneo",
            }.get(manual, manual),
            "signals_integration_status": "blocked",
            "signals_integration_status_label_it": "Bloccata",
            "earliest_theoretical_review_at": progress.get("earliest_theoretical_review_at"),
            "banner_it": (
                "Lo storico diagnostico consente analisi esplorative ma non promuove "
                "il modulo. La readiness usa esclusivamente snapshot prospettici "
                "verificati."
            ),
        }
    )


def build_balance_readiness_overview(
    db: Session,
    *,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    filters = _parse_filters(
        date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    cache_key = (
        BALANCE_READINESS_VERSION,
        BALANCE_READINESS_POLICY_VERSION,
        BALANCE_EMPIRICAL_ANALYSIS_VERSION,
        _max_updated_at(db),
        filters.get("date_from"),
        filters.get("date_to"),
        filters.get("competition_id"),
    )
    hit = _cache_get(cache_key)
    if hit is not None:
        hit["cache_hit"] = True
        return hit

    f_range = {k: filters.get(k) for k in ("date_from", "date_to", "competition_id")}
    hist_n = _count(
        _base_q(db, source_cohort=COHORT_HISTORICAL_DIAGNOSTIC, **f_range)
    )
    prosp_n = _count(_base_q(db, source_cohort=COHORT_PROSPECTIVE, **f_range))
    decision = build_balance_readiness_decision(db, filters=filters)
    progress = build_balance_prospective_progress(db, filters=filters)
    health = build_balance_prospective_collection_health(db, filters=filters)

    out = make_json_safe(
        {
            "status": "ok",
            "readiness_version": BALANCE_READINESS_VERSION,
            "policy_version": BALANCE_READINESS_POLICY_VERSION,
            "governance_version": BALANCE_GOVERNANCE_VERSION,
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            "policy": build_balance_readiness_policy_payload(),
            "filters": _serialize_filters(filters),
            "coverage": {
                "historical_diagnostic": hist_n,
                "prospective_persisted": prosp_n,
            },
            **decision,
            "progress_summary": progress.get("ratios"),
            "prospective_collection_health": health,
            "cache_hit": False,
            "generated_at": _utcnow().isoformat(),
        }
    )
    _cache_set(cache_key, out)
    return out


def build_balance_readiness_full_report(
    db: Session,
    *,
    filters: dict[str, Any] | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    if filters is None:
        filters = _parse_filters(
            date_from=date_from, date_to=date_to, competition_id=competition_id
        )
    overview = build_balance_readiness_overview(
        db,
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
        competition_id=filters.get("competition_id"),
    )
    return make_json_safe(
        {
            "overview": overview,
            "technical_gates": build_balance_technical_gates(db, filters=filters),
            "scientific_gates": build_balance_scientific_gates(db, filters=filters),
            "pillars": build_balance_pillar_readiness(db, filters=filters),
            "prospective_progress": build_balance_prospective_progress(db, filters=filters),
            "decision_contract": build_balance_decision_contract(),
            "current_decision": {
                "decision": overview.get("current_decision"),
                "signals_integration_status": overview.get("signals_integration_status"),
            },
            "prospective_collection_health": build_balance_prospective_collection_health(
                db, filters=filters
            ),
            "policy": build_balance_readiness_policy_payload(),
        }
    )


def compute_readiness_hash(payload: dict[str, Any]) -> str:
    cleaned = {
        k: v
        for k, v in payload.items()
        if k not in {"created_at", "updated_at", "id", "generated_at"}
    }
    raw = json.dumps(make_json_safe(cleaned), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def upsert_balance_readiness_daily_snapshot(
    db: Session,
    *,
    snapshot_date: date | None = None,
    competition_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Idempotente: max una riga giornaliera per policy/competition."""
    from app.models.cecchino_balance_v5_readiness_snapshot import (
        CecchinoBalanceV5ReadinessSnapshot,
    )

    snap_d = snapshot_date or _utcnow().date()
    filters = _parse_filters(
        date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    report = build_balance_readiness_full_report(db, filters=filters)
    overview = report.get("overview") or {}
    progress = report.get("prospective_progress") or {}
    ratios = progress.get("ratios") or {}
    pillars = report.get("pillars") or {}
    tech = report.get("technical_gates") or {}
    sci = report.get("scientific_gates") or {}

    body = {
        "snapshot_date": snap_d.isoformat(),
        "readiness_version": BALANCE_READINESS_VERSION,
        "policy_version": BALANCE_READINESS_POLICY_VERSION,
        "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
        "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
        "date_from": (filters.get("date_from").isoformat() if filters.get("date_from") else None),
        "date_to": (filters.get("date_to").isoformat() if filters.get("date_to") else None),
        "competition_id": competition_id,
        "prospective_settled": (ratios.get("prospective_settled") or {}).get("numerator", 0),
        "prospective_pending": progress.get("prospective_pending", 0),
        "prospective_days": (ratios.get("prospective_days") or {}).get("numerator", 0),
        "temporal_folds": (ratios.get("temporal_folds") or {}).get("numerator", 0),
        "operational_status": overview.get("operational_status"),
        "scientific_maturity": overview.get("scientific_maturity"),
        "manual_review_status": overview.get("manual_review_status"),
        "signals_integration_status": overview.get("signals_integration_status"),
        "current_decision": overview.get("current_decision"),
        "pillar_statuses_json": json.dumps(
            make_json_safe(pillars.get("pillars") or {}), ensure_ascii=False
        ),
        "technical_gates_json": json.dumps(make_json_safe(tech), ensure_ascii=False),
        "scientific_gates_json": json.dumps(make_json_safe(sci), ensure_ascii=False),
        "progress_json": json.dumps(make_json_safe(progress), ensure_ascii=False),
    }
    rh = compute_readiness_hash(body)
    now = _utcnow()

    existing = (
        db.query(CecchinoBalanceV5ReadinessSnapshot)
        .filter(
            CecchinoBalanceV5ReadinessSnapshot.snapshot_date == snap_d,
            CecchinoBalanceV5ReadinessSnapshot.policy_version
            == BALANCE_READINESS_POLICY_VERSION,
            CecchinoBalanceV5ReadinessSnapshot.competition_id == competition_id,
        )
        .one_or_none()
    )
    if existing is None:
        row = CecchinoBalanceV5ReadinessSnapshot(
            snapshot_date=snap_d,
            readiness_version=BALANCE_READINESS_VERSION,
            policy_version=BALANCE_READINESS_POLICY_VERSION,
            dataset_version=BALANCE_EMPIRICAL_DATASET_VERSION,
            analysis_version=BALANCE_EMPIRICAL_ANALYSIS_VERSION,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
            competition_id=competition_id,
            prospective_settled=int(body["prospective_settled"] or 0),
            prospective_pending=int(body["prospective_pending"] or 0),
            prospective_days=int(body["prospective_days"] or 0),
            temporal_folds=int(body["temporal_folds"] or 0),
            operational_status=str(body["operational_status"]),
            scientific_maturity=str(body["scientific_maturity"]),
            manual_review_status=str(body["manual_review_status"]),
            signals_integration_status=str(body["signals_integration_status"]),
            current_decision=str(body["current_decision"]),
            pillar_statuses_json=body["pillar_statuses_json"],
            technical_gates_json=body["technical_gates_json"],
            scientific_gates_json=body["scientific_gates_json"],
            progress_json=body["progress_json"],
            readiness_hash=rh,
            generated_at=now,
        )
        db.add(row)
        action = "created"
    else:
        existing.readiness_version = BALANCE_READINESS_VERSION
        existing.dataset_version = BALANCE_EMPIRICAL_DATASET_VERSION
        existing.analysis_version = BALANCE_EMPIRICAL_ANALYSIS_VERSION
        existing.date_from = filters.get("date_from")
        existing.date_to = filters.get("date_to")
        existing.prospective_settled = int(body["prospective_settled"] or 0)
        existing.prospective_pending = int(body["prospective_pending"] or 0)
        existing.prospective_days = int(body["prospective_days"] or 0)
        existing.temporal_folds = int(body["temporal_folds"] or 0)
        existing.operational_status = str(body["operational_status"])
        existing.scientific_maturity = str(body["scientific_maturity"])
        existing.manual_review_status = str(body["manual_review_status"])
        existing.signals_integration_status = str(body["signals_integration_status"])
        existing.current_decision = str(body["current_decision"])
        existing.pillar_statuses_json = body["pillar_statuses_json"]
        existing.technical_gates_json = body["technical_gates_json"]
        existing.scientific_gates_json = body["scientific_gates_json"]
        existing.progress_json = body["progress_json"]
        existing.readiness_hash = rh
        existing.generated_at = now
        action = "updated"

    clear_balance_readiness_cache()
    if commit:
        db.commit()
    else:
        db.flush()
    return {"status": "ok", "action": action, "readiness_hash": rh, "snapshot_date": snap_d.isoformat()}


BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING = (
    "balance_readiness_snapshot_failed_non_blocking"
)


def safe_upsert_balance_readiness_daily_snapshot(
    *,
    phase: str,
    scan_date: date | str | None = None,
    job_id: str | None = None,
    snapshot_date: date | None = None,
    competition_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Esegue l'upsert Readiness in sessione dedicata fail-soft.

    Non riusa la sessione del chiamante: un IntegrityError/rollback resta
    isolato e non avvelena la scansione / recompute / update-results.
    """
    from app.core.database import SessionLocal

    scan_date_s: str | None
    if scan_date is None:
        scan_date_s = None
    elif isinstance(scan_date, date):
        scan_date_s = scan_date.isoformat()
    else:
        scan_date_s = str(scan_date)

    snap_db = SessionLocal()
    rolled_back = False
    try:
        result = upsert_balance_readiness_daily_snapshot(
            snap_db,
            snapshot_date=snapshot_date,
            competition_id=competition_id,
            date_from=date_from,
            date_to=date_to,
            commit=True,
        )
        logger.info(
            "balance_readiness_snapshot_saved_after_scan phase=%s scan_date=%s "
            "job_id=%s action=%s readiness_hash=%s",
            phase,
            scan_date_s,
            job_id,
            result.get("action"),
            result.get("readiness_hash"),
        )
        return result
    except Exception as exc:
        try:
            snap_db.rollback()
            rolled_back = True
        except Exception:
            logger.exception(
                "balance_readiness_snapshot accessory rollback failed phase=%s",
                phase,
            )
        logger.exception(
            "balance_readiness_snapshot_skipped_after_scan phase=%s scan_date=%s "
            "job_id=%s exc_type=%s main_scan_preserved=%s "
            "accessory_session_rolled_back=%s",
            phase,
            scan_date_s,
            job_id,
            type(exc).__name__,
            True,
            rolled_back,
        )
        return {
            "status": "skipped",
            "warning_code": BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING,
            "phase": phase,
            "exc_type": type(exc).__name__,
        }
    finally:
        snap_db.close()


def record_balance_governance_decision(
    db: Session,
    *,
    decision: str,
    decision_reason: str | None = None,
    confirm_token: str | None = None,
    requested_by: str | None = None,
    confirmed_by: str | None = None,
    evidence_snapshot_hash: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    from app.models.cecchino_balance_v5_governance_decision import (
        CecchinoBalanceV5GovernanceDecision,
    )
    from app.services.cecchino.cecchino_balance_v5_readiness_policy import (
        BALANCE_GOVERNANCE_CONFIRM_TOKEN,
    )

    if decision in BLOCKED_SIGNAL_DECISIONS or decision == "eligible_for_manual_signal_integration_review":
        return {
            "status": "rejected",
            "http_status": 422,
            "error": "signal_integration_requires_separate_explicit_implementation",
        }
    if decision not in ALLOWED_GOVERNANCE_DECISIONS_STEP_2C:
        return {
            "status": "rejected",
            "http_status": 422,
            "error": "decision_not_allowed",
        }
    if confirm_token != BALANCE_GOVERNANCE_CONFIRM_TOKEN:
        return {
            "status": "rejected",
            "http_status": 400,
            "error": "invalid_confirm_token",
        }

    row = CecchinoBalanceV5GovernanceDecision(
        governance_version=BALANCE_GOVERNANCE_VERSION,
        readiness_version=BALANCE_READINESS_VERSION,
        policy_version=BALANCE_READINESS_POLICY_VERSION,
        decision=decision,
        decision_status="recorded",
        decision_reason=decision_reason,
        evidence_snapshot_hash=evidence_snapshot_hash,
        requested_by=requested_by,
        confirmed_by=confirmed_by,
        created_at=_utcnow(),
    )
    db.add(row)
    clear_balance_readiness_cache()
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return make_json_safe(
        {
            "status": "ok",
            "id": row.id,
            "decision": decision,
            "decision_status": "recorded",
            "governance_version": BALANCE_GOVERNANCE_VERSION,
        }
    )


def list_balance_readiness_history(
    db: Session,
    *,
    competition_id: int | None = None,
    limit: int = 90,
) -> dict[str, Any]:
    from app.models.cecchino_balance_v5_readiness_snapshot import (
        CecchinoBalanceV5ReadinessSnapshot,
    )

    q = db.query(CecchinoBalanceV5ReadinessSnapshot).filter(
        CecchinoBalanceV5ReadinessSnapshot.policy_version
        == BALANCE_READINESS_POLICY_VERSION
    )
    if competition_id is not None:
        q = q.filter(CecchinoBalanceV5ReadinessSnapshot.competition_id == competition_id)
    rows = (
        q.order_by(CecchinoBalanceV5ReadinessSnapshot.snapshot_date.desc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "snapshot_date": (
                r.snapshot_date.isoformat() if r.snapshot_date is not None else None
            ),
            "prospective_settled": r.prospective_settled,
            "prospective_days": r.prospective_days,
            "temporal_folds": r.temporal_folds,
            "scientific_maturity": r.scientific_maturity,
            "current_decision": r.current_decision,
            "readiness_hash": r.readiness_hash,
        }
        for r in rows
    ]
    return make_json_safe({"items": items, "count": len(items)})


BALANCE_READINESS_HISTORY_CSV_FIELDS = [
    "snapshot_date",
    "prospective_settled",
    "prospective_days",
    "temporal_folds",
    "scientific_maturity",
    "current_decision",
    "readiness_hash",
]

BALANCE_GOVERNANCE_CSV_FIELDS = [
    "id",
    "created_at",
    "decision",
    "decision_status",
    "decision_reason",
    "governance_version",
    "policy_version",
    "requested_by",
    "confirmed_by",
    "evidence_snapshot_hash",
]

BALANCE_READINESS_GATES_CSV_FIELDS = [
    "category",
    "key",
    "label_it",
    "status",
    "value",
    "threshold",
    "numerator",
    "denominator",
    "promotion_blocking",
    "evidence_scope",
    "reason_codes",
]


def list_balance_governance_decisions(
    db: Session,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    from app.models.cecchino_balance_v5_governance_decision import (
        CecchinoBalanceV5GovernanceDecision,
    )

    try:
        rows_orm = (
            db.query(CecchinoBalanceV5GovernanceDecision)
            .order_by(CecchinoBalanceV5GovernanceDecision.created_at.desc())
            .limit(limit)
            .all()
        )
    except Exception:
        rows_orm = []
    items = [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "decision": r.decision,
            "decision_status": r.decision_status,
            "decision_reason": r.decision_reason,
            "governance_version": r.governance_version,
            "policy_version": r.policy_version,
            "requested_by": r.requested_by,
            "confirmed_by": r.confirmed_by,
            "evidence_snapshot_hash": r.evidence_snapshot_hash,
        }
        for r in rows_orm
    ]
    return make_json_safe({"items": items, "count": len(items)})


def build_balance_readiness_gate_csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    gate_rows: list[dict[str, Any]] = []
    for category, block in (
        ("technical", report.get("technical_gates") or {}),
        ("scientific", report.get("scientific_gates") or {}),
    ):
        for g in block.get("gates") or []:
            if not isinstance(g, dict):
                continue
            gate_rows.append(
                {
                    "category": g.get("category") or category,
                    "key": g.get("key"),
                    "label_it": g.get("label_it"),
                    "status": g.get("status"),
                    "value": g.get("value"),
                    "threshold": g.get("threshold"),
                    "numerator": g.get("numerator"),
                    "denominator": g.get("denominator"),
                    "promotion_blocking": g.get("promotion_blocking"),
                    "evidence_scope": g.get("evidence_scope"),
                    "reason_codes": "|".join(
                        str(c) for c in (g.get("reason_codes") or [])
                    ),
                }
            )
    return gate_rows


def build_balance_readiness_pack_payload(
    db: Session,
    *,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Payload canonico condiviso dossier + forensic pack."""
    filters = _parse_filters(
        date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    return make_json_safe(
        {
            "filters": _serialize_filters(filters),
            "report": build_balance_readiness_full_report(db, filters=filters),
            "history": list_balance_readiness_history(
                db, competition_id=competition_id
            ),
            "governance": list_balance_governance_decisions(db, limit=200),
        }
    )


def build_balance_readiness_forensic_file_payload(
    pack: dict[str, Any],
) -> dict[str, Any]:
    """Mappa file forensic readiness (contenuto pre-serializzazione)."""
    report = pack.get("report") or {}
    overview = report.get("overview") or {}
    history_items = list((pack.get("history") or {}).get("items") or [])
    governance_items = list((pack.get("governance") or {}).get("items") or [])
    return {
        "balance_readiness_overview.json": overview,
        "balance_readiness_policy.json": report.get("policy")
        or build_balance_readiness_policy_payload(),
        "balance_readiness_gates.csv": build_balance_readiness_gate_csv_rows(report),
        "balance_pillar_readiness.json": report.get("pillars") or {},
        "balance_prospective_progress.json": report.get("prospective_progress") or {},
        "balance_readiness_history.csv": history_items,
        "balance_current_decision.json": report.get("current_decision")
        or {
            "decision": overview.get("current_decision"),
            "signals_integration_status": overview.get("signals_integration_status"),
        },
        "balance_decision_contract.json": report.get("decision_contract")
        or build_balance_decision_contract(),
        "balance_prospective_collection_health.json": report.get(
            "prospective_collection_health"
        )
        or {},
        "balance_governance_decisions.csv": governance_items,
        "metadata.json": {
            "readiness_version": BALANCE_READINESS_VERSION,
            "policy_version": BALANCE_READINESS_POLICY_VERSION,
            "filters": pack.get("filters") or {},
        },
    }


def build_balance_empirical_reconciliation(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Riconcilia righe monitoring Balance vs dataset empirico corrente."""
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        query_balance_empirical_rows,
    )
    from app.services.cecchino.cecchino_balance_v5_monitoring import (
        build_balance_monitoring_rows,
    )
    from app.services.cecchino.cecchino_monitoring_cohorts import COHORT_HISTORICAL_DIAGNOSTIC

    filters = _parse_filters(
        date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    df = filters.get("date_from")
    dt = filters.get("date_to")
    comp = filters.get("competition_id")
    if df is None or dt is None:
        return {
            "status": "unavailable",
            "reconciliation_status": "unavailable",
            "explanation": "date_from/date_to richiesti per riconciliazione export",
        }

    mon_rows = build_balance_monitoring_rows(
        db, date_from=df, date_to=dt, competition_id=comp
    )
    mon_ids = {
        int(r["today_fixture_id"])
        for r in mon_rows
        if r.get("today_fixture_id") is not None
    }
    emp_items: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = query_balance_empirical_rows(
            db,
            date_from=df,
            date_to=dt,
            competition_id=comp,
            limit=5000,
            offset=offset,
        )
        batch = list(page.get("items") or [])
        emp_items.extend(row for row in batch if isinstance(row, dict))
        total = int(page.get("total") or 0)
        offset += len(batch)
        if not batch or offset >= total:
            break
    emp_ids = {
        int(r["today_fixture_id"])
        for r in emp_items
        if r.get("today_fixture_id") is not None
    }
    only_mon = sorted(mon_ids - emp_ids)
    only_emp = sorted(emp_ids - mon_ids)
    intersection = sorted(mon_ids & emp_ids)

    counts_by_cohort: dict[str, int] = defaultdict(int)
    for r in mon_rows:
        counts_by_cohort[str(r.get("source_cohort") or "unknown")] += 1
    emp_by_cohort: dict[str, int] = defaultdict(int)
    for r in emp_items:
        emp_by_cohort[str(r.get("source_cohort") or "unknown")] += 1

    only_emp_rows = [r for r in emp_items if int(r.get("today_fixture_id") or 0) in only_emp]
    only_emp_hist_diag = sum(
        1 for r in only_emp_rows if r.get("source_cohort") == COHORT_HISTORICAL_DIAGNOSTIC
    )
    explanation_parts: list[str] = []
    if only_emp_hist_diag and len(only_emp) == only_emp_hist_diag:
        explanation_parts.append(
            "Le righe solo empiriche appartengono alla coorte historical_diagnostic "
            "non inclusa nel monitoring Balance corrente."
        )
    elif only_emp:
        explanation_parts.append(
            "Differenza tra righe monitoring e record empirici correnti (is_current)."
        )
    if only_mon:
        explanation_parts.append(
            "Alcune righe monitoring non hanno record empirico corrente corrispondente."
        )
    if not only_mon and not only_emp:
        explanation_parts.append("Monitoring ed empirico allineati sulle fixture_id.")
    reconciliation_status = "explained" if explanation_parts and not only_mon else (
        "mismatch" if (only_mon or only_emp) and not explanation_parts else "explained"
    )
    if only_emp_hist_diag and len(only_emp) == only_emp_hist_diag:
        reconciliation_status = "explained"

    return make_json_safe(
        {
            "status": "ok",
            "balance_monitoring_rows": len(mon_rows),
            "empirical_current_rows": len(emp_items),
            "intersection_rows": len(intersection),
            "only_monitoring_count": len(only_mon),
            "only_empirical_count": len(only_emp),
            "only_monitoring_ids": only_mon[:500],
            "only_empirical_ids": only_emp[:500],
            "counts_by_source_cohort_monitoring": dict(counts_by_cohort),
            "counts_by_source_cohort_empirical": dict(emp_by_cohort),
            "counts_by_reason": {
                "only_empirical_historical_diagnostic": only_emp_hist_diag,
            },
            "explanation": " ".join(explanation_parts) or "Nessuna differenza rilevata.",
            "reconciliation_status": reconciliation_status,
        }
    )


def build_balance_readiness_dossier_files(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, bytes]:
    """File per ZIP dossier readiness dedicato."""
    from fastapi.encoders import jsonable_encoder

    pack = build_balance_readiness_pack_payload(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    report = pack.get("report") or {}
    history = pack.get("history") or {}
    filters = pack.get("filters") or {}

    def _jb(obj: Any) -> bytes:
        encoded = jsonable_encoder(make_json_safe(obj))
        return (
            json.dumps(encoded, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8")

    readme = (
        "# Balance v5 Readiness Dossier\n\n"
        "Solo readiness/governance. Non sostituisce lo ZIP forensic completo.\n"
        f"Readiness: {BALANCE_READINESS_VERSION}\n"
        f"Policy: {BALANCE_READINESS_POLICY_VERSION}\n"
    ).encode("utf-8")

    return {
        "README.md": readme,
        "balance_readiness_overview.json": _jb(report.get("overview")),
        "balance_readiness_policy.json": _jb(report.get("policy")),
        "balance_readiness_gates.json": _jb(
            {
                "technical": report.get("technical_gates"),
                "scientific": report.get("scientific_gates"),
            }
        ),
        "balance_pillar_readiness.json": _jb(report.get("pillars")),
        "balance_prospective_progress.json": _jb(report.get("prospective_progress")),
        "balance_readiness_history.json": _jb(history),
        "balance_current_decision.json": _jb(report.get("current_decision")),
        "balance_decision_contract.json": _jb(report.get("decision_contract")),
        "balance_prospective_collection_health.json": _jb(
            report.get("prospective_collection_health")
        ),
        "metadata.json": _jb(
            {
                "readiness_version": BALANCE_READINESS_VERSION,
                "policy_version": BALANCE_READINESS_POLICY_VERSION,
                "filters": filters,
            }
        ),
    }
