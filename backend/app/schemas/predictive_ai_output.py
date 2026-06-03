"""Schemi output analisi AI mirata."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AnalysisType = Literal[
    "missed_high_non_extreme",
    "false_high_predictions",
    "top3_model_comparison",
    "single_fixture",
]


class KeyEvidenceItem(BaseModel):
    metric: str
    value: str
    interpretation: str


class RootCauseItem(BaseModel):
    cause: str
    evidence: str
    affected_models: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high"] = "medium"


class RecommendedExperimentItem(BaseModel):
    experiment_name: str
    hypothesis: str
    change_to_test: str
    expected_benefit: str
    risk: str
    success_metric: str


class DoNotOverreactItem(BaseModel):
    case: str
    reason: str


class FixtureNoteItem(BaseModel):
    match: str = ""
    predicted: str | float | None = None
    actual: str | float | None = None
    error: str | float | None = None
    reason_codes: list[str] | str = Field(default_factory=list)
    diagnosis: str = ""


class AiAuditBlock(BaseModel):
    openai_analysis_no_weight_mutation: bool = True
    no_sot_prediction: bool = True


class PredictiveAiOutputSchema(BaseModel):
    analysis_type: str
    short_verdict: str = ""
    key_evidence: list[KeyEvidenceItem] = Field(default_factory=list)
    root_causes: list[RootCauseItem] = Field(default_factory=list)
    recommended_experiments: list[RecommendedExperimentItem] = Field(default_factory=list)
    do_not_overreact_to: list[DoNotOverreactItem] = Field(default_factory=list)
    next_action: str = ""
    fixture_notes: list[FixtureNoteItem] = Field(default_factory=list)
    audit: AiAuditBlock = Field(default_factory=AiAuditBlock)

    @field_validator("key_evidence", "root_causes", "recommended_experiments", "do_not_overreact_to", "fixture_notes", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> Any:
        return v if v is not None else []


def normalize_ai_output(raw: dict[str, Any], analysis_type: str) -> dict[str, Any]:
    """Valida e normalizza output OpenAI; fallback su campi mancanti."""
    raw = dict(raw or {})
    raw.setdefault("analysis_type", analysis_type)
    raw.setdefault("audit", {})
    if isinstance(raw["audit"], dict):
        raw["audit"].setdefault("openai_analysis_no_weight_mutation", True)
        raw["audit"].setdefault("no_sot_prediction", True)

    # Migrazione legacy headline -> short_verdict
    if not raw.get("short_verdict") and raw.get("headline"):
        raw["short_verdict"] = raw["headline"]

    # Migrazione legacy structural_issues -> root_causes
    if not raw.get("root_causes") and raw.get("structural_issues"):
        legacy = raw["structural_issues"]
        causes: list[dict[str, Any]] = []
        if isinstance(legacy, list):
            for item in legacy:
                if isinstance(item, str):
                    causes.append({"cause": item, "evidence": "", "affected_models": [], "severity": "medium"})
                elif isinstance(item, dict):
                    causes.append(
                        {
                            "cause": item.get("issue") or item.get("cause") or str(item),
                            "evidence": item.get("description") or item.get("evidence") or "",
                            "affected_models": item.get("affected_models") or [],
                            "severity": item.get("severity") or "medium",
                        },
                    )
        raw["root_causes"] = causes

    try:
        parsed = PredictiveAiOutputSchema.model_validate(raw)
        return parsed.model_dump()
    except Exception:
        return PredictiveAiOutputSchema(
            analysis_type=analysis_type,
            short_verdict=str(raw.get("short_verdict") or raw.get("headline") or "Analisi completata"),
            next_action=str(raw.get("next_action") or "Rivedere evidenze numeriche e pianificare un esperimento."),
        ).model_dump()
