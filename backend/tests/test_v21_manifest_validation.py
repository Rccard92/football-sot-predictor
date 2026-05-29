"""Validazione manifest v2.1."""

import pytest

from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS, V21MacroAreaSpec, V21MicroSpec
from app.services.predictions_v21.v21_manifest_validation import validate_v21_manifest


def test_v21_macro_weights_sum_to_100():
    validate_v21_manifest(V21_MANIFEST_DEFINITIONS)
    total = sum(m.macro_weight for m in V21_MANIFEST_DEFINITIONS)
    assert total == 100


def test_v21_predictive_macro_micro_weights_sum_to_100():
    for macro in V21_MANIFEST_DEFINITIONS:
        if macro.is_quality_only:
            continue
        micro_sum = sum(m.micro_weight or 0 for m in macro.micros)
        assert micro_sum == 100, f"Macro {macro.key}: micro sum {micro_sum}"


def test_v21_quality_macro_has_no_micro_weights():
    quality = next(m for m in V21_MANIFEST_DEFINITIONS if m.is_quality_only)
    assert all(m.micro_weight is None for m in quality.micros)


def test_v21_validation_fails_bad_macro_sum():
    bad = (
        V21MacroAreaSpec(
            key="bad",
            label="Bad",
            macro_weight=50,
            micros=(V21MicroSpec(key="x", label="X", micro_weight=100, source_path="a.b"),),
        ),
    )
    with pytest.raises(ValueError, match="Somma pesi macro"):
        validate_v21_manifest(bad)
