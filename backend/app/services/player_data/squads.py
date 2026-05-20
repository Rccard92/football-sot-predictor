from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, PlayerTeamSeason, Team
from app.services.api_football_client import ApiFootballClient
from app.services.ingestion_service import IngestionService
from app.services.player_data.registry import upsert_player_registry

logger = logging.getLogger(__name__)


def _sync_one_team_squad(
    db: Session,
    *,
    team: Team,
    season_year: int,
    league_id: int,
    api: ApiFootballClient,
    now: datetime,
) -> tuple[int, int, int, list[dict[str, Any]]]:
    """Ritorna (players_touched, pts_created, deactivated_count, errors)."""
    players_touched = 0
    pts_created = 0
    errors: list[dict[str, Any]] = []
    seen_api_player_ids: set[int] = set()

    try:
        blocks = api.get_player_squads(int(team.api_team_id))
    except Exception as exc:
        logger.warning(
            "player squads: team_id=%s api_team_id=%s err=%s",
            team.id,
            team.api_team_id,
            exc,
        )
        errors.append({"team_id": team.id, "api_team_id": team.api_team_id, "error": str(exc)})
        return 0, 0, 0, errors

    for block in blocks:
        for pl in block.get("players") or []:
            if not isinstance(pl, dict):
                continue
            try:
                api_pid = int(pl["id"])
            except (KeyError, TypeError, ValueError):
                continue
            seen_api_player_ids.add(api_pid)
            name = str(pl.get("name") or "")
            reg = upsert_player_registry(db, api_player_id=api_pid, name=name)
            players_touched += 1
            pos_raw = pl.get("position") or pl.get("pos")
            position_str = str(pos_raw).strip()[:255] if pos_raw else None

            pts = db.scalar(
                select(PlayerTeamSeason).where(
                    PlayerTeamSeason.season == season_year,
                    PlayerTeamSeason.league_id == league_id,
                    PlayerTeamSeason.api_team_id == team.api_team_id,
                    PlayerTeamSeason.api_player_id == api_pid,
                ),
            )
            if pts is None:
                db.add(
                    PlayerTeamSeason(
                        season=season_year,
                        league_id=league_id,
                        team_id=team.id,
                        api_team_id=int(team.api_team_id),
                        player_id=reg.id,
                        api_player_id=api_pid,
                        position=position_str,
                        is_active=True,
                        last_seen_at=now,
                    ),
                )
                pts_created += 1
            else:
                pts.team_id = team.id
                if position_str:
                    pts.position = position_str
                pts.is_active = True
                pts.last_seen_at = now

    existing = list(
        db.scalars(
            select(PlayerTeamSeason).where(
                PlayerTeamSeason.season == season_year,
                PlayerTeamSeason.league_id == league_id,
                PlayerTeamSeason.api_team_id == int(team.api_team_id),
            ),
        ).all(),
    )
    deactivated = 0
    for row in existing:
        if int(row.api_player_id) not in seen_api_player_ids and row.is_active:
            row.is_active = False
            deactivated += 1

    return players_touched, pts_created, deactivated, errors


def sync_team_squads(
    db: Session,
    season_year: int,
    team_ids: list[int],
    *,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    """Sync rosa API-Sports per un sottoinsieme di squadre (fixture o admin)."""
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, season_year)
    api = client or ApiFootballClient()
    league_id = int(season_row.league_id)
    year = int(season_row.year)

    unique_ids = sorted({int(t) for t in team_ids if t})
    if not unique_ids:
        return {
            "status": "skipped",
            "message": "Nessuna squadra da sincronizzare",
            "teams_considered": 0,
            "players_touched": 0,
            "player_team_season_rows_created": 0,
            "players_deactivated": 0,
            "errors": [],
        }

    teams = list(db.scalars(select(Team).where(Team.id.in_(unique_ids))).all())
    now = datetime.now(timezone.utc)
    players_touched = 0
    pts_created = 0
    deactivated_total = 0
    errors: list[dict[str, Any]] = []

    for team in teams:
        pt, pc, deact, errs = _sync_one_team_squad(
            db,
            team=team,
            season_year=year,
            league_id=league_id,
            api=api,
            now=now,
        )
        players_touched += pt
        pts_created += pc
        deactivated_total += deact
        errors.extend(errs)

    db.commit()
    return {
        "status": "success" if not errors else "partial",
        "season_year": year,
        "league_id": league_id,
        "teams_considered": len(teams),
        "players_touched": players_touched,
        "player_team_season_rows_created": pts_created,
        "players_deactivated": deactivated_total,
        "errors": errors[:50],
    }


def sync_serie_a_player_squads(
    db: Session,
    season_year: int,
    *,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    """Sincronizza rose API (`players/squads`) in `player_registry` + `player_team_seasons`."""
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, season_year)

    home_ids = db.scalars(
        select(Fixture.home_team_id).where(Fixture.season_id == season_row.id),
    ).all()
    away_ids = db.scalars(
        select(Fixture.away_team_id).where(Fixture.season_id == season_row.id),
    ).all()
    team_ids = list(set(home_ids) | set(away_ids))
    if not team_ids:
        return {
            "status": "skipped",
            "message": "Nessuna fixture per la stagione: rose non sincronizzate",
            "teams_considered": 0,
            "players_touched": 0,
            "player_team_season_rows_created": 0,
            "players_deactivated": 0,
            "errors": [],
        }

    return sync_team_squads(db, season_year, team_ids, client=client)
