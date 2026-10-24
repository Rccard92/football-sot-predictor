"""BET-RESULTS-01 — Evidence Sort primary selection (parità frontend).

v3 dal 25/10/2026: origine → segnali, senza acquistabilita'. Le giornate prima del 25/10 restano con la v2
(origine → V3.1 → segnali), cosi' i risultati passati mostrano la giocata che era stata davvero proposta.

Comparator dedicato: NON modifica lo sort globale pre-match dell'aggregator.
"""

from __future__ import annotations

from datetime import date
from functools import cmp_to_key
from typing import Any

from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_EVIDENCE_SORT_V3_FROM,
    BET_BUILDER_PRIMARY_SELECTION_VERSION,
    BET_BUILDER_PRIMARY_SELECTION_VERSION_V2,
    ORIGIN_PRICE,
    ORIGIN_PRICE_AND_SIGNALS,
    ORIGIN_SIGNALS,
)

ORIGIN_RANK: dict[str, int] = {
    ORIGIN_PRICE_AND_SIGNALS: 0,
    ORIGIN_SIGNALS: 1,
    ORIGIN_PRICE: 2,
}


def _cmp_nullable_number_desc(a: Any, b: Any) -> int:
    a_null = a is None
    b_null = b is None
    if not a_null:
        try:
            a = float(a)
            if a != a:  # NaN
                a_null = True
        except (TypeError, ValueError):
            a_null = True
    if not b_null:
        try:
            b = float(b)
            if b != b:
                b_null = True
        except (TypeError, ValueError):
            b_null = True
    if a_null and b_null:
        return 0
    if a_null:
        return 1
    if b_null:
        return -1
    if b > a:
        return 1
    if b < a:
        return -1
    return 0


def compare_opportunity_evidence_strength(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    use_v31: bool = False,
) -> int:
    """Comparator lessicografico Evidence Sort — allineato a betBuilderUtils.ts.

    v3 (default): origin → signals.passed → yes_count → context.available → rating → edge → opportunity_key.
    v2 (`use_v31`, giornate prima del 25/10/2026): V3.1 subito dopo l'origine.
    Nessuno score aggregato.
    """
    origin_a = ORIGIN_RANK.get(str(a.get("origin") or ""), 99)
    origin_b = ORIGIN_RANK.get(str(b.get("origin") or ""), 99)
    by_origin = origin_a - origin_b
    if by_origin != 0:
        return by_origin

    if use_v31:
        purch_a = a.get("purchasability_v31") or {}
        purch_b = b.get("purchasability_v31") or {}
        by_v31 = _cmp_nullable_number_desc(purch_a.get("score"), purch_b.get("score"))
        if by_v31 != 0:
            return by_v31

    signals_a = a.get("signals") or {}
    signals_b = b.get("signals") or {}
    a_passed = signals_a.get("passed") is True
    b_passed = signals_b.get("passed") is True
    if a_passed != b_passed:
        return -1 if a_passed else 1

    by_yes = _cmp_nullable_number_desc(
        signals_a.get("yes_count"),
        signals_b.get("yes_count"),
    )
    if by_yes != 0:
        return by_yes

    ctx_a = (a.get("context_support") or {}).get("available") is True
    ctx_b = (b.get("context_support") or {}).get("available") is True
    if ctx_a != ctx_b:
        return -1 if ctx_a else 1

    price_a = a.get("price_value") or {}
    price_b = b.get("price_value") or {}
    by_rating = _cmp_nullable_number_desc(price_a.get("rating"), price_b.get("rating"))
    if by_rating != 0:
        return by_rating

    by_edge = _cmp_nullable_number_desc(price_a.get("edge_pct"), price_b.get("edge_pct"))
    if by_edge != 0:
        return by_edge

    key_a = str(a.get("opportunity_key") or "")
    key_b = str(b.get("opportunity_key") or "")
    if key_a < key_b:
        return -1
    if key_a > key_b:
        return 1
    return 0


def uses_v31(scan_date: date | None) -> bool:
    """Giornate prima del 25/10/2026: ordinamento v2 con la V3.1 (quello mostrato allora)."""
    return scan_date is not None and scan_date < BET_BUILDER_EVIDENCE_SORT_V3_FROM


def sort_opportunities_by_evidence_strength(
    opportunities: list[dict[str, Any]],
    scan_date: date | None = None,
) -> list[dict[str, Any]]:
    v31 = uses_v31(scan_date)
    copy = list(opportunities)
    copy.sort(key=cmp_to_key(lambda a, b: compare_opportunity_evidence_strength(a, b, use_v31=v31)))
    return copy


def select_primary_opportunity(
    opportunities: list[dict[str, Any]],
    scan_date: date | None = None,
) -> dict[str, Any] | None:
    """Predizione madre = prima dopo l'Evidence Sort della giornata."""
    if not opportunities:
        return None
    sorted_ops = sort_opportunities_by_evidence_strength(opportunities, scan_date)
    return sorted_ops[0]


def primary_selection_version(scan_date: date | None = None) -> str:
    return BET_BUILDER_PRIMARY_SELECTION_VERSION_V2 if uses_v31(scan_date) else BET_BUILDER_PRIMARY_SELECTION_VERSION
