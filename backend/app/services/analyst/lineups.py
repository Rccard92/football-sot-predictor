"""Indisponibili e probabili formazioni (Miglioria 3 di Giovanni, 17/11/2026).

- Formazioni: per le gare del Diario di oggi e domani si scaricano le formazioni titolari delle ultime 10 gare di
  campionato di ogni squadra (fixtures?ids= a gruppi di 20: una chiamata porta formazioni ed eventi, quindi anche i
  gialli). Una gara si scarica una volta sola.
- Titolari abituali = gli 11 con piu' presenze da titolare nelle ultime 10 gare (non 5: chi ha saltato le ultime 5
  puo' essere comunque titolare). Servono almeno 5 formazioni.
- Storico: per ogni gara della forma, "rosa completa" oppure "-N titolari (ruoli)" rispetto ai titolari abituali.
- Indisponibili: quelli che il fornitore annuncia per la gara (injuries?ids=, a gruppi di 20). Il fornitore li da'
  solo in pochi campionati (23 su 1.244 dichiarati): altrove si vede "non disponibili".
- Probabile formazione = titolari abituali meno gli indisponibili.
"""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.analyst_extra import AnalystInjury, AnalystLineup
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.fixture import Fixture
from app.models.team import Team
from app.services.analyst.leagues import league_admitted

logger = logging.getLogger(__name__)

