"""Resolver dipendenze v3.0 da risultati già calcolati (DB o in-memory)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_preflight import model_block_is_error, model_block_is_no_prediction


@dataclass(frozen=True)
class V30Dependencies:
    status: str  # "ok" | "missing_dependencies"
    missing_dependencies: list[str]
    v11_block: dict[str, Any] | None = None
    v21_block: dict[str, Any] | None = None
    explanation_v21: dict[str, Any] | None = None


def resolve_v30_dependencies(
    *,
    models_json: dict[str, Any] | None,
    explanation_json: dict[str, Any] | None,
) -> V30Dependencies:
    """Estrae v1.1 e v2.1 già salvate per calcolare v3.0 senza ricalcoli."""
    models_json = dict(models_json or {})
    explanation_json = dict(explanation_json or {})

    missing: list[str] = []

    v11 = models_json.get(BASELINE_SOT_MODEL_VERSION_V11_SOT)
    if not isinstance(v11, dict) or model_block_is_error(v11) or model_block_is_no_prediction(v11):
        missing.append(BASELINE_SOT_MODEL_VERSION_V11_SOT)

    v21 = models_json.get(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
    if not isinstance(v21, dict) or model_block_is_error(v21) or model_block_is_no_prediction(v21):
        missing.append(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)

    explanation_v21 = explanation_json.get(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
    if BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS not in missing and not isinstance(explanation_v21, dict):
        # Non è una dipendenza "modello" mancante, ma senza macro snapshot perdiamo contesto.
        # La trattiamo come dipendenza mancante della v2.1 (input incompleto).
        missing.append(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
        explanation_v21 = None

    if missing:
        # Normalizza unici
        uniq: list[str] = []
        for k in missing:
            if k not in uniq:
                uniq.append(k)
        return V30Dependencies(status="missing_dependencies", missing_dependencies=uniq)

    v11_block = {
        "predicted_total_sot": v11.get("predicted_total_sot"),
        "cautious_advice": v11.get("cautious_advice"),
        "cautious_line": v11.get("cautious_line"),
    }
    v21_block = {
        "predicted_total_sot": v21.get("predicted_total_sot"),
        "cautious_advice": v21.get("cautious_advice"),
        "cautious_line": v21.get("cautious_line"),
        "warnings": list(v21.get("warnings") or []),
        "confidence": v21.get("confidence"),
        "sample_bucket": v21.get("sample_bucket"),
        "data_quality": dict(v21.get("data_quality") or {}),
    }

    return V30Dependencies(
        status="ok",
        missing_dependencies=[],
        v11_block=v11_block,
        v21_block=v21_block,
        explanation_v21=dict(explanation_v21),
    )

