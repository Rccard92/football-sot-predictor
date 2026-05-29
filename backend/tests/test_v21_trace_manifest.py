"""Manifest e trace stub v2.1."""

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.services.model_applied_variable_manifest import is_countable_role, manifest_for_model
from app.services.model_applied_variable_trace import build_applied_variable_trace_side


def test_v21_manifest_not_empty():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
    assert len(specs) >= 70


def test_v21_trace_all_not_tracked_yet_without_engine():
    raw = {"engine_status": "experimental_not_ready", "status": "experimental_not_ready"}
    trace = build_applied_variable_trace_side(
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        raw,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=12.0,
        prediction_confidence=None,
    )
    assert len(trace) == len(manifest_for_model(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS))
    predictive = [r for r in trace if r.get("application_role") in ("direct_formula_component", "component_input")]
    assert predictive
    assert all(r.get("status") == "not_tracked_yet" for r in predictive)


def test_v21_quality_rows_not_formula_final():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
    quality = [s for s in specs if s.area == "Controlli qualità / sicurezza modello"]
    assert len(quality) == 7
    assert all(s.application_role == "quality_control" for s in quality)
    assert all(not s.direct_formula_impact for s in quality)
    assert not any(is_countable_role(s.application_role) and s.direct_formula_impact for s in quality if s.application_role == "quality_control")
