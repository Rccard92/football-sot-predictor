"""Riconciliazione cardinalità Purchasability Evaluation — monitoraggio moduli.

Conteggi per dimensione e verifica gap tra settled+pending vs totali righe.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_purchasability_evaluation import (
    CecchinoPurchasabilityEvaluation,
    EVAL_LOST,
    EVAL_PENDING,
    EVAL_WON,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe


def build_purchasability_evaluation_cardinality_report(
    db: Session,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """
    Genera report di cardinalità per CecchinoPurchasabilityEvaluation.
    
    Conteggi per:
    - source_cohort
    - candidate_version
    - evaluation_status
    - promotion_eligible
    - is_current
    - market_key
    
    Totali:
    - validation_rows_total
    - settled (won + lost)
    - pending
    - not_evaluable
    - result_missing
    - altri status
    
    Riconciliazione: confronto settled+pending vs totali e residui.
    
    NO scritture DB.
    """
    # Query base
    query = select(CecchinoPurchasabilityEvaluation).where(
        CecchinoPurchasabilityEvaluation.scan_date >= date_from,
        CecchinoPurchasabilityEvaluation.scan_date <= date_to,
    )
    
    if competition_id is not None:
        query = query.where(
            CecchinoPurchasabilityEvaluation.competition_id == int(competition_id)
        )
    
    rows = list(db.scalars(query).all())
    
    # Conteggi dimensionali
    by_cohort: Counter[str] = Counter()
    by_version: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_promotion: Counter[bool] = Counter()
    by_current: Counter[bool] = Counter()
    by_market: Counter[str] = Counter()
    
    # Combinazioni
    cohort_version: dict[tuple[str, str], int] = defaultdict(int)
    cohort_status: dict[tuple[str, str], int] = defaultdict(int)
    cohort_promotion: dict[tuple[str, bool], int] = defaultdict(int)
    
    for row in rows:
        cohort = str(row.source_cohort or "unknown")
        version = str(row.candidate_version or "unknown")
        status = str(row.evaluation_status or "unknown")
        promo = bool(row.promotion_eligible)
        current = bool(row.is_current)
        market = str(row.market_key or "unknown")
        
        by_cohort[cohort] += 1
        by_version[version] += 1
        by_status[status] += 1
        by_promotion[promo] += 1
        by_current[current] += 1
        by_market[market] += 1
        
        cohort_version[(cohort, version)] += 1
        cohort_status[(cohort, status)] += 1
        cohort_promotion[(cohort, promo)] += 1
    
    # Totali per categoria di status
    total_rows = len(rows)
    won_count = by_status.get(EVAL_WON, 0)
    lost_count = by_status.get(EVAL_LOST, 0)
    settled_count = won_count + lost_count
    pending_count = by_status.get(EVAL_PENDING, 0)
    not_evaluable_count = by_status.get("not_evaluable", 0)
    result_missing_count = by_status.get("result_missing", 0)
    
    # Altri status (residui)
    accounted_statuses = {EVAL_WON, EVAL_LOST, EVAL_PENDING, "not_evaluable", "result_missing"}
    other_statuses = {k: v for k, v in by_status.items() if k not in accounted_statuses}
    other_count = sum(other_statuses.values())
    
    # Riconciliazione: settled + pending vs totali
    settled_plus_pending = settled_count + pending_count
    reconciliation_gap = total_rows - settled_plus_pending
    
    # Nota di riconciliazione
    reconciliation_note = (
        f"Totale righe: {total_rows}. "
        f"Settled (won+lost): {settled_count}. "
        f"Pending: {pending_count}. "
        f"Settled + Pending: {settled_plus_pending}. "
        f"Gap (total - settled - pending): {reconciliation_gap}."
    )
    
    if reconciliation_gap > 0:
        residual_list = []
        if not_evaluable_count > 0:
            residual_list.append(f"not_evaluable={not_evaluable_count}")
        if result_missing_count > 0:
            residual_list.append(f"result_missing={result_missing_count}")
        if other_count > 0:
            residual_list.append(f"altri_status={other_count}")
        
        if residual_list:
            reconciliation_note += f" Residui: {', '.join(residual_list)}."
    
    # Costruzione payload
    payload = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "competition_id": competition_id,
        "validation_rows_total": total_rows,
        "totals": {
            "won": won_count,
            "lost": lost_count,
            "settled": settled_count,
            "pending": pending_count,
            "not_evaluable": not_evaluable_count,
            "result_missing": result_missing_count,
            "other_statuses": other_count,
        },
        "reconciliation": {
            "settled_plus_pending": settled_plus_pending,
            "gap": reconciliation_gap,
            "note": reconciliation_note,
            "other_status_details": dict(other_statuses) if other_statuses else {},
        },
        "by_dimension": {
            "source_cohort": dict(by_cohort),
            "candidate_version": dict(by_version),
            "evaluation_status": dict(by_status),
            "promotion_eligible": {str(k): v for k, v in by_promotion.items()},
            "is_current": {str(k): v for k, v in by_current.items()},
            "market_key_top_20": dict(by_market.most_common(20)),
        },
        "cross_dimensions": {
            "cohort_x_version": {
                f"{c}|{v}": cnt for (c, v), cnt in cohort_version.items()
            },
            "cohort_x_status": {
                f"{c}|{s}": cnt for (c, s), cnt in cohort_status.items()
            },
            "cohort_x_promotion": {
                f"{c}|{p}": cnt for (c, p), cnt in cohort_promotion.items()
            },
        },
        "notes": [
            "Report di cardinalità basato su CecchinoPurchasabilityEvaluation",
            "NO scritture DB",
            "Gap rappresenta righe con status diversi da won, lost, pending",
        ],
    }
    
    return make_json_safe(payload)
