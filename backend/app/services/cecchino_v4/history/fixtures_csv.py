"""Partite in programma dal file pubblico football-data.co.uk/fixtures.csv.

Fonte di riserva per la vista Partite e per il test locale senza API-Football: date, orari,
squadre (nomi football-data, identici allo storico) e quote Bet365 / Betfair Exchange dei
mercati classici (1X2, over/under 2,5, handicap asiatico). Nessun mercato speciale.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.cecchino_v4.constants import (
    BOOKMAKER_BET365_ID,
    BOOKMAKER_BETFAIR_ID,
    CURRENT_SEASON,
    LEAGUE_BY_CODE,
)

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "v4" / "football_data" / "fixtures.csv"
ROME = ZoneInfo("Europe/Rome")


@dataclass
class UpcomingFixture:
    key: str  # stabile: sha1 di codice·data·casa·ospite
    league_code: str
    competition: str
    season_label: str
    match_date: date
    kickoff_at: datetime  # aware, Europe/Rome (football-data pubblica orari UK: vedi nota)
    home_team: str
    away_team: str
    referee: str | None
    odds: dict[int, dict[str, float]] = field(default_factory=dict)  # bookmaker_id -> {market_key: quota}

    @property
    def synthetic_api_fixture_id(self) -> int:
        """Id negativo e stabile: non collide mai con gli id API-Football (positivi)."""
        return -int(self.key[:12], 16)


def _f(v: str | None) -> float | None:
    if not v:
        return None
    try:
        out = float(v)
    except ValueError:
        return None
    return out if out > 1.0 else None


def _ah_key(side: str, line: float) -> str:
    sign = "+" if line > 0 else ("-" if line < 0 else "")
    return f"AH_{side}:{sign}{abs(line):g}" if line != 0 else f"AH_{side}:0.0"


def _parse_dt(d: str, t: str) -> tuple[date, datetime] | None:
    d = d.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            day = datetime.strptime(d, fmt).date()
            break
        except ValueError:
            continue
    else:
        return None
    try:
        tm = datetime.strptime((t or "").strip(), "%H:%M").time()
    except ValueError:
        tm = time(15, 0)
    # football-data pubblica gli orari in ora del Regno Unito: +1 ora per l'Italia.
    uk = datetime.combine(day, tm, tzinfo=ZoneInfo("Europe/London"))
    rome = uk.astimezone(ROME)
    return rome.date(), rome


def load_upcoming(path: Path | None = None, *, season_label: str = CURRENT_SEASON) -> list[UpcomingFixture]:
    p = path or DEFAULT_PATH
    if not p.exists():
        return []
    text = p.read_bytes().decode("utf-8-sig", errors="ignore")
    out: list[UpcomingFixture] = []
    for row in csv.DictReader(text.splitlines()):
        code = (row.get("Div") or "").strip()
        league = LEAGUE_BY_CODE.get(code)
        if league is None:
            continue
        parsed = _parse_dt(row.get("Date", ""), row.get("Time", ""))
        if parsed is None:
            continue
        match_date, kickoff = parsed
        home, away = row["HomeTeam"].strip(), row["AwayTeam"].strip()
        key = hashlib.sha1(f"{code}|{match_date.isoformat()}|{home}|{away}".encode("utf-8")).hexdigest()
        b365: dict[str, float] = {}
        bfe: dict[str, float] = {}
        for market, col in (("HOME", "B365H"), ("DRAW", "B365D"), ("AWAY", "B365A"), ("OVER_2_5", "B365>2.5"), ("UNDER_2_5", "B365<2.5")):
            v = _f(row.get(col))
            if v:
                b365[market] = v
        for market, col in (("HOME", "BFEH"), ("DRAW", "BFED"), ("AWAY", "BFEA"), ("OVER_2_5", "BFE>2.5"), ("UNDER_2_5", "BFE<2.5")):
            v = _f(row.get(col))
            if v:
                bfe[market] = v
        line = row.get("AHh")
        try:
            ah_line = float(line) if line not in (None, "") else None
        except ValueError:
            ah_line = None
        if ah_line is not None:
            h, a = _f(row.get("B365AHH")), _f(row.get("B365AHA"))
            if h:
                b365[_ah_key("HOME", ah_line)] = h
            if a:
                b365[_ah_key("AWAY", -ah_line)] = a
            h, a = _f(row.get("BFEAHH")), _f(row.get("BFEAHA"))
            if h:
                bfe[_ah_key("HOME", ah_line)] = h
            if a:
                bfe[_ah_key("AWAY", -ah_line)] = a
        odds: dict[int, dict[str, float]] = {}
        if b365:
            odds[BOOKMAKER_BET365_ID] = b365
        if bfe:
            odds[BOOKMAKER_BETFAIR_ID] = bfe
        out.append(
            UpcomingFixture(
                key=key,
                league_code=code,
                competition=league.competition,
                season_label=season_label,
                match_date=match_date,
                kickoff_at=kickoff,
                home_team=home,
                away_team=away,
                referee=(row.get("Referee") or "").strip() or None,
                odds=odds,
            )
        )
    out.sort(key=lambda f: (f.kickoff_at, f.competition, f.home_team))
    return out
