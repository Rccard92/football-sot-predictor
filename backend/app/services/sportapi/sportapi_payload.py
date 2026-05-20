"""Estrazione campi da payload SportAPI (strutture annidate)."""

from __future__ import annotations

from typing import Any


def _as_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def extract_events_list(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [e for e in body if isinstance(e, dict)]
    if not isinstance(body, dict):
        return []
    for key in ("events", "response", "data", "items"):
        val = body.get(key)
        if isinstance(val, list):
            return [e for e in val if isinstance(e, dict)]
    event = body.get("event")
    if isinstance(event, dict):
        return [event]
    return []


def is_football_event(ev: dict[str, Any]) -> bool:
    sport = ev.get("sport") or ev.get("category")
    if isinstance(sport, dict):
        slug = str(sport.get("slug") or sport.get("name") or "").lower()
        if slug and "football" not in slug and "soccer" not in slug:
            return False
    elif isinstance(sport, str):
        s = sport.lower()
        if s and "football" not in s and "soccer" not in s:
            return False
    return True


def event_id(ev: dict[str, Any]) -> int | None:
    for key in ("id", "eventId", "event_id"):
        v = ev.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return None


def event_start_timestamp(ev: dict[str, Any]) -> int | None:
    for key in ("startTimestamp", "start_timestamp", "timestamp"):
        v = ev.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    fixture = _as_dict(ev.get("fixture"))
    for key in ("startTimestamp", "timestamp"):
        v = fixture.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return None


def event_home_away_names(ev: dict[str, Any]) -> tuple[str, str]:
    home = _as_dict(ev.get("homeTeam") or ev.get("home_team") or ev.get("home"))
    away = _as_dict(ev.get("awayTeam") or ev.get("away_team") or ev.get("away"))
    hn = str(home.get("name") or home.get("shortName") or "")
    an = str(away.get("name") or away.get("shortName") or "")
    return hn, an


def event_tournament_info(ev: dict[str, Any]) -> dict[str, Any]:
    t = _as_dict(ev.get("tournament"))
    ut = _as_dict(t.get("uniqueTournament") or t.get("unique_tournament"))
    season = _as_dict(ev.get("season") or t.get("season"))
    ri = _as_dict(ev.get("roundInfo") or ev.get("round_info"))
    country = _as_dict(t.get("country") or ut.get("country"))
    return {
        "tournament_name": str(t.get("name") or ""),
        "tournament_id": t.get("id"),
        "unique_tournament_id": ut.get("id"),
        "season_id": season.get("id"),
        "season_name": str(season.get("name") or ""),
        "round": ri.get("round"),
        "country": str(country.get("name") or country.get("alpha2") or ""),
    }


def event_team_ids(ev: dict[str, Any]) -> tuple[int | None, int | None]:
    home = _as_dict(ev.get("homeTeam") or ev.get("home"))
    away = _as_dict(ev.get("awayTeam") or ev.get("away"))
    hid = home.get("id")
    aid = away.get("id")
    try:
        hi = int(hid) if hid is not None else None
    except (TypeError, ValueError):
        hi = None
    try:
        ai = int(aid) if aid is not None else None
    except (TypeError, ValueError):
        ai = None
    return hi, ai


def lineups_block(body: Any) -> dict[str, Any]:
    if isinstance(body, dict):
        if "lineups" in body:
            return _as_dict(body.get("lineups"))
        if "home" in body or "away" in body:
            return body
        inner = body.get("event") or body.get("data")
        if isinstance(inner, dict) and "lineups" in inner:
            return _as_dict(inner.get("lineups"))
    return {}


def side_block(lineups: dict[str, Any], side: str) -> dict[str, Any]:
    return _as_dict(lineups.get(side))


def players_from_side(side: dict[str, Any]) -> list[dict[str, Any]]:
    players = side.get("players")
    if isinstance(players, list):
        return [p for p in players if isinstance(p, dict)]
    return []


def missing_from_side(side: dict[str, Any]) -> list[dict[str, Any]]:
    mp = side.get("missingPlayers") or side.get("missing_players")
    if isinstance(mp, list):
        return [p for p in mp if isinstance(p, dict)]
    return []


def player_display_name(p: dict[str, Any]) -> str:
    pl = _as_dict(p.get("player"))
    if pl:
        return str(pl.get("name") or pl.get("shortName") or pl.get("slug") or "Unknown")
    return str(p.get("name") or p.get("shortName") or "Unknown")


def player_id_from_row(p: dict[str, Any]) -> int | None:
    pl = _as_dict(p.get("player"))
    for key in ("id", "playerId"):
        v = pl.get(key) if pl else p.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return None
