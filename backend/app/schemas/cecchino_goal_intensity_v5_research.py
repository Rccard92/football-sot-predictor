"""Schemi API audit / dataset Intensità Goal v5 — Fase 1A/1B / coorte Today."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.services.cecchino.cecchino_goal_intensity_v5_today_cohort import (
    MIN_GOAL_INTENSITY_TODAY_SCAN_DATE,
    RANGE_ERROR_MESSAGE,
)


class _GoalIntensityScanDateRangeMixin(BaseModel):
    date_from: date
    date_to: date
    competition_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from deve essere <= date_to")
        if (self.date_to - self.date_from).days > 365 * 5:
            raise ValueError("Il range massimo consentito è 5 anni")
        if self.date_to < MIN_GOAL_INTENSITY_TODAY_SCAN_DATE:
            raise ValueError(RANGE_ERROR_MESSAGE)
        return self


class CecchinoGoalIntensityV5AuditBody(_GoalIntensityScanDateRangeMixin):
    pass


class CecchinoGoalIntensityV5DatasetBody(_GoalIntensityScanDateRangeMixin):
    pass


class CecchinoGoalIntensityV5StatisticsBody(_GoalIntensityScanDateRangeMixin):
    minimum_history_sample: int = Field(default=10)
    bootstrap_iterations: int = Field(default=1000, ge=10, le=10000)
    random_seed: int = Field(default=42, ge=0)

    @model_validator(mode="after")
    def validate_statistics_parameters(self):
        if self.minimum_history_sample not in (10, 20):
            raise ValueError("minimum_history_sample deve essere 10 o 20")
        return self


class CecchinoGoalIntensityV5CandidateIndicesBody(_GoalIntensityScanDateRangeMixin):
    minimum_history_sample: int = Field(default=10)
    bootstrap_iterations: int = Field(default=1000, ge=10, le=10000)
    random_seed: int = Field(default=42, ge=0)

    @model_validator(mode="after")
    def validate_candidate_indices_parameters(self):
        if self.minimum_history_sample not in (10, 20):
            raise ValueError("minimum_history_sample deve essere 10 o 20")
        return self
