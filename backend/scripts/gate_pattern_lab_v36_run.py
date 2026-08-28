"""Gate Pattern Lab V3.6 su una run storica (pilot o full).

Verifica:
  eligible_core > 0
  pre_match_verified=true (su eligible)
  almeno alcuni pre_purch_v36_score != null
  Pattern Lab filtro V3.6 → selections > 0
  Bet Builder Replay con V3.6 → selections > 0

Uso:
  python -m scripts.gate_pattern_lab_v36_run --run-id N
"""
from __future__ import annotations

import argparse
import os
import sys
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
    print("ERROR: DATABASE_URL missing")
    raise SystemExit(2)
if "railway.internal" in db_url:
    print("ERROR: railway.internal not reachable")
    raise SystemExit(2)
os.environ["DATABASE_URL"] = db_url
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.services.cecchino_data_lab.pattern_lab_canonical import (
    evaluate_canonical_flags,
    runs_with_purchasability_v36,
    runs_with_purchasability_v36_scores,
)
from app.services.cecchino_data_lab.pattern_lab_service import (
    bet_builder_replay,
    query_pattern_lab,
)


def _fail(msg: str) -> None:
    print(f"GATE_FAIL: {msg}")
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--v36-min", type=float, default=1.0)
    args = parser.parse_args()
    run_id = int(args.run_id)

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        run = db.get(CecchinoLabHistoricalScanRun, run_id)
        if not run:
            _fail(f"run {run_id} not found")
        print(
            "run",
            {
                "id": run.id,
                "season_label": run.season_label,
                "status": run.status,
                "scan_version": run.scan_version,
                "matches_eligible_core": run.matches_eligible_core,
            },
        )

        stats = db.execute(
            text(
                """
                SELECT
                  COUNT(*) FILTER (
                    WHERE historical_eligibility_status = 'eligible_core'
                  ) AS eligible_core,
                  COUNT(*) FILTER (
                    WHERE historical_eligibility_status = 'eligible_core'
                      AND (purchasability_compatibility_json->'engine_batch'
                           ->>'pre_match_verified') = 'true'
                  ) AS verified_true,
                  COUNT(*) FILTER (
                    WHERE historical_eligibility_status = 'eligible_core'
                      AND (purchasability_compatibility_json->'engine_batch'
                           ->>'pre_match_verified') = 'false'
                  ) AS verified_false,
                  (
                    SELECT COUNT(*)
                    FROM cecchino_lab_historical_match_snapshots s2,
                         jsonb_array_elements(
                           COALESCE(
                             s2.purchasability_compatibility_json->'markets',
                             '[]'::jsonb
                           )
                         ) m
                    WHERE s2.run_id = :run_id
                      AND s2.historical_eligibility_status = 'eligible_core'
                      AND m->>'score' IS NOT NULL
                      AND m->>'score' <> 'null'
                  ) AS scored_markets
                FROM cecchino_lab_historical_match_snapshots
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id},
        ).mappings().one()
        print("v36_stats", dict(stats))

        eligible = int(stats["eligible_core"] or 0)
        verified = int(stats["verified_true"] or 0)
        scored = int(stats["scored_markets"] or 0)
        if eligible <= 0:
            _fail("eligible_core == 0")
        if verified <= 0:
            _fail("pre_match_verified=true assente su eligible_core")
        if verified < eligible:
            print(
                "WARN: verified_true < eligible_core",
                verified,
                eligible,
            )
        if scored <= 0:
            _fail("nessun pre_purch_v36_score valorizzato")

        q = query_pattern_lab(
            db,
            run_ids=[run_id],
            filters={
                "eligibility": "eligible_core",
                "purchasability_v36_min": float(args.v36_min),
            },
            include_rows=False,
        )
        sel = int(q["summary"]["selections"] or 0)
        print(
            "pl_v36",
            sel,
            "avg_v36",
            q["summary"].get("avg_purchasability_v36"),
            "avg_r",
            q["summary"].get("avg_rating"),
        )
        if sel <= 0:
            _fail("Pattern Lab filtro V3.6: selections=0")

        bb = bet_builder_replay(
            db,
            run_ids=[run_id],
            filters={
                "eligibility": "eligible_core",
                "purchasability_v36_min": float(args.v36_min),
            },
        )
        bb_sel = int(bb["summary"]["selections"] or 0)
        print("bb_v36", bb_sel, "days", len(bb["timeline_by_day"]))
        if bb_sel <= 0:
            _fail("Bet Builder Replay con V3.6: selections=0")

        v36 = runs_with_purchasability_v36(db, [run_id])
        v36s = runs_with_purchasability_v36_scores(db, [run_id])
        flags = evaluate_canonical_flags(
            run, has_v36=run_id in v36, has_v36_scores=run_id in v36s
        )
        print(
            "canonical_flags",
            flags["is_canonical"],
            flags.get("incomplete_v36"),
            "scope",
            flags["run_scope"],
            "checks",
            flags["canonical_checks"],
        )

        print("GATE PASSED")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
