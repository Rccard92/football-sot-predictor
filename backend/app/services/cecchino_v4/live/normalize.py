"""Funzioni pure: dalle forme API-Football v3 alle colonne delle tabelle V4.

Nessun accesso a database o rete. Le chiavi di mercato seguono docs/v4/API.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services.cecchino_v4.constants import LEAGUE_BY_API_ID

ROME_TZ = ZoneInfo("Europe/Rome")

FINAL_STATUSES: frozenset[str] = frozenset({"FT", "AET", "PEN"})
LINEUPS_OFFICIAL = "ufficiali"
LINEUPS_UNKNOWN = "non_note"


# --- utilita' ---------------------------------------------------------------------------------
def _int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).strip().rstrip("%")))
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def parse_api_datetime(raw: str | None, *, timestamp: int | None = None) -> datetime | None:
    """ISO 8601 API-Football ("2026-09-21T18:45:00+00:00") -> datetime UTC; fallback sul timestamp."""
    if raw:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    if timestamp is not None:
        try:
            return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    return None


def season_label_from_api(season: int | None) -> str:
    """API season 2025 -> "2025/2026"."""
    y = int(season or 0)
    return f"{y}/{y + 1}"


def api_season_for(day: date) -> int:
    """Stagione API-Football in corso in una data: da luglio e' l'anno corrente, prima l'anno precedente."""
    return day.year if day.month >= 7 else day.year - 1


def rome_date(dt: datetime) -> date:
    return dt.astimezone(ROME_TZ).date()


def snapshot_kind_for(now: datetime) -> str:
    """Istantanea del registro quote per ora di Roma: <12 mattina, <17 pomeriggio, altrimenti sera."""
    hour = now.astimezone(ROME_TZ).hour
    if hour < 12:
        return "mattina"
    if hour < 17:
        return "pomeriggio"
    return "sera"


# --- fixture -------------------------------------------------------------------------------------
def normalize_fixture(item: dict[str, Any]) -> dict[str, Any] | None:
    """Voce di /fixtures -> campi di `CecchinoV4Fixture` (None se il campionato non e' tra i 16)."""
    fx = item.get("fixture") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    score = item.get("score") or {}
    try:
        api_league_id = int(league.get("id"))
    except (TypeError, ValueError):
        return None
    lg = LEAGUE_BY_API_ID.get(api_league_id)
    if lg is None:
        return None
    kickoff = parse_api_datetime(fx.get("date"), timestamp=fx.get("timestamp"))
    if kickoff is None or fx.get("id") is None:
        return None
    home, away = teams.get("home") or {}, teams.get("away") or {}
    if home.get("id") is None or away.get("id") is None:
        return None
    status = str(((fx.get("status") or {}).get("short")) or "NS")[:8]
    ht = score.get("halftime") or {}
    ft = score.get("fulltime") or {}
    ft_home = _int(ft.get("home")) if ft.get("home") is not None else _int(goals.get("home"))
    ft_away = _int(ft.get("away")) if ft.get("away") is not None else _int(goals.get("away"))
    venue = fx.get("venue") or {}
    return {
        "api_fixture_id": int(fx["id"]),
        "league_code": lg.code,
        "api_league_id": api_league_id,
        "competition": lg.competition,
        "season_label": season_label_from_api(league.get("season")),
        "round": (str(league.get("round"))[:64] if league.get("round") else None),
        "match_date": rome_date(kickoff),
        "kickoff_at": kickoff,
        "status": status,
        "home_team_api_id": int(home["id"]),
        "away_team_api_id": int(away["id"]),
        "home_team": str(home.get("name") or "")[:128],
        "away_team": str(away.get("name") or "")[:128],
        "referee": (str(fx.get("referee"))[:128] if fx.get("referee") else None),
        "venue_city": (str(venue.get("city"))[:128] if venue.get("city") else None),
        "ft_home": ft_home if status in FINAL_STATUSES or ft_home is not None else None,
        "ft_away": ft_away if status in FINAL_STATUSES or ft_away is not None else None,
        "ht_home": _int(ht.get("home")),
        "ht_away": _int(ht.get("away")),
    }


