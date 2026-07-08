"""Value gate segnali monitorati Cecchino — quota book >= quota Cecchino e soglia minima."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.cecchino.cecchino_signal_min_odds import (
    DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    get_min_book_odd,
)

VALUE_REASON_BOOK_BELOW_MIN = "book_odd_below_min_threshold"
VALUE_REASON_OK = "value_ok"
DEACTIVATION_REASON_BOOK_BELOW_MIN = "deactivated_book_odd_below_min_threshold"


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def signal_has_value_from_kpi_context(
    kpi_ctx: dict[str, Any],
    *,
    target_market_key: str | None = None,
    min_book_odds: Mapping[str, Decimal] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Verifica se il contesto KPI indica un segnale comprabile a valore."""
    if not kpi_ctx or not isinstance(kpi_ctx, dict):
        return False, "missing_quota_book", {}

    book = _to_decimal(kpi_ctx.get("quota_book"))
    cecchino = _to_decimal(kpi_ctx.get("quota_cecchino"))

    if book is None:
        return False, "missing_quota_book", {"target_market_key": target_market_key}
    if cecchino is None:
        return False, "missing_quota_cecchino", {
            "quota_book": book,
            "target_market_key": target_market_key,
        }
    if book <= 0:
        return False, "invalid_quota_book", {
            "quota_book": book,
            "quota_cecchino": cecchino,
            "target_market_key": target_market_key,
        }
    if cecchino <= 0:
        return False, "invalid_quota_cecchino", {
            "quota_book": book,
            "quota_cecchino": cecchino,
            "target_market_key": target_market_key,
        }

    odds_table = dict(min_book_odds) if min_book_odds is not None else DEFAULT_SIGNAL_MIN_BOOK_ODDS
    min_odd = get_min_book_odd(target_market_key, min_book_odds=odds_table)

    meta: dict[str, Any] = {
        "quota_book": book,
        "quota_cecchino": cecchino,
        "value_delta": book - cecchino,
        "value_edge_pct": ((book / cecchino) - Decimal("1")) * Decimal("100"),
        "target_market_key": target_market_key,
        "min_book_odd": min_odd,
        "min_book_odd_delta": (book - min_odd) if min_odd is not None else None,
    }

    if book < cecchino:
        return False, "no_value_book_below_cecchino", meta

    if min_odd is not None and book < min_odd:
        return False, VALUE_REASON_BOOK_BELOW_MIN, meta

    return True, VALUE_REASON_OK, meta


def deactivation_reason_for_value_gate(value_reason: str) -> str:
    if value_reason == VALUE_REASON_BOOK_BELOW_MIN:
        return DEACTIVATION_REASON_BOOK_BELOW_MIN
    return value_reason


SYNC_VALUE_COUNTER_KEYS: tuple[str, ...] = (
    "si_cells_seen",
    "value_passed",
    "no_value_skipped",
    "missing_book_quote_skipped",
    "missing_cecchino_quote_skipped",
    "invalid_quote_skipped",
    "deactivated_no_value",
    "min_book_odd_skipped",
    "deactivated_min_book_odd",
    "min_book_odd_threshold_applied",
    "draw_pt_created",
    "draw_pt_updated",
    "draw_pt_deactivated",
    "draw_pt_evaluated",
    "derived_observations_created",
    "derived_observations_deactivated",
)


def empty_sync_value_counters() -> dict[str, int]:
    return {key: 0 for key in SYNC_VALUE_COUNTER_KEYS}


def merge_sync_value_counters(base: dict[str, int], other: dict[str, int]) -> None:
    for key in SYNC_VALUE_COUNTER_KEYS:
        base[key] = int(base.get(key, 0)) + int(other.get(key, 0))
