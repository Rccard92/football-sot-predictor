"""Registry v2.1 — riga sintetica model-status quando assente dal DB."""

from __future__ import annotations

from typing import Any

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.services.model_applied_variable_manifest import v21_manifest_error, v21_manifest_valid
from app.services.predictions_v21.baseline_v2_1_weighted_components_service import (
    SotPredictionV21WeightedComponentsService,
)
from app.services.sot_model_registry import get_model_display


def synthetic_v21_model_status_row() -> dict[str, Any]:
    display = get_model_display(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
    if not v21_manifest_valid():
        return {
            "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "predictions_total": 0,
            "upcoming_predictions": 0,
            "avg_expected_sot": None,
            "min_expected_sot": None,
            "max_expected_sot": None,
            "generated_at": None,
            "is_available_for_upcoming": False,
            "engine_status": "manifest_invalid",
            "manifest_error": v21_manifest_error(),
            "is_experimental": True,
            "model_label": display.label if display else BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "registry_status": display.registry_status if display else "experimental",
        }
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        "predictions_total": 0,
        "upcoming_predictions": 0,
        "avg_expected_sot": None,
        "min_expected_sot": None,
        "max_expected_sot": None,
        "generated_at": None,
        "is_available_for_upcoming": False,
        "engine_status": SotPredictionV21WeightedComponentsService.engine_status,
        "is_experimental": True,
        "model_label": display.label if display else BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        "registry_status": display.registry_status if display else "experimental",
    }


def ensure_v21_in_available_list(available_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inietta v2.1 in coda se non presente in DB."""
    if any(
        str(r.get("model_version")) == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
        for r in available_list
    ):
        return available_list
    return list(available_list) + [synthetic_v21_model_status_row()]