# --- statistiche -----------------------------------------------------------------------------------
_STAT_TYPES: dict[str, str] = {
    "total shots": "shots",
    "shots on goal": "sot",
    "shots on target": "sot",
    "shots insidebox": "shots_inside",
    "shots inside box": "shots_inside",
    "shots outsidebox": "shots_outside",
    "shots outside box": "shots_outside",
    "blocked shots": "blocked",
    "goalkeeper saves": "saves",
    "corner kicks": "corners",
    "fouls": "fouls",
    "yellow cards": "yellow",
    "red cards": "red",
    "ball possession": "possession",
    "expected_goals": "xg",
    "expected goals": "xg",
    "offsides": "offsides",
}
STAT_KEYS: tuple[str, ...] = (
    "shots", "sot", "shots_inside", "shots_outside", "blocked", "saves", "corners", "fouls",
    "yellow", "red", "possession", "xg", "offsides",
)


def _side_for(team_id: Any, home_id: int, away_id: int) -> str | None:
    tid = _int(team_id)
    if tid == int(home_id):
        return "home"
    if tid == int(away_id):
        return "away"
    return None


def normalize_statistics(items: list[dict[str, Any]], home_team_api_id: int, away_team_api_id: int) -> dict[str, Any] | None:
    """/fixtures/statistics -> stats_json {"home": {...}, "away": {...}}; None se manca una squadra."""
    out: dict[str, dict[str, Any]] = {}
    for entry in items or []:
        side = _side_for((entry.get("team") or {}).get("id"), home_team_api_id, away_team_api_id)
        if side is None:
            continue
        stats: dict[str, Any] = {k: None for k in STAT_KEYS}
        for st in entry.get("statistics") or []:
            key = _STAT_TYPES.get(str(st.get("type") or "").strip().lower())
            if key is None:
                continue
            stats[key] = _float(st.get("value")) if key == "xg" else _int(st.get("value"))
        out[side] = stats
    if "home" not in out or "away" not in out:
        return None
    return out


# --- eventi -------------------------------------------------------------------------------------------
_EVENT_TYPES = {"goal": "goal", "card": "card", "subst": "subst", "var": "var"}


