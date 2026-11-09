"""Tabella analisi (dal 05/11/2026): una riga per partita di Cecchino Today con forma, gol e gialli recenti.

Bozza di Giovanni (04/11/2026) e decisioni del 05/11/2026:
- forma = punti 3/1/0 sul risultato finale; sotto, i risultati di primo tempo e finali, l'ultima gara a destra;
  "Forma casa" = gare in casa della squadra di casa, "Forma fuori" = gare fuori dell'ospite, "Forma totale" = tutte;
- da 3 a 5 gare: sotto le 3 la cella resta vuota; la partita entra se almeno un blocco ha 3 gare;
- vittoria verde, sconfitta rossa, pareggio grigio; con la cornice i risultati contro squadre piu' in alto
  nella classifica di oggi, ricostruita dai risultati (non ne abbiamo una salvata); dal 06/11 anche i pareggi;
- gol fatti contro subiti sulle stesse gare, del primo tempo e finali, per tutti e quattro i blocchi (06/11);
  gialli fatti e subiti sulle ultime 5 gare totali, con la media a partita, solo dove ci sono le statistiche
  (nessuna chiamata API in piu');
- classifica completa del campionato: totale, casa e trasferta (06/11);
- solo le partite calcolate da Cecchino (07/11): senza quota Cecchino e pannello KPI non c'e' analisi da fare;
- tipo di partita dalle quote 1-X-2 con la regola di Giovanni (vedi rules.py), solo in questa pagina;
- equilibrio = indice e classe gia' salvati da Today (cecchino_balance_v5_evaluations);
- quote = tutte quelle del pannello KPI.
Dal 09/11/2026 (documento "Modifiche" di Giovanni, vedi form.py): le gare recenti NON arrivano piu' dalla
fotografia del calcolo Cecchino (che a inizio stagione completa con la stagione passata) ma dalle gare del
campionato nella stagione in corso; ogni risultato ha il numero +/- (differenza punti alla data della gara) e la
cornice va con quel numero (da +3), non piu' con la classifica di oggi; ogni blocco ha forza media e segni;
la partita non si puo' aggiungere al diario se la squadra di casa ha meno di 3 gare in casa o l'ospite meno di
3 fuori; avviso "forma da gol" sopra 2,7 gol a partita.
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
from app.services.analyst.form import LeagueSeason, diff_level, goal_form, signs, strength
from app.services.analyst.journal import MARKETS, odds_read_at
from app.services.analyst.rules import match_type

MIN_GAMES = 3
MAX_GAMES = 5
CACHE_SECONDS = 600  # la fotografia del mattino non cambia: si ricalcola al massimo ogni 10 minuti
_cache: dict[date, tuple[float, list[dict[str, Any]]]] = {}

# blocco -> (squadra: "home" | "away", gare: "home" = solo in casa, "away" = solo fuori, None = tutte)
_BLOCKS = {
    "forma_casa": ("home", "home"),
    "forma_fuori": ("away", "away"),
    "forma_totale_casa": ("home", None),
    "forma_totale_fuori": ("away", None),
}
_VOID_STATUSES = frozenset({"PST", "CANC", "ABD", "AWD", "WO"})


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso_or_none(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


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


def _game(
    g: dict[str, Any], team: int, ranks: dict[int, int], names: dict[int, str], diff: int | None = None
) -> dict[str, Any]:
    home = g["home"] == team
    gf, ga = (g["gh"], g["ga"]) if home else (g["ga"], g["gh"])
    hf, ha = (g["hth"], g["hta"]) if home else (g["hta"], g["hth"])
    opponent = g["away"] if home else g["home"]
    ft, ht = _outcome(gf, ga), _outcome(hf, ha)
    if diff is None:
        # Classifica (riquadro): posizione di oggi, come prima
        stronger = opponent in ranks and team in ranks and ranks[opponent] < ranks[team]
    else:
        # Tabella (dal 09/11/2026): avversaria piu' forte di almeno 3 punti alla data della gara
        stronger = diff_level(diff) == "strong"
    return {
        "date": g["kickoff"].date().isoformat() if g["kickoff"] else None,
        "opponent_id": opponent,
        "opponent": names.get(opponent),
        "opponent_rank": ranks.get(opponent),  # posizione nella classifica di oggi
        "home": home,
        "ft": f"{gf}-{ga}" if ft else None,  # sempre dal punto di vista della squadra in esame
        "ht": f"{hf}-{ha}" if ht else None,
        "ft_outcome": ft,
        "ht_outcome": ht,
        "diff": diff,
        "level": diff_level(diff),
        # cornice e grassetto: vittorie, pareggi e sconfitte (pareggi dal 06/11/2026)
        "bold_ft": bool(stronger and ft),
        "bold_ht": bool(stronger and ht),
    }


def _block(
    games: list[dict[str, Any]],
    team: int,
    ranks: dict[int, int],
    names: dict[int, str],
    season: LeagueSeason | None = None,
    missing: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    games = [g for g in games if g["gh"] is not None and g["ga"] is not None][-MAX_GAMES:]
    lacking = [g["kickoff"].date().isoformat() for g in (missing or []) if g["kickoff"]]
    if len(games) < MIN_GAMES:
        return {"games": len(games), "enough": False, "missing_results": lacking}
    rows = [_game(g, team, ranks, names, season.diff(team, g) if season else None) for g in games]
    points = sum(3 if r["ft_outcome"] == "V" else 1 if r["ft_outcome"] == "N" else 0 for r in rows)
    scored = sum(int(r["ft"].split("-")[0]) for r in rows if r["ft"])
    conceded = sum(int(r["ft"].split("-")[1]) for r in rows if r["ft"])
    halves = [r["ht"] for r in rows if r["ht"]]
    diffs = [r["diff"] for r in rows if r["diff"] is not None]
    avg = strength(diffs)
    return {
        "games": len(rows),
        "enough": True,
        "points": points,
        "max_points": 3 * len(rows),
        "scored": scored,
        "conceded": conceded,
        # primo tempo: solo le gare con il parziale noto
        "ht_games": len(halves),
        "ht_scored": sum(int(h.split("-")[0]) for h in halves),
        "ht_conceded": sum(int(h.split("-")[1]) for h in halves),
        "results": rows,
        "team_rank": ranks.get(team),
        # dal 09/11/2026
        "strength": avg,
        "strength_level": None if avg is None else "strong" if avg >= 3 else "weak" if avg <= -3 else "even",
        "signs": signs(rows),
        "missing_results": lacking,
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
    return {
        "games": with_data,
        "available": True,
        "own": own,
        "opponents": conceded,
        "own_avg": round(own / with_data, 1),
        "opponents_avg": round(conceded / with_data, 1),
    }


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


def _league_seasons(db: Session, pairs: set[tuple[int, int]]) -> dict[tuple[int, int], LeagueSeason]:
    """Tutte le gare (anche da giocare) di ogni campionato e stagione: forma, classifica alla data, risultati mancanti."""
    if not pairs:
        return {}
    postgres = db.get_bind().dialect.name == "postgresql"
    cols = [
        Fixture.id,
        Fixture.league_id,
        Fixture.season_id,
        Fixture.kickoff_at,
        Fixture.home_team_id,
        Fixture.away_team_id,
        Fixture.goals_home,
        Fixture.goals_away,
        Fixture.status,
        Fixture.round,
    ]
    if postgres:
        cols += [
            func.jsonb_extract_path_text(Fixture.raw_json, "score", "halftime", "home"),
            func.jsonb_extract_path_text(Fixture.raw_json, "score", "halftime", "away"),
        ]
    else:
        cols.append(Fixture.raw_json)
    games: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    rows = db.execute(
        select(*cols).where(Fixture.league_id.in_({p[0] for p in pairs}), Fixture.season_id.in_({p[1] for p in pairs}))
    ).all()
    for row in rows:
        pair = (int(row.league_id), int(row.season_id))
        if pair not in pairs:
            continue
        if postgres:
            hth, hta = _int(row[10]), _int(row[11])
        else:
            ht = (((row[10] or {}).get("score") or {}).get("halftime")) or {}
            hth, hta = _int(ht.get("home")), _int(ht.get("away"))
        status = row.status or ""
        finished = status in FINISHED_STATUSES and row.goals_home is not None and row.goals_away is not None
        games[pair].append(
            {
                "id": int(row.id),
                "kickoff": _aware(row.kickoff_at),
                "home": int(row.home_team_id),
                "away": int(row.away_team_id),
                "gh": row.goals_home if finished else None,
                "ga": row.goals_away if finished else None,
                "hth": hth if finished else None,
                "hta": hta if finished else None,
                "round": row.round,
                "void": status in _VOID_STATUSES or status in FINISHED_STATUSES,
            }
        )
    return {p: LeagueSeason(games.get(p, [])) for p in pairs}


def _table(rows: list[tuple[int, int, int, int]], names: dict[int, str], side: str) -> list[dict[str, Any]]:
    """Una classifica: "total", "home" (solo gare in casa) o "away" (solo gare fuori). Ordine come standings()."""
    acc: dict[int, dict[str, int]] = defaultdict(lambda: {"played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "points": 0})
    for h, a, gh, ga in rows:
        for team, gf, gs, is_home in ((h, gh, ga, True), (a, ga, gh, False)):
            if (side == "home" and not is_home) or (side == "away" and is_home):
                continue
            r = acc[team]
            r["played"] += 1
            r["gf"] += gf
            r["ga"] += gs
            if gf > gs:
                r["won"] += 1
                r["points"] += 3
            elif gf == gs:
                r["drawn"] += 1
                r["points"] += 1
            else:
                r["lost"] += 1
    order = sorted(acc, key=lambda t: (-acc[t]["points"], -(acc[t]["gf"] - acc[t]["ga"]), -acc[t]["gf"], names.get(t) or ""))
    return [
        {"rank": i + 1, "team_id": t, "team": names.get(t), **acc[t], "gd": acc[t]["gf"] - acc[t]["ga"]}
        for i, t in enumerate(order)
    ]


def league_tables(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    """Classifica completa del campionato della partita: totale, casa e trasferta, dai risultati nel DB."""
    fx = db.get(CecchinoTodayFixture, today_fixture_id)
    if fx is None or fx.local_fixture_id is None:
        return None
    loc = db.get(Fixture, int(fx.local_fixture_id))
    if loc is None:
        return None
    played_games = db.execute(
        select(Fixture.id, Fixture.kickoff_at, Fixture.home_team_id, Fixture.away_team_id, Fixture.goals_home, Fixture.goals_away).where(
            Fixture.league_id == loc.league_id,
            Fixture.season_id == loc.season_id,
            Fixture.status.in_(FINISHED_STATUSES),
            Fixture.goals_home.is_not(None),
            Fixture.goals_away.is_not(None),
        )
    ).all()
    rows = [(int(h), int(a), int(gh), int(ga)) for _id, _ko, h, a, gh, ga in played_games]
    team_ids = {r[0] for r in rows} | {r[1] for r in rows} | {int(loc.home_team_id), int(loc.away_team_id)}
    names = {int(i): n for i, n in db.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids))).all()}
    total = _table(rows, names, "total")
    played = [r["played"] for r in total]
    ranks = {r["team_id"]: r["rank"] for r in total}
    # ultime 5 partite delle due squadre, in totale, in casa e fuori (08/11/2026): al clic sulla squadra la
    # classifica accende le avversarie e il box sotto mostra i risultati (posizione = classifica totale)
    recent: dict[str, dict[str, list[dict[str, Any]]]] = {}
    ordered = sorted(played_games, key=lambda g: (_aware(g.kickoff_at) or datetime.min.replace(tzinfo=timezone.utc), g.id))
    picked: dict[int, dict[str, list[int]]] = {}
    for team in (int(loc.home_team_id), int(loc.away_team_id)):
        mine = [g for g in ordered if int(g.home_team_id) == team or int(g.away_team_id) == team]
        picked[team] = {
            "total": [int(g.id) for g in mine][-MAX_GAMES:],
            "home": [int(g.id) for g in mine if int(g.home_team_id) == team][-MAX_GAMES:],
            "away": [int(g.id) for g in mine if int(g.away_team_id) == team][-MAX_GAMES:],
        }
    history = _history(db, {i for scopes in picked.values() for ids in scopes.values() for i in ids})
    for team, scopes in picked.items():
        recent[str(team)] = {
            kind: [_game(history[i], team, ranks, names) for i in ids if i in history] for kind, ids in scopes.items()
        }
    return {
        "today_fixture_id": int(fx.id),
        "league": fx.league_name,
        "country": fx.country_name,
        "home_team_id": int(loc.home_team_id),
        "away_team_id": int(loc.away_team_id),
        "games": len(rows),
        "complete": bool(played) and max(played) - min(played) <= 2,
        "tables": {"total": total, "home": _table(rows, names, "home"), "away": _table(rows, names, "away")},
        "recent": recent,
    }


def _quotes(fx: CecchinoTodayFixture) -> list[dict[str, Any]]:
    by_key: dict[str, Any] = {}
    by_cecchino: dict[str, Any] = {}
    for row in ((fx.kpi_panel_json or {}).get("rows") or []):
        if isinstance(row, dict) and row.get("market_key"):
            by_key[str(row["market_key"])] = row.get("quota_book")
            by_cecchino[str(row["market_key"])] = row.get("quota_cecchino")
    out = []
    for m in MARKETS:
        if m["key"] in by_key:
            q = by_key[m["key"]]
            qc = by_cecchino.get(m["key"])
            out.append(
                {
                    "key": m["key"],
                    "label": m["label"],
                    "group": m["group"],
                    "quota": float(q) if q else None,
                    "quota_cecchino": float(qc) if qc else None,
                }
            )
    return out


def compute_day(db: Session, day: date) -> list[dict[str, Any]]:
    """Tutte le righe del giorno (senza note), ordinate per orario."""
    fixtures = db.execute(
        select(CecchinoTodayFixture)
        .where(
            CecchinoTodayFixture.scan_date == day,
            CecchinoTodayFixture.local_fixture_id.is_not(None),
            # solo le partite calcolate da Cecchino (07/11/2026)
            CecchinoTodayFixture.eligibility_status == "eligible",
        )
        .order_by(CecchinoTodayFixture.kickoff.asc().nulls_last(), CecchinoTodayFixture.id.asc())
    ).scalars().all()
    if not fixtures:
        return []
    locals_ = {
        int(r.id): r
        for r in db.execute(
            select(Fixture.id, Fixture.kickoff_at, Fixture.home_team_id, Fixture.away_team_id, Fixture.league_id, Fixture.season_id).where(
                Fixture.id.in_({int(f.local_fixture_id) for f in fixtures})
            )
        ).all()
    }
    pairs = {(int(r.league_id), int(r.season_id)) for r in locals_.values()}
    seasons = _league_seasons(db, pairs)
    # classifica di oggi (posizioni accanto ai nomi, invariata): tutte le gare finite della stagione
    tables = {
        p: standings([(g["home"], g["away"], int(g["gh"]), int(g["ga"])) for g in season.finished]) for p, season in seasons.items()
    }
    now = datetime.now(timezone.utc)
    picked: dict[int, dict[str, list[dict[str, Any]]]] = {}
    lacking: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for f in fixtures:
        loc = locals_.get(int(f.local_fixture_id))
        if loc is None:
            continue
        season = seasons[(int(loc.league_id), int(loc.season_id))]
        target = {"id": int(loc.id), "kickoff": _aware(loc.kickoff_at)}
        teams = {"home": int(loc.home_team_id), "away": int(loc.away_team_id)}
        picked[int(f.id)] = {
            block: season.recent(teams[who], target, side=side, limit=MAX_GAMES) for block, (who, side) in _BLOCKS.items()
        }
        lacking[int(f.id)] = {
            block: season.missing_before(teams[who], target, now=now, side=side) for block, (who, side) in _BLOCKS.items()
        }
    shown_ids = {int(g["id"]) for blocks in picked.values() for gs in blocks.values() for g in gs}
    yellows = _yellows(db, shown_ids)
    team_ids = {g[k] for blocks in picked.values() for gs in blocks.values() for g in gs for k in ("home", "away")}
    team_ids |= {int(r.home_team_id) for r in locals_.values()} | {int(r.away_team_id) for r in locals_.values()}
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
        if loc is None or int(f.id) not in picked:
            continue
        pair = (int(loc.league_id), int(loc.season_id))
        season = seasons[pair]
        home, away = int(loc.home_team_id), int(loc.away_team_id)
        ranks, complete = tables.get(pair, ({}, False))
        games = picked[int(f.id)]
        blocks = {
            block: _block(games[block], home if who == "home" else away, ranks, names, season, lacking[int(f.id)][block])
            for block, (who, _side) in _BLOCKS.items()
        }
        if not any(b["enough"] for b in blocks.values()):
            continue
        # meno di 3 gare in casa (squadra di casa) o fuori (ospite) nella stagione: non si aggiunge al diario
        short = [
            f"{f.home_team_name} ha {blocks['forma_casa']['games']} gare in casa" if blocks["forma_casa"]["games"] < MIN_GAMES else None,
            f"{f.away_team_name} ha {blocks['forma_fuori']['games']} gare fuori" if blocks["forma_fuori"]["games"] < MIN_GAMES else None,
        ]
        short = [s for s in short if s]
        idx, cls = balance.get(int(f.id), (None, None))
        quotes = _quotes(f)
        main = {q["key"]: q["quota"] for q in quotes}
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
                "quotes": quotes,
                "match_type": match_type(*(main.get(k) for k in ("HOME", "DRAW", "AWAY"))),
                "editable": not short,
                "not_editable_reason": ("Meno di 3 gare in stagione: " + " e ".join(short)) if short else None,
                "goal_form": goal_form(blocks["forma_casa"], blocks["forma_fuori"]),
                # ora in cui il tool ha letto le quote (09/11/2026): sopra le quote, avviso oltre 6 ore
                "odds_checked_at": _iso_or_none(odds_read_at(f)),
            }
        )
    return out


def row_for(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    """La riga della Tabella di una partita (per il controllo di "Aggiungi al diario")."""
    fx = db.get(CecchinoTodayFixture, today_fixture_id)
    if fx is None:
        return None
    return next((r for r in day_rows(db, fx.scan_date) if r["today_fixture_id"] == int(today_fixture_id)), None)


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
