"""Relation registry V3.5 — relazioni strutturali vs complementi deterministici."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_RELATION_REGISTRY_VERSION,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)


@dataclass(frozen=True)
class MarketRelation:
    source_market: str
    related_market: str
    relation_type: str
    relation_weight: float
    used_in_score: bool
    reason: str


def _rel(
    source: str,
    related: str,
    *,
    relation_type: str,
    weight: float,
    used_in_score: bool,
    reason: str,
) -> MarketRelation:
    return MarketRelation(
        source_market=source,
        related_market=related,
        relation_type=relation_type,
        relation_weight=weight,
        used_in_score=used_in_score,
        reason=reason,
    )


def _pair_bidirectional(
    a: str,
    b: str,
    *,
    relation_type: str,
    weight: float,
    used_in_score: bool,
    reason: str,
) -> tuple[MarketRelation, ...]:
    return (
        _rel(a, b, relation_type=relation_type, weight=weight, used_in_score=used_in_score, reason=reason),
        _rel(b, a, relation_type=relation_type, weight=weight, used_in_score=used_in_score, reason=reason),
    )


def _deterministic_complement(over: str, under: str) -> tuple[MarketRelation, ...]:
    return _pair_bidirectional(
        over,
        under,
        relation_type="deterministic",
        weight=1.0,
        used_in_score=False,
        reason="mathematical_complement",
    )


_RELATIONS: tuple[MarketRelation, ...] = (
    # --- Deterministic complements (audit only) ---
    *_deterministic_complement(SEL_OVER_1_5, SEL_UNDER_1_5),
    *_deterministic_complement(SEL_OVER_2_5, SEL_UNDER_2_5),
    *_deterministic_complement(SEL_OVER_3_5, SEL_UNDER_3_5),
    *_deterministic_complement(SEL_OVER_PT_0_5, SEL_UNDER_PT_0_5),
    *_deterministic_complement(SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5),
    *_pair_bidirectional(
        SEL_DRAW,
        SEL_ONE_TWO,
        relation_type="deterministic",
        weight=1.0,
        used_in_score=False,
        reason="mathematical_complement",
    ),
    # --- Match side cover ---
    _rel(SEL_HOME, SEL_ONE_X, relation_type="side_cover", weight=0.60, used_in_score=True, reason="side_cover_support"),
    _rel(SEL_ONE_X, SEL_HOME, relation_type="side_cover", weight=0.60, used_in_score=True, reason="side_cover_support"),
    _rel(SEL_AWAY, SEL_X_TWO, relation_type="side_cover", weight=0.60, used_in_score=True, reason="side_cover_support"),
    _rel(SEL_X_TWO, SEL_AWAY, relation_type="side_cover", weight=0.60, used_in_score=True, reason="side_cover_support"),
    # --- Goal ladder FT OVER ---
    _rel(SEL_OVER_1_5, SEL_OVER_2_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    _rel(SEL_OVER_2_5, SEL_OVER_1_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    _rel(SEL_OVER_2_5, SEL_OVER_3_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    _rel(SEL_OVER_3_5, SEL_OVER_2_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    # --- Goal ladder FT UNDER ---
    _rel(SEL_UNDER_1_5, SEL_UNDER_2_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    _rel(SEL_UNDER_2_5, SEL_UNDER_1_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    _rel(SEL_UNDER_2_5, SEL_UNDER_3_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    _rel(SEL_UNDER_3_5, SEL_UNDER_2_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    # --- Goal ladder HT OVER ---
    _rel(SEL_OVER_PT_0_5, SEL_OVER_PT_1_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    _rel(SEL_OVER_PT_1_5, SEL_OVER_PT_0_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    # --- Goal ladder HT UNDER ---
    _rel(SEL_UNDER_PT_0_5, SEL_UNDER_PT_1_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
    _rel(SEL_UNDER_PT_1_5, SEL_UNDER_PT_0_5, relation_type="adjacent_goal_line", weight=1.00, used_in_score=True, reason="adjacent_goal_line"),
)

RELATION_REGISTRY: tuple[MarketRelation, ...] = _RELATIONS

RELATIONS_BY_SOURCE: dict[str, tuple[MarketRelation, ...]] = {}
for _r in _RELATIONS:
    RELATIONS_BY_SOURCE.setdefault(_r.source_market, []).append(_r)
RELATIONS_BY_SOURCE = {k: tuple(v) for k, v in RELATIONS_BY_SOURCE.items()}


def relations_for_market(market_key: str) -> tuple[MarketRelation, ...]:
    return RELATIONS_BY_SOURCE.get(market_key, ())


def scoreable_relations_for_market(market_key: str) -> tuple[MarketRelation, ...]:
    return tuple(r for r in relations_for_market(market_key) if r.used_in_score)


def relation_registry_audit() -> list[dict[str, Any]]:
    return [
        {
            "source_market": r.source_market,
            "related_market": r.related_market,
            "relation_type": r.relation_type,
            "relation_weight": r.relation_weight,
            "used_in_score": r.used_in_score,
            "reason": r.reason,
        }
        for r in RELATION_REGISTRY
    ]


def relation_registry_version() -> str:
    return PURCHASABILITY_V35_RELATION_REGISTRY_VERSION
