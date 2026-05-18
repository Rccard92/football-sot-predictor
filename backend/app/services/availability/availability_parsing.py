"""Parse risposte API-Football injuries → record normalizzati."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

SOURCE_INJURIES = "api_football_injuries"


@dataclass
class ParsedAvailabilityRecord:
    api_player_id: int | None
    player_name: str
    api_team_id: int | None
    team_name: str | None
    api_fixture_id: int | None
    availability_status: str
    availability_type: str | None
    reason: str | None
    reported_at: datetime | None
    start_date: Any
    end_date: Any
    source: str
    raw_json: dict[str, Any]


def _norm_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    s = str(reason).strip()
    if not s:
        return None
    return s[:512]


def _map_status_type(api_type: str | None, reason: str | None) -> tuple[str, str | None]:
    t = (api_type or "").strip().lower()
    r = (reason or "").strip().lower()

    if "suspension" in t or "yellow card" in t or "red card" in t or "suspended" in t:
        return "suspended", "suspension"
    if "doubt" in t or "doubtful" in t:
        return "doubtful", "injury" if "injur" in r or "muscle" in r or "knee" in r else "other"
    if "missing fixture" in t or "not available" in t:
        return "out", "injury" if "injur" in r or not r else "other"
    if "injur" in t or "injury" in r or "muscle" in r or "knee" in r or "hamstring" in r:
        return "injured", "injury"
    if "illness" in t or "ill" in r:
        return "out", "illness"
    if "personal" in t:
        return "unavailable", "personal"
    if t:
        return "out", t[:32]
    return "unknown", "other"


def _parse_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_injuries_item(item: dict[str, Any]) -> ParsedAvailabilityRecord | None:
    if not isinstance(item, dict):
        return None
    pl = item.get("player")
    if not isinstance(pl, dict):
        return None
    name = str(pl.get("name") or "").strip()
    if not name:
        return None

    api_pid = pl.get("id")
    try:
        api_player_id = int(api_pid) if api_pid is not None else None
    except (TypeError, ValueError):
        api_player_id = None

    tm = item.get("team") if isinstance(item.get("team"), dict) else {}
    api_team_id = None
    team_name = None
    try:
        if tm.get("id") is not None:
            api_team_id = int(tm["id"])
    except (TypeError, ValueError):
        pass
    if tm.get("name"):
        team_name = str(tm["name"])[:255]

    fx = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
    api_fixture_id = None
    reported_at = None
    try:
        if fx.get("id") is not None:
            api_fixture_id = int(fx["id"])
    except (TypeError, ValueError):
        pass
    reported_at = _parse_datetime(fx.get("date"))

    raw_type = item.get("type")
    if isinstance(raw_type, dict):
        raw_type = raw_type.get("type")
    api_type = str(raw_type) if raw_type is not None else None
    reason_raw = item.get("reason")
    if reason_raw is None and isinstance(pl.get("reason"), str):
        reason_raw = pl.get("reason")
    reason = _norm_reason(str(reason_raw) if reason_raw is not None else None)
    status, atype = _map_status_type(api_type, reason)

    return ParsedAvailabilityRecord(
        api_player_id=api_player_id,
        player_name=name[:255],
        api_team_id=api_team_id,
        team_name=team_name,
        api_fixture_id=api_fixture_id,
        availability_status=status,
        availability_type=atype,
        reason=reason,
        reported_at=reported_at,
        start_date=None,
        end_date=None,
        source=SOURCE_INJURIES,
        raw_json=item,
    )
