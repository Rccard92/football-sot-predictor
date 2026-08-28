"""Proiezione Bet Builder storica da snapshot V4 — READ-ONLY, zero ricalcolo motori.

Evidence Sort V2 con score V3.6 al posto di V3.1 (policy storica Pattern Lab).
"""

from __future__ import annotations

from functools import cmp_to_key
from typing import Any

from app.services.cecchino.cecchino_bet_builder_constants import (
    ORIGIN_PRICE,
    ORIGIN_PRICE_AND_SIGNALS,
    ORIGIN_SIGNALS,
)
from app.services.cecchino.cecchino_bet_builder_markets import BET_BUILDER_MARKET_KEYS
from app.services.cecchino.cecchino_bet_builder_opportunity_aggregator import (
    build_price_value,
    build_signals_evidence,
)
from app.services.cecchino.cecchino_bet_builder_primary_selection import (
    _cmp_nullable_number_desc,
)
from app.services.cecchino_data_lab.historical_analytics_agg import as_dict
from app.services.cecchino_data_lab.pattern_lab_constants import PATTERN_LAB_SORT_POLICY_BB
from app.services.cecchino_data_lab.pattern_lab_projection import index_kpi_rows, index_purch_v36


ORIGIN_RANK: dict[str, int] = {
    ORIGIN_PRICE_AND_SIGNALS: 0,
    ORIGIN_SIGNALS: 1,
    ORIGIN_PRICE: 2,
}


def _origin(price_present: bool, signal_present: bool) -> str | None:
    if price_present and signal_present:
        return ORIGIN_PRICE_AND_SIGNALS
    if price_present:
        return ORIGIN_PRICE
    if signal_present:
        return ORIGIN_SIGNALS
    return None


def compare_opportunity_evidence_v36(a: dict[str, Any], b: dict[str, Any]) -> int:
    """Evidence Sort V2 storico: origin → V3.6 → signals → rating → edge → key."""
    origin_a = ORIGIN_RANK.get(str(a.get("origin") or ""), 99)
    origin_b = ORIGIN_RANK.get(str(b.get("origin") or ""), 99)
    by_origin = origin_a - origin_b
    if by_origin != 0:
        return by_origin

    purch_a = a.get("purchasability_v36") or {}
    purch_b = b.get("purchasability_v36") or {}
    by_v36 = _cmp_nullable_number_desc(purch_a.get("score"), purch_b.get("score"))
    if by_v36 != 0:
        return by_v36

    signals_a = a.get("signals") or {}
    signals_b = b.get("signals") or {}
    a_passed = signals_a.get("passed") is True
    b_passed = signals_b.get("passed") is True
    if a_passed != b_passed:
        return -1 if a_passed else 1

    by_yes = _cmp_nullable_number_desc(signals_a.get("yes_count"), signals_b.get("yes_count"))
    if by_yes != 0:
        return by_yes

    price_a = a.get("price_value") or {}
    price_b = b.get("price_value") or {}
    by_rating = _cmp_nullable_number_desc(price_a.get("rating"), price_b.get("rating"))
    if by_rating != 0:
        return by_rating

    by_edge = _cmp_nullable_number_desc(price_a.get("edge_pct"), price_b.get("edge_pct"))
    if by_edge != 0:
        return by_edge

    key_a = str(a.get("market_key") or "")
    key_b = str(b.get("market_key") or "")
    if key_a < key_b:
        return -1
    if key_a > key_b:
        return 1
    return 0


def _signals_matrix_from_snap(snap: Any) -> dict[str, Any] | None:
    output = as_dict(getattr(snap, "cecchino_output_json", None))
    matrix = output.get("signals_matrix")
    if isinstance(matrix, dict):
        return matrix
    signals = as_dict(getattr(snap, "signals_json", None))
    # Prefer model F matrix
    models = as_dict(signals.get("models"))
    f_block = as_dict(models.get("F"))
    if isinstance(f_block.get("matrix"), dict):
        return f_block["matrix"]
    if isinstance(signals.get("default_matrix"), dict):
        return signals["default_matrix"]
    return None


def build_historical_bb_opportunities(snap: Any) -> list[dict[str, Any]]:
    """Opportunity Bet Builder da dati pre-match persistiti (no engine call)."""
    kpi_idx = index_kpi_rows(getattr(snap, "historical_kpi_json", None))
    purch_idx = index_purch_v36(getattr(snap, "purchasability_compatibility_json", None))
    matrix = _signals_matrix_from_snap(snap)
    opportunities: list[dict[str, Any]] = []

    for mk in BET_BUILDER_MARKET_KEYS:
        kpi_row = kpi_idx.get(mk)
        price = build_price_value(kpi_row)
        signals = build_signals_evidence(market_key=mk, signals_matrix=matrix)
        origin = _origin(bool(price.get("present")), bool(signals.get("present")))
        if origin is None:
            continue
        purch_row = purch_idx.get(mk) or {}
        score = purch_row.get("score")
        purch_v36 = {
            "available": score is not None and purch_row.get("status") in (None, "score", "computed"),
            "score": score,
            "class": purch_row.get("class"),
            "status": purch_row.get("status"),
        }
        opportunities.append(
            {
                "market_key": mk,
                "origin": origin,
                "price_value": price,
                "signals": signals,
                "purchasability_v36": purch_v36,
            }
        )
    return opportunities


def bet_builder_meta_by_market(snap: Any) -> dict[str, dict[str, Any]]:
    """Per market_key: active/rank/reason della proiezione storica."""
    ops = build_historical_bb_opportunities(snap)
    if not ops:
        return {}
    sorted_ops = sorted(ops, key=cmp_to_key(compare_opportunity_evidence_v36))
    out: dict[str, dict[str, Any]] = {}
    for rank, opp in enumerate(sorted_ops, start=1):
        mk = str(opp["market_key"])
        active = rank == 1
        reason_parts = [
            f"origin={opp.get('origin')}",
            f"v36={((opp.get('purchasability_v36') or {}).get('score'))}",
            f"signals_passed={((opp.get('signals') or {}).get('passed'))}",
            f"policy={PATTERN_LAB_SORT_POLICY_BB}",
        ]
        out[mk] = {
            "active": active,
            "rank": rank,
            "reason": "; ".join(str(p) for p in reason_parts),
            "origin": opp.get("origin"),
        }
    return out
