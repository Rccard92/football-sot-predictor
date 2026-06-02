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

        # Il v3.0 dipende dagli output v1.1 e v2.1 già calcolati per la fixture.
        # In Round Analysis gli adapter sono eseguiti in sequenza ma non si passano risultati tra loro,
        # quindi qui usiamo una strategia robusta: riusare i motori pre-match v1.1/v2.1 via i rispettivi adapter.
        from app.services.backtest.adapters.sot_v11_round_analysis_adapter import SotV11RoundAnalysisAdapter
        from app.services.backtest.adapters.sot_v21_round_analysis_adapter import SotV21RoundAnalysisAdapter

        try:
            v11_res = SotV11RoundAnalysisAdapter().predict_fixture(
                db,
                fixture=fixture,
                competition_id=competition_id,
                mode=mode,
                lines=lines,
                cautious_drop_threshold=cautious_drop_threshold,
                play_config=play_config,
                data_quality=data_quality,
                actual_total=None,  # anti-leakage: mai usare actuals in input
            )
            v21_res = SotV21RoundAnalysisAdapter().predict_fixture(
                db,
                fixture=fixture,
                competition_id=competition_id,
                mode=mode,
                lines=lines,
                cautious_drop_threshold=cautious_drop_threshold,
                play_config=play_config,
                data_quality=data_quality,
                actual_total=None,  # anti-leakage
            )
        except Exception as exc:  # noqa: BLE001
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="error",
                error_code=ERR_ENGINE,
                error_message=str(exc)[:300],
                data_quality=dict(data_quality),
                label=self.label,
            )

        v11_block = {}
        if v11_res.status == "ok":
            v11_block = {
                "predicted_total_sot": (v11_res.prediction or {}).get("predicted_total_sot"),
                "cautious_advice": (v11_res.picks or {}).get("cautious_advice"),
                "cautious_line": (v11_res.picks or {}).get("cautious_line"),
            }

        v21_block = {}
        explanation_v21 = v21_res.explanation if v21_res.status == "ok" else None
        if v21_res.status == "ok":
            v21_block = {
                "predicted_total_sot": (v21_res.prediction or {}).get("predicted_total_sot"),
                "cautious_advice": (v21_res.picks or {}).get("cautious_advice"),
                "cautious_line": (v21_res.picks or {}).get("cautious_line"),
                "warnings": list((v21_res.prediction or {}).get("warnings") or []),
                "confidence": (v21_res.picks or {}).get("confidence"),
                "sample_bucket": (v21_res.prediction or {}).get("sample_bucket"),
            }

        if not v21_block:
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="no_prediction",
                error_code=ERR_DEPENDENCY_MISSING,
                error_message="Dipendenza v2.1 non disponibile per value selector v3.0.",
                reason=ERR_DEPENDENCY_MISSING,
                data_quality=dict(data_quality),
                trace_summary={"missing": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS},
                label=self.label,
            )

        payload, trace_summary = self._svc.build_selection(
            db,
            fixture=fixture,
            competition_id=competition_id,
            mode=mode,
            cutoff_time=None,
            v11_block=v11_block,
            v21_block=v21_block,
            explanation_v21=explanation_v21,
            data_quality=data_quality,
        )

        # Mappiamo dentro RoundAnalysisModelResult in modo compatibile con models_json:
        # - predicted_total_sot = reference v2.1
        # - picks: popoliamo campi "cautious_*" per rendering/accordion
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
        picks = {
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
            "confidence": (v21_block or {}).get("confidence"),
        }

        return RoundAnalysisModelResult(
            model_version_requested=requested,
            model_version_used=requested,
            model_engine_name=self.model_engine_name,
            status="ok",
            prediction={
                "predicted_home_sot": None,
                "predicted_away_sot": None,
                "predicted_total_sot": (v21_block or {}).get("predicted_total_sot"),
                "sample_bucket": (v21_block or {}).get("sample_bucket"),
                "warnings": list((v21_block or {}).get("warnings") or []),
            },
            picks=picks,
            data_quality=dict(data_quality),
            trace_summary=trace_summary,
            explanation={
                "reference_v1_1": v11_block,
                "reference_v2_1": v21_block,
                "reference_explanation_v2_1": explanation_v21,
            },
            label=self.label,
        )

