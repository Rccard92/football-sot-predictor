"""Cron formazioni pre-match Cecchino (API-Football).

Uso (Railway cron ogni 10 minuti):
  python -m app.jobs.cecchino_prematch_lineups
"""

from __future__ import annotations

import json
import logging
import sys

from app.core.database import SessionLocal
from app.services.cecchino_live.prematch_lineups import run_prematch_lineups

logger = logging.getLogger(__name__)


def main() -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    db = SessionLocal()
    try:
        result = run_prematch_lineups(db)
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
