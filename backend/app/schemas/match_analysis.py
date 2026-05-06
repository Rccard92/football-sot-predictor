from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


AuditVariableStatus = Literal["available", "missing", "partial", "not_applicable"]
AuditMode = Literal["pre_match", "post_match"]
AuditMarket = Literal["shots_on_target"]
AuditImplementationStatus = Literal["implemented", "partial", "debug_only", "todo"]


class AuditTeamBlock(BaseModel):
    id: int
    name: str
    logo_url: str | None = None


class AuditFixtureBlock(BaseModel):
    fixture_id: int
    api_fixture_id: int
    round: str | None
    kickoff_at: datetime
    status_short: str
    home_team: AuditTeamBlock
    away_team: AuditTeamBlock


class AuditDataPolicyBlock(BaseModel):
    no_data_leakage: bool
    included_matches_rule: str


class AuditCalculationBlock(BaseModel):
    formula: str
    # Campi liberi per audit (sum, matches_count, ecc.)
    meta: dict[str, Any] | None = None
    result: float | None = None


class AuditSampleRow(BaseModel):
    fixture_id: int
    date: datetime
    home_team: str
    away_team: str
    team: str
    team_id: int
    opponent: str
    opponent_id: int
    side: Literal["home", "away"]
    shots_on_target: int | None = None
    total_shots: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None


class AuditVariable(BaseModel):
    key: str
    label: str
    team_id: int | None = None
    team_name: str | None = None
    value: float | None = None
    unit: str | None = None
    status: AuditVariableStatus
    implementation_status: AuditImplementationStatus
    applied_to_model: bool
    weight: float | None = None
    weight_label: str | None = None
    source_table: str | None = None
    source_description: str | None = None
    calculation: AuditCalculationBlock | None = None
    sample_rows: list[AuditSampleRow] = []
    notes: str | None = None


class AuditSection(BaseModel):
    id: str
    title: str
    variables: list[AuditVariable]
    variables_available: int
    variables_missing: int
    completeness_pct: float


class ModelInputsSummary(BaseModel):
    home_team_expected_sot_v01: float | None = None
    away_team_expected_sot_v01: float | None = None
    home_team_expected_sot_v02: float | None = None
    away_team_expected_sot_v02: float | None = None


class MatchVariablesAuditResponse(BaseModel):
    fixture: AuditFixtureBlock
    market: AuditMarket
    mode: AuditMode
    data_policy: AuditDataPolicyBlock
    sections: list[AuditSection]
    model_inputs_summary: ModelInputsSummary


class AuditFixturesListItem(BaseModel):
    fixture_id: int
    api_fixture_id: int
    round: str | None
    kickoff_at: datetime
    status_short: str
    home_team: AuditTeamBlock
    away_team: AuditTeamBlock


class AuditFixturesListResponse(BaseModel):
    season: int | None = None
    scope: Literal["upcoming", "completed", "all"]
    fixtures: list[AuditFixturesListItem]


class AuditErrorResponse(BaseModel):
    status: Literal["error"]
    message: str
    failed_step: str
    details: str | None = None

