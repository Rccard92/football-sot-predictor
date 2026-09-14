"""Linee Over/Under Bet365 da salvare per ogni partita: solo linee a .5 (9.5, 10.5...), mai linee intere.

Le linee le decide il bookmaker partita per partita: salvarle tutte e' l'unico modo per avere
uno storico delle linee (nel Lab non esiste) e per sapere quando un pattern con soglia fissa
e' davvero giocabile.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.api_football_data import CecchinoBet365MarketLine
from app.models.cecchino_today_fixture import CecchinoTodayFixture

BET365_ID = 8

# nome mercato API-Football -> chiave interna
OVER_UNDER_MARKETS: dict[str, str] = {
    "Goals Over/Under": "goals_total",
    "Goals Over/Under First Half": "goals_first_half",
    "Goals Over/Under - Second Half": "goals_second_half",
    "Total - Home": "goals_home",
    "Total - Away": "goals_away",
    "Corners Over Under": "corners_total",
    "Home Corners Over/Under": "corners_home",
    "Away Corners Over/Under": "corners_away",
    "Total Corners (1st Half)": "corners_first_half",
    "Cards Over/Under": "cards_total",
    "Home Team Total Cards": "cards_home",
    "Away Team Total Cards": "cards_away",
    "Total ShotOnGoal": "shots_on_target_total",
    "Total Shots": "shots_total",
}

_VALUE_RE = re.compile(r"^(Over|Under)\s+(\d+(?:\.\d+)?)$", re.IGNORECASE)


def is_half_line(line: Decimal) -> bool:
    """True solo per linee che finiscono in .5 (niente pareggio/rimborso possibile)."""
    return (line * 2) % 2 == 1


def _odd(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None
    return d if d > 1 else None


def extract_half_lines(bookmaker_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Da un blocco bookmaker API-Football (bets/values) alle linee .5 Over/Under."""
    out: dict[tuple[str, Decimal], dict[str, Any]] = {}
    for bet in bookmaker_payload.get("bets") or []:
        key = OVER_UNDER_MARKETS.get(str(bet.get("name") or ""))
        if key is None:
            continue
        for v in bet.get("values") or []:
            m = _VALUE_RE.match(str(v.get("value") or "").strip())
            if not m:
                continue
            line = Decimal(m.group(2))
            if not is_half_line(line):
                continue
            entry = out.setdefault((key, line), {"market_key": key, "market_name": bet["name"], "line": line, "over_odd": None, "under_odd": None})
            entry["over_odd" if m.group(1).lower() == "over" else "under_odd"] = _odd(v.get("odd"))
    return sorted(out.values(), key=lambda e: (e["market_key"], e["line"]))


def bet365_block_from_snapshot(odds_snapshot: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    raw = ((odds_snapshot or {}).get("raw_by_bookmaker_id") or {}).get(str(BET365_ID)) or []
    for item in raw:
        for bm in (item or {}).get("bookmakers") or []:
            if int(bm.get("id") or 0) == BET365_ID:
                return bm, (item or {}).get("update")
    return None, None


def store_lines_for_scan_date(db: Session, *, scan_date: date) -> dict[str, int]:
    rows = db.scalars(
        select(CecchinoTodayFixture).where(
            CecchinoTodayFixture.scan_date == scan_date,
            CecchinoTodayFixture.odds_snapshot_json.is_not(None),
        )
    ).all()
    now = datetime.now(timezone.utc)
    fixtures = lines = 0
    for row in rows:
        block, updated = bet365_block_from_snapshot(row.odds_snapshot_json)
        if block is None:
            continue
        extracted = extract_half_lines(block)
        if not extracted:
            continue
        fixtures += 1
        for e in extracted:
            stmt = insert(CecchinoBet365MarketLine).values(
                provider_fixture_id=int(row.provider_fixture_id),
                scan_date=scan_date,
                kickoff=row.kickoff,
                provider_league_id=row.provider_league_id,
                league_name=row.league_name,
                market_key=e["market_key"],
                market_name=e["market_name"],
                line=e["line"],
                over_odd=e["over_odd"],
                under_odd=e["under_odd"],
                odds_updated_at=_parse_dt(updated),
                captured_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_cecchino_bet365_market_lines",
                set_={"over_odd": stmt.excluded.over_odd, "under_odd": stmt.excluded.under_odd,
                      "odds_updated_at": stmt.excluded.odds_updated_at, "captured_at": now, "updated_at": now},
            )
            db.execute(stmt)
            lines += 1
    db.commit()
    return {"fixtures_with_lines": fixtures, "lines": lines}


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
