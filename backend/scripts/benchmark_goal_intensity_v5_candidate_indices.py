"""Benchmark reale Fase 1D per indici candidati Intensità Goal v5.

Uso:
  cd backend && python -m scripts.benchmark_goal_intensity_v5_candidate_indices

Richiede DATABASE_URL (diretta o in backend/.env). Il risultato è PASS solo con
tempo <30 secondi preferibile (<45s max) e payload JSON <2 MB; nessuna scrittura DB.
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
    from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
        VERSION,
        build_goal_intensity_v5_candidate_indices,
    )

    db = SessionLocal()
    try:
        started = time.perf_counter()
        payload = build_goal_intensity_v5_candidate_indices(
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
        readiness = payload.get("phase_2a_readiness") or {}
        criteria = {
            "status_ok": payload.get("status") == "ok",
            "elapsed_lt_30s": elapsed_s < 30.0,
            "elapsed_lt_45s": elapsed_s < 45.0,
            "payload_lt_2mb": payload_bytes < 2 * 1024 * 1024,
            "version_v1_1": VERSION.endswith("v1_1"),
            "no_score_over_100_prob": True,
        }
        # spot-check calibration flag if composites present
        gi_a = ((payload.get("composite_metrics") or {}).get("GI_A_STRICT_CORE") or {}).get("goals_ge_2") or {}
        if gi_a:
            criteria["no_score_over_100_prob"] = gi_a.get("uses_score_over_100_as_probability") is False
            criteria["logistic_calibrated"] = gi_a.get("calibration_method") == "train_logistic_regression"
        return {
            "version": VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
            "minimum_history_sample": 10,
            "bootstrap_iterations": bootstrap_iterations,
            "cohort_counters": cohort,
            "primary_candidate": payload.get("primary_candidate"),
            "challenger_candidate": payload.get("challenger_candidate"),
            "phase_2a_next_step": readiness.get("recommended_next_step"),
            "ready_for_phase_2a": readiness.get("ready_for_phase_2a"),
            "tempo_baseline": payload.get("tempo_baseline_comparison"),
            "elapsed_s": round(elapsed_s, 3),
            "payload_bytes": payload_bytes,
            "criteria": criteria,
            "pass": all(
                [
                    criteria["status_ok"],
                    criteria["elapsed_lt_45s"],
                    criteria["payload_lt_2mb"],
                    criteria.get("no_score_over_100_prob", True),
                ]
            ),
            "preferable_pass": all(v for k, v in criteria.items() if k != "elapsed_lt_30s") and criteria["elapsed_lt_30s"],
            "warnings": payload.get("warnings") or [],
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Fase 1D candidate indices")
    parser.add_argument("--date-from", default=DEFAULT_DATE_FROM.isoformat())
    parser.add_argument("--date-to", default=DEFAULT_DATE_TO.isoformat())
    parser.add_argument("--competition-id", type=int, default=None)
    parser.add_argument("--bootstrap-iterations", type=int, default=1000)
    args = parser.parse_args()

    _load_dotenv()
    if not os.environ.get("DATABASE_URL"):
        print("FAIL: DATABASE_URL assente — benchmark reale non eseguibile")
        return 1

    result = run_benchmark(
        date_from=date.fromisoformat(args.date_from),
        date_to=date.fromisoformat(args.date_to),
        competition_id=args.competition_id,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["pass"]:
        label = "PASS (preferable)" if result["preferable_pass"] else "PASS (max 45s)"
        print(label)
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
