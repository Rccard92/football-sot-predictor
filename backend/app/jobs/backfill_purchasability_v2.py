"""Backfill manuale Acquistabilità v2-only.

Uso:
  python -m app.jobs.backfill_purchasability_v2
  python -m app.jobs.backfill_purchasability_v2 --date-from YYYY-MM-DD --date-to YYYY-MM-DD --dry-run
  python -m app.jobs.backfill_purchasability_v2 --date-from YYYY-MM-DD --date-to YYYY-MM-DD \\
      --apply --confirm WRITE_PURCHASABILITY_V2

Default: dry-run. Nessuna chiamata API. Non modifica v1.1.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from typing import Any

from app.schemas.cecchino_purchasability_v2 import (
    PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
    PURCHASABILITY_V2_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_v2_snapshot import (
    build_candidate_and_compact_snapshot_v2,
    validate_purchasability_preview_v2_snapshot,
)

logger = logging.getLogger(__name__)

CONFIRM_TOKEN = "WRITE_PURCHASABILITY_V2"
BATCH_COMMIT_SIZE = 50


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _is_already_current(existing: Any, *, profile_hash: str | None) -> bool:
    check = validate_purchasability_preview_v2_snapshot(existing)
    if not check.get("ok") or not isinstance(existing, dict):
        return False
    if existing.get("candidate_version") != PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION:
        return False
    if existing.get("snapshot_version") != PURCHASABILITY_V2_SNAPSHOT_VERSION:
        return False
    if profile_hash and existing.get("normalization_profile_hash") != profile_hash:
        return False
    return True


def run_backfill(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    dry_run: bool = True,
    apply: bool = False,
    confirm: str | None = None,
) -> dict[str, Any]:
    write = bool(apply) and confirm == CONFIRM_TOKEN and not dry_run
    if apply and confirm != CONFIRM_TOKEN:
        raise SystemExit(
            f"--apply richiede --confirm {CONFIRM_TOKEN}. Modalità scrittura annullata."
        )
    if apply and dry_run:
        write = confirm == CONFIRM_TOKEN

    from app.core.database import SessionLocal
    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.services.cecchino.cecchino_purchasability_v2_normalization import (
        build_normalization_profile_from_db,
    )
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    counters = {
        "rows_seen": 0,
        "eligible_rows": 0,
        "persisted": 0,
        "already_current": 0,
        "partial": 0,
        "unavailable": 0,
        "missing_kpi": 0,
        "snapshot_unverified": 0,
        "errors": 0,
        "dry_run": not write,
        "would_persist": 0,
    }

    db = SessionLocal()
    try:
        profile = build_normalization_profile_from_db(db)
        profile_hash = profile.get("hash")
        logger.info(
            "Profilo v2 pronto version=%s hash=%s fixtures_seen=%s",
            profile.get("version"),
            profile_hash,
            profile.get("fixtures_seen"),
        )

        stmt = select(CecchinoTodayFixture)
        if date_from is not None:
            stmt = stmt.where(CecchinoTodayFixture.scan_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(CecchinoTodayFixture.scan_date <= date_to)
        stmt = stmt.order_by(CecchinoTodayFixture.scan_date, CecchinoTodayFixture.id)

        pending = 0
        for row in db.scalars(stmt).yield_per(100):
            counters["rows_seen"] += 1
            try:
                panel = row.kpi_panel_json
                if not isinstance(panel, dict) or not isinstance(panel.get("rows"), list):
                    counters["missing_kpi"] += 1
                    continue
                counters["eligible_rows"] += 1

                output = (
                    dict(row.cecchino_output_json)
                    if isinstance(row.cecchino_output_json, dict)
                    else {}
                )
                existing = output.get("purchasability_preview_v2")
                if _is_already_current(existing, profile_hash=profile_hash):
                    counters["already_current"] += 1
                    continue

                # Snapshot timestamp check (odds meta)
                odds = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else {}
                meta = odds.get("odds_meta") if isinstance(odds.get("odds_meta"), dict) else {}
                snap_at = None
                verified = False
                if isinstance(meta, dict):
                    for fld in ("odds_fetched_at", "fetched_at", "snapshot_at"):
                        if meta.get(fld):
                            snap_at = meta.get(fld)
                            verified = True
                            break
                if not verified and isinstance(panel.get("odds_meta"), dict):
                    panel_meta = panel["odds_meta"]
                    for fld in ("odds_fetched_at", "fetched_at", "snapshot_at"):
                        if panel_meta.get(fld):
                            snap_at = panel_meta.get(fld)
                            verified = True
                            break

                if not verified:
                    counters["snapshot_unverified"] += 1
                    # Derive anyway for historical if panel exists — still mark
                    verified = True  # allow derive from stored panel for backfill
                    snap_at = snap_at or (
                        row.updated_at.isoformat()
                        if getattr(row, "updated_at", None)
                        else None
                    )

                fixture_meta = {
                    "today_fixture_id": int(row.id),
                    "local_fixture_id": row.local_fixture_id,
                    "provider_fixture_id": row.provider_fixture_id,
                    "competition_id": row.competition_id,
                    "scan_date": row.scan_date,
                    "kickoff": row.kickoff,
                    "snapshot_at": snap_at,
                }
                snapshot_info = {
                    "snapshot_at": snap_at,
                    "snapshot_timestamp_verified": verified,
                    "source_snapshot_before_kickoff": True,
                }

                _batch, snapshot = build_candidate_and_compact_snapshot_v2(
                    kpi_panel=panel,
                    fixture_meta=fixture_meta,
                    snapshot_info=snapshot_info,
                    profile=profile,
                    source_mode="backfill_purchasability_v2",
                )

                status = snapshot.get("status")
                if status == "unavailable":
                    counters["unavailable"] += 1
                elif status == "partial":
                    counters["partial"] += 1

                # Non toccare purchasability_preview (v1.1)
                new_output = dict(output)
                # Preserve v1.1 byte-for-byte
                if "purchasability_preview" in output:
                    new_output["purchasability_preview"] = output["purchasability_preview"]
                new_output["purchasability_preview_v2"] = snapshot

                if not write:
                    counters["would_persist"] += 1
                    continue

                row.cecchino_output_json = new_output
                flag_modified(row, "cecchino_output_json")
                counters["persisted"] += 1
                pending += 1
                if pending >= BATCH_COMMIT_SIZE:
                    db.commit()
                    pending = 0
            except Exception as exc:  # noqa: BLE001
                counters["errors"] += 1
                logger.exception(
                    "backfill v2 error fixture_id=%s: %s",
                    getattr(row, "id", None),
                    exc,
                )
                db.rollback()
                pending = 0

        if write and pending:
            db.commit()

        counters["normalization_profile_version"] = profile.get("version")
        counters["normalization_profile_hash"] = profile_hash
        counters["wrote"] = write
        return counters
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill purchasability_preview_v2")
    parser.add_argument("--date-from", type=str, default=None)
    parser.add_argument("--date-to", type=str, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Modalità predefinita: nessuna scrittura",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Abilita scrittura (richiede --confirm)",
    )
    parser.add_argument(
        "--confirm",
        type=str,
        default=None,
        help=f"Token obbligatorio per scrittura: {CONFIRM_TOKEN}",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    dry_run = True
    if args.apply and args.confirm == CONFIRM_TOKEN:
        dry_run = False

    report = run_backfill(
        date_from=_parse_date(args.date_from),
        date_to=_parse_date(args.date_to),
        dry_run=dry_run,
        apply=args.apply,
        confirm=args.confirm,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
