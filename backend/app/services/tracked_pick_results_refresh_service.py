"""Aggiorna risultati live/finali dei tracked picks via API-Sports."""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES, SCHEDULED_STATUSES
from app.models import Fixture, Team, TrackedBettingPick
from app.models.tracked_betting_pick import (
    STATUS_LIVE,
    STATUS_LOST,
    STATUS_PENDING,
    STATUS_UNAVAILABLE,
    STATUS_VOID,
    STATUS_WON,
)
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.fixture_sot_statistics import extract_sot_from_statistics_response
from app.services.ingestion_service import IngestionService
from app.services.tracked_monitoring_constants import LIVE_STATUSES, VOID_STATUSES

logger = logging.getLogger(__name__)
RefreshScope = Literal["all", "live", "unfinished", "unfinished_or_recent"]

STALE_LIVE_KICKOFF_HOURS = 3
STALE_LIVE_UPDATED_MINUTES = 30
RECENT_FT_SKIP_MINUTES = 30
RECENT_KICKOFF_HOURS = 48


def _resolve_pick_outcome(total_sot: float | None, line_value: float | None) -> str | None:
    if total_sot is None or line_value is None:
        return None
    if float(total_sot) > float(line_value):
        return STATUS_WON
    return STATUS_LOST


def _live_over_hint(total_sot: float | None, line_value: float | None) -> dict[str, Any]:
    if total_sot is None or line_value is None:
        return {
            "live_sot_remaining": None,
            "line_already_beaten": False,
            "live_hint_label": None,
        }
    total = float(total_sot)
    line = float(line_value)
    beaten = total > line
    if beaten:
        return {
            "live_sot_remaining": 0,
            "line_already_beaten": True,
            "live_hint_label": "Linea già superata",
        }
    need = max(0, int(math.ceil(line + 0.01 - total)))
    label = f"Mancano {need} SOT" if need > 0 else None
    return {
        "live_sot_remaining": need,
        "line_already_beaten": False,
        "live_hint_label": label,
    }


def _final_hint_label(total_sot: float | None, line_value: float | None) -> str | None:
    if total_sot is None or line_value is None:
        return None
    if float(total_sot) > float(line_value):
        return "Linea superata"
    return "Linea non superata"


def _fixture_status_for_pick(pick: TrackedBettingPick, fx: Fixture | None) -> str:
    return (pick.fixture_status or (fx.status if fx else "") or "").strip().upper()


def _kickoff_utc(fx: Fixture | None) -> datetime | None:
    if fx is None or fx.kickoff_at is None:
        return None
    ko = fx.kickoff_at
    if ko.tzinfo is None:
        return ko.replace(tzinfo=timezone.utc)
    return ko.astimezone(timezone.utc)


def _is_stale_live(pick: TrackedBettingPick, fx: Fixture | None, now: datetime) -> bool:
    fs = _fixture_status_for_pick(pick, fx)
    if pick.status != STATUS_LIVE and fs not in LIVE_STATUSES:
        return False
    ko = _kickoff_utc(fx)
    if ko is not None and ko < now - timedelta(hours=STALE_LIVE_KICKOFF_HOURS):
        return True
    updated = pick.updated_at
    if updated is not None:
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        else:
            updated = updated.astimezone(timezone.utc)
        if updated < now - timedelta(minutes=STALE_LIVE_UPDATED_MINUTES):
            return True
    return False


def _is_recent_ft_closed(pick: TrackedBettingPick, fx: Fixture | None, now: datetime) -> bool:
    if pick.status not in (STATUS_WON, STATUS_LOST):
        return False
    fs = _fixture_status_for_pick(pick, fx)
    if fs not in FINISHED_STATUSES:
        return False
    updated = pick.updated_at
    if updated is None:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    else:
        updated = updated.astimezone(timezone.utc)
    return updated >= now - timedelta(minutes=RECENT_FT_SKIP_MINUTES)


