"""Ingestion indisponibili Serie A (injuries API multi-source → player_availability)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import UPCOMING_EXCLUDED_STATUSES
from app.models import Fixture, PlayerSeasonProfile, Season, Team
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_helpers import select_top_shooter_api_ids
from app.services.availability.availability_league import resolve_serie_a_league_context
from app.services.availability.availability_parsing import parse_injuries_item
from app.services.availability.availability_persist import deactivate_scope, upsert_availability_record
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

AVAILABILITY_HORIZON_DAYS = 7
MAX_FIXTURES_MULTI_SOURCE = 10


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


def _upcoming_fixtures(
    db: Session,
    *,
    season_row: Season,
) -> list[Fixture]:
    now = _utc_now()
    horizon = now + timedelta(days=AVAILABILITY_HORIZON_DAYS)
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
        ko = fx.kickoff_at
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        if now <= ko <= horizon:
            out.append(fx)
    return out[:MAX_FIXTURES_MULTI_SOURCE]


def _dedupe_key(item: dict[str, Any]) -> tuple[Any, ...]:
    pl = item.get("player") if isinstance(item.get("player"), dict) else {}
    tm = item.get("team") if isinstance(item.get("team"), dict) else {}
    fx = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
    pid = pl.get("id")
    tid = tm.get("id")
    fid = fx.get("id")
    reason = item.get("reason") or (pl.get("reason") if isinstance(pl, dict) else None)
    return (pid, tid, fid, str(reason or "")[:64])


def _merge_items(*batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for batch in batches:
        for item in batch:
            if not isinstance(item, dict):
                continue
            key = _dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def _fetch_for_fixture(
    api: ApiFootballClient,
    *,
    api_league_id: int,
    season_year: int,
    fx: Fixture,
) -> tuple[list[dict[str, Any]], int, int]:
    """Ritorna (items merged, calls_by_fixture, calls_by_team)."""
    api_fx = int(fx.api_fixture_id)
    home = fx.home_team
    away = fx.away_team
    batches: list[list[dict[str, Any]]] = []
    calls_fixture = 0
    calls_team = 0

    try:
        batches.append(api.get_injuries_by_fixture(api_fx))
        calls_fixture += 1
    except ApiFootballError as exc:
        logger.warning("injuries by fixture %s: %s", api_fx, exc)

    if home is not None:
        try:
            batches.append(api.get_injuries_by_team(api_league_id, season_year, int(home.api_team_id)))
            calls_team += 1
        except ApiFootballError as exc:
            logger.warning("injuries home team %s: %s", home.api_team_id, exc)
    if away is not None:
        try:
            batches.append(api.get_injuries_by_team(api_league_id, season_year, int(away.api_team_id)))
            calls_team += 1
        except ApiFootballError as exc:
            logger.warning("injuries away team %s: %s", away.api_team_id, exc)

    return _merge_items(*batches), calls_fixture, calls_team


def _item_in_scope(
    item: dict[str, Any],
    *,
    api_fixture_id: int | None,
    api_team_ids: set[int],
    allow_team_level: bool,
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

    if api_tm is not None and api_tm not in api_team_ids:
        return False

    if api_fixture_id is not None and api_fx == api_fixture_id:
        return True

    if allow_team_level and api_tm is not None and api_tm in api_team_ids:
        return True

    return False


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
    ctx = resolve_serie_a_league_context(db, int(season_year))
    league_internal_id = ctx.league_internal_id
    api_league_id = ctx.api_league_id
    api = client or ApiFootballClient()

    target_fixtures: list[Fixture] = []
    scope_fixture_db_ids: list[int] = []
    scope_team_db_ids: list[int] = []
    api_team_ids_scope: set[int] = set()

    if fixture_id is not None:
        fx = db.scalar(
            select(Fixture)
            .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
            .where(
                Fixture.id == int(fixture_id),
                Fixture.season_id == int(season_row.id),
            ),
        )
        if fx is None:
            raise ValueError(f"Fixture {fixture_id} non trovata per stagione {season_year}")
        target_fixtures = [fx]
        scope_fixture_db_ids = [int(fx.id)]
        if fx.home_team:
            api_team_ids_scope.add(int(fx.home_team.api_team_id))
            scope_team_db_ids.append(int(fx.home_team_id))
        if fx.away_team:
            api_team_ids_scope.add(int(fx.away_team.api_team_id))
            if fx.away_team_id not in scope_team_db_ids:
                scope_team_db_ids.append(int(fx.away_team_id))
    elif team_id is not None:
        team = db.scalar(select(Team).where(Team.id == int(team_id)))
        if team is None:
            raise ValueError(f"Team {team_id} non trovato")
        api_team_ids_scope = {int(team.api_team_id)}
        scope_team_db_ids = [int(team.id)]
        target_fixtures = [
            f
            for f in _upcoming_fixtures(db, season_row=season_row)
            if int(f.home_team_id) == int(team_id) or int(f.away_team_id) == int(team_id)
        ]
    else:
        target_fixtures = _upcoming_fixtures(db, season_row=season_row)
        for fx in target_fixtures:
            if fx.home_team:
                api_team_ids_scope.add(int(fx.home_team.api_team_id))
            if fx.away_team:
                api_team_ids_scope.add(int(fx.away_team.api_team_id))

    fixtures_checked = len(target_fixtures)
    teams_checked = len(api_team_ids_scope) or len(
        db.scalars(select(Team).where(Team.league_id == league_internal_id)).all(),
    )

    if force:
        deactivate_scope(
            db,
            season=int(season_year),
            league_id=league_internal_id,
            fixture_ids=scope_fixture_db_ids or None,
            team_ids=scope_team_db_ids or None,
        )

    all_items: list[dict[str, Any]] = []
    api_calls = 0
    api_calls_by_fixture = 0
    api_calls_by_team = 0
    errors: list[dict[str, Any]] = []

    if target_fixtures:
        for fx in target_fixtures:
            try:
                merged, cf, ct = _fetch_for_fixture(
                    api,
                    api_league_id=api_league_id,
                    season_year=int(season_year),
                    fx=fx,
                )
                all_items.extend(merged)
                api_calls_by_fixture += cf
                api_calls_by_team += ct
                api_calls += cf + ct
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "fixture_id": int(fx.id),
                        "api_fixture_id": int(fx.api_fixture_id),
                        "error": "fetch_failed",
                        "message": str(exc)[:500],
                    },
                )
    elif api_team_ids_scope:
        for api_tid in api_team_ids_scope:
            try:
                batch = api.get_injuries_by_team(api_league_id, int(season_year), int(api_tid))
                all_items.extend(batch)
                api_calls_by_team += 1
                api_calls += 1
            except ApiFootballError as exc:
                errors.append({"api_team_id": api_tid, "error": "api_error", "message": str(exc)[:500]})
    else:
        try:
            all_items = api.get_injuries(api_league_id, int(season_year))
            api_calls = 1
        except ApiFootballError as exc:
            return _error_summary(
                season_year,
                fixtures_checked,
                teams_checked,
                [{"error": "api_error", "message": str(exc)[:500]}],
            )

    # Dedupe globale dopo merge multi-fixture
    all_items = _merge_items(all_items)

    matched = 0
    not_matched = 0
    upserted = 0
    records_fixture_level = 0
    records_team_level = 0
    by_record_scope: dict[str, int] = {}
    top_shooters_flagged: list[dict[str, Any]] = []
    top_cache: dict[int, set[int]] = {}

    if fixture_id is not None and target_fixtures:
        single_fx = target_fixtures[0]
        scope_api_fx = int(single_fx.api_fixture_id)
        scope_teams = api_team_ids_scope
    else:
        scope_api_fx = None
        scope_teams = api_team_ids_scope

    for raw in all_items:
        if not isinstance(raw, dict):
            continue

        item_api_fx = None
        fx_block = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
        try:
            if fx_block.get("id") is not None:
                item_api_fx = int(fx_block["id"])
        except (TypeError, ValueError):
            pass

        if target_fixtures:
            in_scope = False
            for fx in target_fixtures:
                teams = set()
                if fx.home_team:
                    teams.add(int(fx.home_team.api_team_id))
                if fx.away_team:
                    teams.add(int(fx.away_team.api_team_id))
                if _item_in_scope(
                    raw,
                    api_fixture_id=int(fx.api_fixture_id),
                    api_team_ids=teams,
                    allow_team_level=True,
                ):
                    in_scope = True
                    break
            if not in_scope:
                continue
        elif scope_teams:
            if not _item_in_scope(
                raw,
                api_fixture_id=scope_api_fx,
                api_team_ids=scope_teams,
                allow_team_level=True,
            ):
                continue
        elif api_team_ids_scope:
            if not _item_in_scope(
                raw,
                api_fixture_id=None,
                api_team_ids=api_team_ids_scope,
                allow_team_level=True,
            ):
                continue

        parsed = parse_injuries_item(raw)
        if parsed is None:
            continue
        try:
            _row, reg_ok, _created = upsert_availability_record(
                db,
                season=int(season_year),
                league_id=league_internal_id,
                parsed=parsed,
            )
            sc = getattr(_row, "record_scope", None) or (
                "fixture_level" if parsed.api_fixture_id else "team_level"
            )
            by_record_scope[sc] = by_record_scope.get(sc, 0) + 1
            upserted += 1
            if parsed.api_fixture_id is not None:
                records_fixture_level += 1
            else:
                records_team_level += 1
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
                        league_id=league_internal_id,
                        api_team_id=at,
                    )
                    top_cache[at] = set(select_top_shooter_api_ids(pmap))
                if int(parsed.api_player_id) in top_cache[at]:
                    prof = _profile_map_for_team(
                        db,
                        season_year=int(season_year),
                        league_id=league_internal_id,
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
        "league_internal_id": league_internal_id,
        "api_league_id": api_league_id,
        "fixtures_checked": fixtures_checked,
        "teams_checked": teams_checked,
        "api_calls": api_calls,
        "api_calls_by_fixture": api_calls_by_fixture,
        "api_calls_by_team": api_calls_by_team,
        "availability_records_upserted": upserted,
        "records_fixture_level": records_fixture_level,
        "records_team_level": records_team_level,
        "players_matched_to_registry": matched,
        "players_not_matched_to_registry": not_matched,
        "top_shooters_flagged": top_shooters_flagged,
        "by_record_scope": by_record_scope,
        "errors": errors,
    }


def _error_summary(
    season_year: int,
    fixtures_checked: int,
    teams_checked: int,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "error",
        "season": int(season_year),
        "fixtures_checked": fixtures_checked,
        "teams_checked": teams_checked,
        "api_calls": 0,
        "api_calls_by_fixture": 0,
        "api_calls_by_team": 0,
        "availability_records_upserted": 0,
        "records_fixture_level": 0,
        "records_team_level": 0,
        "players_matched_to_registry": 0,
        "players_not_matched_to_registry": 0,
        "top_shooters_flagged": [],
        "errors": errors,
    }
