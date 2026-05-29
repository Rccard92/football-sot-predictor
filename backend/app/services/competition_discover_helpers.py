from __future__ import annotations

import unicodedata
from typing import Any

from fastapi import HTTPException

from app.services.league_season_api_helpers import (
    extract_available_seasons,
    extract_current_season,
    extract_season_meta,
)

BRAZIL_SERIE_A_ALIASES = (
    "serie a",
    "brazil serie a",
    "brazilian serie a",
    "brasileirao",
    "brasileirão",
    "brasileiro serie a",
    "brasileiro série a",
)

NO_MATCH_MESSAGE = (
    "Nessuna lega compatibile trovata. Prova a lasciare vuoto Nome lega oppure cerca Brasileirão."
)

SEASON_UNAVAILABLE_MESSAGE = (
    "La lega esiste, ma la stagione {season} non risulta disponibile nella risposta API-Sports."
)


def _normalize_text(value: str) -> str:
    lowered = value.casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def build_leagues_query_params(country: str, name_query: str, season: int) -> dict[str, Any]:
    country_value = country.strip()
    name_value = name_query.strip()

    if not country_value and not name_value:
        raise HTTPException(
            status_code=400,
            detail="Discovery richiede almeno Paese o Nome lega.",
        )

    params: dict[str, Any] = {"season": season}
    if country_value:
        params["country"] = country_value
    else:
        params["search"] = name_value
    return params


def format_api_query(params: dict[str, Any]) -> str:
    return "&".join(f"{key}={value}" for key, value in params.items())


def parse_league_response_items(items: list[Any], season: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        lg = item.get("league") or {}
        if not isinstance(lg, dict) or lg.get("id") is None:
            continue

        available_seasons = extract_available_seasons(item)
        meta = extract_season_meta(item, season)
        season_current = meta.get("current")
        country_name = (item.get("country") or {}).get("name")
        candidates.append(
            {
                "provider_league_id": int(lg["id"]),
                "name": str(lg.get("name") or ""),
                "country": country_name,
                "season": season,
                "logo": lg.get("logo"),
                "season_current": season_current if meta.get("found") else None,
                "available_seasons": available_seasons,
                "requested_season_available": bool(meta.get("found")),
                "current_season": extract_current_season(item),
                "raw_payload": item,
            }
        )
    return candidates


def _name_matches_query(name: str, name_query: str) -> bool:
    normalized_name = _normalize_text(name)
    normalized_query = _normalize_text(name_query)

    if not normalized_query:
        return True

    if normalized_query in normalized_name:
        return True

    query_tokens = [token for token in normalized_query.split() if token]
    if query_tokens and all(token in normalized_name for token in query_tokens):
        return True

    expanded_terms = {normalized_query, *query_tokens}
    if "serie" in query_tokens and "a" in query_tokens:
        expanded_terms.update(BRAZIL_SERIE_A_ALIASES)

    return any(term in normalized_name for term in expanded_terms)


def _country_matches(candidate_country: str | None, country: str) -> bool:
    country_value = country.strip()
    if not country_value:
        return True
    if candidate_country is None:
        return False
    return _normalize_text(candidate_country) == _normalize_text(country_value)


def filter_discover_candidates(
    candidates: list[dict[str, Any]],
    *,
    country: str,
    name_query: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    country_value = country.strip()
    name_value = name_query.strip()

    scoped = [
        candidate
        for candidate in candidates
        if _country_matches(candidate.get("country"), country_value)
    ]
    if not country_value:
        scoped = list(candidates)

    if not name_value:
        return scoped, []

    primary = [
        candidate
        for candidate in scoped
        if _name_matches_query(str(candidate.get("name") or ""), name_value)
    ]
    if primary:
        return primary, []

    return [], scoped


def season_unavailable_message(season: int) -> str:
    return SEASON_UNAVAILABLE_MESSAGE.format(season=season)
