"""Preview read-only SOT v2.1 point-in-time su singola fixture (Step E)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI, BACKTEST_MODE_PRE_LINEUP
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
from app.services.backtest.historical_fixture_snapshot_service import HistoricalFixtureSnapshotService
from app.services.backtest.historical_lineup_macro_service import HistoricalLineupMacroService
from app.services.backtest.historical_unavailable_macro_service import HistoricalUnavailableMacroService
from app.services.backtest.point_in_time_context_service import PointInTimeContextService
from app.services.backtest.rolling_player_layer_service import RollingPlayerLayerService
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
        if mode not in (BACKTEST_MODE_PRE_LINEUP, BACKTEST_MODE_HISTORICAL_OFFICIAL_XI):
            raise_backtest_http(
                422,
                "mode_not_supported_yet",
                "SOT v2.1 PIT preview supports pre_lineup and historical_official_xi.",
                mode=mode,
            )

        ctx = PointInTimeContextService().build_sot_context(
            db,
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
            mode=mode,
            market_key="shots_on_target",
        )

        if mode == BACKTEST_MODE_HISTORICAL_OFFICIAL_XI:
            snapshot_svc = HistoricalFixtureSnapshotService()
            layer_svc = RollingPlayerLayerService()
            lineup_svc = HistoricalLineupMacroService()
            unavail_svc = HistoricalUnavailableMacroService()

            snapshot = snapshot_svc.get_fixture_official_snapshot(
                db,
                competition_id=int(competition_id),
                fixture_id=int(fixture_id),
            )

            home_layer = layer_svc.build_team_player_layer(
                db,
                competition_id=int(competition_id),
                team_id=int(ctx.home_team_id),
                cutoff_time=ctx.cutoff_time,
                side_snapshot=snapshot.home,
                league_avg_sot_for=ctx.league_baselines.league_avg_sot_for,
            )
            away_layer = layer_svc.build_team_player_layer(
                db,
                competition_id=int(competition_id),
                team_id=int(ctx.away_team_id),
                cutoff_time=ctx.cutoff_time,
                side_snapshot=snapshot.away,
                league_avg_sot_for=ctx.league_baselines.league_avg_sot_for,
            )
            home_lineup_macro = lineup_svc.build_team_lineup_macro(
                db,
                snapshot=snapshot,
                competition_id=int(competition_id),
                team_id=int(ctx.home_team_id),
                cutoff_time=ctx.cutoff_time,
                side="home",
            )
            away_lineup_macro = lineup_svc.build_team_lineup_macro(
                db,
                snapshot=snapshot,
                competition_id=int(competition_id),
                team_id=int(ctx.away_team_id),
                cutoff_time=ctx.cutoff_time,
                side="away",
            )
            home_unavailable_macro = unavail_svc.build_team_unavailable_macro(
                db,
                snapshot=snapshot,
                competition_id=int(competition_id),
                team_id=int(ctx.home_team_id),
                cutoff_time=ctx.cutoff_time,
                side="home",
                opponent_side=snapshot.away,
                league_avg_sot_for=ctx.league_baselines.league_avg_sot_for,
            )
            away_unavailable_macro = unavail_svc.build_team_unavailable_macro(
                db,
                snapshot=snapshot,
                competition_id=int(competition_id),
                team_id=int(ctx.away_team_id),
                cutoff_time=ctx.cutoff_time,
                side="away",
                opponent_side=snapshot.home,
                league_avg_sot_for=ctx.league_baselines.league_avg_sot_for,
            )
            ctx = ctx.model_copy(
                update={
                    "fixture_snapshot": snapshot,
                    "home_player_layer": home_layer,
                    "away_player_layer": away_layer,
                    "home_lineup_macro": home_lineup_macro,
                    "away_lineup_macro": away_lineup_macro,
                    "home_unavailable_macro": home_unavailable_macro,
                    "away_unavailable_macro": away_unavailable_macro,
                },
            )

        home_side = build_pit_side_preview(
            team=ctx.home_team_stats,
            opponent=ctx.away_team_stats,
            league=ctx.league_baselines,
            ctx=ctx,
            is_home=True,
            mode=mode,
        )
        away_side = build_pit_side_preview(
            team=ctx.away_team_stats,
            opponent=ctx.home_team_stats,
            league=ctx.league_baselines,
            ctx=ctx,
            is_home=False,
            mode=mode,
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
        lineup_macro_active = False
        unavailable_macro_active = False
        if mode == BACKTEST_MODE_HISTORICAL_OFFICIAL_XI:
            warnings.insert(0, "historical_official_xi_mode_not_prelineup")
            lineup_macro_active = (
                ctx.home_lineup_macro is not None
                and ctx.away_lineup_macro is not None
                and ctx.home_lineup_macro.status != "neutral_fallback"
                and ctx.away_lineup_macro.status != "neutral_fallback"
            )
            unavailable_macro_active = (
                ctx.home_unavailable_macro is not None
                and ctx.away_unavailable_macro is not None
                and ctx.home_unavailable_macro.status != "neutral_fallback"
                and ctx.away_unavailable_macro.status != "neutral_fallback"
            )
            if lineup_macro_active:
                suppress = {
                    "no_historical_probable_lineups",
                    "lineups_point_in_time_limited",
                    "lineups_point_in_time_not_built_yet",
                }
                warnings = [w for w in warnings if w not in suppress]
            if unavailable_macro_active or (
                ctx.home_unavailable_macro is not None
                and ctx.away_unavailable_macro is not None
                and ctx.home_unavailable_macro.status == "available"
                and ctx.away_unavailable_macro.status == "available"
            ):
                warnings = [w for w in warnings if w != "injuries_point_in_time_not_built_yet"]
            warnings = list(dict.fromkeys(warnings))
        fallbacks = list(
            dict.fromkeys(ctx.fallback_variables + home_side.fallback_variables + away_side.fallback_variables),
        )
        if mode == BACKTEST_MODE_HISTORICAL_OFFICIAL_XI and lineup_macro_active:
            fallbacks = [f for f in fallbacks if f != "lineups_point_in_time_neutral"]
        if mode == BACKTEST_MODE_HISTORICAL_OFFICIAL_XI and (
            unavailable_macro_active
            or (
                ctx.home_unavailable_macro is not None
                and ctx.away_unavailable_macro is not None
                and "available" in (ctx.home_unavailable_macro.status, ctx.away_unavailable_macro.status)
            )
        ):
            fallbacks = [f for f in fallbacks if f != "injuries_point_in_time_not_built_yet"]

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
