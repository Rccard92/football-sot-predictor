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
        initial_models_json: dict[str, Any] | None = None,
        initial_explanation_json: dict[str, Any] | None = None,
        analysis_id: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        models_json: dict[str, Any] = dict(initial_models_json or {})
        explanation_json: dict[str, Any] = dict(initial_explanation_json or {})

        for model_key in models:
            if model_key == "baseline_v3_0_sot_value_selector":
                from app.services.backtest.round_analysis_v30_dependencies import resolve_v30_dependencies
                from app.services.backtest.sot_v30_value_selector_service import SotV30ValueSelectorService
                from app.services.backtest.sot_pick_evaluation_logic import compute_pick_outcome

                deps = resolve_v30_dependencies(models_json=models_json, explanation_json=explanation_json)
                if deps.status == "ok":
                    payload, trace_summary = SotV30ValueSelectorService().build_selection(
                        db,
                        fixture=fixture,
                        competition_id=competition_id,
                        mode=mode,
                        cutoff_time=None,
                        v11_block=deps.v11_block,
                        v21_block=deps.v21_block,
                        explanation_v21=deps.explanation_v21,
                        data_quality=data_quality,
                    )
                    selection = (payload.get("selection") or {}) if isinstance(payload, dict) else {}
                    decision = str(selection.get("decision") or "NO_BET")
                    line = selection.get("line")
                    reason_codes = list(selection.get("reason_codes") or [])
                    no_bet_reasons = list(selection.get("no_bet_reasons") or [])
                    cautious_reason = ",".join((reason_codes or no_bet_reasons)[:3])

                    cautious_outcome = None
                    if line is not None and actual_total is not None:
                        out = compute_pick_outcome(float(line), int(actual_total))
                        cautious_outcome = "WIN" if out == "win" else "LOSS"

                    result = RoundAnalysisModelResult(
                        model_version_requested=model_key,
                        model_version_used=model_key,
                        model_engine_name="SotV30ValueSelectorService",
                        status="ok",
                        prediction={
                            "predicted_home_sot": None,
                            "predicted_away_sot": None,
                            "predicted_total_sot": (deps.v21_block or {}).get("predicted_total_sot"),
                            "sample_bucket": (deps.v21_block or {}).get("sample_bucket"),
                            "warnings": list((deps.v21_block or {}).get("warnings") or []),
                        },
                        picks={
                            "aggressive_line": None,
                            "aggressive_edge": None,
                            "aggressive_outcome": None,
                            "aggressive_advice": None,
                            "aggressive_reason": None,
                            "cautious_line": line,
                            "cautious_edge": None,
                            "cautious_outcome": cautious_outcome,
                            "cautious_advice": decision,
                            "cautious_reason": cautious_reason,
                            "confidence": (deps.v21_block or {}).get("confidence"),
                        },
                        data_quality=dict(data_quality),
                        trace_summary=trace_summary,
                        explanation={
                            "reference_v1_1": deps.v11_block,
                            "reference_v2_1": deps.v21_block,
                            "reference_explanation_v2_1": deps.explanation_v21,
                        },
                    )
                    log_model_run(analysis_id=analysis_id, fixture_id=int(fixture.id), result=result)
                    models_json[model_key] = model_result_to_block(result)
                    if result.explanation:
                        explanation_json[model_key] = result.explanation
                    continue

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
