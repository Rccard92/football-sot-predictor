from typing import Any

from fastapi import APIRouter

from app.services.api_football_client import ApiFootballClient, ApiFootballError

router = APIRouter(prefix="/admin")


@router.get("/api-football/test")
def api_football_test() -> dict[str, Any]:
    """Chiamata di prova a API-Sports /leagues (nessuna persistenza)."""
    client = ApiFootballClient()
    try:
        body = client.get(
            "leagues",
            {"country": "Italy", "search": "Serie A", "season": 2025},
        )
    except ApiFootballError as exc:
        return {
            "status": "error",
            "message": str(exc),
            "league_id": None,
            "league_name": None,
            "country": None,
            "season": None,
            "coverage": None,
            "raw_response_count": 0,
        }

    items: list[Any] = list(body.get("response") or [])
    raw_response_count = len(items)
    if not items:
        return {
            "status": "error",
            "message": "Nessuna lega nella risposta API per i filtri indicati.",
            "league_id": None,
            "league_name": None,
            "country": None,
            "season": None,
            "coverage": None,
            "raw_response_count": raw_response_count,
        }

    row = items[0]
    league = row.get("league") or {}
    country_obj = row.get("country") or {}
    seasons = row.get("seasons") or []
    season_row: dict[str, Any] | None = None
    for s in seasons:
        if isinstance(s, dict) and s.get("year") == 2025:
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
        "season": 2025,
        "coverage": coverage,
        "raw_response_count": raw_response_count,
    }
