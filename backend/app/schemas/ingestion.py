from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: str
    records_processed: int
    error_message: str | None
    meta: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IngestionRunsResponse(BaseModel):
    runs: list[IngestionRunRead]


class BootstrapResponse(BaseModel):
    runs: list[IngestionRunRead]
