"""Aggiorna risultati live/finali dei tracked picks via API-Sports."""

from __future__ import annotations

import logging
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES, SCHEDULED_STATUSES
from app.models import Fixture, Team, TrackedBettingPick
from app.models.tracked_betting_pick import (
    SOURCE_AUTO_PRE_MATCH,
    SOURCE_BACKFILL_ROUND,
    SOURCE_MANUAL,
    STATUS_LIVE,
    STATUS_LOST,
    STATUS_PENDING,
    STATUS_UNAVAILABLE,
    STATUS_VOID,
    STATUS_WON,
)
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.ingestion_service import IngestionService
from app.services.tracked_betting_pick_service import formation_snapshot_label

logger = logging.getLogger(__name__)

LIVE_STATUSES = frozenset({"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "INT"})
VOID_STATUSES = frozenset({"CANC", "ABD", "AWD", "WO"})


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


def _origin_label(p: TrackedBettingPick) -> str:
    if p.is_backfilled or p.source == SOURCE_BACKFILL_ROUND:
        return "Ricostruita"
    if p.source == SOURCE_AUTO_PRE_MATCH:
        return "Auto 30'"
    if p.source == SOURCE_MANUAL:
        return "Manuale"
    return p.source


def _compute_summary(picks: list[TrackedBettingPick]) -> dict[str, Any]:
    pending = live = won = lost = unavailable = void = 0
    for p in picks:
        st = p.status
        if st == STATUS_PENDING:
            pending += 1
        elif st == STATUS_LIVE:
            live += 1
        elif st == STATUS_WON:
            won += 1
        elif st == STATUS_LOST:
            lost += 1
        elif st == STATUS_UNAVAILABLE:
            unavailable += 1
        elif st == STATUS_VOID:
            void += 1
    concluded = won + lost
    win_rate = round(won / concluded, 4) if concluded > 0 else None
    return {
        "total": len(picks),
        "pending": pending,
        "live": live,
        "won": won,
        "lost": lost,
        "unavailable": unavailable,
        "void": void,
        "win_rate": win_rate,
    }


class TrackedPickResultsRefreshService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def list_tracked_payload(self, db: Session, season_year: int) -> dict[str, Any]:
        ingest = IngestionService()
        season_row = ingest._serie_a_season_row(db, season_year)  # noqa: SLF001
        picks = list(
            db.scalars(
                select(TrackedBettingPick)
                .join(Fixture, Fixture.id == TrackedBettingPick.fixture_id)
                .where(Fixture.season_id == season_row.id)
                .order_by(Fixture.kickoff_at.asc(), TrackedBettingPick.id.asc()),
            ).all(),
        )
        fx_ids = list({int(p.fixture_id) for p in picks})
        fixtures = {int(f.id): f for f in db.scalars(select(Fixture).where(Fixture.id.in_(fx_ids))).all()} if fx_ids else {}
        team_ids = set()
        for f in fixtures.values():
            team_ids.add(int(f.home_team_id))
            team_ids.add(int(f.away_team_id))
        teams = {int(t.id): t for t in db.scalars(select(Team).where(Team.id.in_(list(team_ids)))).all()} if team_ids else {}

        rows_out: list[dict[str, Any]] = []
        for p in picks:
            fx = fixtures.get(int(p.fixture_id))
            if not fx:
                continue
            ht = teams.get(int(fx.home_team_id))
            at = teams.get(int(fx.away_team_id))
            pick_type_label = "Cauta" if p.pick_type == "cautious" else "Statistica"
            live_hint = _live_over_hint(p.result_total_sot, p.line_value)
            rows_out.append(
                {
                    "id": int(p.id),
                    "fixture_id": int(p.fixture_id),
                    "kickoff_at": fx.kickoff_at.isoformat() if fx.kickoff_at else None,
                    "match_name": f"{ht.name if ht else 'Casa'} – {at.name if at else 'Trasferta'}",
                    "home_team": {"id": int(fx.home_team_id), "name": ht.name if ht else "", "logo_url": ht.logo_url if ht else None},
                    "away_team": {"id": int(fx.away_team_id), "name": at.name if at else "", "logo_url": at.logo_url if at else None},
                    "suggested_pick": p.suggested_pick,
                    "pick_type": p.pick_type,
                    "pick_type_label": pick_type_label,
                    "source": p.source,
                    "origin_label": _origin_label(p),
                    "is_backfilled": bool(p.is_backfilled),
                    "prediction_source": p.prediction_source,
                    "backfill_warning": p.backfill_warning,
                    "formation_label": formation_snapshot_label(bool(p.lineup_confirmed)),
                    "lineup_confirmed": bool(p.lineup_confirmed),
                    "predicted_total_sot": p.predicted_total_sot,
                    "fixture_status": p.fixture_status or fx.status,
                    "elapsed": p.elapsed,
                    "score_home": p.score_home if p.score_home is not None else fx.goals_home,
                    "score_away": p.score_away if p.score_away is not None else fx.goals_away,
                    "result_home_sot": p.result_home_sot,
                    "result_away_sot": p.result_away_sot,
                    "result_total_sot": p.result_total_sot,
                    "status": p.status,
                    "confidence_label": p.confidence_label,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                    "auto_generated_at": p.auto_generated_at.isoformat() if p.auto_generated_at else None,
                    **live_hint,
                },
            )
        return {
            "status": "success",
            "season": season_year,
            "picks": rows_out,
            "count": len(rows_out),
            "summary": _compute_summary(picks),
        }

    def refresh_results(self, db: Session, season_year: int) -> dict[str, Any]:
        ingest = IngestionService()
        season_row = ingest._serie_a_season_row(db, season_year)  # noqa: SLF001
        picks = list(
            db.scalars(
                select(TrackedBettingPick)
                .join(Fixture, Fixture.id == TrackedBettingPick.fixture_id)
                .where(
                    Fixture.season_id == season_row.id,
                    TrackedBettingPick.status != STATUS_VOID,
                ),
            ).all(),
        )
        updated = 0
        errors: list[dict[str, Any]] = []
        api_calls = 0

        for pick in picks:
            fx = db.get(Fixture, int(pick.fixture_id))
            if fx is None or not fx.api_fixture_id:
                continue
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
                from app.services.fixture_team_stats_mapping import statistics_list_to_fields

                home_sot: float | None = None
                away_sot: float | None = None
                for block in stats_payload:
                    team_api = int((block.get("team") or {})["id"])
                    parsed = statistics_list_to_fields(block.get("statistics"))
                    sot = parsed.get("shots_on_target")
                    team = db.scalar(select(Team).where(Team.api_team_id == team_api))
                    if team is None:
                        continue
                    if int(team.id) == int(fx.home_team_id):
                        home_sot = float(sot) if sot is not None else None
                    elif int(team.id) == int(fx.away_team_id):
                        away_sot = float(sot) if sot is not None else None

                if home_sot is not None and away_sot is not None:
                    pick.result_home_sot = home_sot
                    pick.result_away_sot = away_sot
                    pick.result_total_sot = round(home_sot + away_sot, 2)

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
            "picks_checked": len(picks),
            "picks_updated": updated,
            "api_calls": api_calls,
            "errors": errors,
        }
