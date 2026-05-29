"""Motore di calcolo autonomo v2.1 SOT Weighted Components."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.models import Fixture
from app.services.predictions_v21.v21_constants import (
    PREDICTIVE_MACRO_KEYS,
    QUALITY_MACRO_KEY,
    V21_ENGINE_STATUS_PARTIAL,
    V21_ENGINE_STATUS_READY,
)
from app.services.predictions_v21.v21_feature_collectors import collect_v21_micro_variables
from app.services.predictions_v21.v21_feature_context import V21SideContext, build_v21_side_context
from app.services.predictions_v21.v21_macro_aggregators import (
    V21MacroResult,
    aggregate_v21_macro_score,
    calculate_v21_base_anchor_sot,
    calculate_v21_expected_sot,
    calculate_v21_weighted_macro_multiplier,
)
from app.services.predictions_v21.v21_manifest_definitions import V21MacroAreaSpec, V21_MANIFEST_DEFINITIONS
from app.services.predictions_v21.v21_manifest_validation import validate_v21_manifest
from app.services.predictions_v21.v21_quality_summary import V21QualitySummary, build_v21_quality_summary


def build_v21_trace(
    *,
    side: str,
    team_id: int,
    base_anchor_sot: float | None,
    final_multiplier: float,
    expected_sot: float | None,
    macro_results: list[V21MacroResult],
    quality: V21QualitySummary,
    anchor_warnings: list[str],
    team_sot_avg: float | None = None,
    opponent_sot_conceded_avg: float | None = None,
) -> dict[str, Any]:
    components: dict[str, Any] = {}
    macroareas_audit: list[dict[str, Any]] = []

    for mr in macro_results:
        if mr.key == QUALITY_MACRO_KEY:
            continue
        components[mr.key] = mr.to_components_blob()
        macroareas_audit.append(
            {
                "key": mr.key,
                "label": mr.label,
                "macro_weight": mr.macro_weight,
                "macro_index": mr.macro_index,
                "macro_contribution_to_multiplier": mr.macro_contribution_to_multiplier,
                "coverage_pct": mr.coverage_pct,
                "status": mr.status,
                "warnings": mr.warnings,
                "micros": [
                    {
                        "key": m.key,
                        "label": m.label,
                        "macro_key": mr.key,
                        "macro_label": mr.label,
                        "micro_weight": m.micro_weight,
                        "raw_value": round(float(m.raw_value), 2) if m.raw_value is not None else None,
                        "normalized_value": round(float(m.normalized_value), 2),
                        "source_path": m.source_path,
                        "sample_count": m.sample_count,
                        "status": m.status,
                        "fallback_used": m.fallback_used,
                        "contribution": m.contribution,
                        "warning": m.warning,
                    }
                    for m in mr.micros
                ],
            },
        )

    all_warnings = list(quality.warnings) + anchor_warnings

    anchor_breakdown: dict[str, Any] | None = None
    if team_sot_avg is not None or opponent_sot_conceded_avg is not None:
        anchor_breakdown = {
            "team_sot_avg": round(float(team_sot_avg), 4) if team_sot_avg is not None else None,
            "opponent_sot_conceded_avg": round(float(opponent_sot_conceded_avg), 4)
            if opponent_sot_conceded_avg is not None
            else None,
            "team_weight": 0.55,
            "opponent_weight": 0.45,
        }

    return {
        "engine_status": V21_ENGINE_STATUS_READY,
        "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        "side": side,
        "team_id": int(team_id),
        "base_anchor_sot": base_anchor_sot,
        "final_multiplier": final_multiplier,
        "predicted_sot": expected_sot,
        "anchor_breakdown": anchor_breakdown,
        "confidence_score": quality.confidence_score,
        "components": components,
        "macroareas": macroareas_audit,
        "quality": quality.to_trace_quality_blob(),
        "warnings": all_warnings,
        "formula": {
            "type": "weighted_macro_components",
            "anchor_weights": {"team_sot_for": 0.55, "opponent_sot_conceded": 0.45},
            "predictive_macro_keys": list(PREDICTIVE_MACRO_KEYS),
            "quality_macro_key": QUALITY_MACRO_KEY,
        },
    }


def build_v21_side_prediction(
    db: Session,
    ctx: V21SideContext,
    *,
    side: str,
    manifest_macros: tuple[V21MacroAreaSpec, ...],
) -> dict[str, Any]:
    macro_results: list[V21MacroResult] = []

    for macro_spec in manifest_macros:
        if macro_spec.is_quality_only:
            continue
        micros = collect_v21_micro_variables(macro_spec, ctx)
        macro_results.append(aggregate_v21_macro_score(macro_spec, micros))

    quality = build_v21_quality_summary(
        macro_results,
        side_warnings=ctx.warnings,
        prior_team_count=ctx.prior.team_prior_count,
        prior_opponent_count=ctx.prior.opponent_prior_count,
    )

    base_anchor, anchor_warnings = calculate_v21_base_anchor_sot(
        team_sot_for=ctx.team_agg.get("sot_mean"),
        opponent_sot_conceded=ctx.opp_conceded_agg.get("sot_mean"),
    )
    final_multiplier, _ = calculate_v21_weighted_macro_multiplier(macro_results)
    expected_sot = calculate_v21_expected_sot(
        base_anchor_sot=base_anchor,
        weighted_macro_multiplier=final_multiplier,
    )

    raw_json = build_v21_trace(
        side=side,
        team_id=ctx.team_id,
        base_anchor_sot=base_anchor,
        final_multiplier=final_multiplier,
        expected_sot=expected_sot,
        macro_results=macro_results,
        quality=quality,
        anchor_warnings=anchor_warnings,
        team_sot_avg=ctx.team_agg.get("sot_mean"),
        opponent_sot_conceded_avg=ctx.opp_conceded_agg.get("sot_mean"),
    )

    engine_status = V21_ENGINE_STATUS_READY
    if expected_sot is None or quality.formula_quality_status == "insufficient_data":
        engine_status = V21_ENGINE_STATUS_PARTIAL
    raw_json["engine_status"] = engine_status

    return {
        "team_id": ctx.team_id,
        "side": side,
        "predicted_sot": expected_sot,
        "confidence_score": quality.confidence_score,
        "raw_json": raw_json,
        "quality_json": quality.to_quality_json(),
        "warnings": raw_json.get("warnings") or [],
        "engine_status": engine_status,
        "valid": expected_sot is not None,
    }


def build_v21_prediction_for_fixture(
    db: Session,
    *,
    competition_id: int,
    fixture_id: int,
) -> dict[str, Any]:
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {"status": "error", "message": "fixture_not_found", "fixture_id": int(fixture_id)}
    if fx.competition_id is not None and int(fx.competition_id) != int(competition_id):
        return {
            "status": "error",
            "message": "guardrail_competition_id",
            "fixture_id": int(fixture_id),
            "competition_id": int(competition_id),
        }

    try:
        validate_v21_manifest(V21_MANIFEST_DEFINITIONS)
    except ValueError as exc:
        return {
            "status": "error",
            "message": "manifest_invalid",
            "details": str(exc),
            "fixture_id": int(fixture_id),
        }

    manifest_macros = V21_MANIFEST_DEFINITIONS
    sides: list[dict[str, Any]] = []
    warnings: list[str] = []

    for team_id, opp_id, side in (
        (int(fx.home_team_id), int(fx.away_team_id), "home"),
        (int(fx.away_team_id), int(fx.home_team_id), "away"),
    ):
        ctx = build_v21_side_context(
            db,
            fx,
            team_id=team_id,
            opponent_id=opp_id,
            competition_id=int(competition_id),
        )
        side_result = build_v21_side_prediction(db, ctx, side=side, manifest_macros=manifest_macros)
        sides.append(side_result)
        warnings.extend(side_result.get("warnings") or [])

    home = next((s for s in sides if s["side"] == "home"), None)
    away = next((s for s in sides if s["side"] == "away"), None)
    home_sot = home.get("predicted_sot") if home else None
    away_sot = away.get("predicted_sot") if away else None
    total = None
    if home_sot is not None and away_sot is not None:
        total = round(float(home_sot) + float(away_sot), 4)

    overall_status = "ok"
    if not all(s.get("valid") for s in sides):
        overall_status = "partial"

    return {
        "status": overall_status,
        "competition_id": int(competition_id),
        "fixture_id": int(fixture_id),
        "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        "home_predicted_sot": home_sot,
        "away_predicted_sot": away_sot,
        "total_predicted_sot": total,
        "sides": sides,
        "warnings": warnings,
    }
