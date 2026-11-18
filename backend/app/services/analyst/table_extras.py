"""Le parti nuove della scheda partita del 18/11/2026 (migliorie 1-3 di Giovanni), calcolate per tutte le righe
del giorno con poche query: movimento delle quote, calendario con le coppe, formazioni e indisponibili, gialli
dagli eventi. Ogni parte che manca resta vuota (None): la Tabella non si ferma mai per queste informazioni."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analyst_extra import AnalystLineup
from app.models.fixture import Fixture
from app.services.analyst.calendar import load_games, team_schedule
from app.services.analyst.form import LeagueSeason
from app.services.analyst.lineups import HABIT_GAMES, api_team_ids, habitual_xi, injuries_for, squad_status, team_lineups
from app.services.analyst.odds_reads import kpi_quotes, movement, reads_for

logger = logging.getLogger(__name__)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_extras(
    db: Session,
    fixtures: list[Any],
    locals_: dict[int, Any],
    targets: dict[int, dict[str, Any]],
    seasons: dict[tuple[int, int], LeagueSeason],
    picked: dict[int, dict[str, list[dict[str, Any]]]],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, int]]]:
    """(parti nuove per riga, gialli dagli eventi per gara locale {"home"/"away": n})."""
    out: dict[int, dict[str, Any]] = {int(f.id): {} for f in fixtures}
    yellows: dict[int, dict[str, int]] = {}
    for part in (_odds_moves, _schedules, _squads):
        try:
            part(db, fixtures, locals_, targets, seasons, picked, out, yellows)
        except Exception:  # noqa: BLE001 - informazione in piu': se manca, la riga resta com'e'
            logger.exception("tabella: %s non calcolato", part.__name__)
            db.rollback()
    return out, yellows


def _odds_moves(db, fixtures, locals_, targets, seasons, picked, out, yellows) -> None:
    reads = reads_for(db, [int(f.id) for f in fixtures])
    for f in fixtures:
        r = reads.get(int(f.id))
        if r is None:
            continue
        morning, cecchino = kpi_quotes(f)
        out[int(f.id)]["odds_move"] = {
            "status": r.status,
            "read_at": _aware(r.read_at).isoformat() if r.read_at else None,
            "markets": movement(morning, r.markets_json or {}, cecchino) if r.status == "ok" else [],
        }


def _schedules(db, fixtures, locals_, targets, seasons, picked, out, yellows) -> None:
    team_ids = {int(loc.home_team_id) for loc in locals_.values()} | {int(loc.away_team_id) for loc in locals_.values()}
    api = api_team_ids(db, team_ids)
    cutoffs = [t["kickoff"] for t in targets.values() if t.get("kickoff")]
    if not api or not cutoffs:
        return
    games = load_games(db, set(api.values()), min(cutoffs) - timedelta(days=16), max(cutoffs) + timedelta(days=16))
    for f in fixtures:
        loc = locals_.get(int(f.local_fixture_id))
        target = targets.get(int(f.id))
        if loc is None or target is None or not target.get("kickoff"):
            continue
        sched = {}
        for side, team in (("home", int(loc.home_team_id)), ("away", int(loc.away_team_id))):
            a = api.get(team)
            sched[side] = (
                team_schedule(games.get(a, []), a, cutoff=target["kickoff"], provider_fixture_id=f.provider_fixture_id, league_id=f.provider_league_id)
                if a
                else None
            )
        if sched.get("home") or sched.get("away"):
            out[int(f.id)]["schedule"] = sched


def _squads(db, fixtures, locals_, targets, seasons, picked, out, yellows) -> None:
    team_ids = {int(loc.home_team_id) for loc in locals_.values()} | {int(loc.away_team_id) for loc in locals_.values()}
    api = api_team_ids(db, team_ids)
    # ultime 10 gare di campionato di ogni squadra (per i titolari abituali) e gare della forma totale
    habit_games: dict[tuple[int, int], list[dict[str, Any]]] = {}
    local_ids: set[int] = set()
    for f in fixtures:
        loc = locals_.get(int(f.local_fixture_id))
        target = targets.get(int(f.id))
        if loc is None or target is None:
            continue
        season = seasons.get((int(loc.league_id), int(loc.season_id)))
        if season is None:
            continue
        for team in (int(loc.home_team_id), int(loc.away_team_id)):
            gs = season.recent(team, target, limit=HABIT_GAMES)
            habit_games[(int(f.id), team)] = gs
            local_ids.update(int(g["id"]) for g in gs)
        for block in ("forma_totale_casa", "forma_totale_fuori"):
            local_ids.update(int(g["id"]) for g in (picked.get(int(f.id)) or {}).get(block, []))
    if not local_ids:
        return
    api_fix = {int(i): int(a) for i, a in db.execute(select(Fixture.id, Fixture.api_fixture_id).where(Fixture.id.in_(local_ids))).all()}
    lineups = team_lineups(db, set(api.values()), set(api_fix.values()))
    injuries = injuries_for(db, {int(f.provider_fixture_id) for f in fixtures})
    for f in fixtures:
        loc = locals_.get(int(f.local_fixture_id))
        if loc is None:
            continue
        squads = {}
        for side, team, block in (("home", int(loc.home_team_id), "forma_totale_casa"), ("away", int(loc.away_team_id), "forma_totale_fuori")):
            a = api.get(team)
            if not a:
                continue

            def starters_of(local_id: int) -> list[dict[str, Any]] | None:
                lu = lineups.get((api_fix.get(local_id, -1), a))
                return lu.starters_json if lu is not None and lu.status == "ok" else None

            habit_src = [{"starters": starters_of(int(g["id"]))} for g in habit_games.get((int(f.id), team), [])]
            habitual = habitual_xi(habit_src)
            injured = injuries.get((int(f.provider_fixture_id), a), [])
            injured_ids = {int(i.player_id) for i in injured}
            history = []
            for g in (picked.get(int(f.id)) or {}).get(block, []):
                st = squad_status(starters_of(int(g["id"])), habitual)
                opp = g["away"] if g["home"] == team else g["home"]
                history.append({"date": g["kickoff"].date().isoformat() if g.get("kickoff") else None, "opponent_id": opp, "rosa": st})
            squads[side] = {
                "lineups_known": sum(1 for x in habit_src if x["starters"]),
                "habitual": habitual,
                "injured": [
                    {"name": i.player_name, "kind": i.kind, "reason": i.reason, "starter": bool(habitual and any(p["id"] == int(i.player_id) for p in habitual))}
                    for i in injured
                ],
                "injuries_known": bool(injured),
                "missing_starters": sum(1 for p in (habitual or []) if p["id"] in injured_ids),
                "probable": [p for p in (habitual or []) if p["id"] not in injured_ids] if habitual else None,
                "history": history,
            }
            # gialli dagli eventi (quando mancano le statistiche): {gara locale: {"home"/"away": n}}
            for g in (picked.get(int(f.id)) or {}).get(block, []):
                lu = lineups.get((api_fix.get(int(g["id"]), -1), a))
                if lu is not None and lu.yellow_cards is not None:
                    yellows.setdefault(int(g["id"]), {})["home" if g["home"] == team else "away"] = int(lu.yellow_cards)
        if squads:
            out[int(f.id)]["squads"] = squads
    # gialli: anche l'avversaria della gara della forma, se la sua formazione e' salvata
    if yellows:
        others = db.execute(
            select(AnalystLineup.provider_fixture_id, AnalystLineup.provider_team_id, AnalystLineup.yellow_cards).where(
                AnalystLineup.provider_fixture_id.in_({api_fix[i] for i in yellows if i in api_fix}), AnalystLineup.yellow_cards.is_not(None)
            )
        ).all()
        by_fix: dict[int, dict[int, int]] = {}
        for pf, pt, yc in others:
            by_fix.setdefault(int(pf), {})[int(pt)] = int(yc)
        teams_of = {
            int(i): (int(h), int(aw))
            for i, h, aw in db.execute(select(Fixture.id, Fixture.home_team_id, Fixture.away_team_id).where(Fixture.id.in_(set(yellows)))).all()
        }
        api_more = api_team_ids(db, {t for pair in teams_of.values() for t in pair})
        for local_id, sides in yellows.items():
            h, aw = teams_of.get(local_id, (None, None))
            vals = by_fix.get(api_fix.get(local_id, -1), {})
            if h is not None and api_more.get(h) in vals:
                sides["home"] = vals[api_more[h]]
            if aw is not None and api_more.get(aw) in vals:
                sides["away"] = vals[api_more[aw]]
