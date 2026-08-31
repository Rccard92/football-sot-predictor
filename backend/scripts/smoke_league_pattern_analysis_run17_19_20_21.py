"""Smoke READ-ONLY League Pattern Analysis su Run 17/19/20/21.

Verifica anchor N/ROI. Se N non coincide → SMOKE_STOP (nessun rituning).
Opzionale: --build per creare snapshot prima dello smoke.
"""

from __future__ import annotations

import argparse
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
    get_latest_league_pattern_analysis_snapshot,
    serialize_latest_payload,
)
from app.services.cecchino_data_lab.league_pattern_analysis_registry import (
    FUTURE_OOS_SEASON,
    LOCKED_SOURCE_RUN_IDS,
)

# Anchors: N esatto; ROI % con tolleranza.
ROI_TOL = 0.55

ANCHORS = {
    "P01_SERIE_B": {
        "kind": "pattern_league",
        "pattern_id": "P01",
        "competition": "Serie B",
        "seasons": {
            "2021/2022": (9, -14.89),
            "2022/2023": (7, 55.29),
            "2023/2024": (9, -64.89),
            "2024/2025": (12, 36.92),
        },
        "pooled": (37, 3.03),
    },
    "P09_SERIE_B": {
        "kind": "pattern_league",
        "pattern_id": "P09",
        "competition": "Serie B",
        "seasons": {
            "2021/2022": (11, -14.55),
            "2022/2023": (18, 23.61),
            "2023/2024": (7, 45.71),
            "2024/2025": (20, 62.00),
        },
        "pooled": (56, 32.59),
    },
    "P08_SERIE_A": {
        "kind": "pattern_league",
        "pattern_id": "P08",
        "competition": "Serie A",
        "seasons": {
            "2021/2022": (6, -6.67),
            "2022/2023": (10, -40.00),
            "2023/2024": (6, 21.50),
            "2024/2025": (5, -36.80),
        },
        "pooled": (27, -18.33),
    },
    "LN01": {
        "kind": "native",
        "pattern_id": "LN01",
        "seasons": {
            "2021/2022": (35, 17.31),
            "2022/2023": (66, 8.91),
            "2023/2024": (60, 27.60),
            "2024/2025": (22, 23.09),
        },
        "pooled": (183, 18.35),
    },
    "LN02": {
        "kind": "native",
        "pattern_id": "LN02",
        "seasons": {
            "2021/2022": (27, 16.00),
            "2022/2023": (45, 27.87),
            "2023/2024": (39, 11.10),
            "2024/2025": (35, 14.14),
        },
        "pooled": (146, 17.90),
    },
    "LN03": {
        "kind": "native",
        "pattern_id": "LN03",
        "seasons": {
            "2021/2022": (48, 11.54),
            "2022/2023": (25, 9.76),
            "2023/2024": (28, 10.61),
            "2024/2025": (42, 22.33),
        },
        "pooled": (143, 14.22),
    },
    "LN08": {
        "kind": "native",
        "pattern_id": "LN08",
        "pooled": (76, 29.21),
    },
    "LN09": {
        "kind": "native",
        "pattern_id": "LN09",
        "seasons": {
            "2021/2022": (None, 17.04),
            "2022/2023": (None, 15.80),
            "2023/2024": (None, 13.04),
            "2024/2025": (None, 10.94),
        },
        "pooled": (107, 14.07),
    },
}


def _stop(msg: str) -> None:
    print(f"SMOKE_STOP: {msg}")
    raise SystemExit(1)