HABIT_GAMES = 10
MIN_LINEUPS = 5
BATCH = 20
ROLE = {"G": "portiere", "D": "difensore", "M": "centrocampista", "F": "attaccante"}
ROLE_PLURAL = {"G": "portieri", "D": "difensori", "M": "centrocampisti", "F": "attaccanti"}
_injury_fetched: dict[int, float] = {}
INJURY_TTL = 6 * 3600


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_fixture_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Da un elemento di fixtures?ids= le due formazioni (titolari) e i gialli per squadra."""
    fid = int((item.get("fixture") or {}).get("id") or 0)
    teams = item.get("teams") or {}
    team_ids = [t for t in ((teams.get("home") or {}).get("id"), (teams.get("away") or {}).get("id")) if t]
    yellows: Counter = Counter()
    for ev in item.get("events") or []:
        if (ev.get("type") or "").lower() == "card" and "yellow" in (ev.get("detail") or "").lower():
            tid = (ev.get("team") or {}).get("id")
            if tid:
                yellows[int(tid)] += 1
    by_team = {int((lu.get("team") or {}).get("id")): lu for lu in item.get("lineups") or [] if (lu.get("team") or {}).get("id")}
    events_known = bool(item.get("events")) or (item.get("fixture") or {}).get("status", {}).get("short") in FINISHED_STATUSES
    out = []
    for tid in team_ids:
        lu = by_team.get(int(tid))
        starters = []
        for p in (lu or {}).get("startXI") or []:
            pl = p.get("player") or {}
            if pl.get("id"):
                starters.append({"id": int(pl["id"]), "name": pl.get("name"), "pos": pl.get("pos")})
        out.append(
            {
                "provider_fixture_id": fid,
                "provider_team_id": int(tid),
                "status": "ok" if len(starters) >= 11 else "nd",
                "formation": (lu or {}).get("formation"),
                "starters_json": starters or None,
                "yellow_cards": int(yellows.get(int(tid), 0)) if events_known else None,
            }
        )
    return out


def _admitted_upcoming(db: Session, now: datetime) -> list[tuple[CecchinoTodayFixture, Fixture]]:
    rows = db.execute(
        select(CecchinoTodayFixture, Fixture)
        .join(Fixture, Fixture.id == CecchinoTodayFixture.local_fixture_id)
        .where(
            CecchinoTodayFixture.eligibility_status == "eligible",
            Fixture.kickoff_at > now,
            Fixture.kickoff_at <= now + timedelta(days=2),
        )
    ).all()
    return [(t, f) for t, f in rows if league_admitted(t.country_name, t.league_name)]


def missing_fixtures(db: Session, now: datetime) -> list[int]:
    """Gare (id del fornitore) delle ultime 10 di campionato delle squadre del Diario senza formazione salvata."""
    matches = _admitted_upcoming(db, now)
    if not matches:
        return []
    pairs = {(int(f.league_id), int(f.season_id)) for _, f in matches}
    teams = {int(f.home_team_id) for _, f in matches} | {int(f.away_team_id) for _, f in matches}
    games = db.execute(
        select(Fixture.api_fixture_id, Fixture.home_team_id, Fixture.away_team_id, Fixture.kickoff_at, Fixture.league_id, Fixture.season_id).where(
            Fixture.league_id.in_({p[0] for p in pairs}),
            Fixture.status.in_(FINISHED_STATUSES),
            Fixture.kickoff_at < now,
            Fixture.kickoff_at >= now - timedelta(days=180),
        )
    ).all()
    per_team: dict[int, list[tuple[datetime, int]]] = defaultdict(list)
    for g in games:
        if (int(g.league_id), int(g.season_id)) not in pairs:
            continue
        for t in (int(g.home_team_id), int(g.away_team_id)):
            if t in teams:
                per_team[t].append((_aware(g.kickoff_at), int(g.api_fixture_id)))
    wanted: set[int] = set()
    for lst in per_team.values():
        lst.sort()
        wanted.update(fid for _, fid in lst[-HABIT_GAMES:])
    if not wanted:
        return []
    have = {int(i) for (i,) in db.execute(select(AnalystLineup.provider_fixture_id).where(AnalystLineup.provider_fixture_id.in_(wanted))).all()}
    return sorted(wanted - have)


def store_items(db: Session, items: list[dict[str, Any]], asked: list[int]) -> int:
    seen: set[int] = set()
    stored = 0
    for item in items or []:
        for row in parse_fixture_item(item):
            seen.add(row["provider_fixture_id"])
            exists = db.execute(
                select(AnalystLineup).where(
                    AnalystLineup.provider_fixture_id == row["provider_fixture_id"], AnalystLineup.provider_team_id == row["provider_team_id"]
                )
            ).scalar_one_or_none()
            if exists is None:
                db.add(AnalystLineup(**row))
                stored += 1
    # gara chiesta ma non restituita: segnata, per non richiederla a ogni giro
    for fid in set(asked) - seen:
        db.add(AnalystLineup(provider_fixture_id=fid, provider_team_id=0, status="nd"))
    db.commit()
    return stored


def refresh_lineups(db: Session, client: Any, now: datetime | None = None, *, max_calls: int = 8) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    out = {"missing": 0, "calls": 0, "stored": 0, "errors": 0}
    missing = missing_fixtures(db, now)
    out["missing"] = len(missing)
    for i in range(0, min(len(missing), max_calls * BATCH), BATCH):
        chunk = missing[i : i + BATCH]
        try:
            body = client.get("fixtures", {"ids": "-".join(str(x) for x in chunk)})
            items = list(body.get("response") or [])
        except Exception:  # noqa: BLE001
            logger.warning("formazioni: gruppo non scaricato", exc_info=True)
            out["errors"] += 1
            continue
        out["calls"] += 1
        out["stored"] += store_items(db, items, chunk)
    return out


def refresh_injuries(db: Session, client: Any, now: datetime | None = None, *, max_calls: int = 6) -> dict[str, int]:
    """Indisponibili delle gare del Diario di oggi e domani, una volta ogni 6 ore per gara."""
    now = now or datetime.now(timezone.utc)
    clock = time.monotonic()
    todo = [int(t.provider_fixture_id) for t, _ in _admitted_upcoming(db, now) if clock - _injury_fetched.get(int(t.provider_fixture_id), -1e9) > INJURY_TTL]
    out = {"fixtures": len(todo), "calls": 0, "stored": 0}
    for i in range(0, min(len(todo), max_calls * BATCH), BATCH):
        chunk = todo[i : i + BATCH]
        items, _errors = client.get_injuries_by_ids(chunk, chunk_size=BATCH)
        out["calls"] += 1
        for fid in chunk:
            _injury_fetched[fid] = clock
        for it in items:
            fid = int((it.get("fixture") or {}).get("id") or 0)
            tid = int((it.get("team") or {}).get("id") or 0)
            pl = it.get("player") or {}
            if not fid or not tid or not pl.get("id"):
                continue
            exists = db.execute(
                select(AnalystInjury).where(
                    AnalystInjury.provider_fixture_id == fid, AnalystInjury.provider_team_id == tid, AnalystInjury.player_id == int(pl["id"])
                )
            ).scalar_one_or_none()
            if exists is None:
                db.add(
                    AnalystInjury(
                        provider_fixture_id=fid, provider_team_id=tid, player_id=int(pl["id"]), player_name=pl.get("name"),
                        kind=(pl.get("type") or None), reason=(pl.get("reason") or None),
                    )
                )
                out["stored"] += 1
        db.commit()
    return out


# --- lettura per la Tabella ---


def habitual_xi(lineups: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Gli 11 con piu' presenze da titolare (a parita', il piu' recente). lineups dal piu' vecchio al piu' recente."""
    ok = [lu for lu in lineups if lu.get("starters")][-HABIT_GAMES:]
    if len(ok) < MIN_LINEUPS:
        return None
    starts: Counter = Counter()
    last_seen: dict[int, int] = {}
    info: dict[int, dict[str, Any]] = {}
    for i, lu in enumerate(ok):
        for p in lu["starters"]:
            starts[p["id"]] += 1
            last_seen[p["id"]] = i
            info[p["id"]] = p
    best = sorted(starts, key=lambda pid: (-starts[pid], -last_seen[pid]))[:11]
    return [{**info[pid], "starts": starts[pid], "of": len(ok)} for pid in best]


