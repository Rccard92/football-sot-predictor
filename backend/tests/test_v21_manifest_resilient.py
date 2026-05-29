"""Caricamento resiliente manifest v2.1."""

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.model_applied_variable_manifest import (
    manifest_for_model,
    v21_manifest_error,
    v21_manifest_valid,
)


def test_v21_manifest_valid_after_import():
    assert v21_manifest_valid() is True
    assert v21_manifest_error() is None


def test_v21_manifest_loads_non_empty():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
    assert len(specs) >= 70


def test_v20_manifest_unaffected():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    assert len(specs) > len(manifest_for_model(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)) // 2