def _check_roi(label: str, got: float | None, expected: float) -> None:
    if got is None:
        _stop(f"{label}: ROI missing (expected ~{expected})")
    if abs(float(got) - float(expected)) > ROI_TOL:
        _stop(f"{label}: ROI {got} vs expected {expected} (tol={ROI_TOL})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="Crea snapshot prima dello smoke")
    args = parser.parse_args()

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        if args.build:
            t0 = time.perf_counter()
            build_league_pattern_analysis_snapshot(
                db, source_run_ids=list(LOCKED_SOURCE_RUN_IDS)
            )
            print(f"build_elapsed_s={time.perf_counter() - t0:.2f}")

        t0 = time.perf_counter()
        snap = get_latest_league_pattern_analysis_snapshot(db)
        if snap is None:
            _stop("Nessuno snapshot ready — esegui con --build")
        payload = serialize_latest_payload(snap)
        get_elapsed = time.perf_counter() - t0

        meta = payload["metadata"]
        summary = payload["summary"]
        print(f"source_runs {meta.get('source_run_ids')}")
        print(f"seasons {meta.get('source_seasons')}")
        print(f"global_patterns {summary.get('global_patterns_count')}")
        print(f"competitions {summary.get('competitions_count')}")
        print(f"league_native {summary.get('league_native_count')}")
        print(f"get_elapsed_s={get_elapsed:.4f}")

        if list(meta.get("source_run_ids") or []) != LOCKED_SOURCE_RUN_IDS:
            _stop(f"source_run_ids {meta.get('source_run_ids')}")
        if meta.get("future_oos_included") is True:
            _stop("future_oos_included=true")
        if FUTURE_OOS_SEASON in (meta.get("source_seasons") or []):
            _stop("2025/2026 in source_seasons")
        print("NO_2025_26_OK")

        # Full pattern blocks from DB row for league anchors
        gp_full = (snap.global_patterns_json or {}).get("patterns") or []
        ln_full = (snap.league_native_json or {}).get("patterns") or []
        gp_by_id = {p["pattern_id"]: p for p in gp_full}
        ln_by_id = {p["pattern_id"]: p for p in ln_full}

        for name, spec in ANCHORS.items():
            if spec["kind"] == "pattern_league":
                p = gp_by_id.get(spec["pattern_id"])
                if not p:
                    _stop(f"{name}: pattern missing")
                cdata = (p.get("by_competition") or {}).get(spec["competition"])
                if not cdata:
                    _stop(f"{name}: competition missing")
                for season, (exp_n, exp_roi) in (spec.get("seasons") or {}).items():
                    s = (cdata.get("by_season") or {}).get(season) or {}
                    got_n = int(s.get("n") or 0)
                    if exp_n is not None and got_n != exp_n:
                        _stop(f"{name} {season}: N={got_n} expected {exp_n}")
                    _check_roi(f"{name} {season}", s.get("roi_pct"), exp_roi)
                pn, proi = spec["pooled"]
                tot = cdata.get("total") or {}
                if int(tot.get("n") or 0) != pn:
                    _stop(f"{name} pooled: N={tot.get('n')} expected {pn}")
                _check_roi(f"{name} pooled", tot.get("roi_pct"), proi)
                print(f"{name}_OK")
            else:
                p = ln_by_id.get(spec["pattern_id"])
                if not p:
                    _stop(f"{name}: LN missing")
                for season, (exp_n, exp_roi) in (spec.get("seasons") or {}).items():
                    s = (p.get("by_season") or {}).get(season) or {}
                    if exp_n is not None:
                        got_n = int(s.get("n") or 0)
                        if got_n != exp_n:
                            _stop(f"{name} {season}: N={got_n} expected {exp_n}")
                    _check_roi(f"{name} {season}", s.get("roi_pct"), exp_roi)
                pn, proi = spec["pooled"]
                tot = p.get("total") or {}
                if int(tot.get("n") or 0) != pn:
                    _stop(f"{name} pooled: N={tot.get('n')} expected {pn}")
                _check_roi(f"{name} pooled", tot.get("roi_pct"), proi)
                print(f"{name}_OK")

        import json

        payload_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
        print(f"payload_bytes={payload_bytes}")
        print("SMOKE_OK")
        return 0
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
