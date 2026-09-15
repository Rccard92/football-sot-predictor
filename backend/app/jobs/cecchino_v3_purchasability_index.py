"""Indice di Acquistabilita' V3 (orchestratore): esame e congelamento, stesse regole della V2.5.

  python -m app.jobs.cecchino_v3_purchasability_index --mode dev
  python -m app.jobs.cecchino_v3_purchasability_index --mode final
  python -m app.jobs.cecchino_v3_purchasability_index --mode freeze

Solo lettura del database. Stampa JSON su stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.core.database import SessionLocal
from app.services.cecchino_v25.orchestrator_runner import run_mode
from app.services.cecchino_v3.purchasability_index import ENGINE_FEATURES, FEATURES, MODULE_VERSION, VARIANTS, load_lab_data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dev", "final", "freeze"), required=True)
    parser.add_argument("--variant", choices=tuple(VARIANTS), default="modules")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        data, runs = load_lab_data(db)
    finally:
        db.close()
    features = VARIANTS[args.variant]
    report = run_mode(args.mode, data, features=features, engine_features=ENGINE_FEATURES, module_version=MODULE_VERSION, runs=runs, data_features=FEATURES)
    report["variant"] = args.variant
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
