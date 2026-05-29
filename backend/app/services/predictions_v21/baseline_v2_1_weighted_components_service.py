"""Service v2.1 — engine autonomo SOT Weighted Components."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS, FINISHED_STATUSES
from app.models import Fixture, Team, TeamSotPrediction
from app.services.model_applied_variable_trace import append_trace_to_raw_json, compute_hours_to_kickoff
from app.services.predictions_v21.v21_constants import V21_ENGINE_STATUS_READY
from app.services.predictions_v21.v21_prediction_engine import build_v21_prediction_for_fixture
from app.services.sot_model_registry import get_model_display

V21_ENGINE_NOT_READY_MESSAGE = "Modello v2.1 registrato, engine di calcolo in preparazione"


class SotPredictionV21WeightedComponentsService:
    model_version = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    engine_status = V21_ENGINE_STATUS_READY

    def _upsert_side(
        self,
        db: Session,
        *,
        fixture: Fixture,
        competition_id: int,
        team_id: int,
        side_result: dict[str, Any],
    ) -> bool:
        raw = side_result.get("raw_json")
        if not isinstance(raw, dict):
            return False

        team_row = db.get(Team, int(team_id))
        tname = team_row.name if team_row is not None else str(team_id)
        raw = append_trace_to_raw_json(
            raw,
            model_version=self.model_version,
            team_id=int(team_id),
            team_name=tname,
            audit_map={},
            hours_to_kickoff=compute_hours_to_kickoff(fixture.kickoff_at),
            prediction_confidence=side_result.get("confidence_score"),
        )

        existing = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture.id),
                TeamSotPrediction.team_id == int(team_id),
                TeamSotPrediction.model_version == self.model_version,
            ),
        )
        if existing is None:
            existing = TeamSotPrediction(
                fixture_id=int(fixture.id),
                team_id=int(team_id),
                model_version=self.model_version,
            )
            db.add(existing)

        existing.competition_id = int(competition_id)
        existing.predicted_sot = side_result.get("predicted_sot")
        existing.confidence_score = side_result.get("confidence_score")
        existing.raw_json = raw
        existing.explanation = (
            "v2.1 SOT Weighted Components: base_anchor_sot × weighted_macro_multiplier "
            "(macroaree 1-9; macro 10 solo confidence/quality)."
        )
        return True

    def generate_for_fixture(self, db: Session, fixture_id: int, *, competition_id: int | None = None) -> dict[str, Any]:
        fx = db.get(Fixture, int(fixture_id))
        if fx is None:
            return {"status": "error", "message": "fixture_not_found", "fixture_id": int(fixture_id)}
        comp_id = competition_id if competition_id is not None else fx.competition_id
        if comp_id is None:
            return {"status": "error", "message": "competition_id_required", "fixture_id": int(fixture_id)}

        result = build_v21_prediction_for_fixture(db, competition_id=int(comp_id), fixture_id=int(fixture_id))
        if result.get("status") == "error":
            return result

        saved = 0
        for side_result in result.get("sides") or []:
            if not isinstance(side_result, dict):
                continue
            tid = side_result.get("team_id")
            if tid is None:
                continue
            if self._upsert_side(db, fixture=fx, competition_id=int(comp_id), team_id=int(tid), side_result=side_result):
                saved += 1
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            return {"status": "error", "message": "persist_failed", "details": str(exc), "fixture_id": int(fixture_id)}

        display = get_model_display(self.model_version)
        return {
            "status": result.get("status") or "ok",
            "model_version": self.model_version,
            "model_label": display.label if display else self.model_version,
            "fixture_id": int(fixture_id),
            "competition_id": int(comp_id),
            "predictions_saved": saved,
            "home_predicted_sot": result.get("home_predicted_sot"),
            "away_predicted_sot": result.get("away_predicted_sot"),
            "total_predicted_sot": result.get("total_predicted_sot"),
            "warnings": result.get("warnings") or [],
        }

    def generate_for_competition(
        self,
        db: Session,
        competition_id: int,
        *,
        season_year: int | None = None,
        fixture_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        if fixture_ids:
            fixtures = list(
                db.scalars(
                    select(Fixture)
                    .where(
                        Fixture.competition_id == int(competition_id),
                        Fixture.id.in_([int(x) for x in fixture_ids]),
                    )
                    .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
                ).all(),
            )
        else:
            q = select(Fixture).where(Fixture.competition_id == int(competition_id)).order_by(
                Fixture.kickoff_at.asc(),
                Fixture.id.asc(),
            )
            fixtures = list(db.scalars(q).all())

        upcoming = [f for f in fixtures if (f.status or "").upper() not in FINISHED_STATUSES]
        if not upcoming:
            return {
                "status": "error",
                "message": "no_upcoming_fixtures",
                "competition_id": int(competition_id),
                "predictions_created_or_updated": 0,
            }

        processed = 0
        saved_total = 0
        warnings: list[str] = []
        errors: list[dict[str, Any]] = []

        for fx in upcoming:
            try:
                out = self.generate_for_fixture(db, int(fx.id), competition_id=int(competition_id))
            except Exception as exc:  # noqa: BLE001
                errors.append({"fixture_id": int(fx.id), "error": str(exc)[:300]})
                continue
            if out.get("status") == "error":
                errors.append({"fixture_id": int(fx.id), "error": out.get("message"), "details": out.get("details")})
                continue
            processed += 1
            saved_total += int(out.get("predictions_saved") or 0)
            warnings.extend(out.get("warnings") or [])

        display = get_model_display(self.model_version)
        status = "ok" if saved_total > 0 else "error"
        if saved_total > 0 and errors:
            status = "partial"

        return {
            "status": status,
            "competition_id": int(competition_id),
            "model_version": self.model_version,
            "model_label": display.label if display else self.model_version,
            "season_year": season_year,
            "fixtures_processed": processed,
            "predictions_created_or_updated": saved_total,
            "warnings": warnings[:50],
            "errors": errors,
        }

    def generate_for_upcoming_season(
        self,
        db: Session,
        season_year: int,
        *,
        competition_id: int | None = None,
        fixture_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        if competition_id is None:
            return {
                "status": "error",
                "message": "competition_id_required_for_v21",
                "season_year": int(season_year),
            }
        return self.generate_for_competition(
            db,
            int(competition_id),
            season_year=int(season_year),
            fixture_ids=fixture_ids,
        )
