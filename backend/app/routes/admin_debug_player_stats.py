"""Diagnostica sola lettura su fixture_player_stats (stagione Serie A)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Fixture, FixturePlayerStat, Player, Team
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/debug/player-stats", tags=["admin-debug-player-stats"])


def _statistics_snippet(raw: dict[str, Any] | None) -> Any:
    if not raw or not isinstance(raw, dict):
        return None
    stats = raw.get("statistics")
    if stats is not None:
        return stats
    return None


@router.get("/serie-a/{season}/summary", response_model=None)
def debug_player_stats_summary(season: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    ing = IngestionService()
    try:
        season_row = ing._serie_a_season_row(db, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    season_f = Fixture.season_id == season_row.id

    try:
        rows_total = int(
            db.scalar(
                select(func.count())
                .select_from(FixturePlayerStat)
                .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
                .where(season_f),
            )
            or 0,
        )
        rows_with_minutes = int(
            db.scalar(
                select(func.count())
                .select_from(FixturePlayerStat)
                .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
                .where(season_f, FixturePlayerStat.minutes.isnot(None), FixturePlayerStat.minutes > 0),
            )
            or 0,
        )
        rows_sht = int(
            db.scalar(
                select(func.count())
                .select_from(FixturePlayerStat)
                .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
                .where(season_f, FixturePlayerStat.shots_total.isnot(None), FixturePlayerStat.shots_total > 0),
            )
            or 0,
        )
        rows_sot = int(
            db.scalar(
                select(func.count())
                .select_from(FixturePlayerStat)
                .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
                .where(
                    season_f,
                    FixturePlayerStat.shots_on_target.isnot(None),
                    FixturePlayerStat.shots_on_target > 0,
                ),
            )
            or 0,
        )
        sum_sht = int(
            db.scalar(
                select(func.coalesce(func.sum(FixturePlayerStat.shots_total), 0))
                .select_from(FixturePlayerStat)
                .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
                .where(season_f),
            )
            or 0,
        )
        sum_sot = int(
            db.scalar(
                select(func.coalesce(func.sum(FixturePlayerStat.shots_on_target), 0))
                .select_from(FixturePlayerStat)
                .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
                .where(season_f),
            )
            or 0,
        )
        max_sht = db.scalar(
            select(func.max(FixturePlayerStat.shots_total))
            .select_from(FixturePlayerStat)
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(season_f),
        )
        max_sot = db.scalar(
            select(func.max(FixturePlayerStat.shots_on_target))
            .select_from(FixturePlayerStat)
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(season_f),
        )

        sample_sot_rows = db.execute(
            select(
                FixturePlayerStat.fixture_id,
                FixturePlayerStat.player_id,
                FixturePlayerStat.minutes,
                FixturePlayerStat.shots_total,
                FixturePlayerStat.shots_on_target,
            )
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(
                Fixture.season_id == season_row.id,
                FixturePlayerStat.shots_on_target.isnot(None),
                FixturePlayerStat.shots_on_target > 0,
            )
            .limit(5),
        ).all()

        sample_raw = db.scalars(
            select(FixturePlayerStat)
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(Fixture.season_id == season_row.id)
            .limit(3),
        ).all()
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("debug_player_stats_summary: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc

    return {
        "season": season,
        "rows_total": rows_total,
        "rows_with_minutes": rows_with_minutes,
        "rows_with_shots_total_gt_0": rows_sht,
        "rows_with_shots_on_target_gt_0": rows_sot,
        "sum_shots_total": sum_sht,
        "sum_shots_on_target": sum_sot,
        "max_shots_total": int(max_sht) if max_sht is not None else 0,
        "max_shots_on_target": int(max_sot) if max_sot is not None else 0,
        "sample_rows_with_sot": [
            {
                "fixture_id": r.fixture_id,
                "player_id": r.player_id,
                "minutes": r.minutes,
                "shots_total": r.shots_total,
                "shots_on_target": r.shots_on_target,
            }
            for r in sample_sot_rows
        ],
        "sample_rows_raw_json": [
            {
                "fixture_id": row.fixture_id,
                "player_id": row.player_id,
                "statistics": _statistics_snippet(row.raw_json if isinstance(row.raw_json, dict) else None),
            }
            for row in sample_raw
        ],
    }


@router.get("/serie-a/{season}/sample", response_model=None)
def debug_player_stats_sample(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=200),
    only_with_shots: bool = Query(False),
) -> dict[str, Any]:
    ing = IngestionService()
    try:
        season_row = ing._serie_a_season_row(db, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    q = (
        select(FixturePlayerStat, Player, Team)
        .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
        .join(Player, Player.id == FixturePlayerStat.player_id)
        .join(Team, Team.id == FixturePlayerStat.team_id)
        .where(Fixture.season_id == season_row.id)
    )
    if only_with_shots:
        q = q.where(
            FixturePlayerStat.shots_on_target.isnot(None),
            FixturePlayerStat.shots_on_target > 0,
        )
    q = q.limit(limit)

    try:
        rows = db.execute(q).all()
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("debug_player_stats_sample: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc

    out: list[dict[str, Any]] = []
    for fps, pl, tm in rows:
        raw = fps.raw_json if isinstance(fps.raw_json, dict) else None
        out.append(
            {
                "fixture_id": fps.fixture_id,
                "team_name": tm.name,
                "player_name": pl.name,
                "minutes": fps.minutes,
                "position": fps.position,
                "shots_total": fps.shots_total,
                "shots_on_target": fps.shots_on_target,
                "statistics": _statistics_snippet(raw),
            },
        )

    return {"season": season, "limit": limit, "only_with_shots": only_with_shots, "rows": out}
