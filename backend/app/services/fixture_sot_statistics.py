"""Estrazione SOT da payload API-Football GET /fixtures/statistics."""

from __future__ import annotations

from typing import Any

from app.services.fixture_team_stats_mapping import _parse_float, statistics_list_to_fields

SOT_FIELD = "shots_on_target"


def parse_sot_stat_value(val: Any) -> float | None:
    """Accetta 5, 5.0, \"5\", \"5.0\"."""
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return float(val)
    if isinstance(val, float):
        return val
    parsed = _parse_float(val)
    if parsed is not None:
        return parsed
    s = str(val).strip()
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _sot_from_block(block: dict[str, Any]) -> float | None:
    parsed = statistics_list_to_fields(block.get("statistics"))
    raw_sot = parsed.get(SOT_FIELD)
    if raw_sot is not None:
        return parse_sot_stat_value(raw_sot)
    for item in block.get("statistics") or []:
        label = " ".join(str(item.get("type") or "").strip().lower().split())
        if label in (
            "shots on goal",
            "shots on target",
            "tiri in porta",
            "on target",
        ):
            v = parse_sot_stat_value(item.get("value"))
            if v is not None:
                return v
    return None


def _team_api_id(block: dict[str, Any]) -> int | None:
    team = block.get("team") or {}
    tid = team.get("id")
    if tid is None:
        return None
    try:
        return int(tid)
    except (TypeError, ValueError):
        return None


def extract_sot_from_statistics_response(
    stats_blocks: list[dict],
    *,
    home_team_id: int,
    away_team_id: int,
    home_api_team_id: int | None,
    away_api_team_id: int | None,
) -> dict[str, Any]:
    """
    Estrae home/away/total SOT da blocchi statistics API-Football.

    Match: prima per api_team_id; se esattamente 2 blocchi e manca un lato, fallback ordine (0=home, 1=away).
    """
    blocks = [b for b in (stats_blocks or []) if isinstance(b, dict)]
    labels_seen: list[str] = []
    for block in blocks:
        for item in block.get("statistics") or []:
            t = str(item.get("type") or "").strip()
            if t and t not in labels_seen:
                labels_seen.append(t)

    home_sot: float | None = None
    away_sot: float | None = None
    match_method: str | None = None
    matched_home = False
    matched_away = False

    for block in blocks:
        api_id = _team_api_id(block)
        sot = _sot_from_block(block)
        if sot is None:
            continue
        if home_api_team_id is not None and api_id == home_api_team_id:
            home_sot = sot
            matched_home = True
            match_method = "api_team_id"
        elif away_api_team_id is not None and api_id == away_api_team_id:
            away_sot = sot
            matched_away = True
            match_method = "api_team_id"

    if len(blocks) == 2 and (home_sot is None or away_sot is None):
        first_sot = _sot_from_block(blocks[0])
        second_sot = _sot_from_block(blocks[1])
        if home_sot is None and first_sot is not None:
            home_sot = first_sot
            matched_home = True
            if match_method is None:
                match_method = "order_fallback"
        if away_sot is None and second_sot is not None:
            away_sot = second_sot
            matched_away = True
            if match_method is None:
                match_method = "order_fallback"

    total_sot: float | None = None
    sot_available = False
    sot_unavailable_reason: str | None = None

    if not blocks:
        sot_unavailable_reason = "Statistiche API-Sports vuote"
    elif home_sot is not None and away_sot is not None:
        total_sot = round(home_sot + away_sot, 2)
        sot_available = True
    else:
        if home_sot is None and away_sot is None:
            sot_unavailable_reason = "Nessun SOT nei blocchi statistiche"
        else:
            sot_unavailable_reason = "SOT parziale (manca casa o trasferta)"

    return {
        "home_sot": home_sot,
        "away_sot": away_sot,
        "total_sot": total_sot,
        "sot_available": sot_available,
        "sot_unavailable_reason": sot_unavailable_reason,
        "debug": {
            "raw_blocks_count": len(blocks),
            "matched_home": matched_home,
            "matched_away": matched_away,
            "labels_seen": labels_seen[:20],
            "match_method": match_method,
            "home_api_team_id": home_api_team_id,
            "away_api_team_id": away_api_team_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
        },
    }
