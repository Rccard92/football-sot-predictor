"""Mapping segnali matrice Cecchino verso mercati valutabili."""

from __future__ import annotations

from typing import Any

from app.models.cecchino_signal_activation import (
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    PERIOD_FT,
    PERIOD_HT,
    PERIOD_UNKNOWN,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

REASON_MISSING_TARGET = "missing_target_market_mapping"

ROW_KEY_TO_SIGNAL_GROUP: dict[str, str] = {
    "under_under_pt": "UNDER_UNDER_PT",
    "draw": "DRAW",
    "over_over_pt": "OVER_OVER_PT",
    "one": "HOME",
    "one_x": "ONE_X",
    "two": "AWAY",
    "x_two": "X_TWO",
    "twelve": "ONE_TWO",
}

SIGNAL_COLUMN_TO_SOURCE: dict[str, str] = {
    "excel_d": "EXCEL_D",
    "excel_e": "EXCEL_E",
    "excel_f": "EXCEL_F",
    "excel_g": "EXCEL_G",
    "scala_1x": "SCALA",
    "scala_x2": "SCALA",
}

SIGNAL_GROUP_TO_MARKET_KEY: dict[str, str] = {
    "HOME": SEL_HOME,
    "DRAW": SEL_DRAW,
    "AWAY": SEL_AWAY,
    "ONE_X": SEL_ONE_X,
    "X_TWO": SEL_X_TWO,
    "ONE_TWO": SEL_ONE_TWO,
}

CECCHINO_SIGNAL_TARGET_MAPPING: dict[str, dict[str, Any]] = {
    "DRAW": {
        "target_market_key": SEL_DRAW,
        "target_market_label": "X",
        "target_period": PERIOD_FT,
    },
    "HOME": {
        "target_market_key": SEL_HOME,
        "target_market_label": "1",
        "target_period": PERIOD_FT,
    },
    "AWAY": {
        "target_market_key": SEL_AWAY,
        "target_market_label": "2",
        "target_period": PERIOD_FT,
    },
    "ONE_X": {
        "target_market_key": SEL_ONE_X,
        "target_market_label": "1X",
        "target_period": PERIOD_FT,
    },
    "X_TWO": {
        "target_market_key": SEL_X_TWO,
        "target_market_label": "X2",
        "target_period": PERIOD_FT,
    },
    "ONE_TWO": {
        "target_market_key": SEL_ONE_TWO,
        "target_market_label": "12",
        "target_period": PERIOD_FT,
    },
    # Placeholder — richiede mapping esplicito per colonna Excel
    "UNDER_UNDER_PT": "requires explicit market mapping",
    "OVER_OVER_PT": "requires explicit market mapping",
}

_GOAL_MARKET_KEYS = {
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
}


def map_row_key_to_signal_group(row_key: str) -> str | None:
    return ROW_KEY_TO_SIGNAL_GROUP.get(row_key)


def map_column_to_source(column_key: str) -> str | None:
    return SIGNAL_COLUMN_TO_SOURCE.get(column_key)


def market_key_for_signal_group(signal_group: str) -> str | None:
    return SIGNAL_GROUP_TO_MARKET_KEY.get(signal_group)


def extract_kpi_context(kpi_panel: dict[str, Any] | None, signal_group: str) -> dict[str, Any]:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return {}
    market_key = market_key_for_signal_group(signal_group)
    if not market_key:
        return {}
    rows = kpi_panel.get("rows") or []
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_key") == market_key or row.get("segno") == market_key:
            return {
                "quota_book": row.get("quota_book"),
                "quota_cecchino": row.get("quota_cecchino"),
                "prob_book": row.get("prob_book"),
                "prob_cecchino": row.get("prob_cecchino"),
                "edge_pct": row.get("edge_pct"),
                "rating": row.get("rating"),
            }
    return {}


def map_cecchino_signal_to_target(
    signal_group: str,
    source_column: str,
    signal_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = signal_payload or {}
    explicit_key = payload.get("target_market_key")
    if explicit_key and explicit_key in _GOAL_MARKET_KEYS:
        period = PERIOD_HT if "PT" in explicit_key else PERIOD_FT
        return {
            "target_market_key": explicit_key,
            "target_market_label": payload.get("target_market_label") or explicit_key,
            "target_period": period,
            "evaluation_status": EVAL_PENDING,
            "evaluation_reason": None,
        }

    mapping = CECCHINO_SIGNAL_TARGET_MAPPING.get(signal_group)
    if isinstance(mapping, dict):
        return {
            "target_market_key": mapping["target_market_key"],
            "target_market_label": mapping["target_market_label"],
            "target_period": mapping["target_period"],
            "evaluation_status": EVAL_PENDING,
            "evaluation_reason": None,
        }

    return {
        "target_market_key": None,
        "target_market_label": None,
        "target_period": PERIOD_UNKNOWN,
        "evaluation_status": EVAL_NOT_EVALUABLE,
        "evaluation_reason": REASON_MISSING_TARGET,
    }
