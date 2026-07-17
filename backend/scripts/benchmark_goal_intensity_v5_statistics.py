"""Benchmark reale Fase 1C per statistiche Intensità Goal v5.

Uso:
  cd backend && python -m scripts.benchmark_goal_intensity_v5_statistics

Richiede DATABASE_URL (diretta o in backend/.env). Il risultato è PASS solo con
tempo <30 secondi e payload JSON <2 MB; non viene mai scritta alcuna riga DB.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_DATE_FROM = date(2026, 6, 19)
DEFAULT_DATE_TO = date(2026, 7, 19)


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        key, _, raw = value.partition("=")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = raw.strip().strip("'").strip('"')


def run_benchmark(
    *, date_from: date, date_to: date, competition_id: int | None, bootstrap_iterations: int
) -> dict[str, Any]:
    from app.core.database import SessionLocal
    from app.services.cecchino.cecchino_goal_intensity_v5_statistics import (
        VERSION,
        build_goal_intensity_v5_statistics,
    )

    db = SessionLocal()
    try:
        started = time.perf_counter()
        payload = build_goal_intensity_v5_statistics(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            minimum_history_sample=10,
            bootstrap_iterations=bootstrap_iterations,
            random_seed=42,
        )
        elapsed_s = time.perf_counter() - started
        encoded = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
        payload_bytes = len(encoded)
        cohort = payload.get("cohort_summary") or {}
        xg = payload.get("xg_value_summary") or {}
        readiness = payload.get("phase_1d_readiness") or {}
        criteria = {
            "status_ok": payload.get("status") == "ok",
            "elapsed_lt_30s": elapsed_s < 30.0,
            "payload_lt_2mb": payload_bytes < 2 * 1024 * 1024,
        }
        return {
            "version": VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
            "minimum_history_sample": 10,
            "bootstrap_iterations": bootstrap_iterations,
            "cohort_counters": cohort,
            "xg_assessment": xg.get("xg_value_assessment"),
            "xg_status": xg.get("status"),
            "readiness": readiness,
            "elapsed_s": round(elapsed_s, 3),
            "payload_bytes": payload_bytes,
            "criteria": criteria,
            "result": "PASS" if all(criteria.values()) else "FAIL",
        }
    finally:
        db.close()


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Benchmark statistiche Intensità Goal v5")
    parser.add_argument("--date-from", type=date.fromisoformat, default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", type=date.fromisoformat, default=DEFAULT_DATE_TO)
    parser.add_argument("--competition-id", type=int, default=None)
    parser.add_argument("--bootstrap-iterations", type=int, default=1000)
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print(json.dumps({
            "result": "FAIL",
            "error": "DATABASE_URL assente: benchmark reale non eseguibile.",
            "date_from": args.date_from.isoformat(),
            "date_to": args.date_to.isoformat(),
        }, indent=2))
        return 2

    report = run_benchmark(
        date_from=args.date_from,
        date_to=args.date_to,
        competition_id=args.competition_id,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
