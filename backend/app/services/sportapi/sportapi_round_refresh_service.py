"""Batch SportAPI per il prossimo turno: mapping, lineups, rose (admin)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixtureProviderLineup, FixtureProviderMapping, League, Season
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI
from app.services.ingestion_service import IngestionService
from app.services.player_data.squads import sync_team_squads
from app.services.sot_feature_service import SotFeatureService
from app.services.sot_prediction_service import _fixture_round_display
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService
from app.services.sportapi.sportapi_matching_service import SportApiMatchingService

logger = logging.getLogger(__name__)


class SportApiRoundRefreshService:
    def _season_row(self, db: Session, season_year: int) -> Season | None:
        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            league = db.scalar(select(League).where(League.api_league_id == get_settings().default_league_id))
        if league is None:
            return None
        return db.scalar(select(Season).where(Season.league_id == league.id, Season.year == int(season_year)))

    def upcoming_next_round_fixtures(self, db: Session, season_year: int, *, limit: int = 50) -> list[Fixture]:
        season = self._season_row(db, season_year)
        if season is None:
            return []
        feat = SotFeatureService()
        raw = feat.list_upcoming_fixtures_for_season(db, season.id)
        upcoming = [f for f in raw if (f.status or "").upper() not in FINISHED_STATUSES]
        upcoming.sort(key=lambda f: (f.kickoff_at, f.id))
        if upcoming:
            r0 = _fixture_round_display(upcoming[0]) or upcoming[0].round
            if r0:
                upcoming = [f for f in upcoming if (_fixture_round_display(f) or f.round) == r0]
            else:
                d0 = upcoming[0].kickoff_at.date()
                upcoming = [f for f in upcoming if f.kickoff_at.date() == d0]
        return upcoming[:limit]

    def _has_mapping(self, db: Session, fixture_id: int) -> bool:
        return (
            db.scalar(
                select(FixtureProviderMapping.id).where(
                    FixtureProviderMapping.fixture_id == int(fixture_id),
                    FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                ),
            )
            is not None
        )

    def _has_lineups(self, db: Session, fixture_id: int) -> bool:
        return (
            db.scalar(
                select(FixtureProviderLineup.id).where(
                    FixtureProviderLineup.fixture_id == int(fixture_id),
                    FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
                ),
            )
            is not None
        )

    def refresh_next_round_lineups(
        self,
        db: Session,
        season_year: int,
        *,
        force: bool = False,
        sync_squads: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        season = self._season_row(db, season_year)
        if season is None:
            return {"status": "error", "message": "Stagione non trovata", "fixtures": [], "estimated_api_calls": 0}

        fixtures = self.upcoming_next_round_fixtures(db, season_year, limit=limit)
        if not fixtures:
            return {"status": "success", "message": "Nessuna fixture upcoming", "fixtures": [], "estimated_api_calls": 0}

        lineup_svc = SportApiLineupService()
        match_svc = SportApiMatchingService()
        results: list[dict[str, Any]] = []
        api_calls = 0

        for fx in fixtures:
            fid = int(fx.id)
            row: dict[str, Any] = {
                "fixture_id": fid,
                "api_fixture_id": int(fx.api_fixture_id),
                "status": "ok",
                "mapping_ok": self._has_mapping(db, fid),
                "lineups_ok": self._has_lineups(db, fid),
                "confirmed": None,
                "fetched_at": None,
                "error": None,
            }
            try:
                need_mapping = force or not row["mapping_ok"]
                if need_mapping:
                    debug = match_svc.debug_match_fixture(db, fid)
                    api_calls += int(debug.get("api_calls") or 1)
                    best = debug.get("best_candidate") if isinstance(debug.get("best_candidate"), dict) else None
                    if best and debug.get("recommendation") == "AUTO_SAFE":
                        out_map = lineup_svc.confirm_mapping(
                            db,
                            fid,
                            provider_event_id=int(best["provider_event_id"]),
                            confidence_score=float(best.get("confidence_score") or 90),
                            matched_by="auto_timestamp_teams",
                            raw_payload=best,
                        )
                        if out_map.get("status") != "error":
                            row["mapping_ok"] = True
                    else:
                        row["status"] = "mapping_failed"
                        row["error"] = str(debug.get("message") or "Nessun candidato AUTO_SAFE")
                        results.append(row)
                        continue

                need_lineups = force or (row["mapping_ok"] and not row["lineups_ok"])
                if need_lineups and row["mapping_ok"]:
                    fetch_out = lineup_svc.fetch_and_persist_lineups(db, fid)
                    api_calls += 1
                    row["lineups_ok"] = fetch_out.get("status") == "success"
                    row["confirmed"] = fetch_out.get("confirmed")
                    row["fetched_at"] = fetch_out.get("fetched_at")
                    if fetch_out.get("status") != "success":
                        row["status"] = "lineups_failed"
                        row["error"] = str(fetch_out.get("message") or "fetch lineups fallito")
                elif row["mapping_ok"] and row["lineups_ok"]:
                    row["status"] = "skipped"

                if sync_squads:
                    sync_team_squads(db, int(season.year), [int(fx.home_team_id), int(fx.away_team_id)])

            except Exception as exc:  # noqa: BLE001
                logger.exception("refresh fixture %s", fid)
                row["status"] = "error"
                row["error"] = str(exc)[:300]
            results.append(row)

        return {
            "status": "success",
            "season": int(season_year),
            "fixtures_count": len(fixtures),
            "estimated_api_calls": api_calls,
            "results": results,
        }

    def sync_next_round_api_squads(self, db: Session, season_year: int, *, limit: int = 50) -> dict[str, Any]:
        season = self._season_row(db, season_year)
        if season is None:
            return {"status": "error", "message": "Stagione non trovata"}
        fixtures = self.upcoming_next_round_fixtures(db, season_year, limit=limit)
        team_ids = list(
            dict.fromkeys([int(fx.home_team_id) for fx in fixtures] + [int(fx.away_team_id) for fx in fixtures]),
        )
        if not team_ids:
            return {"status": "success", "teams_synced": 0, "message": "Nessuna squadra nel turno"}
        out = sync_team_squads(db, int(season.year), team_ids)
        out["fixtures_in_round"] = len(fixtures)
        return out
