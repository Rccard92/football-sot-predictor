"""Smoke READ-ONLY market_informative — Run #17.

Conferma:
  default → 14138 informative
  historical total → 86659
  export FULL row count → 86659
  toggle off (market_informative=false) → 86659
"""
from __future__ import annotations

import os
import sys
import tempfile
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

from app.services.cecchino_data_lab.pattern_lab_constants import EXPORT_MODE_FULL
from app.services.cecchino_data_lab.pattern_lab_discovery_export import (
    write_discovery_dataset_files,
)
from app.services.cecchino_data_lab.pattern_lab_service import (
    count_eligible_market_rows,
    query_pattern_lab,
)

RUN_ID = 17
EXPECTED_TOTAL = 86659
EXPECTED_INFORMATIVE = 14138


def _fail(msg: str) -> None:
    print(f"SMOKE_FAIL: {msg}")
    raise SystemExit(1)


def main() -> int:
    eng = create_engine(db_url)
    Session = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    db = Session()
    try:
        hist = count_eligible_market_rows(db, [RUN_ID], eligibility="eligible_core")
        print("historical_total_count", hist)
        if hist != EXPECTED_TOTAL:
            _fail(f"historical_total={hist} expected={EXPECTED_TOTAL}")

        q_default = query_pattern_lab(
            db,
            run_ids=[RUN_ID],
            filters={"eligibility": "eligible_core", "market_informative": True},
            include_rows=False,
        )
        sel = int(q_default["summary"]["selections"])
        hist_sum = int(q_default["summary"].get("selections_historical_total") or 0)
        print("default_informative_selections", sel)
        print("summary_historical_total", hist_sum)
        if sel != EXPECTED_INFORMATIVE:
            _fail(f"informative={sel} expected={EXPECTED_INFORMATIVE}")
        if hist_sum != EXPECTED_TOTAL:
            _fail(f"summary historical={hist_sum} expected={EXPECTED_TOTAL}")

        q_all = query_pattern_lab(
            db,
            run_ids=[RUN_ID],
            filters={"eligibility": "eligible_core", "market_informative": False},
            include_rows=False,
        )
        sel_all = int(q_all["summary"]["selections"])
        print("toggle_show_all_selections", sel_all)
        if sel_all != EXPECTED_TOTAL:
            _fail(f"toggle_all={sel_all} expected={EXPECTED_TOTAL}")

        with tempfile.TemporaryDirectory(prefix="pl17_export_") as tmp:
            dest = Path(tmp)
            meta = write_discovery_dataset_files(
                db,
                run_ids=[RUN_ID],
                mode=EXPORT_MODE_FULL,
                filters={"eligibility": "eligible_core"},
                dest_dir=dest,
                include_observational_only=True,
            )
            export_n = int(meta.get("row_count") or meta.get("rows") or 0)
            if not export_n:
                # metadata keys may vary
                export_n = int(
                    (meta.get("dataset") or {}).get("row_count")
                    or meta.get("selection_count")
                    or 0
                )
            print("export_full_meta_keys", sorted(meta.keys()))
            print("export_full_row_count", export_n)
            if export_n != EXPECTED_TOTAL:
                _fail(f"export_full={export_n} expected={EXPECTED_TOTAL}")

        print("SMOKE_OK run17 market_informative")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
