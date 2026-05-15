"""Debug read-only: 9 feature produzione offensiva v1.1 (strict)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture, Team
from app.services.predictions_v10.v10_prior_context import build_prior_context
from app.services.predictions_v10.offensive_production_blend import offensive_inputs_as_map
from app.services.predictions_v11.offensive_production_strict import compute_v11_side


def build_fixture_features_debug_v11(
    db: Session,
    fixture_id: int,
    *,
    model_version: str = BASELINE_SOT_MODEL_VERSION_V11_SOT,
) -> dict[str, Any]:
    if model_version != BASELINE_SOT_MODEL_VERSION_V11_SOT:
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
            ctx = build_prior_context(db, fx, team_id=int(team_id), opponent_id=int(opponent_id))
            result = compute_v11_side(db, ctx, ctx.team_prior_fixtures)
        except Exception as exc:  # noqa: BLE001
            return {
                "team": team.name if team else str(team_id),
                "team_id": int(team_id),
                "status": "error",
                "message": str(exc)[:500],
                "features": [],
                "offensive_component_inputs": [],
            }

        raw = result.raw_json
        off = result.component or {}
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
                    "db_field": blob.get("db_field"),
                    "sample_count": blob.get("sample_count"),
                    "fallback_used": False,
                    "status": blob.get("status") or ("missing_required_data" if not result.valid else "available"),
                    "application_role": "component_input",
                    "parent_component": "offensive_production_component",
                },
            )

        return {
            "team": team.name if team else str(team_id),
            "team_id": int(team_id),
            "status": "ok" if result.valid else str(raw.get("formula_quality_status") or "incomplete"),
            "prediction_valid": result.valid,
            "expected_sot": result.expected_sot,
            "formula_quality_status": result.formula_quality_status,
            "missing_required_fields": result.missing_required_fields,
            "offensive_production_component": {
                "value": off.get("value"),
                "quality": off.get("quality"),
            },
            "offensive_component_inputs": offensive_inputs,
            "features": offensive_inputs,
        }

    return {
        "status": "ok",
        "fixture_id": int(fixture_id),
        "model_version": model_version,
        "model_stage": "offensive_production_only",
        "home": _side(int(fx.home_team_id), int(fx.away_team_id)),
        "away": _side(int(fx.away_team_id), int(fx.home_team_id)),
    }
