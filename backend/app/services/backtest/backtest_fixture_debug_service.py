"""Lista fixture candidate per debug PointInTimeContext (Step D + F)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.backtest.errors import raise_backtest_http
from app.core.constants import FINISHED_STATUSES
from app.models import Competition, Fixture, FixtureTeamStat, Season, Team
from app.schemas.backtest_point_in_time import (
    BacktestFixtureCandidate,
    BacktestFixtureListResponse,
    BacktestFixtureTeamBrief,
)
from app.services.backtest.round_filter import extract_fixture_round_number, fixture_matches_round_number


@dataclass(frozen=True)
class MiniRunFixtureSelection:
    items: list[BacktestFixtureCandidate]
    order_by: str
    fixtures_requested: int


@dataclass(frozen=True)
class SeasonBackfillSelection:
    items: list[BacktestFixtureCandidate]
    total_candidates: int
    order_by: str


class BacktestFixtureDebugService:
    def _require_competition(self, db: Session, competition_id: int) -> Competition:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            raise_backtest_http(404, "competition_not_found", f"Competition {competition_id} not found")
        return comp

    def _fixture_to_candidate(self, db: Session, fixture: Fixture) -> BacktestFixtureCandidate:
        home = db.get(Team, int(fixture.home_team_id))
        away = db.get(Team, int(fixture.away_team_id))
        stats = db.scalars(
            select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == int(fixture.id)),
        ).all()
        has_stats = len(stats) >= 1
        home_sot = None
        away_sot = None
        for st in stats:
            if int(st.team_id) == int(fixture.home_team_id) and st.shots_on_target is not None:
                home_sot = int(st.shots_on_target)
            if int(st.team_id) == int(fixture.away_team_id) and st.shots_on_target is not None:
                away_sot = int(st.shots_on_target)
        actual_total = None
        if home_sot is not None and away_sot is not None:
            actual_total = home_sot + away_sot
        return BacktestFixtureCandidate(
            fixture_id=int(fixture.id),
            kickoff_at=fixture.kickoff_at,
            round=fixture.round,
            status=fixture.status,
            home_team=BacktestFixtureTeamBrief(
                id=int(fixture.home_team_id),
                name=home.name if home else str(fixture.home_team_id),
            ),
            away_team=BacktestFixtureTeamBrief(
                id=int(fixture.away_team_id),
                name=away.name if away else str(fixture.away_team_id),
            ),
            has_team_stats=has_stats,
            actual_total_sot=actual_total,
        )

    def _both_teams_sot_stats_clause(self):
        home_stat = exists(
            select(1).where(
                FixtureTeamStat.fixture_id == Fixture.id,
                FixtureTeamStat.team_id == Fixture.home_team_id,
                FixtureTeamStat.shots_on_target.isnot(None),
            ),
        )
        away_stat = exists(
            select(1).where(
                FixtureTeamStat.fixture_id == Fixture.id,
                FixtureTeamStat.team_id == Fixture.away_team_id,
                FixtureTeamStat.shots_on_target.isnot(None),
            ),
        )
        return home_stat, away_stat

    def list_candidate_fixtures(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int | None = None,
        status: str = "finished",
        limit: int = 20,
        offset: int = 0,
        round_contains: str | None = None,
    ) -> BacktestFixtureListResponse:
        comp = self._require_competition(db, competition_id)

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
        if round_contains and round_contains.strip():
            clauses.append(Fixture.round.ilike(f"%{round_contains.strip()}%"))

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
            items.append(self._fixture_to_candidate(db, f))

        return BacktestFixtureListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def select_fixtures_for_mini_run(
        self,
        db: Session,
        *,
        competition_id: int,
        limit: int = 20,
        offset: int = 0,
        round_number: int | None = None,
        round_contains: str | None = None,
        fixture_ids: list[int] | None = None,
        order_by: str = "kickoff_at asc",
    ) -> MiniRunFixtureSelection:
        self._require_competition(db, competition_id)

        clauses = [Fixture.competition_id == int(competition_id)]
        clauses.append(Fixture.status.in_(FINISHED_STATUSES))
        home_stat, away_stat = self._both_teams_sot_stats_clause()
        clauses.extend([home_stat, away_stat])

        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, int(offset))

        if fixture_ids:
            unique_ids = list(dict.fromkeys(int(i) for i in fixture_ids))
            if len(unique_ids) > 50:
                raise_backtest_http(
                    422,
                    "fixture_ids_limit_exceeded",
                    "fixture_ids supports at most 50 fixtures per mini-run.",
                )
            clauses.append(Fixture.id.in_(unique_ids))
            rows = db.scalars(
                select(Fixture)
                .where(*clauses)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all()
            fixtures_requested = len(unique_ids)
        else:
            if round_number is None and round_contains and round_contains.strip():
                clauses.append(Fixture.round.ilike(f"%{round_contains.strip()}%"))
            rows = db.scalars(
                select(Fixture)
                .where(*clauses)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all()
            if round_number is not None:
                rows = [
                    f for f in rows if fixture_matches_round_number(f.round, int(round_number))
                ]
            fixtures_requested = safe_limit
            rows = rows[safe_offset : safe_offset + safe_limit]

        items = [self._fixture_to_candidate(db, f) for f in rows]
        return MiniRunFixtureSelection(
            items=items,
            order_by=order_by,
            fixtures_requested=fixtures_requested if fixture_ids else fixtures_requested,
        )

    def select_fixtures_for_lineup_audit(
        self,
        db: Session,
        *,
        competition_id: int,
        round_number: int,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "kickoff_at asc",
    ) -> MiniRunFixtureSelection:
        """Fixture finite per giornata esatta — audit lineup G2A (no requisito SOT)."""
        self._require_competition(db, competition_id)

        clauses = [
            Fixture.competition_id == int(competition_id),
            Fixture.status.in_(FINISHED_STATUSES),
        ]
        rows = db.scalars(
            select(Fixture)
            .where(*clauses)
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
        ).all()
        rows = [f for f in rows if fixture_matches_round_number(f.round, int(round_number))]

        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, int(offset))
        sliced = rows[safe_offset : safe_offset + safe_limit]

        items = [self._fixture_to_candidate(db, f) for f in sliced]
        return MiniRunFixtureSelection(
            items=items,
            order_by=order_by,
            fixtures_requested=safe_limit,
        )

    def _filter_by_round_range(
        self,
        fixtures: list[Fixture],
        *,
        round_from: int | None,
        round_to: int | None,
    ) -> list[Fixture]:
        if round_from is None and round_to is None:
            return fixtures
        out: list[Fixture] = []
        for f in fixtures:
            rn = extract_fixture_round_number(f.round)
            if rn is None:
                continue
            if round_from is not None and rn < int(round_from):
                continue
            if round_to is not None and rn > int(round_to):
                continue
            out.append(f)
        return out

    def select_fixtures_for_sportapi_season_backfill(
        self,
        db: Session,
        *,
        competition_id: int,
        only_finished: bool = True,
        round_from: int | None = None,
        round_to: int | None = None,
        limit: int = 400,
        offset: int = 0,
        require_sot_stats: bool = False,
        order_by: str = "kickoff_at asc",
    ) -> SeasonBackfillSelection:
        """Fixture per backfill mapping SportAPI stagione (Step K.4)."""
        self._require_competition(db, competition_id)

        clauses = [Fixture.competition_id == int(competition_id)]
        if only_finished:
            clauses.append(Fixture.status.in_(FINISHED_STATUSES))
        if require_sot_stats:
            home_stat, away_stat = self._both_teams_sot_stats_clause()
            clauses.extend([home_stat, away_stat])

        rows = list(
            db.scalars(
                select(Fixture)
                .where(*clauses)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all(),
        )
        rows = self._filter_by_round_range(rows, round_from=round_from, round_to=round_to)
        total = len(rows)

        safe_limit = max(1, min(int(limit), 400))
        safe_offset = max(0, int(offset))
        sliced = rows[safe_offset : safe_offset + safe_limit]

        items = [self._fixture_to_candidate(db, f) for f in sliced]
        return SeasonBackfillSelection(
            items=items,
            total_candidates=total,
            order_by=order_by,
        )

    def select_mapped_fixtures_for_sportapi_unavailable_season(
        self,
        db: Session,
        *,
        competition_id: int,
        only_finished: bool = True,
        round_from: int | None = None,
        round_to: int | None = None,
        limit: int = 400,
        offset: int = 0,
        order_by: str = "kickoff_at asc",
    ) -> SeasonBackfillSelection:
        """Fixture finished con mapping SportAPI per backfill unavailable stagione (Step K.4)."""
        from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping

        self._require_competition(db, competition_id)

        clauses = [
            Fixture.competition_id == int(competition_id),
            FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
        ]
        if only_finished:
            clauses.append(Fixture.status.in_(FINISHED_STATUSES))

        rows = list(
            db.scalars(
                select(Fixture)
                .join(
                    FixtureProviderMapping,
                    FixtureProviderMapping.fixture_id == Fixture.id,
                )
                .where(*clauses)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all(),
        )
        rows = self._filter_by_round_range(rows, round_from=round_from, round_to=round_to)
        total = len(rows)

        safe_limit = max(1, min(int(limit), 400))
        safe_offset = max(0, int(offset))
        sliced = rows[safe_offset : safe_offset + safe_limit]

        items = [self._fixture_to_candidate(db, f) for f in sliced]
        return SeasonBackfillSelection(
            items=items,
            total_candidates=total,
            order_by=order_by,
        )
