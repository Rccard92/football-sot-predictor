"""Schemi API tracked betting picks / monitoraggio."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models.tracked_betting_pick import PICK_TYPE_CAUTIOUS


class CreateTrackedPicksFromRoundBody(BaseModel):
    round: str = Field(default="current")
    model_id: str = Field(default=BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    pick_type: str = Field(default=PICK_TYPE_CAUTIOUS)
    force: bool = False
