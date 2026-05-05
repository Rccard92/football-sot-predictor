from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select, union_all, update
from sqlalchemy.exc import OperationalError, ProgrammingError
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
    PlayerAvailabilityEvent,
    PlayerSotProfile,
    Season,
    StandingEntry,
    StandingsSnapshot,
    Team,
    TeamSotFeature,
    TeamSotPrediction,
)
from app.core.constants import FINISHED_STATUSES, SCHEDULED_STATUSES, fixture_eligible_for_upcoming_sot
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.fixture_team_stats_mapping import apply_parsed_to_row, statistics_list_to_fields
from app.services.player_stats_parsing import (
    parse_fixture_player_statistics,
    player_entry_flags,
    player_position,
)

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
        league_meta = item.get("league") or {}
        round_raw = fx.get("round")
        if round_raw is None:
            round_raw = league_meta.get("round")
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

    def ingest_serie_a_standings(self, db: Session, season: int) -> IngestionRun:
        run = self._begin_run(db, "serie_a_standings", meta={"season": season})
        try:
            league = self._serie_a_league_row(db, season)
            season_row = self._serie_a_season_row(db, season)
            payload = self._client.get_standings(league.api_league_id, season)
            if not payload:
                raise ValueError("standings_response_empty")
            snapshot = StandingsSnapshot(
                season_id=season_row.id,
                league_id=league.id,
                snapshot_at=_utcnow(),
                raw_json={"response": payload},
            )
            db.add(snapshot)
            db.flush()
            processed = 0
            first = payload[0] if payload else {}
            league_block = (first or {}).get("league") or {}
            standings_groups = league_block.get("standings") or []
            if not standings_groups:
                raise ValueError("standings_groups_empty")
            for group in standings_groups:
                for entry in group or []:
                    team_block = entry.get("team") or {}
                    team_api_id = team_block.get("id")
                    if team_api_id is None:
                        continue
                    team = db.scalar(select(Team).where(Team.api_team_id == int(team_api_id)))
                    if team is None:
                        continue
                    all_block = entry.get("all") or {}
                    goals_block = all_block.get("goals") or {}
                    row = StandingEntry(
                        snapshot_id=snapshot.id,
                        season_id=season_row.id,
                        league_id=league.id,
                        team_id=team.id,
                        rank=_parse_int(entry.get("rank")),
                        points=_parse_int(entry.get("points")),
                        goals_diff=_parse_int(entry.get("goalsDiff")),
                        played=_parse_int(all_block.get("played")),
                        win=_parse_int(all_block.get("win")),
                        draw=_parse_int(all_block.get("draw")),
                        lose=_parse_int(all_block.get("lose")),
                        goals_for=_parse_int(goals_block.get("for")),
                        goals_against=_parse_int(goals_block.get("against")),
                        form=str(entry.get("form"))[:64] if entry.get("form") is not None else None,
                        status=str(entry.get("status"))[:64] if entry.get("status") is not None else None,
                        description=(
                            str(entry.get("description"))[:255]
                            if entry.get("description") is not None
                            else None
                        ),
                        raw_json=entry,
                    )
                    db.add(row)
                    processed += 1
            if processed <= 0:
                raise ValueError("standings_entries_not_found")
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=processed)
        except Exception as exc:
            logger.exception("ingest_serie_a_standings failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def latest_standings_for_season(self, db: Session, season: int) -> dict[str, Any]:
        try:
            season_row = self._serie_a_season_row(db, season)
        except ValueError:
            return {"season": season, "snapshot_at": None, "teams": []}
        snap = db.scalar(
            select(StandingsSnapshot)
            .where(StandingsSnapshot.season_id == season_row.id)
            .order_by(StandingsSnapshot.snapshot_at.desc(), StandingsSnapshot.id.desc()),
        )
        if snap is None:
            return {"season": season, "snapshot_at": None, "teams": []}
        rows = db.scalars(
            select(StandingEntry)
            .where(StandingEntry.snapshot_id == snap.id)
            .order_by(StandingEntry.rank.asc().nulls_last(), StandingEntry.team_id.asc()),
        ).all()
        team_ids = {r.team_id for r in rows}
        teams = {
            t.id: t
            for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
        } if team_ids else {}
        return {
            "season": season,
            "snapshot_at": snap.snapshot_at,
            "teams": [
                {
                    "rank": r.rank,
                    "team_id": r.team_id,
                    "team_name": teams[r.team_id].name if r.team_id in teams else "",
                    "points": r.points,
                    "played": r.played,
                    "goals_diff": r.goals_diff,
                    "form": r.form,
                    "description": r.description,
                }
                for r in rows
            ],
        }

    def run_post_matchday_refresh(self, db: Session, season: int, *, force_update: bool = False) -> dict[str, Any]:
        from app.services.player_sot_profile_service import PlayerSotProfileService
        from app.services.sot_backtest_service import SotBacktestService
        from app.services.sot_feature_service import SotFeatureService
        from app.services.sot_prediction_service import SotPredictionService

        run = self._begin_run(
            db,
            "post_matchday_refresh",
            meta={"season": season, "force_update": force_update},
        )
        steps: list[dict[str, Any]] = []

        def mark_step(name: str, status: str, records: int = 0, extra: dict[str, Any] | None = None) -> None:
            row: dict[str, Any] = {"name": name, "status": status, "records_processed": records}
            if extra:
                row.update(extra)
            steps.append(row)

        try:
            s1 = self.sync_serie_a_fixtures(db, season)
            mark_step("sync_fixtures", "success" if s1.status == "success" else "failed", s1.records_processed)
            if s1.status != "success":
                raise RuntimeError(s1.error_message or "sync fixtures fallito")

            s2 = self.sync_completed_fixture_team_stats(db, season)
            mark_step("sync_team_stats", "success" if s2.status == "success" else "failed", s2.records_processed)
            if s2.status != "success":
                raise RuntimeError(s2.error_message or "sync team stats fallito")

            s3 = self.sync_completed_fixture_player_stats(db, season)
            mark_step("sync_player_stats", "success" if s3.status == "success" else "failed", s3.records_processed)
            if s3.status != "success":
                raise RuntimeError(s3.error_message or "sync player stats fallito")

            s4 = self.sync_completed_fixture_lineups(db, season)
            mark_step("sync_lineups", "success" if s4.status == "success" else "failed", s4.records_processed)
            if s4.status != "success":
                raise RuntimeError(s4.error_message or "sync lineups fallito")

            feat = SotFeatureService().build_features_for_season_admin(db, season)
            mark_step(
                "rebuild_sot_features_completed",
                "success" if feat.get("status") == "success" else "failed",
                int(feat.get("feature_rows_created_or_updated") or 0),
            )
            if feat.get("status") != "success":
                raise RuntimeError(str(feat.get("message") or "build completed features fallito"))

            pred = SotPredictionService().generate_for_season_admin(db, season)
            mark_step(
                "generate_baseline_predictions_completed",
                "success" if pred.get("status") == "success" else "failed",
                int(pred.get("predictions_created_or_updated") or 0),
            )
            if pred.get("status") != "success":
                raise RuntimeError(str(pred.get("message") or "generate completed predictions fallito"))

            bt = SotBacktestService().run_numeric_backtest_admin(db, season)
            mark_step(
                "run_backtest",
                "success" if bt.get("status") == "success" else "failed",
                int(bt.get("rows_created_or_updated") or 0),
            )
            if bt.get("status") != "success":
                raise RuntimeError(str(bt.get("message") or "backtest fallito"))

            up_feat = SotFeatureService().build_upcoming_features_for_season(db, season)
            mark_step(
                "build_upcoming_features",
                "success" if up_feat.get("status") == "success" else "failed",
                int(up_feat.get("feature_rows_created_or_updated") or 0),
            )
            if up_feat.get("status") != "success":
                raise RuntimeError(str(up_feat.get("message") or "build upcoming features fallito"))

            up_pred = SotPredictionService().generate_upcoming_predictions_for_season(db, season)
            mark_step(
                "generate_upcoming_predictions",
                "success" if up_pred.get("status") == "success" else "failed",
                int(up_pred.get("predictions_created_or_updated") or 0),
            )
            if up_pred.get("status") != "success":
                raise RuntimeError(str(up_pred.get("message") or "generate upcoming predictions fallito"))

            profiles = PlayerSotProfileService().build_for_season(db, season)
            mark_step(
                "build_player_sot_profiles",
                "success" if profiles.get("status") == "success" else "failed",
                int(profiles.get("profiles_created_or_updated") or 0),
            )
            if profiles.get("status") != "success":
                raise RuntimeError(str(profiles.get("message") or "build player profiles fallito"))

            dash = self.dashboard_serie_a(db, season)
            summary = {
                "fixtures_total": int(dash.get("fixtures_total") or 0),
                "fixtures_completed": int(dash.get("fixtures_completed") or 0),
                "upcoming_fixtures_total": int(dash.get("upcoming_fixtures_total") or 0),
                "next_round": dash.get("next_round"),
                "team_stats_coverage_pct": float(dash.get("team_stats_coverage_pct") or 0.0),
                "player_stats_coverage_pct": float(dash.get("player_stats_coverage_pct") or 0.0),
                "lineups_coverage_pct": float(dash.get("lineups_coverage_pct") or 0.0),
                "sot_feature_coverage_pct": float(dash.get("sot_feature_coverage_pct") or 0.0),
                "sot_predictions_coverage_pct": float(dash.get("sot_predictions_coverage_pct") or 0.0),
            }
            result = {"status": "success", "season": season, "steps": steps, "summary": summary}
            self._finish_run(
                db,
                run,
                success=True,
                records_processed=sum(int(s.get("records_processed") or 0) for s in steps),
                meta_merge={"result": result},
            )
            return result
        except Exception as exc:
            failed_step = next((s["name"] for s in steps if s.get("status") == "failed"), None)
            result = {
                "status": "error",
                "season": season,
                "failed_step": failed_step,
                "message": str(exc),
                "steps": steps,
            }
            self._finish_run(
                db,
                run,
                success=False,
                records_processed=sum(int(s.get("records_processed") or 0) for s in steps),
                error=str(exc),
                meta_merge={"result": result},
            )
            return result

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
                    parsed = statistics_list_to_fields(block.get("statistics"))
                    side = (
                        "home"
                        if team.id == f.home_team_id
                        else "away"
                        if team.id == f.away_team_id
                        else None
                    )
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
                            side=side,
                            raw_json=block,
                        )
                        db.add(row)
                    else:
                        row.side = side
                        row.raw_json = block
                    apply_parsed_to_row(row, parsed)
                    processed += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=processed)
        except Exception as exc:
            logger.exception("sync_completed_fixture_team_stats failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def sync_serie_a_team_stats_admin(self, db: Session, season: int) -> dict[str, Any]:
        """Importa statistiche squadra per partite concluse; non interrompe il job su singole fixture."""
        summary: dict[str, Any] = {
            "status": "pending",
            "season": season,
            "fixtures_completed": 0,
            "fixtures_processed": 0,
            "fixtures_with_stats": 0,
            "team_stats_rows_created_or_updated": 0,
            "missing_stats": [],
            "errors": [],
        }
        run = self._begin_run(db, "serie_a_team_stats", meta={"season": season, "step": "team_stats"})
        try:
            settings = get_settings()
            league = self._serie_a_league_by_settings(db)
            if int(league.api_league_id) != int(settings.default_league_id):
                logger.warning(
                    "sync team stats: league api_league_id=%s vs settings default_league_id=%s",
                    league.api_league_id,
                    settings.default_league_id,
                )
            season_row = self._serie_a_season_row(db, season)
            fixtures_list = db.scalars(
                select(Fixture)
                .where(
                    Fixture.season_id == season_row.id,
                    Fixture.status.in_(FINISHED_STATUSES),
                )
                .order_by(Fixture.id.asc()),
            ).all()
            summary["fixtures_completed"] = len(fixtures_list)

            for f in fixtures_list:
                rows_this = 0
                try:
                    stats_payload = self._client.get_fixture_statistics(int(f.api_fixture_id))
                except ApiFootballError as exc:
                    logger.warning(
                        "fixture %s api %s: API error %s",
                        f.id,
                        f.api_fixture_id,
                        exc,
                    )
                    summary["errors"].append(
                        {
                            "fixture_id": f.id,
                            "api_fixture_id": int(f.api_fixture_id),
                            "message": str(exc),
                        },
                    )
                    summary["fixtures_processed"] += 1
                    continue

                if not stats_payload:
                    summary["missing_stats"].append(
                        {
                            "fixture_id": f.id,
                            "api_fixture_id": int(f.api_fixture_id),
                            "reason": "empty_response",
                        },
                    )
                    summary["fixtures_processed"] += 1
                    continue

                for block in stats_payload:
                    tid = (block.get("team") or {}).get("id")
                    if tid is None:
                        continue
                    team_api = int(tid)
                    team = db.scalar(select(Team).where(Team.api_team_id == team_api))
                    if team is None:
                        continue
                    side = (
                        "home"
                        if team.id == f.home_team_id
                        else "away"
                        if team.id == f.away_team_id
                        else None
                    )
                    parsed = statistics_list_to_fields(block.get("statistics"))
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
                            side=side,
                            raw_json=block,
                        )
                        db.add(row)
                    else:
                        row.side = side
                        row.raw_json = block
                    apply_parsed_to_row(row, parsed)
                    rows_this += 1
                    summary["team_stats_rows_created_or_updated"] += 1

                summary["fixtures_processed"] += 1
                if rows_this >= 2:
                    summary["fixtures_with_stats"] += 1
                elif rows_this == 0:
                    summary["missing_stats"].append(
                        {
                            "fixture_id": f.id,
                            "api_fixture_id": int(f.api_fixture_id),
                            "reason": "no_team_rows_saved",
                        },
                    )
                else:
                    summary["missing_stats"].append(
                        {
                            "fixture_id": f.id,
                            "api_fixture_id": int(f.api_fixture_id),
                            "reason": f"partial_rows_{rows_this}",
                        },
                    )

            db.commit()
            summary["status"] = "success"
            self._finish_run(
                db,
                run,
                success=True,
                records_processed=int(summary["team_stats_rows_created_or_updated"]),
                meta_merge={"summary": {k: v for k, v in summary.items() if k != "status"}},
            )
        except Exception as exc:
            logger.exception("sync_serie_a_team_stats_admin failed")
            db.rollback()
            summary["status"] = "error"
            summary["message"] = str(exc)
            try:
                self._finish_run(
                    db,
                    run,
                    success=False,
                    records_processed=int(summary.get("team_stats_rows_created_or_updated") or 0),
                    error=str(exc),
                    meta_merge={"summary": {k: v for k, v in summary.items() if k not in ("status", "message")}},
                )
            except Exception:
                logger.exception("could not finalize ingestion_run after team stats failure")

        summary["ingestion_run_id"] = run.id
        return summary

    def serie_a_team_stats_data_health(self, db: Session, season: int) -> dict[str, Any]:
        try:
            season_row = self._serie_a_season_row(db, season)
        except ValueError:
            return {
                "fixtures_completed": 0,
                "fixtures_with_team_stats": 0,
                "fixtures_missing_team_stats": 0,
                "missing_fixture_ids": [],
                "team_stats_rows_total": 0,
                "team_stats_coverage_pct": 0.0,
            }

        fixtures_completed = db.scalars(
            select(Fixture).where(
                Fixture.season_id == season_row.id,
                Fixture.status.in_(FINISHED_STATUSES),
            ),
        ).all()
        n_completed = len(fixtures_completed)
        completed_ids = {f.id for f in fixtures_completed}

        if not completed_ids:
            return {
                "fixtures_completed": 0,
                "fixtures_with_team_stats": 0,
                "fixtures_missing_team_stats": 0,
                "missing_fixture_ids": [],
                "team_stats_rows_total": 0,
                "team_stats_coverage_pct": 0.0,
            }

        counts_rows = db.execute(
            select(FixtureTeamStat.fixture_id, func.count())
            .where(FixtureTeamStat.fixture_id.in_(completed_ids))
            .group_by(FixtureTeamStat.fixture_id),
        ).all()
        counts = {int(fid): int(n) for fid, n in counts_rows}

        fixtures_with_two = sum(1 for fid in completed_ids if counts.get(fid, 0) >= 2)
        missing_ids = sorted(fid for fid in completed_ids if counts.get(fid, 0) < 2)

        team_stats_rows_total = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureTeamStat)
                .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
                .where(Fixture.season_id == season_row.id),
            )
            or 0,
        )

        pct = round(100.0 * fixtures_with_two / n_completed, 2) if n_completed else 0.0

        return {
            "fixtures_completed": n_completed,
            "fixtures_with_team_stats": fixtures_with_two,
            "fixtures_missing_team_stats": len(missing_ids),
            "missing_fixture_ids": missing_ids,
            "team_stats_rows_total": team_stats_rows_total,
            "team_stats_coverage_pct": pct,
        }

    def serie_a_player_stats_data_health(self, db: Session, season: int) -> dict[str, Any]:
        try:
            season_row = self._serie_a_season_row(db, season)
        except ValueError:
            return {
                "fixtures_completed": 0,
                "fixtures_with_player_stats": 0,
                "fixtures_missing_player_stats": 0,
                "player_stats_rows_total": 0,
                "player_stats_coverage_pct": 0.0,
                "missing_fixture_ids": [],
            }
        fixtures_completed = db.scalars(
            select(Fixture).where(
                Fixture.season_id == season_row.id,
                Fixture.status.in_(FINISHED_STATUSES),
            ),
        ).all()
        completed_ids = {f.id for f in fixtures_completed}
        n_completed = len(completed_ids)
        if not completed_ids:
            return {
                "fixtures_completed": 0,
                "fixtures_with_player_stats": 0,
                "fixtures_missing_player_stats": 0,
                "player_stats_rows_total": 0,
                "player_stats_coverage_pct": 0.0,
                "missing_fixture_ids": [],
            }
        with_rows = db.scalars(
            select(FixturePlayerStat.fixture_id)
            .where(FixturePlayerStat.fixture_id.in_(completed_ids))
            .distinct(),
        ).all()
        with_set = {int(x) for x in with_rows}
        fixtures_with_player_stats = len(with_set)
        missing_fixture_ids = sorted(completed_ids - with_set)
        player_stats_rows_total = int(
            db.scalar(
                select(func.count())
                .select_from(FixturePlayerStat)
                .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
                .where(Fixture.season_id == season_row.id),
            )
            or 0,
        )
        pct = round(100.0 * fixtures_with_player_stats / n_completed, 2) if n_completed else 0.0
        return {
            "fixtures_completed": n_completed,
            "fixtures_with_player_stats": fixtures_with_player_stats,
            "fixtures_missing_player_stats": len(missing_fixture_ids),
            "player_stats_rows_total": player_stats_rows_total,
            "player_stats_coverage_pct": pct,
            "missing_fixture_ids": missing_fixture_ids,
        }

    def serie_a_lineups_data_health(self, db: Session, season: int) -> dict[str, Any]:
        try:
            season_row = self._serie_a_season_row(db, season)
        except ValueError:
            return {
                "fixtures_completed": 0,
                "fixtures_with_lineups": 0,
                "fixtures_missing_lineups": 0,
                "lineups_rows_total": 0,
                "lineups_coverage_pct": 0.0,
                "missing_fixture_ids": [],
            }
        fixtures_completed = db.scalars(
            select(Fixture).where(
                Fixture.season_id == season_row.id,
                Fixture.status.in_(FINISHED_STATUSES),
            ),
        ).all()
        completed_ids = {f.id for f in fixtures_completed}
        n_completed = len(completed_ids)
        if not completed_ids:
            return {
                "fixtures_completed": 0,
                "fixtures_with_lineups": 0,
                "fixtures_missing_lineups": 0,
                "lineups_rows_total": 0,
                "lineups_coverage_pct": 0.0,
                "missing_fixture_ids": [],
            }
        with_lineup = db.scalars(
            select(FixtureLineup.fixture_id)
            .where(FixtureLineup.fixture_id.in_(completed_ids))
            .distinct(),
        ).all()
        with_set = {int(x) for x in with_lineup}
        fixtures_with_lineups = len(with_set)
        missing_fixture_ids = sorted(completed_ids - with_set)
        lineups_rows_total = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureLineup)
                .join(Fixture, Fixture.id == FixtureLineup.fixture_id)
                .where(Fixture.season_id == season_row.id),
            )
            or 0,
        )
        pct = round(100.0 * fixtures_with_lineups / n_completed, 2) if n_completed else 0.0
        return {
            "fixtures_completed": n_completed,
            "fixtures_with_lineups": fixtures_with_lineups,
            "fixtures_missing_lineups": len(missing_fixture_ids),
            "lineups_rows_total": lineups_rows_total,
            "lineups_coverage_pct": pct,
            "missing_fixture_ids": missing_fixture_ids,
        }

    @staticmethod
    def _apply_parsed_player_stat(
        row: FixturePlayerStat,
        parsed: dict[str, Any],
        *,
        position: str | None,
        captain: bool | None,
        substitute: bool | None,
        minutes_fallback: int | None,
    ) -> None:
        row.position = position
        row.captain = captain
        row.substitute = substitute
        if "minutes" in parsed:
            row.minutes = int(parsed["minutes"])
        elif minutes_fallback is not None:
            row.minutes = minutes_fallback
        if "rating" in parsed and parsed["rating"] is not None:
            row.rating = float(parsed["rating"])
        if "passes_accuracy_pct" in parsed and parsed["passes_accuracy_pct"] is not None:
            row.passes_accuracy_pct = float(parsed["passes_accuracy_pct"])
        int_attrs = (
            "shots_total",
            "shots_on_target",
            "goals",
            "assists",
            "passes_total",
            "passes_key",
            "tackles_total",
            "tackles_blocks",
            "interceptions",
            "duels_total",
            "duels_won",
            "dribbles_attempts",
            "dribbles_success",
            "fouls_drawn",
            "fouls_committed",
            "yellow_cards",
            "red_cards",
        )
        for attr in int_attrs:
            if attr in parsed:
                setattr(row, attr, int(parsed[attr]))

    def ingest_serie_a_player_stats(
        self,
        db: Session,
        season: int,
        *,
        run_source: str = "serie_a_player_stats",
    ) -> IngestionRun:
        run = self._begin_run(db, run_source, meta={"season": season})
        missing_fixture_ids: list[int] = []
        processed = 0
        try:
            season_row = self._serie_a_season_row(db, season)
            fixtures = db.scalars(
                select(Fixture).where(
                    Fixture.season_id == season_row.id,
                    Fixture.status.in_(FINISHED_STATUSES),
                ),
            ).all()
            for f in fixtures:
                try:
                    groups = self._client.get_fixture_players(int(f.api_fixture_id))
                except Exception as exc:
                    logger.warning(
                        "ingest player_stats: fixture_id=%s api_fixture_id=%s err=%s",
                        f.id,
                        f.api_fixture_id,
                        exc,
                    )
                    missing_fixture_ids.append(f.id)
                    continue
                if not groups:
                    missing_fixture_ids.append(f.id)
                    continue
                had_stat = False
                for group in groups:
                    team_block = group.get("team") or {}
                    try:
                        team_api = int(team_block["id"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    team = db.scalar(select(Team).where(Team.api_team_id == team_api))
                    if team is None:
                        continue
                    for entry in group.get("players") or []:
                        try:
                            p = entry.get("player") or {}
                            api_player_id = int(p["id"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        name = str(p.get("name") or "")
                        stats_list = entry.get("statistics")
                        if not isinstance(stats_list, list):
                            stats_list = []
                        try:
                            parsed = dict(parse_fixture_player_statistics(stats_list))
                            cap, sub = player_entry_flags(p, entry)
                            pos_games = parsed.pop("position", None)
                            if isinstance(pos_games, str) and pos_games.strip():
                                pos = pos_games.strip()[:32]
                            else:
                                pos = player_position(p)
                            c_g = parsed.pop("captain", None)
                            s_g = parsed.pop("substitute", None)
                            if c_g is not None:
                                cap = c_g
                            if s_g is not None:
                                sub = s_g
                            minutes_fb = _extract_minutes_from_statistics(stats_list)
                            player = db.scalar(select(Player).where(Player.api_player_id == api_player_id))
                            if player is None:
                                player = Player(
                                    api_player_id=api_player_id,
                                    name=name or f"Player {api_player_id}",
                                    team_id=team.id,
                                    raw_json=p,
                                )
                                db.add(player)
                                db.flush()
                            else:
                                if name:
                                    player.name = name
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
                                    raw_json=entry,
                                )
                                db.add(row)
                            else:
                                row.team_id = team.id
                                row.raw_json = entry
                            self._apply_parsed_player_stat(
                                row,
                                parsed,
                                position=pos,
                                captain=cap,
                                substitute=sub,
                                minutes_fallback=minutes_fb,
                            )
                            processed += 1
                            had_stat = True
                        except Exception as row_exc:
                            logger.warning(
                                "ingest player_stats row skip fixture_id=%s player_api=%s: %s",
                                f.id,
                                api_player_id,
                                row_exc,
                            )
                            continue
                if not had_stat:
                    missing_fixture_ids.append(f.id)
            db.commit()
            return self._finish_run(
                db,
                run,
                success=True,
                records_processed=processed,
                meta_merge={
                    "missing_fixture_ids": sorted(set(missing_fixture_ids)),
                    "fixtures_completed": len(fixtures),
                },
            )
        except Exception as exc:
            logger.exception("ingest_serie_a_player_stats failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def sync_completed_fixture_player_stats(self, db: Session, season: int = 2025) -> IngestionRun:
        return self.ingest_serie_a_player_stats(
            db,
            season,
            run_source="sync_completed_fixture_player_stats",
        )

    def ingest_serie_a_lineups(
        self,
        db: Session,
        season: int,
        *,
        run_source: str = "serie_a_lineups",
    ) -> IngestionRun:
        run = self._begin_run(db, run_source, meta={"season": season})
        processed = 0
        try:
            season_row = self._serie_a_season_row(db, season)
            fixtures = db.scalars(
                select(Fixture).where(
                    Fixture.season_id == season_row.id,
                    Fixture.status.in_(FINISHED_STATUSES),
                ),
            ).all()
            for f in fixtures:
                try:
                    blocks = self._client.get_fixture_lineups(int(f.api_fixture_id))
                except Exception as exc:
                    logger.warning(
                        "ingest lineups: fixture_id=%s api_fixture_id=%s err=%s",
                        f.id,
                        f.api_fixture_id,
                        exc,
                    )
                    continue
                for block in blocks:
                    team_block = block.get("team") or {}
                    try:
                        team_api = int(team_block["id"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    team = db.scalar(select(Team).where(Team.api_team_id == team_api))
                    if team is None:
                        continue
                    formation = block.get("formation")
                    formation_str = str(formation) if formation else None
                    coach = block.get("coach")
                    coach_name = None
                    if isinstance(coach, dict):
                        cn = coach.get("name")
                        if cn:
                            coach_name = str(cn)[:255]
                    start_xi = block.get("startXI")
                    substitutes = block.get("substitutes")
                    lineup_json = {
                        "startXI": start_xi,
                        "substitutes": substitutes,
                        "coach": coach,
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
                            coach_name=coach_name,
                            start_xi=start_xi,
                            substitutes=substitutes,
                            lineup_json=lineup_json,
                            raw_json=block,
                        )
                        db.add(row)
                    else:
                        row.formation = formation_str
                        row.coach_name = coach_name
                        row.start_xi = start_xi  # type: ignore[assignment]
                        row.substitutes = substitutes  # type: ignore[assignment]
                        row.lineup_json = lineup_json
                        row.raw_json = block
                    processed += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=processed)
        except Exception as exc:
            logger.exception("ingest_serie_a_lineups failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def sync_completed_fixture_lineups(self, db: Session, season: int = 2025) -> IngestionRun:
        return self.ingest_serie_a_lineups(db, season, run_source="sync_completed_fixture_lineups")

    def ingest_serie_a_availability(self, db: Session, season: int) -> IngestionRun:
        """Importa injuries API-Football come eventi di disponibilità (solo debug; non usato nel baseline)."""
        run = self._begin_run(db, "serie_a_availability", meta={"season": season})
        settings = get_settings()
        try:
            season_row = self._serie_a_season_row(db, season)
        except ValueError as exc:
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))
        try:
            if not (settings.api_football_key or "").strip():
                db.commit()
                return self._finish_run(
                    db,
                    run,
                    success=True,
                    records_processed=0,
                    meta_merge={"status": "skipped", "reason": "API key assente"},
                )
            try:
                items = self._client.get_injuries(int(settings.default_league_id), int(season))
            except ApiFootballError as exc:
                db.commit()
                return self._finish_run(
                    db,
                    run,
                    success=True,
                    records_processed=0,
                    meta_merge={"status": "skipped", "reason": str(exc)},
                )
            if not items:
                db.commit()
                return self._finish_run(
                    db,
                    run,
                    success=True,
                    records_processed=0,
                    meta_merge={"status": "skipped", "reason": "Nessun record injuries dalla API"},
                )
            first = items[0]
            if not isinstance(first, dict) or "player" not in first:
                db.commit()
                return self._finish_run(
                    db,
                    run,
                    success=True,
                    records_processed=0,
                    meta_merge={
                        "status": "skipped",
                        "reason": "Formato risposta injuries non gestito in questa versione",
                    },
                )

            db.execute(
                delete(PlayerAvailabilityEvent).where(
                    PlayerAvailabilityEvent.season_id == season_row.id,
                    PlayerAvailabilityEvent.source == "api_football_injuries",
                ),
            )
            n_ok = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                pl = it.get("player") or {}
                tm = it.get("team") or {}
                api_pid = pl.get("id")
                name = str(pl.get("name") or "").strip() or "Nome non disponibile"
                team = None
                try:
                    if tm.get("id") is not None:
                        team = db.scalar(select(Team).where(Team.api_team_id == int(tm["id"])))
                except (TypeError, ValueError):
                    pass
                player = None
                try:
                    if api_pid is not None:
                        player = db.scalar(select(Player).where(Player.api_player_id == int(api_pid)))
                except (TypeError, ValueError):
                    pass
                typ = it.get("type") or "injury"
                if isinstance(typ, dict):
                    typ = typ.get("type") or "injury"
                typ_s = str(typ)[:64]
                reason = it.get("reason")
                if reason is not None:
                    reason = str(reason)[:512]
                ev = PlayerAvailabilityEvent(
                    season_id=season_row.id,
                    team_id=team.id if team else None,
                    player_id=player.id if player else None,
                    api_player_id=int(api_pid) if api_pid is not None else None,
                    player_name=name,
                    fixture_id=None,
                    type=typ_s,
                    reason=reason,
                    start_date=None,
                    end_date=None,
                    source="api_football_injuries",
                    raw_json=it,
                )
                db.add(ev)
                n_ok += 1
            db.commit()
            return self._finish_run(db, run, success=True, records_processed=n_ok)
        except Exception as exc:
            logger.exception("ingest_serie_a_availability failed")
            db.rollback()
            return self._finish_run(db, run, success=False, records_processed=0, error=str(exc))

    def bootstrap_serie_a(self, db: Session, season: int = 2025) -> list[IngestionRun]:
        return self.bootstrap_serie_a_admin(db, season)

    @staticmethod
    def dashboard_serie_a_empty() -> dict[str, Any]:
        return {
            "league": None,
            "season": None,
            "teams_total": 0,
            "fixtures_total": 0,
            "fixtures_completed": 0,
            "fixtures_scheduled": 0,
            "fixtures_live_or_unknown": 0,
            "fixtures_with_team_stats": 0,
            "team_stats_rows_total": 0,
            "team_stats_coverage_pct": 0.0,
            "fixtures_with_player_stats": 0,
            "player_stats_rows_total": 0,
            "player_stats_coverage_pct": 0.0,
            "fixtures_with_lineups": 0,
            "lineups_rows_total": 0,
            "lineups_coverage_pct": 0.0,
            "players_profiled_total": 0,
            "player_profiles_total": 0,
            "player_profiles_sot_data_suspicious": False,
            "availability_events_total": 0,
            "sot_feature_rows_total": 0,
            "sot_feature_expected_rows": 0,
            "sot_feature_coverage_pct": 0.0,
            "sot_predictions_total": 0,
            "sot_predictions_expected": 0,
            "sot_predictions_coverage_pct": 0.0,
            "avg_expected_sot": 0.0,
            "avg_prediction_confidence": 0.0,
            "sot_backtests_total": 0,
            "sot_backtests_expected": 0,
            "sot_backtest_coverage_pct": 0.0,
            "sot_backtest_mae": 0.0,
            "sot_backtest_rmse": 0.0,
            "sot_backtest_avg_expected_sot": 0.0,
            "sot_backtest_avg_actual_sot": 0.0,
            "upcoming_fixtures_total": 0,
            "upcoming_sot_feature_rows_total": 0,
            "upcoming_sot_predictions_total": 0,
            "standings_snapshot_available": False,
            "standings_snapshot_at": None,
            "next_round": None,
            "v02_predictions_upcoming": 0,
            "v02_avg_total_adjustment": 0.0,
            "v02_avg_player_adjustment": 0.0,
            "v02_avg_h2h_adjustment": 0.0,
            "v02_avg_motivation_adjustment": 0.0,
            "v02_matches_with_context_warning": 0,
            "last_ingestion_run": None,
            "data_coverage": {
                "teams_imported": False,
                "fixtures_imported": False,
            },
        }

    def dashboard_serie_a(self, db: Session, season: int) -> dict[str, Any]:
        try:
            return self._dashboard_serie_a_impl(db, season)
        except (ProgrammingError, OperationalError) as exc:
            logger.warning(
                "dashboard_serie_a: errore database (%s)",
                exc.__class__.__name__,
                exc_info=True,
            )
            return self.dashboard_serie_a_empty()

    def _dashboard_serie_a_impl(self, db: Session, season: int) -> dict[str, Any]:
        settings = get_settings()
        league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            return self.dashboard_serie_a_empty()

        season_row = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season),
        )
        if season_row is None:
            return self.dashboard_serie_a_empty()

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

        health = self.serie_a_team_stats_data_health(db, season)
        ph = self.serie_a_player_stats_data_health(db, season)
        lh = self.serie_a_lineups_data_health(db, season)
        players_profiled_total = int(
            db.scalar(
                select(func.count()).select_from(PlayerSotProfile).where(
                    PlayerSotProfile.season_id == season_row.id,
                ),
            )
            or 0,
        )
        profiles_with_positive_sot = int(
            db.scalar(
                select(func.count()).select_from(PlayerSotProfile).where(
                    PlayerSotProfile.season_id == season_row.id,
                    or_(
                        PlayerSotProfile.shots_on_target_per90 > 0,
                        PlayerSotProfile.total_shots_on_target > 0,
                    ),
                ),
            )
            or 0,
        )
        player_profiles_sot_data_suspicious = (
            players_profiled_total > 0 and profiles_with_positive_sot == 0
        )
        availability_events_total = int(
            db.scalar(
                select(func.count()).select_from(PlayerAvailabilityEvent).where(
                    PlayerAvailabilityEvent.season_id == season_row.id,
                ),
            )
            or 0,
        )

        from app.services.sot_feature_service import SotFeatureService

        sot_sum = SotFeatureService().get_season_summary(db, season)

        from app.services.sot_prediction_service import SotPredictionService

        pred_sum = SotPredictionService().get_season_predictions_summary(db, season)

        from app.services.sot_backtest_service import SotBacktestService

        bt_sum = SotBacktestService().get_dashboard_backtest_block(db, season)

        last_run = None
        try:
            last_run = db.scalar(
                select(IngestionRun).order_by(
                    IngestionRun.started_at.desc().nulls_last(),
                    IngestionRun.id.desc(),
                ),
            )
        except (ProgrammingError, OperationalError):
            logger.warning("dashboard_serie_a: lettura ingestion_runs fallita", exc_info=True)

        season_fixtures = db.scalars(select(Fixture).where(Fixture.season_id == season_row.id)).all()
        upcoming_ids = [
            f.id for f in season_fixtures if fixture_eligible_for_upcoming_sot(f.status, f.kickoff_at)
        ]
        next_round = None
        if upcoming_ids:
            first_upcoming = min(
                (f for f in season_fixtures if f.id in upcoming_ids),
                key=lambda x: (x.kickoff_at, x.id),
            )
            next_round = first_upcoming.round
        upcoming_fixtures_total = len(upcoming_ids)
        if not upcoming_ids:
            upcoming_sot_feature_rows_total = 0
            upcoming_sot_predictions_total = 0
        else:
            upcoming_sot_feature_rows_total = int(
                db.scalar(
                    select(func.count()).select_from(TeamSotFeature).where(
                        TeamSotFeature.fixture_id.in_(upcoming_ids),
                    ),
                )
                or 0,
            )
            upcoming_sot_predictions_total = int(
                db.scalar(
                    select(func.count()).select_from(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id.in_(upcoming_ids),
                    ),
                )
                or 0,
            )

        latest_standings_snapshot = db.scalar(
            select(StandingsSnapshot)
            .where(StandingsSnapshot.season_id == season_row.id)
            .order_by(StandingsSnapshot.snapshot_at.desc(), StandingsSnapshot.id.desc()),
        )
        from app.services.sot_prediction_v02_service import SotPredictionV02Service
        v02_block = SotPredictionV02Service().dashboard_block(db, season)

        return {
            "league": league,
            "season": season_row,
            "teams_total": teams_total,
            "fixtures_total": fixtures_total,
            "fixtures_completed": fixtures_completed,
            "fixtures_scheduled": fixtures_scheduled,
            "fixtures_live_or_unknown": fixtures_live_or_unknown,
            "fixtures_with_team_stats": health["fixtures_with_team_stats"],
            "team_stats_rows_total": health["team_stats_rows_total"],
            "team_stats_coverage_pct": health["team_stats_coverage_pct"],
            "fixtures_with_player_stats": ph["fixtures_with_player_stats"],
            "player_stats_rows_total": ph["player_stats_rows_total"],
            "player_stats_coverage_pct": ph["player_stats_coverage_pct"],
            "fixtures_with_lineups": lh["fixtures_with_lineups"],
            "lineups_rows_total": lh["lineups_rows_total"],
            "lineups_coverage_pct": lh["lineups_coverage_pct"],
            "players_profiled_total": players_profiled_total,
            "player_profiles_total": players_profiled_total,
            "player_profiles_sot_data_suspicious": player_profiles_sot_data_suspicious,
            "availability_events_total": availability_events_total,
            "sot_feature_rows_total": sot_sum["feature_rows_total"],
            "sot_feature_expected_rows": sot_sum["expected_feature_rows"],
            "sot_feature_coverage_pct": float(sot_sum["coverage_pct"]),
            "sot_predictions_total": pred_sum["predictions_total"],
            "sot_predictions_expected": pred_sum["feature_rows_total"],
            "sot_predictions_coverage_pct": float(pred_sum["coverage_pct"]),
            "avg_expected_sot": float(pred_sum["avg_expected_sot"]),
            "avg_prediction_confidence": float(pred_sum["avg_confidence_score"]),
            "sot_backtests_total": bt_sum["sot_backtests_total"],
            "sot_backtests_expected": bt_sum["sot_backtests_expected"],
            "sot_backtest_coverage_pct": float(bt_sum["sot_backtest_coverage_pct"]),
            "sot_backtest_mae": float(bt_sum["sot_backtest_mae"]),
            "sot_backtest_rmse": float(bt_sum["sot_backtest_rmse"]),
            "sot_backtest_avg_expected_sot": float(bt_sum["sot_backtest_avg_expected_sot"]),
            "sot_backtest_avg_actual_sot": float(bt_sum["sot_backtest_avg_actual_sot"]),
            "upcoming_fixtures_total": upcoming_fixtures_total,
            "upcoming_sot_feature_rows_total": upcoming_sot_feature_rows_total,
            "upcoming_sot_predictions_total": upcoming_sot_predictions_total,
            "standings_snapshot_available": latest_standings_snapshot is not None,
            "standings_snapshot_at": latest_standings_snapshot.snapshot_at if latest_standings_snapshot else None,
            "next_round": next_round,
            "v02_predictions_upcoming": int(v02_block.get("v02_predictions_upcoming") or 0),
            "v02_avg_total_adjustment": float(v02_block.get("avg_total_adjustment") or 0.0),
            "v02_avg_player_adjustment": float(v02_block.get("avg_player_adjustment") or 0.0),
            "v02_avg_h2h_adjustment": float(v02_block.get("avg_h2h_adjustment") or 0.0),
            "v02_avg_motivation_adjustment": float(v02_block.get("avg_motivation_adjustment") or 0.0),
            "v02_matches_with_context_warning": int(v02_block.get("matches_with_context_warning") or 0),
            "last_ingestion_run": last_run,
            "data_coverage": {
                "teams_imported": teams_imported,
                "fixtures_imported": fixtures_imported,
            },
        }
