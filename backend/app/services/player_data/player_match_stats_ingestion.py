"""Ingestion fixture → player_registry, player_team_seasons, player_match_stats (API /fixtures/players)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, PlayerMatchStat, PlayerTeamSeason, Team
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.ingestion_service import IngestionService
from app.services.player_data.fixtures_players_statistics import (
    bump_missing_summary,
    extract_statistics_row_nullable,
)
from app.services.player_data.registry import upsert_player_registry

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _kickoff_past(fixture: Fixture, now: datetime) -> bool:
    ko = fixture.kickoff_at
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    return ko < now


def _is_rate_limit(exc: Exception) -> bool:
    s = str(exc).lower()
    return "429" in s or "too many requests" in s or "rate limit" in s


def ingest_serie_a_player_match_stats(
    db: Session,
    season_year: int,
    *,
    force: bool = False,
    client: ApiFootballClient | None = None,
    competition_id: int | None = None,
    season_id_override: int | None = None,
) -> dict[str, Any]:
    """
    Importa statistiche giocatore per partite finite Serie A.
    Idempotente su player_match_stats (UPSERT per fixture_id + api_team_id + api_player_id).
    """
    logger.info(
        "player_match_stats ingestion start season=%s force=%s competition_id=%s",
        season_year,
        force,
        competition_id,
    )
    ing = IngestionService()
    if season_id_override is not None:
        from app.models import Season

        season_row = db.get(Season, season_id_override)
        if season_row is None:
            return {"status": "error", "message": f"Season id={season_id_override} non trovata"}
    else:
        season_row = ing._serie_a_season_row(db, season_year)
    year = int(season_row.year)
    league_id = int(season_row.league_id)
    api = client or ApiFootballClient()

    now = _utc_now()
    fixture_q = select(Fixture).where(
        Fixture.season_id == season_row.id,
        Fixture.status.in_(FINISHED_STATUSES),
    )
    if competition_id is not None:
        fixture_q = fixture_q.where(Fixture.competition_id == competition_id)
    fixtures = db.scalars(fixture_q.order_by(Fixture.kickoff_at.asc())).all()

    eligible: list[Fixture] = [f for f in fixtures if _kickoff_past(f, now)]
    fixtures_completed = len(eligible)

    fixtures_skipped = 0
    fixtures_processed = 0
    api_calls = 0
    players_upserted = 0
    player_team_seasons_upserted = 0
    player_match_stats_upserted = 0
    missing_fields_summary: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    stopped_rate_limit = False

    for fx in eligible:
        if not force:
            existing = db.scalar(
                select(PlayerMatchStat.id).where(PlayerMatchStat.fixture_id == fx.id).limit(1),
            )
            if existing is not None:
                fixtures_skipped += 1
                continue

        try:
            logger.info(
                "player_match_stats: inizio fixture id=%s api_fixture_id=%s",
                fx.id,
                fx.api_fixture_id,
            )
            groups = api.get_fixture_players(int(fx.api_fixture_id))
        except ApiFootballError as exc:
            logger.warning(
                "player_match_stats API error fixture_id=%s api_fixture_id=%s: %s",
                fx.id,
                fx.api_fixture_id,
                exc,
            )
            if _is_rate_limit(exc):
                stopped_rate_limit = True
                errors.append(
                    {
                        "fixture_id": fx.id,
                        "api_fixture_id": int(fx.api_fixture_id),
                        "error": "Rate limit o 429 da API-Football — ingestion interrotta",
                    },
                )
                break
            errors.append(
                {
                    "fixture_id": fx.id,
                    "api_fixture_id": int(fx.api_fixture_id),
                    "error": str(exc),
                },
            )
            continue
        except Exception as exc:
            logger.exception(
                "player_match_stats unexpected error fixture_id=%s",
                fx.id,
            )
            errors.append(
                {
                    "fixture_id": fx.id,
                    "api_fixture_id": int(fx.api_fixture_id),
                    "error": str(exc),
                },
            )
            continue

        api_calls += 1

        if not groups:
            errors.append(
                {
                    "fixture_id": fx.id,
                    "api_fixture_id": int(fx.api_fixture_id),
                    "error": "API returned empty response",
                },
            )
            db.commit()
            fixtures_processed += 1
            continue

        try:
            for group in groups:
                team_block = group.get("team") or {}
                try:
                    api_team_id = int(team_block["id"])
                except (KeyError, TypeError, ValueError):
                    continue

                team_row = db.scalar(select(Team).where(Team.api_team_id == api_team_id))
                internal_team_id = int(team_row.id) if team_row is not None else None
                if team_row is None:
                    errors.append(
                        {
                            "fixture_id": fx.id,
                            "api_fixture_id": int(fx.api_fixture_id),
                            "api_team_id": api_team_id,
                            "warning": "team_id interno non trovato per api_team_id",
                        },
                    )

                for entry in group.get("players") or []:
                    if not isinstance(entry, dict):
                        continue
                    plobj = entry.get("player") or {}
                    try:
                        api_player_id = int(plobj["id"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    name = str(plobj.get("name") or "")
                    stats_list = entry.get("statistics")
                    if not isinstance(stats_list, list):
                        stats_list = []

                    parsed = extract_statistics_row_nullable(stats_list)
                    bump_missing_summary(missing_fields_summary, parsed)

                    reg = upsert_player_registry(db, api_player_id=api_player_id, name=name)
                    players_upserted += 1

                    pts = db.scalar(
                        select(PlayerTeamSeason).where(
                            PlayerTeamSeason.season == year,
                            PlayerTeamSeason.league_id == league_id,
                            PlayerTeamSeason.api_team_id == api_team_id,
                            PlayerTeamSeason.api_player_id == api_player_id,
                        ),
                    )
                    pos = parsed.get("position")
                    if pts is None:
                        db.add(
                            PlayerTeamSeason(
                                season=year,
                                league_id=league_id,
                                competition_id=competition_id or fx.competition_id,
                                team_id=internal_team_id,
                                api_team_id=api_team_id,
                                player_id=reg.id,
                                api_player_id=api_player_id,
                                position=pos,
                                is_active=True,
                                last_seen_at=now,
                            ),
                        )
                    else:
                        pts.team_id = internal_team_id if internal_team_id is not None else pts.team_id
                        if pos:
                            pts.position = pos
                        pts.last_seen_at = now
                    player_team_seasons_upserted += 1

                    raw_blob: dict[str, Any] = dict(entry) if entry else {}
                    mrow = db.scalar(
                        select(PlayerMatchStat).where(
                            PlayerMatchStat.fixture_id == fx.id,
                            PlayerMatchStat.api_team_id == api_team_id,
                            PlayerMatchStat.api_player_id == api_player_id,
                        ),
                    )
                    common = dict(
                        fixture_id=fx.id,
                        api_fixture_id=int(fx.api_fixture_id),
                        season=year,
                        league_id=league_id,
                        competition_id=competition_id or fx.competition_id,
                        team_id=internal_team_id,
                        api_team_id=api_team_id,
                        player_id=reg.id,
                        api_player_id=api_player_id,
                        minutes=parsed.get("minutes"),
                        position=parsed.get("position"),
                        rating=parsed.get("rating"),
                        substitute=parsed.get("substitute"),
                        shots_total=parsed.get("shots_total"),
                        shots_on=parsed.get("shots_on"),
                        goals_total=parsed.get("goals_total"),
                        goals_assists=parsed.get("goals_assists"),
                        passes_total=parsed.get("passes_total"),
                        passes_key=parsed.get("passes_key"),
                        passes_accuracy=parsed.get("passes_accuracy"),
                        dribbles_attempts=parsed.get("dribbles_attempts"),
                        dribbles_success=parsed.get("dribbles_success"),
                        fouls_drawn=parsed.get("fouls_drawn"),
                        fouls_committed=parsed.get("fouls_committed"),
                        cards_yellow=parsed.get("cards_yellow"),
                        cards_red=parsed.get("cards_red"),
                        penalty_scored=parsed.get("penalty_scored"),
                        penalty_missed=parsed.get("penalty_missed"),
                        penalty_won=parsed.get("penalty_won"),
                        raw_json=raw_blob,
                    )
                    if mrow is None:
                        db.add(PlayerMatchStat(**common))
                    else:
                        for k, v in common.items():
                            setattr(mrow, k, v)
                    player_match_stats_upserted += 1

            db.commit()
            fixtures_processed += 1
            logger.info(
                "player_match_stats fixture done id=%s api_fixture_id=%s",
                fx.id,
                fx.api_fixture_id,
            )
        except Exception as exc:
            db.rollback()
            logger.exception("player_match_stats commit failed fixture_id=%s", fx.id)
            errors.append(
                {
                    "fixture_id": fx.id,
                    "api_fixture_id": int(fx.api_fixture_id),
                    "error": str(exc),
                },
            )

    if stopped_rate_limit:
        status = "partial_success"
    elif errors and fixtures_processed == 0 and api_calls == 0 and fixtures_skipped < fixtures_completed:
        status = "error"
    else:
        status = "success"

    out = {
        "status": status,
        "season": season_year,
        "fixtures_completed": fixtures_completed,
        "fixtures_processed": fixtures_processed,
        "fixtures_skipped": fixtures_skipped,
        "api_calls": api_calls,
        "players_upserted": players_upserted,
        "player_team_seasons_upserted": player_team_seasons_upserted,
        "player_match_stats_upserted": player_match_stats_upserted,
        "missing_fields_summary": missing_fields_summary,
        "errors": errors[:200],
    }
    logger.info(
        "player_match_stats ingestion end status=%s processed=%s skipped=%s api_calls=%s",
        status,
        fixtures_processed,
        fixtures_skipped,
        api_calls,
    )
    return out


def ingest_competition_player_match_stats(
    db: Session,
    competition_id: int,
    *,
    force: bool = False,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    from app.models import Competition

    comp = db.get(Competition, competition_id)
    if comp is None:
        return {"status": "error", "message": f"Competition {competition_id} non trovata"}
    if comp.season_id is None:
        return {"status": "error", "message": "Competition senza season_id: eseguire bootstrap"}
    result = ingest_serie_a_player_match_stats(
        db,
        comp.season,
        force=force,
        client=client,
        competition_id=comp.id,
        season_id_override=comp.season_id,
    )
    result["competition_id"] = comp.id
    return result
