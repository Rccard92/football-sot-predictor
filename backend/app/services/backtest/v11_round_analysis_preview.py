"""Preview v1.1 in-memory per fixture finished (Step I) — motore produzione compute_v11_side."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture, Team
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.backtest.round_analysis_v11_context import (
    WARN_HOME_AWAY_SPLIT_MISSING,
    WARN_SPLIT_SAMPLE_INSUFFICIENT_USED_GENERAL_BASE,
    build_split_context,
    build_v11_fixture_trace,
    count_league_baseline_eligible_fixtures,
    detect_v11_split_fallback,
    extract_v11_predictions,
    infer_v11_failure_code,
    resolve_season_id_for_round_analysis,
)
from app.services.backtest.v11_round_analysis_engine import predict_v11_side_for_team
from app.services.predictions_v11.player_layer_feature_sources import COMPONENT_KEY_PLAYER
from app.services.predictions_v11.player_layer_lineup_helpers import fixture_both_lineups_available


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _aggregate_formula_quality(home_res: Any, away_res: Any) -> str:
    statuses = {str(home_res.formula_quality_status or ""), str(away_res.formula_quality_status or "")}
    if "partial_low_sample" in statuses:
        return "partial_low_sample"
    if statuses == {"ok"}:
        return "ok"
    return str(home_res.formula_quality_status or away_res.formula_quality_status or "")


class V11RoundAnalysisPreviewService:
    def build_fixture_model(
        self,
        db: Session,
        *,
        fixture: Fixture,
        competition_id: int,
        data_quality: dict[str, str],
    ) -> dict[str, Any]:
        home = db.get(Team, int(fixture.home_team_id))
        away = db.get(Team, int(fixture.away_team_id))
        warnings: list[str] = []

        season_id_used, season_resolution = resolve_season_id_for_round_analysis(
            db,
            fixture,
            competition_id,
        )

        home_res, home_ctx = predict_v11_side_for_team(
            db,
            fixture,
            team_id=int(fixture.home_team_id),
            opponent_id=int(fixture.away_team_id),
            competition_id=competition_id,
        )
        away_res, away_ctx = predict_v11_side_for_team(
            db,
            fixture,
            team_id=int(fixture.away_team_id),
            opponent_id=int(fixture.home_team_id),
            competition_id=competition_id,
        )

        league_baseline_eligible = 0
        if fixture.kickoff_at is not None:
            league_baseline_eligible = count_league_baseline_eligible_fixtures(
                db,
                season_id=int(home_ctx.season_id),
                cutoff_kickoff=fixture.kickoff_at,
                cutoff_fixture_id=int(fixture.id),
            )

        if not home_res.valid or home_res.expected_sot is None:
            warnings.append("home_prediction_incomplete")
        if not away_res.valid or away_res.expected_sot is None:
            warnings.append("away_prediction_incomplete")

        home_pred = _round4(home_res.expected_sot)
        away_pred = _round4(away_res.expected_sot)
        total_pred = None
        if home_pred is not None and away_pred is not None:
            total_pred = _round4(home_pred + away_pred)

        if total_pred is None:
            eh, ea, et = extract_v11_predictions(
                {
                    "predicted_home_sot": home_pred,
                    "predicted_away_sot": away_pred,
                    "predicted_total_sot": total_pred,
                },
            )
            home_pred = home_pred if home_pred is not None else eh
            away_pred = away_pred if away_pred is not None else ea
            total_pred = et

        if total_pred is not None and (home_pred is None or away_pred is None):
            warnings.append(WARN_HOME_AWAY_SPLIT_MISSING)

        fallback_used = detect_v11_split_fallback(home_res, away_res)
        if fallback_used:
            warnings.append(WARN_SPLIT_SAMPLE_INSUFFICIENT_USED_GENERAL_BASE)

        formula_quality = _aggregate_formula_quality(home_res, away_res)

        both_lineups = fixture_both_lineups_available(
            db,
            fixture_id=int(fixture.id),
            home_team_id=int(fixture.home_team_id),
            away_team_id=int(fixture.away_team_id),
        )
        if not both_lineups:
            warnings.append("lineup_missing")

        sample_bucket = "stable_sample"
        min_prior = min(home_ctx.team_prior_count, away_ctx.team_prior_count)
        if min_prior < 5:
            sample_bucket = "early_low_sample"
        elif min_prior <= 14:
            sample_bucket = "medium_sample"

        player_neutral = False
        for res in (home_res, away_res):
            comps = (res.raw_json or {}).get("components") or {}
            pl = comps.get(COMPONENT_KEY_PLAYER) if isinstance(comps, dict) else None
            if isinstance(pl, dict) and str(pl.get("status") or "") in ("neutral", "fallback"):
                player_neutral = True

        split_context = build_split_context(
            home_ctx=home_ctx,
            away_ctx=away_ctx,
            home_res=home_res,
            away_res=away_res,
        )

        inferred_error = infer_v11_failure_code(
            home_res,
            away_res,
            total_pred,
            league_baseline_eligible=league_baseline_eligible,
        )

        trace_summary = build_v11_fixture_trace(
            fixture=fixture,
            competition_id=competition_id,
            season_id_used=int(home_ctx.season_id),
            season_resolution=season_resolution,
            home_prior_count=int(home_ctx.team_prior_count),
            away_prior_count=int(away_ctx.team_prior_count),
            league_baseline_eligible=league_baseline_eligible,
            home_res=home_res,
            away_res=away_res,
            home_pred=home_pred,
            away_pred=away_pred,
            total_pred=total_pred,
            context_mode="production_v11",
            inferred_error_code=inferred_error,
            split_context=split_context,
            fallback_used=fallback_used,
            formula_quality=formula_quality,
        )

        return {
            "model_key": BASELINE_SOT_MODEL_VERSION_V11_SOT,
            "label": MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V11_SOT],
            "predicted_home_sot": home_pred,
            "predicted_away_sot": away_pred,
            "predicted_total_sot": total_pred,
            "sample_bucket": sample_bucket,
            "formula_quality": formula_quality,
            "fallback_used": fallback_used,
            "used_split": split_context.get("used_split"),
            "warnings": list(dict.fromkeys(warnings)),
            "data_quality": dict(data_quality),
            "_meta": {
                "home_prior_count": home_ctx.team_prior_count,
                "away_prior_count": away_ctx.team_prior_count,
                "player_layer_neutral": player_neutral,
                "formula_quality_status": formula_quality,
                "season_id_used": int(home_ctx.season_id),
                "season_resolution": season_resolution,
                "league_baseline_eligible_fixtures": league_baseline_eligible,
                "inferred_error_code": inferred_error,
                "fallback_used": fallback_used,
                "used_split": split_context.get("used_split"),
                "split_context": split_context,
                "trace_summary": trace_summary,
                "home_side": trace_summary.get("home_side"),
                "away_side": trace_summary.get("away_side"),
            },
        }
