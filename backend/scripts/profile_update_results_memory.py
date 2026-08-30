"""Baseline memoria update-results (Fase 0 BEFORE).

ATTENZIONE: questo script SCRIVE sul DB (risultati, settlement Signals/KPI/
Purchasability/Balance). Usare solo clone/dev o dataset controllato.
NON lanciare su production senza conferma esplicita dell'operatore.

Uso (da cartella backend):

  set CECCHINO_UPDATE_RESULTS_MEMORY_PROFILE=true
  set DATABASE_URL=...
  python -m scripts.profile_update_results_memory --date 2026-08-29 --settle-seconds 120

Passi:
  1) query pg_column_size JSONB (Session dedicata, chiusa prima del job)
  2) update_today_fixture_results (workload reale profilato)
  3) opzionale sleep per RSS residuo (HWM proxy)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("CECCHINO_UPDATE_RESULTS_MEMORY_PROFILE", "true")

_JSONB_COLS = (
    "odds_snapshot_json",
    "stats_snapshot_json",
    "cecchino_output_json",
    "kpi_panel_json",
    "xg_profiles_json",
    "raw_fixture_json",
    "warnings_json",
    "blocking_reasons_json",
)


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


def measure_jsonb_pg_column_size(Session, *, scan_date: date) -> dict[str, Any]:
    """Misura dimensione JSONB lato PostgreSQL — Session dedicata, fuori dal peak del job."""
    from sqlalchemy import text

    col_exprs = ",\n        ".join(
        f"COALESCE(SUM(pg_column_size(t.{col})), 0) AS {col}_bytes" for col in _JSONB_COLS
    )
    sql = text(
        f"""
        SELECT
            COUNT(*)::bigint AS fixtures_count,
            {col_exprs},
            COALESCE(SUM(
                {" + ".join(f"COALESCE(pg_column_size(t.{c}), 0)" for c in _JSONB_COLS)}
            ), 0) AS jsonb_total_bytes
        FROM cecchino_today_fixtures t
        WHERE t.scan_date = :scan_date
        """
    )
    with Session() as db:
        row = db.execute(sql, {"scan_date": scan_date}).mappings().one()
        out = dict(row)
    # Session chiusa: nessun ORM/JSONB in identity map del job successivo.
    return {
        "scan_date": scan_date.isoformat(),
        "fixtures_count": int(out["fixtures_count"]),
        "jsonb_total_bytes": int(out["jsonb_total_bytes"]),
        "jsonb_total_mb": round(int(out["jsonb_total_bytes"]) / (1024 * 1024), 3),
        "per_column_bytes": {col: int(out[f"{col}_bytes"]) for col in _JSONB_COLS},
        "note": "Measured via pg_column_size in a dedicated Session closed before the job.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Profile memoria update-results (BEFORE). SCRIVE sul DB."
    )
    parser.add_argument("--date", required=True, help="scan_date YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Rome")
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=120,
        help="attesa post-job per RSS residuo (0=skip). Default 120.",
    )
    parser.add_argument("--out", default=None, help="path JSON report")
    parser.add_argument(
        "--phase",
        default="BEFORE",
        help="etichetta report",
    )
    parser.add_argument(
        "--i-understand-writes",
        action="store_true",
        help="obbligatorio: conferma che lo script scrive sul DB target",
    )
    args = parser.parse_args()

    if not args.i_understand_writes:
        print(
            "Rifiuto: passare --i-understand-writes per confermare scritture sul DB.\n"
            "Usare solo clone/dev. Non production senza conferma operatore.",
            file=sys.stderr,
        )
        return 2

    scan_date = date.fromisoformat(args.date)
    os.environ["CECCHINO_UPDATE_RESULTS_MEMORY_PROFILE"] = "true"

    from app.services.cecchino.update_results_memory_profile import (
        clear_last_profile,
        get_last_profile,
    )
    from app.services.cecchino.cecchino_today_service import update_today_fixture_results

    engine, Session = _build_session()
    report: dict[str, Any] = {
        "meta": {
            "phase": args.phase,
            "scan_date": scan_date.isoformat(),
            "timezone": args.timezone,
            "pid": os.getpid(),
            "cecchino_update_results_memory_profile": True,
            "settle_seconds": args.settle_seconds,
            "warning": "This run WRITES results/settlement to the target database.",
        },
        "process_rss_start_mb": _rss_mb(),
    }

    print(f"=== UPDATE RESULTS memory profile {args.phase} ===")
    print(json.dumps(report["meta"], indent=2))
    print(f"process_rss_start_mb={report['process_rss_start_mb']}")

    print("\n--- Pre-job: pg_column_size JSONB (Session dedicata) ---")
    jsonb_meta = measure_jsonb_pg_column_size(Session, scan_date=scan_date)
    report["jsonb_pg_column_size"] = jsonb_meta
    print(json.dumps(jsonb_meta, indent=2, default=str))

    clear_last_profile()
    rss_before = _rss_mb()
    t0 = time.perf_counter()
    print("\n--- Job: update_today_fixture_results ---")
    with Session() as db:
        payload = update_today_fixture_results(
            db,
            scan_date=scan_date,
            timezone=args.timezone,
        )
    elapsed_s = round(time.perf_counter() - t0, 3)
    rss_after = _rss_mb()
    prof = get_last_profile() or {}

    report["job"] = {
        "elapsed_s": elapsed_s,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": (
            round(rss_after - rss_before, 2)
            if rss_before is not None and rss_after is not None
            else None
        ),
        "payload_status": payload.get("status"),
        "fixtures_checked": payload.get("fixtures_checked"),
        "results_updated": payload.get("results_updated"),
        "api_calls": payload.get("api_calls"),
        "signals_evaluated": payload.get("signals_evaluated"),
        "failed_count": len(payload.get("failed") or []),
        "warnings_count": len(payload.get("warnings") or []),
        "profile": prof,
    }
    print(json.dumps({k: v for k, v in report["job"].items() if k != "profile"}, indent=2))
    print("profile_peak_rss_mb=", (prof or {}).get("rss_peak_mb"))
    print("profile_uow_peak=", (prof or {}).get("uow_peak"))

    settle = {}
    if args.settle_seconds > 0:
        print(f"\n--- Settle {args.settle_seconds}s (RSS residuo / HWM proxy) ---")
        samples = []
        step = max(30, min(60, args.settle_seconds))
        waited = 0
        while waited < args.settle_seconds:
            sleep_for = min(step, args.settle_seconds - waited)
            time.sleep(sleep_for)
            waited += sleep_for
            samples.append({"after_s": waited, "rss_mb": _rss_mb()})
            print(f"  t+{waited}s rss_mb={samples[-1]['rss_mb']}")
        settle = {
            "settle_seconds": args.settle_seconds,
            "samples": samples,
            "rss_final_mb": samples[-1]["rss_mb"] if samples else _rss_mb(),
        }
        report["settle"] = settle

    report["process_rss_end_mb"] = _rss_mb()
    if report["process_rss_start_mb"] is not None and report["process_rss_end_mb"] is not None:
        report["process_rss_growth_mb"] = round(
            report["process_rss_end_mb"] - report["process_rss_start_mb"],
            2,
        )

    report["human_summary"] = _build_human_summary(report)
    print("\n" + report["human_summary"])

    out_path = args.out
    if not out_path:
        out_path = str(
            _BACKEND_ROOT
            / "scripts"
            / f"update_results_memory_{args.phase.lower()}_{scan_date.isoformat()}.json"
        )
    Path(out_path).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport scritto: {out_path}")
    engine.dispose()
    return 0 if payload.get("status") == "ok" else 1


def _cp_rss(prof: dict, name: str) -> Any:
    cp = (prof.get("checkpoints") or {}).get(name) or {}
    return cp.get("rss_mb")


def _cp_uow(prof: dict, name: str) -> dict:
    cp = (prof.get("checkpoints") or {}).get(name) or {}
    return cp.get("uow") or {}


def _stage_delta_summary(prof: dict) -> str:
    lines = []
    for sample in prof.get("stage_samples") or []:
        stages = sample.get("stages") or {}
        order = [
            "after_apply_result",
            "after_signals_evaluation",
            "after_kpi_revaluation",
            "after_purchasability_validation",
            "after_balance_settlement",
        ]
        prev_rss = None
        deltas = []
        for name in order:
            rss = (stages.get(name) or {}).get("rss_mb")
            if rss is not None and prev_rss is not None:
                deltas.append(f"{name}: {round(rss - prev_rss, 2)} MB")
            if rss is not None:
                prev_rss = rss
        lines.append(
            f"  fixture_index={sample.get('fixture_index')} id={sample.get('fixture_id')}: "
            + ("; ".join(deltas) if deltas else "n/a")
        )
    return "\n".join(lines) if lines else "  (nessun campione)"


def _build_human_summary(report: dict[str, Any]) -> str:
    job = report.get("job") or {}
    prof = job.get("profile") or {}
    jsonb = report.get("jsonb_pg_column_size") or {}
    settle = report.get("settle") or {}
    counters = prof.get("counters") or {}
    uow_peak = prof.get("uow_peak") or {}
    enter_uow = _cp_uow(prof, "enter")
    end_uow = _cp_uow(prof, "before_return")
    commit_uow = _cp_uow(prof, "before_commit")

    return f"""UPDATE RESULTS — {report.get('meta', {}).get('phase', 'BEFORE')}

