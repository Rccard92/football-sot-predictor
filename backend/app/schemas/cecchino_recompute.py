"""Schema API ricalcolo offline Cecchino."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CecchinoRecomputeBody(BaseModel):
    date_from: date
    date_to: date
    scope: str = Field(default="cecchino")
    recompute_kpi: bool = True
    recompute_debug: bool = True
    recompute_balance: bool = True
    recompute_delta_force: bool = True
    recompute_signals: bool = True
    sync_signal_activations: bool = True
    evaluate_signals_after: bool = True
    force_remap_signals: bool = True
    use_existing_bookmaker_odds: bool = True
    refresh_bookmaker_odds: bool = False
