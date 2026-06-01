"""Adapter v1.1 per Round Analysis — solo logica v1.1."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.backtest.round_analysis_model_picks import apply_v11_style_picks
from app.services.backtest.round_analysis_model_registry import RoundAnalysisModelResult
from app.services.backtest.round_analysis_preflight import REASON_INSUFFICIENT_HISTORY
from app.services.backtest.round_analysis_v11_context import (
    extract_v11_predictions,
    infer_v11_failure_code,
)
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig
from app.services.backtest.v11_round_analysis_preview import V11RoundAnalysisPreviewService

ENGINE_NAME = "V11RoundAnalysisPreviewService"


def _trace_side_to_result(side: dict[str, Any]) -> Any:
    """Costruisce un oggetto minimo per infer_v11_failure_code da trace."""
    from types import SimpleNamespace

    return SimpleNamespace(
        valid=bool(side.get("valid")),
        expected_sot=side.get("expected_sot"),
        formula_quality_status=side.get("formula_quality_status"),
        raw_json={"components": {}},
    )

ERR_PRIOR_CONTEXT_EMPTY = "V11_PRIOR_CONTEXT_EMPTY"
ERR_INSUFFICIENT_PRIOR = "V11_INSUFFICIENT_PRIOR_MATCHES"
ERR_PREDICTION_INCOMPLETE = "V11_PREDICTION_INCOMPLETE"
ERR_MISSING_TOTAL_SOT = "V11_MISSING_TOTAL_SOT"
ERR_LEAGUE_BASELINE_EMPTY = "V11_LEAGUE_BASELINE_EMPTY"
ERR_MISSING_TEAM_STATS = "V11_MISSING_TEAM_STATS"
ERR_ENGINE = "V11_ENGINE_ERROR"


class SotV11RoundAnalysisAdapter:
    model_version = BASELINE_SOT_MODEL_VERSION_V11_SOT
    model_engine_name = ENGINE_NAME
    label = MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V11_SOT]

    def __init__(self) -> None:
        self._preview = V11RoundAnalysisPreviewService()

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
        dq = dict(raw.get("data_quality") or data_quality)

        home_pred, away_pred, predicted = extract_v11_predictions(raw)
        trace: dict[str, Any] = dict(meta.get("trace_summary") or {})
        trace.setdefault("home_prior_count", home_prior)
        trace.setdefault("away_prior_count", away_prior)

        if min_prior == 0:
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="no_prediction",
                error_code=ERR_PRIOR_CONTEXT_EMPTY,
                error_message=(
                    f"Storico non recuperato per v1.1 (casa {home_prior}, trasferta {away_prior})."
                ),
                reason=REASON_INSUFFICIENT_HISTORY,
                data_quality=dq,
                trace_summary=trace,
                label=self.label,
            )

        if predicted is not None:
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
                "predicted_home_sot": home_pred,
                "predicted_away_sot": away_pred,
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

        league_eligible = int(meta.get("league_baseline_eligible_fixtures") or 0)
        if league_eligible == 0:
            fq = meta.get("formula_quality_status") or trace.get("home_side", {}).get(
                "formula_quality_status",
            )
            return RoundAnalysisModelResult(
                model_version_requested=requested,
                model_version_used=requested,
                model_engine_name=self.model_engine_name,
                status="no_prediction",
                error_code=ERR_LEAGUE_BASELINE_EMPTY,
                error_message=(
                    f"Baseline lega v1.1 senza fixture eligible (season_id={meta.get('season_id_used')}, "
                    f"formula_quality={fq})."
                ),
                reason=ERR_LEAGUE_BASELINE_EMPTY,
                data_quality=dq,
                trace_summary=trace,
                label=self.label,
            )

        inferred = meta.get("inferred_error_code") or trace.get("inferred_error_code")
        if inferred is None:
            home_side = trace.get("formula_outputs", {}).get("home") or trace.get("home_side") or {}
            away_side = trace.get("formula_outputs", {}).get("away") or trace.get("away_side") or {}
            inferred = infer_v11_failure_code(
                _trace_side_to_result(home_side),
                _trace_side_to_result(away_side),
                None,
                league_baseline_eligible=league_eligible,
            )

        if str(dq.get("team_stats") or "").lower() in ("missing", "partial"):
            code = ERR_MISSING_TEAM_STATS
            msg = "Team stats mancanti per il calcolo v1.1."
        elif inferred:
            code = str(inferred)
            hs = trace.get("home_side") or {}
            aws = trace.get("away_side") or {}
            fo = trace.get("formula_outputs") or {}
            failed = (fo.get("home") or {}).get("failed_components", []) + (
                fo.get("away") or {}
            ).get("failed_components", [])
            msg = (
                f"v1.1 non calcolabile ({code}): "
                f"home={hs.get('formula_quality_status')}, away={aws.get('formula_quality_status')}"
                + (f"; componenti={','.join(failed)}" if failed else ".")
            )
        else:
            code = ERR_MISSING_TOTAL_SOT
            msg = "Predizione totale mancante per v1.1."

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
