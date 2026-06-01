"""Adapter v2.1 per Round Analysis — PIT weighted components."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.models import Fixture
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.schemas.backtest_sot_v21_preview import SotV21PreviewResponse
from app.services.backtest.round_analysis_model_picks import apply_v21_picks
from app.services.backtest.round_analysis_model_registry import RoundAnalysisModelResult
from app.services.backtest.round_analysis_preflight import REASON_INSUFFICIENT_HISTORY, insufficient_history_message
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig
from app.services.backtest.sot_v21_preview_service import SotV21PointInTimePreviewService

ENGINE_NAME = "SotV21PointInTimePreviewService"

ERR_INSUFFICIENT_PRIOR = "V21_INSUFFICIENT_PRIOR_MATCHES"
ERR_PREDICTION_INCOMPLETE = "V21_PREDICTION_INCOMPLETE"
ERR_ENGINE = "V21_ENGINE_ERROR"


def _v21_explanation(preview: SotV21PreviewResponse) -> dict[str, Any]:
    def _macro_detail(side: str) -> dict[str, Any]:
        trace = preview.home_trace if side == "home" else preview.away_trace
        out: dict[str, Any] = {
            "macros": [],
            "base_anchor_sot": trace.base_anchor_sot,
            "weighted_macro_multiplier": trace.weighted_macro_multiplier,
            "expected_sot_v21": trace.expected_sot_v21_pit,
        }
        for macro in trace.macros:
            entry: dict[str, Any] = {
                "key": macro.key,
                "status": macro.status,
                "macro_index": macro.macro_index,
            }
            if macro.key == "injuries_unavailable":
                details = macro.details or {}
                entry["unavailable_macro_detail"] = details.get("unavailable_macro_detail")
            out["macros"].append(entry)
        return out

    return {
        "home": _macro_detail("home"),
        "away": _macro_detail("away"),
        "leakage_guard": preview.leakage_guard,
        "actuals_used_as_input": preview.actuals_used_as_input,
        "warnings": list(preview.warnings or []),
        "fallback_count": len(preview.fallback_variables or []),
        "fallback_variables": list(preview.fallback_variables or []),
        "source_fixture_id_lineup_home": preview.source_fixture_id_lineup_home,
        "source_fixture_id_lineup_away": preview.source_fixture_id_lineup_away,
        "source_fixture_id_unavailable_home": preview.source_fixture_id_unavailable_home,
        "source_fixture_id_unavailable_away": preview.source_fixture_id_unavailable_away,
    }


class SotV21RoundAnalysisAdapter:
    model_version = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    model_engine_name = ENGINE_NAME
    label = MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS]

    def __init__(self) -> None:
        self._preview = SotV21PointInTimePreviewService()

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
        try:
            preview = self._preview.build_preview(
                db,
                competition_id=competition_id,
                fixture_id=int(fixture.id),
                mode=mode or BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
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
            )

        home_prior = int(preview.home_prior_matches_count)
        away_prior = int(preview.away_prior_matches_count)
        min_prior = min(home_prior, away_prior)
        total_raw = preview.prediction.total_predicted_sot
        expl = _v21_explanation(preview)
        trace: dict[str, Any] = {
            "home_prior_matches": home_prior,
            "away_prior_matches": away_prior,
            "pit_mode": mode or BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
        }

        if min_prior == 0:
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="no_prediction",
                error_code=ERR_INSUFFICIENT_PRIOR,
                error_message=insufficient_history_message(min_prior, prior_home=home_prior, prior_away=away_prior),
                reason=REASON_INSUFFICIENT_HISTORY,
                data_quality=dict(data_quality),
                trace_summary=trace,
                explanation=expl,
                label=self.label,
            )

        if total_raw is None:
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="no_prediction",
                error_code=ERR_PREDICTION_INCOMPLETE,
                error_message="Preview v2.1 senza totale SOT predetto.",
                reason=ERR_PREDICTION_INCOMPLETE,
                data_quality=dict(data_quality),
                trace_summary=trace,
                explanation=expl,
                label=self.label,
            )

        predicted = float(total_raw)
        pred_patch, pick_fields = apply_v21_picks(
            preview=preview,
            predicted_total=predicted,
            lines=lines,
            cautious_drop_threshold=cautious_drop_threshold,
            play_config=play_config,
            actual_total=actual_total,
        )

        prediction = {
            "predicted_home_sot": preview.prediction.home_predicted_sot,
            "predicted_away_sot": preview.prediction.away_predicted_sot,
            "predicted_total_sot": pred_patch.get("predicted_total_sot"),
            "sample_bucket": pred_patch.get("sample_bucket"),
            "warnings": pred_patch.get("warnings"),
        }

        return RoundAnalysisModelResult(
            model_version_requested=requested,
            model_version_used=requested,
            model_engine_name=self.model_engine_name,
            status="ok",
            prediction=prediction,
            picks=pick_fields,
            data_quality=dict(data_quality),
            trace_summary=trace,
            explanation=expl,
            label=self.label,
        )
