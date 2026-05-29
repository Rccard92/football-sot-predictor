"""Verifica assenza di circular import nei moduli v2.1."""

from __future__ import annotations


def test_v21_feature_context_imports_cleanly():
    from app.services.predictions_v21.v21_feature_context import V21SideContext, build_v21_side_context

    assert V21SideContext is not None
    assert callable(build_v21_side_context)


def test_v21_lineup_impact_helpers_imports_without_context_cycle():
    from app.services.predictions_v21.v21_lineup_impact_helpers import (
        important_returns_score,
        top_shooter_absence_score,
    )
    from app.services.predictions_v21.v21_payload_helpers import missing_ids_from_refresh_payload

    assert callable(top_shooter_absence_score)
    assert callable(important_returns_score)
    assert callable(missing_ids_from_refresh_payload)


def test_v21_prediction_engine_imports():
    from app.services.predictions_v21.v21_prediction_engine import build_v21_prediction_for_fixture

    assert callable(build_v21_prediction_for_fixture)
