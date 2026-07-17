"""Audit / riparazione gated identità fixture Today vs Fixture locale (Fase 2A.3).

Uso:
  cd backend && python -m scripts.audit_fixture_identity_9510
  cd backend && python -m scripts.audit_fixture_identity_9510 --dry-run
  cd backend && python -m scripts.audit_fixture_identity_9510 --apply-confirmed-fix --case A

Default: sempre dry-run. Nessuna scrittura senza --apply-confirmed-fix --case A|B.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TODAY_ID = 9510
LOCAL_ID = 562


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat()
    return str(v)


def _propose_case(today, local) -> dict:
    """Propone A/B solo se i raw distinguono chiaramente; altrimenti undetermined."""
    if today is None or local is None:
        return {"case": "undetermined", "reason": "missing_today_or_local"}

    today_ko = today.kickoff
    local_ko = local.kickoff_at
    today_finished = (today.match_display_status or "").lower() == "finished" or (
        today.fixture_status or ""
    ).upper() in {"FT", "AET", "PEN"}
    today_has_score = today.goals_home is not None and today.goals_away is not None
    local_upcoming = (local.status or "").upper() in {"NS", "TBD", "PST"}

    # Segnale tipico Caso A: Today passato+FT+score, Local kickoff futuro diverso giorno
    if (
        today_ko
        and local_ko
        and today_ko.date() != local_ko.date()
        and today_finished
        and today_has_score
        and local_ko > datetime.now(timezone.utc)
    ):
        return {
            "case": "A_candidate",
            "reason": (
                "Today finished+score su data passata; Local kickoff futuro diverso. "
                "Confermare prima di --apply --case A (ripristina Local → Today kickoff)."
            ),
        }

    # Segnale tipico Caso B: Local/calc futuro coerente, Today FT/score su data diversa
    if (
        today_ko
        and local_ko
        and today_ko.date() != local_ko.date()
        and today_finished
        and local_upcoming
        and local_ko > datetime.now(timezone.utc)
    ):
        return {
            "case": "B_candidate",
            "reason": (
                "Today finished mentre Local upcoming su data futura. "
                "Potrebbe essere score/status Today stale (Caso B) oppure Local errato (Caso A). "
                "Non auto-scegliere: usa audit Railway."
            ),
        }

    return {"case": "undetermined", "reason": "insufficient_discrimination"}


def _apply_case_a(db, today, local) -> dict:
    """Caso A: Today corretto → allinea Fixture locale al kickoff Today."""
    if today.kickoff is None:
        return {"applied": False, "reason": "today_kickoff_missing"}
    old = local.kickoff_at
    local.kickoff_at = today.kickoff
    db.add(local)
    db.commit()
    return {
        "applied": True,
        "case": "A",
        "fixture_id": int(local.id),
        "from": _iso(old),
        "to": _iso(today.kickoff),
        "note": "Local kickoff allineato a Today. Rigenerare snapshot single-fixture separatamente.",
    }


def _apply_case_b(db, today, local) -> dict:
    """Caso B: Local corretto → invalida score/status stale su Today; allinea kickoff a Local."""
    if local.kickoff_at is None:
        return {"applied": False, "reason": "local_kickoff_missing"}
    old_ko = today.kickoff
    old_status = today.fixture_status
    old_display = today.match_display_status
    old_gh, old_ga = today.goals_home, today.goals_away
    today.kickoff = local.kickoff_at
    today.fixture_status = local.status
    today.match_display_status = "upcoming"
    today.goals_home = None
    today.goals_away = None
    today.score_fulltime_home = None
    today.score_fulltime_away = None
    warnings = list(today.warnings_json or [])
    msg = "case_b_stale_result_invalidated"
    if msg not in warnings:
        warnings.append(msg)
    today.warnings_json = warnings
    db.add(today)
    db.commit()
    return {
        "applied": True,
        "case": "B",
        "today_fixture_id": int(today.id),
        "kickoff_from": _iso(old_ko),
        "kickoff_to": _iso(local.kickoff_at),
        "cleared_status": {"from": old_status, "display_from": old_display},
        "cleared_score": {"home": old_gh, "away": old_ga},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit identity fixture 9510 (Fase 2A.3)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Solo lettura (default). Nessuna scrittura.",
    )
    parser.add_argument(
        "--apply-confirmed-fix",
        action="store_true",
        default=False,
        help="Applica fix solo con --case A|B. Disabilita dry-run.",
    )
    parser.add_argument(
        "--case",
        choices=["A", "B"],
        default=None,
        help="Caso confermato dall'audit umano (richiesto con --apply-confirmed-fix).",
    )
    parser.add_argument("--today-id", type=int, default=TODAY_ID)
    parser.add_argument("--local-id", type=int, default=LOCAL_ID)
    args = parser.parse_args(argv)

    dry_run = not args.apply_confirmed_fix

    if args.apply_confirmed_fix and args.case is None:
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "--apply-confirmed-fix richiede --case A|B",
                    "dry_run": True,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2

    if not os.environ.get("DATABASE_URL") and not Path(".env").exists():
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "dry_run": True,
                    "reason": "DATABASE_URL / backend/.env non disponibili",
                    "hint": "Usa GET /api/admin/cecchino/audit/fixture-identity/9510 su Railway",
                    "protection_shipped": [
                        "GET detail read-only (no auto-realign)",
                        "fixture_identity_consistency su raw sources",
                        "balance_v5_preview_v1_2 blocked if inconsistent",
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    from app.core.database import SessionLocal
    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.models.fixture import Fixture
    from app.services.cecchino.cecchino_fixture_identity_audit import build_fixture_identity_audit

    db = SessionLocal()
    try:
        audit = build_fixture_identity_audit(db, args.today_id)
        today = db.get(CecchinoTodayFixture, args.today_id)
        local = None
        if today and today.local_fixture_id:
            local = db.get(Fixture, int(today.local_fixture_id))
        elif args.local_id:
            local = db.get(Fixture, args.local_id)

        proposal = _propose_case(today, local)
        report = {
            "status": "ok",
            "dry_run": dry_run,
            "audit": audit,
            "case_proposal": proposal,
            "apply": None,
        }

        if dry_run:
            report["apply"] = {
                "applied": False,
                "reason": "dry_run_default",
                "hint": "Per applicare: --apply-confirmed-fix --case A|B dopo conferma audit",
            }
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 0

        if today is None or local is None:
            report["apply"] = {"applied": False, "reason": "missing_records"}
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 1

        if args.case == "A":
            report["apply"] = _apply_case_a(db, today, local)
        else:
            report["apply"] = _apply_case_b(db, today, local)

        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report["apply"].get("applied") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
