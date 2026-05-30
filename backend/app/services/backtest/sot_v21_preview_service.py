"""Preview read-only SOT v2.1 point-in-time su singola fixture (Step E)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.backtest.errors import raise_backtest_http
from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.schemas.backtest_sot_v21_preview import (
    SotV21PreviewErrors,
    SotV21PreviewFixtureBrief,
    SotV21PreviewMacroTrace,
    SotV21PreviewPrediction,
    SotV21PreviewResponse,
    SotV21PreviewSideTrace,
)
from app.services.backtest.point_in_time_context_service import PointInTimeContextService
from app.services.backtest.sot_v21_pit_macro_builder import build_pit_side_preview


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _error_pair(predicted: float | None, actual: int | None) -> tuple[float | None, float | None]:
    if predicted is None or actual is None:
        return None, None
    err = round(float(predicted) - float(actual), 4)
    return err, round(abs(err), 4)


class SotV21PointInTimePreviewService:
    def build_preview(
        self,
        db: Session,
        *,
        competition_id: int,
        fixture_id: int,
        mode: str = "pre_lineup",
    ) -> SotV21PreviewResponse:
        if mode != "pre_lineup":
            raise_backtest_http(
                422,
                "mode_not_supported_yet",
                "SOT v2.1 PIT preview supports only pre_lineup in Step E.",
                mode=mode,
            )

        ctx = PointInTimeContextService().build_sot_context(
            db,
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
            mode=mode,
            market_key="shots_on_target",
        )

        home_side = build_pit_side_preview(
            team=ctx.home_team_stats,
            opponent=ctx.away_team_stats,
            league=ctx.league_baselines,
            ctx=ctx,
        )
        away_side = build_pit_side_preview(
            team=ctx.away_team_stats,
            opponent=ctx.home_team_stats,
            league=ctx.league_baselines,
            ctx=ctx,
        )

        home_pred = _round4(home_side.expected_sot)
        away_pred = _round4(away_side.expected_sot)
        total_pred = None
        if home_pred is not None and away_pred is not None:
            total_pred = _round4(home_pred + away_pred)

        actuals = ctx.actuals_for_scoring
        home_err, home_abs = _error_pair(home_pred, actuals.actual_home_sot)
        away_err, away_abs = _error_pair(away_pred, actuals.actual_away_sot)
        total_err, total_abs = _error_pair(total_pred, actuals.actual_total_sot)

        warnings = list(dict.fromkeys(ctx.warnings + home_side.warnings + away_side.warnings))
        fallbacks = list(
            dict.fromkeys(ctx.fallback_variables + home_side.fallback_variables + away_side.fallback_variables),
        )

        neutral_macro_count = sum(
            1
            for m in home_side.macro_traces + away_side.macro_traces
            if m.get("status") in ("not_built_yet", "neutral_fallback")
        )

        feature_snapshot: dict[str, Any] = {
            **ctx.feature_snapshot_json,
            "preview_only": True,
            "algorithm_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "neutral_macro_count": neutral_macro_count,
            "home_predicted_sot": home_pred,
            "away_predicted_sot": away_pred,
            "total_predicted_sot": total_pred,
        }

        def _side_trace(side) -> SotV21PreviewSideTrace:
            return SotV21PreviewSideTrace(
                base_anchor_sot=side.base_anchor_trace,
                weighted_macro_multiplier=side.weighted_macro_multiplier,
                expected_sot_v21_pit=side.expected_sot,
                macros=[SotV21PreviewMacroTrace(**m) for m in side.macro_traces],
            )

        return SotV21PreviewResponse(
            status="ok",
            market_key="shots_on_target",
            algorithm_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            mode=mode,
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
            fixture=SotV21PreviewFixtureBrief(
                home_team=ctx.home_team_name,
                away_team=ctx.away_team_name,
                kickoff_at=ctx.fixture_kickoff_at,
                round=ctx.fixture_round,
            ),
            leakage_guard=ctx.leakage_guard,
            cutoff_time=ctx.cutoff_time,
            latest_fixture_used_at=ctx.latest_fixture_used_at,
            actuals_used_as_input=False,
            prediction=SotV21PreviewPrediction(
                home_predicted_sot=home_pred,
                away_predicted_sot=away_pred,
                total_predicted_sot=total_pred,
            ),
            actuals_for_scoring=actuals,
            errors=SotV21PreviewErrors(
                home_error=home_err,
                away_error=away_err,
                total_error=total_err,
                home_abs_error=home_abs,
                away_abs_error=away_abs,
                total_abs_error=total_abs,
            ),
            home_trace=_side_trace(home_side),
            away_trace=_side_trace(away_side),
            home_prior_matches_count=int(ctx.home_prior_matches_count),
            away_prior_matches_count=int(ctx.away_prior_matches_count),
            warnings=warnings,
            fallback_variables=fallbacks,
            feature_snapshot_json=feature_snapshot,
        )
