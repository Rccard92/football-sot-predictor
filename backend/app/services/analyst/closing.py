"""Quota di chiusura e CLV delle giocate del Diario analisi (documento "Modifiche" di Giovanni, 09/11/2026).

- Solo per le partite con almeno una giocata: 60 minuti prima del calcio d'inizio il sito rilegge le quote
  (una chiamata API-Football "odds?fixture=" per partita, con tutti i bookmaker dentro).
- Bookmaker della chiusura: Bet365; solo se Bet365 non ha quel segno, Pinnacle (il riferimento piu' preciso per
  la chiusura), poi Betfair. Il bookmaker usato si salva sempre accanto alla quota. Nessuno dei tre: "n.d.".
- Le doppie chance ricavate dall'1-X-2 non valgono come chiusura (non hanno il margine del book).
- CLV = quota presa / quota di chiusura - 1. Sopra 0 abbiamo comprato meglio del mercato.
- Giocate gia' salvate: si prova a recuperare la chiusura se la partita e' degli ultimi 7 giorni (dopo il
  fornitore non tiene piu' le quote); la quota letta dopo l'inizio e' segnata come "recuperata". Altrimenti n.d.

Il giro parte dal backend ogni 5 minuti (main.py), con un blocco su Postgres perche' giri una volta sola.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.analyst_journal import AnalystEntry
from app.services.cecchino.cecchino_canonical_book_payload import build_single_bookmaker_payload

logger = logging.getLogger(__name__)

# (id API-Football, nome, slug): in quest'ordine
CLOSING_BOOKS: tuple[tuple[int, str, str], ...] = ((8, "Bet365", "bet365"), (4, "Pinnacle", "pinnacle"), (3, "Betfair", "betfair"))
BEFORE_KICKOFF = timedelta(minutes=60)
RECOVER_DAYS = 7
LOOP_SECONDS = 300
CLOSING_OK = "ok"
CLOSING_ND = "nd"
NOTE_RECOVERED = "recuperata dopo il calcio d'inizio"
_LOCK_ID = 20261109  # pg_try_advisory_lock: un solo giro alla volta anche durante un riavvio


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def clv_value(taken: float | None, closing: float | None) -> float | None:
    if not taken or not closing or closing <= 1.0 or taken <= 1.0:
        return None
    return round(float(taken) / float(closing) - 1.0, 4)


def book_quotes(items: list[dict[str, Any]], book_id: int, name: str, slug: str) -> dict[str, float]:
    """Quote di un bookmaker per segno (chiavi del Diario: HOME, DRAW, UNDER_2_5, DRAW_PT...), dalla risposta "odds"."""
    raw = []
    for item in items or []:
        books = [b for b in (item.get("bookmakers") or []) if isinstance(b, dict) and int(b.get("id") or 0) == book_id]
        if books:
            raw.append({**item, "bookmakers": books})
    if not raw:
        return {}
    payload = build_single_bookmaker_payload(raw, {"name": name, "slug": slug, "provider_bookmaker_id": book_id})
    derived = payload.get("dc_derived") or {}
    out: dict[str, float] = {}
    for block in (payload.get("markets") or {}).values():
        for key, odd in (block or {}).items():
            if odd is None or derived.get(key):
                continue
            try:
                value = float(odd)
            except (TypeError, ValueError):
                continue
            if value > 1.0:
                out[str(key)] = value
    return out


def pick_closing(items: list[dict[str, Any]], market_key: str) -> tuple[float | None, str | None]:
    """Quota di chiusura del segno: Bet365, se manca Pinnacle, poi Betfair."""
    for book_id, name, slug in CLOSING_BOOKS:
        q = book_quotes(items, book_id, name, slug).get(market_key)
        if q:
            return q, name
    return None, None


def apply_closing(entry: AnalystEntry, items: list[dict[str, Any]] | None, now: datetime, *, recovered: bool = False) -> None:
    q, book = pick_closing(items or [], entry.market_key) if items else (None, None)
    entry.closing_at = now
    if q is None:
        entry.closing_status = CLOSING_ND
        entry.closing_note = "nessuna quota di Bet365, Pinnacle o Betfair per questo segno" if items else "quote non disponibili"
        return
    entry.closing_quota = q
    entry.closing_bookmaker = book
    entry.closing_status = CLOSING_OK
    entry.closing_note = NOTE_RECOVERED if recovered else None
    entry.clv = clv_value(entry.quota, q)


def refresh_clv(entry: AnalystEntry) -> None:
    """Se cambia la quota presa, il CLV si ricalcola sulla chiusura gia' letta."""
    entry.clv = clv_value(entry.quota, entry.closing_quota) if entry.closing_status == CLOSING_OK else None


