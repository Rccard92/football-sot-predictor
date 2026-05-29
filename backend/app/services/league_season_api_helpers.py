from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

LOG_EVENT = "COMPETITION_BOOTSTRAP_LEAGUE_RESPONSE"
RAW_DEBUG_MAX_CHARS = 2048


def normalize_season_year(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_available_seasons(picked: dict[str, Any]) -> list[int]:
    seasons = picked.get("seasons") or []
    out: list[int] = []
    for row in seasons:
        if not isinstance(row, dict):
            continue
        year = normalize_season_year(row.get("year"))
        if year is not None and year not in out:
            out.append(year)
    return sorted(out)


def extract_current_season(picked: dict[str, Any]) -> int | None:
    for row in picked.get("seasons") or []:
        if not isinstance(row, dict):
            continue
        if row.get("current") is True:
            return normalize_season_year(row.get("year"))
    return None


def extract_season_meta(picked: dict[str, Any], season: int) -> dict[str, Any]:
    requested = int(season)
    for row in picked.get("seasons") or []:
        if not isinstance(row, dict):
            continue
        year = normalize_season_year(row.get("year"))
        if year == requested:
            current = row.get("current")
            return {
                "found": True,
                "year": year,
                "current": bool(current) if current is not None else None,
                "entry": row,
            }
    return {"found": False, "year": requested, "current": None, "entry": None}


def truncate_raw_debug(payload: Any) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(payload)
    if len(text) <= RAW_DEBUG_MAX_CHARS:
        return text
    return text[:RAW_DEBUG_MAX_CHARS] + "…"


@dataclass
class LeaguePickInfo:
    provider_league_id: int
    league_name: str
    country: str | None
    available_seasons: list[int]
    current_season: int | None
    requested_season: int
    requested_season_available: bool
    raw_payload: dict[str, Any]
    raw_debug: str


def parse_league_pick(
    *,
    picked: dict[str, Any],
    provider_league_id: int,
    requested_season: int,
) -> LeaguePickInfo:
    lg = picked.get("league") or {}
    country_name = (picked.get("country") or {}).get("name")
    available = extract_available_seasons(picked)
    meta = extract_season_meta(picked, requested_season)
    info = LeaguePickInfo(
        provider_league_id=int(provider_league_id),
        league_name=str(lg.get("name") or ""),
        country=country_name,
        available_seasons=available,
        current_season=extract_current_season(picked),
        requested_season=int(requested_season),
        requested_season_available=bool(meta["found"]),
        raw_payload=picked,
        raw_debug=truncate_raw_debug(picked),
    )
    logger.info(
        "%s provider_league_id=%s requested_season=%s seasons_found=%s "
        "available_seasons=%s league_name=%r country=%r raw_debug=%s",
        LOG_EVENT,
        info.provider_league_id,
        info.requested_season,
        len(picked.get("seasons") or []),
        info.available_seasons,
        info.league_name,
        info.country,
        info.raw_debug,
    )
    return info


def season_not_available_payload(
    *,
    competition_id: int,
    competition_key: str,
    competition_name: str,
    provider_league_id: int,
    requested_season: int,
    available_seasons: list[int],
    league_name: str | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    label = competition_name or league_name or f"league {provider_league_id}"
    return {
        "status": "error",
        "code": "season_not_available",
        "message": (
            f"La stagione {requested_season} non è disponibile per {label} su API-Sports."
        ),
        "competition_id": competition_id,
        "competition_key": competition_key,
        "provider_league_id": provider_league_id,
        "requested_season": requested_season,
        "available_seasons": available_seasons,
        "league_name": league_name,
        "country": country,
        "suggestion": "Seleziona una stagione disponibile o aggiorna la competition.",
    }


class SeasonNotAvailableError(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(payload.get("message") or "season_not_available")