def roles_text(players: list[dict[str, Any]]) -> str:
    counts = Counter((p.get("pos") or "?") for p in players)
    parts = []
    for pos in ("G", "D", "M", "F", "?"):
        n = counts.get(pos, 0)
        if not n:
            continue
        if pos == "?":
            parts.append(f"{n} n.d.")
        else:
            parts.append(ROLE[pos] if n == 1 else f"{n} {ROLE_PLURAL[pos]}")
    return ", ".join(parts)


def squad_status(starters: list[dict[str, Any]] | None, habitual: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Con che rosa ha giocato una gara: completa o -N titolari abituali (ruoli)."""
    if not starters or not habitual:
        return None
    ids = {p["id"] for p in starters}
    missing = [p for p in habitual if p["id"] not in ids]
    if not missing:
        return {"complete": True, "missing": 0, "text": "completa"}
    return {"complete": False, "missing": len(missing), "text": f"−{len(missing)} titolari ({roles_text(missing)})", "players": [p.get("name") for p in missing]}


def team_lineups(db: Session, provider_team_ids: set[int], provider_fixture_ids: set[int]) -> dict[tuple[int, int], AnalystLineup]:
    if not provider_team_ids or not provider_fixture_ids:
        return {}
    return {
        (int(lu.provider_fixture_id), int(lu.provider_team_id)): lu
        for lu in db.execute(
            select(AnalystLineup).where(
                AnalystLineup.provider_fixture_id.in_(provider_fixture_ids), AnalystLineup.provider_team_id.in_(provider_team_ids)
            )
        ).scalars()
    }


def injuries_for(db: Session, provider_fixture_ids: set[int]) -> dict[tuple[int, int], list[AnalystInjury]]:
    out: dict[tuple[int, int], list[AnalystInjury]] = defaultdict(list)
    if not provider_fixture_ids:
        return out
    for inj in db.execute(select(AnalystInjury).where(AnalystInjury.provider_fixture_id.in_(provider_fixture_ids))).scalars():
        out[(int(inj.provider_fixture_id), int(inj.provider_team_id))].append(inj)
    return out


def api_team_ids(db: Session, team_ids: set[int]) -> dict[int, int]:
    if not team_ids:
        return {}
    return {int(i): int(a) for i, a in db.execute(select(Team.id, Team.api_team_id).where(Team.id.in_(team_ids))).all() if a}
