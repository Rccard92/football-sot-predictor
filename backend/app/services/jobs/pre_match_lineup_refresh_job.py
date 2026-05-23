"""Job pre-match: refresh SportAPI, v2.0, impact snapshot, sync tracked_betting_picks."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    FINISHED_STATUSES,
    LIVE_STATUSES,
)
from app.models import Fixture, IngestionRun, League, Season, Team, TeamSotPrediction
from app.services.ingestion_service import IngestionService
from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import (
    SotPredictionV20LineupImpactService,
)
from app.services.sot_betting_advice_service import (
    advice_context_from_upcoming_lineup,
    build_fixture_betting_advice,
)
from app.services.sportapi.lineup_refresh_impact_orchestrator import LineupRefreshImpactOrchestrator
from app.services.sportapi.lineup_refresh_snapshot_service import build_snapshot
from app.services.sportapi.sportapi_fixture_refresh import (
    get_sportapi_event_id,
    refresh_fixture_sportapi_pre_match,
)
from app.services.sportapi.sportapi_lineup_status import formation_status_from_lineup, lineup_row_for_fixture
from app.services.tracked_betting_pick_service import TrackedBettingPickService

logger = logging.getLogger(__name__)

JOB_SOURCE = "pre_match_official_lineup"
JOB_SOURCE_LEGACY = "pre_match_lineup_refresh"
RUNNING_LOCK_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_total(snapshot: dict[str, Any]) -> float | None:
    if not snapshot.get("v20_available"):
        return None
    h = snapshot.get("predicted_home_sot")
    a = snapshot.get("predicted_away_sot")
    if h is None or a is None:
        return None
    return round(float(h) + float(a), 2)


class PreMatchOfficialLineupRefreshJob:
    def _season_row(self, db: Session, season_year: int) -> Season | None:
        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            league = db.scalar(select(League).where(League.api_league_id == get_settings().default_league_id))
        if league is None:
            return None
        return db.scalar(select(Season).where(Season.league_id == league.id, Season.year == int(season_year)))

    def fixtures_in_kickoff_window(
        self,
        db: Session,
        season_year: int,
        *,
        minutes_before: int,
        window_minutes: int,
        force: bool = False,
    ) -> tuple[list[Fixture], list[Fixture]]:
        """Ritorna (tutte in finestra DB, eleggibili dopo filtri live/past)."""
        season = self._season_row(db, season_year)
        if season is None:
            return [], []
        now = _utcnow()
        half = max(1, int(window_minutes) // 2)
        start = now + timedelta(minutes=int(minutes_before) - half)
        end = now + timedelta(minutes=int(minutes_before) + half)
        rows = list(
            db.scalars(
                select(Fixture).where(
                    Fixture.season_id == season.id,
                    Fixture.kickoff_at >= start,
                    Fixture.kickoff_at <= end,
                    Fixture.status.notin_(list(FINISHED_STATUSES)),
                ),
            ).all(),
        )
        in_window = [f for f in rows if f.api_fixture_id]
        eligible: list[Fixture] = []
        for f in in_window:
            st = (f.status or "").strip().upper()
            if st in LIVE_STATUSES:
                continue
            ko = f.kickoff_at
            if ko is not None:
                if ko.tzinfo is None:
                    ko = ko.replace(tzinfo=timezone.utc)
                if not force and ko < now:
                    continue
            eligible.append(f)
        return in_window, eligible

    def _load_v20_sot(
        self,
        db: Session,
        fixture_id: int,
        home_team_id: int,
        away_team_id: int,
    ) -> tuple[float | None, float | None, dict[str, Any]]:
        mv = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
        home_row = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture_id),
                TeamSotPrediction.team_id == int(home_team_id),
                TeamSotPrediction.model_version == mv,
            ),
        )
        away_row = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture_id),
                TeamSotPrediction.team_id == int(away_team_id),
                TeamSotPrediction.model_version == mv,
            ),
        )
        payload: dict[str, Any] = {}
        if home_row and isinstance(home_row.raw_json, dict):
            payload["home"] = home_row.raw_json
        if away_row and isinstance(away_row.raw_json, dict):
            payload["away"] = away_row.raw_json
        h = float(home_row.predicted_sot) if home_row and home_row.predicted_sot is not None else None
        a = float(away_row.predicted_sot) if away_row and away_row.predicted_sot is not None else None
        return h, a, payload

    def _running_job_exists(self, db: Session) -> bool:
        cutoff = _utcnow() - timedelta(minutes=RUNNING_LOCK_MINUTES)
        row = db.scalar(
            select(IngestionRun.id).where(
                IngestionRun.source.in_([JOB_SOURCE, JOB_SOURCE_LEGACY]),
                IngestionRun.status == "running",
                IngestionRun.started_at >= cutoff,
            ),
        )
        return row is not None

    def _begin_run(self, db: Session, meta: dict[str, Any] | None = None) -> IngestionRun:
        run = IngestionRun(
            source=JOB_SOURCE,
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
        meta_merge: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        row = db.get(IngestionRun, run.id)
        if row is None:
            return
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

    def run(
        self,
        db: Session,
        season_year: int,
        *,
        force: bool = False,
        minutes_before: int | None = None,
        window_minutes: int | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        mb = int(minutes_before if minutes_before is not None else settings.prematch_refresh_minutes_before)
        wm = int(window_minutes if window_minutes is not None else settings.prematch_refresh_window_minutes)
        skip_recent = float(settings.prematch_refresh_skip_recent_minutes)

        if not force and self._running_job_exists(db):
            return {
                "status": "skipped",
                "message": "Job pre-match già in esecuzione",
                "season": int(season_year),
                "checked_fixtures": 0,
                "eligible_fixtures": 0,
                "checked": 0,
                "refreshed": 0,
                "errors": [],
                "results": [],
            }

        checked_list, fixtures = self.fixtures_in_kickoff_window(
            db,
            season_year,
            minutes_before=mb,
            window_minutes=wm,
            force=force,
        )
        run = self._begin_run(
            db,
            meta={
                "season": season_year,
                "minutes_before": mb,
                "window_minutes": wm,
                "force": force,
            },
        )

        checked = len(checked_list)
        eligible = len(fixtures)
        refreshed = 0
        picks_created = 0
        picks_updated = 0
        picks_skipped = 0
        skipped_recent = 0
        mapping_missing = 0
        lineup_confirmed_count = 0
        errors: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []

        pick_svc = TrackedBettingPickService()
        v20_svc = SotPredictionV20LineupImpactService()
        impact_orch = LineupRefreshImpactOrchestrator()

        for fx in fixtures:
            fid = int(fx.id)
            home_t = db.get(Team, int(fx.home_team_id))
            away_t = db.get(Team, int(fx.away_team_id))
            match_name = f"{home_t.name if home_t else 'Casa'} – {away_t.name if away_t else 'Trasferta'}"
            kickoff_iso = fx.kickoff_at.isoformat() if fx.kickoff_at else None
            event_id = get_sportapi_event_id(db, fid)

            row: dict[str, Any] = {
                "fixture_id": fid,
                "match": match_name,
                "match_name": match_name,
                "kickoff": kickoff_iso,
                "sportapi_event_id": event_id,
                "status": "ok",
            }
            monitoring_status = "none"

            try:
                before_snapshot = build_snapshot(db, fid)
                before_total = _snapshot_total(before_snapshot)

                refresh_out = refresh_fixture_sportapi_pre_match(
                    db,
                    fid,
                    force_mapping=force,
                    force_fetch=force,
                    skip_recent_minutes=skip_recent if not force else None,
                )
                row.update(refresh_out)

                if refresh_out.get("status") == "unchanged" and refresh_out.get("confirmed") and not force:
                    lu = lineup_row_for_fixture(db, fid)
                    if lu and lu.confirmed:
                        skipped_recent += 1
                        row["status"] = "skipped_recent"
                        row["before_total_sot"] = before_total
                        row["after_total_sot"] = before_total
                        row["delta_total_sot"] = 0.0
                        row["monitoring_pick_status"] = "skipped_recent"
                        results.append(row)
                        db.commit()
                        continue

                if not refresh_out.get("mapping_ok"):
                    mapping_missing += 1
                    row["status"] = "skipped_no_mapping"
                    row["monitoring_pick_status"] = "no_mapping"
                    results.append(row)
                    db.commit()
                    continue

                if refresh_out.get("status") == "lineups_failed":
                    errors.append({"fixture_id": fid, "error": row.get("error") or "lineups_failed"})
                    row["monitoring_pick_status"] = "lineups_failed"
                    results.append(row)
                    db.commit()
                    continue

                if refresh_out.get("status") in ("updated", "unchanged") and refresh_out.get("lineups_ok"):
                    refreshed += 1

                lu = lineup_row_for_fixture(db, fid)
                confirmed = bool(lu.confirmed) if lu else False
                if confirmed:
                    lineup_confirmed_count += 1
                fetched_at = lu.fetched_at if lu else None
                lineup_status = formation_status_from_lineup(lu)
                row["confirmed"] = confirmed

                v20_out = v20_svc.generate_for_fixture(db, fid)
                if v20_out.get("status") not in ("success", "partial_success"):
                    row["status"] = "v20_failed"
                    row["error"] = str(v20_out.get("message") or "v20 failed")
                    errors.append({"fixture_id": fid, "error": row["error"]})
                    row["monitoring_pick_status"] = "v20_failed"
                    results.append(row)
                    db.commit()
                    continue

                impact_delta = impact_orch.finalize_impact_after_refresh(db, fid, before_snapshot)
                after_total = _snapshot_total(build_snapshot(db, fid))
                row["before_total_sot"] = before_total
                row["after_total_sot"] = after_total
                if impact_delta:
                    row["delta_total_sot"] = impact_delta.get("delta_total_sot")
                    if impact_delta.get("main_reason"):
                        row["impact_main_reason"] = impact_delta.get("main_reason")

                home_sot, away_sot, raw_pred = self._load_v20_sot(
                    db,
                    fid,
                    int(fx.home_team_id),
                    int(fx.away_team_id),
                )
                if home_sot is None or away_sot is None:
                    row["status"] = "predictions_missing"
                    errors.append({"fixture_id": fid, "error": "Predizioni v2.0 mancanti"})
                    row["monitoring_pick_status"] = "predictions_missing"
                    results.append(row)
                    db.commit()
                    continue

                advice_ctx = advice_context_from_upcoming_lineup(lineup_status)
                advice = build_fixture_betting_advice(
                    home_sot,
                    away_sot,
                    model_version=BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
                    context=advice_ctx,
                )
                pick_stats = pick_svc.persist_from_betting_advice(
                    db,
                    fixture_id=fid,
                    home_sot=home_sot,
                    away_sot=away_sot,
                    advice=advice,
                    lineup_confirmed=confirmed,
                    lineup_fetched_at=fetched_at,
                    raw_prediction_payload=raw_pred,
                    force=force,
                )
                picks_created += pick_stats["created"]
                picks_updated += pick_stats["updated"]
                picks_skipped += pick_stats["skipped"]
                monitoring_status = (
                    "created"
                    if pick_stats["created"] > 0
                    else "updated"
                    if pick_stats["updated"] > 0
                    else "skipped"
                )
                row["picks"] = pick_stats
                row["lineup_confirmed"] = confirmed
                row["monitoring_pick_status"] = monitoring_status
                db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.exception("pre-match job fixture %s", fid)
                db.rollback()
                row["status"] = "error"
                row["error"] = str(exc)[:300]
                row["monitoring_pick_status"] = "error"
                errors.append({"fixture_id": fid, "error": row["error"]})
            results.append(row)

        summary = {
            "status": "success",
            "season": int(season_year),
            "checked_fixtures": checked,
            "eligible_fixtures": eligible,
            "refreshed": refreshed,
            "skipped_recent": skipped_recent,
            "skipped_no_mapping": mapping_missing,
            "updated_monitoring_picks": picks_updated,
            "created_monitoring_picks": picks_created,
            "minutes_before": mb,
            "window_minutes": wm,
            "errors": errors,
            "results": results,
            # legacy aliases
            "checked": checked,
            "picks_created": picks_created,
            "picks_updated": picks_updated,
            "skipped": picks_skipped,
            "mapping_missing": mapping_missing,
            "lineup_confirmed": lineup_confirmed_count,
        }
        self._finish_run(
            db,
            run,
            success=True,
            records_processed=eligible,
            meta_merge=summary,
        )
        return summary


# Backward compatibility
PreMatchLineupRefreshJob = PreMatchOfficialLineupRefreshJob
