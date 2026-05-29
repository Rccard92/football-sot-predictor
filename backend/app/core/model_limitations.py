"""Limitazioni del modello baseline SOT (solo metadati API, non logica predittiva)."""

from __future__ import annotations

from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)

MODEL_LIMITATIONS_NOTE_IT = (
    "Questa versione baseline usa solo statistiche squadra storiche. "
    "Formazioni, assenze e quote bookmaker automatiche non sono ancora considerate."
)

V21_LIMITATIONS_NOTE_IT = (
    "La v2.1 usa macroaree pesate e traccia formazioni/indisponibili quando disponibili. "
    "Le formazioni SportAPI sono probabili, non ufficiali."
)

V20_LIMITATIONS_NOTE_IT = (
    "La v2.0 incorpora l'impatto delle formazioni probabili SportAPI e indisponibilità quando disponibili. "
    "Le formazioni SportAPI sono probabili, non ufficiali."
)


def default_model_limitations_dict() -> dict[str, str | bool]:
    return {
        "lineups_considered": False,
        "injuries_considered": False,
        "odds_automatically_imported": False,
        "note": MODEL_LIMITATIONS_NOTE_IT,
    }


def _lineups_tracked(lineup_coverage: dict[str, Any] | None) -> bool:
    if not isinstance(lineup_coverage, dict):
        return False
    pct = lineup_coverage.get("next_round_coverage_pct")
    if pct is not None and float(pct) > 0:
        return True
    for key in ("next_round_sportapi_lineups_count", "probable_lineups_count", "confirmed_lineups_count"):
        count = lineup_coverage.get(key)
        if count is not None and int(count) > 0:
            return True
    return False


def model_limitations_for_version(
    model_version: str,
    *,
    lineup_coverage: dict[str, Any] | None = None,
) -> dict[str, str | bool]:
    tracked = _lineups_tracked(lineup_coverage)
    if model_version == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS:
        return {
            "lineups_considered": tracked,
            "injuries_considered": tracked,
            "odds_automatically_imported": False,
            "note": V21_LIMITATIONS_NOTE_IT,
        }
    if model_version == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT:
        return {
            "lineups_considered": tracked,
            "injuries_considered": tracked,
            "odds_automatically_imported": False,
            "note": V20_LIMITATIONS_NOTE_IT,
        }
    return default_model_limitations_dict()
