"""CLI enrichment storico Bet365 → CecchinoLabMatch.

Uso prepare (read-only):
  cd backend
  python -m app.jobs.cecchino_bet365_enrichment --csv "<file>" --dry-run --output-dir "<dir>"
  python -m app.jobs.cecchino_bet365_enrichment --csv "<file>" --dry-run \\
    --prepare-apply --output-dir "<dir>"

Uso apply (solo plan congelato + summary; nessun rematching):
  python -m app.jobs.cecchino_bet365_enrichment \\
    --apply-plan "<bet365_enrichment_apply_plan.csv>" \\
    --apply-summary "<bet365_enrichment_apply_summary.json>" \\
    --output-dir "<dir>"

  # Scrittura reale (esplicita):
  python -m app.jobs.cecchino_bet365_enrichment \\
    --apply-plan "<plan.csv>" --apply-summary "<summary.json>" \\
    --output-dir "<dir>" --confirm-apply
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
            "Bet365 enrichment: dry-run/prepare-apply (read-only) oppure "
            "apply del plan congelato."
        )
    )
    parser.add_argument("--csv", default=None, help="Path del CSV di enrichment")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Modalità prepare: solo SELECT + report (nessuna scrittura)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory di output per report/plan/result",
    )
    parser.add_argument(
        "--fuzzy-suggestions",
        action="store_true",
        default=False,
        help=(
            "Abilita suggerimenti fuzzy diagnostici (SequenceMatcher) "
            "su AMBIGUOUS/NOT_FOUND; non assegna mai un match. Default: off."
        ),
    )
    parser.add_argument(
        "--discover-aliases",
        action="store_true",
        default=False,
        help=(
            "Dopo il matching, esegue Alias Discovery V2 (kickoff profile, "
            "anchor, bootstrap). Non modifica TEAM_ALIASES né il DB."
        ),
    )
    parser.add_argument(
        "--prepare-apply",
        action="store_true",
        default=False,
        help=(
            "Genera bet365_enrichment_apply_plan.csv + summary (read-only). "
            "Forza Alias Discovery V2 e matching simulato."
        ),
    )
    parser.add_argument(
        "--apply-plan",
        default=None,
        help="Path del plan CSV congelato (modalità apply)",
    )
    parser.add_argument(
        "--apply-summary",
        default=None,
        help="Path del summary JSON del plan (modalità apply)",
    )
    parser.add_argument(
        "--confirm-apply",
        action="store_true",
        default=False,
        help=(
            "Obbligatorio per scrivere sul DB in modalità apply. "
            "Senza questo flag: solo preflight + pre-state read-only."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)

    apply_mode = bool(args.apply_plan or args.apply_summary)
    prepare_mode = bool(args.dry_run or args.csv or args.prepare_apply)

    if apply_mode and prepare_mode:
        parser.error(
            "Modalità apply (--apply-plan/--apply-summary) e prepare "
            "(--csv/--dry-run/--prepare-apply) sono mutualmente esclusive"
        )

    if apply_mode:
        if not args.apply_plan or not args.apply_summary:
            parser.error("--apply-plan e --apply-summary sono entrambi obbligatori")
        return _run_apply(args)

    if not args.dry_run:
        parser.error("--dry-run è obbligatorio in modalità prepare")
    if not args.csv:
        parser.error("--csv è obbligatorio in modalità prepare")
    return _run_prepare(args)


def _run_prepare(args: argparse.Namespace) -> int:
    from app.core.database import SessionLocal
    from app.services.cecchino_data_lab.bet365_enrichment.dry_run import (
        run_bet365_enrichment_dry_run,
    )

    csv_path = Path(args.csv)
    output_dir = Path(args.output_dir)
    db = SessionLocal()
    try:
        summary = run_bet365_enrichment_dry_run(
            csv_path=csv_path,
            output_dir=output_dir,
            session=db,
            fuzzy_suggestions=bool(args.fuzzy_suggestions),
            discover_aliases=bool(args.discover_aliases),
            prepare_apply=bool(args.prepare_apply),
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("dry-run enrichment fallito: %s", exc)
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        db.close()


def _run_apply(args: argparse.Namespace) -> int:
    from app.core.database import SessionLocal
    from app.services.cecchino_data_lab.bet365_enrichment.apply_plan import (
        run_bet365_enrichment_apply,
    )

    db = SessionLocal()
    try:
        result = run_bet365_enrichment_apply(
            session=db,
            plan_path=Path(args.apply_plan),
            summary_path=Path(args.apply_summary),
            output_dir=Path(args.output_dir),
            confirm_apply=bool(args.confirm_apply),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if result.get("committed"):
            return 0
        if result.get("abort_code") == "ABORT_CONFIRM_REQUIRED":
            return 0
        return 2
    except Exception as exc:  # noqa: BLE001
        logger.exception("apply enrichment fallito: %s", exc)
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
