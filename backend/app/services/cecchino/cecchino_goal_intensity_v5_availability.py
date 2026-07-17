"""Availability dati locali per audit Intensità Goal v5 — coorte Today eligible."""

from __future__ import annotations

from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.models.competition import Competition
from app.services.cecchino.cecchino_goal_intensity_v5_today_cohort import (
    COHORT_BASIS,
    MIN_GOAL_INTENSITY_TODAY_SCAN_DATE,
    TARGET_SOURCE,
)


def build_goal_intensity_v5_availability(db: Session) -> dict[str, Any]:
    """Aggregato read-only su scansioni Today eleggibili (scan_date ≥ 2026-06-19)."""
    clauses = (
        CecchinoTodayFixture.scan_date >= MIN_GOAL_INTENSITY_TODAY_SCAN_DATE,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    count = int(db.scalar(select(func.count(CecchinoTodayFixture.id)).where(*clauses)) or 0)
    earliest = db.scalar(select(func.min(CecchinoTodayFixture.scan_date)).where(*clauses))
    latest = db.scalar(select(func.max(CecchinoTodayFixture.scan_date)).where(*clauses))

    comp_ids = list(
        db.scalars(
            select(distinct(CecchinoTodayFixture.competition_id)).where(
                *clauses,
                CecchinoTodayFixture.competition_id.is_not(None),
            )
        ).all()
    )
    competitions = sorted(int(c) for c in comp_ids if c is not None)

    countries: list[str] = []
    if competitions:
        countries = sorted(
            {
                str(c.country)
                for c in db.scalars(select(Competition).where(Competition.id.in_(competitions))).all()
                if c.country
            }
        )

    earliest_s = earliest.isoformat() if earliest is not None else None
    latest_s = latest.isoformat() if latest is not None else None

    return {
        "status": "ok",
        "finished_fixtures_with_result": count,
        "eligible_today_scans": count,
        "earliest_kickoff": earliest_s,
        "latest_kickoff": latest_s,
        "earliest_kickoff_date": earliest_s,
        "latest_kickoff_date": latest_s,
        "earliest_scan_date": earliest_s,
        "latest_scan_date": latest_s,
        "min_scan_date": MIN_GOAL_INTENSITY_TODAY_SCAN_DATE.isoformat(),
        "competitions_count": len(competitions),
        "competition_ids": competitions[:200],
        "countries_count": len(countries),
        "countries": countries[:100],
        "cohort_basis": COHORT_BASIS,
        "target_source": TARGET_SOURCE,
    }
