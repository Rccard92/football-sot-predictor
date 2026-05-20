from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SportApiMappingConfirmBody(BaseModel):
    provider_event_id: int
    confidence_score: float | None = None
    matched_by: str | None = None
    raw_payload: dict[str, Any] | None = None