def normalize_events(items: list[dict[str, Any]], home_team_api_id: int, away_team_api_id: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in items or []:
        side = _side_for((ev.get("team") or {}).get("id"), home_team_api_id, away_team_api_id)
        t = ev.get("time") or {}
        kind = _EVENT_TYPES.get(str(ev.get("type") or "").strip().lower(), str(ev.get("type") or "").lower())
        player = ev.get("player") or {}
        assist = ev.get("assist") or {}
        out.append(
            {
                "minute": _int(t.get("elapsed")),
                "extra": _int(t.get("extra")),
                "type": kind,
                "team": side,
                "player": player.get("name"),
                "player_id": _int(player.get("id")),
                "assist": assist.get("name"),
                "assist_id": _int(assist.get("id")),
                "detail": ev.get("detail"),
                "comments": ev.get("comments"),
            }
        )
    out.sort(key=lambda e: ((e["minute"] or 0), (e["extra"] or 0)))
    return out


# --- formazioni --------------------------------------------------------------------------------------
def _players(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out = []
    for r in rows or []:
        p = r.get("player") or {}
        if p.get("id") is None and not p.get("name"):
            continue
        out.append({"id": _int(p.get("id")), "name": p.get("name"), "pos": p.get("pos"), "number": _int(p.get("number")), "grid": p.get("grid")})
    return out


def normalize_lineups(items: list[dict[str, Any]], home_team_api_id: int, away_team_api_id: int, *, fetched_at: datetime) -> tuple[dict[str, Any] | None, str]:
    """/fixtures/lineups -> (lineups_json, lineups_status). 'ufficiali' se entrambe le squadre hanno lo startXI."""
    out: dict[str, Any] = {}
    for entry in items or []:
        side = _side_for((entry.get("team") or {}).get("id"), home_team_api_id, away_team_api_id)
        if side is None:
            continue
        out[side] = {
            "formation": entry.get("formation"),
            "coach": ((entry.get("coach") or {}).get("name")),
            "starters": _players(entry.get("startXI")),
            "bench": _players(entry.get("substitutes")),
        }
    if not out:
        return None, LINEUPS_UNKNOWN
    out["fetched_at"] = fetched_at.astimezone(timezone.utc).isoformat()
    official = all(len((out.get(s) or {}).get("starters") or []) >= 11 for s in ("home", "away"))
    return out, (LINEUPS_OFFICIAL if official else LINEUPS_UNKNOWN)


# --- giocatori -----------------------------------------------------------------------------------------
def normalize_players(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """/fixtures/players -> righe per `CecchinoV4PlayerMinutes` (senza fixture_id)."""
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entry in items or []:
        team_id = _int((entry.get("team") or {}).get("id"))
        if team_id is None:
            continue
        for row in entry.get("players") or []:
            p = row.get("player") or {}
            pid = _int(p.get("id"))
            if pid is None or pid in seen:
                continue
            stats = (row.get("statistics") or [{}])[0] or {}
            games = stats.get("games") or {}
            seen.add(pid)
            out.append(
                {
                    "team_api_id": team_id,
                    "player_api_id": pid,
                    "player_name": str(p.get("name") or "")[:128],
                    "position": (str(games.get("position"))[:4] if games.get("position") else None),
                    "minutes": _int(games.get("minutes")) or 0,
                    "started": not bool(games.get("substitute", True)),
                    "rating": _float(games.get("rating")),
                }
            )
    return out


# --- infortuni e classifica ------------------------------------------------------------------------------
def normalize_injuries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for it in items or []:
        p, t, fx = it.get("player") or {}, it.get("team") or {}, it.get("fixture") or {}
        out.append(
            {
                "player_id": _int(p.get("id")),
                "player": p.get("name"),
                "type": p.get("type"),
                "reason": p.get("reason"),
                "team_id": _int(t.get("id")),
                "team": t.get("name"),
                "fixture_id": _int(fx.get("id")),
                "fixture_date": fx.get("date"),
            }
        )
    return out


def normalize_standings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """/standings -> lista piatta di righe (con `group` se il campionato e' a gironi)."""
    out: list[dict[str, Any]] = []
    for it in items or []:
        league = it.get("league") or {}
        for table in league.get("standings") or []:
            for row in table or []:
                team = row.get("team") or {}
                allg = row.get("all") or {}
                goals = allg.get("goals") or {}
                out.append(
                    {
                        "rank": _int(row.get("rank")),
                        "team_id": _int(team.get("id")),
                        "team": team.get("name"),
                        "points": _int(row.get("points")),
                        "played": _int(allg.get("played")),
                        "win": _int(allg.get("win")),
                        "draw": _int(allg.get("draw")),
                        "lose": _int(allg.get("lose")),
                        "gf": _int(goals.get("for")),
                        "ga": _int(goals.get("against")),
                        "goal_diff": _int(row.get("goalsDiff")),
                        "form": row.get("form"),
                        "group": row.get("group"),
                        "description": row.get("description"),
                    }
                )
    return out


# --- quote -------------------------------------------------------------------------------------------------
@dataclass
class NormalizedOdds:
    bookmaker_id: int
    bookmaker_name: str | None
    markets: dict[str, float] = field(default_factory=dict)
    unmapped_bets: list[str] = field(default_factory=list)


_HALF_RE = re.compile(r"\b(first half|1st half|half time|halftime|second half|2nd half|ht)\b")
_SIDE_RE = re.compile(r"\b(home|away)\b")
_LINE_RE = re.compile(r"(over|under)\s*([+-]?\d+(?:\.\d+)?)", re.IGNORECASE)
_AH_RE = re.compile(r"^(home|away)\s*([+-]?\d+(?:\.\d+)?)(?:\s*[,/]\s*([+-]?\d+(?:\.\d+)?))?$", re.IGNORECASE)

_1X2_VALUES = {"home": "HOME", "1": "HOME", "draw": "DRAW", "x": "DRAW", "away": "AWAY", "2": "AWAY"}
_DC_VALUES = {
    "home/draw": "ONE_X", "draw/home": "ONE_X", "1x": "ONE_X", "x1": "ONE_X",
    "home/away": "ONE_TWO", "away/home": "ONE_TWO", "12": "ONE_TWO",
    "draw/away": "X_TWO", "away/draw": "X_TWO", "x2": "X_TWO", "2x": "X_TWO",
}
_GOAL_LINES = ("0.5", "1.5", "2.5", "3.5")

_1X2_NAMES = {"match winner", "fulltime result", "full time result", "1x2", "match result", "winner"}
_HT_NAMES = {"first half winner", "half time result", "halftime result", "1st half winner", "1x2 first half", "first half result"}
_DC_NAMES = {"double chance"}
_GOALS_NAMES = {"goals over/under", "over/under", "total goals", "goals over under", "total goals over/under", "match goals"}
_AH_NAMES = {"asian handicap", "handicap"}

_STAT_WORDS: tuple[tuple[str, str], ...] = (
    ("shotongoal", "sot"), ("shots on goal", "sot"), ("shot on goal", "sot"), ("shots on target", "sot"),
    ("shot on target", "sot"), ("sot", "sot"),
    ("corner", "corners"), ("card", "cards"), ("foul", "fouls"), ("shot", "shots"),
)
_STAT_EXCLUDE = (
    "1x2", "3 way", "3-way", "handicap", "odd/even", "odd even", "race", "exact", "first", "last", "1st", "2nd",
    "half", "team to score", "to score", "most", "asian", "player", "anytime", "yellow", "red", "booking", "points",
)


def _clean_bet_name(name: str) -> str:
    text = str(name or "").strip().lower()
    text = re.sub(r"\s*-\s*", " ", text)  # "Corners Over Under - Home" -> "corners over under home"
    return re.sub(r"\s+", " ", text)


def format_line(value: float) -> str:
    """-0.5 -> "-0.5", 0.25 -> "+0.25", 0 -> "0.0", -1 -> "-1.0"."""
    v = round(float(value) * 4) / 4  # quarti di gol
    if abs(v) < 1e-9:
        return "0.0"
    text = f"{v:+.2f}"
    return text[:-1] if text.endswith("0") else text


def _stat_line(value: float) -> str:
    return f"{float(value):.1f}"


def _parse_over_under(value: str) -> tuple[str, float] | None:
    m = _LINE_RE.search(str(value or ""))
    if not m:
        return None
    return m.group(1).lower(), float(m.group(2))


def _stat_of(name: str) -> str | None:
    for word, stat in _STAT_WORDS:
        if word in name:
            return stat
    return None


def classify_bet(name: str) -> tuple[str, dict[str, Any]] | None:
    """Nome del bet API-Football -> (famiglia, dettagli) o None se fuori contratto."""
    n = _clean_bet_name(name)
    if not n:
        return None
    is_half = bool(_HALF_RE.search(n))
    stat = _stat_of(n)
    if stat is not None:
        if is_half or any(x in n for x in _STAT_EXCLUDE):
            return None
        side_m = _SIDE_RE.search(n)
        side = side_m.group(1) if side_m else "total"
        return "STAT", {"stat": stat, "side": side}
    if n in _HT_NAMES or (is_half and ("winner" in n or "result" in n or "1x2" in n) and "second" not in n and "2nd" not in n):
        return "HT_1X2", {}
    if is_half:
        return None
    if n in _1X2_NAMES:
        return "FT_1X2", {}
    if n in _DC_NAMES:
        return "DOUBLE_CHANCE", {}
    if n in _GOALS_NAMES:
        return "FT_OVER_UNDER", {}
    if n in _AH_NAMES:
        return "AH", {}
    return None


def normalize_bets(bets: list[dict[str, Any]]) -> tuple[dict[str, float], list[str]]:
    """Lista `bets` di un bookmaker -> ({market_key: quota}, nomi dei bet non mappati)."""
    markets: dict[str, float] = {}
    unmapped: list[str] = []
    for bet in bets or []:
        name = str(bet.get("name") or "")
        kind = classify_bet(name)
        if kind is None:
            if name and name not in unmapped:
                unmapped.append(name)
            continue
        family, info = kind
        for val in bet.get("values") or []:
            odd = _float(val.get("odd"))
            raw = str(val.get("value") or "").strip()
            if odd is None or odd <= 1.0 or not raw:
                continue
            key = _market_key(family, info, raw)
            if key is not None and key not in markets:
                markets[key] = odd
    return markets, unmapped


def _market_key(family: str, info: dict[str, Any], raw_value: str) -> str | None:
    v = raw_value.lower().strip()
    if family == "FT_1X2":
        return _1X2_VALUES.get(v)
    if family == "HT_1X2":
        base = _1X2_VALUES.get(v)
        return f"{base}_PT" if base else None
    if family == "DOUBLE_CHANCE":
        return _DC_VALUES.get(v.replace(" ", ""))
    if family == "FT_OVER_UNDER":
        ou = _parse_over_under(v)
        if ou is None:
            return None
        direction, line = ou
        line_txt = f"{line:.1f}"
        if line_txt not in _GOAL_LINES:
            return None
        return f"{direction.upper()}_{line_txt.replace('.', '_')}"
    if family == "AH":
        m = _AH_RE.match(v)
        if not m:
            return None
        side = m.group(1).upper()
        line = float(m.group(2))
        if m.group(3) is not None:  # linea doppia "Home -0.5, -1" -> media
            line = (line + float(m.group(3))) / 2.0
        return f"AH_{side}:{format_line(line)}"
    if family == "STAT":
        ou = _parse_over_under(v)
        if ou is None:
            return None
        direction, line = ou
        if abs(line - round(line)) < 1e-9:  # solo linee con il mezzo (docs/v4/API.md)
            return None
        return f"STAT:{info['stat']}:{info['side']}:{direction}:{_stat_line(line)}"
    return None


def normalize_odds_item(item: dict[str, Any], *, bookmaker_ids: set[int] | None = None) -> dict[int, NormalizedOdds]:
    """Una voce di /odds (una partita) -> {bookmaker_id: NormalizedOdds} per i bookmaker richiesti."""
    out: dict[int, NormalizedOdds] = {}
    for bk in item.get("bookmakers") or []:
        bid = _int(bk.get("id"))
        if bid is None or (bookmaker_ids is not None and bid not in bookmaker_ids):
            continue
        markets, unmapped = normalize_bets(bk.get("bets") or [])
        out[bid] = NormalizedOdds(bookmaker_id=bid, bookmaker_name=bk.get("name"), markets=markets, unmapped_bets=unmapped)
    return out


def odds_item_fixture_id(item: dict[str, Any]) -> int | None:
    return _int((item.get("fixture") or {}).get("id"))


def market_family(market_key: str) -> str | None:
    """Famiglia per la matrice di copertura: FT_1X2, DOUBLE_CHANCE, FT_OVER_UNDER, HT_1X2, AH, STAT:<stat>."""
    if market_key in ("HOME", "DRAW", "AWAY"):
        return "FT_1X2"
    if market_key in ("ONE_X", "X_TWO", "ONE_TWO"):
        return "DOUBLE_CHANCE"
    if market_key.endswith("_PT"):
        return "HT_1X2"
    if market_key.startswith(("OVER_", "UNDER_")):
        return "FT_OVER_UNDER"
    if market_key.startswith("AH_"):
        return "AH"
    if market_key.startswith("STAT:"):
        parts = market_key.split(":")
        return f"STAT:{parts[1]}" if len(parts) > 1 else None
    return None


COVERAGE_FAMILIES: tuple[str, ...] = (
    "FT_1X2", "DOUBLE_CHANCE", "FT_OVER_UNDER", "HT_1X2", "AH",
    "STAT:shots", "STAT:sot", "STAT:corners", "STAT:cards", "STAT:fouls",
)
