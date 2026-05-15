"""Debug read-only: feature v1.1 offensiva (9) + difensiva (6) + split (5) + forma recente (6) + xG (5)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture, Team
from app.services.predictions_v10.v10_prior_context import build_prior_context
from app.services.predictions_v10.offensive_production_blend import offensive_inputs_as_map
from app.services.predictions_v11.offensive_production_strict import compute_v11_side
from app.services.sot_feature_registry import V11_MODEL_STAGE


def _recent_goals_debug(recentc: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(recentc, dict):
        return None
    inp = recentc.get("inputs")
    if not isinstance(inp, list):
        return None
    for x in inp:
        if isinstance(x, dict) and x.get("key") == "recent_avg_goals_for":
            norm = x.get("normalization") if isinstance(x.get("normalization"), dict) else {}
            return {
                "recent_avg_goals_for": x.get("raw_value"),
                "league_recent_avg_goals_for": norm.get("league_recent_avg_goals_for"),
                "recent_goals_for_scaled": x.get("normalized_value"),
                "league_recent_avg_sot_for": norm.get("league_recent_avg_sot_for"),
                "source_path": x.get("source_path"),
                "sample_count": x.get("sample_count"),
                "status": x.get("status"),
            }
    return None


def _inputs_from_component(comp: dict[str, Any] | None, parent: str) -> list[dict[str, Any]]:
    if not comp:
        return []
    out: list[dict[str, Any]] = []
    for k, blob in offensive_inputs_as_map(comp).items():
        if not isinstance(blob, dict):
            continue
        row: dict[str, Any] = {
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
            "split_context": blob.get("split_context"),
            "fallback_used": False,
            "status": blob.get("status"),
            "application_role": "component_input",
            "parent_component": parent,
        }
        if "normalization" in blob:
            row["normalization"] = blob.get("normalization")
        if "no_data_leakage" in blob:
            row["no_data_leakage"] = blob.get("no_data_leakage")
        out.append(row)
    return out


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
                "defensive_component_inputs": [],
                "split_component_inputs": [],
                "recent_component_inputs": [],
                "recent_goals_debug": None,
                "xg_component_inputs": [],
            }

        raw = result.raw_json
        off = result.component or {}
        defc = result.defensive_component or {}
        splitc = result.split_component or {}
        recentc = result.recent_component or {}
        xgc = result.xg_component or {}
        offensive_inputs = _inputs_from_component(off, "offensive_production_component")
        defensive_inputs = _inputs_from_component(defc, "opponent_defensive_resistance_component")
        split_inputs = _inputs_from_component(splitc, "home_away_split_component")
        recent_inputs = _inputs_from_component(recentc, "recent_form_component")
        xg_inputs = _inputs_from_component(xgc, "xg_chance_quality_component")

        return {
            "team": team.name if team else str(team_id),
            "team_id": int(team_id),
            "status": "ok" if result.valid else str(raw.get("formula_quality_status") or "incomplete"),
            "prediction_valid": result.valid,
            "expected_sot": result.expected_sot,
            "formula_quality_status": result.formula_quality_status,
            "formula_terms_count": (raw.get("formula") or {}).get("terms_count")
            if isinstance(raw.get("formula"), dict)
            else None,
            "missing_required_fields": result.missing_required_fields,
            "offensive_production_component": {"value": off.get("value"), "quality": off.get("quality")},
            "opponent_defensive_resistance_component": {"value": defc.get("value"), "quality": defc.get("quality")},
            "home_away_split_component": {
                "value": splitc.get("value"),
                "quality": splitc.get("quality"),
                "split_context": splitc.get("split_context"),
                "opponent_split_context": splitc.get("opponent_split_context"),
            },
            "recent_form_component": {
                "value": recentc.get("value"),
                "quality": recentc.get("quality"),
                "league_baselines_recent": recentc.get("league_baselines_recent"),
            },
            "xg_chance_quality_component": {"value": xgc.get("value"), "quality": xgc.get("quality")},
            "offensive_component_inputs": offensive_inputs,
            "defensive_component_inputs": defensive_inputs,
            "split_component_inputs": split_inputs,
            "recent_component_inputs": recent_inputs,
            "recent_goals_debug": _recent_goals_debug(recentc),
            "xg_component_inputs": xg_inputs,
            "features": offensive_inputs + defensive_inputs + split_inputs + recent_inputs + xg_inputs,
        }

    return {
        "status": "ok",
        "fixture_id": int(fixture_id),
        "model_version": model_version,
        "model_stage": V11_MODEL_STAGE,
        "home": _side(int(fx.home_team_id), int(fx.away_team_id)),
        "away": _side(int(fx.away_team_id), int(fx.home_team_id)),
    }
