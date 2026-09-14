"""Test della configurazione delle fasi V3."""

from __future__ import annotations

from app.services.cecchino_v3.constants import PHASE_BASELINE, PHASE_FEATURES, PHASES


def test_final_phase_is_reference_model_plus_lockbox_only():
    assert 9 in PHASES and 9 not in PHASE_BASELINE
    final, reference = PHASE_FEATURES[9], PHASE_FEATURES[4]
    assert final.lockbox and not reference.lockbox
    assert (final.game, final.form, final.calendar, final.discipline, final.promotion, final.calibration) == (
        reference.game,
        reference.form,
        reference.calendar,
        reference.discipline,
        reference.promotion,
        reference.calibration,
    )
    assert not any(PHASE_FEATURES[p].lockbox for p in PHASES if p != 9)