fixtures: {job.get('fixtures_checked')} (jsonb_pg fixtures_count={jsonb.get('fixtures_count')})
elapsed: {job.get('elapsed_s')} s

RSS:
  enter: {_cp_rss(prof, 'enter')}
  after_rows: {_cp_rss(prof, 'after_rows_query')}
  after_api: {_cp_rss(prof, 'after_initial_api_fetch')}
  peak: {prof.get('rss_peak_mb')}
  before_second_pass: {_cp_rss(prof, 'before_second_pass')}
  after_second_pass: {_cp_rss(prof, 'after_second_pass')}
  after_readiness_goal: {_cp_rss(prof, 'after_readiness_goal')}
  before_commit: {_cp_rss(prof, 'before_commit')}
  return: {_cp_rss(prof, 'before_return')}
  after_request (settle): {(settle.get('rss_final_mb') if settle else 'n/a')}

SQLAlchemy UoW:
  enter: {enter_uow}
  peak: {uow_peak}
  before_commit: {commit_uow}
  end: {end_uow}

Counters:
  api_calls={counters.get('api_calls')} signals={counters.get('signals_evaluated')}
  kpi={counters.get('kpi_revaluated')} purchasability={counters.get('purchasability_evaluated')}
  balance={counters.get('balance_settled')} errors={counters.get('errors')}
  fixtures_processed={counters.get('fixtures_processed')}

JSONB (pg_column_size pre-job, fuori peak):
  total_bytes={jsonb.get('jsonb_total_bytes')} ({jsonb.get('jsonb_total_mb')} MB)
  per_column={jsonb.get('per_column_bytes')}

Per-stage delta (campione):
{_stage_delta_summary(prof)}

Materializzazione:
  CecchinoTodayFixture: SELECT full ORM giornata (8 JSONB)
  altre ORM: SignalActivation + KpiSignalActivation + PurchasabilityEvaluation + BalanceV5Evaluation per fixture
  Session: 1 request-scoped, 1 commit finale, rows tiene vivi tutti gli ORM

Diagnosi: (compilare A–I dai delta RSS/UoW sopra)
Raccomandazione: (in-process / batch-runner / entrambe) — solo dopo i numeri
STOP.
"""


if __name__ == "__main__":
    raise SystemExit(main())
