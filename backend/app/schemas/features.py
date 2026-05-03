from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TeamSotFeatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fixture_id: int
    team_id: int
    feature_set_version: str | None
    features: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class SotFeatureBuildResponse(BaseModel):
    league_id: int
    season: int
    rows_upserted: int


class SotFixtureFeaturesResponse(BaseModel):
    fixture_id: int
    rows: list[TeamSotFeatureRead]
