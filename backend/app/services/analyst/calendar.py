"""Ultima e prossima gara delle squadre, coppe comprese (Miglioria 2 di Giovanni, 17/11/2026).

Il fornitore da' in una sola chiamata tutte le gare del mondo di un giorno (fixtures?date=), coppe comprese.
Si tengono i giorni da 14 indietro a 10 avanti: un giorno passato si scarica una volta, quelli da ieri in avanti
si riscaricano ogni giorno (rinvii e orari). Costo: circa 12 chiamate al giorno.
Per ogni squadra della partita: data e competizione dell'ultima e della prossima gara, giorni di riposo, gare
negli ultimi 7 e 14 giorni (tutto prima del calcio d'inizio della partita).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.analyst_extra import AnalystCalendarDay, AnalystTeamGame

logger = logging.getLogger(__name__)

DAYS_BACK = 14
DAYS_AHEAD = 10
REFRESH_HOURS = 20
_VOID = {"PST", "CANC", "ABD", "AWD", "WO", "TBD"}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def days_to_fetch(db: Session, today: date, now: datetime) -> list[date]:
    wanted = [today + timedelta(days=d) for d in range(-DAYS_BACK, DAYS_AHEAD + 1)]
    have = {r.day: _aware(r.fetched_at) for r in db.execute(select(AnalystCalendarDay).where(AnalystCalendarDay.day.in_(wanted))).scalars()}
    out = []
    for d in wanted:
        fetched = have.get(d)
        if fetched is None:
            out.append(d)
        elif d >= today - timedelta(days=1) and (now - fetched).total_seconds() > REFRESH_HOURS * 3600:
            out.append(d)
        elif d < today - timedelta(days=1) and fetched.date() <= d + timedelta(days=1):
            out.append(d)  # scaricato mentre il giorno era ancora in corso: una volta ancora a giorno finito
    return out


def _item_row(item: dict[str, Any], day: date) -> dict[str, Any] | None:
    fx, lg, teams = item.get("fixture") or {}, item.get("league") or {}, item.get("teams") or {}
    if not fx.get("id"):
        return None
    try:
        kickoff = datetime.fromisoformat(str(fx.get("date")).replace("Z", "+00:00")) if fx.get("date") else None
    except ValueError:
        kickoff = None
    return {
        "provider_fixture_id": int(fx["id"]),
        "day": day,
        "kickoff": kickoff,
        "status": ((fx.get("status") or {}).get("short") or None),
        "provider_league_id": lg.get("id"),
        "league_name": (lg.get("name") or None),
        "league_country": (lg.get("country") or None),
        "league_round": (str(lg.get("round"))[:120] if lg.get("round") else None),
        "home_provider_team_id": (teams.get("home") or {}).get("id"),
        "away_provider_team_id": (teams.get("away") or {}).get("id"),
        "home_team_name": ((teams.get("home") or {}).get("name") or None),
        "away_team_name": ((teams.get("away") or {}).get("name") or None),
    }


def store_day(db: Session, day: date, items: list[dict[str, Any]], now: datetime) -> int:
    rows = [r for r in (_item_row(i, day) for i in items or []) if r]
    existing = {
        int(g.provider_fixture_id): g
        for g in db.execute(
            select(AnalystTeamGame).where(AnalystTeamGame.provider_fixture_id.in_([r["provider_fixture_id"] for r in rows]))
        ).scalars()
    } if rows else {}
    for r in rows:
        g = existing.get(r["provider_fixture_id"])
        if g is None:
            db.add(AnalystTeamGame(**r))
        else:
            for k, v in r.items():
                setattr(g, k, v)
    marker = db.get(AnalystCalendarDay, day)
    if marker is None:
        db.add(AnalystCalendarDay(day=day, fetched_at=now, games=len(rows)))
    else:
        marker.fetched_at, marker.games = now, len(rows)
    db.commit()
    return len(rows)


def refresh_calendar(db: Session, client: Any, now: datetime | None = None, *, max_calls: int = 4) -> dict[str, int]:
    """Pochi giorni per giro (il giro e' ogni 5 minuti): in un'ora il calendario e' completo."""
    now = now or datetime.now(timezone.utc)
    out = {"days": 0, "games": 0, "errors": 0}
    for day in days_to_fetch(db, now.date(), now)[:max_calls]:
        try:
            items = client.get_fixtures_by_date(day.isoformat(), timezone="UTC")
        except Exception:  # noqa: BLE001
            logger.warning("calendario: giorno %s non scaricato", day, exc_info=True)
            out["errors"] += 1
            continue
        out["games"] += store_day(db, day, items, now)
        out["days"] += 1
    return out


def load_games(db: Session, team_ids: set[int], start: datetime, end: datetime) -> dict[int, list[AnalystTeamGame]]:
    if not team_ids:
        return {}
    games = db.execute(
        select(AnalystTeamGame).where(
            or_(AnalystTeamGame.home_provider_team_id.in_(team_ids), AnalystTeamGame.away_provider_team_id.in_(team_ids)),
            AnalystTeamGame.kickoff >= start,
            AnalystTeamGame.kickoff <= end,
        )
    ).scalars().all()
    out: dict[int, list[AnalystTeamGame]] = defaultdict(list)
    for g in games:
        for t in (g.home_provider_team_id, g.away_provider_team_id):
            if t is not None and int(t) in team_ids:
                out[int(t)].append(g)
    for lst in out.values():
        lst.sort(key=lambda g: _aware(g.kickoff) or datetime.min.replace(tzinfo=timezone.utc))
    return out


def _game_info(g: AnalystTeamGame, team: int, league_id: int | None, ref: datetime) -> dict[str, Any]:
    home = g.home_provider_team_id is not None and int(g.home_provider_team_id) == team
    ko = _aware(g.kickoff)
    return {
        "date": ko.date().isoformat() if ko else None,
        "kickoff": ko.isoformat() if ko else None,
        "competition": g.league_name,
        "league_match": league_id is not None and g.provider_league_id is not None and int(g.provider_league_id) == int(league_id),
        "opponent": g.away_team_name if home else g.home_team_name,
        "home": home,
        "days": abs((ref.date() - ko.date()).days) if ko else None,
    }


def team_schedule(
    games: list[AnalystTeamGame], team: int, *, cutoff: datetime, provider_fixture_id: int | None, league_id: int | None
) -> dict[str, Any] | None:
    """Ultima e prossima gara (tutte le competizioni) rispetto al calcio d'inizio della partita."""
    played = [g for g in games if (g.status or "") not in _VOID and _aware(g.kickoff) and _aware(g.kickoff) < cutoff]
    upcoming = [
        g for g in games
        if (g.status or "") not in _VOID and _aware(g.kickoff) and _aware(g.kickoff) > cutoff
        and (provider_fixture_id is None or int(g.provider_fixture_id) != int(provider_fixture_id))
    ]
    if not played and not upcoming:
        return None
    last = played[-1] if played else None
    nxt = upcoming[0] if upcoming else None
    return {
        "last": _game_info(last, team, league_id, cutoff) if last else None,
        "next": _game_info(nxt, team, league_id, cutoff) if nxt else None,
        "games_7": sum(1 for g in played if (cutoff - _aware(g.kickoff)).days < 7),
        "games_14": sum(1 for g in played if (cutoff - _aware(g.kickoff)).days < 14),
    }
