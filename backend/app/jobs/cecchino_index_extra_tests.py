"""Test 1-2-3 sull'Indice di Acquistabilita' (quote del mattino, V2.5+V3 d'accordo, una giocata per partita).

  python -m app.jobs.cecchino_index_extra_tests

Solo lettura del database. Stampa JSON su stdout.
"""

from __future__ import annotations

import json
import sys

from threadpoolctl import threadpool_limits

from app.core.database import SessionLocal
from app.services.cecchino_v25 import index_extra_tests as ext
from app.services.cecchino_v25.index_pattern_accord import TEST_SEASONS, walk_forward_scores


def main() -> int:
    from app.services.cecchino_v25.orchestrator import FEATURES as V25_FEATURES
    from app.services.cecchino_v25.orchestrator_data import load_run_rows, v25_runs_by_season
    from app.services.cecchino_v3.purchasability_index import ENGINE_FEATURES, FEATURES as V3_FEATURES, load_lab_data

    db = SessionLocal()
    try:
        with threadpool_limits(limits=1, user_api="blas"):
            runs = v25_runs_by_season(db)
            v25_data = {s: load_run_rows(db, r) for s, r in runs.items() if s <= TEST_SEASONS[-1]}
            v25 = walk_forward_scores(v25_data, features=V25_FEATURES, data_features=V25_FEATURES)
            del v25_data
            v3_data, _ = load_lab_data(db)
            v3_data = {s: d for s, d in v3_data.items() if s <= TEST_SEASONS[-1]}
            v3 = walk_forward_scores(v3_data, features=ENGINE_FEATURES, data_features=V3_FEATURES)
            del v3_data
            ids = {int(i) for rows in list(v25.values()) + list(v3.values()) for i in rows.match_id}
            opening = ext.lab_quotes(db, ids, ext.OPENING_COLUMNS)
            closing = ext.lab_quotes(db, ids, ext.CLOSING_COLUMNS)
            result = {
                "test_1_quote_apertura": {"V2.5": ext.test_opening(v25, opening, closing), "V3": ext.test_opening(v3, opening, closing)},
                "test_2_v25_v3_d_accordo": ext.test_agreement(v25, v3),
                "test_3_una_giocata_per_partita": {"V2.5": ext.test_one_per_match(v25), "V3": ext.test_one_per_match(v3)},
            }
    finally:
        db.close()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
