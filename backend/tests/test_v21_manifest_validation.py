"""Validazione manifest v2.1."""

import pytest

from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS, V21MacroAreaSpec, V21MicroSpec
from app.services.predictions_v21.v21_manifest_validation import (
    find_v21_duplicate_micro_keys,
    format_v21_duplicate_micro_keys_error,
    list_v21_duplicate_micro_keys,
    validate_v21_manifest,
)


def test_v21_macro_weights_sum_to_100():
    validate_v21_manifest(V21_MANIFEST_DEFINITIONS)
    total = sum(m.macro_weight for m in V21_MANIFEST_DEFINITIONS)
    assert total == 100


def test_v21_no_duplicate_micro_keys_globally():
    assert list_v21_duplicate_micro_keys(V21_MANIFEST_DEFINITIONS) == []


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


def test_v21_duplicate_error_message_includes_macros():
    dup_key = "shared_key"
    defs = (
        V21MacroAreaSpec(
            key="player_layer",
            label="Player layer",
            macro_weight=50,
            micros=(V21MicroSpec(key=dup_key, label="Assenza dei top shooter", micro_weight=100, source_path="a"),),
        ),
        V21MacroAreaSpec(
            key="injuries_unavailable",
            label="Infortuni / indisponibili",
            macro_weight=50,
            micros=(V21MicroSpec(key=dup_key, label="Assenza top shooter", micro_weight=100, source_path="b"),),
        ),
    )
    duplicates = find_v21_duplicate_micro_keys(defs)
    msg = format_v21_duplicate_micro_keys_error(duplicates)
    assert "shared_key" in msg
    assert "Player layer" in msg
    assert "Assenza dei top shooter" in msg
    assert "Infortuni / indisponibili" in msg
    assert "Assenza top shooter" in msg
    with pytest.raises(ValueError, match="Player layer"):
        validate_v21_manifest(defs)


def test_v21_renamed_top_shooter_keys_present():
    player = next(m for m in V21_MANIFEST_DEFINITIONS if m.key == "player_layer")
    injuries = next(m for m in V21_MANIFEST_DEFINITIONS if m.key == "injuries_unavailable")
    player_keys = {m.key for m in player.micros}
    injury_keys = {m.key for m in injuries.micros}
    assert "player_layer_top_shooter_absence" in player_keys
    assert "injuries_top_shooter_absence" in injury_keys
    assert "top_shooter_absence" not in player_keys
    assert "top_shooter_absence" not in injury_keys
