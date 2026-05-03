from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.api_football_client import ApiFootballClient, ApiFootballError

router = APIRouter(prefix="/admin")


def _error_payload(message: str, season: int) -> dict[str, Any]:
    return {
        "status": "error",
        "message": message,
        "league_id": None,
        "league_name": None,
        "country": None,
        "season": season,
        "coverage": None,
        "raw_response_count": 0,
    }


@router.get("/api-football/test")
def api_football_test() -> dict[str, Any]:
    """Chiamata di prova a API-Sports /leagues per id e stagione (nessuna persistenza)."""
    settings = get_settings()
    league_id = settings.default_league_id
    season = settings.default_season
    client = ApiFootballClient()
    try:
        body = client.get(
            "leagues",
            {"id": league_id, "season": season},
        )
    except ApiFootballError as exc:
        return _error_payload(str(exc), season)

    items: list[Any] = list(body.get("response") or [])
    raw_response_count = len(items)
    if not items:
        return _error_payload(
            "Nessuna lega nella risposta API per id e stagione indicati.",
            season,
        )

    row = items[0]
    league = row.get("league") or {}
    country_obj = row.get("country") or {}
    seasons = row.get("seasons") or []
    season_row: dict[str, Any] | None = None
    for s in seasons:
        if isinstance(s, dict) and s.get("year") == season:
            season_row = s
            break
    if season_row is None and seasons and isinstance(seasons[0], dict):
        season_row = seasons[0]

    coverage = season_row.get("coverage") if season_row else None

    return {
        "status": "ok",
        "league_id": league.get("id"),
        "league_name": league.get("name"),
        "country": country_obj.get("name"),
        "season": season,
        "coverage": coverage,
        "raw_response_count": raw_response_count,
    }
