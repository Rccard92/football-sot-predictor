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
Dal 18/11/2026 (documento "Errori, modifiche, migliorie"): l'ora della gara e' quella della fotografia del
mattino (o quella nuova se la gara e' stata anticipata): una gara rinviata non prende piu' nella forma le gare
giocate dopo (FC Tulsa, 5 luglio, giocata il 6 agosto) e resta nel giorno originale come "rinviata", senza
"Aggiungi"; posizioni e classifica del riquadro sono quelle alla data; controllo dei dati delle squadre
(rosso = non si aggiunge, e dal 18/11 la gara e' esclusa anche da Today); gare mancanti alla fine.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.cecchino_balance_v5_evaluation import CecchinoBalanceV5Evaluation
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.fixture import Fixture
from app.models.fixture_team_stat import FixtureTeamStat
from app.models.team import Team
from app.models.season import Season
from app.services.analyst.form import (
    LeagueSeason,
    goal_form,
    ppg_level,
    pt_form,
    season_lengths,
    signs,
    strength,
    strength_ppg,
)
from app.services.analyst.leagues import league_admitted
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
_ROME = ZoneInfo("Europe/Rome")
MOVED_AFTER = timedelta(hours=12)  # ora del fornitore lontana da quella della fotografia: gara rinviata o spostata


def match_cutoff(scan_kickoff: datetime | None, fixture_kickoff: datetime | None) -> datetime | None:
    """Ora della gara per forma e classifica: la prima tra quella della fotografia del mattino e quella attuale.

    Una gara rinviata cambia ora nel nostro archivio (FC Tulsa: 5 luglio -> 6 agosto) ma la riga di Today resta
    nel giorno originale: la forma va presa a quella data, non a quella nuova."""
    times = [t for t in (_aware(scan_kickoff), _aware(fixture_kickoff)) if t is not None]
    return min(times) if times else None


def moved_to(scan_kickoff: datetime | None, fixture_kickoff: datetime | None, status: str | None) -> dict[str, Any] | None:
    """Gara rinviata o spostata rispetto alla fotografia del mattino (None se si gioca quando previsto)."""
    a, b = _aware(scan_kickoff), _aware(fixture_kickoff)
    if (status or "") in ("PST", "CANC", "ABD"):
        return {"status": status, "kickoff": b.isoformat() if b else None}
    if a is None or b is None or abs(b - a) <= MOVED_AFTER:
        return None
    return {"status": "moved", "kickoff": b.isoformat()}


def _moved_text(moved: dict[str, Any]) -> str:
    if moved["status"] == "CANC":
        return "Gara annullata"
    if moved["status"] == "ABD":
        return "Gara sospesa"
    if moved.get("kickoff") and moved["status"] == "moved":
        return "Gara spostata al " + datetime.fromisoformat(moved["kickoff"]).astimezone(_ROME).strftime("%d/%m")
    return "Gara rinviata"


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
    g: dict[str, Any],
    team: int,
    ranks: dict[int, int],
    names: dict[int, str],
    diff: float | None = None,
    diff_points: int | None = None,
    scored: bool = False,
) -> dict[str, Any]:
    """Una gara della forma. diff = punti a partita dell'avversaria meno i nostri alla data (dal 18/11/2026);
    diff_points = la vecchia differenza in punti (formula del 09/11), tenuta per confronto."""
    home = g["home"] == team
    gf, ga = (g["gh"], g["ga"]) if home else (g["ga"], g["gh"])
    hf, ha = (g["hth"], g["hta"]) if home else (g["hta"], g["hth"])
    opponent = g["away"] if home else g["home"]
    ft, ht = _outcome(gf, ga), _outcome(hf, ha)
    if not scored:
        # Classifica (riquadro): posizione nella classifica mostrata, come prima
        stronger = opponent in ranks and team in ranks and ranks[opponent] < ranks[team]
    else:
        # Tabella: avversaria piu' forte alla data della gara (dal 18/11/2026 di almeno 0,3 punti a partita)
        stronger = ppg_level(diff) == "strong"
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
        "diff_points": diff_points,
        "level": ppg_level(diff),
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
    rows = [
        _game(g, team, ranks, names, season.diff_ppg(team, g), season.diff(team, g), scored=True)
        if season
        else _game(g, team, ranks, names)
        for g in games
    ]
    points = sum(3 if r["ft_outcome"] == "V" else 1 if r["ft_outcome"] == "N" else 0 for r in rows)
    scored = sum(int(r["ft"].split("-")[0]) for r in rows if r["ft"])
    conceded = sum(int(r["ft"].split("-")[1]) for r in rows if r["ft"])
    halves = [r["ht"] for r in rows if r["ht"]]
    diffs = [r["diff"] for r in rows if r["diff"] is not None]
    avg = strength_ppg(diffs)
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
        # forza media in punti a partita (18/11/2026): da +0,3 avversarie piu' forti, da -0,3 piu' deboli
        "strength": avg,
        "strength_level": ppg_level(avg),
        "strength_points": strength([r["diff_points"] for r in rows if r.get("diff_points") is not None]),
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


def league_seasons(db: Session, pairs: set[tuple[int, int]]) -> dict[tuple[int, int], LeagueSeason]:
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
    lengths = _previous_season_lengths(db, pairs)
    return {p: LeagueSeason(games.get(p, []), lengths.get(p)) for p in pairs}


def _previous_season_lengths(db: Session, pairs: set[tuple[int, int]]) -> dict[tuple[int, int], dict[str, int]]:
    """Gare di campionato per squadra nella stagione precedente (stima delle gare che mancano, 18/11/2026)."""
    try:
        current = {
            int(r.id): (int(r.league_id), int(r.year))
            for r in db.execute(select(Season.id, Season.league_id, Season.year).where(Season.id.in_({p[1] for p in pairs}))).all()
        }
        wanted = {(lg, yr - 1) for lg, yr in current.values()}
        if not wanted:
            return {}
        previous = {
            (int(r.league_id), int(r.year)): int(r.id)
            for r in db.execute(
                select(Season.id, Season.league_id, Season.year).where(
                    Season.league_id.in_({w[0] for w in wanted}), Season.year.in_({w[1] for w in wanted})
                )
            ).all()
        }
        ids = set(previous.values())
        by_season: dict[int, list[tuple[int, int, str | None]]] = defaultdict(list)
        if ids:
            for r in db.execute(
                select(Fixture.season_id, Fixture.home_team_id, Fixture.away_team_id, Fixture.round).where(
                    Fixture.season_id.in_(ids), Fixture.status.in_(FINISHED_STATUSES)
                )
            ).all():
                by_season[int(r.season_id)].append((int(r.home_team_id), int(r.away_team_id), r.round))
        out: dict[tuple[int, int], dict[str, int]] = {}
        for pair in pairs:
            lg_yr = current.get(pair[1])
            prev_id = previous.get((lg_yr[0], lg_yr[1] - 1)) if lg_yr else None
            if prev_id is not None and by_season.get(prev_id):
                out[pair] = season_lengths(by_season[prev_id])
        return out
    except Exception:  # pragma: no cover - la stima e' solo un'informazione in piu'
        return {}


ODDS_OLD_HOURS = 12


def _reliability(
    *,
    problems: list[str],
    future_games: list[dict[str, Any]],
    standings_complete: bool,
    odds_at: datetime | None,
    kickoff: datetime | None,
    cards: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Indice di affidabilita' della gara (Modifica 1 di Giovanni, 18/11/2026).

    Rosso (gara esclusa): dati della squadra sbagliati (due gare a meno di 12 ore, gare oltre la mediana + 4),
    forma con gare giocate dopo la partita. Il campionato non ammesso non arriva qui: e' gia' fuori dalla Tabella.
    Giallo (solo da leggere): classifica incompleta, quote lette piu' di 12 ore prima del via, ammonizioni mancanti.
    Verde: tutto a posto.
    Non usati, perche' con i nostri dati non possono scattare: "punti diversi da 3V+N" e "somma delle gare
    dispari" (la classifica la ricostruiamo noi dai risultati, quindi e' sempre coerente)."""
    red = list(problems)
    if future_games:
        red.append("Forma con gare giocate dopo la partita")
    yellow: list[str] = []
    if not standings_complete:
        yellow.append("Classifica incompleta (mancano alcuni risultati)")
    odds_at, kickoff = _aware(odds_at), _aware(kickoff)
    if odds_at and kickoff and (kickoff - odds_at).total_seconds() > ODDS_OLD_HOURS * 3600:
        yellow.append(f"Quote lette più di {ODDS_OLD_HOURS} ore prima della gara")
    if not all((c or {}).get("available") for c in cards.values()):
        yellow.append("Ammonizioni mancanti")
    level = "red" if red else "yellow" if yellow else "green"
    return {"level": level, "red": red, "yellow": yellow}


def data_check(season: LeagueSeason, target: dict[str, Any], teams: dict[str, tuple[int, str | None]]) -> list[str]:
    """Problemi nei dati delle due squadre alla data della gara (vuoto = tutto a posto)."""
    out: list[str] = []
    for team_id, name in teams.values():
        out += [f"{name or 'Squadra'}: {p}" for p in season.data_problems(int(team_id), target)]
    return out


_CHECK_CACHE_SECONDS = 300
_check_cache: dict[tuple[int, int], tuple[float, LeagueSeason]] = {}


def fixture_data_problems(db: Session, local_fixture_id: int, *, scan_kickoff: datetime | None = None) -> list[str]:
    """Controllo dei dati delle squadre per lo scan di Today (18/11/2026): se non e' vuoto la gara si esclude.

    Le gare dello stesso campionato si leggono una volta ogni 5 minuti (il sabato ci sono decine di gare per lega)."""
    loc = db.get(Fixture, int(local_fixture_id))
    if loc is None or loc.league_id is None or loc.season_id is None:
        return []
    pair = (int(loc.league_id), int(loc.season_id))
    hit = _check_cache.get(pair)
    if hit and time.monotonic() - hit[0] < _CHECK_CACHE_SECONDS:
        season = hit[1]
    else:
        season = league_seasons(db, {pair})[pair]
        _check_cache[pair] = (time.monotonic(), season)
        for old in [p for p, (ts, _) in _check_cache.items() if time.monotonic() - ts > _CHECK_CACHE_SECONDS]:
            _check_cache.pop(old, None)
    names = {int(i): n for i, n in db.execute(select(Team.id, Team.name).where(Team.id.in_({int(loc.home_team_id), int(loc.away_team_id)}))).all()}
    target = {"id": int(loc.id), "kickoff": match_cutoff(scan_kickoff, loc.kickoff_at)}
    teams = {side: (int(t), names.get(int(t))) for side, t in (("home", loc.home_team_id), ("away", loc.away_team_id))}
    return data_check(season, target, teams)


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
    """Classifica completa del campionato della partita: totale, casa e trasferta, dai risultati nel DB.

    Dal 18/11/2026 e' la classifica ALLA DATA della gara (solo gare finite prima del calcio d'inizio, stesso
    torneo, niente eliminazione diretta): aperta dopo la partita non contiene piu' la partita stessa."""
    fx = db.get(CecchinoTodayFixture, today_fixture_id)
    if fx is None or fx.local_fixture_id is None:
        return None
    loc = db.get(Fixture, int(fx.local_fixture_id))
    if loc is None or loc.league_id is None or loc.season_id is None:
        return None
    pair = (int(loc.league_id), int(loc.season_id))
    season = league_seasons(db, {pair})[pair]
    target = {"id": int(loc.id), "kickoff": match_cutoff(fx.kickoff, loc.kickoff_at)}
    rows = [(int(g["home"]), int(g["away"]), int(g["gh"]), int(g["ga"])) for g in season.table_games_before(target)]
    team_ids = {r[0] for r in rows} | {r[1] for r in rows} | {int(loc.home_team_id), int(loc.away_team_id)}
    names = {int(i): n for i, n in db.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids))).all()}
    total = _table(rows, names, "total")
    played = [r["played"] for r in total]
    ranks = {r["team_id"]: r["rank"] for r in total}
    # ultime 5 partite delle due squadre, in totale, in casa e fuori (08/11/2026): al clic sulla squadra la
    # classifica accende le avversarie e il box sotto mostra i risultati (posizione = classifica totale)
    recent: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for team in (int(loc.home_team_id), int(loc.away_team_id)):
        recent[str(team)] = {
            kind: [_game(g, team, ranks, names) for g in season.recent(team, target, side=side, limit=MAX_GAMES)]
            for kind, side in (("total", None), ("home", "home"), ("away", "away"))
        }
    now = datetime.now(timezone.utc)
    return {
        "as_of": target["kickoff"].isoformat() if target["kickoff"] else None,
        "remaining": {
            str(int(loc.home_team_id)): season.remaining(int(loc.home_team_id), target, now=now),
            str(int(loc.away_team_id)): season.remaining(int(loc.away_team_id), target, now=now),
        },
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
    # dal 18/11/2026: solo i campionati ammessi (campionati_ammessi.txt, decisione di Giovanni)
    fixtures = [f for f in fixtures if league_admitted(f.country_name, f.league_name)]
    if not fixtures:
        return []
    locals_ = {
        int(r.id): r
        for r in db.execute(
            select(
                Fixture.id, Fixture.kickoff_at, Fixture.home_team_id, Fixture.away_team_id, Fixture.league_id, Fixture.season_id, Fixture.status
            ).where(Fixture.id.in_({int(f.local_fixture_id) for f in fixtures}))
        ).all()
    }
    pairs = {(int(r.league_id), int(r.season_id)) for r in locals_.values()}
    seasons = league_seasons(db, pairs)
    now = datetime.now(timezone.utc)
    picked: dict[int, dict[str, list[dict[str, Any]]]] = {}
    lacking: dict[int, dict[str, list[dict[str, Any]]]] = {}
    targets: dict[int, dict[str, Any]] = {}
    for f in fixtures:
        loc = locals_.get(int(f.local_fixture_id))
        if loc is None:
            continue
        season = seasons[(int(loc.league_id), int(loc.season_id))]
        # dal 18/11/2026: ora della fotografia del mattino (gara rinviata = forma alla data originale)
        target = {"id": int(loc.id), "kickoff": match_cutoff(f.kickoff, loc.kickoff_at)}
        targets[int(f.id)] = target
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
        target = targets[int(f.id)]
        # classifica alla data della gara (dal 18/11/2026; prima era quella di oggi)
        ranks, complete = standings([(g["home"], g["away"], int(g["gh"]), int(g["ga"])) for g in season.table_games_before(target)])
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
        problems = data_check(season, target, {"home": (home, f.home_team_name), "away": (away, f.away_team_name)})
        moved = moved_to(f.kickoff, loc.kickoff_at, loc.status)
        reasons = []
        if problems:
            reasons.append("Dati della squadra da verificare (gara esclusa)")
        if moved:
            reasons.append(_moved_text(moved))
        if short:
            reasons.append("Meno di 3 gare in stagione: " + " e ".join(short))
        idx, cls = balance.get(int(f.id), (None, None))
        quotes = _quotes(f)
        main = {q["key"]: q["quota"] for q in quotes}
        kickoff = _aware(f.kickoff)
        cards = {
            "home": _cards(games["forma_totale_casa"], home, yellows),
            "away": _cards(games["forma_totale_fuori"], away, yellows),
        }
        reliability = _reliability(
            problems=problems,
            future_games=[
                g for gs in games.values() for g in gs if target["kickoff"] and g["kickoff"] and g["kickoff"] >= target["kickoff"]
            ],
            standings_complete=complete,
            odds_at=odds_read_at(f),
            kickoff=target["kickoff"],
            cards=cards,
        )
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
                "yellows": cards,
                "standings_complete": complete,
                "home_rank": ranks.get(home),
                "away_rank": ranks.get(away),
                "quotes": quotes,
                "match_type": match_type(*(main.get(k) for k in ("HOME", "DRAW", "AWAY"))),
                "editable": not reasons,
                "not_editable_reason": " · ".join(reasons) if reasons else None,
                "goal_form": goal_form(blocks["forma_casa"], blocks["forma_fuori"]),
                # riquadro primo tempo con la media delle due squadre e avviso sopra 1,5 gol PT (18/11/2026)
                "pt_form": pt_form(blocks["forma_casa"], blocks["forma_fuori"]),
                # indice di affidabilita' dei dati della gara (18/11/2026)
                "reliability": reliability,
                # ora in cui il tool ha letto le quote (09/11/2026): sopra le quote, avviso oltre 12 ore (18/11)
                "odds_checked_at": _iso_or_none(odds_read_at(f)),
                # dal 18/11/2026
                "data_check": {"level": "red", "problems": problems} if problems else {"level": "ok", "problems": []},
                "moved": moved,
                "remaining": {
                    "home": season.remaining(home, target, now=now),
                    "away": season.remaining(away, target, now=now),
                },
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
