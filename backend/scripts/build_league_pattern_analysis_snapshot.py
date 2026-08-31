"""Build snapshot League Pattern Analysis — run bloccate 17/19/20/21.

Uso:
  cd backend
  python -m scripts.build_league_pattern_analysis_snapshot

Richiede DATABASE_PUBLIC_URL o DATABASE_URL. Non lancia Historical Scan.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(root / ".env")
    load_dotenv(root / ".env.local", override=True)
except Exception:
    pass

db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not db_url:
    print("SKIP: DATABASE_URL missing")
    raise SystemExit(2)
if "railway.internal" in db_url:
    print("SKIP: railway.internal not reachable")
    raise SystemExit(2)
os.environ["DATABASE_URL"] = db_url
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.cecchino_data_lab.league_pattern_analysis import (
    build_league_pattern_analysis_snapshot,
)
from app.services.cecchino_data_lab.league_pattern_analysis_registry import (
    LOCKED_SOURCE_RUN_IDS,
)


def main() -> int:
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        t0 = time.perf_counter()
        print(f"Building League Pattern Analysis snapshot from runs {LOCKED_SOURCE_RUN_IDS}…")
        snap = build_league_pattern_analysis_snapshot(
            db, source_run_ids=list(LOCKED_SOURCE_RUN_IDS)
        )
        elapsed = time.perf_counter() - t0
        summary = snap.summary_json or {}
        print(f"snapshot_id={snap.id}")
        print(f"analysis_version={snap.analysis_version} status={snap.status}")
        print(f"source_run_ids={snap.source_run_ids}")
        print(f"source_seasons={snap.source_seasons}")
        print(f"eligible_matches={summary.get('eligible_matches_analyzed')}")
        print(f"market_rows={summary.get('informative_market_rows_analyzed')}")
        print(f"global_patterns={summary.get('global_patterns_count')}")
        print(f"league_native={summary.get('league_native_count')}")
        print(f"elapsed_s={elapsed:.2f}")
        print("BUILD_OK")
        return 0
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
