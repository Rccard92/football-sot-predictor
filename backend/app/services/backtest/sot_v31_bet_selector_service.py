"""Scaffold v3.1 Bet Selector — step successivo a V3.1-A."""

from __future__ import annotations

from typing import Any

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V31_CALIBRATED_PREDICTOR

V31_LINES = [5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5]


class SotV31BetSelectorService:
    """Valuta linee e decisione GIOCA/NO_BET/BORDERLINE sulla prediction v3.1 (non in V3.1-A)."""

    model_key = BASELINE_SOT_MODEL_VERSION_V31_CALIBRATED_PREDICTOR
    supported_lines = V31_LINES

    def select_bet(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("v3.1 bet selector non è ancora implementato.")
