"""Controllo live API injuries per fixture (solo lettura, nessuna persistenza)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture, Season
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_parsing import parse_injuries_item


def build_availability_live_fixture_check(
    db: Session,
    season_year: int,
    fixture_id: int,
    *,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    fx = db.scalar(
        select(Fixture)
        .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
        .where(Fixture.id == int(fixture_id)),
    )
    if fx is None:
        return {
            "status": "error",
            "message": f"Fixture {fixture_id} non trovata",
            "fixture_id": int(fixture_id),
        }

    season_row = db.scalar(select(Season).where(Season.id == int(fx.season_id)))
    if season_row is None or int(season_row.year) != int(season_year):
        return {
            "status": "error",
            "message": f"Fixture {fixture_id} non appartiene alla stagione {season_year}",
            "fixture_id": int(fixture_id),
        }

    api_fx_id = int(fx.api_fixture_id)
    request = f"injuries?fixture={api_fx_id}"
    api = client or ApiFootballClient()
    errors: list[str] = []

    try:
        items = api.get_injuries_by_fixture(api_fx_id)
    except ApiFootballError as exc:
        return {
            "status": "error",
            "message": str(exc)[:500],
            "fixture_id": int(fixture_id),
            "api_fixture_id": api_fx_id,
            "request": request,
            "results": 0,
            "records": [],
            "errors": [str(exc)[:500]],
        }

    records: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        parsed = parse_injuries_item(raw)
        pl = raw.get("player") if isinstance(raw.get("player"), dict) else {}
        tm = raw.get("team") if isinstance(raw.get("team"), dict) else {}
        records.append(
            {
                "player_name": pl.get("name"),
                "player_api_id": pl.get("id"),
                "team_name": tm.get("name"),
                "team_api_id": tm.get("id"),
                "type": pl.get("type") or raw.get("type"),
                "reason": pl.get("reason") or raw.get("reason"),
                "parsed_status": parsed.availability_status if parsed else None,
                "parsed_type": parsed.availability_type if parsed else None,
                "raw_json": raw,
            },
        )

    return {
        "status": "success",
        "season": int(season_year),
        "fixture_id": int(fixture_id),
        "api_fixture_id": api_fx_id,
        "request": request,
        "results": len(records),
        "records": records,
        "errors": errors,
        "note": "Solo lettura API: nessun dato salvato nel DB.",
    }
