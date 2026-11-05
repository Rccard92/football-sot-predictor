"""Tabella analisi (dal 05/11/2026): una riga per partita di Cecchino Today con forma, gol e gialli recenti.

Bozza di Giovanni (04/11/2026) e decisioni del 05/11/2026:
- forma = punti 3/1/0 sul risultato finale; sotto, i risultati di primo tempo e finali, l'ultima gara a destra;
  "Forma casa" = gare in casa della squadra di casa, "Forma fuori" = gare fuori dell'ospite, "Forma totale" = tutte;
- da 3 a 5 gare: sotto le 3 la cella resta vuota; la partita entra se almeno un blocco ha 3 gare;
- vittoria verde, sconfitta rossa, pareggio grigio; in grassetto vittorie e sconfitte contro squadre piu' in alto
  nella classifica di oggi, ricostruita dai risultati (non ne abbiamo una salvata);
- gol fatti contro subiti sulle stesse gare di "Forma casa/fuori"; gialli fatti e subiti sulle ultime 5 gare
  totali, solo dove ci sono le statistiche (nessuna chiamata API in piu');
- equilibrio = indice e classe gia' salvati da Today (cecchino_balance_v5_evaluations);
- quote = tutte quelle del pannello KPI.
Le gare recenti sono quelle della fotografia della scansione del mattino (stesso campionato, coppe escluse).
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.cecchino_balance_v5_evaluation import CecchinoBalanceV5Evaluation
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.fixture import Fixture
from app.models.fixture_team_stat import FixtureTeamStat
from app.models.team import Team
from app.services.analyst.journal import MARKETS

MIN_GAMES = 3
MAX_GAMES = 5
CACHE_SECONDS = 600  # la fotografia del mattino non cambia: si ricalcola al massimo ogni 10 minuti
_cache: dict[date, tuple[float, list[dict[str, Any]]]] = {}

# blocco -> (chiave della fotografia, squadra: "home" | "away")
_SNAPSHOT_KEYS = {
    "forma_casa": ("home_recent_context_5", "home"),
    "forma_fuori": ("away_recent_context_5", "away"),
    "forma_totale_casa": ("home_recent_total_6", "home"),
    "forma_totale_fuori": ("away_recent_total_6", "away"),
}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _outcome(scored: int | None, conceded: int | None) -> str | None:
    if scored is None or conceded is None:
        return None
    return "V" if scored > conceded else "P" if scored < conceded else "N"


def standings(games: list[tuple[int, int, int, int]]) -> tuple[dict[int, int], bool]:
    """Classifica dai risultati (casa, ospite, gol casa, gol ospite): {squadra: posizione}, e se e' completa.

    Ordine: punti, differenza reti, gol fatti. "Completa" = tutte le squadre con lo stesso numero di gare
    (scarto massimo 2), altrimenti nella stagione mancano risultati e il grassetto va preso con cautela."""
    pts: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # punti, diff, fatti, giocate
    for h, a, gh, ga in games:
        for team, gf, gs in ((h, gh, ga), (a, ga, gh)):
            row = pts[team]
            row[0] += 3 if gf > gs else 1 if gf == gs else 0
            row[1] += gf - gs
            row[2] += gf
            row[3] += 1
    order = sorted(pts, key=lambda t: (-pts[t][0], -pts[t][1], -pts[t][2]))
    played = [pts[t][3] for t in order]
    complete = bool(played) and max(played) - min(played) <= 2
    return {team: i + 1 for i, team in enumerate(order)}, complete


def _game(g: dict[str, Any], team: int, ranks: dict[int, int], names: dict[int, str]) -> dict[str, Any]:
    home = g["home"] == team
    gf, ga = (g["gh"], g["ga"]) if home else (g["ga"], g["gh"])
    hf, ha = (g["hth"], g["hta"]) if home else (g["hta"], g["hth"])
    opponent = g["away"] if home else g["home"]
    ft, ht = _outcome(gf, ga), _outcome(hf, ha)
    stronger = opponent in ranks and team in ranks and ranks[opponent] < ranks[team]
    return {
        "date": g["kickoff"].date().isoformat() if g["kickoff"] else None,
        "opponent": names.get(opponent),
        "opponent_rank": ranks.get(opponent),
        "home": home,
        "ft": f"{gf}-{ga}" if ft else None,  # sempre dal punto di vista della squadra in esame
        "ht": f"{hf}-{ha}" if ht else None,
        "ft_outcome": ft,
        "ht_outcome": ht,
        # grassetto solo per vittorie e sconfitte, e per ciascuna riga solo se c'e' quel risultato
        "bold_ft": bool(stronger and ft in ("V", "P")),
        "bold_ht": bool(stronger and ht in ("V", "P")),
    }


def _block(games: list[dict[str, Any]], team: int, ranks: dict[int, int], names: dict[int, str]) -> dict[str, Any]:
    games = [g for g in games if g["gh"] is not None and g["ga"] is not None][-MAX_GAMES:]
    if len(games) < MIN_GAMES:
        return {"games": len(games), "enough": False}
    rows = [_game(g, team, ranks, names) for g in games]
    points = sum(3 if r["ft_outcome"] == "V" else 1 if r["ft_outcome"] == "N" else 0 for r in rows)
    scored = sum(int(r["ft"].split("-")[0]) for r in rows if r["ft"])
    conceded = sum(int(r["ft"].split("-")[1]) for r in rows if r["ft"])
    return {
        "games": len(rows),
        "enough": True,
        "points": points,
        "max_points": 3 * len(rows),
        "scored": scored,
        "conceded": conceded,
        "results": rows,
        "team_rank": ranks.get(team),
    }


def _cards(games: list[dict[str, Any]], team: int, yellows: dict[int, dict[str, int]]) -> dict[str, Any]:
    games = [g for g in games if g["gh"] is not None and g["ga"] is not None][-MAX_GAMES:]
    own = conceded = with_data = 0
    for g in games:
        y = yellows.get(g["id"])
        if not y or "home" not in y or "away" not in y:
            continue
        side, other = ("home", "away") if g["home"] == team else ("away", "home")
        own += y[side]
        conceded += y[other]
        with_data += 1
    if with_data < MIN_GAMES:
        return {"games": with_data, "available": False}
    return {"games": with_data, "available": True, "own": own, "opponents": conceded}


def _history(db: Session, ids: set[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    postgres = db.get_bind().dialect.name == "postgresql"
    cols = [Fixture.id, Fixture.kickoff_at, Fixture.home_team_id, Fixture.away_team_id, Fixture.goals_home, Fixture.goals_away, Fixture.status]
    if postgres:
        cols += [
            func.jsonb_extract_path_text(Fixture.raw_json, "score", "halftime", "home"),
            func.jsonb_extract_path_text(Fixture.raw_json, "score", "halftime", "away"),
        ]
    else:
        cols.append(Fixture.raw_json)
    out: dict[int, dict[str, Any]] = {}
    for row in db.execute(select(*cols).where(Fixture.id.in_(ids))).all():
        if postgres:
            hth, hta = _int(row[7]), _int(row[8])
        else:
            ht = (((row[7] or {}).get("score") or {}).get("halftime")) or {}
            hth, hta = _int(ht.get("home")), _int(ht.get("away"))
        finished = (row.status or "") in FINISHED_STATUSES
        out[int(row.id)] = {
            "id": int(row.id),
            "kickoff": _aware(row.kickoff_at),
            "home": int(row.home_team_id),
            "away": int(row.away_team_id),
            "gh": row.goals_home if finished else None,
            "ga": row.goals_away if finished else None,
            "hth": hth if finished else None,
            "hta": hta if finished else None,
        }
    return out


def _yellows(db: Session, ids: set[int]) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = defaultdict(dict)
    if not ids:
        return out
    for fid, side, yc in db.execute(
        select(FixtureTeamStat.fixture_id, FixtureTeamStat.side, FixtureTeamStat.yellow_cards).where(
            FixtureTeamStat.fixture_id.in_(ids), FixtureTeamStat.yellow_cards.is_not(None)
        )
    ).all():
        if side in ("home", "away"):
            out[int(fid)][side] = int(yc)
    return out


def _league_standings(db: Session, pairs: set[tuple[int, int]]) -> dict[tuple[int, int], tuple[dict[int, int], bool]]:
    if not pairs:
        return {}
    games: dict[tuple[int, int], list[tuple[int, int, int, int]]] = defaultdict(list)
    rows = db.execute(
        select(Fixture.league_id, Fixture.season_id, Fixture.home_team_id, Fixture.away_team_id, Fixture.goals_home, Fixture.goals_away).where(
            Fixture.league_id.in_({p[0] for p in pairs}),
            Fixture.season_id.in_({p[1] for p in pairs}),
            Fixture.status.in_(FINISHED_STATUSES),
            Fixture.goals_home.is_not(None),
            Fixture.goals_away.is_not(None),
        )
    ).all()
    for lg, season, h, a, gh, ga in rows:
        if (lg, season) in pairs:
            games[(lg, season)].append((int(h), int(a), int(gh), int(ga)))
    return {p: standings(games.get(p, [])) for p in pairs}


def _quotes(fx: CecchinoTodayFixture) -> list[dict[str, Any]]:
    by_key: dict[str, Any] = {}
    for row in ((fx.kpi_panel_json or {}).get("rows") or []):
        if isinstance(row, dict) and row.get("market_key"):
            by_key[str(row["market_key"])] = row.get("quota_book")
    out = []
    for m in MARKETS:
        if m["key"] in by_key:
            q = by_key[m["key"]]
            out.append({"key": m["key"], "label": m["label"], "group": m["group"], "quota": float(q) if q else None})
    return out


def compute_day(db: Session, day: date) -> list[dict[str, Any]]:
    """Tutte le righe del giorno (senza note), ordinate per orario."""
    fixtures = db.execute(
        select(CecchinoTodayFixture)
        .where(CecchinoTodayFixture.scan_date == day, CecchinoTodayFixture.local_fixture_id.is_not(None))
        .order_by(CecchinoTodayFixture.kickoff.asc().nulls_last(), CecchinoTodayFixture.id.asc())
    ).scalars().all()
    if not fixtures:
        return []
    locals_ = {
        int(r.id): r
        for r in db.execute(
            select(Fixture.id, Fixture.home_team_id, Fixture.away_team_id, Fixture.league_id, Fixture.season_id).where(
                Fixture.id.in_({int(f.local_fixture_id) for f in fixtures})
            )
        ).all()
    }
    wanted: dict[int, dict[str, list[int]]] = {}
    all_ids: set[int] = set()
    for f in fixtures:
        snap = ((f.stats_snapshot_json or {}).get("input_snapshot")) or {}
        ids = {}
        for block, (key, _side) in _SNAPSHOT_KEYS.items():
            raw = ((snap.get(key) or {}).get("fixture_ids")) or []
            ids[block] = [int(x) for x in raw if _int(x) is not None]
            all_ids.update(ids[block])
        wanted[int(f.id)] = ids
    history = _history(db, all_ids)
    yellows = _yellows(db, all_ids)
    pairs = {(int(r.league_id), int(r.season_id)) for r in locals_.values()}
    tables = _league_standings(db, pairs)
    team_ids = {g["home"] for g in history.values()} | {g["away"] for g in history.values()}
    names = {int(i): n for i, n in db.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids))).all()} if team_ids else {}
    balance = {
        int(fid): (float(idx) if idx is not None else None, cls)
        for fid, idx, cls in db.execute(
            select(CecchinoBalanceV5Evaluation.today_fixture_id, CecchinoBalanceV5Evaluation.f36_index, CecchinoBalanceV5Evaluation.f36_class).where(
                CecchinoBalanceV5Evaluation.today_fixture_id.in_([int(f.id) for f in fixtures]),
                CecchinoBalanceV5Evaluation.is_current.is_(True),
            )
        ).all()
    }

    out: list[dict[str, Any]] = []
    for f in fixtures:
        loc = locals_.get(int(f.local_fixture_id))
        if loc is None:
            continue
        home, away = int(loc.home_team_id), int(loc.away_team_id)
        ranks, complete = tables.get((int(loc.league_id), int(loc.season_id)), ({}, False))
        games = {block: [history[i] for i in ids if i in history] for block, ids in wanted[int(f.id)].items()}
        # le "ultime 6 totali" della fotografia: si tengono le 5 piu' recenti (in ordine dalla piu' vecchia)
        games = {block: sorted(gs, key=lambda g: g["kickoff"] or datetime.min.replace(tzinfo=timezone.utc)) for block, gs in games.items()}
        blocks = {
            block: _block(games[block], home if side == "home" else away, ranks, names)
            for block, (_key, side) in _SNAPSHOT_KEYS.items()
        }
        if not any(b["enough"] for b in blocks.values()):
            continue
        idx, cls = balance.get(int(f.id), (None, None))
        kickoff = _aware(f.kickoff)
        out.append(
            {
                "today_fixture_id": int(f.id),
                "scan_date": f.scan_date.isoformat(),
                "kickoff": kickoff.isoformat() if kickoff else None,
                "country": f.country_name,
                "league": f.league_name,
                "home_team": f.home_team_name,
                "away_team": f.away_team_name,
                "eligible": f.eligibility_status == "eligible",
                "balance": {"index": round(idx, 1) if idx is not None else None, "class": cls} if cls or idx is not None else None,
                "blocks": blocks,
                "yellows": {
                    "home": _cards(games["forma_totale_casa"], home, yellows),
                    "away": _cards(games["forma_totale_fuori"], away, yellows),
                },
                "standings_complete": complete,
                "home_rank": ranks.get(home),
                "away_rank": ranks.get(away),
                "quotes": _quotes(f),
            }
        )
    return out


def day_rows(db: Session, day: date) -> list[dict[str, Any]]:
    hit = _cache.get(day)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    rows = compute_day(db, day)
    _cache[day] = (time.monotonic(), rows)
    for old in [d for d, (ts, _) in _cache.items() if time.monotonic() - ts > CACHE_SECONDS]:
        _cache.pop(old, None)
    return rows


def filter_rows(
    rows: list[dict[str, Any]],
    *,
    now: datetime,
    upcoming_only: bool,
    country: str | None,
    league: str | None,
    query: str | None,
) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    out = []
    for r in rows:
        if upcoming_only and r["kickoff"] and datetime.fromisoformat(r["kickoff"]) <= now:
            continue
        if country and r["country"] != country:
            continue
        if league and r["league"] != league:
            continue
        if q and q not in f"{r['home_team']} {r['away_team']} {r['league']} {r['country']}".lower():
            continue
        out.append(r)
    return out
