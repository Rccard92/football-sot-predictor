"""Test preferenza modello v2.0 / v2.1."""

from __future__ import annotations

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.model_version_preference import (
    MODEL_VERSION_PREFERENCE_ORDER,
    preferred_model_versions,
    resolve_active_model_for_fixture_preds,
)
from app.services.sot_model_registry import user_visible_model_versions


def test_preferred_model_versions_ui_only_v21_v20() -> None:
    versions = preferred_model_versions()
    assert versions == list(user_visible_model_versions())
    assert versions[0] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    assert versions[1] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT


def test_preference_order_v20_still_before_v11() -> None:
    assert MODEL_VERSION_PREFERENCE_ORDER.index(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT) < MODEL_VERSION_PREFERENCE_ORDER.index(
        BASELINE_SOT_MODEL_VERSION_V11_SOT,
    )


def test_resolve_active_model_v20_wins_when_all_present() -> None:
    preds = {
        BASELINE_SOT_MODEL_VERSION_V11_SOT: {"home": 3.9, "away": 3.7},
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: {"home": 4.1, "away": 3.5},
    }
    assert resolve_active_model_for_fixture_preds(preds) == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
