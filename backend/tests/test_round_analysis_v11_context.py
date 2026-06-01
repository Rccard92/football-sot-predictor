"""Test contesto v1.1 Round Analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.backtest.round_analysis_v11_context import (
    extract_v11_predictions,
    infer_v11_failure_code,
    resolve_season_id_for_round_analysis,
)
from app.services.predictions_v11.v11_side_result import V11SideResult


def test_extract_v11_predictions_sums_home_away():
    h, a, t = extract_v11_predictions(
        {"predicted_home_sot": 4.5, "predicted_away_sot": 5.0, "predicted_total_sot": None},
    )
    assert h == 4.5
    assert a == 5.0
    assert t == 9.5


def test_resolve_season_from_competition():
    db = MagicMock()
    fx = MagicMock()
    fx.season_id = None
    fx.competition_id = 1
    comp = MagicMock()
    comp.season_id = 42
    comp.season = 2025
    comp.league_id = 1
    db.get.return_value = comp

    sid, trace = resolve_season_id_for_round_analysis(db, fx, 1)
    assert sid == 42
    assert trace["resolution_source"] == "competition.season_id"


def test_infer_v11_failure_code_player_league_baseline():
    home = V11SideResult(
        valid=False,
        expected_sot=None,
        component=None,
        formula_quality_status="missing_required_player_league_baseline",
        raw_json={},
    )
    away = V11SideResult(
        valid=False,
        expected_sot=None,
        component=None,
        formula_quality_status="missing_required_player_league_baseline",
        raw_json={},
    )
    code = infer_v11_failure_code(home, away, None, league_baseline_eligible=90)
    assert code == "V11_MISSING_PLAYER_LEAGUE_BASELINE"


def test_infer_v11_failure_code_none_when_total_ok():
    home = V11SideResult(
        valid=True, expected_sot=5.0, component=None, formula_quality_status="ok", raw_json={},
    )
    away = V11SideResult(
        valid=True, expected_sot=4.0, component=None, formula_quality_status="ok", raw_json={},
    )
    assert infer_v11_failure_code(home, away, 9.0, league_baseline_eligible=90) is None
