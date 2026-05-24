"""Costanti e helper condivisi per monitoraggio giocate (no dipendenze tra refresh e dashboard)."""

from __future__ import annotations

from app.core.constants import FINISHED_STATUSES, LIVE_STATUSES, SCHEDULED_STATUSES
from app.models.tracked_betting_pick import STATUS_LIVE

PENDING_STATUSES = frozenset({"NS", "TBD", "PST"})
VOID_STATUSES = frozenset({"CANC", "ABD", "AWD", "WO"})

__all__ = [
    "FINISHED_STATUSES",
    "LIVE_STATUSES",
    "SCHEDULED_STATUSES",
    "PENDING_STATUSES",
    "VOID_STATUSES",
    "is_live_status",
    "is_finished_status",
    "is_pending_status",
    "is_live_fixture",
    "sot_display_and_reason",
]


def _normalize_status(status: str | None) -> str:
    return (status or "").strip().upper()


def is_live_status(status: str | None) -> bool:
    return _normalize_status(status) in LIVE_STATUSES


def is_finished_status(status: str | None) -> bool:
    return _normalize_status(status) in FINISHED_STATUSES


def is_pending_status(status: str | None) -> bool:
    st = _normalize_status(status)
    return st in PENDING_STATUSES or st == ""


def is_live_fixture(pick_status: str, fixture_status: str | None) -> bool:
    return pick_status == STATUS_LIVE or is_live_status(fixture_status)


def sot_display_and_reason(
    *,
    fixture_status: str | None,
    pick_status: str,
    result_home_sot: float | None,
    result_away_sot: float | None,
    result_total_sot: float | None,
) -> tuple[str, str | None]:
    fs = _normalize_status(fixture_status)
    is_live = is_live_fixture(pick_status, fs)
    is_finished = is_finished_status(fs)
    is_scheduled = fs in SCHEDULED_STATUSES or fs in PENDING_STATUSES

    if is_scheduled and not is_live:
        return "—", None

    if result_total_sot is not None:
        h = int(result_home_sot) if result_home_sot is not None else "—"
        a = int(result_away_sot) if result_away_sot is not None else "—"
        total = result_total_sot
        total_str = str(int(total)) if total == int(total) else f"{total:.1f}"
        return f"{h} + {a} = {total_str}", None

    if is_live:
        return (
            "SOT non disponibili",
            "API-Sports non ha restituito i tiri in porta per questo aggiornamento.",
        )
    if is_finished:
        return "N/D", "SOT finali non disponibili da API-Sports"
    return "—", None
