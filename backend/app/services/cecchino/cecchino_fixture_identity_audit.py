"""Audit read-only identità fixture Today ↔ Fixture locale (Fase 2A.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.models.team import Team
from app.services.cecchino.cecchino_expected_goal_engine_diagnostics import (
    build_expected_goal_engine_diagnostics_for_today_row,
)
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_fixture_identity_consistency,
)
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = ensure_datetime_utc(value, field_name="audit.dt")
        return safe_isoformat(dt, field_name="audit.dt") if dt else None
    return str(value)


def _team_dump(db: Session, team_id: int | None) -> dict[str, Any] | None:
    if team_id is None:
        return None
    t = db.get(Team, int(team_id))
    if t is None:
        return None
    return {"id": int(t.id), "api_team_id": int(t.api_team_id), "name": t.name}


def _competition_dump(db: Session, competition_id: int | None) -> dict[str, Any] | None:
    if competition_id is None:
        return None
    c = db.get(Competition, int(competition_id))
    if c is None:
        return {"id": int(competition_id), "found": False}
    return {
        "id": int(c.id),
        "name": getattr(c, "name", None),
        "country": getattr(c, "country", None),
    }


def _dump_today(row: CecchinoTodayFixture) -> dict[str, Any]:
    leak = None
    out = row.cecchino_output_json or {}
    if isinstance(out, dict):
        dq = out.get("data_quality") or {}
        if isinstance(dq, dict):
            leak = (dq.get("leakage_check") or {}).get("target_kickoff")
    return {
        "id": int(row.id),
        "provider_source": row.provider_source,
        "provider_fixture_id": int(row.provider_fixture_id),
        "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
        "competition_id": int(row.competition_id) if row.competition_id else None,
        "country_name": row.country_name,
        "league_name": row.league_name,
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
        "kickoff": _iso(row.kickoff),
        "fixture_status": row.fixture_status,
        "match_display_status": row.match_display_status,
        "goals_home": row.goals_home,
        "goals_away": row.goals_away,
        "score_fulltime_home": getattr(row, "score_fulltime_home", None),
        "score_fulltime_away": getattr(row, "score_fulltime_away", None),
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        "eligibility_status": row.eligibility_status,
        "created_at": _iso(getattr(row, "created_at", None)),
        "updated_at": _iso(getattr(row, "updated_at", None)),
        "leakage_target_kickoff": str(leak) if leak else None,
        "warnings_json": list(row.warnings_json or []),
    }


def _dump_fixture(db: Session, fx: Fixture) -> dict[str, Any]:
    return {
        "id": int(fx.id),
        "api_fixture_id": int(fx.api_fixture_id),
        "competition_id": int(fx.competition_id) if fx.competition_id else None,
        "home_team": _team_dump(db, fx.home_team_id),
        "away_team": _team_dump(db, fx.away_team_id),
        "kickoff_at": _iso(fx.kickoff_at),
        "status": fx.status,
        "status_long": fx.status_long,
        "goals_home": fx.goals_home,
        "goals_away": fx.goals_away,
        "created_at": _iso(getattr(fx, "created_at", None)),
        "updated_at": _iso(getattr(fx, "updated_at", None)),
    }


def build_fixture_identity_audit(db: Session, today_fixture_id: int) -> dict[str, Any]:
    """Audit read-only: nessuna scrittura DB."""
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {
            "status": "not_found",
            "message": f"CecchinoTodayFixture {today_fixture_id} non trovata",
        }

    local: Fixture | None = None
    if row.local_fixture_id:
        local = db.get(Fixture, int(row.local_fixture_id))

    local_home_name = None
    local_away_name = None
    if local is not None:
        ht = db.get(Team, int(local.home_team_id)) if local.home_team_id else None
        at = db.get(Team, int(local.away_team_id)) if local.away_team_id else None
        local_home_name = ht.name if ht else None
        local_away_name = at.name if at else None

    diagnostics = build_expected_goal_engine_diagnostics_for_today_row(db, row)
    consistency = build_fixture_identity_consistency(
        today_row=row,
        local_fixture=local,
        cecchino_output=row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else None,
        expected_goal_diagnostics=diagnostics if isinstance(diagnostics, dict) else None,
        local_home_team_name=local_home_name,
        local_away_team_name=local_away_name,
    )

    provider_id = int(row.provider_fixture_id)
    dup_today = db.scalars(
        select(CecchinoTodayFixture).where(CecchinoTodayFixture.provider_fixture_id == provider_id)
    ).all()
    dup_fixtures = db.scalars(select(Fixture).where(Fixture.api_fixture_id == provider_id)).all()

    # Vicini al 22 luglio (utile per 9510) senza assumere root cause
    july22 = datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)
    window_fixtures: list[dict[str, Any]] = []
    if local is not None:
        near = db.scalars(
            select(Fixture).where(
                Fixture.kickoff_at >= july22 - timedelta(hours=12),
                Fixture.kickoff_at <= july22 + timedelta(hours=12),
                Fixture.home_team_id == local.home_team_id,
                Fixture.away_team_id == local.away_team_id,
            )
        ).all()
        window_fixtures = [_dump_fixture(db, f) for f in near]

    xg_cutoff = None
    if isinstance(diagnostics, dict):
        profiles = diagnostics.get("xg_profiles") or {}
        if isinstance(profiles, dict):
            anti = profiles.get("anti_leakage") or {}
            if isinstance(anti, dict):
                xg_cutoff = anti.get("fixture_date_cutoff")

    return {
        "status": "ok",
        "read_only": True,
        "today_fixture": _dump_today(row),
        "local_fixture": _dump_fixture(db, local) if local else None,
        "competition": _competition_dump(db, row.competition_id),
        "calculation_snapshot": {
            "target_kickoff": consistency.get("calculation_target_kickoff"),
            "xg_cutoff": str(xg_cutoff) if xg_cutoff else consistency.get("xg_cutoff"),
        },
        "duplicates": {
            "today_rows_same_provider_fixture_id": [
                {"id": int(r.id), "scan_date": r.scan_date.isoformat() if r.scan_date else None, "kickoff": _iso(r.kickoff)}
                for r in dup_today
            ],
            "fixtures_same_api_fixture_id": [
                {"id": int(f.id), "kickoff_at": _iso(f.kickoff_at), "status": f.status}
                for f in dup_fixtures
            ],
            "fixtures_near_2026_07_22_same_teams": window_fixtures,
        },
        "fixture_identity_consistency": consistency,
        "case_hint": {
            "note": (
                "Non scegliere Caso A/B senza confrontare questi raw. "
                "A: Today 16/07+FT+score corretti, Local 22/07 errato. "
                "B: Local/calc 22/07 corretti, Today FT/score stale."
            ),
        },
    }
