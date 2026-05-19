"""Ingestion operativa indisponibili: solo injuries?fixture= per partite upcoming."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import UPCOMING_EXCLUDED_STATUSES
from app.models import Fixture, Season
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_league import resolve_serie_a_league_context
from app.services.availability.availability_parsing import parse_injuries_item
from app.services.availability.availability_persist import (
    deactivate_fixture_injuries,
    upsert_fixture_injury_record,
)
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

DEFAULT_DAYS_AHEAD = 14
MAX_UPCOMING_FIXTURES = 30


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _kickoff_aware(ko: datetime) -> datetime:
    if ko.tzinfo is None:
        return ko.replace(tzinfo=timezone.utc)
    return ko


def _upcoming_fixtures(
    db: Session,
    *,
    season_row: Season,
    days_ahead: int,
    fixture_id: int | None = None,
) -> list[Fixture]:
    now = _utc_now()
    horizon = now + timedelta(days=int(days_ahead))
    if fixture_id is not None:
        fx = db.scalar(
            select(Fixture)
            .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
            .where(Fixture.id == int(fixture_id), Fixture.season_id == int(season_row.id)),
        )
        return [fx] if fx is not None else []

    out: list[Fixture] = []
    fixtures = db.scalars(
        select(Fixture)
        .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
        .where(Fixture.season_id == int(season_row.id))
        .order_by(Fixture.kickoff_at.asc()),
    ).all()
    for fx in fixtures:
        st = (fx.status or "").strip().upper()
        if st in UPCOMING_EXCLUDED_STATUSES:
            continue
        ko = _kickoff_aware(fx.kickoff_at)
        if now <= ko <= horizon:
            out.append(fx)
    return out[:MAX_UPCOMING_FIXTURES]


def _fixture_label(fx: Fixture) -> str:
    home = fx.home_team.name if fx.home_team else "?"
    away = fx.away_team.name if fx.away_team else "?"
    return f"{home} - {away}"


def ingest_serie_a_availability_upcoming(
    db: Session,
    season_year: int,
    *,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    force: bool = False,
    fixture_id: int | None = None,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, int(season_year))
    ctx = resolve_serie_a_league_context(db, int(season_year))
    league_internal_id = ctx.league_internal_id
    api = client or ApiFootballClient()

    target = _upcoming_fixtures(
        db,
        season_row=season_row,
        days_ahead=int(days_ahead),
        fixture_id=fixture_id,
    )
    if not target:
        return {
            "status": "success",
            "season": int(season_year),
            "fixtures_checked": 0,
            "api_calls": 0,
            "records_from_fixture_api": 0,
            "records_saved": 0,
            "fixtures_with_availability": [],
            "fixtures_without_availability": [],
            "errors": [],
            "message": "Nessuna fixture upcoming nel periodo selezionato.",
        }

    api_calls = 0
    records_from_api = 0
    records_saved = 0
    with_availability: list[dict[str, Any]] = []
    without_availability: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    fetched_at = _utc_now()

    for fx in target:
        api_fx_id = int(fx.api_fixture_id)
        label = _fixture_label(fx)
        try:
            deactivate_fixture_injuries(
                db,
                season=int(season_year),
                league_id=league_internal_id,
                api_fixture_id=api_fx_id,
            )

            items = api.get_injuries_by_fixture(api_fx_id)
            api_calls += 1
            records_from_api += len(items)

            saved_this = 0
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                parsed = parse_injuries_item(raw)
                if parsed is None or parsed.api_player_id is None:
                    continue
                try:
                    upsert_fixture_injury_record(
                        db,
                        fx=fx,
                        season_year=int(season_year),
                        league_internal_id=league_internal_id,
                        parsed=parsed,
                        fetched_at=fetched_at,
                    )
                    saved_this += 1
                    records_saved += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "api_player_id": parsed.api_player_id,
                            "error": "persist_failed",
                            "message": str(exc)[:300],
                        },
                    )

            entry = {
                "fixture_id": int(fx.id),
                "fixture": label,
                "api_fixture_id": api_fx_id,
                "records_saved": saved_this,
            }
            if saved_this > 0:
                with_availability.append(entry)
            else:
                without_availability.append(entry)
        except ApiFootballError as exc:
            api_calls += 1
            errors.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": api_fx_id,
                    "error": "api_error",
                    "message": str(exc)[:500],
                },
            )
            without_availability.append(
                {
                    "fixture_id": int(fx.id),
                    "fixture": label,
                    "api_fixture_id": api_fx_id,
                    "records_saved": 0,
                },
            )

    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {
            "status": "error",
            "season": int(season_year),
            "fixtures_checked": len(target),
            "api_calls": api_calls,
            "records_from_fixture_api": records_from_api,
            "records_saved": 0,
            "fixtures_with_availability": with_availability,
            "fixtures_without_availability": without_availability,
            "errors": errors + [{"error": "commit_failed", "message": str(exc)[:500]}],
        }

    status = "success"
    if errors and records_saved > 0:
        status = "partial_success"
    elif errors and records_saved == 0:
        status = "partial_success"

    return {
        "status": status,
        "season": int(season_year),
        "league_internal_id": league_internal_id,
        "api_league_id": ctx.api_league_id,
        "days_ahead": int(days_ahead),
        "force": bool(force),
        "fixtures_checked": len(target),
        "api_calls": api_calls,
        "records_from_fixture_api": records_from_api,
        "records_saved": records_saved,
        "fixtures_with_availability": with_availability,
        "fixtures_without_availability": without_availability,
        "errors": errors,
    }
