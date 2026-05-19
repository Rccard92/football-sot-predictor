"""Debug flusso indisponibili per singola fixture (solo DB, nessuna API live)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture, PlayerAvailability, Season
from app.models.player_availability import (
    SCOPE_FIXTURE_LEVEL,
    SCOPE_MANUAL_FIXTURE_LEVEL,
    SCOPE_MANUAL_TEAM_LEVEL,
)
from app.services.availability.availability_fixture_scope import (
    applicable_for_team,
    build_fixture_context,
    exclusion_reason,
    generic_for_team,
    infer_record_scope_from_row,
    load_fixture_availability_buckets,
)
from app.services.availability.availability_league import resolve_serie_a_league_context


def _serialize_row(row: PlayerAvailability, *, team_name: str | None = None) -> dict[str, Any]:
    return {
        "player_name": row.player_name,
        "api_player_id": row.api_player_id,
        "api_team_id": row.api_team_id,
        "team_name": team_name or row.team_name,
        "availability_status": row.availability_status,
        "availability_type": row.availability_type,
        "reason": row.reason,
        "source": row.source,
        "record_scope": infer_record_scope_from_row(row),
        "api_fixture_id": row.api_fixture_id,
        "fixture_id": row.fixture_id,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "fixture_date": row.fixture_date.isoformat() if row.fixture_date else None,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "is_active": row.is_active,
    }


def _team_name_for_row(row: PlayerAvailability, ctx) -> str:
    if row.api_team_id == ctx.api_home_team_id:
        return ctx.home_name
    if row.api_team_id == ctx.api_away_team_id:
        return ctx.away_name
    return row.team_name or "?"


def build_availability_fixture_flow_debug(
    db: Session,
    season_year: int,
    fixture_id: int,
) -> dict[str, Any]:
    try:
        ctx = build_fixture_context(db, int(fixture_id))
        if ctx is None:
            return {
                "status": "error",
                "message": f"Fixture {fixture_id} non trovata o squadre mancanti",
                "fixture_id": int(fixture_id),
                "season": int(season_year),
                "diagnosis": [
                    "Verificare che la fixture esista nel DB e abbia home/away collegati.",
                ],
            }

        if int(ctx.season_year) != int(season_year):
            return {
                "status": "error",
                "message": f"Fixture {fixture_id} non appartiene alla stagione {season_year}",
                "fixture_id": int(fixture_id),
                "season": int(season_year),
                "diagnosis": [f"Stagione fixture: {ctx.season_year}, richiesta: {season_year}"],
            }

        fx = db.scalar(
            select(Fixture)
            .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
            .where(Fixture.id == int(fixture_id)),
        )
        api_fx_id = ctx.api_fixture_id

        try:
            league_ctx = resolve_serie_a_league_context(db, int(season_year))
            api_league_id = league_ctx.api_league_id
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "message": str(exc)[:300],
                "fixture_id": int(fixture_id),
                "season": int(season_year),
                "diagnosis": ["Configurazione lega/API league id mancante."],
            }

        buckets = load_fixture_availability_buckets(db, int(fixture_id))
        if buckets is None:
            return {
                "status": "error",
                "message": "Impossibile classificare record availability",
                "fixture_id": int(fixture_id),
                "diagnosis": [],
            }

        home_applicable = applicable_for_team(
            buckets,
            api_team_id=ctx.api_home_team_id,
            team_id=ctx.home_team_id,
        )
        away_applicable = applicable_for_team(
            buckets,
            api_team_id=ctx.api_away_team_id,
            team_id=ctx.away_team_id,
        )
        records_returned = len(home_applicable) + len(away_applicable)

        home_generic = generic_for_team(
            buckets,
            api_team_id=ctx.api_home_team_id,
            team_id=ctx.home_team_id,
        )
        away_generic = generic_for_team(
            buckets,
            api_team_id=ctx.api_away_team_id,
            team_id=ctx.away_team_id,
        )

        db_by_api_fixture = list(
            db.scalars(
                select(PlayerAvailability).where(
                    PlayerAvailability.season == int(season_year),
                    PlayerAvailability.league_id == ctx.league_id,
                    PlayerAvailability.is_active.is_(True),
                    PlayerAvailability.api_fixture_id == api_fx_id,
                ),
            ).all(),
        )

        db_home_team = list(
            db.scalars(
                select(PlayerAvailability).where(
                    PlayerAvailability.season == int(season_year),
                    PlayerAvailability.league_id == ctx.league_id,
                    PlayerAvailability.is_active.is_(True),
                    PlayerAvailability.api_team_id == ctx.api_home_team_id,
                ),
            ).all(),
        )
        db_away_team = list(
            db.scalars(
                select(PlayerAvailability).where(
                    PlayerAvailability.season == int(season_year),
                    PlayerAvailability.league_id == ctx.league_id,
                    PlayerAvailability.is_active.is_(True),
                    PlayerAvailability.api_team_id == ctx.api_away_team_id,
                ),
            ).all(),
        )

        fixture_level = [
            r for r in buckets.applicable + buckets.generic_not_applied + buckets.excluded
            if infer_record_scope_from_row(r) == SCOPE_FIXTURE_LEVEL
        ]
        manual_fixture = [
            r
            for r in buckets.applicable + buckets.generic_not_applied + buckets.excluded
            if infer_record_scope_from_row(r) == SCOPE_MANUAL_FIXTURE_LEVEL
        ]
        manual_team_valid = [
            r for r in buckets.applicable if infer_record_scope_from_row(r) == SCOPE_MANUAL_TEAM_LEVEL
        ]

        last_fetched = db.scalar(
            select(func.max(PlayerAvailability.fetched_at)).where(
                PlayerAvailability.season == int(season_year),
                PlayerAvailability.league_id == ctx.league_id,
                PlayerAvailability.is_active.is_(True),
                or_(
                    PlayerAvailability.api_fixture_id == api_fx_id,
                    PlayerAvailability.api_team_id.in_([ctx.api_home_team_id, ctx.api_away_team_id]),
                ),
            ),
        )

        excluded_serialized = [
            {
                "player_name": r.player_name,
                "team_name": _team_name_for_row(r, ctx),
                "reason_excluded": exclusion_reason(r, ctx),
                "record_scope": infer_record_scope_from_row(r),
                "source": r.source,
                "api_player_id": r.api_player_id,
                "api_fixture_id": r.api_fixture_id,
            }
            for r in buckets.excluded
        ]

        diagnosis: list[str] = []
        fixture_level_active = [r for r in db_by_api_fixture if r.record_scope == SCOPE_FIXTURE_LEVEL]
        if records_returned == 0 and len(fixture_level_active) == 0:
            diagnosis.append(f"Nessun record fixture-level trovato per api_fixture_id {api_fx_id}.")
        if len(home_generic) + len(away_generic) > 0:
            diagnosis.append(
                f"Sono presenti {len(home_generic) + len(away_generic)} record generici (senza date valide) "
                "non applicati all'audit.",
            )
        if len(excluded_serialized) > 0:
            team_api_excl = sum(1 for e in excluded_serialized if e["reason_excluded"] == "team_level_api_excluded")
            if team_api_excl:
                diagnosis.append(
                    f"{team_api_excl} record team-level da ingestione league/season esclusi "
                    "(usare POST availability-upcoming).",
                )
        if records_returned == 0:
            diagnosis.append(
                "Esegui Admin → Aggiorna indisponibili prossima giornata e verifica records_from_fixture_api.",
            )
        if not diagnosis:
            diagnosis.append("Record applicabili presenti: audit dovrebbe mostrarli.")

        kickoff_str = (
            fx.kickoff_at.isoformat()
            if fx is not None and hasattr(fx.kickoff_at, "isoformat")
            else str(ctx.kickoff)
        )

        return {
            "status": "success",
            "season": int(season_year),
            "fixture": {
                "fixture_id": int(fixture_id),
                "api_fixture_id": api_fx_id,
                "label": f"{ctx.home_name} - {ctx.away_name}",
                "kickoff_at": kickoff_str,
                "status": (fx.status or "") if fx is not None else "",
                "home_team": ctx.home_name,
                "home_team_id": ctx.home_team_id,
                "api_home_team_id": ctx.api_home_team_id,
                "away_team": ctx.away_name,
                "away_team_id": ctx.away_team_id,
                "api_away_team_id": ctx.api_away_team_id,
            },
            "audit_endpoint": {
                "url": f"/api/debug/sot/fixture/{fixture_id}/availability",
                "records_returned": records_returned,
            },
            "api_football_expected_request": {
                "fixture_request": f"injuries?fixture={api_fx_id}",
                "api_league_id": api_league_id,
                "note": (
                    "L'audit partita usa solo record fixture-level o override manuali validi "
                    "per questa fixture. Usa «Controlla API live» per vedere la risposta API senza salvare."
                ),
            },
            "db_checks": {
                "player_availability_total_for_fixture_api_id": len(db_by_api_fixture),
                "player_availability_total_for_home_team": len(db_home_team),
                "player_availability_total_for_away_team": len(db_away_team),
                "fixture_level_records": [_serialize_row(r, team_name=_team_name_for_row(r, ctx)) for r in fixture_level[:20]],
                "manual_fixture_level_records": [
                    _serialize_row(r, team_name=_team_name_for_row(r, ctx)) for r in manual_fixture[:20]
                ],
                "manual_team_level_valid_records": [
                    _serialize_row(r, team_name=_team_name_for_row(r, ctx)) for r in manual_team_valid[:20]
                ],
                "generic_records_not_applied": [
                    _serialize_row(r, team_name=_team_name_for_row(r, ctx))
                    for r in (home_generic + away_generic)[:20]
                ],
            },
            "applicable_records": {
                "home": [_serialize_row(r, team_name=ctx.home_name) for r in home_applicable],
                "away": [_serialize_row(r, team_name=ctx.away_name) for r in away_applicable],
            },
            "excluded_records": excluded_serialized[:50],
            "diagnosis": diagnosis,
            "last_availability_fetched_at": (
                last_fetched.isoformat() if isinstance(last_fetched, datetime) else None
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "message": str(exc)[:500],
            "fixture_id": int(fixture_id),
            "season": int(season_year),
            "diagnosis": ["Errore interno durante il debug availability fixture flow."],
        }
