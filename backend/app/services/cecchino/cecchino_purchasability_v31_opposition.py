"""Famiglie e complemento matematico Acquistabilità V3.1.

Usa cecchino_market_opposition / MARKET_COMPLETE_SETS come fonte canonica.
Pressione opposizione = probabilità fair del complemento (1 - p_selected).
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_market_opposition import (
    FAMILY_DOUBLE_CHANCE,
    FAMILY_MATCH_WINNER,
    MARKET_COMPLETE_SETS,
    NORM_NOT_APPLICABLE_OVERLAPPING,
    PANEL_MARKET_KEYS,
    PERIOD_FT,
    get_opposition,
    required_selections_for_normalization,
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

V31_OPPOSITION_MAP_VERSION = "cecchino_purchasability_v31_opposition_map_v1"

FAMILY_MATCH_WINNER_FT = "MATCH_WINNER_FT"
FAMILY_MATCH_WINNER_HT = "MATCH_WINNER_HT"
FAMILY_DOUBLE_CHANCE_FT = "DOUBLE_CHANCE_FT"
FAMILY_GOALS_FT_1_5 = "GOALS_FT_1_5"
FAMILY_GOALS_FT_2_5 = "GOALS_FT_2_5"
FAMILY_GOALS_FT_3_5 = "GOALS_FT_3_5"
FAMILY_GOALS_HT_0_5 = "GOALS_HT_0_5"
FAMILY_GOALS_HT_1_5 = "GOALS_HT_1_5"

MATCH_WINNER_FT_MARKETS = frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY})
MATCH_WINNER_HT_MARKETS = frozenset({SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT})
DOUBLE_CHANCE_FT_MARKETS = frozenset({SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO})
GOALS_FT_1_5_MARKETS = frozenset({SEL_OVER_1_5, SEL_UNDER_1_5})
GOALS_FT_2_5_MARKETS = frozenset({SEL_OVER_2_5, SEL_UNDER_2_5})
GOALS_FT_3_5_MARKETS = frozenset({SEL_OVER_3_5, SEL_UNDER_3_5})
GOALS_HT_0_5_MARKETS = frozenset({SEL_OVER_PT_0_5, SEL_UNDER_PT_0_5})
GOALS_HT_1_5_MARKETS = frozenset({SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5})

SUPPORTED_V31_MARKETS = frozenset(PANEL_MARKET_KEYS)

_DC_COMPLEMENT: dict[str, str] = {
    SEL_ONE_X: SEL_AWAY,
    SEL_X_TWO: SEL_HOME,
    SEL_ONE_TWO: SEL_DRAW,
}

_COMPLEMENT_DEFINITIONS: dict[str, str] = {
    SEL_HOME: "DRAW + AWAY (= X2) = 1 - p_fair_HOME",
    SEL_DRAW: "HOME + AWAY (= 12) = 1 - p_fair_DRAW",
    SEL_AWAY: "HOME + DRAW (= 1X) = 1 - p_fair_AWAY",
    SEL_HOME_PT: "DRAW_PT + AWAY_PT = 1 - p_fair_HOME_PT",
    SEL_DRAW_PT: "HOME_PT + AWAY_PT = 1 - p_fair_DRAW_PT",
    SEL_AWAY_PT: "HOME_PT + DRAW_PT = 1 - p_fair_AWAY_PT",
    SEL_ONE_X: "AWAY",
    SEL_X_TWO: "HOME",
    SEL_ONE_TWO: "DRAW",
    SEL_OVER_1_5: "UNDER_1_5",
    SEL_UNDER_1_5: "OVER_1_5",
    SEL_OVER_2_5: "UNDER_2_5",
    SEL_UNDER_2_5: "OVER_2_5",
    SEL_OVER_3_5: "UNDER_3_5",
    SEL_UNDER_3_5: "OVER_3_5",
    SEL_OVER_PT_0_5: "UNDER_PT_0_5",
    SEL_UNDER_PT_0_5: "OVER_PT_0_5",
    SEL_OVER_PT_1_5: "UNDER_PT_1_5",
    SEL_UNDER_PT_1_5: "OVER_PT_1_5",
}

MARKET_LABELS: dict[str, str] = {
    SEL_HOME: "1",
    SEL_DRAW: "X",
    SEL_AWAY: "2",
    SEL_HOME_PT: "1 PT",
    SEL_DRAW_PT: "X PT",
    SEL_AWAY_PT: "2 PT",
    SEL_ONE_X: "1X",
    SEL_X_TWO: "X2",
    SEL_ONE_TWO: "12",
    SEL_OVER_1_5: "Over 1.5",
    SEL_UNDER_1_5: "Under 1.5",
    SEL_OVER_2_5: "Over 2.5",
    SEL_UNDER_2_5: "Under 2.5",
    SEL_OVER_3_5: "Over 3.5",
    SEL_UNDER_3_5: "Under 3.5",
    SEL_OVER_PT_0_5: "Over PT 0.5",
    SEL_UNDER_PT_0_5: "Under PT 0.5",
    SEL_OVER_PT_1_5: "Over PT 1.5",
    SEL_UNDER_PT_1_5: "Under PT 1.5",
}

COMPLEMENT_SUM_TOLERANCE = 1e-6


def is_v31_supported_market(market_key: str) -> bool:
    return market_key in SUPPORTED_V31_MARKETS


def market_family_for(market_key: str) -> str | None:
    if market_key in MATCH_WINNER_FT_MARKETS:
        return FAMILY_MATCH_WINNER_FT
    if market_key in MATCH_WINNER_HT_MARKETS:
        return FAMILY_MATCH_WINNER_HT
    if market_key in DOUBLE_CHANCE_FT_MARKETS:
        return FAMILY_DOUBLE_CHANCE_FT
    if market_key in GOALS_FT_1_5_MARKETS:
        return FAMILY_GOALS_FT_1_5
    if market_key in GOALS_FT_2_5_MARKETS:
        return FAMILY_GOALS_FT_2_5
    if market_key in GOALS_FT_3_5_MARKETS:
        return FAMILY_GOALS_FT_3_5
    if market_key in GOALS_HT_0_5_MARKETS:
        return FAMILY_GOALS_HT_0_5
    if market_key in GOALS_HT_1_5_MARKETS:
        return FAMILY_GOALS_HT_1_5
    return None


def family_markets(family: str) -> frozenset[str]:
    mapping = {
        FAMILY_MATCH_WINNER_FT: MATCH_WINNER_FT_MARKETS,
        FAMILY_MATCH_WINNER_HT: MATCH_WINNER_HT_MARKETS,
        FAMILY_DOUBLE_CHANCE_FT: DOUBLE_CHANCE_FT_MARKETS,
        FAMILY_GOALS_FT_1_5: GOALS_FT_1_5_MARKETS,
        FAMILY_GOALS_FT_2_5: GOALS_FT_2_5_MARKETS,
        FAMILY_GOALS_FT_3_5: GOALS_FT_3_5_MARKETS,
        FAMILY_GOALS_HT_0_5: GOALS_HT_0_5_MARKETS,
        FAMILY_GOALS_HT_1_5: GOALS_HT_1_5_MARKETS,
    }
    return mapping.get(family, frozenset())


def family_ambiguity_applicable(family: str | None) -> bool:
    return family in (FAMILY_MATCH_WINNER_FT, FAMILY_MATCH_WINNER_HT)


def family_ambiguity_status_default(family: str | None) -> str:
    if family in (FAMILY_MATCH_WINNER_FT, FAMILY_MATCH_WINNER_HT):
        return "applicable"
    if family == FAMILY_DOUBLE_CHANCE_FT:
        return NORM_NOT_APPLICABLE_OVERLAPPING
    if family and family.startswith("GOALS_"):
        return "not_applicable_binary_complement"
    return "not_applicable"


def competitors_for_market(market_key: str) -> list[str]:
    family = market_family_for(market_key)
    if not family_ambiguity_applicable(family):
        return []
    return sorted(m for m in family_markets(family or "") if m != market_key)


def market_label_for(market_key: str) -> str:
    return MARKET_LABELS.get(market_key, market_key)


def period_and_line_for(market_key: str) -> tuple[str | None, float | None]:
    opp = get_opposition(market_key)
    if opp.get("opposition_status") != "supported":
        return None, None
    return opp.get("period"), opp.get("line")


def complete_set_for(market_key: str) -> frozenset[str] | None:
    opp = get_opposition(market_key)
    family = opp.get("canonical_market_family")
    period = opp.get("period")
    line = opp.get("line")
    if family == FAMILY_DOUBLE_CHANCE:
        return MARKET_COMPLETE_SETS.get((FAMILY_MATCH_WINNER, PERIOD_FT, None))
    if family is None or period is None:
        return None
    return required_selections_for_normalization(family, period, line)


def complement_selection_keys(market_key: str) -> list[str]:
    if market_key in _DC_COMPLEMENT:
        return [_DC_COMPLEMENT[market_key]]
    complete = complete_set_for(market_key)
    if complete is None:
        return []
    opp = get_opposition(market_key)
    if opp.get("canonical_market_family") == FAMILY_DOUBLE_CHANCE:
        return [_DC_COMPLEMENT[market_key]]
    return sorted(k for k in complete if k != market_key)


def complement_definition_for(market_key: str) -> str:
    return _COMPLEMENT_DEFINITIONS.get(market_key, f"1 - p_fair_{market_key}")


def resolve_mathematical_complement(
    market_key: str,
    *,
    selected_fair_probability: float | None,
    normalized_fair_probabilities: dict[str, float] | None = None,
    fair_book_by_market: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """Risolve complemento = 1 - p_selected (set completo) o p(complemento DC)."""
    fair = fair_book_by_market or {}
    normalized = dict(normalized_fair_probabilities or {})
    complement_keys = complement_selection_keys(market_key)
    definition = complement_definition_for(market_key)
    complete = complete_set_for(market_key)

    if selected_fair_probability is None:
        return {
            "status": "unavailable",
            "complement_fair_probability": None,
            "complement_definition": definition,
            "complement_selection_keys": complement_keys,
            "complete_set": sorted(complete) if complete else None,
            "complement_sum_check": None,
            "complement_sum_ok": False,
            "reason_code": "complement_probability_unavailable",
        }

    p_sel = float(selected_fair_probability)
    if p_sel > 1.0:
        p_sel = p_sel / 100.0

    if market_key not in DOUBLE_CHANCE_FT_MARKETS:
        p_comp = 1.0 - p_sel
        sum_check = p_sel + p_comp
        return {
            "status": "ok",
            "complement_fair_probability": p_comp,
            "selected_fair_probability": p_sel,
            "complement_definition": definition,
            "complement_selection_keys": complement_keys,
            "complete_set": sorted(complete) if complete else None,
            "complement_sum_check": sum_check,
            "complement_sum_ok": abs(sum_check - 1.0) <= COMPLEMENT_SUM_TOLERANCE,
            "normalization_source": "one_minus_selected_fair",
        }

    comp_key = complement_keys[0] if complement_keys else None
    p_comp = None
    if comp_key and comp_key in normalized:
        p_comp = float(normalized[comp_key])
    elif comp_key and fair.get(comp_key) is not None:
        raw = float(fair[comp_key])  # type: ignore[arg-type]
        p_comp = raw / 100.0 if raw > 1.0 else raw

    if p_comp is None:
        p_comp = 1.0 - p_sel

    sum_check = p_sel + p_comp
    return {
        "status": "ok",
        "complement_fair_probability": p_comp,
        "selected_fair_probability": p_sel,
        "complement_definition": definition,
        "complement_selection_keys": complement_keys,
        "complete_set": sorted(complete) if complete else None,
        "complement_sum_check": sum_check,
        "complement_sum_ok": abs(sum_check - 1.0) <= COMPLEMENT_SUM_TOLERANCE,
        "normalization_source": "dc_single_outcome_complement",
        "diagnostic_comparators": get_opposition(market_key).get(
            "comparator_selections"
        ),
    }


def diagnostic_direct_comparators(market_key: str) -> list[str]:
    opp = get_opposition(market_key)
    return list(opp.get("comparator_selections") or [])
