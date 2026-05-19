from __future__ import annotations

from typing import Any

from app.models import PlayerAvailabilityEvent, PlayerSotProfile


def compute_availability_adjustment(
    *,
    top_profiles: list[PlayerSotProfile],
    availability_events: list[PlayerAvailabilityEvent],
) -> tuple[float, dict[str, Any]]:
    """Stub: componente indisponibili disattivata (dati API non affidabili)."""
    _ = top_profiles, availability_events
    return 0.0, {
        "status": "disabled",
        "availability_status": "disabled",
        "applied": False,
        "penalty": 0.0,
        "note": "Componente indisponibili disattivata: dati API non affidabili.",
    }
