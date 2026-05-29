#!/usr/bin/env python3
"""Backfill competition_id per Serie A italiana esistente."""

from __future__ import annotations

import json
import sys

from app.core.database import SessionLocal
from app.services.competition_backfill_service import CompetitionBackfillService


def main() -> int:
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    db = SessionLocal()
    try:
        svc = CompetitionBackfillService()
        result = svc.backfill_serie_a(db, season_year=season)
        print(json.dumps(result, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
