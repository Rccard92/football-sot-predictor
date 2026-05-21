"""Test base v2.0 Lineup Impact: status, penalità Top5, formula moltiplicativa."""

from __future__ import annotations

from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import SotPredictionV20LineupImpactService
from app.services.sportapi.sportapi_lineup_impact_logic import (
    classify_lineup_status,
    clamp_factor,
    find_replacement,
    penalty_weight_for_status,
)


def test_classify_starter_pid_in_starters() -> None:
    assert (
        classify_lineup_status(
            player_id=1,
            mapping_recommendation="AUTO_SAFE",
            mapping_confidence=95.0,
            sportapi_provider_id=10,
            sportapi_starter_pids={10},
            sportapi_bench_pids=set(),
            sportapi_missing_pids=set(),
        )
        == "STARTER"
    )


def test_classify_missing_pid_in_missing_set() -> None:
    assert (
        classify_lineup_status(
            player_id=2,
            mapping_recommendation="AUTO_SAFE",
            mapping_confidence=90.0,
            sportapi_provider_id=30,
            sportapi_starter_pids=set(),
            sportapi_bench_pids=set(),
            sportapi_missing_pids={30},
        )
        == "MISSING"
    )


def test_top5_missing_lowers_offensive_factor_vs_replacement() -> None:
    """Top5 assente (MISSING) abbassa il fattore; sostituto da starter_pool lo recupera parzialmente."""
    share = 0.20
    confirmed = False
    lineup_weight = 0.60

    penalty_missing = share * penalty_weight_for_status("MISSING", confirmed)
    factor_without_rep = clamp_factor(1.0 - penalty_missing * lineup_weight, confirmed)

    starter_pool = [
        {
            "player_id": 100,
            "display_role": "A",
            "team_sot_share": 0.12,
            "sot_per_90": 1.5,
            "player_name": "Sostituto",
        },
    ]
    _rep, credit, _ = find_replacement(
        target_role="A",
        target_share=share,
        starter_pool=starter_pool,
        bench_pool=[],
        used_replacement_player_ids=set(),
    )
    net_with_rep = max(0.0, penalty_missing - credit)
    factor_with_rep = clamp_factor(1.0 - net_with_rep * lineup_weight, confirmed)

    assert factor_without_rep < 1.0
    assert factor_with_rep > factor_without_rep
    assert factor_with_rep <= 1.0


def test_compute_side_v20_multiplicative() -> None:
    svc = SotPredictionV20LineupImpactService()
    impact = {"sportapi_lineups_available": True, "status": "ok"}
    adjusted, status, warnings, raw = svc._compute_side_v20(
        base_sot=5.0,
        offensive_factor=0.92,
        opponent_defensive_weakness=1.04,
        impact=impact,
    )
    assert adjusted == round(5.0 * 0.92 * 1.04, 3)
    assert status == "full"
    assert not warnings
    assert raw["base_v1_1_sot"] == 5.0
    assert raw["offensive_lineup_factor"] == 0.92
    assert raw["opponent_defensive_weakness_factor"] == 1.04
