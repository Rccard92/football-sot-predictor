"""Engine v2.1 — service pronto (non più stub experimental_not_ready)."""

from unittest.mock import MagicMock

from app.services.predictions_v21.baseline_v2_1_weighted_components_service import (
    SotPredictionV21WeightedComponentsService,
)


def test_v21_service_engine_status_ready():
    svc = SotPredictionV21WeightedComponentsService()
    assert svc.engine_status == "ready"
    assert svc.model_version == "baseline_v2_1_weighted_components"


def test_v21_generate_for_fixture_not_found():
    db = MagicMock()
    db.get.return_value = None
    svc = SotPredictionV21WeightedComponentsService()
    out = svc.generate_for_fixture(db, 999999)
    assert out["status"] == "error"
    assert out["message"] == "fixture_not_found"
