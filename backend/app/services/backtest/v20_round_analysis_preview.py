"""Preview v2.0 in-memory: v1.1 base × lineup impact (Step I)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models import Fixture, Team
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.backtest.v11_round_analysis_preview import V11RoundAnalysisPreviewService
from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import SotPredictionV20LineupImpactService
from app.services.sportapi.sportapi_lineup_impact_service import LineupImpactSimulationService


class V20RoundAnalysisPreviewService:
    def __init__(self) -> None:
        self._v11 = V11RoundAnalysisPreviewService()
        self._v20_formula = SotPredictionV20LineupImpactService()

    def build_fixture_model(
        self,
        db: Session,
        *,
        fixture: Fixture,
        competition_id: int,
        data_quality: dict[str, str],
    ) -> dict[str, Any]:
        v11 = self._v11.build_fixture_model(
            db,
            fixture=fixture,
            competition_id=competition_id,
            data_quality=data_quality,
        )
        warnings = list(v11.get("warnings") or [])
        dq = dict(data_quality)

        home = db.get(Team, int(fixture.home_team_id))
        away = db.get(Team, int(fixture.away_team_id))
        hn = home.name if home else str(fixture.home_team_id)
        an = away.name if away else str(fixture.away_team_id)

        impact = LineupImpactSimulationService().simulate_for_fixture(
            db,
            int(fixture.id),
            home_team_name=hn,
            away_team_name=an,
        )

        home_side = impact.get("home") or {}
        away_side = impact.get("away") or {}
        if not impact.get("sportapi_lineups_available"):
            warnings.append("lineup_impact_fallback")
            dq["lineup"] = "missing"
        elif impact.get("status") != "ok":
            warnings.append("lineup_impact_partial")
            dq["lineup"] = "partial"

        base_home = v11.get("predicted_home_sot")
        base_away = v11.get("predicted_away_sot")
        home_pred = None
        away_pred = None
        lineup_impact_factors: dict[str, Any] = {}

        if base_home is not None:
            off = float(home_side.get("offensive_lineup_factor") or home_side.get("factor") or 1.0)
            opp_def = float(
                home_side.get("opponent_defensive_weakness_factor")
                or away_side.get("defensive_weakness_factor")
                or 1.0,
            )
            lineup_impact_factors["home"] = {
                "offensive_lineup_factor": off,
                "opponent_defensive_weakness": opp_def,
                "base_sot": float(base_home),
            }
            home_pred, _, _, _ = self._v20_formula._compute_side_v20(  # noqa: SLF001
                base_sot=float(base_home),
                offensive_factor=off,
                opponent_defensive_weakness=opp_def,
                impact=impact,
            )
            if home_pred is not None:
                lineup_impact_factors["home"]["adjusted_sot"] = home_pred

        if base_away is not None:
            off = float(away_side.get("offensive_lineup_factor") or away_side.get("factor") or 1.0)
            opp_def = float(
                away_side.get("opponent_defensive_weakness_factor")
                or home_side.get("defensive_weakness_factor")
                or 1.0,
            )
            lineup_impact_factors["away"] = {
                "offensive_lineup_factor": off,
                "opponent_defensive_weakness": opp_def,
                "base_sot": float(base_away),
            }
            away_pred, _, side_warn, _ = self._v20_formula._compute_side_v20(  # noqa: SLF001
                base_sot=float(base_away),
                offensive_factor=off,
                opponent_defensive_weakness=opp_def,
                impact=impact,
            )
            if away_pred is not None:
                lineup_impact_factors["away"]["adjusted_sot"] = away_pred
            warnings.extend(side_warn)

        total_pred = None
        if home_pred is not None and away_pred is not None:
            total_pred = round(float(home_pred) + float(away_pred), 4)

        return {
            "model_key": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
            "label": MODEL_LABELS[BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT],
            "predicted_home_sot": home_pred,
            "predicted_away_sot": away_pred,
            "predicted_total_sot": total_pred,
            "sample_bucket": v11.get("sample_bucket"),
            "warnings": list(dict.fromkeys(warnings)),
            "data_quality": dq,
            "_meta": {
                **(v11.get("_meta") or {}),
                "lineup_impact_status": impact.get("status"),
                "sportapi_lineups_available": bool(impact.get("sportapi_lineups_available")),
                "v11_trace_summary": (v11.get("_meta") or {}).get("trace_summary"),
                "base_v1_1_total": (
                    round(float(base_home) + float(base_away), 4)
                    if base_home is not None and base_away is not None
                    else None
                ),
                "lineup_impact_factors": lineup_impact_factors,
                "adjusted_total_sot": total_pred,
            },
        }
