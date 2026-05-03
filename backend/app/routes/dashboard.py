from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dashboard import (
    DataCoverageBlock,
    IngestionRunSummary,
    LeagueDashboardBlock,
    SeasonDashboardBlock,
    SerieADashboardResponse,
)
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/serie-a/{season}", response_model=SerieADashboardResponse)
def serie_a_dashboard(season: int, db: Session = Depends(get_db)) -> SerieADashboardResponse:
    svc = IngestionService()
    data = svc.dashboard_serie_a(db, season)

    last = data.get("last_ingestion_run")
    cov = data["data_coverage"]
    league = data.get("league")
    season_row = data.get("season")
    return SerieADashboardResponse(
        league=LeagueDashboardBlock.model_validate(league) if league is not None else None,
        season=SeasonDashboardBlock.model_validate(season_row) if season_row is not None else None,
        teams_total=data["teams_total"],
        fixtures_total=data["fixtures_total"],
        fixtures_completed=data["fixtures_completed"],
        fixtures_scheduled=data["fixtures_scheduled"],
        fixtures_live_or_unknown=data["fixtures_live_or_unknown"],
        fixtures_with_team_stats=data["fixtures_with_team_stats"],
        team_stats_rows_total=data["team_stats_rows_total"],
        team_stats_coverage_pct=float(data["team_stats_coverage_pct"]),
        sot_feature_rows_total=int(data["sot_feature_rows_total"]),
        sot_feature_expected_rows=int(data["sot_feature_expected_rows"]),
        sot_feature_coverage_pct=float(data["sot_feature_coverage_pct"]),
        sot_predictions_total=int(data["sot_predictions_total"]),
        sot_predictions_expected=int(data["sot_predictions_expected"]),
        sot_predictions_coverage_pct=float(data["sot_predictions_coverage_pct"]),
        avg_expected_sot=float(data["avg_expected_sot"]),
        avg_prediction_confidence=float(data["avg_prediction_confidence"]),
        sot_backtests_total=int(data["sot_backtests_total"]),
        sot_backtests_expected=int(data["sot_backtests_expected"]),
        sot_backtest_coverage_pct=float(data["sot_backtest_coverage_pct"]),
        sot_backtest_mae=float(data["sot_backtest_mae"]),
        sot_backtest_rmse=float(data["sot_backtest_rmse"]),
        sot_backtest_avg_expected_sot=float(data["sot_backtest_avg_expected_sot"]),
        sot_backtest_avg_actual_sot=float(data["sot_backtest_avg_actual_sot"]),
        upcoming_fixtures_total=int(data.get("upcoming_fixtures_total", 0)),
        upcoming_sot_feature_rows_total=int(data.get("upcoming_sot_feature_rows_total", 0)),
        upcoming_sot_predictions_total=int(data.get("upcoming_sot_predictions_total", 0)),
        last_ingestion_run=IngestionRunSummary.model_validate(last) if last else None,
        data_coverage=DataCoverageBlock(
            teams_imported=bool(cov["teams_imported"]),
            fixtures_imported=bool(cov["fixtures_imported"]),
        ),
    )
