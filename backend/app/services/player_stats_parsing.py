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


def _int_summable(val: Any) -> int:
    """Intero per campi sommabili: None / assente → 0."""
    n = _parse_int(val)
    return n if n is not None else 0


def _nested_statistics_v3_to_fields(statistics: list[dict[str, Any]]) -> dict[str, Any]:
    """Path API-Sports tipico: statistics[0] con games, shots, goals, …"""
    out: dict[str, Any] = {}
    if not statistics or not isinstance(statistics[0], dict):
        return out
    s0 = statistics[0]
    games = s0.get("games") if isinstance(s0.get("games"), dict) else {}

    m = _parse_int(games.get("minutes"))
    if m is not None:
        out["minutes"] = m

    pos = games.get("position")
    if pos is not None:
        ps = str(pos).strip()
        if ps:
            out["position"] = ps[:32]

    r = _parse_float(games.get("rating"))
    if r is not None:
        out["rating"] = r

    cap = _parse_bool(games.get("captain"))
    if cap is not None:
        out["captain"] = cap
    sub = _parse_bool(games.get("substitute"))
    if sub is not None:
        out["substitute"] = sub

    shots = s0.get("shots") if isinstance(s0.get("shots"), dict) else {}
    out["shots_total"] = _int_summable(shots.get("total"))
    out["shots_on_target"] = _int_summable(shots.get("on"))

    goals = s0.get("goals") if isinstance(s0.get("goals"), dict) else {}
    out["goals"] = _int_summable(goals.get("total"))
    out["assists"] = _int_summable(goals.get("assists"))

    passes = s0.get("passes") if isinstance(s0.get("passes"), dict) else {}
    out["passes_total"] = _int_summable(passes.get("total"))
    out["passes_key"] = _int_summable(passes.get("key"))
    acc = passes.get("accuracy")
    acc_f = _parse_float(acc)
    if acc_f is not None:
        out["passes_accuracy_pct"] = acc_f

    tackles = s0.get("tackles") if isinstance(s0.get("tackles"), dict) else {}
    out["tackles_total"] = _int_summable(tackles.get("total"))
    out["tackles_blocks"] = _int_summable(tackles.get("blocks"))
    out["interceptions"] = _int_summable(tackles.get("interceptions"))

    duels = s0.get("duels") if isinstance(s0.get("duels"), dict) else {}
    out["duels_total"] = _int_summable(duels.get("total"))
    out["duels_won"] = _int_summable(duels.get("won"))

    dribbles = s0.get("dribbles") if isinstance(s0.get("dribbles"), dict) else {}
    out["dribbles_attempts"] = _int_summable(dribbles.get("attempts"))
    out["dribbles_success"] = _int_summable(dribbles.get("success"))

    fouls = s0.get("fouls") if isinstance(s0.get("fouls"), dict) else {}
    out["fouls_drawn"] = _int_summable(fouls.get("drawn"))
    out["fouls_committed"] = _int_summable(fouls.get("committed"))

    cards = s0.get("cards") if isinstance(s0.get("cards"), dict) else {}
    out["yellow_cards"] = _int_summable(cards.get("yellow"))
    out["red_cards"] = _int_summable(cards.get("red"))

    return out


def _is_flat_type_value_statistics(statistics: list[dict[str, Any]]) -> bool:
    if not statistics:
        return False
    first = statistics[0]
    if not isinstance(first, dict):
        return False
    return "type" in first and "value" in first


def _looks_like_nested_v3_block(first: dict[str, Any]) -> bool:
    if "games" in first and isinstance(first.get("games"), dict):
        return True
    if isinstance(first.get("shots"), dict):
        return True
    if isinstance(first.get("passes"), dict):
        return True
    return False


def parse_fixture_player_statistics(statistics: list[dict[str, Any]] | None) -> dict[str, Any]:
    """
    Unifica parsing risposta /fixtures/players per giocatore.
    - Formato v3: primo elemento con blocchi annidati (games, shots, …).
    - Formato legacy: lista di {type, value}.
    """
    if not statistics:
        return {}
    first = statistics[0]
    if isinstance(first, dict) and _looks_like_nested_v3_block(first):
        return _nested_statistics_v3_to_fields(statistics)
    if _is_flat_type_value_statistics(statistics):
        return statistics_list_to_player_fields(statistics)
    return {}


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
