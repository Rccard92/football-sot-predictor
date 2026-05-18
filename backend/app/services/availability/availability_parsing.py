"""Parse risposte API-Football injuries → record normalizzati."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

SOURCE_INJURIES = "api_football_injuries"


@dataclass
class ParsedAvailabilityRecord:
    api_player_id: int | None
    player_name: str
    api_team_id: int | None
    team_name: str | None
    api_fixture_id: int | None
    fixture_date: date | None
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


def _extract_type_reason(item: dict[str, Any], pl: dict[str, Any]) -> tuple[str | None, str | None]:
    """Priorità: player.type / player.reason, poi root type / reason."""
    raw_type = pl.get("type")
    if raw_type is None:
        raw_type = item.get("type")
    if isinstance(raw_type, dict):
        raw_type = raw_type.get("type")

    reason_raw = pl.get("reason")
    if reason_raw is None:
        reason_raw = item.get("reason")

    api_type = str(raw_type).strip() if raw_type is not None else None
    reason = _norm_reason(str(reason_raw) if reason_raw is not None else None)
    return api_type or None, reason


def _map_status_type(api_type: str | None, reason: str | None) -> tuple[str, str | None]:
    combined = f"{api_type or ''} {reason or ''}".strip().lower()
    t = (api_type or "").strip().lower()
    r = (reason or "").strip().lower()

    suspension_markers = (
        "suspension",
        "suspended",
        "yellow card",
        "red card",
        "cards",
        "squalifica",
        "squalificato",
        "ban",
        "accumulation",
    )
    if any(m in combined for m in suspension_markers):
        return "suspended", "suspension"

    if "doubt" in combined or "doubtful" in combined:
        return "doubtful", "injury" if any(x in r for x in ("injur", "muscle", "knee")) else "other"
    if "missing fixture" in combined or "not available" in combined:
        return "out", "injury" if any(x in r for x in ("injur", "muscle", "knee")) or not r else "other"
    injury_markers = ("injur", "injured", "muscle", "knee", "ankle", "hamstring", "groin", "calf")
    if any(m in combined for m in injury_markers):
        return "injured" if "injured" in combined else "out", "injury"
    if "illness" in combined or "ill" in r:
        return "out", "illness"
    if "personal" in combined:
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
    fixture_date: date | None = None
    if reported_at is not None:
        fixture_date = reported_at.date()

    api_type, reason = _extract_type_reason(item, pl)
    status, atype = _map_status_type(api_type, reason)

    return ParsedAvailabilityRecord(
        api_player_id=api_player_id,
        player_name=name[:255],
        api_team_id=api_team_id,
        team_name=team_name,
        api_fixture_id=api_fixture_id,
        fixture_date=fixture_date,
        availability_status=status,
        availability_type=atype,
        reason=reason,
        reported_at=reported_at,
        start_date=None,
        end_date=None,
        source=SOURCE_INJURIES,
        raw_json=item,
    )
