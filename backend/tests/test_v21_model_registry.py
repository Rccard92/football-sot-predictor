"""Registry v2.1 visibile in UI."""

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.sot_model_registry import (
    get_model_display,
    user_visible_model_versions,
)


def test_user_visible_includes_v20_and_v21_not_v11():
    visible = user_visible_model_versions()
    assert BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS in visible
    assert BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT in visible
    assert BASELINE_SOT_MODEL_VERSION_V11_SOT not in visible


def test_v21_registry_metadata():
    info = get_model_display(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
    assert info is not None
    assert info.label == "v2.1 SOT Weighted Components"
    assert info.stage_badge == "Weighted Components"
    assert info.registry_status == "experimental"
    assert info.is_stable is False
