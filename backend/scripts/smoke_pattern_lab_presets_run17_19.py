"""Smoke READ-ONLY preset P01-P12 + coverage Run #17 / #19 / #20 (una passata per run).

Non lancia Historical Scan. Stampa tabella metriche, confronta discovery P06-P12
(N esatto; ROI a precisione dei target congelati),
rigenera AI Summary Run #20.
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
    PRESET_REGISTRY_VERSION,
    preset_scientific_filters,
)
from app.services.cecchino_data_lab.pattern_lab_service import (
    count_eligible_market_rows,
    iter_pattern_lab_rows,
)

RUN17 = 17
RUN19 = 19
RUN20 = 20
EXPECTED_17_TOTAL = 86659
EXPECTED_17_INFORMATIVE = 14138
EXPECTED_17_V36 = 4036
EXPECTED_19_TOTAL = 84683
EXPECTED_19_V36 = 4064

# Discovery attesa P06-P12 (controllo, non target da ritoccare).
# season_label -> (selections, roi_pct). ROI in percentuale punti.
# P06-P10: ROI tolleranza <0.15 pp; P11: round 2 decimali; P12: round 1 decimale.
DISCOVERY_TARGETS: dict[str, dict[str, tuple[int, float]]] = {
    "P06": {
        "2021/2022": (71, 23.66),
        "2022/2023": (54, 25.28),
        "2023/2024": (63, 27.56),
    },
    "P07": {
        "2021/2022": (54, 23.98),
        "2022/2023": (49, 24.49),
        "2023/2024": (66, 32.24),
    },
    "P08": {
        "2021/2022": (53, 18.81),
        "2022/2023": (51, 13.71),
        "2023/2024": (60, 17.35),
    },
    "P09": {
        "2021/2022": (80, 30.81),
        "2022/2023": (69, 11.67),
        "2023/2024": (64, 26.66),
    },
    "P10": {
        "2021/2022": (66, 94.92),
        "2022/2023": (57, 16.05),
        "2023/2024": (61, 24.80),
    },
    "P11": {
        "2021/2022": (54, 11.85),
        "2022/2023": (70, 17.59),
        "2023/2024": (76, 11.63),
    },
    "P12": {
        "2021/2022": (23, 34.7),
        "2022/2023": (24, 32.2),
        "2023/2024": (36, 15.3),
    },
}

SEASON_BY_RUN = {
    RUN17: "2021/2022",
    RUN19: "2022/2023",
    RUN20: "2023/2024",
}


def _fail(msg: str) -> None:
    print(f"SMOKE_FAIL: {msg}")
    raise SystemExit(1)


def _roi_ok(pid: str, got_roi: float | None, exp_roi: float) -> bool:
    """Confronta ROI% con la precisione dei target congelati."""
    if got_roi is None:
        return False
    if pid == "P12":
        return round(got_roi, 1) == exp_roi
    if pid == "P11":
        return round(got_roi, 2) == exp_roi
    return abs(got_roi - exp_roi) < 0.15


def _scan_run(db, run_id: int) -> dict:
    """Una sola passata: informative, v36 coverage, preset metrics P01-P12."""
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
            "season": SEASON_BY_RUN.get(run_id),
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
        f"{'preset':<8} {'season':<10} {'N':>8} {'real':>8} {'WR':>8} "
        f"{'avgOdds':>8} {'profit':>10} {'ROI':>8}"
    )
    for p in presets:
        wr = p["win_rate"]
        wr_s = f"{wr*100:.1f}%" if wr is not None else "-"
        avg = p["avg_real_odds"]
        avg_s = f"{avg:.3f}" if avg is not None else "-"
        roi = p["roi"]
        roi_s = f"{roi*100:.2f}%" if roi is not None else "-"
        season = p.get("season") or "-"
        print(
            f"{p['preset_id']:<8} {season:<10} {p['selections']:>8} {p['real_quote_count']:>8} "
            f"{wr_s:>8} {avg_s:>8} {p['profit_1u']:>10.2f} {roi_s:>8}"
        )


def _check_discovery(presets_by_run: dict[int, list[dict]]) -> list[str]:
    """Confronta P06-P12 con target discovery. Ritorna lista discrepanze (non ritocca)."""
    deltas: list[str] = []
    for run_id, season in SEASON_BY_RUN.items():
        by_id = {p["preset_id"]: p for p in presets_by_run[run_id]}
        for pid, seasons in DISCOVERY_TARGETS.items():
            if season not in seasons:
                continue
            if pid not in by_id:
                deltas.append(f"{pid} {season}: missing from registry scan")
                continue
            exp_n, exp_roi = seasons[season]
            got = by_id[pid]
            got_n = int(got["selections"])
            got_roi = (got["roi"] * 100.0) if got["roi"] is not None else None
            n_ok = got_n == exp_n
            roi_ok = _roi_ok(pid, got_roi, exp_roi)
            if pid == "P12":
                round_roi = round(got_roi, 1) if got_roi is not None else None
                status = "MATCH" if (n_ok and roi_ok) else "DIFF"
                print(
                    f"P12 {season}: expected N={exp_n} ROI={exp_roi}% "
                    f"got N={got_n} ROI={got_roi} round1={round_roi} {status}"
                )
            if not n_ok or not roi_ok:
                if pid == "P12":
                    round_roi = round(got_roi, 1) if got_roi is not None else None
                    deltas.append(
                        f"P12 {season}: expected N={exp_n} ROI={exp_roi}% "
                        f"got N={got_n} ROI={got_roi} round1={round_roi}"
                    )
                else:
                    deltas.append(
                        f"{pid} {season}: expected N={exp_n} ROI~={exp_roi}% "
                        f"got N={got_n} ROI={got_roi}"
                    )
    return deltas


def main() -> int:
    if PRESET_REGISTRY_VERSION != "pattern_lab_presets_v3":
        _fail(f"registry_version={PRESET_REGISTRY_VERSION} expected pattern_lab_presets_v3")
    if len(PATTERN_LAB_PRESETS) != 12:
        _fail(f"presets count={len(PATTERN_LAB_PRESETS)} expected 12")

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

        print("scanning_run20...")
        s20 = _scan_run(db, RUN20)
        print("run20_market_informative", s20["informative"])
        print("run20_v36_score_coverage", s20["v36"])

        presets_by_run = {RUN17: s17["presets"], RUN19: s19["presets"], RUN20: s20["presets"]}
        combined = []
        for rid in (RUN17, RUN19, RUN20):
            combined.extend(presets_by_run[rid])
        _print_preset_table("P01-P12 x Run #17/#19/#20", combined)

        deltas = _check_discovery(presets_by_run)
        if deltas:
            print("\n=== DISCOVERY DELTAS (nessuna rituning) ===")
            for d in deltas:
                print("DELTA:", d)
            print("SMOKE_STOP: discrepanze rispetto ai numeri discovery P06-P12 attesi.")
            return 1
        print("discovery_p06_p12_ok")

        print("writing_ai_summary_run20...")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            path = tmp.name
        with open(path, "wb") as dest:
            filename, size = write_ai_summary_v5_zip(db, RUN20, dest)
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
            for key in (
                "scan_source_git_commit_recorded",
                "report_generator_git_commit",
                "report_generator_revision_status",
            ):
                if key not in manifest:
                    _fail(f"manifest missing {key}")
            print(
                "provenance",
                {
                    "scan_recorded": manifest.get("scan_source_git_commit_recorded"),
                    "scan_source": manifest.get("scan_source_git_commit_source"),
                    "gen": manifest.get("report_generator_git_commit"),
                    "gen_source": manifest.get("report_generator_git_commit_source"),
                    "conflict": manifest.get("report_generator_revision_conflict"),
                },
            )
            v36 = json.loads(zf.read("purchasability_v36_summary.json"))
            print("v36_coverage_score", v36.get("coverage_score"))
            presets_zip = json.loads(zf.read("preset_patterns_summary.json"))
            if presets_zip.get("registry_version") != "pattern_lab_presets_v3":
                _fail(
                    f"preset_patterns_summary registry_version="
                    f"{presets_zip.get('registry_version')} expected pattern_lab_presets_v3"
                )
            if len(presets_zip.get("presets") or []) != 12:
                _fail(
                    f"preset_patterns_summary expected 12 got "
                    f"{len(presets_zip.get('presets') or [])}"
                )
            for p in presets_zip["presets"]:
                if not p.get("scientific_filters_sha256"):
                    _fail(f"missing sha256 on {p.get('preset_id')}")
                if "validation_history" not in p:
                    _fail(f"missing validation_history on {p.get('preset_id')}")
            p12_zip = next(
                (p for p in presets_zip["presets"] if p.get("preset_id") == "P12"),
                None,
            )
            if not p12_zip:
                _fail("P12 missing from preset_patterns_summary")
            flags = p12_zip.get("flags") or {}
            if flags.get("low_sample") is not True:
                _fail("P12 flags.low_sample missing")
            if flags.get("refinement_pattern") is not True:
                _fail("P12 flags.refinement_pattern missing")
            if flags.get("derived_from") != "P03":
                _fail("P12 flags.derived_from expected P03")
            _print_preset_table(
                "Run #20 presets (from AI Summary ZIP)",
                [
                    {
                        "preset_id": p["preset_id"],
                        "season": "2023/2024",
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
            readme = zf.read("README_FOR_AI.md").decode("utf-8")
            if "P06–P12" not in readme:
                _fail("README missing P06–P12 note")
            if "low-sample refinement candidate" not in readme:
                _fail("README missing P12 low-sample refinement note")
            if "first OOS 2024/25" not in readme:
                _fail("README missing P12 first OOS 2024/25 note")
            instr = zf.read("AI_INSTRUCTIONS.md").decode("utf-8")
            if "Acquistabilità ufficiale = **solo V3**" in instr:
                _fail("obsolete V3-only instruction still present")

        print("ai_summary_run20_ok")
        print("SMOKE_OK")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
