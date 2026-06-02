"""Adapter v3.0 per Round Analysis — value selector basato su v1.1 + v2.1."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR,
)
from app.models import Fixture
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.backtest.round_analysis_model_registry import RoundAnalysisModelResult
from app.services.backtest.sot_pick_evaluation_logic import compute_pick_outcome
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig
from app.services.backtest.sot_v30_value_selector_service import SotV30ValueSelectorService

ENGINE_NAME = "SotV30ValueSelectorService"

ERR_DEPENDENCY_MISSING = "V30_DEPENDENCY_MISSING"
ERR_ENGINE = "V30_ENGINE_ERROR"


class SotV30ValueSelectorRoundAnalysisAdapter:
    model_version = BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR
    model_engine_name = ENGINE_NAME
    label = MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR]

    def __init__(self) -> None:
        self._svc = SotV30ValueSelectorService()

    def predict_fixture(
        self,
        db: Session,
        *,
        fixture: Fixture,
        competition_id: int,
        mode: str,
        lines: list[float],
        cautious_drop_threshold: float,
        play_config: PlayAdviceConfig,
        data_quality: dict[str, str],
        actual_total: int | None,
    ) -> RoundAnalysisModelResult:
        requested = self.model_version

        # Nota importante: per evitare ricalcoli inutili, v3.0 NON calcola automaticamente v1.1/v2.1.
        # Il runner deve passare v1.1/v2.1 già presenti (DB o in-memory) tramite resolver dedicato.
        return RoundAnalysisModelResult(
            model_version_requested=requested,
            model_version_used=requested,
            model_engine_name=self.model_engine_name,
            status="no_prediction",
            error_code=ERR_DEPENDENCY_MISSING,
            error_message="v3.0 richiede v1.1 e v2.1 già calcolate per questa giornata.",
            reason=ERR_DEPENDENCY_MISSING,
            data_quality=dict(data_quality),
            trace_summary={"missing": [BASELINE_SOT_MODEL_VERSION_V11_SOT, BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS]},
            label=self.label,
        )

