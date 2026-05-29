"""Stub service v2.1 — registry e manifest senza engine numerico (Step 1)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.services.sot_model_registry import get_model_display

V21_ENGINE_NOT_READY_MESSAGE = "Modello v2.1 registrato, engine di calcolo in preparazione"


class SotPredictionV21WeightedComponentsService:
    model_version = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    engine_status = "experimental_not_ready"

    def generate_for_fixture(self, db: Session, fixture_id: int) -> dict[str, Any]:
        _ = db
        display = get_model_display(self.model_version)
        return {
            "status": self.engine_status,
            "message": V21_ENGINE_NOT_READY_MESSAGE,
            "model_version": self.model_version,
            "model_label": display.label if display else self.model_version,
            "fixture_id": int(fixture_id),
            "predictions_saved": 0,
        }

    def generate_for_competition(
        self,
        db: Session,
        competition_id: int,
        *,
        season_year: int | None = None,
    ) -> dict[str, Any]:
        _ = db
        display = get_model_display(self.model_version)
        return {
            "status": self.engine_status,
            "message": V21_ENGINE_NOT_READY_MESSAGE,
            "model_version": self.model_version,
            "model_label": display.label if display else self.model_version,
            "competition_id": int(competition_id),
            "season_year": season_year,
            "predictions_saved": 0,
        }

    def generate_for_upcoming_season(
        self,
        db: Session,
        season_year: int,
        *,
        competition_id: int | None = None,
    ) -> dict[str, Any]:
        _ = db
        display = get_model_display(self.model_version)
        return {
            "status": self.engine_status,
            "message": V21_ENGINE_NOT_READY_MESSAGE,
            "model_version": self.model_version,
            "model_label": display.label if display else self.model_version,
            "season_year": int(season_year),
            "competition_id": competition_id,
            "predictions_saved": 0,
        }
