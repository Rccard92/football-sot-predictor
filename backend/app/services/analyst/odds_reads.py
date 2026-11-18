"""Seconda lettura Bet365 a 75 minuti dal via e movimento delle quote (Miglioria 1 di Giovanni, 17/11/2026).

- Per 8 settimane (fino al 13/01/2027), per tutte le gare del Diario (eleggibili e nei campionati ammessi):
  75 minuti prima del calcio d'inizio una chiamata "odds?fixture=" e si salvano le quote Bet365.
- Con le due letture (mattino 6:00 della fotografia di Today e T-75) la scheda della partita mostra il movimento
  della probabilita' senza margine e se il mercato si e' mosso verso il numero del Cecchino (= chi ha comprato al
  mattino nella direzione del Cecchino avrebbe avuto CLV positivo).
- Riepilogo su tutte le letture: quante volte il mercato va verso il Cecchino, per mercato.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analyst_extra import AnalystOddsRead
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.fixture import Fixture
from app.services.analyst.closing import book_quotes
from app.services.analyst.leagues import league_admitted
from app.services.analyst.novig import novig_prob

logger = logging.getLogger(__name__)

READ_BEFORE = timedelta(minutes=75)
READ_UNTIL = date(2027, 1, 13)  # 8 settimane dal 18/11/2026
KIND = "t75"
BET365 = (8, "Bet365", "bet365")
# mercati mostrati nel movimento (le doppie chance si leggono dall'1-X-2)
MOVE_MARKETS = ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5", "OVER_1_5", "UNDER_3_5", "DRAW_PT", "UNDER_PT_1_5")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def due_reads(db: Session, now: datetime) -> list[tuple[CecchinoTodayFixture, datetime]]:
    """Gare ammesse che partono entro 75 minuti e non hanno ancora la seconda lettura."""
    rows = db.execute(
        select(CecchinoTodayFixture, Fixture.kickoff_at)
        .join(Fixture, Fixture.id == CecchinoTodayFixture.local_fixture_id)
        .where(
            CecchinoTodayFixture.eligibility_status == "eligible",
            Fixture.kickoff_at > now,
            Fixture.kickoff_at <= now + READ_BEFORE,
        )
    ).all()
    if not rows:
        return []
    done = {
        int(i)
        for (i,) in db.execute(
            select(AnalystOddsRead.today_fixture_id).where(
                AnalystOddsRead.today_fixture_id.in_([int(f.id) for f, _ in rows]), AnalystOddsRead.kind == KIND
            )
        ).all()
    }
    return [(f, _aware(ko)) for f, ko in rows if int(f.id) not in done and league_admitted(f.country_name, f.league_name)]


def run_second_read(db: Session, client: Any, now: datetime | None = None, *, max_calls: int = 80) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    out = {"due": 0, "ok": 0, "nd": 0, "errors": 0}
    if now.date() > READ_UNTIL:
        return out
    due = due_reads(db, now)
    out["due"] = len(due)
    for fx, kickoff in due[:max_calls]:
        try:
            items = client.get_fixture_odds_by_fixture(int(fx.provider_fixture_id))
        except Exception:  # noqa: BLE001 - si riprova al giro dopo, finche' la gara non parte
            logger.warning("seconda lettura: quote non lette per %s", fx.provider_fixture_id, exc_info=True)
            out["errors"] += 1
            continue
        quotes = book_quotes(items or [], *BET365)
        db.add(
            AnalystOddsRead(
                today_fixture_id=int(fx.id), provider_fixture_id=int(fx.provider_fixture_id), kind=KIND,
                status="ok" if quotes else "nd", read_at=now, kickoff=kickoff, bookmaker_id=BET365[0], markets_json=quotes or None,
            )
        )
        out["ok" if quotes else "nd"] += 1
    db.commit()
    return out


def _cecchino_prob(quota: float | None) -> float | None:
    try:
        q = float(quota) if quota else None
    except (TypeError, ValueError):
        return None
    return 1.0 / q if q and q > 1.0 else None


def movement(morning: dict[str, Any], later: dict[str, Any], cecchino: dict[str, Any]) -> list[dict[str, Any]]:
    """Per mercato: probabilita' senza margine al mattino e a T-75, movimento in punti e confronto con il Cecchino.

    toward_cecchino = il mercato si e' mosso dalla parte del Cecchino (Cecchino sopra il mattino e la probabilita' e'
    salita, o sotto e scesa): chi ha comprato al mattino in quella direzione ha CLV positivo."""
    out = []
    for key in MOVE_MARKETS:
        p0, p1 = novig_prob(morning, key), novig_prob(later, key)
        if p0 is None or p1 is None:
            continue
        move = round(100 * (p1 - p0), 1)
        pc = _cecchino_prob(cecchino.get(key))
        toward = None
        if pc is not None and move != 0 and abs(pc - p0) >= 0.005:
            toward = (pc > p0) == (move > 0)
        out.append(
            {
                "key": key,
                "morning_quota": morning.get(key),
                "later_quota": later.get(key),
                "morning_prob": round(p0, 4),
                "later_prob": round(p1, 4),
                "move_points": move,
                "cecchino_prob": round(pc, 4) if pc is not None else None,
                "toward_cecchino": toward,
                # CLV di chi comprava il segno al mattino: quota del mattino x probabilita' a T-75 - 1
                "clv_morning": round(float(morning[key]) * p1 - 1, 4) if morning.get(key) else None,
            }
        )
    return out


def reads_for(db: Session, today_fixture_ids: list[int]) -> dict[int, AnalystOddsRead]:
    if not today_fixture_ids:
        return {}
    return {
        int(r.today_fixture_id): r
        for r in db.execute(
            select(AnalystOddsRead).where(AnalystOddsRead.today_fixture_id.in_(today_fixture_ids), AnalystOddsRead.kind == KIND)
        ).scalars()
    }


def summary(db: Session) -> dict[str, Any]:
    """Tutte le seconde letture: per mercato quante volte il mercato va verso il Cecchino e il CLV del mattino."""
    reads = db.execute(select(AnalystOddsRead).where(AnalystOddsRead.kind == KIND, AnalystOddsRead.status == "ok")).scalars().all()
    if not reads:
        return {"reads": 0, "markets": [], "until": READ_UNTIL.isoformat()}
    fixtures = {
        int(f.id): f
        for f in db.execute(
            select(CecchinoTodayFixture).where(CecchinoTodayFixture.id.in_([int(r.today_fixture_id) for r in reads]))
        ).scalars()
    }
    acc: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "toward": 0, "judged": 0, "move": 0.0, "clv": 0.0, "clv_pos": 0})
    for r in reads:
        fx = fixtures.get(int(r.today_fixture_id))
        if fx is None:
            continue
        morning, cecchino = kpi_quotes(fx)
        for m in movement(morning, r.markets_json or {}, cecchino):
            a = acc[m["key"]]
            a["n"] += 1
            a["move"] += abs(m["move_points"])
            if m["toward_cecchino"] is not None:
                a["judged"] += 1
                a["toward"] += 1 if m["toward_cecchino"] else 0
            if m["clv_morning"] is not None:
                a["clv"] += m["clv_morning"]
                a["clv_pos"] += 1 if m["clv_morning"] > 0 else 0
    markets = [
        {
            "key": k,
            "n": int(a["n"]),
            "avg_abs_move_points": round(a["move"] / a["n"], 2) if a["n"] else None,
            "toward_cecchino_pct": round(100 * a["toward"] / a["judged"], 1) if a["judged"] else None,
            "judged": int(a["judged"]),
            "clv_morning_avg_pct": round(100 * a["clv"] / a["n"], 2) if a["n"] else None,
            "clv_morning_pos_pct": round(100 * a["clv_pos"] / a["n"], 1) if a["n"] else None,
        }
        for k, a in sorted(acc.items(), key=lambda kv: MOVE_MARKETS.index(kv[0]) if kv[0] in MOVE_MARKETS else 99)
    ]
    return {"reads": len(reads), "markets": markets, "until": READ_UNTIL.isoformat()}


def kpi_quotes(fx: CecchinoTodayFixture) -> tuple[dict[str, float], dict[str, float]]:
    """Quote del mattino (book) e quote Cecchino dal pannello KPI della fotografia di Today."""
    book: dict[str, float] = {}
    cec: dict[str, float] = {}
    for row in ((fx.kpi_panel_json or {}).get("rows") or []):
        if not isinstance(row, dict) or not row.get("market_key"):
            continue
        key = str(row["market_key"])
        for target, field in ((book, "quota_book"), (cec, "quota_cecchino")):
            try:
                v = float(row.get(field)) if row.get(field) is not None else None
            except (TypeError, ValueError):
                v = None
            if v and v > 1.0:
                target[key] = v
    return book, cec
