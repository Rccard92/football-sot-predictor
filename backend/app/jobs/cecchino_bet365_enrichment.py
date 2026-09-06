"""CLI dry-run enrichment storico Bet365 → CecchinoLabMatch.

Uso:
  cd backend
  python -m app.jobs.cecchino_bet365_enrichment --csv "<file>" --dry-run --output-dir "<dir>"

Solo SELECT + report. Nessuna scrittura DB. Nessun --apply in questa fase.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.services.cecchino_data_lab.bet365_enrichment.dry_run import (
    run_bet365_enrichment_dry_run,
)

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run matching CSV Bet365 (*_last_seen) → CecchinoLabMatch. "
            "Nessuna scrittura DB."
        )
    )
    parser.add_argument("--csv", required=True, help="Path del CSV di enrichment")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Obbligatorio: esegue solo SELECT + report (nessuna scrittura)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory di output per summary/detail/anomalies",
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
        parser.error("--dry-run è obbligatorio in questa fase")

    from app.core.database import SessionLocal

    csv_path = Path(args.csv)
    output_dir = Path(args.output_dir)

    db = SessionLocal()
    try:
        summary = run_bet365_enrichment_dry_run(
            csv_path=csv_path,
            output_dir=output_dir,
            session=db,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("dry-run enrichment fallito: %s", exc)
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        # Mai commit: chiude senza scrivere
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