def _should_refresh_pick(
    pick: TrackedBettingPick,
    fx: Fixture | None,
    scope: RefreshScope,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> bool:
    if scope == "all":
        return True
    now = now or datetime.now(timezone.utc)
    fs = _fixture_status_for_pick(pick, fx)

    if not force and scope == "unfinished_or_recent" and _is_recent_ft_closed(pick, fx, now):
        return False

    if scope == "live":
        return pick.status == STATUS_LIVE or fs in LIVE_STATUSES

    if scope == "unfinished":
        return fs not in FINISHED_STATUSES

    if scope == "unfinished_or_recent":
        if _is_stale_live(pick, fx, now):
            return True
        if pick.status in (STATUS_PENDING, STATUS_LIVE, STATUS_UNAVAILABLE):
            return True
        if fs not in FINISHED_STATUSES:
            return True
        ko = _kickoff_utc(fx)
        if ko is not None and ko >= now - timedelta(hours=RECENT_KICKOFF_HOURS):
            if fs not in FINISHED_STATUSES:
                return True
            if pick.status in (STATUS_PENDING, STATUS_LIVE) and ko < now:
                return True
        return False

    return True


def _pick_in_scope(
    pick: TrackedBettingPick,
    fx: Fixture | None,
    scope: RefreshScope,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> bool:
    return _should_refresh_pick(pick, fx, scope, force=force, now=now)


class TrackedPickResultsRefreshService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def refresh_results(
        self,
        db: Session,
        season_year: int,
        *,
        scope: RefreshScope = "all",
        force: bool = False,
    ) -> dict[str, Any]:
        ingest = IngestionService()
        season_row = ingest._serie_a_season_row(db, season_year)  # noqa: SLF001
        all_picks = list(
            db.scalars(
                select(TrackedBettingPick)
                .join(Fixture, Fixture.id == TrackedBettingPick.fixture_id)
                .where(
                    Fixture.season_id == season_row.id,
                    TrackedBettingPick.status != STATUS_VOID,
                ),
            ).all(),
        )
        fixture_ids = list({int(p.fixture_id) for p in all_picks})
        fixtures_map = (
            {int(f.id): f for f in db.scalars(select(Fixture).where(Fixture.id.in_(fixture_ids))).all()}
            if fixture_ids
            else {}
        )
        team_ids: set[int] = set()
        for fx in fixtures_map.values():
            team_ids.add(int(fx.home_team_id))
            team_ids.add(int(fx.away_team_id))
        teams_map = (
            {int(t.id): t for t in db.scalars(select(Team).where(Team.id.in_(list(team_ids)))).all()}
            if team_ids
            else {}
        )

        now = datetime.now(timezone.utc)
        picks = [
            p
            for p in all_picks
            if _pick_in_scope(p, fixtures_map.get(int(p.fixture_id)), scope, force=force, now=now)
        ]
        updated = 0
        errors: list[dict[str, Any]] = []
        stats_debug: list[dict[str, Any]] = []
        api_calls = 0
        last_refreshed_at = datetime.now(timezone.utc).isoformat()

        for pick in picks:
            fx = fixtures_map.get(int(pick.fixture_id))
            if fx is None or not fx.api_fixture_id:
                continue
            ht = teams_map.get(int(fx.home_team_id))
            at = teams_map.get(int(fx.away_team_id))
            try:
                body = self._client.get("fixtures", {"id": int(fx.api_fixture_id)})
                api_calls += 1
                resp = list(body.get("response") or [])
                if not resp:
                    errors.append({"pick_id": int(pick.id), "error": "fixture API vuota"})
                    continue
                item = resp[0]
                fix = item.get("fixture") or {}
                goals = item.get("goals") or {}
                st_short = str((fix.get("status") or {}).get("short") or fx.status or "")
                elapsed = (fix.get("status") or {}).get("elapsed")
                pick.fixture_status = st_short
                pick.elapsed = int(elapsed) if elapsed is not None else None
                if goals.get("home") is not None:
                    pick.score_home = int(goals["home"])
                if goals.get("away") is not None:
                    pick.score_away = int(goals["away"])

                if st_short in VOID_STATUSES:
                    pick.status = STATUS_VOID
                    db.add(pick)
                    updated += 1
                    continue

                stats_payload = self._client.get_fixture_statistics(int(fx.api_fixture_id))
                api_calls += 1
                sot_result = extract_sot_from_statistics_response(
                    stats_payload,
                    home_team_id=int(fx.home_team_id),
                    away_team_id=int(fx.away_team_id),
                    home_api_team_id=int(ht.api_team_id) if ht and ht.api_team_id else None,
                    away_api_team_id=int(at.api_team_id) if at and at.api_team_id else None,
                    home_team_name=ht.name if ht else None,
                    away_team_name=at.name if at else None,
                )
                dbg = sot_result.get("debug") if isinstance(sot_result.get("debug"), dict) else {}

                if sot_result.get("sot_available"):
                    pick.result_home_sot = sot_result["home_sot"]
                    pick.result_away_sot = sot_result["away_sot"]
                    pick.result_total_sot = sot_result["total_sot"]
                elif st_short in LIVE_STATUSES or st_short in FINISHED_STATUSES:
                    pick.result_home_sot = None
                    pick.result_away_sot = None
                    pick.result_total_sot = None
                    reason = sot_result.get("sot_unavailable_reason") or "SOT non disponibili"
                    snippet = str(dbg.get("raw_statistics_sample") or json.dumps(stats_payload, ensure_ascii=False)[:2048])
                    log_fn = logger.warning if st_short in FINISHED_STATUSES else logger.info
                    log_fn(
                        "SOT non disponibili pick_id=%s api_fixture_id=%s status=%s reason=%s debug=%s raw=%s",
                        pick.id,
                        fx.api_fixture_id,
                        st_short,
                        reason,
                        dbg,
                        snippet,
                    )
                    stats_debug.append(
                        {
                            "pick_id": int(pick.id),
                            "fixture_id": int(fx.id),
                            "api_fixture_id": int(fx.api_fixture_id),
                            "fixture_status": st_short,
                            "statistics_found": bool(dbg.get("statistics_found")),
                            "raw_statistics_sample": snippet,
                            "extracted_home_sot": sot_result.get("home_sot"),
                            "extracted_away_sot": sot_result.get("away_sot"),
                            "extraction_error": dbg.get("extraction_error"),
                            "metric_labels_seen": dbg.get("labels_seen"),
                            "metric_label_home": dbg.get("metric_label_home"),
                            "metric_label_away": dbg.get("metric_label_away"),
                        },
                    )

                if st_short in FINISHED_STATUSES:
                    if pick.result_total_sot is not None and pick.line_value is not None:
                        pick.status = _resolve_pick_outcome(pick.result_total_sot, pick.line_value) or STATUS_UNAVAILABLE
                    else:
                        pick.status = STATUS_UNAVAILABLE
                elif st_short in LIVE_STATUSES:
                    pick.status = STATUS_LIVE
                elif st_short in SCHEDULED_STATUSES or st_short in ("NS", "TBD", "PST"):
                    pick.status = STATUS_PENDING
                else:
                    pick.status = STATUS_PENDING

                db.add(pick)
                updated += 1
            except ApiFootballError as exc:
                errors.append({"pick_id": int(pick.id), "error": str(exc)[:200]})
            except Exception as exc:  # noqa: BLE001
                logger.exception("refresh pick %s", pick.id)
                errors.append({"pick_id": int(pick.id), "error": str(exc)[:200]})

        db.commit()
        return {
            "status": "success",
            "season": season_year,
            "scope": scope,
            "force": force,
            "last_refreshed_at": last_refreshed_at,
            "picks_checked": len(picks),
            "picks_updated": updated,
            "api_calls": api_calls,
            "errors": errors,
            "stats_debug": stats_debug,
        }
