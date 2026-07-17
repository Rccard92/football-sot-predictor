"""Schemi API audit Intensità Goal v5 — Fase 1A."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator


class CecchinoGoalIntensityV5AuditBody(BaseModel):
    date_from: date
    date_to: date
    competition_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from deve essere <= date_to")
        if (self.date_to - self.date_from).days > 365 * 5:
            raise ValueError("Il range massimo consentito è 5 anni")
        return self
