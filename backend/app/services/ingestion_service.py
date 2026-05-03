from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Fixture,
    FixtureLineup,
    FixturePlayerStat,
    FixtureTeamStat,
    IngestionRun,
    League,
    Player,
    Season,
    Team,
)
from app.core.constants import FINISHED_STATUSES
from app.services.api_football_client import ApiFootballClient, ApiFootballError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime:
    if not value:
        raise ValueError("data partita mancante")
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    try:
        return int(str(val).strip())
    except ValueError:
        return None


def _extract_shots_from_statistics(statistics: list[dict[str, Any]] | None) -> tuple[int | None, int | None]:
    shots: int | None = None
    sot: int | None = None
    for item in statistics or []:
        t = (item.get("type") or "").strip()
        v = item.get("value")
        if t in ("Total Shots", "Shots Total"):
            shots = _parse_int(v)
        elif t in ("Shots on Goal", "Shots on Target", "On Target"):
            sot = _parse_int(v)
    return shots, sot


def _extract_minutes_from_statistics(statistics: list[dict[str, Any]] | None) -> int | None:
    for item in statistics or []:
        t = (item.get("type") or "").strip()
        if t in ("Minutes played", "Minutes Played"):
            return _parse_int(item.get("value"))
    return None


class IngestionService:
    SERIE_A_COUNTRY = "Italy"
    SERIE_A_LEAGUE_NAME = "Serie A"

    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def _begin_run(self, db: Session, source: str, meta: dict[str, Any] | None = None) -> IngestionRun:
        run = IngestionRun(
            source=source,
            status="running",
            records_processed=0,
            error_message=None,
            meta=meta,
            started_at=_utcnow(),
            completed_at=None,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _finish_run(
        self,
        db: Session,
        run: IngestionRun,
        *,
        success: bool,
        records_processed: int,
        error: str | None = None,
    ) -> IngestionRun:
        row = db.get(IngestionRun, run.id)
        if row is None:
            raise RuntimeError("ingestion_run non trovato al termine del job")
        row.status = "success" if success else "failed"
        row.records_processed = records_processed
        row.error_message = (error[:10000] if error else None)
        row.completed_at = _utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _serie_a_season_row(self, db: Session, season_year: int) -> Season:
        season_row = db.scalar(
            select(Season)
            .join(League, League.id == Season.league_id)
            .where(
                Season.year == season_year,
                League.name == self.SERIE_A_LEAGUE_NAME,
            ),
        )
        if season_row is None:
            raise ValueError(
                f"Stagione {season_year} non trovata per {self.SERIE_A_LEAGUE_NAME}: eseguire prima il bootstrap.",
            )
        return season_row

    def _serie_a_league_row(self, db: Session, season_year: int) -> League:
        season_row = self._serie_a_season_row(db, season_year)
        league = db.get(League, season_row.league_id)
        if league is None:
            raise ValueError("League non trovata")
        return league

    def sync_serie_a_league(self, db: Session, season: int = 2025) -> IngestionRun:
        run = self._begin_run(
            db,
            "sync_serie_a_league",
            meta={"season": season, "country": self.SERIE_A_COUNTRY},
        )
        try:
            items = self._client.get_league(self.SERIE_A_COUNTRY, self.SERIE_A_LEAGUE_NAME, season)
            picked: dict[str, Any] | None = None
            for it in items:
                lg = it.get("league") or {}
                if (lg.get("name") or "").strip() == self.SERIE_A_LEAGUE_NAME:
                    picked = it
                    break
            if picked is None and items:
                picked = items[0]
            if picked is None:
                raise ApiFootballError("Nessuna lega trovata dalla API")

            lg = picked["league"]
            country_name = (picked.get("country") or {}).get("name")
            api_league_id = int(lg["id"])

            league = db.scalar(select(League).where(League.api_league_id == api_league_id))
            if league is None:
                league = League(
                    api_league_id=api_league_id,
                    name=str(lg.get("name") or self.SERIE_A_LEAGUE_NAME),
                    country=country_name,
                    raw_json=picked,
                )
                db.add(league)
                db.flush()
            else:
                league.name = str(lg.get("name") or league.name)
                league.country = country_name or league.country
                league.raw_json = picked

            season_row = db.scalar(
                select(Season).where(Season.league_id == league.id, Season.year == season),
            )
            if season_row is None:
                season_row = Season(league_id=league.id, year=season, raw_json={"season": season})
                db.add(season_row)
            else:
                season_row.raw_json = {**(season_row.raw_json or {}), "season": season}

            db.commit()
            return self._finish_run(db, run, success=True, records_processed=1)
        except Exception as exc:
            logger.exception("sync_serie_a_league failed")
            db.rollback()
            return self._finish_run(
                db,
                run,
                success=False,
                records_processed=0,
                error=str(exc),
            )

    def sync_serie_a_teams(self, db: Session, season: int = 2025) -> IngestionRun:
        run = self._begin_run(db, "sync_serie_a_teams", meta={"season": season})
        try:
            league = self._serie_a_league_row(db, season)
            items = self._client.get_teams(league.api_league_id, season)
            n = 0
            for item in items:
                t = item.get("team") or {}
                api_team_id = int(t["id"])
                name = str(t.get("name") or "")
                logo = t.get("logo")
                logo_url = str(logo) if logo else None
                team = db.scalar(select(Team).where(Team.api_team_id == api_team_id))
                if team is None:
                    team = Team(
                        api_team_id=api_team_id,
                        name=name,
                        logo_url=logo_url,
                        raw_json=item,
                    )
                    db.add(team)
                else:
                    team.name = name or team.name
                    team.logo_url = logo_url or team.logo_url
                    team.raw_json = item
                n += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=n)
        except Exception as exc:
            logger.exception("sync_serie_a_teams failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def sync_serie_a_fixtures(self, db: Session, season: int = 2025) -> IngestionRun:
        run = self._begin_run(db, "sync_serie_a_fixtures", meta={"season": season})
        try:
            league = self._serie_a_league_row(db, season)
            season_row = self._serie_a_season_row(db, season)
            items = self._client.get_fixtures(league.api_league_id, season, status=None)
            n = 0
            for item in items:
                fx = item.get("fixture") or {}
                teams = item.get("teams") or {}
                goals = item.get("goals") or {}
                api_fixture_id = int(fx["id"])
                status_obj = fx.get("status") or {}
                status_short = str(status_obj.get("short") or "NS")
                kickoff_at = _parse_dt(fx.get("date"))
                home_api = int((teams.get("home") or {})["id"])
                away_api = int((teams.get("away") or {})["id"])

                home_team = db.scalar(select(Team).where(Team.api_team_id == home_api))
                away_team = db.scalar(select(Team).where(Team.api_team_id == away_api))
                if home_team is None or away_team is None:
                    logger.warning(
                        "Fixture %s saltata: team mancante in DB (home=%s away=%s)",
                        api_fixture_id,
                        home_api,
                        away_api,
                    )
                    continue

                gh = goals.get("home")
                ga = goals.get("away")
                goals_home = _parse_int(gh)
                goals_away = _parse_int(ga)

                row = db.scalar(select(Fixture).where(Fixture.api_fixture_id == api_fixture_id))
                if row is None:
                    row = Fixture(
                        api_fixture_id=api_fixture_id,
                        league_id=league.id,
                        season_id=season_row.id,
                        home_team_id=home_team.id,
                        away_team_id=away_team.id,
                        kickoff_at=kickoff_at,
                        status=status_short,
                        goals_home=goals_home,
                        goals_away=goals_away,
                        raw_json=item,
                    )
                    db.add(row)
                else:
                    row.league_id = league.id
                    row.season_id = season_row.id
                    row.home_team_id = home_team.id
                    row.away_team_id = away_team.id
                    row.kickoff_at = kickoff_at
                    row.status = status_short
                    row.goals_home = goals_home
                    row.goals_away = goals_away
                    row.raw_json = item
                n += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=n)
        except Exception as exc:
            logger.exception("sync_serie_a_fixtures failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def sync_completed_fixture_team_stats(self, db: Session, season: int = 2025) -> IngestionRun:
        run = self._begin_run(db, "sync_completed_fixture_team_stats", meta={"season": season})
        try:
            season_row = self._serie_a_season_row(db, season)
            fixtures = db.scalars(
                select(Fixture).where(
                    Fixture.season_id == season_row.id,
                    Fixture.status.in_(FINISHED_STATUSES),
                ),
            ).all()
            processed = 0
            for f in fixtures:
                stats_payload = self._client.get_fixture_statistics(int(f.api_fixture_id))
                for block in stats_payload:
                    team_api = int((block.get("team") or {})["id"])
                    team = db.scalar(select(Team).where(Team.api_team_id == team_api))
                    if team is None:
                        continue
                    statistics = block.get("statistics") or []
                    shots, sot = _extract_shots_from_statistics(statistics)
                    row = db.scalar(
                        select(FixtureTeamStat).where(
                            FixtureTeamStat.fixture_id == f.id,
                            FixtureTeamStat.team_id == team.id,
                        ),
                    )
                    if row is None:
                        row = FixtureTeamStat(
                            fixture_id=f.id,
                            team_id=team.id,
                            shots=shots,
                            shots_on_target=sot,
                            raw_json=block,
                        )
                        db.add(row)
                    else:
                        row.shots = shots
                        row.shots_on_target = sot
                        row.raw_json = block
                    processed += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=processed)
        except Exception as exc:
            logger.exception("sync_completed_fixture_team_stats failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def sync_completed_fixture_player_stats(self, db: Session, season: int = 2025) -> IngestionRun:
        run = self._begin_run(db, "sync_completed_fixture_player_stats", meta={"season": season})
        try:
            season_row = self._serie_a_season_row(db, season)
            fixtures = db.scalars(
                select(Fixture).where(
                    Fixture.season_id == season_row.id,
                    Fixture.status.in_(FINISHED_STATUSES),
                ),
            ).all()
            processed = 0
            for f in fixtures:
                groups = self._client.get_fixture_players(int(f.api_fixture_id))
                for group in groups:
                    team_block = group.get("team") or {}
                    team_api = int(team_block["id"])
                    team = db.scalar(select(Team).where(Team.api_team_id == team_api))
                    if team is None:
                        continue
                    for entry in group.get("players") or []:
                        p = entry.get("player") or {}
                        api_player_id = int(p["id"])
                        name = str(p.get("name") or "")
                        minutes = _extract_minutes_from_statistics(entry.get("statistics"))
                        player = db.scalar(select(Player).where(Player.api_player_id == api_player_id))
                        if player is None:
                            player = Player(
                                api_player_id=api_player_id,
                                name=name,
                                team_id=team.id,
                                raw_json=p,
                            )
                            db.add(player)
                            db.flush()
                        else:
                            player.name = name or player.name
                            player.team_id = team.id
                            player.raw_json = p

                        row = db.scalar(
                            select(FixturePlayerStat).where(
                                FixturePlayerStat.fixture_id == f.id,
                                FixturePlayerStat.player_id == player.id,
                            ),
                        )
                        if row is None:
                            row = FixturePlayerStat(
                                fixture_id=f.id,
                                player_id=player.id,
                                team_id=team.id,
                                minutes=minutes,
                                raw_json=entry,
                            )
                            db.add(row)
                        else:
                            row.team_id = team.id
                            row.minutes = minutes
                            row.raw_json = entry
                        processed += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=processed)
        except Exception as exc:
            logger.exception("sync_completed_fixture_player_stats failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def sync_completed_fixture_lineups(self, db: Session, season: int = 2025) -> IngestionRun:
        run = self._begin_run(db, "sync_completed_fixture_lineups", meta={"season": season})
        try:
            season_row = self._serie_a_season_row(db, season)
            fixtures = db.scalars(
                select(Fixture).where(
                    Fixture.season_id == season_row.id,
                    Fixture.status.in_(FINISHED_STATUSES),
                ),
            ).all()
            processed = 0
            for f in fixtures:
                blocks = self._client.get_fixture_lineups(int(f.api_fixture_id))
                for block in blocks:
                    team_block = block.get("team") or {}
                    team_api = int(team_block["id"])
                    team = db.scalar(select(Team).where(Team.api_team_id == team_api))
                    if team is None:
                        continue
                    formation = block.get("formation")
                    formation_str = str(formation) if formation else None
                    lineup_json = {
                        "startXI": block.get("startXI"),
                        "substitutes": block.get("substitutes"),
                        "coach": block.get("coach"),
                    }
                    row = db.scalar(
                        select(FixtureLineup).where(
                            FixtureLineup.fixture_id == f.id,
                            FixtureLineup.team_id == team.id,
                        ),
                    )
                    if row is None:
                        row = FixtureLineup(
                            fixture_id=f.id,
                            team_id=team.id,
                            formation=formation_str,
                            lineup_json=lineup_json,
                            raw_json=block,
                        )
                        db.add(row)
                    else:
                        row.formation = formation_str
                        row.lineup_json = lineup_json
                        row.raw_json = block
                    processed += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=processed)
        except Exception as exc:
            logger.exception("sync_completed_fixture_lineups failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def bootstrap_serie_a(self, db: Session, season: int = 2025) -> list[IngestionRun]:
        return [
            self.sync_serie_a_league(db, season),
            self.sync_serie_a_teams(db, season),
            self.sync_serie_a_fixtures(db, season),
        ]

    def dashboard_serie_a(self, db: Session, season: int) -> dict[str, Any]:
        league = db.scalar(select(League).where(League.name == self.SERIE_A_LEAGUE_NAME))
        if league is None:
            raise ValueError("Lega Serie A non presente in database")

        season_row = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season),
        )
        if season_row is None:
            raise ValueError(f"Stagione {season} non presente")

        fixtures_total = int(
            db.scalar(select(func.count()).select_from(Fixture).where(Fixture.season_id == season_row.id)) or 0,
        )
        fixtures_completed = int(
            db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(Fixture.season_id == season_row.id, Fixture.status.in_(FINISHED_STATUSES)),
            )
            or 0,
        )

        fixtures_with_team_stats = int(
            db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(
                    Fixture.season_id == season_row.id,
                    Fixture.id.in_(
                        select(FixtureTeamStat.fixture_id)
                        .group_by(FixtureTeamStat.fixture_id)
                        .having(func.count() >= 2),
                    ),
                ),
            )
            or 0,
        )

        fixtures_with_player_stats = int(
            db.scalar(
                select(func.count(func.distinct(FixturePlayerStat.fixture_id))).where(
                    FixturePlayerStat.fixture_id.in_(
                        select(Fixture.id).where(Fixture.season_id == season_row.id),
                    ),
                ),
            )
            or 0,
        )

        fixtures_with_lineups = int(
            db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(
                    Fixture.season_id == season_row.id,
                    Fixture.id.in_(
                        select(FixtureLineup.fixture_id)
                        .group_by(FixtureLineup.fixture_id)
                        .having(func.count() >= 2),
                    ),
                ),
            )
            or 0,
        )

        def pct(part: int, whole: int) -> float:
            if whole <= 0:
                return 0.0
            return round(100.0 * part / whole, 2)

        coverage_team_stats_pct = pct(fixtures_with_team_stats, fixtures_completed)
        coverage_player_stats_pct = pct(fixtures_with_player_stats, fixtures_completed)
        coverage_lineups_pct = pct(fixtures_with_lineups, fixtures_completed)

        last_run = db.scalar(
            select(IngestionRun)
            .order_by(IngestionRun.started_at.desc().nulls_last(), IngestionRun.id.desc())
            .limit(1),
        )

        return {
            "season": season,
            "league_api_id": int(league.api_league_id),
            "fixtures_total": fixtures_total,
            "fixtures_completed": fixtures_completed,
            "fixtures_with_team_stats": fixtures_with_team_stats,
            "fixtures_with_player_stats": fixtures_with_player_stats,
            "fixtures_with_lineups": fixtures_with_lineups,
            "coverage_team_stats_pct": coverage_team_stats_pct,
            "coverage_player_stats_pct": coverage_player_stats_pct,
            "coverage_lineups_pct": coverage_lineups_pct,
            "last_ingestion_run": last_run,
        }
