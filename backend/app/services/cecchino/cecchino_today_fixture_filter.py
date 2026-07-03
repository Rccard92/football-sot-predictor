"""Filtri fixture Cecchino Today (non iniziate)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.constants import SCHEDULED_STATUSES
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat


def _parse_kickoff(item: dict[str, Any]) -> datetime | None:
    fx = item.get("fixture") or {}
    raw = fx.get("date")
    if not raw:
        return None
    return ensure_datetime_utc(raw, field_name="fixture.date")


def get_fixture_local_date(api_item: dict[str, Any], timezone_str: str) -> date | None:
    """Data locale del kickoff nella timezone della scansione."""
    kickoff_utc = _parse_kickoff(api_item)
    if kickoff_utc is None:
        return None
    return kickoff_utc.astimezone(ZoneInfo(timezone_str)).date()


def fixture_belongs_to_scan_date(
    api_item: dict[str, Any],
    scan_date: date,
    timezone_str: str,
) -> tuple[bool, dict[str, Any]]:
    """Gate locale: la fixture appartiene allo scan_date solo se kickoff locale coincide."""
    kickoff_utc = _parse_kickoff(api_item)
    fixture_local_date = get_fixture_local_date(api_item, timezone_str)
    base: dict[str, Any] = {
        "scan_date": scan_date.isoformat(),
        "fixture_local_date": fixture_local_date.isoformat() if fixture_local_date else None,
        "fixture_utc": safe_isoformat(kickoff_utc, field_name="fixture.date") if kickoff_utc else None,
        "timezone": timezone_str,
    }
    if fixture_local_date is None:
        return False, {**base, "belongs": False, "reason": "fixture_kickoff_unparseable"}
    if fixture_local_date == scan_date:
        return True, {**base, "belongs": True, "reason": "same_local_date"}
    return False, {**base, "belongs": False, "reason": "fixture_out_of_scan_date"}


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
