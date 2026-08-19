"""Risoluzione Affidabilità storica per orchestrazione V3.1 (batch-friendly)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_historical_reliability import (
    build_historical_reliability_for_panel,
    build_historical_reliability_global_index,
    build_historical_reliability_index,
    iter_current_kpi_panel_rows,
    panel_item_key,
)
from app.services.cecchino.cecchino_purchasability_audit import build_purchasability_rows


def build_hr_history_context(
    db: Session,
    *,
    date_to: date,
) -> dict[str, Any]:
    """Costruisce indici storici una sola volta per un intervallo/job."""
    history_rows = build_purchasability_rows(db, date_to=date_to)
    return {
        "history_rows": history_rows,
        "local_index": build_historical_reliability_index(history_rows),
        "global_index": build_historical_reliability_global_index(history_rows),
        "date_to": date_to,
    }


def resolve_hr_by_market_for_fixture(
    db: Session | None,
    row: CecchinoTodayFixture | None,
    kpi_panel: dict[str, Any] | None,
    *,
    history_context: dict[str, Any] | None = None,
    today_fixture_id: Any = None,
    competition_id: Any = None,
    kickoff: Any = None,
    scan_date: date | None = None,
) -> dict[str, dict[str, Any]]:
    """Mappa market_key → item Affidabilità storica. Nessuna scrittura."""
    if row is not None:
        today_fixture_id = int(row.id)
        competition_id = row.competition_id
        kickoff = row.kickoff
        scan_date = row.scan_date
        fixtures = [row]
        current_rows = iter_current_kpi_panel_rows([row])
    else:
        fixtures = None
        current_rows = []

    if not current_rows and isinstance(kpi_panel, dict):
        for r in kpi_panel.get("rows") or []:
            if not isinstance(r, dict):
                continue
            current_rows.append(
                {
                    **r,
                    "today_fixture_id": today_fixture_id,
                    "competition_id": competition_id,
                    "kickoff": kickoff.isoformat()
                    if hasattr(kickoff, "isoformat")
                    else kickoff,
                    "scan_date": scan_date.isoformat()
                    if hasattr(scan_date, "isoformat")
                    else scan_date,
                }
            )

    if not current_rows:
        return {}

    scan_d = scan_date
    if scan_d is None:
        return {}

    history_rows = None
    local_index = None
    global_index = None
    if isinstance(history_context, dict):
        history_rows = history_context.get("history_rows")
        local_index = history_context.get("local_index")
        global_index = history_context.get("global_index")

    if db is None and history_rows is None:
        return {}

    try:
        payload = build_historical_reliability_for_panel(
            db,  # type: ignore[arg-type]
            date_from=scan_d,
            date_to=scan_d,
            competition_id=int(competition_id) if competition_id is not None else None,
            current_rows=current_rows,
            fixtures=fixtures,
            history_rows=history_rows,
            local_index=local_index,
            global_index=global_index,
        )
    except Exception:
        return {}

    items = payload.get("items") if isinstance(payload, dict) else {}
    by_market: dict[str, dict[str, Any]] = {}
    if not isinstance(items, dict):
        return by_market

    for _key, item in items.items():
        if not isinstance(item, dict):
            continue
        mk = str(item.get("market_key") or item.get("selection") or "")
        if mk:
            by_market[mk] = item

    for r in current_rows:
        mk = str(r.get("market_key") or r.get("segno") or "")
        if not mk:
            continue
        k = panel_item_key(today_fixture_id=today_fixture_id, market_key=mk)
        if k in items and mk not in by_market:
            by_market[mk] = items[k]
    return by_market
