"""Ingestion indisponibili Serie A (injuries API → player_availability)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import UPCOMING_EXCLUDED_STATUSES
from app.models import Fixture, PlayerSeasonProfile, Season, Team
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_helpers import select_top_shooter_api_ids
from app.services.availability.availability_parsing import parse_injuries_item
from app.services.availability.availability_persist import deactivate_scope, upsert_availability_record
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

AVAILABILITY_HORIZON_DAYS = 7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _profile_map_for_team(
    db: Session,
    *,
    season_year: int,
    league_id: int,
    api_team_id: int,
) -> dict[int, PlayerSeasonProfile]:
    rows = db.scalars(
        select(PlayerSeasonProfile).where(
            PlayerSeasonProfile.season == int(season_year),
            PlayerSeasonProfile.league_id == int(league_id),
            PlayerSeasonProfile.api_team_id == int(api_team_id),
        ),
    ).all()
    return {int(p.api_player_id): p for p in rows}


def _upcoming_fixture_api_ids(
    db: Session,
    *,
    season_row: Season,
) -> set[int]:
    now = _utc_now()
    horizon = now + timedelta(days=AVAILABILITY_HORIZON_DAYS)
    api_ids: set[int] = set()
    fixtures = db.scalars(
        select(Fixture).where(Fixture.season_id == int(season_row.id)).order_by(Fixture.kickoff_at.asc()),
    ).all()
    for fx in fixtures:
        st = (fx.status or "").strip().upper()
        if st in UPCOMING_EXCLUDED_STATUSES:
            continue
        ko = fx.kickoff_at
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        if now <= ko <= horizon:
            api_ids.add(int(fx.api_fixture_id))
    return api_ids


def _item_in_scope(
    item: dict[str, Any],
    *,
    api_fixture_ids: set[int] | None,
    api_team_ids: set[int] | None,
    single_api_fixture_id: int | None,
) -> bool:
    fx = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
    api_fx = None
    try:
        if fx.get("id") is not None:
            api_fx = int(fx["id"])
    except (TypeError, ValueError):
        pass

    tm = item.get("team") if isinstance(item.get("team"), dict) else {}
    api_tm = None
    try:
        if tm.get("id") is not None:
            api_tm = int(tm["id"])
    except (TypeError, ValueError):
        pass

    if single_api_fixture_id is not None:
        return api_fx == single_api_fixture_id

    if api_team_ids is not None and api_tm is not None and api_tm not in api_team_ids:
        return False

    if api_fixture_ids is not None:
        if api_fx is not None:
            return api_fx in api_fixture_ids
        return False

    return True


def ingest_serie_a_availability(
    db: Session,
    season_year: int,
    *,
    fixture_id: int | None = None,
    team_id: int | None = None,
    force: bool = False,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, int(season_year))
    league_id = int(season_row.league_id)
    api = client or ApiFootballClient()

    api_fixture_ids: set[int] | None = None
    api_team_ids: set[int] | None = None
    single_api_fixture_id: int | None = None
    scope_fixture_db_ids: list[int] = []
    scope_team_db_ids: list[int] = []
    fixtures_checked = 0
    teams_checked = 0

    if fixture_id is not None:
        fx = db.scalar(
            select(Fixture).where(
                Fixture.id == int(fixture_id),
                Fixture.season_id == int(season_row.id),
            ),
        )
        if fx is None:
            raise ValueError(f"Fixture {fixture_id} non trovata per stagione {season_year}")
        single_api_fixture_id = int(fx.api_fixture_id)
        scope_fixture_db_ids = [int(fx.id)]
        fixtures_checked = 1
        teams_checked = 2
    elif team_id is not None:
        team = db.scalar(select(Team).where(Team.id == int(team_id)))
        if team is None:
            raise ValueError(f"Team {team_id} non trovato")
        api_team_ids = {int(team.api_team_id)}
        scope_team_db_ids = [int(team.id)]
        teams_checked = 1
        api_fixture_ids = _upcoming_fixture_api_ids(db, season_row=season_row)
        fixtures_checked = len(api_fixture_ids)
    else:
        api_fixture_ids = _upcoming_fixture_api_ids(db, season_row=season_row)
        fixtures_checked = len(api_fixture_ids)
        team_rows = db.scalars(
            select(Team).where(Team.league_id == league_id),
        ).all()
        teams_checked = len(team_rows)

    if force:
        deactivate_scope(
            db,
            season=int(season_year),
            league_id=league_id,
            fixture_ids=scope_fixture_db_ids or None,
            team_ids=scope_team_db_ids or None,
        )

    api_calls = 0
    errors: list[dict[str, Any]] = []
    try:
        items = api.get_injuries(league_id, int(season_year))
        api_calls = 1
    except ApiFootballError as exc:
        return {
            "status": "error",
            "season": int(season_year),
            "fixtures_checked": fixtures_checked,
            "teams_checked": teams_checked,
            "api_calls": 0,
            "availability_records_upserted": 0,
            "players_matched_to_registry": 0,
            "players_not_matched_to_registry": 0,
            "top_shooters_flagged": [],
            "errors": [{"error": "api_error", "message": str(exc)[:500]}],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "season": int(season_year),
            "fixtures_checked": fixtures_checked,
            "teams_checked": teams_checked,
            "api_calls": 0,
            "availability_records_upserted": 0,
            "players_matched_to_registry": 0,
            "players_not_matched_to_registry": 0,
            "top_shooters_flagged": [],
            "errors": [{"error": "unexpected_error", "message": str(exc)[:500]}],
        }

    if not isinstance(items, list):
        items = []

    matched = 0
    not_matched = 0
    upserted = 0
    top_shooters_flagged: list[dict[str, Any]] = []
    top_cache: dict[int, set[int]] = {}

    for raw in items:
        if not isinstance(raw, dict):
            continue
        if not _item_in_scope(
            raw,
            api_fixture_ids=api_fixture_ids,
            api_team_ids=api_team_ids,
            single_api_fixture_id=single_api_fixture_id,
        ):
            continue
        parsed = parse_injuries_item(raw)
        if parsed is None:
            continue
        try:
            _row, reg_ok = upsert_availability_record(
                db,
                season=int(season_year),
                league_id=league_id,
                parsed=parsed,
            )
            upserted += 1
            if reg_ok:
                matched += 1
            else:
                not_matched += 1

            if parsed.api_player_id is not None and parsed.api_team_id is not None:
                at = int(parsed.api_team_id)
                if at not in top_cache:
                    pmap = _profile_map_for_team(
                        db,
                        season_year=int(season_year),
                        league_id=league_id,
                        api_team_id=at,
                    )
                    top_cache[at] = set(select_top_shooter_api_ids(pmap))
                if int(parsed.api_player_id) in top_cache[at]:
                    prof = _profile_map_for_team(
                        db,
                        season_year=int(season_year),
                        league_id=league_id,
                        api_team_id=at,
                    ).get(int(parsed.api_player_id))
                    top_shooters_flagged.append(
                        {
                            "player_name": parsed.player_name,
                            "team_name": parsed.team_name,
                            "api_player_id": parsed.api_player_id,
                            "reason": parsed.reason,
                            "availability_status": parsed.availability_status,
                            "shooting_impact_score": (
                                float(prof.shooting_impact_score)
                                if prof is not None and prof.shooting_impact_score is not None
                                else None
                            ),
                        },
                    )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "api_player_id": parsed.api_player_id if parsed else None,
                    "error": "persist_failed",
                    "message": str(exc)[:500],
                },
            )

    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        errors.append({"error": "commit_failed", "message": str(exc)[:500]})

    status = "success"
    if errors:
        status = "partial_success" if upserted > 0 else "partial_success"

    return {
        "status": status,
        "season": int(season_year),
        "fixtures_checked": fixtures_checked,
        "teams_checked": teams_checked,
        "api_calls": api_calls,
        "availability_records_upserted": upserted,
        "players_matched_to_registry": matched,
        "players_not_matched_to_registry": not_matched,
        "top_shooters_flagged": top_shooters_flagged,
        "errors": errors,
    }
