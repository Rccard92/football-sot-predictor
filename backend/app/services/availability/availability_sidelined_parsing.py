"""Parse risposte API-Football sidelined."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.services.availability.availability_parsing import _map_status_type, _norm_reason


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def parse_sidelined_entries(
    items: list[dict[str, Any]],
    *,
    api_player_id: int,
    player_name: str,
    api_team_id: int | None,
    team_name: str | None,
) -> list[dict[str, Any]]:
    """Espande lista sidelined in dict normalizzati per candidato."""
    out: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        start = _parse_date(raw.get("start"))
        end = _parse_date(raw.get("end"))
        typ = raw.get("type")
        reason = _norm_reason(str(typ) if typ is not None else None)
        status, atype = _map_status_type(str(typ) if typ else None, reason)
        out.append(
            {
                "api_player_id": api_player_id,
                "player_name": player_name,
                "api_team_id": api_team_id,
                "team_name": team_name,
                "start_date": start,
                "end_date": end,
                "availability_status": status,
                "availability_type": atype,
                "reason": reason or (str(typ) if typ else None),
                "raw_json": raw,
            },
        )
    return out
