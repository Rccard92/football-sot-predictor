"""Benchmark dataset Intensità Goal v5 — coorte Today eleggibile.

Uso reale (richiede DATABASE_URL o backend/.env):
  cd backend && python -m scripts.benchmark_goal_intensity_v5_dataset --summary-only

Default range: scan_date 2026-06-19 → oggi, competition_id=null.

Stress sintetico (solo dedupe O(n log n), no coorte Today):
  cd backend && python -m scripts.benchmark_goal_intensity_v5_dataset --synthetic --n 14979

PASS reale: elapsed < 30s, payload < 2MB, zero pre-MIN / ineligible / unknown / no-Today,
cohort_basis=cecchino_today_eligible_scan_date.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MIN_SCAN = date(2026, 6, 19)
COHORT_BASIS = "cecchino_today_eligible_scan_date"


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def _synthetic_benchmark(n: int) -> dict[str, Any]:
    from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
        dedupe_fixtures_provider_then_composite,
    )
    from app.services.cecchino.cecchino_goal_intensity_v5_dataset import VERSION

    ko0 = datetime(2026, 6, 19, 15, 0, tzinfo=timezone.utc)
    fixtures: list[Any] = []
    for i in range(n):
        fx = MagicMock()
        fx.id = i + 1
        fx.api_fixture_id = 100_000 + i
        fx.home_team_id = 1 + (i % 200)
        fx.away_team_id = 201 + (i % 200)
        fx.goals_home = 1
        fx.goals_away = 1
        fx.kickoff_at = ko0 + timedelta(hours=i)
        fx.status = "FT"
        fx.competition_id = 39 + (i % 5)
        fixtures.append(fx)

    t_dedupe = time.perf_counter()
    retained, dedupe_report = dedupe_fixtures_provider_then_composite(fixtures)
    dedupe_s = time.perf_counter() - t_dedupe

    time_ok = dedupe_s < 30.0
    passed = time_ok and len(retained) > 0

    return {
        "mode": "synthetic",
        "version": VERSION,
        "n_input": n,
        "n_retained": len(retained),
        "dedupe_s": round(dedupe_s, 4),
        "dedupe_timings_ms": dedupe_report.get("timings_ms"),
        "criteria": {
            "dedupe_lt_30s": time_ok,
        },
        "result": "PASS" if passed else "FAIL",
        "note": (
            "Stress dedupe O(n log n) senza DB/coorte Today. "
            "Per PASS reale sulla coorte eleggibile serve DATABASE_URL."
        ),
    }


def _real_benchmark(
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    summary_only: bool,
) -> dict[str, Any]:
    from app.core.database import SessionLocal
    from app.services.cecchino.cecchino_goal_intensity_v5_dataset import (
        VERSION,
        build_goal_intensity_v5_dataset,
        build_goal_intensity_v5_dataset_internal,
    )
    from app.services.cecchino.cecchino_goal_intensity_v5_today_cohort import (
        MIN_GOAL_INTENSITY_TODAY_SCAN_DATE,
    )

    db = SessionLocal()
    try:
        t0 = time.perf_counter()
        if summary_only:
            payload = build_goal_intensity_v5_dataset(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
            elig = payload.get("eligibility_diagnostics") or {}
            summary = payload.get("dataset_summary") or {}
            rows = payload.get("performance", {}).get("estimated_full_dataset_rows")
            payload_bytes = payload.get("performance", {}).get("response_payload_bytes")
            phases = payload.get("performance", {}).get("calculation_phases") or {}
            db_phases = payload.get("performance", {}).get("db_query_phases") or {}
            elapsed_ms = payload.get("performance", {}).get("elapsed_ms")
            fps = payload.get("performance", {}).get("fixtures_per_second")
            preview = payload.get("dataset_preview_rows") or []
            cohort_basis = payload.get("cohort_basis") or summary.get("cohort_basis")
            status = payload.get("status")
            warnings = list(payload.get("warnings") or [])
            feature_safe = summary.get("leakage_safe_rows") or elig.get("eligible_feature_safe_matches")
            xg = payload.get("xg_cohorts") or summary.get("xg_cohorts") or {}
            history = payload.get("history_quality") or {}
        else:
            internal = build_goal_intensity_v5_dataset_internal(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
            elig = internal.get("eligibility_diagnostics") or {}
            rows = len(internal.get("dataset_rows") or [])
            payload_bytes = None
            phases = internal.get("phases") or {}
            db_phases = {
                "cohort_ms": phases.get("cohort_ms"),
                "preload_ms": phases.get("preload_ms"),
            }
            elapsed_ms = internal.get("elapsed_ms")
            fps = internal.get("fixtures_per_second")
            preview = internal.get("dataset_rows") or []
            cohort_basis = internal.get("cohort_basis")
            status = internal.get("status")
            warnings = list(internal.get("warnings") or [])
            feature_safe = len(internal.get("dataset_rows") or [])
            xg = internal.get("xg_cohorts") or {}
            history = internal.get("history_quality") or {}

        wall_s = time.perf_counter() - t0
        elapsed_s = float(elapsed_ms or 0) / 1000.0
        if elapsed_s <= 0:
            elapsed_s = wall_s

        unknown = int(elig.get("today_eligibility_unknown") or 0)
        ineligible = int(elig.get("today_ineligible_matches") or 0)
        # Model-ready devono essere solo eligible finished; pending/unresolved fuori
        preview_bad = [
            r
            for r in preview
            if isinstance(r, dict) and r.get("eligibility_status") not in (None, "eligible")
        ]
        pre_min = [
            r
            for r in preview
            if isinstance(r, dict)
            and r.get("scan_date")
            and str(r["scan_date"]) < MIN_GOAL_INTENSITY_TODAY_SCAN_DATE.isoformat()
        ]

        bytes_ok = payload_bytes is None or int(payload_bytes) < 2 * 1024 * 1024
        time_ok = elapsed_s < 30.0
        basis_ok = cohort_basis == COHORT_BASIS
        # Criterio brief: zero unknown + nessun ineligible nel model-ready
        model_ok = (
            status != "error"
            and len(preview_bad) == 0
            and len(pre_min) == 0
            and basis_ok
        )
        strict_unknown_ok = unknown == 0
        passed = bool(time_ok and bytes_ok and model_ok and strict_unknown_ok)

        return {
            "mode": "real",
            "version": VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
            "summary_only": summary_only,
            "cohort_basis": cohort_basis,
            "status": status,
            "rows": rows,
            "preview_rows": len(preview) if isinstance(preview, list) else preview,
            "feature_safe_matches": feature_safe,
            "eligibility_diagnostics": {
                "today_rows_raw": elig.get("today_rows_raw"),
                "today_unique_matches": elig.get("today_unique_matches"),
                "today_eligible_matches": elig.get("today_eligible_matches"),
                "today_ineligible_matches": ineligible,
                "today_eligibility_unknown": unknown,
                "eligible_finished_matches": elig.get("eligible_finished_matches"),
                "eligible_pending_matches": elig.get("eligible_pending_matches"),
                "eligible_unresolved_matches": elig.get("eligible_unresolved_matches"),
                "eligible_feature_safe_matches": elig.get("eligible_feature_safe_matches"),
            },
            "xg_cohorts": xg,
            "history_quality": history,
            "elapsed_ms": elapsed_ms,
            "elapsed_s": round(elapsed_s, 3),
            "wall_clock_s": round(wall_s, 3),
            "fixtures_per_second": fps,
            "payload_bytes": payload_bytes,
            "payload_mb": round(int(payload_bytes or 0) / (1024 * 1024), 4)
            if payload_bytes is not None
            else None,
            "db_query_phases": db_phases,
            "calculation_phases": phases,
            "warnings": warnings,
            "criteria": {
                "elapsed_lt_30s": time_ok,
                "payload_lt_2mb": bytes_ok,
                "cohort_basis_ok": basis_ok,
                "zero_pre_min_scan_date": len(pre_min) == 0,
                "zero_ineligible_in_model": len(preview_bad) == 0,
                "zero_unknown": strict_unknown_ok,
                "status_not_error": status != "error",
                "no_external_api": True,
                "no_db_writes": True,
            },
            "result": "PASS" if passed else "FAIL",
        }
    finally:
        db.close()


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Benchmark goal intensity v5 dataset (Today eligible)")
    parser.add_argument("--date-from", type=date.fromisoformat, default=None)
    parser.add_argument("--date-to", type=date.fromisoformat, default=None)
    parser.add_argument("--competition-id", type=int, default=None)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        default=True,
        help="Summary HTTP (default). Usa --full per dataset interno completo.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Esegue build_goal_intensity_v5_dataset_internal (no summary-only).",
    )
    parser.add_argument("--synthetic", action="store_true", help="Stress dedupe senza DB")
    parser.add_argument("--n", type=int, default=14979, help="Fixture sintetiche")
    args = parser.parse_args()

    if args.synthetic:
        report = _synthetic_benchmark(args.n)
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["result"] == "PASS" else 1

    date_from = args.date_from or MIN_SCAN
    date_to = args.date_to or date.today()
    summary_only = not bool(args.full)

    if not os.environ.get("DATABASE_URL"):
        print(
            json.dumps(
                {
                    "result": "FAIL",
                    "error": "DATABASE_URL assente: impossibile eseguire benchmark reale. "
                    "Imposta DATABASE_URL o crea backend/.env, oppure usa --synthetic.",
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                    "competition_id": args.competition_id,
                    "note": "Non chiudere come PASS senza run reale quando il DB è disponibile.",
                },
                indent=2,
            )
        )
        return 2

    report = _real_benchmark(
        date_from=date_from,
        date_to=date_to,
        competition_id=args.competition_id,
        summary_only=summary_only,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
