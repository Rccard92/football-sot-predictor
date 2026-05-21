"""Batch SportAPI per il prossimo turno: mapping, lineups, rose (admin)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixtureProviderLineup, FixtureProviderMapping, League, Season, Team
from app.services.sportapi.lineup_refresh_impact_orchestrator import LineupRefreshImpactOrchestrator
from app.services.sportapi.lineup_refresh_snapshot_service import build_snapshot
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI
from app.services.ingestion_service import IngestionService
from app.services.player_data.squads import sync_team_squads
from app.services.sot_feature_service import SotFeatureService
from app.services.sot_prediction_service import _fixture_round_display
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService
from app.services.sportapi.sportapi_lineup_status import lineup_row_for_fixture
from app.services.sportapi.sportapi_matching_service import SportApiMatchingService

logger = logging.getLogger(__name__)

SKIP_FETCH_MINUTES = 10.0


def _fetched_at_age_minutes(fetched_at: datetime | None) -> float | None:
    if fetched_at is None:
        return None
    now = datetime.now(timezone.utc)
    ft = fetched_at
    if ft.tzinfo is None:
        ft = ft.replace(tzinfo=timezone.utc)
    return (now - ft.astimezone(timezone.utc)).total_seconds() / 60.0


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

    def _apply_lineup_meta(self, row: dict[str, Any], db: Session, fixture_id: int) -> None:
        lu = lineup_row_for_fixture(db, int(fixture_id))
        if lu is None:
            row["lineups_ok"] = False
            return
        row["lineups_ok"] = True
        row["confirmed"] = bool(lu.confirmed)
        row["fetched_at"] = lu.fetched_at.isoformat() if lu.fetched_at else None

    def refresh_next_round_lineups(
        self,
        db: Session,
        season_year: int,
        *,
        force: bool = False,
        sync_squads: bool = False,
        regenerate_v20: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        season = self._season_row(db, season_year)
        if not season:
            return {
                "status": "error",
                "message": "Stagione non trovata",
                "total_fixtures": 0,
                "updated": 0,
                "skipped_no_mapping": 0,
                "skipped_recent": 0,
                "failed": 0,
                "estimated_api_calls": 0,
                "results": [],
            }

        fixtures = self.upcoming_next_round_fixtures(db, season_year, limit=limit)
        if not fixtures:
            return {
                "status": "success",
                "message": "Nessuna fixture upcoming",
                "total_fixtures": 0,
                "updated": 0,
                "skipped_no_mapping": 0,
                "skipped_recent": 0,
                "failed": 0,
                "estimated_api_calls": 0,
                "results": [],
            }

        lineup_svc = SportApiLineupService()
        match_svc = SportApiMatchingService()
        results: list[dict[str, Any]] = []
        api_calls = 0
        updated = 0
        skipped_no_mapping = 0
        skipped_recent = 0
        failed = 0
        v20_regenerated = 0
        up_count = 0
        down_count = 0
        flat_count = 0
        impact_orch = LineupRefreshImpactOrchestrator()

        for fx in fixtures:
            fid = int(fx.id)
            row: dict[str, Any] = {
                "fixture_id": fid,
                "api_fixture_id": int(fx.api_fixture_id),
                "status": "ok",
                "mapping_ok": self._has_mapping(db, fid),
                "lineups_ok": False,
                "confirmed": None,
                "fetched_at": None,
                "error": None,
                "v20_regenerated": False,
            }
            lineup_updated_this_run = False
            before_snapshot: dict[str, Any] | None = None
            home_t = db.get(Team, int(fx.home_team_id))
            away_t = db.get(Team, int(fx.away_team_id))
            row["match_name"] = f"{home_t.name if home_t else 'Casa'} – {away_t.name if away_t else 'Trasferta'}"
            try:
                need_mapping = force or not row["mapping_ok"]
                if need_mapping:
                    debug = match_svc.debug_match_fixture(db, fid)
                    api_calls += int(debug.get("api_calls") or 1)
                    best = debug.get("best_candidate") if isinstance(debug.get("best_candidate"), dict) else None
                    if best and debug.get("recommendation") == "AUTO_SAFE":
                        conf = float(best.get("confidence_score") or 90)
                        if conf >= 90:
                            out_map = lineup_svc.confirm_mapping(
                                db,
                                fid,
                                provider_event_id=int(best["provider_event_id"]),
                                confidence_score=conf,
                                matched_by="auto_timestamp_teams",
                                raw_payload=best,
                            )
                            if out_map.get("status") != "error":
                                row["mapping_ok"] = True
                    if not row["mapping_ok"]:
                        row["status"] = "mapping_failed"
                        row["error"] = str(debug.get("message") or "Nessun candidato AUTO_SAFE")
                        skipped_no_mapping += 1
                        results.append(row)
                        continue

                self._apply_lineup_meta(row, db, fid)

                if row["mapping_ok"] and row["lineups_ok"] and not force:
                    lu = lineup_row_for_fixture(db, fid)
                    age_min = _fetched_at_age_minutes(lu.fetched_at if lu else None)
                    if age_min is not None and age_min < SKIP_FETCH_MINUTES:
                        row["status"] = "skipped_recent"
                        skipped_recent += 1
                        results.append(row)
                        continue

                lu = lineup_row_for_fixture(db, fid)
                should_fetch = force or lu is None
                if not should_fetch and lu and lu.fetched_at:
                    age_min = _fetched_at_age_minutes(lu.fetched_at)
                    should_fetch = age_min is None or age_min >= SKIP_FETCH_MINUTES

                if should_fetch and regenerate_v20:
                    before_snapshot = build_snapshot(db, fid)

                if should_fetch:
                    fetch_out = lineup_svc.fetch_and_persist_lineups(db, fid)
                    api_calls += 1
                    if fetch_out.get("status") == "success":
                        row["lineups_ok"] = True
                        row["confirmed"] = fetch_out.get("confirmed")
                        row["fetched_at"] = fetch_out.get("fetched_at")
                        row["status"] = "updated"
                        lineup_updated_this_run = True
                        updated += 1
                    else:
                        row["status"] = "lineups_failed"
                        row["error"] = str(fetch_out.get("message") or "fetch lineups fallito")
                        failed += 1
                else:
                    self._apply_lineup_meta(row, db, fid)
                    row["status"] = "unchanged"

                if sync_squads and row["mapping_ok"]:
                    sync_team_squads(db, int(season.year), [int(fx.home_team_id), int(fx.away_team_id)])

                if regenerate_v20 and lineup_updated_this_run:
                    from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import (
                        SotPredictionV20LineupImpactService,
                    )

                    v20_out = SotPredictionV20LineupImpactService().generate_for_fixture(db, fid)
                    if v20_out.get("status") in ("success", "partial_success"):
                        row["v20_regenerated"] = True
                        v20_regenerated += 1

                if regenerate_v20 and lineup_updated_this_run and before_snapshot is not None:
                    impact_delta = impact_orch.finalize_impact_after_refresh(
                        db,
                        fid,
                        before_snapshot,
                    )
                    if impact_delta:
                        row["before_total_sot"] = impact_delta.get("before_total_sot")
                        row["after_total_sot"] = impact_delta.get("after_total_sot")
                        row["delta_total_sot"] = impact_delta.get("delta_total_sot")
                        row["direction_total"] = impact_delta.get("direction_total")
                        row["main_reason"] = impact_delta.get("main_reason")
                        ddir = str(impact_delta.get("direction_total") or "")
                        if ddir == "UP":
                            up_count += 1
                        elif ddir == "DOWN":
                            down_count += 1
                        elif ddir == "FLAT":
                            flat_count += 1

            except Exception as exc:  # noqa: BLE001
                logger.exception("refresh fixture %s", fid)
                row["status"] = "error"
                row["error"] = str(exc)[:300]
                failed += 1
            results.append(row)

        return {
            "status": "success",
            "season": int(season_year),
            "total_fixtures": len(fixtures),
            "fixtures_count": len(fixtures),
            "updated": updated,
            "skipped_no_mapping": skipped_no_mapping,
            "skipped_recent": skipped_recent,
            "failed": failed,
            "v20_regenerated": v20_regenerated,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
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
