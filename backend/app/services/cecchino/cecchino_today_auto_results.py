"""Aggiornamento automatico dei risultati di Cecchino Today (dal 13/10/2026).

Prima i risultati si aggiornavano solo con il pulsante "Aggiorna risultati giornata": le giornate
mai aggiornate, o aggiornate a partite in corso, restavano ferme a "da giocare" o "live" (circa una
eleggibile su sette tra il 13/09 e il 10/10). Questo modulo, chiamato dal giro del mattino del cron,
usa la stessa funzione del pulsante (`update_today_fixture_results`) e la stessa chiusura del
registro live della rotta, sulle giornate che ne hanno bisogno:

- i `days_back` giorni precedenti, sempre (partite finite a notte fonda, ritardi del fornitore);
- le giornate piu' vecchie, fino a `stale_lookback_days`, che hanno ancora eleggibili ferme a
  "da giocare" o "live" a partita passata da almeno 3 ore; al massimo `max_days` per giro.

Ogni giornata costa circa una chiamata API (fixtures per data) piu' poche richieste per le partite
spostate. Mai bloccante: un errore su una giornata non ferma le altre ne' la scansione.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, MATCH_LIVE, MATCH_UPCOMING

logger = logging.getLogger(__name__)

STALE_AFTER_KICKOFF = timedelta(hours=3)


def stale_scan_dates(
    db: Session,
    *,
    local_date: date,
    lookback_days: int,
    now: datetime | None = None,
) -> list[date]:
    """Giornate passate con eleggibili ancora "da giocare" o "live" a partita chiusa da 3 ore."""
    now = now or datetime.now(dt_timezone.utc)
    rows = db.execute(
        select(CecchinoTodayFixture.scan_date)
        .where(
            CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
            CecchinoTodayFixture.scan_date < local_date,
            CecchinoTodayFixture.scan_date >= local_date - timedelta(days=int(lookback_days)),
            CecchinoTodayFixture.kickoff < now - STALE_AFTER_KICKOFF,
            (CecchinoTodayFixture.match_display_status.is_(None))
            | (CecchinoTodayFixture.match_display_status.in_([MATCH_UPCOMING, MATCH_LIVE])),
        )
        .distinct()
    ).all()
    return sorted({r[0] for r in rows})


def dates_to_refresh(
    *,
    local_date: date,
    days_back: int,
    stale: list[date],
    max_days: int,
) -> list[date]:
    """Prima i giorni piu' recenti (sempre), poi le giornate ferme piu' recenti, fino a max_days."""
    recent = [local_date - timedelta(days=i) for i in range(1, int(days_back) + 1)]
    out: list[date] = []
    for d in recent + sorted(stale, reverse=True):
        if d not in out and d < local_date:
            out.append(d)
    return out[: max(0, int(max_days))]


def refresh_recent_results(
    *,
    session_factory: Callable[[], Session],
    local_date: date,
    timezone: str,
    days_back: int = 3,
    stale_lookback_days: int = 30,
    max_days: int = 10,
    update_fn: Callable[..., dict[str, Any]] | None = None,
    settle_fn: Callable[[Session], Any] | None = None,
) -> dict[str, Any]:
    """Aggiorna i risultati delle giornate scelte, una sessione per giornata. Mai solleva."""
    if update_fn is None:
        from app.services.cecchino.cecchino_today_service import update_today_fixture_results

        update_fn = update_today_fixture_results
    if settle_fn is None:
        from app.services.cecchino_live.registry import settle_predictions

        settle_fn = settle_predictions

    summary: dict[str, Any] = {"days": [], "errors": 0}
    db = session_factory()
    try:
        stale = stale_scan_dates(db, local_date=local_date, lookback_days=stale_lookback_days)
    except Exception:  # noqa: BLE001
        logger.exception("auto results: giornate ferme non leggibili")
        stale = []
    finally:
        db.close()
    days = dates_to_refresh(local_date=local_date, days_back=days_back, stale=stale, max_days=max_days)
    summary["stale_found"] = [d.isoformat() for d in stale]

    for d in days:
        db = session_factory()
        try:
            out = update_fn(db, scan_date=d, timezone=timezone)
            summary["days"].append(
                {
                    "date": d.isoformat(),
                    "status": out.get("status"),
                    "fixtures_checked": out.get("fixtures_checked"),
                    "still_upcoming": out.get("still_upcoming"),
                    "live": out.get("live"),
                    "api_calls": out.get("api_calls"),
                }
            )
            logger.info(
                "auto results date=%s status=%s still_upcoming=%s live=%s api_calls=%s",
                d.isoformat(),
                out.get("status"),
                out.get("still_upcoming"),
                out.get("live"),
                out.get("api_calls"),
            )
        except Exception:  # noqa: BLE001 - una giornata non ferma le altre
            logger.exception("auto results failed date=%s", d.isoformat())
            summary["errors"] += 1
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            db.close()

    # come la rotta del pulsante: chiude anche le previsioni del registro live
    db = session_factory()
    try:
        summary["live_registry_settlement"] = settle_fn(db)
    except Exception:  # noqa: BLE001
        logger.exception("auto results: registro live non chiuso")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()

    # e le giocate del Diario analisi (30/10/2026); il diario le chiude anche quando lo si apre
    db = session_factory()
    try:
        from app.services.analyst.journal import settle_entries

        summary["analyst_journal_settled"] = settle_entries(db)
    except Exception:  # noqa: BLE001
        logger.exception("auto results: diario analisi non chiuso")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()
    return summary
