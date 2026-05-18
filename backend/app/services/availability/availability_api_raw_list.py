"""Lista raw indisponibili da API-Football (solo lettura, nessuna persistenza)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, Team
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_league import resolve_serie_a_league_context
from app.services.availability.availability_parsing import parse_injuries_item, SOURCE_INJURIES


def _parse_fixture_date(item: dict[str, Any]) -> str | None:
    fx = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
    raw = fx.get("date")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.isoformat()
    return str(raw)


def _extract_type_reason(item: dict[str, Any]) -> tuple[str | None, str | None]:
    pl = item.get("player") if isinstance(item.get("player"), dict) else {}
    raw_type = pl.get("type") or item.get("type")
    if isinstance(raw_type, dict):
        raw_type = raw_type.get("type")
    reason = pl.get("reason") or item.get("reason")
    return (
        str(raw_type) if raw_type is not None else None,
        str(reason) if reason is not None else None,
    )


def _normalize_record(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    pl = item.get("player") if isinstance(item.get("player"), dict) else {}
    tm = item.get("team") if isinstance(item.get("team"), dict) else {}
    fx = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
    api_type, reason = _extract_type_reason(item)
    parsed = parse_injuries_item(item)
    return {
        "fixture_api_id": fx.get("id"),
        "fixture_date": _parse_fixture_date(item),
        "team_api_id": tm.get("id"),
        "team_name": tm.get("name"),
        "player_api_id": pl.get("id"),
        "player_name": pl.get("name"),
        "type": api_type,
        "reason": reason,
        "parsed_status": parsed.availability_status if parsed else None,
        "parsed_type": parsed.availability_type if parsed else None,
        "source": source,
        "raw_json": item,
    }


def build_availability_api_raw_list(
    db: Session,
    season_year: int,
    *,
    team_id: int | None = None,
    fixture_id: int | None = None,
    date: str | None = None,
    source: str = "injuries",
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    if source != "injuries":
        return {
            "status": "error",
            "message": f"source non supportata: {source}",
            "season": int(season_year),
        }

    ctx = resolve_serie_a_league_context(db, int(season_year))
    api_league_id = ctx.api_league_id
    league_internal_id = ctx.league_internal_id
    api = client or ApiFootballClient()

    request = f"injuries?league={api_league_id}&season={season_year}"
    params: dict[str, Any] = {"league": api_league_id, "season": int(season_year)}
    errors: list[str] = []

    if fixture_id is not None:
        fx = db.scalar(
            select(Fixture).where(
                Fixture.id == int(fixture_id),
                Fixture.season_id == int(ctx.season_row_id),
            ),
        )
        if fx is None:
            raise ValueError(f"Fixture {fixture_id} non trovata per stagione {season_year}")
        api_fx = int(fx.api_fixture_id)
        request = f"injuries?fixture={api_fx}"
        params = {"fixture": api_fx}
    elif team_id is not None:
        team = db.scalar(select(Team).where(Team.id == int(team_id)))
        if team is None:
            raise ValueError(f"Team {team_id} non trovato")
        api_team = int(team.api_team_id)
        request = f"injuries?league={api_league_id}&season={season_year}&team={api_team}"
        params = {"league": api_league_id, "season": int(season_year), "team": api_team}
    elif date and date.strip():
        d = date.strip()
        request = f"injuries?league={api_league_id}&season={season_year}&date={d}"
        params = {"league": api_league_id, "season": int(season_year), "date": d}

    try:
        body = api.get("injuries", params)
        items, api_errs = ApiFootballClient.injuries_response_items(body)
        errors.extend(str(e) for e in api_errs)
    except ApiFootballError as exc:
        items = []
        errors.append(str(exc)[:500])

    records = [_normalize_record(x, source=SOURCE_INJURIES) for x in items if isinstance(x, dict)]

    coverage: dict[str, Any] = {}
    try:
        coverage = api.get_league_season_coverage(api_league_id, int(season_year))
    except Exception as exc:  # noqa: BLE001
        coverage = {"_fetch_error": str(exc)[:300]}

    return {
        "status": "success",
        "season": int(season_year),
        "league_internal_id": league_internal_id,
        "api_league_id": api_league_id,
        "request": request,
        "results": len(records),
        "errors": errors,
        "records": records,
        "coverage": {
            "injuries": coverage.get("injuries"),
            "raw": coverage,
        },
    }
