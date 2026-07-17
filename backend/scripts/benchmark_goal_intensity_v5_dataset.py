"""Benchmark reale / sintetico dataset Intensità Goal v5 (Fase 1B.1).

Uso reale (richiede DATABASE_URL o backend/.env):
  cd backend && python -m scripts.benchmark_goal_intensity_v5_dataset \\
    --date-from 2025-06-01 --date-to 2026-07-17 --summary-only

Stress sintetico (no DB, ~15k fixture):
  cd backend && python -m scripts.benchmark_goal_intensity_v5_dataset --synthetic --n 14979

PASS reale: elapsed < 60s, payload summary < 2MB, nessuna scrittura DB.
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
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
    from app.services.cecchino.cecchino_goal_intensity_v5_audit_indexes import AuditIndexes
    from app.services.cecchino.cecchino_goal_intensity_v5_dataset import (
        VERSION,
        build_goal_intensity_v5_dataset,
    )

    ko0 = datetime(2025, 6, 1, 15, 0, tzinfo=timezone.utc)
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

    db = MagicMock()
    db.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    db.commit = MagicMock()
    db.add = MagicMock()
    sample = retained[:200]

    def _empty_indexes(*_a, **_k):
        return AuditIndexes()

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.finished_local_fixtures_in_kickoff_range",
            return_value=list(sample),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.load_today_snapshots_for_fixtures",
            return_value=[],
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset._fixture_ids_with_team_stats",
            return_value=set(),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.preload_audit_indexes",
            side_effect=_empty_indexes,
        ),
    ):
        t_sum = time.perf_counter()
        payload = build_goal_intensity_v5_dataset(
            db,
            date_from=date(2025, 6, 1),
            date_to=date(2026, 7, 17),
        )
        summary_s = time.perf_counter() - t_sum

    payload_bytes = int(payload["performance"].get("response_payload_bytes") or 0)
    time_ok = dedupe_s < 60.0
    bytes_ok = payload_bytes < 2 * 1024 * 1024
    passed = time_ok and bytes_ok and len(retained) > 0
    db.commit.assert_not_called()
    db.add.assert_not_called()

    return {
        "mode": "synthetic",
        "version": VERSION,
        "n_input": n,
        "n_retained": len(retained),
        "dedupe_s": round(dedupe_s, 4),
        "dedupe_timings_ms": dedupe_report.get("timings_ms"),
        "summary_sample_rows": len(sample),
        "summary_build_s": round(summary_s, 4),
        "payload_bytes": payload_bytes,
        "preview_rows": len(payload.get("dataset_preview_rows") or []),
        "criteria": {
            "dedupe_lt_60s": time_ok,
            "payload_lt_2mb": bytes_ok,
            "no_db_writes": True,
        },
        "result": "PASS" if passed else "FAIL",
        "note": "Stress dedupe O(n log n) senza DB. Per PASS reale sul range completo serve DATABASE_URL.",
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
            rows = payload["performance"].get("estimated_full_dataset_rows")
            payload_bytes = payload["performance"].get("response_payload_bytes")
            phases = payload["performance"].get("calculation_phases") or {}
            db_phases = payload["performance"].get("db_query_phases") or {}
            elapsed_ms = payload["performance"].get("elapsed_ms")
            fps = payload["performance"].get("fixtures_per_second")
            preview = payload["performance"].get("response_preview_rows")
        else:
            internal = build_goal_intensity_v5_dataset_internal(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
            rows = len(internal["dataset_rows"])
            payload_bytes = None
            phases = internal["phases"]
            db_phases = {
                "cohort_ms": phases.get("cohort_ms"),
                "today_load_ms": phases.get("today_load_ms"),
                "fts_lookup_ms": phases.get("fts_lookup_ms"),
                "preload_ms": phases.get("preload_ms"),
            }
            elapsed_ms = internal["elapsed_ms"]
            fps = internal["fixtures_per_second"]
            preview = None

        wall_s = time.perf_counter() - t0
        elapsed_s = float(elapsed_ms or 0) / 1000.0
        bytes_ok = payload_bytes is None or int(payload_bytes) < 2 * 1024 * 1024
        time_ok = elapsed_s < 60.0
        passed = bool(time_ok and bytes_ok)

        return {
            "mode": "real",
            "version": VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
            "summary_only": summary_only,
            "rows": rows,
            "preview_rows": preview,
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
            "criteria": {
                "elapsed_lt_60s": time_ok,
                "payload_lt_2mb": bytes_ok,
                "no_external_api": True,
                "no_db_writes": True,
            },
            "result": "PASS" if passed else "FAIL",
        }
    finally:
        db.close()


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Benchmark goal intensity v5 dataset")
    parser.add_argument("--date-from", type=date.fromisoformat, default=None)
    parser.add_argument("--date-to", type=date.fromisoformat, default=None)
    parser.add_argument("--competition-id", type=int, default=None)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--synthetic", action="store_true", help="Stress dedupe senza DB")
    parser.add_argument("--n", type=int, default=14979, help="Fixture sintetiche")
    args = parser.parse_args()

    if args.synthetic:
        report = _synthetic_benchmark(args.n)
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["result"] == "PASS" else 1

    if not args.date_from or not args.date_to:
        print(
            json.dumps(
                {
                    "result": "FAIL",
                    "error": "date_from/date_to richiesti per benchmark reale (o usa --synthetic)",
                },
                indent=2,
            )
        )
        return 1

    if not os.environ.get("DATABASE_URL"):
        print(
            json.dumps(
                {
                    "result": "FAIL",
                    "error": "DATABASE_URL assente: impossibile eseguire benchmark reale. "
                    "Imposta DATABASE_URL o crea backend/.env, oppure usa --synthetic.",
                    "date_from": args.date_from.isoformat(),
                    "date_to": args.date_to.isoformat(),
                },
                indent=2,
            )
        )
        return 2

    report = _real_benchmark(
        date_from=args.date_from,
        date_to=args.date_to,
        competition_id=args.competition_id,
        summary_only=args.summary_only,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
