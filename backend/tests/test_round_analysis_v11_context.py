"""Test contesto v1.1 Round Analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.backtest.round_analysis_v11_context import (
    extract_v11_predictions,
    resolve_season_id_for_round_analysis,
)


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
