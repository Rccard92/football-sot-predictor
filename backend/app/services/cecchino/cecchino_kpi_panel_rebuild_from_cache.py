"""Rebuild offline Pannello KPI Cecchino da snapshot/cache salvati — nessuna API esterna."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_betfair_odds_payload import build_betfair_payload_from_snapshot
from app.services.cecchino.cecchino_bookmaker_odds_service import load_betfair_odds_payload
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import build_cecchino_kpi_panel_v2_betfair
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW_PT
from app.services.cecchino.cecchino_signal_evaluation import evaluate_activations_for_fixture
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations
from app.services.cecchino.cecchino_signal_value_gate import merge_sync_value_counters
from app.services.cecchino.cecchino_today_odds_meta import read_odds_meta

logger = logging.getLogger(__name__)


def _fixtures_in_range(db: Session, date_from: date, date_to: date) -> list[CecchinoTodayFixture]:
    return list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date >= date_from,
                CecchinoTodayFixture.scan_date <= date_to,
            ),
        ).all(),
    )


def _kpi_row_for_market(kpi_panel: dict[str, Any] | None, market_key: str) -> dict[str, Any] | None:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return None
    for row in kpi_panel.get("rows") or []:
        if isinstance(row, dict) and row.get("market_key") == market_key:
            return row
    return None


def rebuild_kpi_panels_from_cache(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    include_xpt: bool = True,
    rebuild_signals_after: bool = False,
    evaluate_after: bool = False,
) -> dict[str, Any]:
    fixtures = _fixtures_in_range(db, date_from, date_to)
    counters = {
        "fixtures_seen": 0,
        "kpi_rebuilt": 0,
        "xpt_book_found": 0,
        "xpt_book_missing": 0,
        "xpt_cecchino_found": 0,
        "xpt_cecchino_missing": 0,
        "signals_rebuilt": 0,
        "si_cells_seen": 0,
        "value_passed": 0,
        "no_value_skipped": 0,
        "min_book_odd_skipped": 0,
        "missing_book_quote_skipped": 0,
        "missing_cecchino_quote_skipped": 0,
        "invalid_quote_skipped": 0,
        "deactivated_no_value": 0,
        "deactivated_min_book_odd": 0,
    }
    errors: list[str] = []

    for row in fixtures:
        counters["fixtures_seen"] += 1
        output = row.cecchino_output_json or {}
        if not isinstance(output, dict):
            errors.append(f"fixture_{row.id}:missing_cecchino_output")
            continue

        goal_markets = output.get("goal_markets")
        if goal_markets is None:
            errors.append(f"fixture_{row.id}:missing_goal_markets")

        betfair_payload = build_betfair_payload_from_snapshot(
            row.odds_snapshot_json,
            source="cached_betfair_odds",
            home_team_name=row.home_team_name,
            away_team_name=row.away_team_name,
        )
        if betfair_payload.get("status") == "not_available" and row.competition_id and row.local_fixture_id:
            betfair_payload = load_betfair_odds_payload(
                db,
                competition_id=int(row.competition_id),
                fixture_id=int(row.local_fixture_id),
            )

        if betfair_payload.get("status") == "not_available":
            errors.append(f"fixture_{row.id}:missing_odds_snapshot")
            continue

        kpi_panel = build_cecchino_kpi_panel_v2_betfair(
            final_odds=output.get("final") or {},
            betfair_payload=betfair_payload,
            goal_markets=goal_markets if isinstance(goal_markets, dict) else None,
        )
        meta = read_odds_meta(row.odds_snapshot_json)
        if meta:
            kpi_panel["odds_meta"] = meta

        row.kpi_panel_json = kpi_panel
        counters["kpi_rebuilt"] += 1

        if include_xpt:
            xpt_row = _kpi_row_for_market(kpi_panel, SEL_DRAW_PT)
            if xpt_row is None:
                counters["xpt_book_missing"] += 1
                counters["xpt_cecchino_missing"] += 1
                errors.append(f"fixture_{row.id}:xpt_row_missing")
            else:
                if xpt_row.get("quota_book") is not None:
                    counters["xpt_book_found"] += 1
                else:
                    counters["xpt_book_missing"] += 1
                    errors.append(f"fixture_{row.id}:xpt_book_missing")
                if xpt_row.get("quota_cecchino") is not None:
                    counters["xpt_cecchino_found"] += 1
                else:
                    counters["xpt_cecchino_missing"] += 1
                    errors.append(f"fixture_{row.id}:xpt_cecchino_missing")

        if rebuild_signals_after:
            sync_counts = sync_cecchino_signal_activations(db, int(row.id))
            counters["signals_rebuilt"] += 1
            merge_sync_value_counters(counters, sync_counts)
            if evaluate_after:
                evaluate_activations_for_fixture(db, int(row.id))

    db.commit()
    status = "ok" if not errors else "partial"
    logger.info(
        "cecchino_kpi_panel_rebuild_from_cache date_from=%s date_to=%s rebuilt=%s errors=%s",
        date_from.isoformat(),
        date_to.isoformat(),
        counters["kpi_rebuilt"],
        len(errors),
    )
    return {
        "status": status,
        **counters,
        "errors": errors[:100],
    }
