"""Cron formazioni pre-match Cecchino (API-Football).

Uso (Railway cron ogni 10 minuti):
  python -m app.jobs.cecchino_prematch_lineups
Esecuzione forzata (tutte le partite eleggibili delle prossime 24 ore):
  python -m app.jobs.cecchino_prematch_lineups --force
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.cecchino_live.prematch_lineups import run_prematch_lineups

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs.cecchino_prematch_lineups")
    parser.add_argument("--force", action="store_true", help="tutte le partite eleggibili delle prossime 24 ore")
    args = parser.parse_args(argv)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    if not args.force and not get_settings().cecchino_prematch_lineups_enabled:
        logger.info("cecchino_prematch_lineups in pausa (CECCHINO_PREMATCH_LINEUPS_ENABLED=false)")
        return 0
    db = SessionLocal()
    try:
        result = run_prematch_lineups(db, force=args.force)
        logger.info("cecchino_prematch_lineups %s", json.dumps(result, default=str))
        return 0
    except Exception:  # noqa: BLE001
        logger.exception("cecchino_prematch_lineups fallito")
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
