"""Smoke READ-ONLY Pattern Lab — Run #15 legacy + assert anti falso-positivo.

Non modifica Historical Scan / Run #15.
Fail se selections=0 senza reason esplicitamente attesa.
"""
from __future__ import annotations

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
    print("SKIP: DATABASE_URL missing")
    raise SystemExit(2)
if "railway.internal" in db_url:
    print("SKIP: railway.internal not reachable")
    raise SystemExit(2)
os.environ["DATABASE_URL"] = db_url
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.services.cecchino_data_lab.pattern_lab_canonical import (
    evaluate_canonical_flags,
    list_pattern_lab_runs,
    runs_with_purchasability_v36,
    runs_with_purchasability_v36_scores,
)
from app.services.cecchino_data_lab.pattern_lab_service import (
    bet_builder_replay,
    pattern_lab_filter_options,
    query_pattern_lab,
)


def _fail(msg: str) -> None:
    print(f"SMOKE_FAIL: {msg}")
    raise SystemExit(1)


def _v36_score_stats(db, run_id: int) -> dict:
    row = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (
                WHERE s.historical_eligibility_status = 'eligible_core'
              ) AS eligible_core,
              COUNT(*) FILTER (
                WHERE s.historical_eligibility_status = 'eligible_core'
                  AND (s.purchasability_compatibility_json->'engine_batch'
                       ->>'pre_match_verified') = 'true'
              ) AS verified_true,
              (
                SELECT COUNT(*)
                FROM cecchino_lab_historical_match_snapshots s2,
                     jsonb_array_elements(
                       COALESCE(s2.purchasability_compatibility_json->'markets', '[]'::jsonb)
                     ) m
                WHERE s2.run_id = :run_id
                  AND s2.historical_eligibility_status = 'eligible_core'
                  AND m->>'score' IS NOT NULL
                  AND m->>'score' <> 'null'
              ) AS scored_markets
            FROM cecchino_lab_historical_match_snapshots s
            WHERE s.run_id = :run_id
            """
        ),
        {"run_id": run_id},
    ).mappings().one()
    return dict(row)


def main() -> None:
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        items = list_pattern_lab_runs(db, include_legacy=False)
        ids = [i["run_id"] for i in items]
        print("canonical_ids", ids)
        print("15_in_canonical", 15 in ids)

        legacy = list_pattern_lab_runs(db, include_legacy=True)
        print("15_in_legacy", any(i["run_id"] == 15 for i in legacy))
        print("3_in_legacy", any(i["run_id"] == 3 for i in legacy))

        v36 = runs_with_purchasability_v36(db, [3, 15])
        v36_scores = runs_with_purchasability_v36_scores(db, [3, 15])
        print("v36_module", sorted(v36))
        print("v36_scores", sorted(v36_scores))

        r15 = db.get(CecchinoLabHistoricalScanRun, 15)
        if not r15:
            _fail("Run #15 non trovata")
        flags15 = evaluate_canonical_flags(
            r15,
            has_v36=15 in v36,
            has_v36_scores=15 in v36_scores,
        )
        print(
            "r15_canonical",
            flags15["is_canonical"],
            "incomplete_v36",
            flags15.get("incomplete_v36"),
            "checks",
            flags15["canonical_checks"],
        )
        if flags15["is_canonical"]:
            _fail("Run #15 non deve essere canonica (V3.6 incomplete atteso)")
        if not flags15.get("incomplete_v36"):
            # Se un giorno #15 avesse score, lo smoke andrebbe aggiornato; oggi deve essere incomplete
            stats = _v36_score_stats(db, 15)
            if int(stats.get("scored_markets") or 0) == 0 and 15 in v36:
                print("r15_incomplete_v36_ok")
            else:
                _fail("Run #15 attesa incomplete-V3.6 (module sì, score no)")

        mr_core = db.execute(
            text(
                """
                SELECT COUNT(*) FROM cecchino_lab_historical_market_results m
                JOIN cecchino_lab_historical_match_snapshots s
                  ON s.id = m.match_snapshot_id
                WHERE m.run_id = 15
                  AND s.historical_eligibility_status = 'eligible_core'
                """
            )
        ).scalar()
        print("mr_core", mr_core)

        opts = pattern_lab_filter_options(db, [15])
        print(
            "filter_options",
            len(opts["competitions"]),
            "comps",
            len(opts["markets"]),
            "markets",
        )

        # Baseline senza filtri stretti
        q = query_pattern_lab(
            db,
            run_ids=[15],
            filters={"eligibility": "eligible_core"},
            include_rows=True,
            page=1,
            page_size=3,
        )
        sel = int(q["summary"]["selections"] or 0)
        print(
            "query",
            sel,
            "roi",
            q["summary"]["roi"],
            "avg_r",
            q["summary"].get("avg_rating"),
            "avg_v36",
            q["summary"].get("avg_purchasability_v36"),
            "by_season",
            len(q["breakdown"]["by_season"]),
            "by_comp",
            len(q["breakdown"]["by_competition"]),
            "by_market",
            len(q["breakdown"]["by_market"]),
        )
        if sel <= 0:
            _fail("Run #15 baseline eligible_core: selections=0 (inesperto)")
        if mr_core is not None and sel != int(mr_core):
            _fail(f"selections {sel} != mr_core {mr_core}")
        if q["summary"].get("avg_rating") is None:
            _fail("avg_rating atteso valorizzato")
        seasons = {b.get("key") for b in q["breakdown"]["by_season"]}
        if "2021/2022" not in seasons:
            _fail("breakdown.by_season deve contenere 2021/2022")
        if len(q["breakdown"]["by_competition"]) <= 0:
            _fail("breakdown.by_competition vuoto")
        if len(q["breakdown"]["by_market"]) <= 0:
            _fail("breakdown.by_market vuoto")

        q_home = query_pattern_lab(
            db,
            run_ids=[15],
            filters={"eligibility": "eligible_core", "market_keys": ["HOME"]},
            include_rows=False,
        )
        home_sel = int(q_home["summary"]["selections"] or 0)
        print("HOME", home_sel)
        if home_sel <= 0:
            _fail("Filtro HOME: selections=0")

        stats = _v36_score_stats(db, 15)
        print("v36_stats", stats)
        scored = int(stats.get("scored_markets") or 0)
        if scored == 0:
            if q["summary"].get("avg_purchasability_v36") is not None:
                _fail("avg_v36 dovrebbe essere None con 0 score persistiti")
            print(
                "v36_reason",
                "Run #15 incomplete: pre_match_verified storico false / score null "
                "(adapter pre-epoch; non re-scan)",
            )
            q_v36 = query_pattern_lab(
                db,
                run_ids=[15],
                filters={
                    "eligibility": "eligible_core",
                    "purchasability_v36_min": 1,
                },
                include_rows=False,
            )
            if int(q_v36["summary"]["selections"] or 0) != 0:
                _fail("Con 0 score, filtro V3.6 min dovrebbe dare 0")
            print("v36_filter_zero_expected_ok")
        else:
            if q["summary"].get("avg_purchasability_v36") is None:
                _fail("avg_v36 None nonostante score persistiti")

        # BB senza filtro V3.6: su #15 atteso >0 (price/signals)
        bb = bet_builder_replay(
            db, run_ids=[15], filters={"eligibility": "eligible_core"}
        )
        bb_sel = int(bb["summary"]["selections"] or 0)
        days = len(bb["timeline_by_day"])
        print("bb_sel", bb_sel, "days", days)
        if bb_sel <= 0:
            _fail("Bet Builder senza filtro V3.6: selections=0 inatteso su Run #15")

        if scored == 0:
            bb_v36 = bet_builder_replay(
                db,
                run_ids=[15],
                filters={
                    "eligibility": "eligible_core",
                    "purchasability_v36_min": 50,
                },
            )
            if int(bb_v36["summary"]["selections"] or 0) != 0:
                _fail("BB con V3.6 min su #15 incomplete dovrebbe essere 0")
            print("bb_v36_zero_expected_ok reason=incomplete_v36_scores")

        print("SMOKE_OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
