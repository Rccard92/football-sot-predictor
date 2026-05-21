"""Test servizio v2.0 Lineup Impact."""

from __future__ import annotations

from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import SotPredictionV20LineupImpactService


def test_compute_side_v20_formula() -> None:
    svc = SotPredictionV20LineupImpactService()
    impact = {"sportapi_lineups_available": True, "status": "ok", "confidence_label": "alta"}
    adjusted, status, warnings, raw = svc._compute_side_v20(
        base_sot=5.0,
        offensive_factor=0.95,
        opponent_defensive_weakness=1.05,
        impact=impact,
    )
    assert adjusted == round(5.0 * 0.95 * 1.05, 3)
    assert status == "full"
    assert not warnings
    assert raw["base_v1_1_sot"] == 5.0


def test_compute_side_fallback_without_lineups() -> None:
    svc = SotPredictionV20LineupImpactService()
    impact = {"sportapi_lineups_available": False, "status": "no_lineups"}
    adjusted, status, warnings, _raw = svc._compute_side_v20(
        base_sot=4.2,
        offensive_factor=0.9,
        opponent_defensive_weakness=1.1,
        impact=impact,
    )
    assert adjusted == round(4.2 * 0.9 * 1.1, 3)
    assert status == "fallback_v11_only"
    assert any("v1.1" in w for w in warnings)


def test_compute_side_missing_factors_default_one() -> None:
    svc = SotPredictionV20LineupImpactService()
    impact = {"sportapi_lineups_available": True, "status": "ok"}
    adjusted, _status, _warnings, raw = svc._compute_side_v20(
        base_sot=3.0,
        offensive_factor=0.0,
        opponent_defensive_weakness=0.0,
        impact=impact,
    )
    assert adjusted == 3.0
    assert raw["offensive_lineup_factor"] == 1.0
    assert raw["opponent_defensive_weakness_factor"] == 1.0
