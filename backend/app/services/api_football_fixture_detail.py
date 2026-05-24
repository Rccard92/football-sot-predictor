"""Parsing dettaglio fixture da API-Football GET /fixtures?id="""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_fixture_detail_item(item: dict[str, Any]) -> dict[str, Any]:
    """Estrae campi richiesti da un elemento response /fixtures."""
    fx = item.get("fixture") or {}
    teams = item.get("teams") or {}
    league = item.get("league") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    status_obj = fx.get("status") or {}

    referee_raw = fx.get("referee")
    referee = str(referee_raw).strip() if referee_raw else None
    if referee == "":
        referee = None

    kickoff = _parse_dt(fx.get("date"))
    ts = fx.get("timestamp")
    try:
        timestamp = int(ts) if ts is not None else None
    except (TypeError, ValueError):
        timestamp = None

    return {
        "api_fixture_id": int(fx["id"]) if fx.get("id") is not None else None,
        "referee": referee,
        "date": fx.get("date"),
        "kickoff_at": kickoff,
        "timestamp": timestamp,
        "status_short": str(status_obj.get("short") or ""),
        "status_long": status_obj.get("long"),
        "league_api_id": int(league["id"]) if league.get("id") is not None else None,
        "season_year": int(league["season"]) if league.get("season") is not None else None,
        "home_team_name": str(home.get("name") or "").strip(),
        "away_team_name": str(away.get("name") or "").strip(),
        "home_team_api_id": int(home["id"]) if home.get("id") is not None else None,
        "away_team_api_id": int(away["id"]) if away.get("id") is not None else None,
        "raw_item": item,
    }


def match_label_from_detail(detail: dict[str, Any]) -> str:
    home = detail.get("home_team_name") or "Casa"
    away = detail.get("away_team_name") or "Trasferta"
    return f"{home} - {away}"
