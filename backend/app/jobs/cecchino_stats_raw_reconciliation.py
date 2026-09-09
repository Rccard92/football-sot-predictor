"""CLI dry-run riconciliazione stats Cecchino Lab da raw_json.

Uso (solo read-only):
  cd backend
  python -m app.jobs.cecchino_stats_raw_reconciliation --dry-run --output-dir "<dir>"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Riconciliazione stats BLOCCO 2 da raw_json: dry-run read-only "
            "(nessun UPDATE)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Obbligatorio: solo SELECT + report filesystem",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory di output per summary JSON e audit CSV",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.dry_run:
        parser.error("--dry-run è obbligatorio (nessun apply in questo job)")

    from app.core.database import SessionLocal
    from app.services.cecchino_data_lab.stats_raw_reconciliation.dry_run import (
        run_stats_raw_reconciliation_dry_run,
    )

    output_dir = Path(args.output_dir)
    db = SessionLocal()
    try:
        summary = run_stats_raw_reconciliation_dry_run(
            session=db,
            output_dir=output_dir,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("stats raw reconciliation dry-run fallito: %s", exc)
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