def due_entries(db: Session, now: datetime) -> tuple[list[AnalystEntry], list[AnalystEntry], list[AnalystEntry]]:
    """(da leggere ora, da recuperare, troppo vecchie): solo giocate senza chiusura e con la partita del fornitore."""
    rows = db.scalars(
        select(AnalystEntry).where(
            AnalystEntry.closing_status.is_(None),
            AnalystEntry.kickoff.is_not(None),
            AnalystEntry.kickoff <= now + BEFORE_KICKOFF,
        )
    ).all()
    upcoming, recover, old = [], [], []
    for e in rows:
        ko = _aware(e.kickoff)
        if e.provider_fixture_id is None or ko < now - timedelta(days=RECOVER_DAYS):
            old.append(e)
        elif ko > now:
            upcoming.append(e)
        else:
            recover.append(e)
    return upcoming, recover, old


def run_closing(db: Session, client: Any, now: datetime | None = None, *, max_calls: int = 60) -> dict[str, Any]:
    """Un giro: una chiamata per partita, al massimo max_calls; le giocate della stessa partita la condividono."""
    now = now or _now()
    upcoming, recover, old = due_entries(db, now)
    out = {"upcoming": len(upcoming), "recovered": 0, "nd": 0, "ok": 0, "calls": 0, "errors": 0}
    for e in old:
        e.closing_at = now
        e.closing_status = CLOSING_ND
        e.closing_note = "partita troppo vecchia per recuperare le quote"
        out["nd"] += 1
    groups: dict[int, list[tuple[AnalystEntry, bool]]] = defaultdict(list)
    for e in upcoming:
        groups[int(e.provider_fixture_id)].append((e, False))
    for e in recover:
        groups[int(e.provider_fixture_id)].append((e, True))
    for fixture_id, entries in groups.items():
        if out["calls"] >= max_calls:
            break
        try:
            items = client.get_fixture_odds_by_fixture(fixture_id)
        except Exception:  # noqa: BLE001 - si riprova al giro dopo (le giocate passate diventano "recuperate")
            logger.warning("analyst closing: quote non lette per la partita %s", fixture_id, exc_info=True)
            out["errors"] += 1
            out["calls"] += 1
            # prima del calcio d'inizio si riprova al giro dopo; a partita gia' iniziata si prova una volta sola
            for e, recovered in entries:
                if recovered:
                    e.closing_at = now
                    e.closing_status = CLOSING_ND
                    e.closing_note = "quote non lette (errore del fornitore)"
                    out["nd"] += 1
            continue
        out["calls"] += 1
        for e, recovered in entries:
            apply_closing(e, items, now, recovered=recovered)
            out["recovered" if recovered and e.closing_status == CLOSING_OK else "ok" if e.closing_status == CLOSING_OK else "nd"] += 1
    db.commit()
    return out


def run_closing_locked(db: Session, client: Any) -> dict[str, Any] | None:
    """Come run_closing, ma solo se nessun altro giro e' in corso (Postgres); in locale (sqlite) gira e basta."""
    postgres = db.get_bind().dialect.name == "postgresql"
    if postgres and not db.execute(text("select pg_try_advisory_lock(:k)"), {"k": _LOCK_ID}).scalar():
        return None
    try:
        return run_closing(db, client)
    finally:
        if postgres:
            db.execute(text("select pg_advisory_unlock(:k)"), {"k": _LOCK_ID})
            db.commit()


def closing_loop() -> None:
    """Thread del backend: un giro ogni 5 minuti. Un errore non ferma il giro successivo."""
    import time

    from app.core.database import SessionLocal
    from app.services.api_football_client import ApiFootballClient

    time.sleep(90)
    while True:
        db = SessionLocal()
        try:
            res = run_closing_locked(db, ApiFootballClient())
            if res and (res["calls"] or res["nd"]):
                logger.info("analyst closing %s", res)
        except Exception:  # noqa: BLE001
            logger.exception("analyst closing: giro fallito")
            db.rollback()
        finally:
            db.close()
        time.sleep(LOOP_SECONDS)


__all__ = ["apply_closing", "book_quotes", "clv_value", "pick_closing", "refresh_clv", "run_closing"]
