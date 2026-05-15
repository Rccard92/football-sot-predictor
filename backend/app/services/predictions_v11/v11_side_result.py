"""Risultato calcolo lato singolo per baseline_v1_1_sot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class V11SideResult:
    valid: bool
    expected_sot: float | None
    component: dict[str, Any] | None
    raw_json: dict[str, Any]
    defensive_component: dict[str, Any] | None = None
    split_component: dict[str, Any] | None = None
    recent_component: dict[str, Any] | None = None
    missing_required_fields: list[dict[str, Any]] = field(default_factory=list)
    formula_quality_status: str = "ok"
    sample_count: int = 0
