"""Smoke audit dry-run V3 vs V3.1 — sola lettura, nessuna scrittura DB.

Uso:
  python -m app.jobs.smoke_purchasability_v31_audit --date-from YYYY-MM-DD --date-to YYYY-MM-DD --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any

from sqlalchemy import select

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_purchasability_v31_candidate import (
    calculate_purchasability_v31_batch,
)
from app.services.cecchino.cecchino_purchasability_v31_hr import (
    build_hr_history_context,
    resolve_hr_by_market_for_fixture,
)
from app.services.cecchino.cecchino_purchasability_v3_snapshot import (
    index_purchasability_v3_snapshot_by_market,
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def run_smoke(
    *,
    date_from: date,
    date_to: date,
    limit: int = 20,
) -> dict[str, Any]:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        stmt = (
            select(CecchinoTodayFixture)
            .where(CecchinoTodayFixture.scan_date >= date_from)
            .where(CecchinoTodayFixture.scan_date <= date_to)
            .where(CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE)
            .order_by(CecchinoTodayFixture.scan_date.desc())
            .limit(limit)
        )
        rows = list(db.scalars(stmt).all())
        hr_ctx = build_hr_history_context(db, date_to=date_to)

        fixtures_out: list[dict[str, Any]] = []
        aggregate = {
            "fixtures": 0,
            "rows": 0,
            "scores_v31": 0,
            "non_calculable": 0,
            "gate_failed": 0,
            "derived_quotes": 0,
            "incomplete_fair": 0,
            "historical_insufficient": 0,
            "comparable": 0,
        }

        for row in rows:
            kpi = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
            if not kpi or not isinstance(kpi.get("rows"), list):
                continue
            output = (
                row.cecchino_output_json
                if isinstance(row.cecchino_output_json, dict)
                else {}
            )
            v3 = output.get("purchasability_preview_v3")
            v3_by = index_purchasability_v3_snapshot_by_market(
                v3 if isinstance(v3, dict) else None
            )
            hr_by = resolve_hr_by_market_for_fixture(
                db, row, kpi, history_context=hr_ctx
            )
            batch = calculate_purchasability_v31_batch(
                kpi_panel=kpi,
                fixture_meta={
                    "today_fixture_id": int(row.id),
                    "kickoff": row.kickoff,
                    "scan_date": row.scan_date,
                    "competition_id": row.competition_id,
                    "snapshot_timestamp_verified": True,
                    "kickoff_required": True,
                },
                historical_by_market=hr_by,
                v3_items_by_market=v3_by,
            )
            summary = batch.get("shadow_summary") or batch.get("summary") or {}
            aggregate["fixtures"] += 1
            aggregate["rows"] += int(summary.get("rows_total") or 0)
            aggregate["scores_v31"] += int(summary.get("scores_produced") or 0)
            aggregate["non_calculable"] += int(summary.get("non_calculable") or 0)
            aggregate["gate_failed"] += int(summary.get("gate_failed") or 0)
            aggregate["derived_quotes"] += int(summary.get("quotes_derived") or 0)
            aggregate["incomplete_fair"] += int(summary.get("fair_set_incomplete") or 0)
            aggregate["historical_insufficient"] += int(
                summary.get("historical_insufficient") or 0
            )
            aggregate["comparable"] += int(summary.get("comparable_rows") or 0)
            fixtures_out.append(
                {
                    "today_fixture_id": int(row.id),
                    "scan_date": row.scan_date.isoformat() if row.scan_date else None,
                    "home": row.home_team_name,
                    "away": row.away_team_name,
                    "shadow_summary": summary,
                }
            )

        return {
            "mode": "dry_run_smoke",
            "db_writes": False,
            "external_api_calls": False,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "limit": limit,
            "aggregate": aggregate,
            "fixtures": fixtures_out,
            "note": (
                "Smoke audit V3.1 shadow — nessuna promozione, nessun replay storico completo."
            ),
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke audit V3 vs V3.1 (dry-run)")
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    result = run_smoke(
        date_from=_parse_date(args.date_from),  # type: ignore[arg-type]
        date_to=_parse_date(args.date_to),  # type: ignore[arg-type]
        limit=args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
