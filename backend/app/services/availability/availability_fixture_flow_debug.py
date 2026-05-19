"""Debug flusso indisponibili per singola fixture (fixture API only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture, PlayerAvailability, Season
from app.models.player_availability import SCOPE_FIXTURE_LEVEL
from app.services.availability.availability_debug import build_fixture_availability_debug
from app.services.availability.availability_fixture_scope import load_fixture_availability_buckets
from app.services.availability.availability_parsing import SOURCE_INJURIES


def build_availability_fixture_flow_debug(
    db: Session,
    season_year: int,
    fixture_id: int,
    *,
    api_items: list[dict[str, Any]] | None = None,
    api_error: str | None = None,
) -> dict[str, Any]:
    fx = db.scalar(
        select(Fixture)
        .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
        .where(Fixture.id == int(fixture_id)),
    )
    if fx is None:
        return {
            "status": "error",
            "message": f"Fixture {fixture_id} non trovata",
            "fixture_id": int(fixture_id),
        }

    season_row = db.scalar(select(Season).where(Season.id == int(fx.season_id)))
    if season_row is None or int(season_row.year) != int(season_year):
        return {
            "status": "error",
            "message": f"Fixture {fixture_id} non appartiene alla stagione {season_year}",
            "fixture_id": int(fixture_id),
        }

    api_fx_id = int(fx.api_fixture_id)
    request = f"injuries?fixture={api_fx_id}"
    home = fx.home_team
    away = fx.away_team
    fixture_label = f"{home.name if home else '?'} - {away.name if away else '?'}"

    db_active = list(
        db.scalars(
            select(PlayerAvailability).where(
                PlayerAvailability.season == int(season_year),
                PlayerAvailability.league_id == int(fx.league_id),
                PlayerAvailability.is_active.is_(True),
                PlayerAvailability.api_fixture_id == api_fx_id,
                PlayerAvailability.source == SOURCE_INJURIES,
            ),
        ).all(),
    )
    db_fixture_level = [r for r in db_active if r.record_scope == SCOPE_FIXTURE_LEVEL]

    buckets = load_fixture_availability_buckets(db, int(fixture_id))
    audit = build_fixture_availability_debug(db, int(fixture_id))

    applicable_count = 0
    if buckets:
        applicable_count = len(buckets.applicable)

    diagnosis: list[str] = []
    if api_error:
        diagnosis.append(f"Errore API: {api_error[:300]}")
    if api_items is not None and len(api_items) == 0:
        diagnosis.append("API injuries?fixture= ha restituito 0 record.")
    if api_items and len(api_items) > 0 and len(db_fixture_level) == 0:
        diagnosis.append(
            "API ha restituito record ma il DB non ha fixture_level attivi: eseguire POST availability-upcoming.",
        )
    if applicable_count == 0 and len(db_fixture_level) > 0:
        diagnosis.append(
            "Record DB presenti ma nessuno applicabile in audit: verificare api_team_id e scope.",
        )
    if applicable_count == 0 and len(db_fixture_level) == 0:
        diagnosis.append("Nessun indisponibile fixture-level attivo per questa partita.")

    return {
        "status": "success",
        "season": int(season_year),
        "fixture_id": int(fixture_id),
        "fixture_label": fixture_label,
        "api_fixture_id": api_fx_id,
        "kickoff_at": fx.kickoff_at.isoformat() if hasattr(fx.kickoff_at, "isoformat") else str(fx.kickoff_at),
        "request": request,
        "api_results_count": len(api_items) if api_items is not None else None,
        "api_results_sample": (api_items or [])[:5],
        "db_records_active_fixture_injuries": len(db_active),
        "db_records_fixture_level": len(db_fixture_level),
        "db_records_fixture_level_sample": [
            {
                "player_name": r.player_name,
                "api_player_id": r.api_player_id,
                "api_team_id": r.api_team_id,
                "availability_status": r.availability_status,
                "record_scope": r.record_scope,
            }
            for r in db_fixture_level[:10]
        ],
        "audit_applicable_count": applicable_count,
        "audit": audit,
        "diagnosis": diagnosis,
    }
