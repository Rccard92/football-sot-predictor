"""Registry adapter modelli Round Analysis (isolamento v1.1 / v2.0 / v2.1)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR,
)
from app.models import Fixture
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.backtest.round_analysis_preflight import build_no_prediction_block, build_error_block
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig

logger = logging.getLogger(__name__)

ModelRunStatus = Literal["ok", "no_prediction", "error"]

ERROR_MODEL_VERSION_MISMATCH = "MODEL_VERSION_MISMATCH"
ERROR_MODEL_ERROR = "MODEL_ERROR"


@dataclass
class RoundAnalysisModelResult:
    model_version_requested: str
    model_version_used: str
    model_engine_name: str
    status: ModelRunStatus
    error_code: str | None = None
    error_message: str | None = None
    reason: str | None = None
    prediction: dict[str, Any] | None = None
    picks: dict[str, Any] | None = None
    data_quality: dict[str, str] = field(default_factory=dict)
    trace_summary: dict[str, Any] | None = None
    explanation: dict[str, Any] | None = None
    label: str | None = None


class RoundAnalysisModelAdapter(Protocol):
    model_version: str
    model_engine_name: str
    label: str

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
    ) -> RoundAnalysisModelResult: ...


def get_round_analysis_adapter(model_key: str) -> RoundAnalysisModelAdapter:
    from app.services.backtest.adapters.sot_v11_round_analysis_adapter import SotV11RoundAnalysisAdapter
    from app.services.backtest.adapters.sot_v20_round_analysis_adapter import SotV20RoundAnalysisAdapter
    from app.services.backtest.adapters.sot_v21_round_analysis_adapter import SotV21RoundAnalysisAdapter
    from app.services.backtest.adapters.sot_v30_value_selector_round_analysis_adapter import (
        SotV30ValueSelectorRoundAnalysisAdapter,
    )

    registry: dict[str, type[RoundAnalysisModelAdapter]] = {
        BASELINE_SOT_MODEL_VERSION_V11_SOT: SotV11RoundAnalysisAdapter,
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: SotV20RoundAnalysisAdapter,
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: SotV21RoundAnalysisAdapter,
        BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR: SotV30ValueSelectorRoundAnalysisAdapter,
    }
    cls = registry.get(model_key)
    if cls is None:
        raise ValueError(f"unsupported_round_analysis_model:{model_key}")
    return cls()


ROUND_ANALYSIS_MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    BASELINE_SOT_MODEL_VERSION_V11_SOT: {
        "label": MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V11_SOT],
        "engine": "V11RoundAnalysisPreviewService",
        "market_key": "shots_on_target",
    },
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: {
        "label": MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT],
        "engine": "V20RoundAnalysisPreviewService",
        "market_key": "shots_on_target",
    },
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: {
        "label": MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS],
        "engine": "SotV21PointInTimePreviewService",
        "market_key": "shots_on_target",
    },
    BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR: {
        "label": MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR],
        "engine": "SotV30ValueSelectorService",
        "market_key": "shots_on_target",
    },
}


def _identity_fields(result: RoundAnalysisModelResult) -> dict[str, Any]:
    return {
        "model_version": result.model_version_used,
        "model_version_requested": result.model_version_requested,
        "model_version_used": result.model_version_used,
        "model_engine_name": result.model_engine_name,
        "model_status": result.status,
        "label": result.label or MODEL_LABELS.get(result.model_version_used, result.model_version_used),
    }


def model_result_to_block(result: RoundAnalysisModelResult) -> dict[str, Any]:
    """Converte RoundAnalysisModelResult nel blocco JSON persistito."""
    requested = result.model_version_requested
    used = result.model_version_used

    if used != requested:
        return build_error_block(
            requested,
            error_code=ERROR_MODEL_VERSION_MISMATCH,
            error_message="Il motore ha restituito un modello diverso da quello richiesto.",
            model_version_requested=requested,
            model_version_used=used,
            model_engine_name=result.model_engine_name,
            data_quality=result.data_quality,
        )

    if result.status == "error":
        return build_error_block(
            requested,
            error_code=result.error_code or ERROR_MODEL_ERROR,
            error_message=result.error_message or "Errore motore modello.",
            model_version_requested=requested,
            model_version_used=used,
            model_engine_name=result.model_engine_name,
            data_quality=result.data_quality,
            trace_summary=result.trace_summary,
        )

    if result.status == "no_prediction":
        block = build_no_prediction_block(
            requested,
            reason=result.reason or result.error_code or "NO_PREDICTION",
            message=result.error_message,
            data_quality=result.data_quality,
            error_code=result.error_code,
            model_version_requested=requested,
            model_version_used=used,
            model_engine_name=result.model_engine_name,
            trace_summary=result.trace_summary,
        )
        return block

    pred = result.prediction or {}
    block: dict[str, Any] = {
        **_identity_fields(result),
        "status": "ok",
        "error_code": None,
        "error_message": None,
        "predicted_home_sot": pred.get("predicted_home_sot"),
        "predicted_away_sot": pred.get("predicted_away_sot"),
        "predicted_total_sot": pred.get("predicted_total_sot"),
        "sample_bucket": pred.get("sample_bucket"),
        "warnings": list(pred.get("warnings") or []),
        "data_quality": dict(result.data_quality),
        "trace_summary": result.trace_summary,
    }
    if result.picks:
        block.update(result.picks)
    return block


def log_model_run(
    *,
    analysis_id: int | None,
    fixture_id: int,
    result: RoundAnalysisModelResult,
) -> None:
    logger.info(
        "ROUND_ANALYSIS_MODEL_RUN analysis_id=%s fixture_id=%s "
        "model_version_requested=%s model_version_used=%s model_engine_name=%s "
        "status=%s error_code=%s",
        analysis_id,
        fixture_id,
        result.model_version_requested,
        result.model_version_used,
        result.model_engine_name,
        result.status,
        result.error_code,
    )
