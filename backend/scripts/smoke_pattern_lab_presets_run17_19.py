"""Smoke READ-ONLY preset P01–P05 + coverage Run #17 / #19 (una passata per run).

Non lancia Historical Scan. Stampa tabella metriche e informative Run19.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
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

from app.services.cecchino_data_lab.pattern_lab_ai_summary import (
    AI_SUMMARY_SCHEMA_VERSION,
    write_ai_summary_v5_zip,
)
from app.services.cecchino_data_lab.pattern_lab_filters import (
    is_market_informative,
    parse_pattern_lab_filters,
    row_passes_filters,
    v36_informative,
)
from app.services.cecchino_data_lab.pattern_lab_preset_metrics import (
    _bump_pattern,
    _bump_real,
    _empty_econ,
    _finalize_econ,
)
from app.services.cecchino_data_lab.pattern_lab_presets import (
    PATTERN_LAB_PRESETS,
    preset_scientific_filters,
)
from app.services.cecchino_data_lab.pattern_lab_service import (
    count_eligible_market_rows,
    iter_pattern_lab_rows,
)

RUN17 = 17
RUN19 = 19
EXPECTED_17_TOTAL = 86659
EXPECTED_17_INFORMATIVE = 14138
EXPECTED_17_V36 = 4036
EXPECTED_19_TOTAL = 84683
EXPECTED_19_V36 = 4064


def _fail(msg: str) -> None:
    print(f"SMOKE_FAIL: {msg}")
    raise SystemExit(1)


def _scan_run(db, run_id: int) -> dict:
    """Una sola passata: informative, v36 coverage, preset metrics."""
    parsed = [
        (p, parse_pattern_lab_filters(preset_scientific_filters(p)))
        for p in PATTERN_LAB_PRESETS
    ]
    totals = {p["id"]: _empty_econ() for p, _ in parsed}
    informative = 0
    v36_n = 0
    base = parse_pattern_lab_filters(
        {"eligibility": "eligible_core", "market_informative": False}
    )
    for row in iter_pattern_lab_rows(db, [run_id], filters=base, apply_filters=True):
        if is_market_informative(row):
            informative += 1
        if v36_informative(row):
            v36_n += 1
        for preset, filt in parsed:
            if not row_passes_filters(row, filt):
                continue
            pid = preset["id"]
            _bump_pattern(totals[pid], row)
            _bump_real(totals[pid], row)
    presets = [
        {
            "preset_id": p["id"],
            **_finalize_econ(totals[p["id"]]),
        }
        for p, _ in parsed
    ]
    return {
        "informative": informative,
        "v36": v36_n,
        "presets": presets,
    }


def _print_preset_table(label: str, presets: list[dict]) -> None:
    print(f"\n=== {label} ===")
    print(
        f"{'preset':<6} {'N':>8} {'real':>8} {'WR':>8} {'avgOdds':>8} {'profit':>10} {'ROI':>8}"
    )
    for p in presets:
        wr = p["win_rate"]
        wr_s = f"{wr*100:.1f}%" if wr is not None else "—"
        avg = p["avg_real_odds"]
        avg_s = f"{avg:.3f}" if avg is not None else "—"
        roi = p["roi"]
        roi_s = f"{roi*100:.1f}%" if roi is not None else "—"
        print(
            f"{p['preset_id']:<6} {p['selections']:>8} {p['real_quote_count']:>8} "
            f"{wr_s:>8} {avg_s:>8} {p['profit_1u']:>10.2f} {roi_s:>8}"
        )


def main() -> int:
    eng = create_engine(db_url)
    Session = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    db = Session()
    try:
        hist17 = count_eligible_market_rows(db, [RUN17], eligibility="eligible_core")
        print("run17_historical_total", hist17)
        if hist17 != EXPECTED_17_TOTAL:
            _fail(f"run17 historical={hist17} expected={EXPECTED_17_TOTAL}")

        print("scanning_run17...")
        s17 = _scan_run(db, RUN17)
        print("run17_market_informative", s17["informative"])
        print("run17_v36_score_coverage", s17["v36"])
        if s17["informative"] != EXPECTED_17_INFORMATIVE:
            _fail(f"run17 informative={s17['informative']} expected={EXPECTED_17_INFORMATIVE}")
        if s17["v36"] != EXPECTED_17_V36:
            _fail(f"run17 v36={s17['v36']} expected={EXPECTED_17_V36}")

        hist19 = count_eligible_market_rows(db, [RUN19], eligibility="eligible_core")
        print("run19_historical_total", hist19)
        if hist19 != EXPECTED_19_TOTAL:
            _fail(f"run19 historical={hist19} expected={EXPECTED_19_TOTAL}")

        print("scanning_run19...")
        s19 = _scan_run(db, RUN19)
        print("run19_market_informative", s19["informative"])
        print("run19_v36_score_coverage", s19["v36"])
        if s19["v36"] != EXPECTED_19_V36:
            _fail(f"run19 v36={s19['v36']} expected={EXPECTED_19_V36}")

        _print_preset_table("Run #17 presets", s17["presets"])
        _print_preset_table("Run #19 presets", s19["presets"])
        print(
            "p01_run17_selections",
            next(x["selections"] for x in s17["presets"] if x["preset_id"] == "P01"),
        )

        print("writing_ai_summary_run19...")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            path = tmp.name
        with open(path, "wb") as dest:
            filename, size = write_ai_summary_v5_zip(db, RUN19, dest)
        print("ai_summary_filename", filename)
        print("ai_summary_bytes", size)

        with zipfile.ZipFile(path, "r") as zf:
            names = sorted(zf.namelist())
            print("ai_summary_files", names)
            required = {
                "manifest.json",
                "run_summary.json",
                "pattern_lab_summary.json",
                "kpi_summary.json",
                "signals_summary.json",
                "balance_v5_summary.json",
                "goal_v4_compat_summary.json",
                "purchasability_v36_summary.json",
                "preset_patterns_summary.json",
                "README_FOR_AI.md",
                "AI_INSTRUCTIONS.md",
                "SCHEMA.md",
            }
            missing = required - set(names)
            if missing:
                _fail(f"AI summary missing files: {missing}")
            manifest = json.loads(zf.read("manifest.json"))
            if manifest.get("report_schema_version") != AI_SUMMARY_SCHEMA_VERSION:
                _fail(f"schema={manifest.get('report_schema_version')}")
            v36 = json.loads(zf.read("purchasability_v36_summary.json"))
            if int(v36.get("coverage_score") or 0) != EXPECTED_19_V36:
                _fail(f"v36 coverage in zip={v36.get('coverage_score')}")
            presets_zip = json.loads(zf.read("preset_patterns_summary.json"))
            if len(presets_zip.get("presets") or []) != 5:
                _fail("preset_patterns_summary missing presets")
            # print compact preset ROI from zip for Run19
            _print_preset_table(
                "Run #19 presets (from AI Summary ZIP)",
                [
                    {
                        "preset_id": p["preset_id"],
                        "selections": p["selections"],
                        "real_quote_count": p["real_quote_count"],
                        "win_rate": p["win_rate"],
                        "avg_real_odds": p["avg_real_odds"],
                        "profit_1u": p["profit_1u"],
                        "roi": p["roi"],
                    }
                    for p in presets_zip["presets"]
                ],
            )
            instr = zf.read("AI_INSTRUCTIONS.md").decode("utf-8")
            if "Acquistabilità ufficiale = **solo V3**" in instr:
                _fail("obsolete V3-only instruction still present")
            pl = json.loads(zf.read("pattern_lab_summary.json"))
            print(
                "ai_summary_pattern_lab_informative",
                pl.get("market_informative"),
                "historical",
                pl.get("historical_market_rows"),
            )

        print("ai_summary_run19_ok")
        print("RUN19_MARKET_INFORMATIVE_CANONICAL", s19["informative"])
        print("SMOKE_OK")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
