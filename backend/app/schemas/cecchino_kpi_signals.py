"""Schemi API Segnali KPI Cecchino."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CecchinoKpiSignalsBackfillBody(BaseModel):
    date_from: date
    date_to: date
    only_missing: bool = True
    evaluate_after: bool = True


class CecchinoKpiSignalsRevaluateBody(BaseModel):
    date_from: date
    date_to: date
