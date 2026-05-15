"""Diagnostica read-only sulla copertura statistiche tiri in fixture_team_stats."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models import Fixture, FixtureTeamStat
from app.services.fixture_team_stats_mapping import statistics_list_to_fields
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/debug", tags=["admin-debug-team-shot-stats"])

_COVERAGE_COLS = (
    "shots_on_target",
    "total_shots",
    "shots_inside_box",
    "shots_outside_box",
    "blocked_shots",
    "shots_off_goal",
)


@router.get("/serie-a/{season}/team-shot-stats-summary", response_model=None)
def team_shot_stats_summary_serie_a(
    season: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ing = IngestionService()
    try:
        season_row = ing._serie_a_season_row(db, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    season_filter = Fixture.season_id == season_row.id
    try:
        stats_rows = (
            db.scalars(
                select(FixtureTeamStat)
                .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
                .where(season_filter)
                .options(joinedload(FixtureTeamStat.team))
                .order_by(Fixture.id.desc()),
            )
            .unique()
            .all()
        )
        rows_total = len(stats_rows)
        if rows_total == 0:
            return {
                "status": "success",
                "season": int(season),
                "rows_total": 0,
                "coverage": {c: {"rows_with_value": 0, "coverage_pct": 0.0} for c in _COVERAGE_COLS},
                "column_null_but_raw_parseable": {"blocked_shots": 0, "shots_off_goal": 0},
                "sample": [],
            }
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "team-shot-stats-summary DB error: %s",
            exc.__class__.__name__,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="Database error") from exc

    coverage_counts: dict[str, int] = {c: 0 for c in _COVERAGE_COLS}
    blocked_raw_parseable = 0
    offgoal_raw_parseable = 0
    for st in stats_rows:
        if st.shots_on_target is not None:
            coverage_counts["shots_on_target"] += 1
        if st.total_shots is not None:
            coverage_counts["total_shots"] += 1
        if st.shots_inside_box is not None:
            coverage_counts["shots_inside_box"] += 1
        if st.shots_outside_box is not None:
            coverage_counts["shots_outside_box"] += 1
        parsed = None
        if isinstance(st.raw_json, dict) and (st.blocked_shots is None or st.shots_off_goal is None):
            parsed = statistics_list_to_fields(st.raw_json.get("statistics"))

        if st.blocked_shots is not None:
            coverage_counts["blocked_shots"] += 1
        elif parsed is not None and "blocked_shots" in parsed:
            blocked_raw_parseable += 1

        if st.shots_off_goal is not None:
            coverage_counts["shots_off_goal"] += 1
        elif parsed is not None and "shots_off_goal" in parsed:
            offgoal_raw_parseable += 1

    coverage_out: dict[str, dict[str, float | int]] = {}
    for c in _COVERAGE_COLS:
        n = coverage_counts[c]
        pct = round(100.0 * n / rows_total, 2)
        coverage_out[c] = {"rows_with_value": int(n), "coverage_pct": float(pct)}

    sample: list[dict[str, Any]] = []
    for st in stats_rows[:15]:
        tm = st.team
        sample.append(
            {
                "fixture_id": int(st.fixture_id),
                "team_id": int(st.team_id),
                "team_name": tm.name if tm is not None else "",
                "shots_on_target": st.shots_on_target,
                "total_shots": st.total_shots,
                "shots_inside_box": st.shots_inside_box,
                "shots_outside_box": st.shots_outside_box,
                "blocked_shots": st.blocked_shots,
                "shots_off_goal": st.shots_off_goal,
            },
        )

    return {
        "status": "success",
        "season": int(season),
        "rows_total": rows_total,
        "coverage": coverage_out,
        "column_null_but_raw_parseable": {
            "blocked_shots": int(blocked_raw_parseable),
            "shots_off_goal": int(offgoal_raw_parseable),
        },
        "sample": sample,
    }
