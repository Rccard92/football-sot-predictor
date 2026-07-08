"""Orchestrazione save soglie + backtest/ricalcolo Monitoraggio Segnali."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache import rebuild_kpi_panels_from_cache
from app.services.cecchino.cecchino_signal_backfill import backfill_signal_activations
from app.services.cecchino.cecchino_signal_min_book_odd_settings_service import (
    load_signal_min_book_odds,
    save_signal_min_book_odds,
)


def save_signal_min_book_odds_and_backtest(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    items: list[dict[str, Any]],
    rebuild_kpi_from_cache: bool = False,
    include_xpt: bool = True,
    force_remap_signals: bool = True,
    evaluate_after: bool = True,
    updated_by: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    save_result = save_signal_min_book_odds(db, items, updated_by=updated_by)
    db.commit()

    min_book_odds = load_signal_min_book_odds(db)

    if rebuild_kpi_from_cache:
        rebuild_result = rebuild_kpi_panels_from_cache(
            db,
            date_from=date_from,
            date_to=date_to,
            include_xpt=include_xpt,
            rebuild_signals_after=False,
            evaluate_after=False,
        )
        errors.extend(rebuild_result.get("errors") or [])
        if rebuild_result.get("status") == "partial":
            pass

    backfill_result = backfill_signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        only_missing=False,
        evaluate_after=evaluate_after,
        force_remap=force_remap_signals,
        min_book_odds=min_book_odds,
    )
    errors.extend(backfill_result.get("warnings") or [])

    status = "ok"
    if errors:
        status = "partial"

    backtest = {
        "fixtures_seen": int(backfill_result.get("fixtures_found") or 0),
        "signals_rebuilt": int(backfill_result.get("fixtures_with_signals") or 0),
        "si_cells_seen": int(backfill_result.get("si_cells_seen") or 0),
        "value_passed": int(backfill_result.get("value_passed") or 0),
        "no_value_skipped": int(backfill_result.get("no_value_skipped") or 0),
        "min_book_odd_skipped": int(backfill_result.get("min_book_odd_skipped") or 0),
        "deactivated_min_book_odd": int(backfill_result.get("deactivated_min_book_odd") or 0),
        "missing_book_quote_skipped": int(backfill_result.get("missing_book_quote_skipped") or 0),
        "missing_cecchino_quote_skipped": int(backfill_result.get("missing_cecchino_quote_skipped") or 0),
        "invalid_quote_skipped": int(backfill_result.get("invalid_quote_skipped") or 0),
        "deactivated_no_value": int(backfill_result.get("deactivated_no_value") or 0),
        "evaluated": int(backfill_result.get("evaluated") or 0),
        "won": int(backfill_result.get("won") or 0),
        "lost": int(backfill_result.get("lost") or 0),
        "pending": int(backfill_result.get("pending") or 0),
        "not_evaluable": int(backfill_result.get("not_evaluable") or 0),
    }

    return {
        "status": status,
        "settings": save_result.get("items") or [],
        "backtest": backtest,
        "errors": errors[:100],
    }
