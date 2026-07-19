"""Compatibility adapter — Equilibrio vs Squilibrio legacy.

Tutte le formule vivono in cecchino_balance_v5.py.
Questo modulo re-esporta solo il contratto consumato da:
- Signals Matrix (compute_dominance_pp)
- ICM / Today / KPI debug / Credibilità X dataset (build_* / VERSION)

Rimozione futura: possibile solo quando nessun consumer importa più questo path.
"""

from __future__ import annotations

from app.services.cecchino.cecchino_balance_v5 import (
    LEGACY_VERSION as VERSION,
    build_balance_analysis_from_final,
    build_cecchino_balance_analysis,
    build_legacy_balance_analysis,
    compute_dominance_pp,
)

__all__ = [
    "VERSION",
    "compute_dominance_pp",
    "build_cecchino_balance_analysis",
    "build_balance_analysis_from_final",
    "build_legacy_balance_analysis",
]
