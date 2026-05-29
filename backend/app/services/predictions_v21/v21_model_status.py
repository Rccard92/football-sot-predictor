"""Registry v2.1 — riga sintetica model-status quando assente dal DB."""

from __future__ import annotations

from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.model_applied_variable_manifest import v21_manifest_error, v21_manifest_valid
from app.services.predictions_v21.baseline_v2_1_weighted_components_service import (
    SotPredictionV21WeightedComponentsService,
)
from app.services.sot_model_registry import get_model_display, user_visible_model_versions


def synthetic_v21_model_status_row() -> dict[str, Any]:
    display = get_model_display(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
    if not v21_manifest_valid():
        return {
            "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "predictions_total": 0,
            "predictions_count": 0,
            "upcoming_predictions": 0,
            "next_round_predictions_count": 0,
            "avg_expected_sot": None,
            "min_expected_sot": None,
            "max_expected_sot": None,
            "generated_at": None,
            "last_generated_at": None,
            "is_available_for_upcoming": False,
            "engine_status": "manifest_invalid",
            "manifest_error": v21_manifest_error(),
            "is_experimental": True,
            "model_label": display.label if display else BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "label": display.label if display else BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "registry_status": display.registry_status if display else "experimental",
            "status": "missing",
            "readiness": "missing",
        }
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        "predictions_total": 0,
        "predictions_count": 0,
        "upcoming_predictions": 0,
        "next_round_predictions_count": 0,
        "avg_expected_sot": None,
        "min_expected_sot": None,
        "max_expected_sot": None,
        "generated_at": None,
        "last_generated_at": None,
        "is_available_for_upcoming": True,
        "engine_status": SotPredictionV21WeightedComponentsService.engine_status,
        "is_experimental": True,
        "model_label": display.label if display else BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        "label": display.label if display else BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        "registry_status": display.registry_status if display else "experimental",
        "status": "missing",
        "readiness": "missing",
    }


def synthetic_v20_model_status_row() -> dict[str, Any]:
    display = get_model_display(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    label = display.label if display else BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        "predictions_total": 0,
        "predictions_count": 0,
        "upcoming_predictions": 0,
        "next_round_predictions_count": 0,
        "generated_at": None,
        "last_generated_at": None,
        "is_available_for_upcoming": False,
        "model_label": label,
        "label": label,
        "registry_status": display.registry_status if display else "stable",
        "status": "missing",
        "readiness": "missing",
    }


def _synthetic_row_for_version(model_version: str) -> dict[str, Any] | None:
    if model_version == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS:
        return synthetic_v21_model_status_row()
    if model_version == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT:
        return synthetic_v20_model_status_row()
    return None


def ensure_user_visible_models_in_list(available_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Garantisce v2.0 e v2.1 in available_models, anche senza righe DB."""
    by_mv = {str(r.get("model_version")): r for r in available_list}
    out: list[dict[str, Any]] = []
    for mv in user_visible_model_versions():
        if mv in by_mv:
            out.append(by_mv[mv])
            continue
        synthetic = _synthetic_row_for_version(mv)
        if synthetic is not None:
            out.append(synthetic)
    return out


def ensure_v21_in_available_list(available_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inietta v2.1 in coda se non presente in DB."""
    return ensure_user_visible_models_in_list(available_list)
