"""Scaffold v3.1 SOT Calibrated Predictor — predittore indipendente pre-match (Step V3.1-A)."""

from __future__ import annotations

from typing import Any

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V31_CALIBRATED_PREDICTOR

V31_NOT_IMPLEMENTED = "V31_PREDICTOR_NOT_IMPLEMENTED"


class SotV31CalibratedPredictorService:
    """
    Predittore SOT v3.1 basato su feature grezze/calibrate pre-match.

    Step V3.1-A: solo scaffold. La formula di calibrazione arriverà in uno step successivo.
    """

    model_key = BASELINE_SOT_MODEL_VERSION_V31_CALIBRATED_PREDICTOR
    model_label = "v3.1 SOT Calibrated Predictor"
    stage = "experimental"
    description = (
        "Nuovo predittore indipendente SOT basato su feature pre-match grezze/calibrate. "
        "Non usa le predizioni finali dei modelli precedenti come input."
    )

    def predict_fixture(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "v3.1 calibrated predictor non è ancora implementato; usare il dataset di calibrazione.",
        )
