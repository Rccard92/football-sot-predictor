"""Test selection keys Fase 1 Acquistabilità V3.1."""

from __future__ import annotations

import app.services.cecchino.cecchino_selection_keys as keys


def test_phase1_selection_constants_exist():
    assert keys.SEL_UNDER_1_5 == "UNDER_1_5"
    assert keys.SEL_OVER_3_5 == "OVER_3_5"
    assert keys.SEL_UNDER_PT_0_5 == "UNDER_PT_0_5"
    assert keys.SEL_HOME_PT == "HOME_PT"
    assert keys.SEL_AWAY_PT == "AWAY_PT"
    assert keys.SEL_DRAW_PT == "DRAW_PT"


def test_no_selection_key_collisions():
    vals = [
        v
        for k, v in vars(keys).items()
        if k.startswith("SEL_") and isinstance(v, str)
    ]
    assert len(vals) == len(set(vals))
