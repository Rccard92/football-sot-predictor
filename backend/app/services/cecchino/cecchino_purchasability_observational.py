"""Contesto osservazionale Acquistabilità — sample/ROI read-only per KPI panel.

Non modifica formule candidate né snapshot persistiti. Aggrega evaluation settled
per market_key + score_band (stesso schema validation Fase 5).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_purchasability_evaluation import (
    EVAL_LOST,
    EVAL_WON,
    CecchinoPurchasabilityEvaluation,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_validation import score_band_for
from app.services.cecchino.cecchino_purchasability_validation_aggregation import (
    _metrics_block,
)

# Allineato a Affidabilità storica (MIN_SAMPLE = 30).
OBS_MIN_SAMPLE = 30

STATUS_AVAILABLE = "available"
STATUS_INSUFFICIENT = "insufficient_data"
STATUS_NOT_EVALUATED = "not_evaluated"


def _item_market_key(item: dict[str, Any]) -> str | None:
    raw = item.get("market_key") or item.get("selection")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().upper()


def _item_score(item: dict[str, Any]) -> int | None:
    score = item.get("score")
    if isinstance(score, bool) or score is None:
        return None
    try:
        return int(score)
    except (TypeError, ValueError):
        return None


def _not_evaluated(
    *,
    market_key: str,
    candidate_version: str,
    score_band: str | None = None,
) -> dict[str, Any]:
    return {
        "status": STATUS_NOT_EVALUATED,
        "sample_size": 0,
        "roi_pct": None,
        "score_band": score_band,
        "candidate_version": candidate_version,
        "market_key": market_key,
    }


def _load_settled_by_band(
    db: Session,
    *,
    candidate_version: str,
) -> dict[tuple[str, str], list[CecchinoPurchasabilityEvaluation]]:
    """Carica evaluation settled correnti e le raggruppa per (market_key, score_band)."""
    stmt = select(CecchinoPurchasabilityEvaluation).where(
        CecchinoPurchasabilityEvaluation.is_current.is_(True),
        CecchinoPurchasabilityEvaluation.candidate_version == candidate_version,
        CecchinoPurchasabilityEvaluation.evaluation_status.in_((EVAL_WON, EVAL_LOST)),
    )
    rows = list(db.scalars(stmt).all())
    grouped: dict[tuple[str, str], list[CecchinoPurchasabilityEvaluation]] = {}
    for row in rows:
        mk = str(row.market_key or "").strip().upper()
        if not mk:
            continue
        band = score_band_for(
            int(row.purchasability_score)
            if row.purchasability_score is not None
            else None
        )
        if not band:
            continue
        grouped.setdefault((mk, band), []).append(row)
    return grouped


def build_purchasability_observational_by_market(
    db: Session,
    *,
    items: list[dict[str, Any]] | None,
    candidate_version: str,
    min_sample: int = OBS_MIN_SAMPLE,
) -> dict[str, dict[str, Any]]:
    """Map market_key → contesto osservazionale sample/ROI.

    Status:
    - available: settled >= min_sample
    - insufficient_data: 0 < settled < min_sample
    - not_evaluated: nessun settled / score assente
    """
    out: dict[str, dict[str, Any]] = {}
    if not candidate_version or not isinstance(items, list) or not items:
        return out

    try:
        grouped = _load_settled_by_band(db, candidate_version=candidate_version)
    except Exception:
        return out

    for item in items:
        if not isinstance(item, dict):
            continue
        mk = _item_market_key(item)
        if not mk:
            continue
        score = _item_score(item)
        if score is None:
            out[mk] = _not_evaluated(
                market_key=mk, candidate_version=candidate_version
            )
            continue
        band = score_band_for(score)
        if not band:
            out[mk] = _not_evaluated(
                market_key=mk, candidate_version=candidate_version
            )
            continue

        cohort = grouped.get((mk, band), [])
        metrics = _metrics_block(cohort)
        settled = int(metrics.get("settled") or 0)
        roi = metrics.get("roi_pct")
        if settled <= 0:
            out[mk] = _not_evaluated(
                market_key=mk,
                candidate_version=candidate_version,
                score_band=band,
            )
            continue
        if settled < min_sample:
            out[mk] = {
                "status": STATUS_INSUFFICIENT,
                "sample_size": settled,
                "roi_pct": roi,
                "score_band": band,
                "candidate_version": candidate_version,
                "market_key": mk,
            }
            continue
        out[mk] = {
            "status": STATUS_AVAILABLE,
            "sample_size": settled,
            "roi_pct": roi,
            "score_band": band,
            "candidate_version": candidate_version,
            "market_key": mk,
        }

    return make_json_safe(out)


def build_observational_maps_for_previews(
    db: Session,
    *,
    purch_v1: dict[str, Any] | None,
    purch_v2: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Costruisce le due mappe sibling per il detail Today."""
    from app.schemas.cecchino_purchasability_preview import (
        PURCHASABILITY_CANDIDATE_VERSION,
    )
    from app.schemas.cecchino_purchasability_v2 import (
        PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
    )

    items_v1: list[dict[str, Any]] = []
    cv1 = PURCHASABILITY_CANDIDATE_VERSION
    if isinstance(purch_v1, dict):
        cv1 = str(purch_v1.get("candidate_version") or cv1)
        raw = purch_v1.get("items")
        if isinstance(raw, list):
            items_v1 = [x for x in raw if isinstance(x, dict)]

    items_v2: list[dict[str, Any]] = []
    cv2 = PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION
    if isinstance(purch_v2, dict):
        cv2 = str(purch_v2.get("candidate_version") or cv2)
        raw2 = purch_v2.get("items")
        if isinstance(raw2, list):
            items_v2 = [x for x in raw2 if isinstance(x, dict)]

    try:
        map_v1 = build_purchasability_observational_by_market(
            db, items=items_v1, candidate_version=cv1
        )
    except Exception:
        map_v1 = {}
    try:
        map_v2 = build_purchasability_observational_by_market(
            db, items=items_v2, candidate_version=cv2
        )
    except Exception:
        map_v2 = {}
    return map_v1, map_v2
