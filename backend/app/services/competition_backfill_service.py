from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Competition,
    Fixture,
    FixtureLineup,
    FixtureLineupPlayer,
    FixtureMissingPlayer,
    FixtureProviderLineup,
    FixtureProviderMapping,
    FixtureTeamStat,
    IngestionRun,
    OddsDiscoverySnapshot,
    PlayerMatchStat,
    PlayerSeasonProfile,
    PlayerTeamSeason,
    RefereeSeasonProfile,
    SportApiFixtureOddsSnapshot,
    StandingEntry,
    StandingsSnapshot,
    TeamSotPrediction,
    TrackedBettingPick,
)
from app.services.competition_service import CompetitionService, SERIE_A_SEASON

logger = logging.getLogger(__name__)

# Tabelle backfill: (Model, filtro extra o None)
BACKFILL_TABLES: list[tuple[type, str | None]] = [
    (Fixture, "fixture"),
    (FixtureTeamStat, "via_fixture"),
    (PlayerMatchStat, "league_season"),
    (PlayerSeasonProfile, "league_season"),
    (PlayerTeamSeason, "league_season"),
    (StandingsSnapshot, "league_season"),
    (StandingEntry, "league_season"),
    (TeamSotPrediction, "via_fixture"),
    (FixtureLineup, "league_season"),
    (FixtureLineupPlayer, "league_season"),
    (FixtureProviderMapping, "via_fixture"),
    (FixtureProviderLineup, "via_fixture"),
    (FixtureMissingPlayer, "via_fixture"),
    (TrackedBettingPick, "via_fixture"),
    (RefereeSeasonProfile, "league_season_int"),
    (OddsDiscoverySnapshot, "via_fixture"),
    (SportApiFixtureOddsSnapshot, "via_fixture"),
    (IngestionRun, None),
]


class CompetitionBackfillService:
    def __init__(self) -> None:
        self._comp_svc = CompetitionService()

    def backfill_serie_a(self, db: Session, season_year: int = SERIE_A_SEASON) -> dict[str, Any]:
        settings = get_settings()
        competition = self._comp_svc.ensure_serie_a_competition(db, season_year)
        comp_id = competition.id
        league_id = competition.league_id

        if league_id is None:
            from app.models import League

            league = db.scalar(
                select(League).where(League.api_league_id == settings.default_league_id)
            )
            if league is not None:
                competition.league_id = league.id
                league_id = league.id
                db.add(competition)
                db.commit()
                db.refresh(competition)

        log: dict[str, int] = {}

        # fixtures
        n = self._backfill_fixtures(db, comp_id, league_id, season_year)
        log["fixtures"] = n

        fixture_ids_subq = select(Fixture.id).where(Fixture.competition_id == comp_id).scalar_subquery()

        # via fixture
        for model in (
            FixtureTeamStat,
            TeamSotPrediction,
            FixtureProviderMapping,
            FixtureProviderLineup,
            FixtureMissingPlayer,
            TrackedBettingPick,
        ):
            name = model.__tablename__
            count = db.scalar(
                select(func.count())
                .select_from(model)
                .where(
                    model.fixture_id.in_(select(Fixture.id).where(Fixture.league_id == league_id)),
                    model.competition_id.is_(None),
                )
            )
            if count and league_id:
                db.execute(
                    update(model)
                    .where(
                        model.fixture_id.in_(
                            select(Fixture.id).where(
                                Fixture.league_id == league_id,
                                Fixture.season_id == competition.season_id,
                            )
                        ),
                        model.competition_id.is_(None),
                    )
                    .values(competition_id=comp_id)
                )
                db.commit()
            log[name] = int(count or 0)

        # league_id + season int
        for model in (
            PlayerMatchStat,
            PlayerSeasonProfile,
            PlayerTeamSeason,
            FixtureLineup,
            FixtureLineupPlayer,
        ):
            name = model.__tablename__
            if league_id is None:
                log[name] = 0
                continue
            count = db.scalar(
                select(func.count())
                .select_from(model)
                .where(
                    model.league_id == league_id,
                    model.season == season_year,
                    model.competition_id.is_(None),
                )
            )
            if count:
                db.execute(
                    update(model)
                    .where(
                        model.league_id == league_id,
                        model.season == season_year,
                        model.competition_id.is_(None),
                    )
                    .values(competition_id=comp_id)
                )
                db.commit()
            log[name] = int(count or 0)

        # standings
        if league_id and competition.season_id:
            for model in (StandingsSnapshot, StandingEntry):
                name = model.__tablename__
                count = db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(
                        model.league_id == league_id,
                        model.season_id == competition.season_id,
                        model.competition_id.is_(None),
                    )
                )
                if count:
                    db.execute(
                        update(model)
                        .where(
                            model.league_id == league_id,
                            model.season_id == competition.season_id,
                            model.competition_id.is_(None),
                        )
                        .values(competition_id=comp_id)
                    )
                    db.commit()
                log[name] = int(count or 0)

        # referee season profiles
        if league_id:
            count = db.scalar(
                select(func.count())
                .select_from(RefereeSeasonProfile)
                .where(
                    RefereeSeasonProfile.league_id == league_id,
                    RefereeSeasonProfile.season == season_year,
                    RefereeSeasonProfile.competition_id.is_(None),
                )
            )
            if count:
                db.execute(
                    update(RefereeSeasonProfile)
                    .where(
                        RefereeSeasonProfile.league_id == league_id,
                        RefereeSeasonProfile.season == season_year,
                        RefereeSeasonProfile.competition_id.is_(None),
                    )
                    .values(competition_id=comp_id)
                )
                db.commit()
            log["referee_season_profiles"] = int(count or 0)

        _ = fixture_ids_subq
        log["competition_id"] = comp_id
        log["competition_key"] = competition.key
        logger.info("Backfill Serie A competition_id=%s: %s", comp_id, log)
        return {"competition_id": comp_id, "competition_key": competition.key, "updated_by_table": log}

    def _backfill_fixtures(
        self,
        db: Session,
        comp_id: int,
        league_id: int | None,
        season_year: int,
    ) -> int:
        if league_id is None:
            return 0
        from app.models import Season

        season_row = db.scalar(
            select(Season).where(Season.league_id == league_id, Season.year == season_year)
        )
        if season_row is None:
            return 0
        count = db.scalar(
            select(func.count())
            .select_from(Fixture)
            .where(
                Fixture.league_id == league_id,
                Fixture.season_id == season_row.id,
                Fixture.competition_id.is_(None),
            )
        )
        if count:
            db.execute(
                update(Fixture)
                .where(
                    Fixture.league_id == league_id,
                    Fixture.season_id == season_row.id,
                    Fixture.competition_id.is_(None),
                )
                .values(competition_id=comp_id)
            )
            db.commit()
        return int(count or 0)
