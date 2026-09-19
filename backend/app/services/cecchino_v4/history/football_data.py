"""Caricatore dei CSV football-data.co.uk in `backend/app/data/v4/football_data/<stagione>/<codice>.csv`.

Produce gli stessi `MatchRecord` del motore V3 (cosi' la V3 si riusa come libreria) piu' un
dizionario di extra per partita: corner, quote Bet365 di apertura e chiusura (1X2, O/U 2,5,
handicap asiatico). Le quote NON vengono mai passate ai motori: servono a selezione e misura.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable

from app.services.cecchino_v3.constants import group_of
from app.services.cecchino_v3.data import MatchRecord, annotate_season_context

from app.services.cecchino_v4.constants import (
    CURRENT_SEASON,
    HISTORY_SEASONS,
    LEAGUE_BY_CODE,
    LOCKBOX_SEASON,
    SEASON_CODES,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "v4" / "football_data"

_EPOCH = date(2000, 1, 1)


@dataclass
class MatchExtras:
    """Dati della partita che il motore V3 non conosce."""

    code: str  # E0, I1, ...
    home_corners: int | None = None
    away_corners: int | None = None
    # Quote Bet365 (apertura = colonna base football-data, chiusura = colonne C*)
    odds_open: dict[str, float] = field(default_factory=dict)
    odds_close: dict[str, float] = field(default_factory=dict)
    ah_line_open: float | None = None
    ah_line_close: float | None = None


@dataclass
class History:
    matches: list[MatchRecord]
    extras: dict[int, MatchExtras]

    def by_id(self) -> dict[int, MatchRecord]:
        return {m.lab_match_id: m for m in self.matches}


def _int(v: str | None) -> int | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _float(v: str | None) -> float | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        out = float(v)
    except ValueError:
        return None
    return out


def _date(v: str) -> date | None:
    v = v.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _time(v: str | None) -> time | None:
    if not v:
        return None
    try:
        return datetime.strptime(v.strip(), "%H:%M").time()
    except ValueError:
        return None


_ODDS_OPEN = {
    "HOME": "B365H",
    "DRAW": "B365D",
    "AWAY": "B365A",
    "OVER_2_5": "B365>2.5",
    "UNDER_2_5": "B365<2.5",
    "AH_HOME": "B365AHH",
    "AH_AWAY": "B365AHA",
}
_ODDS_CLOSE = {
    "HOME": "B365CH",
    "DRAW": "B365CD",
    "AWAY": "B365CA",
    "OVER_2_5": "B365C>2.5",
    "UNDER_2_5": "B365C<2.5",
    "AH_HOME": "B365CAHH",
    "AH_AWAY": "B365CAHA",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        text = raw.decode("utf-8", errors="ignore")
    rows: list[dict[str, str]] = []
    for row in csv.DictReader(text.splitlines()):
        if not (row.get("HomeTeam") or "").strip():
            continue
        rows.append({k: (v or "") for k, v in row.items() if k})
    return rows


def _match_id(season_code: str, league_code: str, index: int) -> int:
    """Id stabile e deterministico: stagione (2 cifre) · campionato (2 cifre) · riga (4 cifre)."""
    s = list(SEASON_CODES).index(season_code)
    lg = list(LEAGUE_BY_CODE).index(league_code)
    return int(f"9{s:02d}{lg:02d}{index:04d}")


def load_history(
    *,
    seasons: Iterable[str] | None = None,
    league_codes: Iterable[str] | None = None,
    include_lockbox: bool = False,
    include_current: bool = False,
    data_dir: Path | None = None,
) -> History:
    """Carica lo storico. Di default esclude 2025/26 e la stagione in corso (regola 3 di docs/v4/REGOLE.md).

    `include_lockbox` aggiunge 2025/26, `include_current` la stagione in corso: entrambe solo come
    input del live, mai per stimare parametri o esami.
    """
    base = data_dir or DATA_DIR
    wanted_seasons = set(seasons) if seasons is not None else set(HISTORY_SEASONS)
    if include_lockbox:
        wanted_seasons.add(LOCKBOX_SEASON)
    if include_current:
        wanted_seasons.add(CURRENT_SEASON)
    if not include_lockbox and LOCKBOX_SEASON in wanted_seasons:
        raise ValueError("Stagione sotto chiave richiesta senza include_lockbox=True")
    if not include_current and CURRENT_SEASON in wanted_seasons:
        raise ValueError("Stagione in corso richiesta senza include_current=True")
    codes = list(league_codes) if league_codes is not None else list(LEAGUE_BY_CODE)

    matches: list[MatchRecord] = []
    extras: dict[int, MatchExtras] = {}
    for season_code, season_label in SEASON_CODES.items():
        if season_label not in wanted_seasons:
            continue
        for code in codes:
            path = base / season_code / f"{code}.csv"
            if not path.exists():
                continue
            league = LEAGUE_BY_CODE[code]
            for idx, row in enumerate(_read_csv(path)):
                d = _date(row.get("Date", ""))
                fthg, ftag = _int(row.get("FTHG")), _int(row.get("FTAG"))
                if d is None or fthg is None or ftag is None:
                    continue
                t = _time(row.get("Time"))
                kickoff = datetime.combine(d, t) if t else None
                mid = _match_id(season_code, code, idx)
                matches.append(
                    MatchRecord(
                        lab_match_id=mid,
                        competition=league.competition,
                        group=group_of(league.competition),
                        season_label=season_label,
                        match_date=d,
                        kickoff_at=kickoff,
                        day=(d - _EPOCH).days,
                        home_team=row["HomeTeam"].strip(),
                        away_team=row["AwayTeam"].strip(),
                        ft_home=fthg,
                        ft_away=ftag,
                        ht_home=_int(row.get("HTHG")),
                        ht_away=_int(row.get("HTAG")),
                        home_shots=_int(row.get("HS")),
                        away_shots=_int(row.get("AS")),
                        home_sot=_int(row.get("HST")),
                        away_sot=_int(row.get("AST")),
                        home_fouls=_int(row.get("HF")),
                        away_fouls=_int(row.get("AF")),
                        home_yellow=_int(row.get("HY")),
                        away_yellow=_int(row.get("AY")),
                        home_red=_int(row.get("HR")),
                        away_red=_int(row.get("AR")),
                        referee=(row.get("Referee") or "").strip() or None,
                    )
                )
                ex = MatchExtras(code=code, home_corners=_int(row.get("HC")), away_corners=_int(row.get("AC")))
                for market, col in _ODDS_OPEN.items():
                    v = _float(row.get(col))
                    if v is not None and v > 1.0:
                        ex.odds_open[market] = v
                for market, col in _ODDS_CLOSE.items():
                    v = _float(row.get(col))
                    if v is not None and v > 1.0:
                        ex.odds_close[market] = v
                ex.ah_line_open = _float(row.get("AHh"))
                ex.ah_line_close = _float(row.get("AHCh"))
                extras[mid] = ex
    matches.sort(key=lambda m: (m.day, m.competition, m.home_team))
    annotate_season_context(matches)
    return History(matches=matches, extras=extras)


def cards_weighted(yellow: int | None, red: int | None, *, w_yellow: float = 1.0, w_red: float = 2.0) -> float | None:
    if yellow is None and red is None:
        return None
    return w_yellow * float(yellow or 0) + w_red * float(red or 0)
