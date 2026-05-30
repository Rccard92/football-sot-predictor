"""Lista fixture candidate per debug PointInTimeContext (Step D)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backtest.errors import raise_backtest_http
from app.core.constants import FINISHED_STATUSES
from app.models import Competition, Fixture, FixtureTeamStat, Season, Team
from app.schemas.backtest_point_in_time import (
    BacktestFixtureCandidate,
    BacktestFixtureListResponse,
    BacktestFixtureTeamBrief,
)


class BacktestFixtureDebugService:
    def list_candidate_fixtures(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int | None = None,
        status: str = "finished",
        limit: int = 20,
        offset: int = 0,
    ) -> BacktestFixtureListResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            raise_backtest_http(404, "competition_not_found", f"Competition {competition_id} not found")

        clauses = [Fixture.competition_id == int(competition_id)]
        if season_year is not None:
            if comp.season_id is not None:
                clauses.append(Fixture.season_id == int(comp.season_id))
            else:
                season_row = db.scalar(
                    select(Season).where(
                        Season.league_id == comp.league_id,
                        Season.year == int(season_year),
                    ),
                )
                if season_row is not None:
                    clauses.append(Fixture.season_id == int(season_row.id))
        if status == "finished":
            clauses.append(Fixture.status.in_(FINISHED_STATUSES))

        total = int(
            db.scalar(select(func.count()).select_from(Fixture).where(*clauses)) or 0,
        )
        rows = db.scalars(
            select(Fixture)
            .where(*clauses)
            .order_by(Fixture.kickoff_at.desc(), Fixture.id.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 100))),
        ).all()

        items: list[BacktestFixtureCandidate] = []
        for f in rows:
            home = db.get(Team, int(f.home_team_id))
            away = db.get(Team, int(f.away_team_id))
            stats = db.scalars(
                select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == int(f.id)),
            ).all()
            has_stats = len(stats) >= 1
            home_sot = None
            away_sot = None
            for st in stats:
                if int(st.team_id) == int(f.home_team_id) and st.shots_on_target is not None:
                    home_sot = int(st.shots_on_target)
                if int(st.team_id) == int(f.away_team_id) and st.shots_on_target is not None:
                    away_sot = int(st.shots_on_target)
            actual_total = None
            if home_sot is not None and away_sot is not None:
                actual_total = home_sot + away_sot
            items.append(
                BacktestFixtureCandidate(
                    fixture_id=int(f.id),
                    kickoff_at=f.kickoff_at,
                    round=f.round,
                    status=f.status,
                    home_team=BacktestFixtureTeamBrief(
                        id=int(f.home_team_id),
                        name=home.name if home else str(f.home_team_id),
                    ),
                    away_team=BacktestFixtureTeamBrief(
                        id=int(f.away_team_id),
                        name=away.name if away else str(f.away_team_id),
                    ),
                    has_team_stats=has_stats,
                    actual_total_sot=actual_total,
                ),
            )

        return BacktestFixtureListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )
