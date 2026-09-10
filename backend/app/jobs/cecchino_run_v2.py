"""CLI RUN V2 Cecchino Lab.

La scrittura sul DB richiede sempre un token di conferma esplicito.

  cd backend

  # Preflight read-only: nessuna riga scritta
  python -m app.jobs.cecchino_run_v2 --preflight

  # Run pilota su una stagione
  python -m app.jobs.cecchino_run_v2 --season 2024/2025 --max-matches 50 \\
    --confirm RUN_CECCHINO_RUN_V2

  # Run completa su una stagione
  python -m app.jobs.cecchino_run_v2 --season 2024/2025 --confirm RUN_CECCHINO_RUN_V2

  # Run completa stagione + export dei cinque artefatti
  python -m app.jobs.cecchino_run_v2 --season 2024/2025 --confirm RUN_CECCHINO_RUN_V2 \\
    --export-dir /tmp/run_v2
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
        description="Esegue una RUN V2 sul dataset storico Cecchino Lab"
    )
    parser.add_argument(
        "--confirm",
        default=None,
        help="Token di conferma obbligatorio per scrivere sul DB",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        default=False,
        help="Solo conteggi read-only: dataset, match, copertura quote",
    )
    parser.add_argument(
        "--season",
        default=None,
        help="Stagione Lab obbligatoria (es. 2024/2025). Scope della RUN.",
    )
    parser.add_argument(
        "--max-matches",
        type=int,
        default=None,
        help="Limita la run ai primi N match della stagione (ordine cronologico)",
    )
    parser.add_argument(
        "--resume-run-id",
        type=int,
        default=None,
        help="Riprende una run esistente invece di crearne una nuova",
    )
    parser.add_argument(
        "--export-dir",
        default=None,
        help="Se valorizzato, genera i cinque artefatti al termine della run",
    )
    parser.add_argument(
        "--git-commit",
        default=None,
        help="Commit sorgente da registrare nella run",
    )
    return parser


def _preflight() -> int:
    from sqlalchemy import func, select

    from app.core.database import SessionLocal
    from app.models.cecchino_lab_dataset import CecchinoLabDataset
    from app.models.cecchino_lab_match import CecchinoLabMatch
    from app.services.cecchino_data_lab.run_v2.constants import (
        CORE_MARKETS,
        ECONOMIC_QUOTE_COLUMNS,
        STRICT_QUOTE_COLUMNS,
    )

    db = SessionLocal()
    try:
        datasets = int(db.execute(select(func.count(CecchinoLabDataset.id))).scalar() or 0)
        matches = int(db.execute(select(func.count(CecchinoLabMatch.id))).scalar() or 0)
        first, last = db.execute(
            select(func.min(CecchinoLabMatch.kickoff_at), func.max(CecchinoLabMatch.kickoff_at))
        ).one()

        coverage: dict[str, int] = {}
        for column in (*STRICT_QUOTE_COLUMNS, *ECONOMIC_QUOTE_COLUMNS):
            attribute = getattr(CecchinoLabMatch, column, None)
            if attribute is None:
                coverage[column] = -1
                continue
            coverage[column] = int(
                db.execute(select(func.count()).where(attribute.is_not(None))).scalar() or 0
            )

        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "preflight",
                    "datasets": datasets,
                    "matches": matches,
                    "kickoff_range": {
                        "first": first.isoformat() if first else None,
                        "last": last.isoformat() if last else None,
                    },
                    "core_markets": len(CORE_MARKETS),
                    "quote_coverage": coverage,
                    "writes_performed": False,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        db.rollback()
        db.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.preflight:
        return _preflight()

    from app.core.database import SessionLocal
    from app.services.cecchino_data_lab.run_v2.constants import RUN_V2_CONFIRM_TOKEN
    from app.services.cecchino_data_lab.run_v2.executor import create_run_v2, execute_run_v2

    if args.confirm != RUN_V2_CONFIRM_TOKEN:
        parser.error(
            f"--confirm {RUN_V2_CONFIRM_TOKEN} e obbligatorio per scrivere sul DB"
        )

    db = SessionLocal()
    try:
        if args.resume_run_id:
            run_id = int(args.resume_run_id)
        else:
            if not args.season:
                parser.error("--season e obbligatorio (es. 2024/2025)")
            run = create_run_v2(
                db,
                season_label=args.season,
                max_matches=args.max_matches,
                source_git_commit=args.git_commit,
                run_scope="pilot" if args.max_matches else "full",
            )
            run_id = int(run.id)
    finally:
        db.close()

    try:
        result = execute_run_v2(run_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_v2 %s fallita: %s", run_id, exc)
        print(
            json.dumps({"ok": False, "run_id": run_id, "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 1

    payload = {"ok": True, "run_id": run_id, **result}

    if args.export_dir:
        from app.services.cecchino_data_lab.run_v2.export import build_export_bundle

        db = SessionLocal()
        try:
            payload["export"] = build_export_bundle(
                db, run_id=run_id, output_dir=Path(args.export_dir)
            )
        finally:
            db.close()

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("status") not in {"failed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
