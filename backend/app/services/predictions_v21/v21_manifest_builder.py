"""Costruisce AppliedVariableSpec per manifest v2.1."""

from __future__ import annotations

from app.services.model_applied_variable_manifest import AppliedVariableSpec
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS
from app.services.predictions_v21.v21_manifest_validation import validate_v21_manifest


def build_v21_manifest() -> list[AppliedVariableSpec]:
    validate_v21_manifest(V21_MANIFEST_DEFINITIONS)
    specs: list[AppliedVariableSpec] = []
    for macro in V21_MANIFEST_DEFINITIONS:
        area_label = macro.label
        if macro.is_quality_only:
            for micro in macro.micros:
                specs.append(
                    AppliedVariableSpec(
                        trace_key=f"v21_quality_{macro.key}_{micro.key}",
                        label=micro.label,
                        area=area_label,
                        application_role="quality_control",
                        parent_component=None,
                        direct_formula_impact=False,
                        expected_in_debug=True,
                        framework_key=None,
                        resolver=f"v21:quality:{macro.key}:{micro.key}",
                    ),
                )
        else:
            specs.append(
                AppliedVariableSpec(
                    trace_key=f"v21_macro_{macro.key}",
                    label=macro.label,
                    area=area_label,
                    application_role="direct_formula_component",
                    parent_component=None,
                    direct_formula_impact=True,
                    expected_in_debug=True,
                    framework_key=None,
                    resolver=f"v21:macro:{macro.key}",
                ),
            )
            for micro in macro.micros:
                specs.append(
                    AppliedVariableSpec(
                        trace_key=f"v21_micro_{macro.key}_{micro.key}",
                        label=micro.label,
                        area=area_label,
                        application_role="component_input",
                        parent_component=macro.key,
                        direct_formula_impact=True,
                        expected_in_debug=True,
                        framework_key=micro.key,
                        resolver=f"v21:micro:{macro.key}:{micro.key}",
                    ),
                )
    return specs
