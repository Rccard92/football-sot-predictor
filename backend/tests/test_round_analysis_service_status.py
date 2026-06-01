"""Test status completed_with_warnings."""

from __future__ import annotations

from app.services.backtest.round_analysis_preflight import RoundHistoryPreflight
from app.services.backtest.round_analysis_service import RoundAnalysisService


def test_resolve_completed_with_warnings_on_insufficient_history():
    svc = RoundAnalysisService()
    pf = RoundHistoryPreflight(
        fixtures_count=10,
        min_prior_matches_home=0,
        min_prior_matches_away=0,
        avg_prior_matches=0.0,
        team_stats_available=10,
        lineups_available=5,
        unavailable_available=0,
        player_stats_available=0,
        insufficient_history=True,
        data_quality_status="critical",
        reason="INSUFFICIENT_HISTORY",
        message="test",
        first_recommended_round=3,
    )
    status = svc._resolve_final_status(
        history_preflight=pf,
        model_summary={
            "baseline_v1_1_sot": {"predictions_available": 0},
        },
        dq_summary={"badge": "Critico"},
    )
    assert status == "completed_with_warnings"
