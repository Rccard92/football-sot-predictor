"""Schema API monitoraggio segnali Cecchino."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CecchinoSignalsRevaluateBody(BaseModel):
    date_from: date
    date_to: date
    force: bool = False
