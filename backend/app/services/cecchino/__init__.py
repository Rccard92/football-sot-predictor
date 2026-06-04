"""Modulo Cecchino — quote 1X2 da picchetti tecnici (separato da SOT)."""

from app.services.cecchino.cecchino_constants import CECCHINO_VERSION
from app.services.cecchino.cecchino_engine import (
    CecchinoCalculationInput,
    CecchinoCalculationOutput,
    WDLRecord,
    build_full_cecchino_output,
    compute_picchetto,
)
from app.services.cecchino.cecchino_fixture_history import wdl_from_fixtures

__all__ = [
    "CECCHINO_VERSION",
    "CecchinoCalculationInput",
    "CecchinoCalculationOutput",
    "WDLRecord",
    "build_full_cecchino_output",
    "compute_picchetto",
    "wdl_from_fixtures",
]
