from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, union_all, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
from app.core.constants import FINISHED_STATUSES, SCHEDULED_STATUSES
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
        meta_merge: dict[str, Any] | None = None,
    ) -> IngestionRun:
        row = db.get(IngestionRun, run.id)
        if row is None:
            raise RuntimeError("ingestion_run non trovato al termine del job")
        row.status = "success" if success else "failed"
        row.records_processed = records_processed
        row.error_message = (error[:10000] if error else None)
        row.completed_at = _utcnow()
        if meta_merge:
            base = dict(row.meta or {})
            base.update(meta_merge)
            row.meta = base
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _serie_a_league_by_settings(self, db: Session) -> League:
        settings = get_settings()
        league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError(
                f"Lega api_league_id={settings.default_league_id} non presente: eseguire prima il bootstrap.",
            )
        return league

    def _serie_a_season_row(self, db: Session, season_year: int) -> Season:
        league = self._serie_a_league_by_settings(db)
        season_row = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season_year),
        )
        if season_row is None:
            raise ValueError(
                f"Stagione {season_year} non trovata per la lega configurata: eseguire prima il bootstrap.",
            )
        return season_row

    def _serie_a_league_row(self, db: Session, season_year: int) -> League:
        _ = self._serie_a_season_row(db, season_year)
        return self._serie_a_league_by_settings(db)

    def _fetch_leagues_picked(self, season: int) -> dict[str, Any]:
        settings = get_settings()
        body = self._client.get("leagues", {"id": settings.default_league_id, "season": season})
        items = list(body.get("response") or [])
        if not items:
            raise ApiFootballError("Nessuna lega nella risposta API")
        return items[0]

    def _upsert_league_from_picked(self, db: Session, picked: dict[str, Any]) -> League:
        lg = picked.get("league") or {}
        country_name = (picked.get("country") or {}).get("name")
        api_league_id = int(lg["id"])
        logo = lg.get("logo")
        logo_url = str(logo) if logo else None
        league = db.scalar(select(League).where(League.api_league_id == api_league_id))
        if league is None:
            league = League(
                api_league_id=api_league_id,
                name=str(lg.get("name") or self.SERIE_A_LEAGUE_NAME),
                country=country_name,
                logo_url=logo_url,
                raw_json=picked,
            )
            db.add(league)
            db.flush()
        else:
            league.name = str(lg.get("name") or league.name)
            league.country = country_name or league.country
            league.logo_url = logo_url or league.logo_url
            league.raw_json = picked
        return league

    def _upsert_season_from_picked(
        self,
        db: Session,
        league: League,
        picked: dict[str, Any],
        season: int,
    ) -> None:
        settings = get_settings()
        seasons = picked.get("seasons") or []
        season_entry: dict[str, Any] | None = None
        for s in seasons:
            if isinstance(s, dict) and s.get("year") == season:
                season_entry = s
                break
        if season_entry is None and seasons and isinstance(seasons[0], dict):
            season_entry = seasons[0]
        label = f"{season}/{season + 1}"
        is_current = season == settings.default_season
        db.execute(update(Season).where(Season.league_id == league.id).values(is_current=False))
        season_row = db.scalar(select(Season).where(Season.league_id == league.id, Season.year == season))
        if season_row is None:
            season_row = Season(
                league_id=league.id,
                year=season,
                label=label,
                is_current=is_current,
                raw_json=season_entry or {},
            )
            db.add(season_row)
        else:
            season_row.label = label
            season_row.is_current = is_current
            season_row.raw_json = season_entry or picked

    def sync_serie_a_league(self, db: Session, season: int = 2025) -> IngestionRun:
        run = self._begin_run(
            db,
            "sync_serie_a_league",
            meta={"season": season, "country": self.SERIE_A_COUNTRY},
        )
        try:
            picked = self._fetch_leagues_picked(season)
            league = self._upsert_league_from_picked(db, picked)
            self._upsert_season_from_picked(db, league, picked, season)
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

    def bootstrap_sync_league(self, db: Session, season: int) -> IngestionRun:
        settings = get_settings()
        run = self._begin_run(
            db,
            "serie_a_bootstrap",
            meta={
                "step": "sync_league",
                "season": season,
                "api_league_id": settings.default_league_id,
            },
        )
        try:
            picked = self._fetch_leagues_picked(season)
            self._upsert_league_from_picked(db, picked)
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=1)
        except Exception as exc:
            logger.exception("bootstrap_sync_league failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def bootstrap_sync_season(self, db: Session, season: int) -> IngestionRun:
        settings = get_settings()
        run = self._begin_run(
            db,
            "serie_a_bootstrap",
            meta={
                "step": "sync_season",
                "season": season,
                "api_league_id": settings.default_league_id,
            },
        )
        try:
            league = self._serie_a_league_by_settings(db)
            picked = self._fetch_leagues_picked(season)
            self._upsert_season_from_picked(db, league, picked, season)
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=1)
        except Exception as exc:
            logger.exception("bootstrap_sync_season failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def bootstrap_sync_teams(self, db: Session, season: int) -> IngestionRun:
        settings = get_settings()
        run = self._begin_run(
            db,
            "serie_a_bootstrap",
            meta={
                "step": "sync_teams",
                "season": season,
                "api_league_id": settings.default_league_id,
            },
        )
        try:
            league = self._serie_a_league_by_settings(db)
            items = self._client.get_teams(league.api_league_id, season)
            n = 0
            for item in items:
                self._upsert_team_from_api_item(db, item)
                n += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=n)
        except Exception as exc:
            logger.exception("bootstrap_sync_teams failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def bootstrap_sync_fixtures(self, db: Session, season: int) -> IngestionRun:
        settings = get_settings()
        run = self._begin_run(
            db,
            "serie_a_bootstrap",
            meta={
                "step": "sync_fixtures",
                "season": season,
                "api_league_id": settings.default_league_id,
            },
        )
        try:
            league = self._serie_a_league_by_settings(db)
            season_row = self._serie_a_season_row(db, season)
            items = self._client.get_fixtures(league.api_league_id, season, status=None)
            n = 0
            for item in items:
                if self._upsert_fixture_from_api_item(db, league, season_row, item):
                    n += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=n)
        except Exception as exc:
            logger.exception("bootstrap_sync_fixtures failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def bootstrap_serie_a_admin(self, db: Session, season: int) -> list[IngestionRun]:
        steps = [
            self.bootstrap_sync_league,
            self.bootstrap_sync_season,
            self.bootstrap_sync_teams,
            self.bootstrap_sync_fixtures,
        ]
        runs: list[IngestionRun] = []
        for fn in steps:
            run = fn(db, season)
            runs.append(run)
            if run.status == "failed":
                break
        return runs

    def _upsert_team_from_api_item(self, db: Session, item: dict[str, Any]) -> None:
        t = item.get("team") or {}
        v = item.get("venue") or {}
        api_team_id = int(t["id"])
        name = str(t.get("name") or "")
        logo = t.get("logo")
        logo_url = str(logo) if logo else None
        code_raw = t.get("code")
        code = str(code_raw).strip()[:16] if code_raw else None
        country_raw = t.get("country")
        country = str(country_raw) if country_raw else None
        founded = _parse_int(t.get("founded"))
        national = bool(t.get("national")) if t.get("national") is not None else False
        venue_name_raw = v.get("name")
        venue_name = str(venue_name_raw)[:255] if venue_name_raw else None
        venue_city_raw = v.get("city")
        venue_city = str(venue_city_raw)[:128] if venue_city_raw else None
        team = db.scalar(select(Team).where(Team.api_team_id == api_team_id))
        if team is None:
            team = Team(
                api_team_id=api_team_id,
                name=name,
                code=code,
                country=country,
                founded=founded,
                national=national,
                logo_url=logo_url,
                venue_name=venue_name,
                venue_city=venue_city,
                raw_json=item,
            )
            db.add(team)
        else:
            team.name = name or team.name
            team.code = code or team.code
            team.country = country or team.country
            team.founded = founded if founded is not None else team.founded
            team.national = national
            team.logo_url = logo_url or team.logo_url
            team.venue_name = venue_name or team.venue_name
            team.venue_city = venue_city or team.venue_city
            team.raw_json = item

    def _upsert_fixture_from_api_item(
        self,
        db: Session,
        league: League,
        season_row: Season,
        item: dict[str, Any],
    ) -> bool:
        fx = item.get("fixture") or {}
        teams = item.get("teams") or {}
        goals = item.get("goals") or {}
        venue_fx = fx.get("venue") or {}
        api_fixture_id = int(fx["id"])
        status_obj = fx.get("status") or {}
        status_short = str(status_obj.get("short") or "NS")
        status_long_raw = status_obj.get("long")
        status_long = str(status_long_raw)[:128] if status_long_raw else None
        elapsed = _parse_int(status_obj.get("elapsed"))
        kickoff_at = _parse_dt(fx.get("date"))
        home_api = int((teams.get("home") or {})["id"])
        away_api = int((teams.get("away") or {})["id"])
        round_raw = fx.get("round")
        round_str = str(round_raw)[:64] if round_raw is not None else None
        referee_raw = fx.get("referee")
        referee = str(referee_raw)[:255] if referee_raw else None
        tz_raw = fx.get("timezone")
        timezone_str = str(tz_raw)[:64] if tz_raw else None
        vn_raw = venue_fx.get("name")
        venue_name = str(vn_raw)[:255] if vn_raw else None
        vc_raw = venue_fx.get("city")
        venue_city = str(vc_raw)[:128] if vc_raw else None

        home_team = db.scalar(select(Team).where(Team.api_team_id == home_api))
        away_team = db.scalar(select(Team).where(Team.api_team_id == away_api))
        if home_team is None or away_team is None:
            logger.warning(
                "Fixture %s saltata: team mancante in DB (home=%s away=%s)",
                api_fixture_id,
                home_api,
                away_api,
            )
            return False

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
                round=round_str,
                referee=referee,
                timezone=timezone_str,
                kickoff_at=kickoff_at,
                status=status_short,
                status_long=status_long,
                elapsed=elapsed,
                goals_home=goals_home,
                goals_away=goals_away,
                venue_name=venue_name,
                venue_city=venue_city,
                raw_json=item,
            )
            db.add(row)
        else:
            row.league_id = league.id
            row.season_id = season_row.id
            row.home_team_id = home_team.id
            row.away_team_id = away_team.id
            row.round = round_str
            row.referee = referee
            row.timezone = timezone_str
            row.kickoff_at = kickoff_at
            row.status = status_short
            row.status_long = status_long
            row.elapsed = elapsed
            row.goals_home = goals_home
            row.goals_away = goals_away
            row.venue_name = venue_name
            row.venue_city = venue_city
            row.raw_json = item
        return True

    def sync_serie_a_teams(self, db: Session, season: int = 2025) -> IngestionRun:
        run = self._begin_run(db, "sync_serie_a_teams", meta={"season": season})
        try:
            league = self._serie_a_league_row(db, season)
            items = self._client.get_teams(league.api_league_id, season)
            n = 0
            for item in items:
                self._upsert_team_from_api_item(db, item)
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
                if self._upsert_fixture_from_api_item(db, league, season_row, item):
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
        return self.bootstrap_serie_a_admin(db, season)

    def dashboard_serie_a(self, db: Session, season: int) -> dict[str, Any]:
        settings = get_settings()
        league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError(
                f"Lega api_league_id={settings.default_league_id} non presente in database: eseguire il bootstrap.",
            )

        season_row = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season),
        )
        if season_row is None:
            raise ValueError(f"Stagione {season} non presente per la lega configurata")

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
        fixtures_scheduled = int(
            db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(Fixture.season_id == season_row.id, Fixture.status.in_(SCHEDULED_STATUSES)),
            )
            or 0,
        )
        fixtures_live_or_unknown = max(0, fixtures_total - fixtures_completed - fixtures_scheduled)

        team_ids_subq = union_all(
            select(Fixture.home_team_id.label("tid")).where(Fixture.season_id == season_row.id),
            select(Fixture.away_team_id.label("tid")).where(Fixture.season_id == season_row.id),
        ).subquery()
        teams_from_fixtures = int(
            db.scalar(select(func.count(func.distinct(team_ids_subq.c.tid))).select_from(team_ids_subq)) or 0,
        )
        teams_total = teams_from_fixtures
        if teams_total == 0:
            teams_total = int(db.scalar(select(func.count()).select_from(Team)) or 0)

        teams_imported = teams_from_fixtures > 0 or (
            fixtures_total == 0 and int(db.scalar(select(func.count()).select_from(Team)) or 0) > 0
        )
        fixtures_imported = fixtures_total > 0

        last_run = db.scalar(
            select(IngestionRun).order_by(
                IngestionRun.started_at.desc().nulls_last(),
                IngestionRun.id.desc(),
            ),
        )

        return {
            "league": league,
            "season": season_row,
            "teams_total": teams_total,
            "fixtures_total": fixtures_total,
            "fixtures_completed": fixtures_completed,
            "fixtures_scheduled": fixtures_scheduled,
            "fixtures_live_or_unknown": fixtures_live_or_unknown,
            "last_ingestion_run": last_run,
            "data_coverage": {
                "teams_imported": teams_imported,
                "fixtures_imported": fixtures_imported,
            },
        }
