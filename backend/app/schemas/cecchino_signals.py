"""Schema API monitoraggio segnali Cecchino."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CecchinoSignalsRevaluateBody(BaseModel):
    date_from: date
    date_to: date
    force: bool = False
    sync_missing: bool = False
    force_remap: bool = False
    refresh_signal_odds: bool = False


class CecchinoSignalsBackfillBody(BaseModel):
    date_from: date
    date_to: date
    only_missing: bool = True
    evaluate_after: bool = True
    force_remap: bool = False
