"""Estrae campi nullable da `statistics` nel payload /fixtures/players (per giocatore)."""

from __future__ import annotations

from typing import Any

from app.services.player_data.api_player_parsing import (
    parse_bool_nullable,
    parse_float_nullable,
    parse_int_nullable,
    parse_percent_nullable,
)

# Campi inclusi in missing_fields_summary (valore None dopo il parse).
MISSING_SUMMARY_FIELDS: tuple[str, ...] = (
    "minutes",
    "position",
    "rating",
    "shots_total",
    "shots_on",
    "goals_total",
    "goals_assists",
    "passes_total",
    "passes_key",
    "passes_accuracy",
)


def _looks_like_nested_v3(first: dict[str, Any]) -> bool:
    if "games" in first and isinstance(first.get("games"), dict):
        return True
    if isinstance(first.get("shots"), dict):
        return True
    return False


def _is_flat_type_value(first: dict[str, Any]) -> bool:
    return isinstance(first, dict) and "type" in first and "value" in first


_FLAT_TO_FIELD: dict[str, str] = {
    "rating": "rating",
    "position": "position",
    "minutes played": "minutes",
    "total shots": "shots_total",
    "shots total": "shots_total",
    "shots on goal": "shots_on",
    "shots on target": "shots_on",
    "on target": "shots_on",
    "goals": "goals_total",
    "assists": "goals_assists",
    "total passes": "passes_total",
    "key passes": "passes_key",
    "passes %": "passes_accuracy",
    "passes accuracy": "passes_accuracy",
    "dribbles": "dribbles_attempts",
    "successful dribbles": "dribbles_success",
    "dribble succes": "dribbles_success",
    "fouls drawn": "fouls_drawn",
    "fouls committed": "fouls_committed",
    "yellow cards": "cards_yellow",
    "red cards": "cards_red",
    "penalty scored": "penalty_scored",
    "penalty miss": "penalty_missed",
    "penalty misses": "penalty_missed",
    "penalty won": "penalty_won",
}


def _empty_row() -> dict[str, Any]:
    return {
        "minutes": None,
        "position": None,
        "rating": None,
        "substitute": None,
        "shots_total": None,
        "shots_on": None,
        "goals_total": None,
        "goals_assists": None,
        "passes_total": None,
        "passes_key": None,
        "passes_accuracy": None,
        "dribbles_attempts": None,
        "dribbles_success": None,
        "fouls_drawn": None,
        "fouls_committed": None,
        "cards_yellow": None,
        "cards_red": None,
        "penalty_scored": None,
        "penalty_missed": None,
        "penalty_won": None,
    }


def _parse_nested_v3(s0: dict[str, Any]) -> dict[str, Any]:
    out = _empty_row()
    games = s0.get("games") if isinstance(s0.get("games"), dict) else {}
    out["minutes"] = parse_int_nullable(games.get("minutes"))
    pos = games.get("position")
    if pos is not None:
        ps = str(pos).strip()
        out["position"] = ps[:255] if ps else None
    out["rating"] = parse_float_nullable(games.get("rating"))
    out["substitute"] = parse_bool_nullable(games.get("substitute"))

    shots = s0.get("shots") if isinstance(s0.get("shots"), dict) else {}
    out["shots_total"] = parse_int_nullable(shots.get("total"))
    out["shots_on"] = parse_int_nullable(shots.get("on"))

    goals = s0.get("goals") if isinstance(s0.get("goals"), dict) else {}
    out["goals_total"] = parse_int_nullable(goals.get("total"))
    out["goals_assists"] = parse_int_nullable(goals.get("assists"))

    passes = s0.get("passes") if isinstance(s0.get("passes"), dict) else {}
    out["passes_total"] = parse_int_nullable(passes.get("total"))
    out["passes_key"] = parse_int_nullable(passes.get("key"))
    out["passes_accuracy"] = parse_percent_nullable(passes.get("accuracy"))

    dribbles = s0.get("dribbles") if isinstance(s0.get("dribbles"), dict) else {}
    out["dribbles_attempts"] = parse_int_nullable(dribbles.get("attempts"))
    out["dribbles_success"] = parse_int_nullable(dribbles.get("success"))

    fouls = s0.get("fouls") if isinstance(s0.get("fouls"), dict) else {}
    out["fouls_drawn"] = parse_int_nullable(fouls.get("drawn"))
    out["fouls_committed"] = parse_int_nullable(fouls.get("committed"))

    cards = s0.get("cards") if isinstance(s0.get("cards"), dict) else {}
    out["cards_yellow"] = parse_int_nullable(cards.get("yellow"))
    out["cards_red"] = parse_int_nullable(cards.get("red"))

    pen = s0.get("penalty") if isinstance(s0.get("penalty"), dict) else {}
    pens = s0.get("penalties") if isinstance(s0.get("penalties"), dict) else {}
    src = pen if pen else pens
    out["penalty_scored"] = parse_int_nullable(src.get("scored"))
    out["penalty_missed"] = parse_int_nullable(src.get("missed"))
    out["penalty_won"] = parse_int_nullable(src.get("won"))

    return out


def _parse_flat_list(statistics: list[dict[str, Any]]) -> dict[str, Any]:
    out = _empty_row()
    for item in statistics:
        t_raw = item.get("type")
        if t_raw is None:
            continue
        t = str(t_raw).strip().lower()
        key = _FLAT_TO_FIELD.get(t)
        if not key:
            continue
        v = item.get("value")
        if key == "rating":
            out["rating"] = parse_float_nullable(v)
        elif key == "passes_accuracy":
            out["passes_accuracy"] = parse_percent_nullable(v)
        elif key == "minutes":
            out["minutes"] = parse_int_nullable(v)
        elif key == "position" and v is not None:
            ps = str(v).strip()
            out["position"] = ps[:255] if ps else None
        elif key == "substitute":
            out["substitute"] = parse_bool_nullable(v)
        elif key in (
            "shots_total",
            "shots_on",
            "goals_total",
            "goals_assists",
            "passes_total",
            "passes_key",
            "dribbles_attempts",
            "dribbles_success",
            "fouls_drawn",
            "fouls_committed",
            "cards_yellow",
            "cards_red",
            "penalty_scored",
            "penalty_missed",
            "penalty_won",
        ):
            out[key] = parse_int_nullable(v)
    return out


def extract_statistics_row_nullable(statistics: list[dict[str, Any]] | None) -> dict[str, Any]:
    """
    Unifica formato annidato v3 e lista piatta {type, value}.
    Ritorna dict con tutte le chiavi di _empty_row().
    """
    if not statistics:
        return _empty_row()
    first = statistics[0]
    if not isinstance(first, dict):
        return _empty_row()
    if _looks_like_nested_v3(first):
        return _parse_nested_v3(first)
    if _is_flat_type_value(first):
        return _parse_flat_list([x for x in statistics if isinstance(x, dict)])
    return _empty_row()


def bump_missing_summary(missing_summary: dict[str, int], parsed: dict[str, Any]) -> None:
    for k in MISSING_SUMMARY_FIELDS:
        if parsed.get(k) is None:
            missing_summary[k] = missing_summary.get(k, 0) + 1
