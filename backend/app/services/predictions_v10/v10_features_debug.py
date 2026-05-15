"""Debug read-only: feature risolte per fixture (v1.0 registry)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V10_SOT
from app.models import Fixture, Team
from app.services.predictions_v10.offensive_production_blend import offensive_inputs_as_map
from app.services.predictions_v10.v10_feature_resolvers import resolve_side_features


def build_fixture_features_debug(
    db: Session,
    fixture_id: int,
    *,
    model_version: str = BASELINE_SOT_MODEL_VERSION_V10_SOT,
) -> dict[str, Any]:
    if model_version != BASELINE_SOT_MODEL_VERSION_V10_SOT:
        return {
            "status": "error",
            "message": f"model_version non supportato: {model_version}",
            "fixture_id": int(fixture_id),
        }

    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {"status": "missing", "message": "Fixture non trovata", "fixture_id": int(fixture_id)}

    def _side(team_id: int, opponent_id: int) -> dict[str, Any]:
        team = db.get(Team, int(team_id))
        try:
            resolved = resolve_side_features(db, fx, team_id=int(team_id), opponent_id=int(opponent_id))
        except Exception as exc:  # noqa: BLE001
            return {
                "team": team.name if team else str(team_id),
                "team_id": int(team_id),
                "status": "error",
                "message": str(exc)[:500],
                "features": [],
                "offensive_component_inputs": [],
            }
        features: list[dict[str, Any]] = []
        for t in resolved["base_terms"] + [resolved["xg_term"]]:
            features.append(
                {
                    "key": t.key,
                    "label": t.label,
                    "value": t.value,
                    "weight": t.weight,
                    "contribution": t.contribution,
                    "source": f"{t.source_table}.{t.source_field}",
                    "source_path": t.source_path,
                    "sample_count": t.sample_count,
                    "fallback_used": t.fallback_used,
                    "fallback_reason": t.fallback_reason,
                    "status": t.status,
                    "application_role": "direct_formula_component",
                },
            )
        off = resolved.get("offensive_component") if isinstance(resolved.get("offensive_component"), dict) else {}
        offensive_inputs: list[dict[str, Any]] = []
        for k, blob in offensive_inputs_as_map(off).items():
            if not isinstance(blob, dict):
                continue
            offensive_inputs.append(
                {
                    "key": k,
                    "label": blob.get("label"),
                    "raw_value": blob.get("raw_value"),
                    "normalized_value": blob.get("normalized_value"),
                    "internal_weight": blob.get("internal_weight"),
                    "internal_contribution": blob.get("internal_contribution"),
                    "source_path": blob.get("source_path"),
                    "api_source": blob.get("api_source"),
                    "sample_count": blob.get("sample_count"),
                    "fallback_used": blob.get("fallback_used"),
                    "application_role": "component_input",
                    "parent_component": "offensive_production_component",
                },
            )
        return {
            "team": team.name if team else str(team_id),
            "team_id": int(team_id),
            "features": features,
            "offensive_production_component": {
                "value": off.get("value"),
                "weight_in_final_formula": off.get("weight_in_final_formula"),
                "contribution_in_final_formula": off.get("contribution_in_final_formula"),
                "quality": off.get("quality"),
            },
            "offensive_component_inputs": offensive_inputs,
            "base_explicit_sot": resolved["base_explicit_sot"],
            "final_sot": resolved["final_sot"],
            "formula_quality_status": (resolved.get("quality_meta") or {}).get("formula_quality_status"),
            "formula_quality_warnings": (resolved.get("quality_meta") or {}).get("formula_quality_warnings"),
        }

    return {
        "status": "success",
        "fixture_id": int(fixture_id),
        "model_version": model_version,
        "home": _side(int(fx.home_team_id), int(fx.away_team_id)),
        "away": _side(int(fx.away_team_id), int(fx.home_team_id)),
    }
