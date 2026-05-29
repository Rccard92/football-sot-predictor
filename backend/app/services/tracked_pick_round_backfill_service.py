"""Crea pick monitorate dal turno corrente (backfill da predizioni DB)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    FINISHED_STATUSES,
)
from app.models import Fixture, Season, Team, TeamSotPrediction
from app.models.tracked_betting_pick import (
    BACKFILL_WARNING_RECONSTRUCTED,
    PICK_TYPE_CAUTIOUS,
    PICK_TYPE_STATISTICAL,
    PREDICTION_SOURCE_CERTIFIED,
    PREDICTION_SOURCE_DB_V11,
    PREDICTION_SOURCE_DB_V20,
    PREDICTION_SOURCE_RECONSTRUCTED,
    SOURCE_AUTO_PRE_MATCH,
)
from app.services.ingestion_service import IngestionService
from app.services.sot_betting_advice_service import (
    advice_context_from_upcoming_lineup,
    build_fixture_betting_advice,
)
from app.services.sot_feature_service import SotFeatureService
from app.services.sot_prediction_service import _fixture_round_display
from app.services.sportapi.sportapi_lineup_status import formation_status_from_lineup, lineup_row_for_fixture
from app.services.tracked_betting_pick_service import (
    MARKET_MATCH_TOTAL,
    TrackedBettingPickService,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _round_key(fx: Fixture) -> str | None:
    return _fixture_round_display(fx) or (fx.round if fx.round else None)


class TrackedPickRoundBackfillService:
    def _season_row(self, db: Session, season_year: int) -> Season | None:
        ingest = IngestionService()
        return ingest._serie_a_season_row(db, season_year)  # noqa: SLF001

    def current_round_fixtures(self, db: Session, season_year: int, *, limit: int = 50) -> list[Fixture]:
        season = self._season_row(db, season_year)
        if season is None:
            return []
        all_rows = list(
            db.scalars(
                select(Fixture)
                .where(Fixture.season_id == season.id)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all(),
        )
        if not all_rows:
            return []

        feat = SotFeatureService()
        upcoming = feat.list_upcoming_fixtures_for_season(db, season.id)
        anchor: Fixture | None = None
        if upcoming:
            anchor = upcoming[0]
        else:
            live_or_recent = [
                f
                for f in all_rows
                if (f.status or "").upper() not in {"CANC", "ABD", "AWD", "WO"}
            ]
            if live_or_recent:
                anchor = live_or_recent[-1]
            else:
                anchor = all_rows[-1]

        r0 = _round_key(anchor) if anchor else None
        if r0:
            matched = [f for f in all_rows if _round_key(f) == r0]
        elif anchor:
            d0 = anchor.kickoff_at.date()
            matched = [f for f in all_rows if f.kickoff_at and f.kickoff_at.date() == d0]
        else:
            matched = all_rows
        return matched[:limit]

    @staticmethod
    def _load_sot_predictions(
        db: Session,
        fixture_id: int,
        home_team_id: int,
        away_team_id: int,
        model_id: str,
    ) -> tuple[float | None, float | None, dict[str, Any], str | None]:
        home_row = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture_id),
                TeamSotPrediction.team_id == int(home_team_id),
                TeamSotPrediction.model_version == model_id,
            ),
        )
        away_row = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture_id),
                TeamSotPrediction.team_id == int(away_team_id),
                TeamSotPrediction.model_version == model_id,
            ),
        )
        payload: dict[str, Any] = {}
        if home_row and isinstance(home_row.raw_json, dict):
            payload["home"] = home_row.raw_json
        if away_row and isinstance(away_row.raw_json, dict):
            payload["away"] = away_row.raw_json
        h = float(home_row.predicted_sot) if home_row and home_row.predicted_sot is not None else None
        a = float(away_row.predicted_sot) if away_row and away_row.predicted_sot is not None else None
        if h is not None and a is not None:
            src = PREDICTION_SOURCE_DB_V20 if model_id == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT else PREDICTION_SOURCE_DB_V11
            return h, a, payload, src
        return None, None, payload, None

    def _resolve_prediction(
        self,
        db: Session,
        fx: Fixture,
        *,
        model_id: str,
        pick_type: str,
        strict_model: bool = False,
    ) -> tuple[float | None, float | None, dict[str, Any], str | None, str | None, bool]:
        """Ritorna home, away, raw_pred, prediction_source, backfill_warning, is_backfilled."""
        pick_svc = TrackedBettingPickService()
        certified = pick_svc.get_auto_pre_match(
            db,
            int(fx.id),
            model_id=model_id,
            market_id=MARKET_MATCH_TOTAL,
            pick_type=pick_type,
        )
        if certified is not None and certified.suggested_pick:
            return (
                certified.predicted_home_sot,
                certified.predicted_away_sot,
                certified.raw_prediction_payload or {},
                PREDICTION_SOURCE_CERTIFIED,
                None,
                False,
            )

        h, a, raw, src = self._load_sot_predictions(
            db,
            int(fx.id),
            int(fx.home_team_id),
            int(fx.away_team_id),
            model_id,
        )
        if h is not None and a is not None:
            ko = fx.kickoff_at
            if ko is not None and ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
            kickoff_passed = ko is not None and ko < _utcnow()
            is_bf = kickoff_passed or (fx.status or "").upper() in FINISHED_STATUSES
            warn = BACKFILL_WARNING_RECONSTRUCTED if is_bf else None
            pred_src = src or PREDICTION_SOURCE_RECONSTRUCTED
            return h, a, raw, pred_src, warn, is_bf

        if strict_model:
            return None, None, {}, None, None, True

        if model_id != BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT:
            h, a, raw, src = self._load_sot_predictions(
                db,
                int(fx.id),
                int(fx.home_team_id),
                int(fx.away_team_id),
                BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
            )
            if h is not None and a is not None:
                return h, a, raw, PREDICTION_SOURCE_DB_V20, BACKFILL_WARNING_RECONSTRUCTED, True

        h11, a11, raw11, _ = self._load_sot_predictions(
            db,
            int(fx.id),
            int(fx.home_team_id),
            int(fx.away_team_id),
            BASELINE_SOT_MODEL_VERSION_V11_SOT,
        )
        if h11 is not None and a11 is not None:
            return h11, a11, raw11, PREDICTION_SOURCE_DB_V11, BACKFILL_WARNING_RECONSTRUCTED, True

        return None, None, {}, None, None, True

    def create_from_round(
        self,
        db: Session,
        season_year: int,
        *,
        round_key: str = "current",
        model_id: str | None = None,
        pick_type: str = PICK_TYPE_CAUTIOUS,
        force: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        _ = round_key
        strict_model = model_id is not None
        mid = model_id or BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
        if pick_type not in (PICK_TYPE_CAUTIOUS, PICK_TYPE_STATISTICAL):
            pick_type = PICK_TYPE_CAUTIOUS

        fixtures = self.current_round_fixtures(db, season_year, limit=limit)
        if not fixtures:
            return {
                "status": "success",
                "season": season_year,
                "fixtures_total": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "errors": [],
                "warnings": ["Nessuna fixture nel turno corrente."],
            }

        pick_svc = TrackedBettingPickService()
        created = updated = skipped = 0
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []

        for fx in fixtures:
            fid = int(fx.id)
            home_t = db.get(Team, int(fx.home_team_id))
            away_t = db.get(Team, int(fx.away_team_id))
            try:
                home_sot, away_sot, raw_pred, pred_src, bf_warn, is_bf = self._resolve_prediction(
                    db,
                    fx,
                    model_id=mid,
                    pick_type=pick_type,
                    strict_model=strict_model,
                )
                if home_sot is None or away_sot is None:
                    errors.append(
                        {
                            "fixture_id": fid,
                            "match": f"{home_t.name if home_t else '?'} – {away_t.name if away_t else '?'}",
                            "error": "Predizioni non disponibili",
                        },
                    )
                    continue

                lu = lineup_row_for_fixture(db, fid)
                lineup_status = formation_status_from_lineup(lu)
                advice_ctx = advice_context_from_upcoming_lineup(lineup_status)
                advice = build_fixture_betting_advice(
                    home_sot,
                    away_sot,
                    model_version=mid,
                    context=advice_ctx,
                    home_team_name=home_t.name if home_t else None,
                    away_team_name=away_t.name if away_t else None,
                )
                match = advice.get("match_total") if isinstance(advice.get("match_total"), dict) else {}
                key = "cautious_pick" if pick_type == PICK_TYPE_CAUTIOUS else "statistical_pick"
                suggested = match.get(key)
                if not suggested:
                    errors.append({"fixture_id": fid, "error": f"Nessun {key} nel betting advice"})
                    continue

                line_ln = (
                    match.get("cautious_line")
                    if pick_type == PICK_TYPE_CAUTIOUS
                    else match.get("statistical_line")
                )
                if bf_warn and bf_warn not in warnings:
                    warnings.append(bf_warn)

                action = pick_svc.upsert_backfill_round(
                    db,
                    fixture_id=fid,
                    model_id=mid,
                    pick_type=pick_type,
                    suggested_pick=str(suggested),
                    line_value=float(line_ln) if line_ln is not None else None,
                    predicted_home_sot=round(float(home_sot), 2),
                    predicted_away_sot=round(float(away_sot), 2),
                    predicted_total_sot=round(float(home_sot) + float(away_sot), 2),
                    confidence_label=match.get("confidence_label"),
                    lineup_confirmed=bool(lu.confirmed) if lu else False,
                    lineup_fetched_at=lu.fetched_at if lu else None,
                    raw_prediction_payload=raw_pred,
                    raw_betting_advice_payload=advice,
                    is_backfilled=is_bf,
                    prediction_source=pred_src,
                    backfill_warning=bf_warn,
                    force=force,
                )
                if action == "created":
                    created += 1
                elif action == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("backfill fixture %s", fid)
                errors.append({"fixture_id": fid, "error": str(exc)[:200]})

        db.commit()
        return {
            "status": "success",
            "season": season_year,
            "model_id": mid,
            "model_version": mid,
            "pick_type": pick_type,
            "fixtures_total": len(fixtures),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "warnings": warnings,
        }

    def current_round_fixtures_for_competition(
        self, db: Session, competition_id: int, *, limit: int = 50
    ) -> list[Fixture]:
        from app.services.next_round_selection import select_next_round_fixtures

        all_rows = list(
            db.scalars(
                select(Fixture)
                .where(Fixture.competition_id == int(competition_id))
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all(),
        )
        upcoming = [f for f in all_rows if (f.status or "").upper() not in FINISHED_STATUSES]
        selection = select_next_round_fixtures(upcoming, limit=limit, only_next_round=True)
        return selection.fixtures

    def create_from_competition(
        self,
        db: Session,
        competition_id: int,
        *,
        round_key: str = "current",
        model_id: str | None = None,
        pick_type: str = PICK_TYPE_CAUTIOUS,
        force: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        from app.models import Competition

        comp = db.get(Competition, int(competition_id))
        if comp is None:
            return {
                "status": "error",
                "message": f"Competition {competition_id} non trovata.",
                "competition_id": int(competition_id),
            }
        _ = round_key
        strict_model = model_id is not None
        mid = model_id or BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
        if pick_type not in (PICK_TYPE_CAUTIOUS, PICK_TYPE_STATISTICAL):
            pick_type = PICK_TYPE_CAUTIOUS

        fixtures = self.current_round_fixtures_for_competition(db, int(competition_id), limit=limit)
        if not fixtures:
            return {
                "status": "success",
                "competition_id": int(competition_id),
                "competition_key": comp.key,
                "season": int(comp.season),
                "model_id": mid,
                "model_version": mid,
                "fixtures_total": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "errors": [],
                "warnings": ["Nessuna fixture nel turno corrente."],
            }

        pick_svc = TrackedBettingPickService()
        created = updated = skipped = 0
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []

        for fx in fixtures:
            fid = int(fx.id)
            home_t = db.get(Team, int(fx.home_team_id))
            away_t = db.get(Team, int(fx.away_team_id))
            try:
                home_sot, away_sot, raw_pred, pred_src, bf_warn, is_bf = self._resolve_prediction(
                    db,
                    fx,
                    model_id=mid,
                    pick_type=pick_type,
                    strict_model=strict_model,
                )
                if home_sot is None or away_sot is None:
                    errors.append(
                        {
                            "fixture_id": fid,
                            "match": f"{home_t.name if home_t else '?'} – {away_t.name if away_t else '?'}",
                            "error": f"Predizioni {mid} non disponibili",
                        },
                    )
                    continue

                lu = lineup_row_for_fixture(db, fid)
                lineup_status = formation_status_from_lineup(lu)
                advice_ctx = advice_context_from_upcoming_lineup(lineup_status)
                advice = build_fixture_betting_advice(
                    home_sot,
                    away_sot,
                    model_version=mid,
                    context=advice_ctx,
                    home_team_name=home_t.name if home_t else None,
                    away_team_name=away_t.name if away_t else None,
                )
                match = advice.get("match_total") if isinstance(advice.get("match_total"), dict) else {}
                key = "cautious_pick" if pick_type == PICK_TYPE_CAUTIOUS else "statistical_pick"
                suggested = match.get(key)
                if not suggested:
                    errors.append({"fixture_id": fid, "error": f"Nessun {key} nel betting advice"})
                    continue

                line_ln = (
                    match.get("cautious_line")
                    if pick_type == PICK_TYPE_CAUTIOUS
                    else match.get("statistical_line")
                )
                if bf_warn and bf_warn not in warnings:
                    warnings.append(bf_warn)

                action = pick_svc.upsert_backfill_round(
                    db,
                    fixture_id=fid,
                    model_id=mid,
                    pick_type=pick_type,
                    suggested_pick=str(suggested),
                    line_value=float(line_ln) if line_ln is not None else None,
                    predicted_home_sot=round(float(home_sot), 2),
                    predicted_away_sot=round(float(away_sot), 2),
                    predicted_total_sot=round(float(home_sot) + float(away_sot), 2),
                    confidence_label=match.get("confidence_label"),
                    lineup_confirmed=bool(lu.confirmed) if lu else False,
                    lineup_fetched_at=lu.fetched_at if lu else None,
                    raw_prediction_payload=raw_pred,
                    raw_betting_advice_payload=advice,
                    is_backfilled=is_bf,
                    prediction_source=pred_src,
                    backfill_warning=bf_warn,
                    force=force,
                )
                if action == "created":
                    created += 1
                elif action == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("backfill competition=%s fixture %s", competition_id, fid)
                errors.append({"fixture_id": fid, "error": str(exc)[:200]})

        db.commit()
        return {
            "status": "success",
            "competition_id": int(competition_id),
            "competition_key": comp.key,
            "season": int(comp.season),
            "model_id": mid,
            "model_version": mid,
            "pick_type": pick_type,
            "fixtures_total": len(fixtures),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "warnings": warnings,
        }
