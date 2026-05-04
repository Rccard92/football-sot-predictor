"""Estrazione campi numerici da `statistics` API-Football /fixtures/players (per giocatore)."""

from __future__ import annotations

import re
from typing import Any


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _parse_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "-"):
        return None
    m = re.match(r"^([\d.]+)\s*%$", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _parse_bool(val: Any) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "yes", "1", "y"):
        return True
    if s in ("false", "no", "0", "n"):
        return False
    return None


# type string (normalized lower) -> attribute name on FixturePlayerStat
_TYPE_ALIASES: dict[str, str] = {
    "rating": "rating",
    "minutes played": "minutes",
    "goals": "goals",
    "assists": "assists",
    "total shots": "shots_total",
    "shots total": "shots_total",
    "shots on goal": "shots_on_target",
    "shots on target": "shots_on_target",
    "on target": "shots_on_target",
    "key passes": "passes_key",
    "total passes": "passes_total",
    "passes %": "passes_accuracy_pct",
    "passes accuracy": "passes_accuracy_pct",
    "tackles": "tackles_total",
    "blocked shots": "tackles_blocks",
    "interceptions": "interceptions",
    "duels": "duels_total",
    "duels won": "duels_won",
    "dribbles": "dribbles_attempts",
    "successful dribbles": "dribbles_success",
    "dribble succes": "dribbles_success",
    "fouls drawn": "fouls_drawn",
    "fouls committed": "fouls_committed",
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
}


def statistics_list_to_player_fields(
    statistics: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """
    Ritorna dict con chiavi allineate a FixturePlayerStat (esclusi fixture/team/player ids).
    Valori mancanti omessi.
    """
    out: dict[str, Any] = {}
    if not statistics:
        return out

    for item in statistics:
        t_raw = item.get("type")
        if t_raw is None:
            continue
        t = str(t_raw).strip().lower()
        key = _TYPE_ALIASES.get(t)
        if not key:
            continue
        v = item.get("value")
        if key == "rating":
            f = _parse_float(v)
            if f is not None:
                out["rating"] = f
        elif key == "passes_accuracy_pct":
            f = _parse_float(v)
            if f is not None:
                out["passes_accuracy_pct"] = f
        elif key == "minutes":
            n = _parse_int(v)
            if n is not None:
                out["minutes"] = n
        else:
            n = _parse_int(v)
            if n is not None:
                out[key] = n

    return out


def player_entry_flags(player_obj: dict[str, Any], entry: dict[str, Any]) -> tuple[bool | None, bool | None]:
    """(captain, substitute) da payload giocatore."""
    cap = _parse_bool(player_obj.get("captain"))
    if cap is None:
        cap = _parse_bool(entry.get("captain"))
    sub = _parse_bool(player_obj.get("substitute"))
    if sub is None:
        sub = _parse_bool(entry.get("substitute"))
    return cap, sub


def player_position(player_obj: dict[str, Any]) -> str | None:
    pos = player_obj.get("pos") or player_obj.get("position")
    if pos is None:
        return None
    s = str(pos).strip()
    return s[:32] if s else None
