from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES, fixture_eligible_for_upcoming_sot
from app.models import Competition, Fixture, League, Season
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.competition_service import CompetitionService
from app.services.ingestion_service import IngestionService
from app.services.player_data.profile_builder import build_player_season_profiles_for_competition
from app.services.player_data.player_match_stats_ingestion import ingest_competition_player_match_stats

logger = logging.getLogger(__name__)


class CompetitionIngestionService:
    def __init__(
        self,
        client: ApiFootballClient | None = None,
    ) -> None:
        self._ingest = IngestionService(client)
        self._comp_svc = CompetitionService(client)

    def _competition(self, db: Session, competition_id: int) -> Competition:
        return self._comp_svc.get_by_id_or_raise(db, competition_id)

    def _ensure_league_season(self, db: Session, comp: Competition) -> tuple[League, Season]:
        league = None
        if comp.league_id:
            league = db.get(League, comp.league_id)
        if league is None:
            league = db.scalar(
                select(League).where(League.api_league_id == comp.provider_league_id)
            )
        if league is None:
            picked = self._ingest._client.get(
                "leagues",
                {"id": comp.provider_league_id, "season": comp.season},
            )
            items = list(picked.get("response") or [])
            if not items:
                raise ApiFootballError(
                    f"Lega provider_league_id={comp.provider_league_id} non trovata via API"
                )
            league = self._ingest._upsert_league_from_picked(db, items[0])
            comp.league_id = league.id

        season_row = None
        if comp.season_id:
            season_row = db.get(Season, comp.season_id)
        if season_row is None:
            season_row = db.scalar(
                select(Season).where(Season.league_id == league.id, Season.year == comp.season)
            )
        if season_row is None:
            picked = self._ingest._client.get(
                "leagues",
                {"id": comp.provider_league_id, "season": comp.season},
            )
            items = list(picked.get("response") or [])
            if items:
                self._ingest._upsert_season_from_picked(db, league, items[0], comp.season)
            season_row = db.scalar(
                select(Season).where(Season.league_id == league.id, Season.year == comp.season)
            )
        if season_row is None:
            raise ValueError(f"Stagione {comp.season} non trovata per competition {comp.key}")

        comp.league_id = league.id
        comp.season_id = season_row.id
        db.add(comp)
        db.commit()
        db.refresh(comp)
        return league, season_row

    def bootstrap(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        league, season_row = self._ensure_league_season(db, comp)

        try:
            team_items = self._ingest._client.get_teams(comp.provider_league_id, comp.season)
            fixture_items = self._ingest._client.get_fixtures(
                comp.provider_league_id, comp.season, status=None
            )
        except ApiFootballError as exc:
            return {"status": "error", "message": str(exc), "dry_run": dry_run}

        finished = [
            f for f in fixture_items
            if str(((f.get("fixture") or {}).get("status") or {}).get("short") or "").upper()
            in FINISHED_STATUSES
        ]
        upcoming = [f for f in fixture_items if f not in finished]
        estimate_api_calls = 2 + len(finished) * 3

        preview = {
            "competition_id": comp.id,
            "competition_key": comp.key,
            "teams_found": len(team_items),
            "fixtures_found": len(fixture_items),
            "finished_fixtures": len(finished),
            "upcoming_fixtures": len(upcoming),
            "estimated_api_calls": estimate_api_calls,
            "dry_run": dry_run,
        }

        if dry_run:
            preview["status"] = "dry_run"
            return preview

        runs = []
        for fn in (
            lambda: self._ingest.bootstrap_sync_league_for_competition(db, comp),
            lambda: self._ingest.bootstrap_sync_season_for_competition(db, comp),
            lambda: self._ingest.bootstrap_sync_teams_for_competition(db, comp),
            lambda: self._ingest.bootstrap_sync_fixtures_for_competition(db, comp),
        ):
            run = fn()
            runs.append(
                {
                    "source": run.source,
                    "status": run.status,
                    "records_processed": run.records_processed,
                    "error_message": run.error_message,
                }
            )
            if run.status == "failed":
                break

        preview["status"] = "error" if any(r["status"] == "failed" for r in runs) else "ok"
        preview["runs"] = runs
        _ = league, season_row
        return preview

    def ingest_standings(self, db: Session, competition_id: int, *, dry_run: bool = False) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            return {"status": "dry_run", "competition_id": comp.id, "action": "ingest_standings"}
        run = self._ingest.ingest_standings_for_competition(db, comp)
        return {"status": run.status, "records_processed": run.records_processed}

    def ingest_team_stats(self, db: Session, competition_id: int, *, dry_run: bool = False) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            n = db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(
                    Fixture.competition_id == comp.id,
                    Fixture.status.in_(tuple(FINISHED_STATUSES)),
                )
            )
            return {
                "status": "dry_run",
                "competition_id": comp.id,
                "finished_fixtures": int(n or 0),
                "estimated_api_calls": int(n or 0) * 2,
            }
        return self._ingest.sync_team_stats_for_competition(db, comp)

    def ingest_player_match_stats(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            n = db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(
                    Fixture.competition_id == comp.id,
                    Fixture.status.in_(tuple(FINISHED_STATUSES)),
                )
            )
            return {
                "status": "dry_run",
                "competition_id": comp.id,
                "finished_fixtures": int(n or 0),
                "estimated_api_calls": int(n or 0),
            }
        return ingest_competition_player_match_stats(db, comp.id, force=force)

    def build_player_season_profiles(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            n = db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(Fixture.competition_id == comp.id)
            )
            return {"status": "dry_run", "competition_id": comp.id, "fixtures_in_competition": int(n or 0)}
        return build_player_season_profiles_for_competition(db, comp.id)

    def ingest_lineups(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
        fixture_id: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            return {"status": "dry_run", "competition_id": comp.id, "action": "ingest_lineups"}
        return self._ingest.ingest_lineups_for_competition(
            db, comp, fixture_id=fixture_id, force=force
        )

    def refresh_next_round(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        upcoming = [
            f
            for f in db.scalars(
                select(Fixture)
                .where(Fixture.competition_id == comp.id)
                .order_by(Fixture.kickoff_at.asc())
            ).all()
            if fixture_eligible_for_upcoming_sot(f)
        ]
        if dry_run:
            return {
                "status": "dry_run",
                "competition_id": comp.id,
                "upcoming_fixtures": len(upcoming),
            }

        from app.services.predictions_v11.baseline_v1_1_sot_service import (
            SotPredictionV11BaselineSotService,
        )
        from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import (
            SotPredictionV20LineupImpactService,
        )

        v11 = SotPredictionV11BaselineSotService()
        v20 = SotPredictionV20LineupImpactService()
        v11_result = v11.generate_for_competition(db, comp.id)
        v20_result = v20.generate_for_competition(db, comp.id)
        return {
            "status": "ok",
            "competition_id": comp.id,
            "upcoming_fixtures": len(upcoming),
            "v11": v11_result,
            "v20": v20_result,
        }
