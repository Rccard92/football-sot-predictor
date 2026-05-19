"""Tipi conmotioni per provider availability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]
ApplicabilityStatus = Literal["applied", "not_applied", "candidate"]


@dataclass
class NormalizedAvailabilityCandidate:
    fixture_id: int
    api_fixture_id: int
    season: int
    league_id: int
    api_league_id: int
    team_id: int | None
    api_team_id: int | None
    team_name: str | None
    player_id: Any | None
    api_player_id: int | None
    player_name: str
    availability_status: str
    availability_type: str | None
    reason: str | None
    source: str
    source_detail: str
    record_scope: str
    confidence: ConfidenceLevel
    applicability_status: ApplicabilityStatus
    applicability_reason: str | None
    start_date: date | None = None
    end_date: date | None = None
    fixture_date: date | None = None
    reported_at: datetime | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "player_name": self.player_name,
            "api_player_id": self.api_player_id,
            "team_name": self.team_name,
            "source": self.source,
            "source_detail": self.source_detail,
            "record_scope": self.record_scope,
            "confidence": self.confidence,
            "applicability_status": self.applicability_status,
            "applicability_reason": self.applicability_reason,
            "availability_status": self.availability_status,
            "availability_type": self.availability_type,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }
