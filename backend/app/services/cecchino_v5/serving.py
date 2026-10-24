"""Letture pubbliche della V5: giocate del giorno e confronto giornaliero di tutti i motori sullo stesso metro."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.services.audit.models_compare import load_plays, summarize
from app.services.cecchino.cecchino_bet_builder_results import roi_stats
from app.services.cecchino_v5.constants import STAT_SPECIALISTS, STATUS_ADVISED, VALORE_KEY, VALORE_LABEL, VERSION
from app.services.cecchino_v5.pipeline import plays_for_day

ROME = ZoneInfo("Europe/Rome")
# Il calcolo a freddo dura circa un minuto (Bet Builder e acquistabilita'): la pagina riceve subito l'ultima
# versione e, se ha piu' di 10 minuti, la si ricalcola in sottofondo.
CACHE_SECONDS = 600

# Nome italiano e famiglia di ogni motore del confronto (le chiavi sono quelle di app/services/audit/models_compare.py).
ENGINE_LABELS: dict[str, tuple[str, str]] = {
    "bet_builder": ("Bet Builder", "Bet Builder"),
    "v25_evidenza": ("V2.5 in evidenza", "Today"),
    "v3_evidenza": ("V3 in evidenza", "Today"),
    "v25_indice": ("V2.5 indice ≥ 70", "Today"),
    "v3_indice": ("V3 indice ≥ 70", "Today"),
    "combo": ("Combo V2.5 + V3", "Today"),
    "kpi_segnali": ("Segnali KPI", "Segnali"),
    "segnali_si": ("Segnali SI", "Segnali"),
    "acquistabilita_v1": ("Acquistabilità V1 ≥ 70", "Segnali"),
    "v4": ("V4 shortlist", "V4"),
    **{f"v5_{s.key}": (f"V5 {s.label}", "V5") for s in STAT_SPECIALISTS},
    f"v5_{VALORE_KEY}": (f"V5 {VALORE_LABEL}", "V5"),
    "tutti_i_mercati": ("Tutti i mercati (riferimento)", "Riferimento"),
}
ENGINE_ORDER = list(ENGINE_LABELS)
ADVISED_ENGINES = {f"v5_{s.key}" for s in STAT_SPECIALISTS if s.status == STATUS_ADVISED}
V5_ENGINES = {k for k in ENGINE_LABELS if k.startswith("v5_")}

_cache: dict[int, tuple[float, dict[str, Any]]] = {}
_refreshing: set[int] = set()
_lock = threading.Lock()


def today_rome() -> date:
    return datetime.now(timezone.utc).astimezone(ROME).date()


def _engine_meta(engine: str) -> dict[str, Any]:
    label, family = ENGINE_LABELS.get(engine, (engine, "Altro"))
    meta: dict[str, Any] = {"engine": engine, "label": label, "family": family}
    if engine in V5_ENGINES:
        meta["v5_status"] = "consigliata" if engine in ADVISED_ENGINES else "osservazione"
    return meta


def _order(engine: str) -> int:
    return ENGINE_ORDER.index(engine) if engine in ENGINE_ORDER else len(ENGINE_ORDER)


def engines_compare(db: Session, *, days: int = 30) -> dict[str, Any]:
    """Totali del periodo, tabella per giorno e profitto cumulato di ogni motore (1 unita' a giocata)."""
    with _lock:
        hit = _cache.get(days)
    if hit is None:
        return _compute(db, days)
    if time.time() - hit[0] >= CACHE_SECONDS:
        _refresh_in_background(days)
    return hit[1]


def _refresh_in_background(days: int) -> None:
    with _lock:
        if days in _refreshing:
            return
        _refreshing.add(days)

    def run() -> None:
        try:
            warm(days)
        finally:
            with _lock:
                _refreshing.discard(days)

    threading.Thread(target=run, name=f"engines-compare-{days}", daemon=True).start()


def warm(days: int = 30) -> None:
    """Calcolo in una sessione di sola lettura propria (avvio dell'app e aggiornamento in sottofondo)."""
    from app.services.audit.readonly import readonly_session

    gen = readonly_session()
    db = next(gen)
    try:
        _compute(db, days)
    except Exception:  # noqa: BLE001 - resta la versione precedente
        logging.getLogger(__name__).exception("confronto motori non aggiornato (%s giorni)", days)
    finally:
        gen.close()


def _compute(db: Session, days: int) -> dict[str, Any]:
    now = time.time()
    date_to = today_rome()
    date_from = date_to - timedelta(days=days - 1)
    plays, errors = load_plays(db, date_from, date_to)

    totals = []
    for row in summarize(plays, "engine"):
        engine = row["group"][0]
        totals.append({**_engine_meta(engine), **{k: v for k, v in row.items() if k != "group"}})
    totals.sort(key=lambda r: _order(r["engine"]))

    by_day: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in summarize(plays, "engine_day"):
        engine, day = row["group"]
        by_day[day][engine] = {"plays": row["plays"], "won": row["won"], "profit": row["profit"], "roi_pct": row["roi_pct"]}
    day_list = sorted(by_day, reverse=True)

    engines_seen = sorted({r["engine"] for r in totals}, key=_order)
    cumulative: dict[str, list[dict[str, Any]]] = {}
    for engine in engines_seen:
        running = 0.0
        series = []
        for day in sorted(by_day):
            cell = by_day[day].get(engine)
            if cell is None:
                continue
            running += cell["profit"]
            series.append({"day": day, "profit": round(running, 2)})
        cumulative[engine] = series

    payload = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "days": days,
        "engines": [_engine_meta(e) for e in engines_seen],
        "totals": totals,
        "daily": [{"day": d, "engines": by_day[d]} for d in day_list],
        "cumulative": cumulative,
        "errors": errors,
        "v5_version": VERSION,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _cache[days] = (now, payload)
    return payload


def v5_day(db: Session, day: date) -> dict[str, Any]:
    plays = plays_for_day(db, day)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in plays:
        groups[p["specialist"]].append(p)
    specialists = [
        {"key": s.key, "label": s.label, "status": s.status} for s in STAT_SPECIALISTS
    ] + [{"key": VALORE_KEY, "label": VALORE_LABEL, "status": "osservazione"}]
    out = []
    for s in specialists:
        items = groups.get(s["key"], [])
        settled = [(p["result"] == "vinta", p["quota"]) for p in items if p["result"] in ("vinta", "persa")]
        out.append({**s, "plays": items, "summary": roi_stats(settled)})
    return {"day": day.isoformat(), "version": VERSION, "specialists": out}
