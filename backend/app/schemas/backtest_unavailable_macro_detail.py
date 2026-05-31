"""Schemi trace dettagliato macro indisponibili storici (Step K.5)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UnavailableMacroPlayerDetail(BaseModel):
    player_name: str
    provider_player_id: int | None = None
    player_id: int | None = None
    api_player_id: int | None = None
    mapping_status: str
    status: str
    team_side: str
    role: str | None = None
    prior_matches_count: int = 0
    prior_minutes: int = 0
    prior_sot: int = 0
    prior_shots: int = 0
    prior_sot_per90: float | None = None
    prior_shots_per90: float | None = None
    team_sot_share: float | None = None
    impact_score: float | None = None
    is_important_absence: bool = False
    importance_reason: str = "LOW_IMPACT"


class UnavailableMacroSideDetail(BaseModel):
    source_fixture_id: int
    records_count: int = 0
    mapped_count: int = 0
    unmapped_count: int = 0
    important_absences_count: int = 0
    players: list[UnavailableMacroPlayerDetail] = Field(default_factory=list)
