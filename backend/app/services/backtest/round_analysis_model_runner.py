"""Runner modelli per analisi giornata (Step I)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.models import Fixture
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.schemas.backtest_sot_v21_preview import SotV21PreviewResponse
from app.services.backtest.round_analysis_pick_builder import (
    build_aggressive_cautious_payload,
    v11_confidence_signals,
    v21_advice_signals,
)
from app.services.backtest.round_analysis_preflight import (
    REASON_INSUFFICIENT_HISTORY,
    build_no_prediction_block,
    insufficient_history_message,
)
from app.services.backtest.sot_pick_evaluation_logic import evaluate_over_picks, sample_bucket_key
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig, PlayAdviceSignals
from app.services.backtest.sot_pick_evaluation_logic import player_layer_is_neutral
from app.services.backtest.sot_pick_evaluation_preview_service import _player_layer_status
from app.services.backtest.sot_v21_preview_service import SotV21PointInTimePreviewService
from app.services.backtest.v11_round_analysis_preview import V11RoundAnalysisPreviewService
from app.services.backtest.v20_round_analysis_preview import V20RoundAnalysisPreviewService


class RoundAnalysisModelRunner:
    def __init__(self) -> None:
        self._v21_preview = SotV21PointInTimePreviewService()
        self._v11 = V11RoundAnalysisPreviewService()
        self._v20 = V20RoundAnalysisPreviewService()

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
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        models_json: dict[str, Any] = {}
        explanation_json: dict[str, Any] = {}

        for model_key in models:
            try:
                if model_key == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS:
                    block, expl = self._run_v21(
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
                elif model_key == BASELINE_SOT_MODEL_VERSION_V11_SOT:
                    block, expl = self._run_v11_v20_style(
                        self._v11,
                        fixture=fixture,
                        db=db,
                        competition_id=competition_id,
                        model_key=model_key,
                        lines=lines,
                        cautious_drop_threshold=cautious_drop_threshold,
                        play_config=play_config,
                        data_quality=data_quality,
                        actual_total=actual_total,
                    )
                elif model_key == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT:
                    block, expl = self._run_v11_v20_style(
                        self._v20,
                        fixture=fixture,
                        db=db,
                        competition_id=competition_id,
                        model_key=model_key,
                        lines=lines,
                        cautious_drop_threshold=cautious_drop_threshold,
                        play_config=play_config,
                        data_quality=data_quality,
                        actual_total=actual_total,
                    )
                else:
                    continue
            except Exception as exc:  # noqa: BLE001
                block = build_no_prediction_block(
                    model_key,
                    reason="MODEL_ERROR",
                    message=str(exc)[:300],
                    data_quality=data_quality,
                )
                expl = {}

            models_json[model_key] = block
            if expl:
                explanation_json[model_key] = expl

        return models_json, explanation_json

    def _run_v21(
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
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        preview = self._v21_preview.build_preview(
            db,
            competition_id=competition_id,
            fixture_id=int(fixture.id),
            mode=mode or BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
        )
        home_prior = int(preview.home_prior_matches_count)
        away_prior = int(preview.away_prior_matches_count)
        min_prior = min(home_prior, away_prior)

        total_raw = preview.prediction.total_predicted_sot
        if total_raw is None or min_prior == 0:
            return (
                build_no_prediction_block(
                    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
                    reason=REASON_INSUFFICIENT_HISTORY,
                    message=insufficient_history_message(min_prior, prior_home=home_prior, prior_away=away_prior),
                    prior_home=home_prior,
                    prior_away=away_prior,
                    data_quality=data_quality,
                ),
                self._v21_explanation(preview),
            )

        predicted = float(total_raw)
        home_pred = preview.prediction.home_predicted_sot
        away_pred = preview.prediction.away_predicted_sot

        bucket = sample_bucket_key(home_prior, away_prior)
        signals = v11_confidence_signals(
            home_prior=home_prior,
            away_prior=away_prior,
            warnings_count=len(preview.warnings),
            player_layer_neutral=player_layer_is_neutral(
                _player_layer_status(preview, "home"),
                _player_layer_status(preview, "away"),
            ),
        )

        aggressive, cautious, fixture_warnings = evaluate_over_picks(
            predicted,
            lines,
            actual_total,
            cautious_drop_threshold=cautious_drop_threshold,
            signals=signals,
        )
        no_lower = "no_lower_cautious_line_available" in fixture_warnings
        picks = build_aggressive_cautious_payload(
            predicted_total=predicted,
            actual_total=actual_total,
            lines=lines,
            cautious_drop_threshold=cautious_drop_threshold,
            signals=signals,
            play_config=play_config,
            advice_signals=v21_advice_signals(
                preview,
                pick_kind="aggressive",
                no_line=aggressive is None,
                no_lower=False,
            ),
            cautious_advice_signals=v21_advice_signals(
                preview,
                pick_kind="cautious",
                no_line=cautious is None,
                no_lower=no_lower,
            ),
        )

        block: dict[str, Any] = {
            "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "status": "ok",
            "label": MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS],
            "predicted_home_sot": home_pred,
            "predicted_away_sot": away_pred,
            "predicted_total_sot": picks.get("predicted_total_sot"),
            "sample_bucket": bucket,
            "warnings": list(dict.fromkeys(list(preview.warnings) + list(picks.get("warnings") or []))),
            "data_quality": dict(data_quality),
            **{k: v for k, v in picks.items() if k not in ("predicted_total_sot", "warnings")},
        }

        expl = self._v21_explanation(preview)
        return block, expl

    def _v21_explanation(self, preview: SotV21PreviewResponse) -> dict[str, Any]:
        def _macro_detail(side: str) -> dict[str, Any]:
            trace = preview.home_trace if side == "home" else preview.away_trace
            out: dict[str, Any] = {"macros": []}
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
            "source_fixture_id_lineup_home": preview.source_fixture_id_lineup_home,
            "source_fixture_id_lineup_away": preview.source_fixture_id_lineup_away,
            "source_fixture_id_unavailable_home": preview.source_fixture_id_unavailable_home,
            "source_fixture_id_unavailable_away": preview.source_fixture_id_unavailable_away,
        }

    def _run_v11_v20_style(
        self,
        svc: V11RoundAnalysisPreviewService | V20RoundAnalysisPreviewService,
        *,
        fixture: Fixture,
        db: Session,
        competition_id: int,
        model_key: str,
        lines: list[float],
        cautious_drop_threshold: float,
        play_config: PlayAdviceConfig,
        data_quality: dict[str, str],
        actual_total: int | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        raw = svc.build_fixture_model(
            db,
            fixture=fixture,
            competition_id=competition_id,
            data_quality=data_quality,
        )
        meta = dict(raw.pop("_meta", {}) or {})
        home_prior = int(meta.get("home_prior_count") or 0)
        away_prior = int(meta.get("away_prior_count") or 0)
        min_prior = min(home_prior, away_prior)
        predicted = raw.get("predicted_total_sot")

        if predicted is None or min_prior == 0:
            return (
                build_no_prediction_block(
                    model_key,
                    reason=REASON_INSUFFICIENT_HISTORY,
                    message=insufficient_history_message(min_prior, prior_home=home_prior, prior_away=away_prior),
                    prior_home=home_prior,
                    prior_away=away_prior,
                    data_quality=data_quality,
                ),
                {},
            )

        signals = v11_confidence_signals(
            home_prior=home_prior,
            away_prior=away_prior,
            warnings_count=len(raw.get("warnings") or []),
            player_layer_neutral=bool(meta.get("player_layer_neutral")),
        )
        aggressive, cautious, fixture_warnings = evaluate_over_picks(
            float(predicted),
            lines,
            actual_total,
            cautious_drop_threshold=cautious_drop_threshold,
            signals=signals,
        )
        no_lower = "no_lower_cautious_line_available" in fixture_warnings
        bucket = str(raw.get("sample_bucket") or "stable_sample")
        picks = build_aggressive_cautious_payload(
            predicted_total=float(predicted),
            actual_total=actual_total,
            lines=lines,
            cautious_drop_threshold=cautious_drop_threshold,
            signals=signals,
            play_config=play_config,
            advice_signals=PlayAdviceSignals(
                min_prior_matches=signals.min_prior_matches,
                warnings_count=signals.warnings_count,
                sample_bucket=bucket,
                player_layer_fallback=bool(meta.get("player_layer_neutral")),
                split_fallback=False,
                pick_kind="aggressive",
                no_line_available=aggressive is None,
            ),
            cautious_advice_signals=PlayAdviceSignals(
                min_prior_matches=signals.min_prior_matches,
                warnings_count=signals.warnings_count,
                sample_bucket=bucket,
                player_layer_fallback=bool(meta.get("player_layer_neutral")),
                split_fallback=False,
                pick_kind="cautious",
                no_line_available=cautious is None,
                no_lower_line=no_lower,
            ),
        )

        block = {
            "model_version": model_key,
            "status": "ok",
            **{k: v for k, v in raw.items() if k != "model_key"},
            **{k: v for k, v in picks.items() if k not in ("warnings",)},
            "warnings": list(dict.fromkeys(list(raw.get("warnings") or []) + list(picks.get("warnings") or []))),
        }
        return block, {}
