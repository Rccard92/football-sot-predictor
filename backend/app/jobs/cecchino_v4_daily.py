"""Cron Cecchino V4 (Railway): un comando per ogni servizio programmato.

    python -m app.jobs.cecchino_v4_daily daily     # 08:00 Roma: partite -> quote -> previsioni + ragionamenti + shortlist -> regolamento
    python -m app.jobs.cecchino_v4_daily odds      # pomeriggio/sera: istantanea quote, shortlist aggiornata, regolamento
    python -m app.jobs.cecchino_v4_daily prematch  # ogni 30 min: formazioni e quote di chiusura delle partite imminenti, poi risultati
    python -m app.jobs.cecchino_v4_daily predict   # solo previsioni e shortlist
    python -m app.jobs.cecchino_v4_daily settle    # solo regolamento

Esce subito, senza chiamate, se CECCHINO_V4_ENABLED non e' vero. Ogni job live registra le chiamate
API-Football e si ferma da solo al limite giornaliero.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from app.core.database import SessionLocal
from app.services.cecchino_v4.settings import v4_enabled

logger = logging.getLogger("cecchino_v4_daily")

PLANS: dict[str, list[str]] = {
    "daily": ["fixtures", "odds_snapshot", "post_match", "predict", "settle"],
    "odds": ["odds_snapshot", "shortlist", "settle"],
    "prematch": ["lineups", "odds_closing", "post_match", "shortlist", "settle"],
    "predict": ["predict"],
    "settle": ["settle"],
}


def run_plan(name: str) -> dict[str, Any]:
    from app.services.cecchino_v4.live import jobs as live_jobs
    from app.services.cecchino_v4.live.client import V4ApiClient
    from app.services.cecchino_v4.pipeline import dispatch

    out: dict[str, Any] = {"plan": name, "steps": {}}
    db = SessionLocal()
    try:
        client = V4ApiClient(db=db)
        for step in PLANS[name]:
            try:
                if step in dispatch.LIVE_JOBS:
                    row = live_jobs.run_job(db, step, client=client, params={})
                    out["steps"][step] = {"status": row.status, "api_calls": row.api_calls, "error": row.error_message}
                else:
                    out["steps"][step] = dispatch.run_compute(db, step, {})
            except live_jobs.JobAlreadyRunning as exc:
                out["steps"][step] = {"status": "skipped", "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 - un passo fallito non ferma gli altri
                logger.exception("passo %s fallito", step)
                db.rollback()
                out["steps"][step] = {"status": "failed", "error": f"{exc.__class__.__name__}: {exc}"[:500]}
    finally:
        db.close()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cron Cecchino V4")
    parser.add_argument("plan", choices=sorted(PLANS))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not v4_enabled():
        print(json.dumps({"plan": args.plan, "skipped": "CECCHINO_V4_ENABLED non attivo"}))
        return 0
    result = run_plan(args.plan)
    print(json.dumps(result, ensure_ascii=False, default=str)[:6000])
    failed = [k for k, v in result["steps"].items() if isinstance(v, dict) and v.get("status") == "failed"]
    return 1 if failed and len(failed) == len(result["steps"]) else 0


if __name__ == "__main__":
    sys.exit(main())
