"""CLI export RUN V2: rigenera i cinque artefatti dal DB.

  cd backend
  python -m app.jobs.cecchino_run_v2_export --run-id 12 --output-dir /tmp/run_v2

L'export e sempre ricostruibile: il DB e la sorgente di verita, i file sono
solo un artefatto di comodita.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export artefatti di una RUN V2")
    parser.add_argument("--run-id", type=int, required=True, help="ID della run")
    parser.add_argument("--output-dir", required=True, help="Directory di destinazione")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)

    from app.core.database import SessionLocal
    from app.services.cecchino_data_lab.run_v2.export import build_export_bundle

    db = SessionLocal()
    try:
        manifest = build_export_bundle(
            db, run_id=int(args.run_id), output_dir=Path(args.output_dir)
        )
        print(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("export run_v2 %s fallito: %s", args.run_id, exc)
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
