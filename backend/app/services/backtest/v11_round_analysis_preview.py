"""Preview v1.1 in-memory per fixture finished (Step I) — nessuna scrittura DB."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture, Team
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.predictions_v10.v10_prior_context import build_prior_context
from app.services.predictions_v11.offensive_production_strict import compute_v11_side
from app.services.predictions_v11.player_layer_feature_sources import COMPONENT_KEY_PLAYER
from app.services.predictions_v11.player_layer_lineup_helpers import fixture_both_lineups_available


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


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

        home_ctx = build_prior_context(
            db,
            fixture,
            team_id=int(fixture.home_team_id),
            opponent_id=int(fixture.away_team_id),
            competition_id=competition_id,
        )
        away_ctx = build_prior_context(
            db,
            fixture,
            team_id=int(fixture.away_team_id),
            opponent_id=int(fixture.home_team_id),
            competition_id=competition_id,
        )

        home_res = compute_v11_side(db, home_ctx, home_ctx.team_prior_fixtures)
        away_res = compute_v11_side(db, away_ctx, away_ctx.team_prior_fixtures)

        if not home_res.valid or home_res.expected_sot is None:
            warnings.append("home_prediction_incomplete")
        if not away_res.valid or away_res.expected_sot is None:
            warnings.append("away_prediction_incomplete")

        home_pred = _round4(home_res.expected_sot)
        away_pred = _round4(away_res.expected_sot)
        total_pred = None
        if home_pred is not None and away_pred is not None:
            total_pred = _round4(home_pred + away_pred)

        fq = str(home_res.formula_quality_status or away_res.formula_quality_status or "")
        if fq and fq != "ok":
            warnings.append(fq)

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

        return {
            "model_key": BASELINE_SOT_MODEL_VERSION_V11_SOT,
            "label": MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V11_SOT],
            "predicted_home_sot": home_pred,
            "predicted_away_sot": away_pred,
            "predicted_total_sot": total_pred,
            "sample_bucket": sample_bucket,
            "warnings": warnings,
            "data_quality": dict(data_quality),
            "_meta": {
                "home_prior_count": home_ctx.team_prior_count,
                "away_prior_count": away_ctx.team_prior_count,
                "player_layer_neutral": player_neutral,
                "formula_quality_status": fq,
            },
        }
