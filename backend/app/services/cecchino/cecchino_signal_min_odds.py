"""Soglie minime quota book per Monitoraggio Segnali Cecchino — centralizzate."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.cecchino.cecchino_selection_keys import (
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)

DEFAULT_SIGNAL_MIN_BOOK_ODDS: dict[str, Decimal] = {
    SEL_DRAW: Decimal("3.00"),
    SEL_DRAW_PT: Decimal("1.90"),
    SEL_ONE_X: Decimal("1.37"),
    SEL_X_TWO: Decimal("1.45"),
    SEL_ONE_TWO: Decimal("1.37"),
    SEL_UNDER_2_5: Decimal("2.00"),
    SEL_OVER_2_5: Decimal("1.85"),
}

MIN_BOOK_ODD_LABELS: dict[str, str] = {
    SEL_DRAW: "X",
    SEL_DRAW_PT: "X PT",
    SEL_ONE_X: "1X",
    SEL_X_TWO: "X2",
    SEL_ONE_TWO: "1/2",
    SEL_UNDER_2_5: "Under 2.5",
    SEL_OVER_2_5: "Over 2.5",
}


def get_min_book_odd(
    target_market_key: str | None,
    *,
    min_book_odds: dict[str, Decimal] | None = None,
) -> Decimal | None:
    if not target_market_key:
        return None
    table = min_book_odds if min_book_odds is not None else DEFAULT_SIGNAL_MIN_BOOK_ODDS
    return table.get(target_market_key)


def list_min_book_odds_for_api(
    *,
    min_book_odds: dict[str, Decimal] | None = None,
    db: Any | None = None,
) -> list[dict[str, Any]]:
    if min_book_odds is None and db is not None:
        from app.services.cecchino.cecchino_signal_min_book_odd_settings_service import (
            load_signal_min_book_odds,
        )

        min_book_odds = load_signal_min_book_odds(db)
    table = min_book_odds if min_book_odds is not None else DEFAULT_SIGNAL_MIN_BOOK_ODDS
    items: list[dict[str, Any]] = []
    for key in (
        SEL_DRAW,
        SEL_DRAW_PT,
        SEL_ONE_X,
        SEL_X_TWO,
        SEL_ONE_TWO,
        SEL_UNDER_2_5,
        SEL_OVER_2_5,
    ):
        min_odd = table.get(key)
        if min_odd is None:
            continue
        items.append(
            {
                "target_market_key": key,
                "label": MIN_BOOK_ODD_LABELS.get(key, key),
                "min_book_odd": float(min_odd),
            },
        )
    return items
