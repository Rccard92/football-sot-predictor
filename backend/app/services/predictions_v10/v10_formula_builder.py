"""
Assemblaggio formula v1.0 da feature registry + payload raw_json.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Fixture
from app.services.predictions_v10.explicit_terms_from_v04 import build_formula_payload_v10
from app.services.predictions_v10.v10_feature_resolvers import resolve_side_features
from app.services.sot_feature_registry import FEATURE_REGISTRY_VERSION, ResolvedFeature, V10_ARCHITECTURE


def _resolved_to_formula_term(r: ResolvedFeature) -> dict[str, Any]:
    return {
        "key": r.key,
        "label": r.label,
        "value": r.value,
        "weight": r.weight,
        "contribution": r.contribution,
        "formula": r.formula,
        "source": r.api_source,
        "source_table": r.source_table,
        "source_field": r.source_field,
        "api_source": r.api_source,
        "source_path": r.source_path,
        "sample_count": r.sample_count,
        "fallback_used": r.fallback_used,
        "fallback_reason": r.fallback_reason,
        "status": r.status,
        "application_role": r.application_role,
        "cap_applied": False,
        "type": "adjustment_component" if r.key == "expected_goals" else None,
        "parent_component": "xg_quality_component" if r.key == "expected_goals" else None,
    }


def build_v10_side_formula(
    db: Session,
    fixture: Fixture,
    *,
    team_id: int,
    opponent_id: int,
) -> dict[str, Any]:
    resolved = resolve_side_features(db, fixture, team_id=team_id, opponent_id=opponent_id)
    base_terms = [_resolved_to_formula_term(t) for t in resolved["base_terms"]]
    xg_term = _resolved_to_formula_term(resolved["xg_term"])
    base_explicit = float(resolved["base_explicit_sot"])
    final_sot = float(resolved["final_sot"])
    xg_comp = resolved["xg_component"]

    formula_payload = build_formula_payload_v10(
        base_terms,
        base_explicit_sot=base_explicit,
        xg_component=xg_comp if isinstance(xg_comp, dict) else {},
        final_sot=final_sot,
    )
    formula_payload["type"] = "explicit_feature_registry_sum"
    formula_payload["terms_count"] = 7

    off = resolved.get("offensive_component") if isinstance(resolved.get("offensive_component"), dict) else {}

    return {
        "base_terms": base_terms,
        "xg_term": xg_term,
        "formula_payload": formula_payload,
        "base_explicit_sot": base_explicit,
        "final_sot": final_sot,
        "xg_component": xg_comp,
        "quality_meta": resolved["quality_meta"],
        "offensive_production_component": off,
        "feature_registry_version": FEATURE_REGISTRY_VERSION,
        "architecture": V10_ARCHITECTURE,
    }
