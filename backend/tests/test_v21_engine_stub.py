"""Stub engine v2.1 — nessun calcolo numerico."""

from unittest.mock import MagicMock

from app.services.predictions_v21.baseline_v2_1_weighted_components_service import (
    SotPredictionV21WeightedComponentsService,
    V21_ENGINE_NOT_READY_MESSAGE,
)


def test_v21_generate_for_fixture_not_ready():
    svc = SotPredictionV21WeightedComponentsService()
    out = svc.generate_for_fixture(MagicMock(), 123)
    assert out["status"] == "experimental_not_ready"
    assert out["message"] == V21_ENGINE_NOT_READY_MESSAGE
    assert out["predictions_saved"] == 0
    assert "predicted_sot" not in out


def test_v21_generate_for_competition_not_ready():
    svc = SotPredictionV21WeightedComponentsService()
    out = svc.generate_for_competition(MagicMock(), 2, season_year=2025)
    assert out["status"] == "experimental_not_ready"
    assert out["competition_id"] == 2
