"""Adapter v2.0 per Round Analysis — v1.1 base + lineup impact."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models import Fixture
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.backtest.round_analysis_model_picks import apply_v11_style_picks
from app.services.backtest.round_analysis_model_registry import RoundAnalysisModelResult
from app.services.backtest.round_analysis_preflight import REASON_INSUFFICIENT_HISTORY
from app.services.backtest.round_analysis_v11_context import extract_v11_predictions
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig
from app.services.backtest.v20_round_analysis_preview import V20RoundAnalysisPreviewService

ENGINE_NAME = "V20RoundAnalysisPreviewService"

ERR_V11_BASE_FAILED = "V20_V11_BASE_FAILED"
ERR_REQUIRES_HOME_AWAY_BASE = "V20_REQUIRES_HOME_AWAY_BASE"
ERR_LINEUP_MISSING = "V20_LINEUP_DATA_MISSING"
ERR_PLAYER_LAYER = "V20_PLAYER_LAYER_MISSING"
ERR_INSUFFICIENT_PRIOR = "V20_INSUFFICIENT_PRIOR_MATCHES"
ERR_PREDICTION_INCOMPLETE = "V20_PREDICTION_INCOMPLETE"
ERR_ENGINE = "V20_ENGINE_ERROR"


class SotV20RoundAnalysisAdapter:
    model_version = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    model_engine_name = ENGINE_NAME
    label = MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT]

    def __init__(self) -> None:
        self._preview = V20RoundAnalysisPreviewService()

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
            raw = self._preview.build_fixture_model(
                db,
                fixture=fixture,
                competition_id=competition_id,
                data_quality=data_quality,
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

        meta = dict(raw.get("_meta") or {})
        home_prior = int(meta.get("home_prior_count") or 0)
        away_prior = int(meta.get("away_prior_count") or 0)
        min_prior = min(home_prior, away_prior)
        warnings = list(raw.get("warnings") or [])
        home_pred, away_pred, predicted = extract_v11_predictions(raw)
        dq = dict(raw.get("data_quality") or data_quality)

        v11_trace = dict(meta.get("v11_trace_summary") or meta.get("trace_summary") or {})
        trace: dict[str, Any] = {
            "v11_base_used": True,
            "home_prior_count": home_prior,
            "away_prior_count": away_prior,
            "base_predicted_total": predicted,
            "base_home": home_pred,
            "base_away": away_pred,
            "lineup_impact_status": meta.get("lineup_impact_status"),
            "sportapi_lineups_available": meta.get("sportapi_lineups_available"),
            "v11_trace": v11_trace,
        }

        if min_prior == 0:
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="no_prediction",
                error_code=ERR_INSUFFICIENT_PRIOR,
                error_message=(
                    f"Prior matches insufficienti per v2.0 (casa {home_prior}, trasferta {away_prior})."
                ),
                reason=REASON_INSUFFICIENT_HISTORY,
                data_quality=dq,
                trace_summary=trace,
                label=self.label,
            )

        base_home = raw.get("predicted_home_sot")
        base_away = raw.get("predicted_away_sot")
        if predicted is not None and (base_home is None or base_away is None):
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="no_prediction",
                error_code=ERR_REQUIRES_HOME_AWAY_BASE,
                error_message="v2.0 richiede base v1.1 con home e away; disponibile solo il totale.",
                reason=ERR_REQUIRES_HOME_AWAY_BASE,
                data_quality=dq,
                trace_summary=trace,
                label=self.label,
            )

        if "home_prediction_incomplete" in warnings or "away_prediction_incomplete" in warnings:
            trace["base_error_code"] = ERR_V11_BASE_FAILED
            if predicted is None:
                return RoundAnalysisModelResult(
                    model_version_requested=requested,
                    model_version_used=requested,
                    model_engine_name=self.model_engine_name,
                    status="no_prediction",
                    error_code=ERR_V11_BASE_FAILED,
                    error_message="Base v1.1 non disponibile per il calcolo v2.0.",
                    reason=ERR_V11_BASE_FAILED,
                    data_quality=dq,
                    trace_summary=trace,
                    label=self.label,
                )

        if "lineup_impact_fallback" in warnings or str(dq.get("lineup") or "") == "missing":
            if predicted is None:
                return RoundAnalysisModelResult(
                    model_version_requested=requested,
                    model_version_used=requested,
                    model_engine_name=self.model_engine_name,
                    status="no_prediction",
                    error_code=ERR_LINEUP_MISSING,
                    error_message="Dati lineup mancanti per lineup impact v2.0.",
                    reason=ERR_LINEUP_MISSING,
                    data_quality=dq,
                    trace_summary=trace,
                    label=self.label,
                )

        if predicted is None:
            if bool(meta.get("player_layer_neutral")) and "lineup_missing" in warnings:
                code = ERR_PLAYER_LAYER
                msg = "Player layer / lineup non disponibili per v2.0."
            else:
                code = ERR_PREDICTION_INCOMPLETE
                msg = "Impossibile calcolare il totale SOT v2.0 dopo lineup impact."
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="no_prediction",
                error_code=code,
                error_message=msg,
                reason=code,
                data_quality=dq,
                trace_summary=trace,
                label=self.label,
            )

        pred_patch, pick_fields = apply_v11_style_picks(
            predicted_total=float(predicted),
            home_prior=home_prior,
            away_prior=away_prior,
            warnings=warnings,
            sample_bucket=str(raw.get("sample_bucket") or "stable_sample"),
            player_layer_neutral=bool(meta.get("player_layer_neutral")),
            lines=lines,
            cautious_drop_threshold=cautious_drop_threshold,
            play_config=play_config,
            actual_total=actual_total,
        )

        prediction = {
            "predicted_home_sot": raw.get("predicted_home_sot"),
            "predicted_away_sot": raw.get("predicted_away_sot"),
            "predicted_total_sot": pred_patch.get("predicted_total_sot"),
            "sample_bucket": raw.get("sample_bucket"),
            "warnings": pred_patch.get("warnings"),
        }

        return RoundAnalysisModelResult(
            model_version_requested=requested,
            model_version_used=requested,
            model_engine_name=self.model_engine_name,
            status="ok",
            prediction=prediction,
            picks=pick_fields,
            data_quality=dq,
            trace_summary=trace,
            label=self.label,
        )
