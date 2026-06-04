"""Gestione dati insufficienti e divisione per zero."""

from __future__ import annotations

from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA, WARNING_ZERO_MATCHES
from app.services.cecchino.cecchino_engine import (
    CecchinoCalculationInput,
    WDLRecord,
    build_full_cecchino_output,
    compute_picchetto,
)


def test_empty_records_no_crash():
    empty = WDLRecord(0, 0, 0)
    block = compute_picchetto("home_away", empty, empty)
    assert block.status == STATUS_INSUFFICIENT_DATA
    assert block.outcome_1 is None or block.outcome_1.quota is None
    assert WARNING_ZERO_MATCHES in block.warnings


def test_full_pipeline_empty():
    inp = CecchinoCalculationInput(
        home_away=(WDLRecord(0, 0, 0), WDLRecord(0, 0, 0)),
        totals=(WDLRecord(0, 0, 0), WDLRecord(0, 0, 0)),
        last5_home_away=(WDLRecord(0, 0, 0), WDLRecord(0, 0, 0)),
        last6_totals=(WDLRecord(0, 0, 0), WDLRecord(0, 0, 0)),
    )
    out = build_full_cecchino_output(inp)
    assert out.status == STATUS_INSUFFICIENT_DATA
    assert out.final.status == STATUS_INSUFFICIENT_DATA
