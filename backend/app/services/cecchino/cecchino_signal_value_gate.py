"""Value gate segnali monitorati Cecchino — quota book >= quota Cecchino."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def signal_has_value_from_kpi_context(kpi_ctx: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Verifica se il contesto KPI indica un segnale comprabile a valore."""
    if not kpi_ctx or not isinstance(kpi_ctx, dict):
        return False, "missing_quota_book", {}

    book = _to_decimal(kpi_ctx.get("quota_book"))
    cecchino = _to_decimal(kpi_ctx.get("quota_cecchino"))

    if book is None:
        return False, "missing_quota_book", {}
    if cecchino is None:
        return False, "missing_quota_cecchino", {"quota_book": book}
    if book <= 0:
        return False, "invalid_quota_book", {"quota_book": book, "quota_cecchino": cecchino}
    if cecchino <= 0:
        return False, "invalid_quota_cecchino", {"quota_book": book, "quota_cecchino": cecchino}

    meta: dict[str, Any] = {
        "quota_book": book,
        "quota_cecchino": cecchino,
        "value_delta": book - cecchino,
        "value_edge_pct": ((book / cecchino) - Decimal("1")) * Decimal("100"),
    }

    if book >= cecchino:
        return True, "value_ok", meta
    return False, "no_value_book_below_cecchino", meta


SYNC_VALUE_COUNTER_KEYS: tuple[str, ...] = (
    "si_cells_seen",
    "value_passed",
    "no_value_skipped",
    "missing_book_quote_skipped",
    "missing_cecchino_quote_skipped",
    "invalid_quote_skipped",
    "deactivated_no_value",
)


def empty_sync_value_counters() -> dict[str, int]:
    return {key: 0 for key in SYNC_VALUE_COUNTER_KEYS}


def merge_sync_value_counters(base: dict[str, int], other: dict[str, int]) -> None:
    for key in SYNC_VALUE_COUNTER_KEYS:
        base[key] = int(base.get(key, 0)) + int(other.get(key, 0))
