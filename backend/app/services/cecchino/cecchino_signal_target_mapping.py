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
LEGACY_WRONG_SCALA_REASON = "wrong_legacy_mapping_scala_belongs_to_1x_x2"
VALID_SCALA_SIGNAL_GROUPS = frozenset({"ONE_X", "X_TWO"})


def is_invalid_legacy_scala_activation(signal_group: str, source_column: str) -> bool:
    return source_column == "SCALA" and signal_group in ("HOME", "AWAY")


def is_valid_scala_activation(signal_group: str, source_column: str) -> bool:
    if source_column != "SCALA":
        return True
    return signal_group in VALID_SCALA_SIGNAL_GROUPS


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
    "UNDER_UNDER_PT": SEL_UNDER_2_5,
    "OVER_OVER_PT": SEL_OVER_2_5,
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
    "UNDER_UNDER_PT": {
        "target_market_key": SEL_UNDER_2_5,
        "target_market_label": "Under 2.5",
        "target_period": PERIOD_FT,
        "evaluation_type": "fulltime_total_goals_under_2_5",
    },
    "OVER_OVER_PT": {
        "target_market_key": SEL_OVER_2_5,
        "target_market_label": "Over 2.5",
        "target_period": PERIOD_FT,
        "evaluation_type": "fulltime_total_goals_over_2_5",
    },
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
    """Compatibilità legacy — delega a resolve_kpi_odds_for_activation."""
    from app.services.cecchino.cecchino_signal_odds_refresh import resolve_kpi_odds_for_activation

    return resolve_kpi_odds_for_activation(kpi_panel, signal_group=signal_group)


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
        result = {
            "target_market_key": mapping["target_market_key"],
            "target_market_label": mapping["target_market_label"],
            "target_period": mapping["target_period"],
            "evaluation_status": EVAL_PENDING,
            "evaluation_reason": None,
        }
        if mapping.get("evaluation_type"):
            result["evaluation_type"] = mapping["evaluation_type"]
        return result

    return {
        "target_market_key": None,
        "target_market_label": None,
        "target_period": PERIOD_UNKNOWN,
        "evaluation_status": EVAL_NOT_EVALUABLE,
        "evaluation_reason": REASON_MISSING_TARGET,
    }


def apply_under_over_target_to_activation(activation) -> bool:
    """Applica mapping Under/Over 2.5 FT a activation esistenti. Ritorna True se modificata."""
    signal_group = getattr(activation, "signal_group", None)
    if not signal_group:
        return False
    mapping = None
    if signal_group == "UNDER_UNDER_PT":
        mapping = CECCHINO_SIGNAL_TARGET_MAPPING["UNDER_UNDER_PT"]
    elif signal_group == "OVER_OVER_PT":
        mapping = CECCHINO_SIGNAL_TARGET_MAPPING["OVER_OVER_PT"]
    if not isinstance(mapping, dict):
        return False

    changed = False
    if activation.target_market_key != mapping["target_market_key"]:
        activation.target_market_key = mapping["target_market_key"]
        changed = True
    if activation.target_market_label != mapping["target_market_label"]:
        activation.target_market_label = mapping["target_market_label"]
        changed = True
    if activation.target_period != PERIOD_FT:
        activation.target_period = PERIOD_FT
        changed = True
    if activation.evaluation_status == EVAL_NOT_EVALUABLE or activation.evaluation_reason:
        activation.evaluation_status = EVAL_PENDING
        activation.evaluation_reason = None
        changed = True
    return changed


def remap_under_over_activations_in_range(db, *, date_from, date_to) -> int:
    """Rimap activation UNDER/OVER con target mancante o not_evaluable nel range scan_date."""
    from sqlalchemy import or_, select

    from app.models.cecchino_signal_activation import (
        EVAL_NOT_EVALUABLE,
        CecchinoSignalActivation,
    )

    rows = list(
        db.scalars(
            select(CecchinoSignalActivation).where(
                CecchinoSignalActivation.scan_date >= date_from,
                CecchinoSignalActivation.scan_date <= date_to,
                CecchinoSignalActivation.signal_group.in_(("UNDER_UNDER_PT", "OVER_OVER_PT")),
                CecchinoSignalActivation.is_current.is_(True),
                or_(
                    CecchinoSignalActivation.target_market_key.is_(None),
                    CecchinoSignalActivation.evaluation_status == EVAL_NOT_EVALUABLE,
                ),
            ),
        ).all(),
    )
    remapped = 0
    for activation in rows:
        if apply_under_over_target_to_activation(activation):
            remapped += 1
    if remapped:
        db.flush()
    return remapped
