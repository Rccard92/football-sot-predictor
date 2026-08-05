"""CLI backfill formule Cecchino V3.1 Fase 1B.

Uso:
  python -m app.jobs.backfill_cecchino_formulas_v31_phase1b \\
      --date-from YYYY-MM-DD --date-to YYYY-MM-DD --limit N

  python -m app.jobs.backfill_cecchino_formulas_v31_phase1b \\
      --date-from YYYY-MM-DD --date-to YYYY-MM-DD --limit N \\
      --apply --confirm WRITE_FORMULA_BACKFILL_V31_P1B

  python -m app.jobs.backfill_cecchino_formulas_v31_phase1b --fixture-id 123

Default: dry-run. Nessuna chiamata API bookmaker.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from typing import Any

from app.services.cecchino.cecchino_formula_backfill_v31 import (
    CONFIRM_TOKEN,
    run_formula_backfill_v31_phase1b,
)

logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill mirato formule Cecchino V3.1 Fase 1B (dry-run default)",
    )
    parser.add_argument("--date-from", type=str, default=None)
    parser.add_argument("--date-to", type=str, default=None)
    parser.add_argument("--fixture-id", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--force", action="store_true", default=False)
    parser.add_argument("--confirm", type=str, default=None)
    args = parser.parse_args(argv)

    if args.dry_run and args.apply:
        parser.error("Non usare --dry-run e --apply insieme")

    # Default dry-run se non --apply
    dry_run = True
    if args.apply:
        if args.confirm != CONFIRM_TOKEN:
            print(
                f"--apply richiede --confirm {CONFIRM_TOKEN}. Modalità scrittura annullata.",
                file=sys.stderr,
            )
            return 2
        dry_run = False
    elif args.dry_run:
        dry_run = True

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        report: dict[str, Any] = run_formula_backfill_v31_phase1b(
            db,
            date_from=_parse_date(args.date_from),
            date_to=_parse_date(args.date_to),
            fixture_id=args.fixture_id,
            dry_run=dry_run,
            force=bool(args.force),
            limit=args.limit,
            batch_size=args.batch_size,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        logger.exception("backfill failed")
        if not dry_run:
            db.rollback()
        return 1
    finally:
        db.close()

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if not report.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
