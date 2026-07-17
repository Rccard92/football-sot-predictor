"""Audit read-only identità fixture Today vs Fixture locale (Fase 2A.2).

Uso:
  cd backend && python -m scripts.audit_fixture_identity_9510

Richiede DATABASE_URL (o settings app). Se assente, stampa SKIP.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as module from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat()
    return str(v)


def main() -> int:
    if not os.environ.get("DATABASE_URL") and not Path(".env").exists():
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "DATABASE_URL / backend/.env non disponibili in questo ambiente",
                    "hypothesis": {
                        "july_22_sources": [
                            "fixtures.kickoff_at via audit_leakage → cecchino_output.data_quality.leakage_check.target_kickoff",
                            "fixtures.kickoff_at via xG diagnostics → fixture_date_cutoff",
                        ],
                        "today_kickoff_source": "cecchino_today_fixtures.kickoff (discovery API Football)",
                        "root_cause_not_confirmed": (
                            "Senza DB live non si distingue mapping errato vs riprogrammazione vs snapshot stale; "
                            "il codice conferma che il 22/07 non nasce da TodayFixture.kickoff."
                        ),
                        "protection_shipped": [
                            "fixture_identity_consistency su GET today detail",
                            "balance_v5_preview_v1_1 blocked if inconsistent",
                            "apply_minimal_kickoff_realignment / flag_stale_calculation_snapshot",
                        ],
                    },
                    "records_expected": {
                        "cecchino_today_fixture_id": 9510,
                        "local_fixture_id": 562,
                        "provider_fixture_id": 1492291,
                        "match": "Botafogo vs Santos",
                        "today_kickoff_reported": "2026-07-16T22:30:00+00:00",
                        "calc_kickoff_reported": "2026-07-22T20:00:00+00:00",
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.core.database import SessionLocal
    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.models.fixture import Fixture
    from app.models.team import Team

    db: Session = SessionLocal()
    try:
        today = db.get(CecchinoTodayFixture, 9510)
        local = db.get(Fixture, 562) if today and today.local_fixture_id else None
        if today and today.local_fixture_id and local is None:
            local = db.get(Fixture, int(today.local_fixture_id))

        def team_name(tid: int | None) -> str | None:
            if tid is None:
                return None
            t = db.get(Team, int(tid))
            return t.name if t else None

        def dump_today(row: CecchinoTodayFixture | None) -> dict:
            if row is None:
                return {"found": False}
            leak = None
            out = row.cecchino_output_json or {}
            if isinstance(out, dict):
                dq = out.get("data_quality") or {}
                if isinstance(dq, dict):
                    leak = (dq.get("leakage_check") or {}).get("target_kickoff")
            return {
                "found": True,
                "id": row.id,
                "provider_source": row.provider_source,
                "provider_fixture_id": row.provider_fixture_id,
                "local_fixture_id": row.local_fixture_id,
                "competition_id": row.competition_id,
                "home_team_name": row.home_team_name,
                "away_team_name": row.away_team_name,
                "kickoff": _iso(row.kickoff),
                "status": row.fixture_status or row.match_display_status,
                "created_at": _iso(getattr(row, "created_at", None)),
                "updated_at": _iso(getattr(row, "updated_at", None)),
                "cecchino_leakage_target_kickoff": leak,
            }

        def dump_fixture(fx: Fixture | None) -> dict:
            if fx is None:
                return {"found": False}
            return {
                "found": True,
                "id": fx.id,
                "api_fixture_id": fx.api_fixture_id,
                "competition_id": fx.competition_id,
                "home_team_id": fx.home_team_id,
                "home_team_name": team_name(fx.home_team_id),
                "away_team_id": fx.away_team_id,
                "away_team_name": team_name(fx.away_team_id),
                "kickoff_at": _iso(fx.kickoff_at),
                "status": fx.status,
                "created_at": _iso(getattr(fx, "created_at", None)),
                "updated_at": _iso(getattr(fx, "updated_at", None)),
            }

        july22 = []
        if today:
            q = (
                select(Fixture)
                .where(Fixture.kickoff_at >= datetime(2026, 7, 22, 19, 0, tzinfo=timezone.utc))
                .where(Fixture.kickoff_at <= datetime(2026, 7, 22, 21, 0, tzinfo=timezone.utc))
                .limit(20)
            )
            for fx in db.scalars(q).all():
                july22.append(dump_fixture(fx))

        report = {
            "status": "ok",
            "today_9510": dump_today(today),
            "fixture_562": dump_fixture(local),
            "fixtures_around_2026_07_22_20z": july22,
            "provider_vs_api_match": (
                today is not None
                and local is not None
                and int(today.provider_fixture_id) == int(local.api_fixture_id)
            ),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
