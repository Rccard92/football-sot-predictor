"""Test storico indice di acquistabilita' + pattern, V2.5 e V3, stagioni 2022/23-2024/25.

  python -m app.jobs.cecchino_index_pattern_accord --model V2.5
  python -m app.jobs.cecchino_index_pattern_accord --model V3

Solo lettura del database. Stampa JSON su stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

from threadpoolctl import threadpool_limits

from app.core.database import SessionLocal
from app.services.cecchino_v25 import index_pattern_accord as acc

V25_MASTER_BUILD = 6
V25_INSIGHT_RUN = 6
V25_DISCOVERY_RUN = 16
V3_MASTER_BUILD = 2
V3_PATTERN_RUN = 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("V2.5", "V3"), required=True)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        with threadpool_limits(limits=1, user_api="blas"):
            if args.model == "V2.5":
                from app.services.cecchino_v25.orchestrator import FEATURES
                from app.services.cecchino_v25.orchestrator_data import load_run_rows, v25_runs_by_season

                runs = v25_runs_by_season(db)
                data = {s: load_run_rows(db, r) for s, r in runs.items() if s <= acc.TEST_SEASONS[-1]}
                scores = acc.walk_forward_scores(data, features=FEATURES, data_features=FEATURES)
                sets = acc.v25_pattern_sets(db, master_build_id=V25_MASTER_BUILD, insight_run_id=V25_INSIGHT_RUN)
                fired = acc.v25_fired(db, run_ids=runs, discovery_run_id=V25_DISCOVERY_RUN, sets=sets)
            else:
                from app.services.cecchino_v3.purchasability_index import ENGINE_FEATURES, FEATURES, REFERENCE_RUN_ID, load_lab_data

                data, info = load_lab_data(db)
                data = {s: d for s, d in data.items() if s <= acc.TEST_SEASONS[-1]}
                scores = acc.walk_forward_scores(data, features=ENGINE_FEATURES, data_features=FEATURES)
                sets = acc.v3_pattern_sets(db, master_build_id=V3_MASTER_BUILD, pattern_run_id=V3_PATTERN_RUN)
                fired = acc.v3_fired(
                    db, run_id=REFERENCE_RUN_ID, index_run_id=int(info["index_run"]), master_build_id=V3_MASTER_BUILD, sets=sets
                )
            result = acc.report(scores, fired)
            result["model"] = args.model
            result["pattern_sets"] = {name: sum(len(v) for v in s.values()) for name, s in sets.items()}
    finally:
        db.close()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
