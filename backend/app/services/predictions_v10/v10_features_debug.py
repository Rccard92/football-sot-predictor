"""Debug read-only: feature risolte per fixture (v1.0 registry)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V10_SOT
from app.models import Fixture, Team
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
        resolved = resolve_side_features(db, fx, team_id=int(team_id), opponent_id=int(opponent_id))
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
                },
            )
        off = resolved.get("offensive_component") if isinstance(resolved.get("offensive_component"), dict) else {}
        inputs = off.get("inputs") if isinstance(off.get("inputs"), dict) else {}
        offensive_inputs = [
            {
                "key": k,
                "value": (v or {}).get("value"),
                "source_path": (v or {}).get("source_path"),
                "fallback_used": (v or {}).get("fallback_used"),
                "status": (v or {}).get("status"),
            }
            for k, v in inputs.items()
            if isinstance(v, dict)
        ]
        return {
            "team": team.name if team else str(team_id),
            "team_id": int(team_id),
            "features": features,
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
