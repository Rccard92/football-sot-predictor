"""Filtri fixture Cecchino Today (non iniziate)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.constants import SCHEDULED_STATUSES


def _parse_kickoff(item: dict[str, Any]) -> datetime | None:
    fx = item.get("fixture") or {}
    raw = fx.get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def is_fixture_not_started(item: dict[str, Any], now: datetime) -> bool:
    fx = item.get("fixture") or {}
    status_obj = fx.get("status") or {}
    short = str(status_obj.get("short") or "NS").upper()
    if short not in SCHEDULED_STATUSES:
        return False
    if short in ("CANC", "ABD", "AWD", "WO"):
        return False
    kickoff = _parse_kickoff(item)
    if kickoff is None:
        return short in ("NS", "TBD", "PST")
    return kickoff > now
