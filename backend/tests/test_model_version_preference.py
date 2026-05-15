"""Test priorità modello v1.0 > v0.4."""

from __future__ import annotations

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
)
from app.services.model_version_preference import (
    MODEL_VERSION_PREFERENCE_ORDER,
    preferred_model_versions,
    resolve_active_model_for_fixture_preds,
)


def test_preferred_model_versions_v10_first() -> None:
    versions = preferred_model_versions()
    assert versions[0] == BASELINE_SOT_MODEL_VERSION_V10_SOT
    assert BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT in versions
    assert versions.index(BASELINE_SOT_MODEL_VERSION_V10_SOT) < versions.index(
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    )


def test_resolve_active_model_v10_wins_when_both_present() -> None:
    preds = {
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT: {"home": 4.2, "away": 3.8},
        BASELINE_SOT_MODEL_VERSION_V10_SOT: {"home": 4.5, "away": 4.0},
        BASELINE_SOT_MODEL_VERSION: {"home": 3.0, "away": 2.9},
    }
    assert resolve_active_model_for_fixture_preds(preds) == BASELINE_SOT_MODEL_VERSION_V10_SOT


def test_resolve_active_model_v04_when_v10_partial() -> None:
    preds = {
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT: {"home": 4.2, "away": 3.8},
        BASELINE_SOT_MODEL_VERSION_V10_SOT: {"home": 4.5, "away": None},
    }
    assert resolve_active_model_for_fixture_preds(preds) == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT


def test_preference_order_matches_export() -> None:
    assert list(MODEL_VERSION_PREFERENCE_ORDER) == preferred_model_versions()
