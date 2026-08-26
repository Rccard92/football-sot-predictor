"""Relation registry V3.5 Structural V2 — family opposition + side-cover + goal ladder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.cecchino_purchasability_v35_v2 import (
    PURCHASABILITY_V35_V2_RELATION_REGISTRY_VERSION,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    STRENGTH_GOAL_LADDER,
    STRENGTH_SAME_FAMILY_OPPOSITION,
    STRENGTH_SIDE_COVER,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
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

BLOCK_SAME_FAMILY = "same_family_opposition"
BLOCK_SIDE_COVER = "side_cover"
BLOCK_GOAL_LADDER = "goal_ladder"


@dataclass(frozen=True)
class StructuralEvidenceBlock:
    """Un evidence block (non relazioni indipendenti dentro la famiglia)."""

    block_type: str
    selected_market: str
    related_markets: tuple[str, ...]
    configured_strength: float
    support_mode: str  # "opposition_inverted" | "agreement"
    reason: str


def _family_block(
    selected: str,
    opponents: tuple[str, str],
) -> StructuralEvidenceBlock:
    return StructuralEvidenceBlock(
        block_type=BLOCK_SAME_FAMILY,
        selected_market=selected,
        related_markets=opponents,
        configured_strength=STRENGTH_SAME_FAMILY_OPPOSITION,
        support_mode="opposition_inverted",
        reason="same_family_opposition_support",
    )


def _side_cover_block(selected: str, related: str) -> StructuralEvidenceBlock:
    return StructuralEvidenceBlock(
        block_type=BLOCK_SIDE_COVER,
        selected_market=selected,
        related_markets=(related,),
        configured_strength=STRENGTH_SIDE_COVER,
        support_mode="agreement",
        reason="side_cover_support",
    )


def _goal_ladder_block(
    selected: str,
    related: tuple[str, ...],
) -> StructuralEvidenceBlock:
    return StructuralEvidenceBlock(
        block_type=BLOCK_GOAL_LADDER,
        selected_market=selected,
        related_markets=related,
        configured_strength=STRENGTH_GOAL_LADDER,
        support_mode="agreement",
        reason="adjacent_goal_line",
    )


_BLOCKS: tuple[StructuralEvidenceBlock, ...] = (
    # --- 1X2 FT family opposition ---
    _family_block(SEL_HOME, (SEL_DRAW, SEL_AWAY)),
    _family_block(SEL_DRAW, (SEL_HOME, SEL_AWAY)),
    _family_block(SEL_AWAY, (SEL_HOME, SEL_DRAW)),
    # --- 1X2 PT family opposition ---
    _family_block(SEL_HOME_PT, (SEL_DRAW_PT, SEL_AWAY_PT)),
    _family_block(SEL_DRAW_PT, (SEL_HOME_PT, SEL_AWAY_PT)),
    _family_block(SEL_AWAY_PT, (SEL_HOME_PT, SEL_DRAW_PT)),
    # --- Side cover (separate blocks) ---
    _side_cover_block(SEL_HOME, SEL_ONE_X),
    _side_cover_block(SEL_ONE_X, SEL_HOME),
    _side_cover_block(SEL_AWAY, SEL_X_TWO),
    _side_cover_block(SEL_X_TWO, SEL_AWAY),
    # --- Goal ladder FT OVER ---
    _goal_ladder_block(SEL_OVER_1_5, (SEL_OVER_2_5,)),
    _goal_ladder_block(SEL_OVER_2_5, (SEL_OVER_1_5, SEL_OVER_3_5)),
    _goal_ladder_block(SEL_OVER_3_5, (SEL_OVER_2_5,)),
    # --- Goal ladder FT UNDER ---
    _goal_ladder_block(SEL_UNDER_1_5, (SEL_UNDER_2_5,)),
    _goal_ladder_block(SEL_UNDER_2_5, (SEL_UNDER_1_5, SEL_UNDER_3_5)),
    _goal_ladder_block(SEL_UNDER_3_5, (SEL_UNDER_2_5,)),
    # --- Goal ladder HT OVER ---
    _goal_ladder_block(SEL_OVER_PT_0_5, (SEL_OVER_PT_1_5,)),
    _goal_ladder_block(SEL_OVER_PT_1_5, (SEL_OVER_PT_0_5,)),
    # --- Goal ladder HT UNDER ---
    _goal_ladder_block(SEL_UNDER_PT_0_5, (SEL_UNDER_PT_1_5,)),
    _goal_ladder_block(SEL_UNDER_PT_1_5, (SEL_UNDER_PT_0_5,)),
)

BLOCKS_BY_MARKET: dict[str, tuple[StructuralEvidenceBlock, ...]] = {}
for _b in _BLOCKS:
    BLOCKS_BY_MARKET.setdefault(_b.selected_market, []).append(_b)
BLOCKS_BY_MARKET = {k: tuple(v) for k, v in BLOCKS_BY_MARKET.items()}

# Deterministic complements — audit only, never used in S
_AUDIT_ONLY_COMPLEMENTS: tuple[tuple[str, str], ...] = (
    (SEL_OVER_1_5, SEL_UNDER_1_5),
    (SEL_OVER_2_5, SEL_UNDER_2_5),
    (SEL_OVER_3_5, SEL_UNDER_3_5),
    (SEL_OVER_PT_0_5, SEL_UNDER_PT_0_5),
    (SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5),
    (SEL_DRAW, SEL_ONE_TWO),
)


def blocks_for_market(market_key: str) -> tuple[StructuralEvidenceBlock, ...]:
    return BLOCKS_BY_MARKET.get(market_key, ())


def relation_registry_audit() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in _BLOCKS:
        rows.append(
            {
                "block_type": block.block_type,
                "selected_market": block.selected_market,
                "related_markets": list(block.related_markets),
                "configured_strength": block.configured_strength,
                "support_mode": block.support_mode,
                "used_in_score": True,
                "reason": block.reason,
                "relation_type": (
                    "same_family_opposition_support"
                    if block.block_type == BLOCK_SAME_FAMILY
                    else block.block_type
                ),
            }
        )
    for a, b in _AUDIT_ONLY_COMPLEMENTS:
        for src, rel in ((a, b), (b, a)):
            rows.append(
                {
                    "block_type": "deterministic",
                    "selected_market": src,
                    "related_markets": [rel],
                    "configured_strength": 1.0,
                    "support_mode": "none",
                    "used_in_score": False,
                    "reason": "mathematical_complement",
                    "relation_type": "deterministic",
                }
            )
    return rows


def relation_registry_version() -> str:
    return PURCHASABILITY_V35_V2_RELATION_REGISTRY_VERSION


def assert_no_synthetic_pt_dc_markets() -> None:
    forbidden = {"ONE_X_PT", "X_TWO_PT", "ONE_TWO_PT"}
    for block in _BLOCKS:
        if block.selected_market in forbidden:
            raise AssertionError(
                f"synthetic PT market in registry: {block.selected_market}"
            )
        for mk in block.related_markets:
            if mk in forbidden:
                raise AssertionError(f"synthetic PT related market: {mk}")
