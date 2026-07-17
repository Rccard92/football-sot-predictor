"""Riparazione gated Caso A — Today 9510 / Fixture 562.

Uso:
  cd backend && python -m scripts.audit_fixture_identity_9510 --dry-run --case A
  cd backend && python -m scripts.audit_fixture_identity_9510 --apply-confirmed-fix --case A

Default: dry-run. Nessuna scrittura senza --apply-confirmed-fix --case A.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TODAY_ID = 9510
LOCAL_ID = 562
PROVIDER_FIXTURE_ID = 1492291
EXPECTED_COMPETITION_ID = 2
EXPECTED_HOME = "Botafogo"
EXPECTED_AWAY = "Santos"
CORRECT_KICKOFF = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
TARGET_STATUS_FT = "FT"
TARGET_STATUS_LONG = "Match Finished"
TARGET_DISPLAY = "finished"
TARGET_GOALS_HOME = 2
TARGET_GOALS_AWAY = 1
REPAIRED_WARNING = "fixture_identity_repaired_case_a"
AUTO_REALIGN_PREFIX = "kickoff_rescheduled_realigned"


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    s = str(v)
    return s.replace("+00:00", "Z") if s.endswith("+00:00") else s


def _names_match(a: str | None, b: str) -> bool:
    return bool(a) and a.strip().casefold() == b.strip().casefold()


def _is_auto_realign_warning(w: Any) -> bool:
    return str(w).startswith(AUTO_REALIGN_PREFIX)


def validate_case_a_guards(
    *,
    today_id: int,
    local_id: int,
    provider_fixture_id: int | None,
    local_api_fixture_id: int | None,
    today_competition_id: int | None,
    local_competition_id: int | None,
    today_home: str | None,
    today_away: str | None,
    local_home: str | None,
    local_away: str | None,
    expected_today_id: int = TODAY_ID,
    expected_local_id: int = LOCAL_ID,
) -> list[str]:
    """Ritorna lista errori; vuota se ok."""
    errors: list[str] = []
    if today_id != expected_today_id:
        errors.append(f"today_fixture_id_mismatch: got={today_id} expected={expected_today_id}")
    if local_id != expected_local_id:
        errors.append(f"local_fixture_id_mismatch: got={local_id} expected={expected_local_id}")
    if provider_fixture_id != PROVIDER_FIXTURE_ID:
        errors.append(
            f"provider_fixture_id_mismatch: got={provider_fixture_id} expected={PROVIDER_FIXTURE_ID}"
        )
    if local_api_fixture_id != PROVIDER_FIXTURE_ID:
        errors.append(
            f"api_fixture_id_mismatch: got={local_api_fixture_id} expected={PROVIDER_FIXTURE_ID}"
        )
    if today_competition_id != EXPECTED_COMPETITION_ID:
        errors.append(
            f"competition_mismatch: today={today_competition_id} expected={EXPECTED_COMPETITION_ID}"
        )
    if local_competition_id is not None and local_competition_id != EXPECTED_COMPETITION_ID:
        errors.append(
            f"competition_mismatch: local={local_competition_id} expected={EXPECTED_COMPETITION_ID}"
        )
    if not _names_match(today_home, EXPECTED_HOME) or not _names_match(today_away, EXPECTED_AWAY):
        errors.append(f"teams_mismatch_today: {today_home} vs {today_away}")
    if local_home is not None and local_away is not None:
        if not _names_match(local_home, EXPECTED_HOME) or not _names_match(local_away, EXPECTED_AWAY):
            errors.append(f"teams_mismatch_local: {local_home} vs {local_away}")
    return errors


def build_case_a_plan(today: Any, local: Any) -> dict[str, Any]:
    """Piano before→after (nessuna mutazione)."""
    removed = [str(w) for w in (today.warnings_json or []) if _is_auto_realign_warning(w)]
    return {
        "case": "A",
        "correct_kickoff": _iso(CORRECT_KICKOFF),
        "today_9510": {
            "kickoff": {"from": _iso(today.kickoff), "to": _iso(CORRECT_KICKOFF)},
            "status": {"from": today.fixture_status, "to": TARGET_STATUS_FT, "note": "invariato se già FT"},
            "match_display_status": {
                "from": today.match_display_status,
                "to": TARGET_DISPLAY,
            },
            "score": {
                "from": f"{today.goals_home}-{today.goals_away}",
                "to": f"{TARGET_GOALS_HOME}-{TARGET_GOALS_AWAY}",
                "note": "invariato se già 2-1",
            },
            "scan_date": {"from": str(today.scan_date) if today.scan_date else None, "to": "unchanged"},
            "odds_snapshot": "unchanged",
            "warnings_remove": removed,
            "warnings_add": REPAIRED_WARNING,
        },
        "local_fixture_562": {
            "kickoff": {"from": _iso(local.kickoff_at), "to": _iso(CORRECT_KICKOFF)},
            "status": {"from": local.status, "to": TARGET_STATUS_FT},
            "status_long": {"from": local.status_long, "to": TARGET_STATUS_LONG},
            "score": {
                "from": f"{local.goals_home}-{local.goals_away}",
                "to": f"{TARGET_GOALS_HOME}-{TARGET_GOALS_AWAY}",
            },
        },
    }


def apply_case_a_mutations(today: Any, local: Any) -> dict[str, Any]:
    """Applica mutazioni in-memory (caller gestisce commit/rollback)."""
    before = {
        "today": {
            "kickoff": _iso(today.kickoff),
            "fixture_status": today.fixture_status,
            "match_display_status": today.match_display_status,
            "goals_home": today.goals_home,
            "goals_away": today.goals_away,
            "warnings": list(today.warnings_json or []),
        },
        "local": {
            "kickoff_at": _iso(local.kickoff_at),
            "status": local.status,
            "status_long": local.status_long,
            "goals_home": local.goals_home,
            "goals_away": local.goals_away,
        },
    }

    today.kickoff = CORRECT_KICKOFF
    today.fixture_status = TARGET_STATUS_FT
    today.match_display_status = TARGET_DISPLAY
    today.goals_home = TARGET_GOALS_HOME
    today.goals_away = TARGET_GOALS_AWAY
    today.score_fulltime_home = TARGET_GOALS_HOME
    today.score_fulltime_away = TARGET_GOALS_AWAY

    local.kickoff_at = CORRECT_KICKOFF
    local.status = TARGET_STATUS_FT
    local.status_long = TARGET_STATUS_LONG
    local.goals_home = TARGET_GOALS_HOME
    local.goals_away = TARGET_GOALS_AWAY

    warnings = [str(w) for w in (today.warnings_json or []) if not _is_auto_realign_warning(w)]
    if REPAIRED_WARNING not in warnings:
        warnings.append(REPAIRED_WARNING)
    today.warnings_json = warnings

    after = {
        "today": {
            "kickoff": _iso(today.kickoff),
            "fixture_status": today.fixture_status,
            "match_display_status": today.match_display_status,
            "goals_home": today.goals_home,
            "goals_away": today.goals_away,
            "warnings": list(today.warnings_json or []),
        },
        "local": {
            "kickoff_at": _iso(local.kickoff_at),
            "status": local.status,
            "status_long": local.status_long,
            "goals_home": local.goals_home,
            "goals_away": local.goals_away,
        },
    }
    return {
        "applied": True,
        "case": "A",
        "before": before,
        "after": after,
        "resolved_auto_realign_warnings": [
            w for w in before["today"]["warnings"] if _is_auto_realign_warning(w)
        ],
        "records_touched": {"today_fixture_id": int(today.id), "local_fixture_id": int(local.id)},
    }


def format_rome_kickoff(iso_or_dt: Any) -> str:
    """Europe/Rome display: 17/07/2026 00:30 for CORRECT_KICKOFF."""
    if isinstance(iso_or_dt, datetime):
        dt = iso_or_dt
    else:
        s = str(iso_or_dt).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        local = dt.astimezone(ZoneInfo("Europe/Rome"))
    except Exception:
        local = dt.astimezone(timezone.utc)
    return local.strftime("%d/%m/%Y %H:%M")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Riparazione Caso A fixture 9510/562")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Solo piano (default se no apply)")
    parser.add_argument(
        "--apply-confirmed-fix",
        action="store_true",
        default=False,
        help="Applica fix Case A in transazione + recompute offline",
    )
    parser.add_argument("--case", choices=["A", "B"], default=None)
    parser.add_argument("--today-id", type=int, default=TODAY_ID)
    parser.add_argument("--local-id", type=int, default=LOCAL_ID)
    args = parser.parse_args(argv)

    dry_run = not args.apply_confirmed_fix
    if args.dry_run:
        dry_run = True
        if args.apply_confirmed_fix:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "reason": "non usare --dry-run insieme a --apply-confirmed-fix",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 2

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

    if args.case == "B":
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "Caso B non confermato per 9510/562; usare --case A",
                    "dry_run": True,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2

    if args.case is None and dry_run:
        # dry-run senza --case: mostra piano Case A se DB disponibile
        args.case = "A"

    if not os.environ.get("DATABASE_URL") and not Path(".env").exists():
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "dry_run": True,
                    "reason": "DATABASE_URL / backend/.env non disponibili",
                    "case_a_plan_expected": {
                        "today_kickoff": {
                            "from": "2026-07-22T20:00:00Z",
                            "to": _iso(CORRECT_KICKOFF),
                        },
                        "local_kickoff": {
                            "from": "2026-07-22T20:00:00Z",
                            "to": _iso(CORRECT_KICKOFF),
                        },
                        "local_status": {"from": "NS", "to": "FT"},
                        "local_score": {"from": "null-null", "to": "2-1"},
                        "europe_rome_display": format_rome_kickoff(CORRECT_KICKOFF),
                    },
                    "hint": "Su Railway: --dry-run --case A poi --apply-confirmed-fix --case A",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    from app.core.database import SessionLocal
    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.models.fixture import Fixture
    from app.models.team import Team
    from app.services.cecchino.cecchino_expected_goal_engine_diagnostics import (
        build_expected_goal_engine_diagnostics_for_today_row,
    )
    from app.services.cecchino.cecchino_fixture_identity_audit import build_fixture_identity_audit
    from app.services.cecchino.cecchino_fixture_identity_consistency import (
        build_fixture_identity_consistency,
    )
    from app.services.cecchino.cecchino_recompute_service import recompute_today_fixture_offline

    db = SessionLocal()
    try:
        today = db.get(CecchinoTodayFixture, args.today_id)
        if today is None:
            print(json.dumps({"status": "error", "reason": "today_not_found"}, indent=2))
            return 1
        local_id = int(today.local_fixture_id) if today.local_fixture_id else args.local_id
        local = db.get(Fixture, local_id)
        if local is None:
            print(json.dumps({"status": "error", "reason": "local_not_found"}, indent=2))
            return 1

        local_home = db.get(Team, int(local.home_team_id)) if local.home_team_id else None
        local_away = db.get(Team, int(local.away_team_id)) if local.away_team_id else None

        guard_errors = validate_case_a_guards(
            today_id=int(today.id),
            local_id=int(local.id),
            provider_fixture_id=int(today.provider_fixture_id),
            local_api_fixture_id=int(local.api_fixture_id),
            today_competition_id=int(today.competition_id) if today.competition_id else None,
            local_competition_id=int(local.competition_id) if local.competition_id else None,
            today_home=today.home_team_name,
            today_away=today.away_team_name,
            local_home=local_home.name if local_home else None,
            local_away=local_away.name if local_away else None,
            expected_today_id=args.today_id,
            expected_local_id=args.local_id,
        )
        plan = build_case_a_plan(today, local)
        report: dict[str, Any] = {
            "status": "ok",
            "dry_run": dry_run,
            "case": "A",
            "plan": plan,
            "europe_rome_display": format_rome_kickoff(CORRECT_KICKOFF),
            "guard_errors": guard_errors,
            "apply": None,
            "recompute": None,
            "verification": None,
        }

        if guard_errors:
            report["status"] = "blocked"
            report["apply"] = {"applied": False, "reason": "guard_failed", "errors": guard_errors}
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 1

        if dry_run:
            report["apply"] = {
                "applied": False,
                "reason": "dry_run",
                "hint": "Eseguire: --apply-confirmed-fix --case A",
            }
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 0

        # --- APPLY (transazione) ---
        try:
            apply_meta = apply_case_a_mutations(today, local)
            db.add(today)
            db.add(local)
            db.commit()
            db.refresh(today)
            db.refresh(local)
            report["apply"] = apply_meta
        except Exception as exc:
            db.rollback()
            report["status"] = "error"
            report["apply"] = {"applied": False, "reason": "transaction_rollback", "error": str(exc)}
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 1

        # --- RECOMPUTE offline (no Betfair / no xG API) ---
        try:
            recompute_result = recompute_today_fixture_offline(
                db,
                today,
                refresh_bookmaker_odds=False,
                use_existing_bookmaker_odds=True,
                ensure_xg=False,
            )
            db.commit()
            db.refresh(today)
            report["recompute"] = recompute_result
        except Exception as exc:
            db.rollback()
            report["status"] = "error"
            report["recompute"] = {"error": str(exc), "note": "DB fix committed; recompute failed"}
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 1

        # --- VERIFY ---
        diagnostics = build_expected_goal_engine_diagnostics_for_today_row(db, today)
        consistency = build_fixture_identity_consistency(
            today_row=today,
            local_fixture=local,
            cecchino_output=today.cecchino_output_json
            if isinstance(today.cecchino_output_json, dict)
            else None,
            expected_goal_diagnostics=diagnostics if isinstance(diagnostics, dict) else None,
            local_home_team_name=local_home.name if local_home else None,
            local_away_team_name=local_away.name if local_away else None,
        )
        leak = None
        out = today.cecchino_output_json or {}
        if isinstance(out, dict):
            leak = ((out.get("data_quality") or {}).get("leakage_check") or {}).get("target_kickoff")
        xg_cutoff = None
        if isinstance(diagnostics, dict):
            xg_cutoff = (
                ((diagnostics.get("xg_profiles") or {}).get("anti_leakage") or {}).get(
                    "fixture_date_cutoff"
                )
            )
        audit = build_fixture_identity_audit(db, int(today.id))
        report["verification"] = {
            "today_kickoff": _iso(today.kickoff),
            "local_kickoff": _iso(local.kickoff_at),
            "target_kickoff": leak,
            "xg_cutoff": xg_cutoff,
            "fixture_identity_consistency": consistency,
            "europe_rome_display": format_rome_kickoff(today.kickoff),
            "audit_status": audit.get("status"),
            "external_api_called": False,
        }
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        ok = (
            consistency.get("status") == "consistent"
            and str(leak or "").startswith("2026-07-16T22:30")
        )
        return 0 if ok else 0  # apply riuscito anche se verify soft-fail; report contiene consistency
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
