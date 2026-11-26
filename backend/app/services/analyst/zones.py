"""Descrizione delle posizioni della classifica (capitolato del 24/11/2026, modifica 17).

API-Football da' nel campo description di standings la zona di ogni posizione ("Promotion", "Relegation",
"Champions League"...). Si legge una volta a settimana per campionato del Diario di oggi e domani: una chiamata per
campionato. Con piu' gironi (conference, Apertura e Clausura nella stessa risposta) la classifica del fornitore non
coincide con la nostra: si salva "groups" e la motivazione resta n.d.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analyst_capitolato import AnalystLeagueZones
from app.models.league import League
from app.models.season import Season
from app.services.analyst.lineups import _admitted_upcoming

logger = logging.getLogger(__name__)

REFRESH = timedelta(days=7)
RETRY = timedelta(days=1)


def parse_standings(response: list[dict[str, Any]]) -> tuple[str, int | None, dict[str, Any] | None]:
    """(status, squadre, {posizione: descrizione}) dalla risposta di standings."""
    groups: list[list[dict[str, Any]]] = []
    for item in response or []:
        for group in ((item.get("league") or {}).get("standings") or []):
            if isinstance(group, list) and group:
                groups.append(group)
    if not groups:
        return "nd", None, None
    if len(groups) > 1:
        return "groups", None, None
    zones = {str(int(e["rank"])): (e.get("description") or None) for e in groups[0] if e.get("rank") is not None}
    return "ok", len(groups[0]), zones


def refresh_zones(db: Session, client: Any, now: datetime | None = None, *, max_calls: int = 6) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    pairs = {(int(f.league_id), int(f.season_id)) for _, f in _admitted_upcoming(db, now)}
    if not pairs:
        return {"leagues": 0, "calls": 0}
    have = {
        (int(z.league_id), int(z.season_id)): z
        for z in db.execute(select(AnalystLeagueZones).where(AnalystLeagueZones.league_id.in_({p[0] for p in pairs}))).scalars()
    }
    todo = []
    for pair in sorted(pairs):
        z = have.get(pair)
        if z is None:
            todo.append(pair)
            continue
        fetched = z.fetched_at if z.fetched_at.tzinfo else z.fetched_at.replace(tzinfo=timezone.utc)
        if now - fetched > (REFRESH if z.status == "ok" else RETRY):
            todo.append(pair)
    out = {"leagues": len(pairs), "calls": 0}
    for league_id, season_id in todo[:max_calls]:
        league, season = db.get(League, league_id), db.get(Season, season_id)
        if league is None or season is None:
            continue
        try:
            response = client.get_standings(int(league.api_league_id), int(season.year))
        except Exception:  # noqa: BLE001 - un campionato senza classifica non ferma gli altri
            logger.warning("diario: classifica di %s non letta", league.name, exc_info=True)
            response = []
        out["calls"] += 1
        status, teams, zones = parse_standings(response)
        row = have.get((league_id, season_id))
        if row is None:
            row = AnalystLeagueZones(league_id=league_id, season_id=season_id, status=status, teams=teams, zones_json=zones, fetched_at=now)
            db.add(row)
        else:
            row.status, row.teams, row.zones_json, row.fetched_at = status, teams, zones, now
    db.commit()
    return out


def zones_for(db: Session, pairs: set[tuple[int, int]]) -> dict[tuple[int, int], dict[str, Any]]:
    if not pairs:
        return {}
    out = {}
    for z in db.execute(select(AnalystLeagueZones).where(AnalystLeagueZones.league_id.in_({p[0] for p in pairs}))).scalars():
        pair = (int(z.league_id), int(z.season_id))
        if pair in pairs:
            out[pair] = {"status": z.status, "teams": z.teams, "zones": z.zones_json or {}, "fetched_at": z.fetched_at.isoformat() if z.fetched_at else None}
    return out
