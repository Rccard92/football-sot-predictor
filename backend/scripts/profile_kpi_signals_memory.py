"""Baseline memoria Segnali KPI (Fase 0 BEFORE).

Uso (da cartella backend, con DATABASE_URL Railway):

  set KPI_SIGNALS_MEMORY_PROFILE=true
  set DATABASE_URL=...
  python -m scripts.profile_kpi_signals_memory

Oppure:

  railway variable list --service backend --kv  (estrarre DATABASE_URL)
  ...

Scenario default: date_from=2026-08-01, date_to=today, only_current=true.
Read-only: non scrive sul DB.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

# Assicura import `app.*` quando lanciato come script
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("KPI_SIGNALS_MEMORY_PROFILE", "true")


def _rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2)
    except Exception as exc:
        print(f"[warn] psutil RSS unavailable: {exc}", file=sys.stderr)
        return None


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgresql://") and "+psycopg" not in url and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


def _build_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    raw = os.environ.get("DATABASE_URL") or ""
    if not raw:
        try:
            from app.core.config import get_settings

            raw = get_settings().database_url
        except Exception as exc:
            raise SystemExit(f"DATABASE_URL mancante: {exc}") from exc
    url = _normalize_db_url(raw)
    engine = create_engine(url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return engine, Session


def _run_summary(db, *, date_from: date, date_to: date, include_diagnostics: bool) -> dict:
    from app.services.cecchino.cecchino_kpi_signals_aggregation import build_kpi_signals_summary
    from app.services.cecchino.kpi_signals_memory_profile import clear_last_profile, get_last_profile

    clear_last_profile()
    rss_before = _rss_mb()
    t0 = time.perf_counter()
    payload = build_kpi_signals_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        only_current=True,
        include_diagnostics=include_diagnostics,
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    rss_after = _rss_mb()
    prof = get_last_profile() or {}
    overall = payload.get("overall") or {}
    diag = payload.get("diagnostics") or {}
    return {
        "scenario": "summary",
        "include_diagnostics": include_diagnostics,
        "elapsed_ms": elapsed_ms,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": (
            round(rss_after - rss_before, 2)
            if rss_before is not None and rss_after is not None
            else None
        ),
        "overall_activations": overall.get("activations"),
        "diagnostics_fixtures": diag.get("today_fixtures_count"),
        "diagnostics_kpi_signals_created": diag.get("kpi_signals_created"),
        "profile": prof,
    }


def _run_activations(db, *, date_from: date, date_to: date, limit: int) -> dict:
    from app.services.cecchino.cecchino_kpi_signals_aggregation import list_kpi_signal_activations
    from app.services.cecchino.kpi_signals_memory_profile import clear_last_profile, get_last_profile

    clear_last_profile()
    rss_before = _rss_mb()
    t0 = time.perf_counter()
    payload = list_kpi_signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        only_current=True,
        limit=limit,
        offset=0,
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    rss_after = _rss_mb()
    prof = get_last_profile() or {}
    return {
        "scenario": "activations",
        "limit": limit,
        "elapsed_ms": elapsed_ms,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": (
            round(rss_after - rss_before, 2)
            if rss_before is not None and rss_after is not None
            else None
        ),
        "total": payload.get("total"),
        "page_rows": len(payload.get("activations") or []),
        "profile": prof,
    }


def _run_load_all_new(db, *, date_from: date, date_to: date, limit: int) -> dict:
    """Path FE post-fix: summary(include_diagnostics=false) + activations; diagnostics solo se activations==0."""
    from app.services.cecchino.cecchino_kpi_signals_aggregation import build_kpi_signals_diagnostics
    from app.services.cecchino.kpi_signals_memory_profile import clear_last_profile, get_last_profile

    clear_last_profile()
    rss_before = _rss_mb()
    t0 = time.perf_counter()
    summary = _run_summary(db, date_from=date_from, date_to=date_to, include_diagnostics=False)
    activations = _run_activations(db, date_from=date_from, date_to=date_to, limit=limit)
    diagnostics = None
    if (summary.get("overall_activations") or 0) == 0:
        clear_last_profile()
        t_d0 = time.perf_counter()
        rss_d0 = _rss_mb()
        build_kpi_signals_diagnostics(db, date_from=date_from, date_to=date_to)
        diagnostics = {
            "elapsed_ms": round((time.perf_counter() - t_d0) * 1000.0, 1),
            "rss_before_mb": rss_d0,
            "rss_after_mb": _rss_mb(),
            "profile": get_last_profile(),
        }
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    rss_after = _rss_mb()
    return {
        "scenario": "loadAll_new_lazy_diagnostics",
        "elapsed_ms": elapsed_ms,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": (
            round(rss_after - rss_before, 2)
            if rss_before is not None and rss_after is not None
            else None
        ),
        "summary": summary,
        "activations": activations,
        "diagnostics_lazy": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile memoria Segnali KPI (BEFORE/AFTER)")
    parser.add_argument("--date-from", default="2026-08-01")
    parser.add_argument("--date-to", default=None, help="default: today UTC/local date()")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--repeats", type=int, default=5, help="ripetizioni loadAll nello stesso processo")
    parser.add_argument("--phase", default="AFTER", help="etichetta report: BEFORE/AFTER")
    parser.add_argument("--json-out", default=None, help="path file JSON report")
    args = parser.parse_args()

    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to) if args.date_to else date.today()

    os.environ["KPI_SIGNALS_MEMORY_PROFILE"] = "true"

    engine, Session = _build_session()
    report: dict = {
        "meta": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "only_current": True,
            "activations_limit": args.limit,
            "repeats": args.repeats,
            "pid": os.getpid(),
            "kpi_signals_memory_profile": True,
            "phase": args.phase,
        },
        "process_rss_start_mb": _rss_mb(),
        "scenarios": {},
    }

    print(f"=== KPI Signals memory profile {args.phase} ===")
    print(json.dumps(report["meta"], indent=2))
    print(f"process_rss_start_mb={report['process_rss_start_mb']}")

    with Session() as db:
        # A. summary alone (con diagnostics — path legacy alleggerito)
        print("\n--- A: summary include_diagnostics=true ---")
        a = _run_summary(db, date_from=date_from, date_to=date_to, include_diagnostics=True)
        report["scenarios"]["A_summary_with_diagnostics"] = a
        print(json.dumps(a, indent=2, default=str))
        db.expire_all()

        # A2. summary senza diagnostics (path FE normale)
        print("\n--- A2: summary include_diagnostics=false ---")
        a2 = _run_summary(db, date_from=date_from, date_to=date_to, include_diagnostics=False)
        report["scenarios"]["A2_summary_no_diagnostics"] = a2
        print(json.dumps(a2, indent=2, default=str))
        db.expire_all()

        # A3. diagnostics endpoint-only
        print("\n--- A3: diagnostics dedicated ---")
        from app.services.cecchino.cecchino_kpi_signals_aggregation import (
            build_kpi_signals_diagnostics,
        )
        from app.services.cecchino.kpi_signals_memory_profile import clear_last_profile, get_last_profile

        clear_last_profile()
        rss_b = _rss_mb()
        t0 = time.perf_counter()
        diag_payload = build_kpi_signals_diagnostics(db, date_from=date_from, date_to=date_to)
        a3 = {
            "scenario": "diagnostics_only",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "rss_before_mb": rss_b,
            "rss_after_mb": _rss_mb(),
            "diagnostics_fixtures": (diag_payload.get("diagnostics") or {}).get(
                "today_fixtures_count"
            ),
            "kpi_signals_created": (diag_payload.get("diagnostics") or {}).get(
                "kpi_signals_created"
            ),
            "profile": get_last_profile(),
        }
        if a3["rss_before_mb"] is not None and a3["rss_after_mb"] is not None:
            a3["rss_delta_mb"] = round(a3["rss_after_mb"] - a3["rss_before_mb"], 2)
        report["scenarios"]["A3_diagnostics_only"] = a3
        print(json.dumps(a3, indent=2, default=str))
        db.expire_all()

        # B. activations
        print("\n--- B: activations limit ---")
        b = _run_activations(db, date_from=date_from, date_to=date_to, limit=args.limit)
        report["scenarios"]["B_activations"] = b
        print(json.dumps(b, indent=2, default=str))
        db.expire_all()

        # C. loadAll legacy (summary+diag true)
        print("\n--- C: loadAll legacy (summary diag=true + activations) ---")
        c_legacy_summary = _run_summary(
            db, date_from=date_from, date_to=date_to, include_diagnostics=True
        )
        c_legacy_act = _run_activations(db, date_from=date_from, date_to=date_to, limit=args.limit)
        report["scenarios"]["C_loadAll_legacy"] = {
            "summary": c_legacy_summary,
            "activations": c_legacy_act,
        }
        print(json.dumps(report["scenarios"]["C_loadAll_legacy"], indent=2, default=str))
        db.expire_all()

        # C2. loadAll new FE path
        print("\n--- C2: loadAll NEW (summary diag=false + activations + lazy diag) ---")
        c2 = _run_load_all_new(db, date_from=date_from, date_to=date_to, limit=args.limit)
        report["scenarios"]["C2_loadAll_new"] = c2
        print(json.dumps(c2, indent=2, default=str))
        db.expire_all()

        # D. repeats new path
        print(f"\n--- D: loadAll NEW x{args.repeats} ---")
        repeats = []
        for i in range(args.repeats):
            r = _run_load_all_new(db, date_from=date_from, date_to=date_to, limit=args.limit)
            r["iteration"] = i + 1
            repeats.append(r)
            print(
                f"  #{i + 1}: elapsed_ms={r['elapsed_ms']} "
                f"rss_before={r['rss_before_mb']} rss_after={r['rss_after_mb']} "
                f"delta={r['rss_delta_mb']}"
            )
            db.expire_all()
        report["scenarios"]["D_loadAll_new_repeats"] = repeats

    report["process_rss_end_mb"] = _rss_mb()
    if report["process_rss_start_mb"] is not None and report["process_rss_end_mb"] is not None:
        report["process_rss_growth_mb"] = round(
            report["process_rss_end_mb"] - report["process_rss_start_mb"],
            2,
        )
    print("\n=== process end ===")
    print(
        json.dumps(
            {
                "process_rss_start_mb": report["process_rss_start_mb"],
                "process_rss_end_mb": report["process_rss_end_mb"],
                "process_rss_growth_mb": report.get("process_rss_growth_mb"),
            },
            indent=2,
        )
    )

    out_path = args.json_out
    if not out_path:
        out_path = str(
            _BACKEND_ROOT
            / "scripts"
            / f"kpi_signals_memory_{args.phase.lower()}_{date_from.isoformat()}_{date_to.isoformat()}.json"
        )
    Path(out_path).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport scritto: {out_path}")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
