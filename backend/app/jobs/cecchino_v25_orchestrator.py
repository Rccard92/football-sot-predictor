"""Indice di Acquistabilita' V2.5 (orchestratore): esame e congelamento.

  python -m app.jobs.cecchino_v25_orchestrator --mode dev     # prova su 2022/23, 2023/24, 2024/25
  python -m app.jobs.cecchino_v25_orchestrator --mode final   # esame finale una sola volta su 2025/26
  python -m app.jobs.cecchino_v25_orchestrator --mode freeze  # parametri sulle stagioni tranne l'ultima (JSON)

Solo lettura del database. Stampa JSON su stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.core.database import SessionLocal
from app.services.cecchino_v25.orchestrator import ENGINE_FEATURES, FEATURES, MODULE_VERSION
from app.services.cecchino_v25.orchestrator_data import load_run_rows, v25_runs_by_season
from app.services.cecchino_v25.orchestrator_runner import run_mode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dev", "final", "freeze"), required=True)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        runs = v25_runs_by_season(db)
        data = {s: load_run_rows(db, run_id) for s, run_id in runs.items()}
    finally:
        db.close()
    report = run_mode(args.mode, data, features=FEATURES, engine_features=ENGINE_FEATURES, module_version=MODULE_VERSION, runs=runs)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
