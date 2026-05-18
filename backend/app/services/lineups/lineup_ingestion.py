"""Ingestion formazioni ufficiali Serie A (fixtures/lineups)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES, UPCOMING_EXCLUDED_STATUSES
from app.models import Fixture, FixtureLineup, Season, Team
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.ingestion_service import IngestionService
from app.services.lineups.lineup_parsing import block_has_official_lineup
from app.services.lineups.lineup_persist import upsert_lineup_from_api_block

logger = logging.getLogger(__name__)

MAX_FIXTURES_PER_RUN = 30
RECENT_FINISHED_LOOKBACK_DAYS = 7
RECENT_FINISHED_CAP = 20
LINEUP_HORIZON_HOURS = 48


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fixture_has_both_lineups_available(db: Session, fixture_id: int) -> bool:
    n = db.scalar(
        select(func.count())
        .select_from(FixtureLineup)
        .where(
            FixtureLineup.fixture_id == int(fixture_id),
            FixtureLineup.is_available.is_(True),
            FixtureLineup.fetched_at.isnot(None),
        ),
    )
    return int(n or 0) >= 2


def _select_fixtures_for_ingestion(
    db: Session,
    *,
    season_row: Season,
    fixture_id: int | None,
) -> list[Fixture]:
    if fixture_id is not None:
        fx = db.scalar(
            select(Fixture).where(
                Fixture.id == int(fixture_id),
                Fixture.season_id == int(season_row.id),
            ),
        )
        return [fx] if fx is not None else []

    now = _utc_now()
    horizon = now + timedelta(hours=LINEUP_HORIZON_HOURS)
    lookback = now - timedelta(days=RECENT_FINISHED_LOOKBACK_DAYS)

    all_fx = db.scalars(
        select(Fixture)
        .where(Fixture.season_id == int(season_row.id))
        .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
    ).all()

    selected: list[Fixture] = []
    recent_finished_candidates: list[Fixture] = []

    for f in all_fx:
        st = (f.status or "").strip().upper()
        if st in UPCOMING_EXCLUDED_STATUSES:
            continue
        ko = f.kickoff_at
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)

        if st not in FINISHED_STATUSES:
            if now <= ko <= horizon:
                selected.append(f)
            elif ko < now:
                selected.append(f)
            continue

        if ko >= lookback and not _fixture_has_both_lineups_available(db, int(f.id)):
            recent_finished_candidates.append(f)

    selected.extend(recent_finished_candidates[:RECENT_FINISHED_CAP])
    selected.sort(key=lambda x: (x.kickoff_at, int(x.id)))
    seen: set[int] = set()
    out: list[Fixture] = []
    for f in selected:
        if int(f.id) in seen:
            continue
        seen.add(int(f.id))
        out.append(f)
        if len(out) >= MAX_FIXTURES_PER_RUN:
            break
    return out


def ingest_serie_a_lineups(
    db: Session,
    season_year: int,
    *,
    fixture_id: int | None = None,
    force: bool = False,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, int(season_year))
    api = client or ApiFootballClient()

    fixtures = _select_fixtures_for_ingestion(db, season_row=season_row, fixture_id=fixture_id)
    fixtures_checked = len(fixtures)
    fixtures_with_lineups = 0
    fixtures_without_lineups = 0
    lineups_upserted = 0
    lineup_players_upserted = 0
    not_available_yet: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for fx in fixtures:
        if not force and _fixture_has_both_lineups_available(db, int(fx.id)):
            continue

        try:
            blocks = api.get_fixture_lineups(int(fx.api_fixture_id))
        except ApiFootballError as exc:
            errors.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": int(fx.api_fixture_id),
                    "error": "api_error",
                    "message": str(exc)[:500],
                },
            )
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": int(fx.api_fixture_id),
                    "error": "unexpected_error",
                    "message": str(exc)[:500],
                },
            )
            continue

        if not blocks or not any(isinstance(b, dict) and block_has_official_lineup(b) for b in blocks):
            fixtures_without_lineups += 1
            not_available_yet.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": int(fx.api_fixture_id),
                    "message": "Lineups non ancora disponibili da API-Football",
                },
            )
            continue

        teams_saved = 0
        players_n = 0
        for block in blocks:
            if not isinstance(block, dict) or not block_has_official_lineup(block):
                continue
            team_block = block.get("team") or {}
            try:
                team_api = int(team_block["id"])
            except (KeyError, TypeError, ValueError):
                continue
            team = db.scalar(select(Team).where(Team.api_team_id == team_api))
            if team is None:
                continue
            if int(team.id) not in (int(fx.home_team_id), int(fx.away_team_id)):
                continue
            try:
                _row, pn = upsert_lineup_from_api_block(
                    db,
                    fixture=fx,
                    season_row=season_row,
                    team=team,
                    block=block,
                )
                if _row is not None:
                    lineups_upserted += 1
                    players_n += pn
                    teams_saved += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "fixture_id": int(fx.id),
                        "api_fixture_id": int(fx.api_fixture_id),
                        "api_team_id": team_api,
                        "error": "persist_failed",
                        "message": str(exc)[:500],
                    },
                )

        if teams_saved > 0:
            fixtures_with_lineups += 1
            lineup_players_upserted += players_n
            try:
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(
                    {
                        "fixture_id": int(fx.id),
                        "api_fixture_id": int(fx.api_fixture_id),
                        "error": "commit_failed",
                        "message": str(exc)[:500],
                    },
                )
        else:
            fixtures_without_lineups += 1
            not_available_yet.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": int(fx.api_fixture_id),
                    "message": "Lineups non ancora disponibili da API-Football",
                },
            )

    status = "success"
    if errors and (fixtures_with_lineups > 0 or fixtures_without_lineups > 0):
        status = "partial_success"
    elif errors and fixtures_with_lineups == 0:
        status = "partial_success"

    return {
        "status": status,
        "season": int(season_year),
        "fixtures_checked": fixtures_checked,
        "fixtures_with_lineups": fixtures_with_lineups,
        "fixtures_without_lineups": fixtures_without_lineups,
        "lineups_upserted": lineups_upserted,
        "lineup_players_upserted": lineup_players_upserted,
        "not_available_yet": not_available_yet,
        "errors": errors,
    }
