"""Runner modelli per analisi giornata (Step I) — registry adapter isolati."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Fixture
from app.services.backtest.round_analysis_model_registry import (
    ERROR_MODEL_ERROR,
    RoundAnalysisModelResult,
    get_round_analysis_adapter,
    log_model_run,
    model_result_to_block,
)
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig


class RoundAnalysisModelRunner:
    def run_for_fixture(
        self,
        db: Session,
        *,
        fixture: Fixture,
        competition_id: int,
        mode: str,
        models: list[str],
        lines: list[float],
        cautious_drop_threshold: float,
        play_config: PlayAdviceConfig,
        data_quality: dict[str, str],
        actual_total: int | None,
        analysis_id: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        models_json: dict[str, Any] = {}
        explanation_json: dict[str, Any] = {}

        for model_key in models:
            result: RoundAnalysisModelResult
            try:
                adapter = get_round_analysis_adapter(model_key)
                result = adapter.predict_fixture(
                    db,
                    fixture=fixture,
                    competition_id=competition_id,
                    mode=mode,
                    lines=lines,
                    cautious_drop_threshold=cautious_drop_threshold,
                    play_config=play_config,
                    data_quality=data_quality,
                    actual_total=actual_total,
                )
            except ValueError:
                continue
            except Exception as exc:  # noqa: BLE001
                result = RoundAnalysisModelResult(
                    model_version_requested=model_key,
                    model_version_used=model_key,
                    model_engine_name="unknown",
                    status="error",
                    error_code=ERROR_MODEL_ERROR,
                    error_message=str(exc)[:300],
                    data_quality=dict(data_quality),
                )

            log_model_run(
                analysis_id=analysis_id,
                fixture_id=int(fixture.id),
                result=result,
            )
            block = model_result_to_block(result)
            models_json[model_key] = block
            if result.explanation:
                explanation_json[model_key] = result.explanation

        return models_json, explanation_json
