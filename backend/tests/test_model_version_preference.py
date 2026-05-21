"""Test priorità modello v1.0 > v0.4."""

from __future__ import annotations

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
)
from app.services.model_version_preference import (
    MODEL_VERSION_PREFERENCE_ORDER,
    preferred_model_versions,
    resolve_active_model_for_fixture_preds,
)


def test_preferred_model_versions_ui_v20_v11() -> None:
    from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT

    versions = preferred_model_versions()
    assert versions[0] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    assert versions[1] == BASELINE_SOT_MODEL_VERSION_V11_SOT
    assert len(versions) == 2


def test_resolve_active_model_v11_wins_when_v20_absent() -> None:
    preds = {
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT: {"home": 4.2, "away": 3.8},
        BASELINE_SOT_MODEL_VERSION_V10_SOT: {"home": 4.5, "away": 4.0},
        BASELINE_SOT_MODEL_VERSION_V11_SOT: {"home": 3.9, "away": 3.7},
        BASELINE_SOT_MODEL_VERSION: {"home": 3.0, "away": 2.9},
    }
    assert resolve_active_model_for_fixture_preds(preds) == BASELINE_SOT_MODEL_VERSION_V11_SOT


def test_resolve_active_model_v10_when_v11_partial() -> None:
    preds = {
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT: {"home": 4.2, "away": 3.8},
        BASELINE_SOT_MODEL_VERSION_V10_SOT: {"home": 4.5, "away": 4.0},
        BASELINE_SOT_MODEL_VERSION_V11_SOT: {"home": 3.9, "away": None},
    }
    assert resolve_active_model_for_fixture_preds(preds) == BASELINE_SOT_MODEL_VERSION_V10_SOT


def test_resolve_active_model_v04_when_v10_partial() -> None:
    preds = {
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT: {"home": 4.2, "away": 3.8},
        BASELINE_SOT_MODEL_VERSION_V10_SOT: {"home": 4.5, "away": None},
    }
    assert resolve_active_model_for_fixture_preds(preds) == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT


def test_preference_order_includes_legacy_after_ui() -> None:
    assert BASELINE_SOT_MODEL_VERSION_V11_SOT in MODEL_VERSION_PREFERENCE_ORDER
    assert BASELINE_SOT_MODEL_VERSION_V10_SOT in MODEL_VERSION_PREFERENCE_ORDER
