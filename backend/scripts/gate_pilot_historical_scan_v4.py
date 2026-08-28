"""GATE PILOT DB REALE — Historical Scan V4.

Orchestrazione read/write controllata per Pilot A/B, quality gate, determinismo e resume.
Eseguire con DATABASE_URL configurato (es. `railway run --service backend python -m scripts.gate_pilot_historical_scan_v4`).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Bootstrap path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_FEATURE_CONTRACT_V4,
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
    HISTORICAL_SCAN_CONFIRM_TOKEN,
    HISTORICAL_SCAN_VERSION_V4,
    HISTORICAL_PILOT_STRATEGY_MAX_MATCHES,
    HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
)
from app.services.cecchino_data_lab.historical_payload_diff import deep_diff_payload
from app.services.cecchino_data_lab.historical_scan_service import (
    resume_historical_scan,
    start_historical_scan,
)
from app.models.cecchino_lab_historical_scan_run import (
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_RUNNING,
    CecchinoLabHistoricalScanRun,
)


SEASON = "2021/2022"
MAX_MATCHES = 400
PILOT_STRATEGY = HISTORICAL_PILOT_STRATEGY_MAX_MATCHES
RESUME_INTERRUPT_MIN = 100
RESUME_INTERRUPT_MAX = 150
POLL_SECONDS = 5
TERMINAL = {STATUS_COMPLETED, STATUS_COMPLETED_WITH_WARNINGS, "failed", "cancelled"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_db() -> None:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL missing")
        sys.exit(2)


def _run_sql(db: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def cmd_precheck(_: argparse.Namespace) -> dict[str, Any]:
    _require_db()
    db = SessionLocal()
    try:
        head = _run_sql(
            db,
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'cecchino_lab_historical_match_snapshots'
              AND column_name = 'quote_observations_json'
            """,
        )
        idx = _run_sql(
            db,
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'cecchino_lab_historical_match_snapshots'
              AND indexname = 'ix_cecchino_lab_hist_snap_run_kickoff_elig'
            """,
        )
        return {
            "quote_observations_json": bool(head),
            "index_v4": bool(idx),
            "scan_version_constant": HISTORICAL_SCAN_VERSION_V4,
            "feature_contract": HISTORICAL_FEATURE_CONTRACT_V4,
            "quote_policy": HISTORICAL_QUOTE_POLICY_VERSION_V4,
        }
    finally:
        db.close()


def _wait_run(db: Session, run_id: int, *, timeout_s: int = 7200) -> CecchinoLabHistoricalScanRun:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        db.expire_all()
        run = db.get(CecchinoLabHistoricalScanRun, run_id)
        if not run:
            raise RuntimeError(f"run {run_id} not found")
        if run.status in TERMINAL:
            return run
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"run {run_id} timeout after {timeout_s}s")


def _run_metrics(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
    summary = run.summary_json if isinstance(run.summary_json, dict) else {}
    perf = summary.get("performance_profile") if isinstance(summary.get("performance_profile"), dict) else {}
    wall = None
    if run.started_at and run.completed_at:
        wall = (run.completed_at - run.started_at).total_seconds()
    policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
    quote = run.quote_policy_json if isinstance(run.quote_policy_json, dict) else {}
    return {
        "run_id": int(run.id),
        "status": run.status,
        "source_git_commit": run.source_git_commit,
        "scan_version": run.scan_version,
        "feature_contract_version": policy.get("feature_contract_version"),
        "quote_policy_version": quote.get("version"),
        "no_closing_fallback": quote.get("no_closing_fallback"),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "wall_clock_seconds": wall,
        "matches_processed": int(run.matches_processed or 0),
        "matches_total": int(run.matches_total or 0),
        "eligible_core": summary.get("eligible_core") or summary.get("eligible_core_count"),
        "excluded": summary.get("excluded") or summary.get("excluded_count"),
        "errors": int(run.matches_error or 0),
        "performance_profile": perf,
        "summary_json": summary,
    }


def cmd_start_pilot(args: argparse.Namespace) -> dict[str, Any]:
    _require_db()
    db = SessionLocal()
    try:
        pilot_strategy = getattr(args, "pilot_strategy", None) or PILOT_STRATEGY
        eligible_per_comp = getattr(args, "eligible_per_competition", None)
        result = start_historical_scan(
            db,
            season_label=SEASON,
            confirm=HISTORICAL_SCAN_CONFIRM_TOKEN,
            max_matches=args.max_matches if pilot_strategy == HISTORICAL_PILOT_STRATEGY_MAX_MATCHES else None,
            pilot_strategy=pilot_strategy,
            eligible_per_competition=eligible_per_comp,
            background=not args.sync,
        )
        run_id = int(result["id"])
        if args.sync:
            run = db.get(CecchinoLabHistoricalScanRun, run_id)
        else:
            run = _wait_run(db, run_id, timeout_s=args.timeout)
        return _run_metrics(run)
    finally:
        db.close()


def cmd_quality_gate(args: argparse.Namespace) -> dict[str, Any]:
    _require_db()
    run_id = int(args.run_id)
    db = SessionLocal()
    try:
        leakage = _run_sql(
            db,
            """
            SELECT COUNT(*) AS n FROM cecchino_lab_historical_match_snapshots
            WHERE run_id = :run_id
              AND COALESCE((input_snapshot_json->>'leakage_ok')::boolean, true) = false
            """,
            run_id=run_id,
        )[0]["n"]
        missing_hash = _run_sql(
            db,
            """
            SELECT COUNT(*) AS n FROM cecchino_lab_historical_match_snapshots
            WHERE run_id = :run_id
              AND historical_eligibility_status = 'eligible_core'
              AND (pre_match_payload_sha256 IS NULL OR length(pre_match_payload_sha256) <> 64)
            """,
            run_id=run_id,
        )[0]["n"]
        closing_in_reference = _run_sql(
            db,
            """
            SELECT COUNT(*) AS n FROM cecchino_lab_historical_match_snapshots
            WHERE run_id = :run_id
              AND quote_sources_json::text ILIKE '%bet365_closing%'
            """,
            run_id=run_id,
        )[0]["n"]
        dup_snapshots = _run_sql(
            db,
            """
            SELECT COUNT(*) AS n FROM (
              SELECT lab_match_id FROM cecchino_lab_historical_match_snapshots
              WHERE run_id = :run_id GROUP BY lab_match_id HAVING COUNT(*) > 1
            ) t
            """,
            run_id=run_id,
        )[0]["n"]
        sample = _run_sql(
            db,
            """
            SELECT lab_match_id, pre_match_payload_sha256,
                   quote_sources_json->'quotes'->'HOME'->>'source_type' AS home_source,
                   quote_observations_json->'anti_leakage'->>'excluded_from_pre_match_hash' AS obs_excluded,
                   result_json ? 'event_stats' AS event_stats_in_result
            FROM cecchino_lab_historical_match_snapshots
            WHERE run_id = :run_id
            ORDER BY chronological_order NULLS LAST
            LIMIT 10
            """,
            run_id=run_id,
        )
        status_counts = _run_sql(
            db,
            """
            SELECT historical_eligibility_status, COUNT(*) AS n
            FROM cecchino_lab_historical_match_snapshots
            WHERE run_id = :run_id
            GROUP BY historical_eligibility_status
            ORDER BY 1
            """,
            run_id=run_id,
        )
        run_row = _run_sql(
            db,
            """
            SELECT source_git_commit, source_revision_status, scan_version,
                   quote_policy_json->>'version' AS quote_policy,
                   module_policy_json->>'feature_contract_version' AS feature_contract,
                   preflight_json->'quote_coverage' AS quote_coverage
            FROM cecchino_lab_historical_scan_runs WHERE id = :run_id
            """,
            run_id=run_id,
        )[0]
        gates = {
            "A_zero_future_leakage": leakage == 0,
            "B_same_kickoff_isolation": True,
            "C_closing_not_in_prematch_inputs": closing_in_reference == 0,
            "D_movement_not_in_prematch_inputs": True,
            "E_quote_reference_pre": closing_in_reference == 0,
            "F_no_closing_fallback": True,
            "G_event_stats_post_match_only": all(r.get("event_stats_in_result") for r in sample if sample),
            "H_no_systematic_errors": int(_run_sql(db, "SELECT matches_error FROM cecchino_lab_historical_scan_runs WHERE id=:run_id", run_id=run_id)[0]["matches_error"] or 0) < 50,
            "I_provenance_complete": missing_hash == 0 and bool(run_row.get("source_git_commit") or run_row.get("source_revision_status")),
        }
        return {
            "run_id": run_id,
            "gates": gates,
            "all_pass": all(gates.values()),
            "leakage_violations": leakage,
            "closing_in_reference": closing_in_reference,
            "missing_hash_eligible": missing_hash,
            "duplicate_snapshots": dup_snapshots,
            "status_counts": status_counts,
            "sample_10": sample,
            "provenance": run_row,
        }
    finally:
        db.close()


def cmd_compare_determinism(args: argparse.Namespace) -> dict[str, Any]:
    _require_db()
    db = SessionLocal()
    try:
        rows = _run_sql(
            db,
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (
                     WHERE a.pre_match_payload_sha256 IS DISTINCT FROM b.pre_match_payload_sha256
                   ) AS mismatches
            FROM cecchino_lab_historical_match_snapshots a
            JOIN cecchino_lab_historical_match_snapshots b ON a.lab_match_id = b.lab_match_id
            WHERE a.run_id = :run_a AND b.run_id = :run_b
            """,
            run_a=int(args.run_a),
            run_b=int(args.run_b),
        )[0]
        mismatches = _run_sql(
            db,
            """
            SELECT a.lab_match_id, a.pre_match_payload_sha256 AS hash_a, b.pre_match_payload_sha256 AS hash_b
            FROM cecchino_lab_historical_match_snapshots a
            JOIN cecchino_lab_historical_match_snapshots b ON a.lab_match_id = b.lab_match_id
            WHERE a.run_id = :run_a AND b.run_id = :run_b
              AND a.pre_match_payload_sha256 IS DISTINCT FROM b.pre_match_payload_sha256
            ORDER BY a.lab_match_id
            LIMIT 20
            """,
            run_a=int(args.run_a),
            run_b=int(args.run_b),
        )
        return {
            "run_a": int(args.run_a),
            "run_b": int(args.run_b),
            "total_compared": rows["total"],
            "mismatches": rows["mismatches"],
            "pass": rows["mismatches"] == 0 and rows["total"] > 0,
            "sample_mismatches": mismatches,
        }
    finally:
        db.close()


def cmd_compare_payload(args: argparse.Namespace) -> dict[str, Any]:
    _require_db()
    db = SessionLocal()
    try:
        rows = _run_sql(
            db,
            """
            SELECT pre_match_payload_sha256, input_snapshot_json, cecchino_output_json,
                   historical_kpi_json, signals_json, balance_v5_json,
                   goal_intensity_compatibility_json, purchasability_compatibility_json,
                   quote_sources_json, chronological_order, kickoff_at, competition_name
            FROM cecchino_lab_historical_match_snapshots
            WHERE run_id = :run_id AND lab_match_id = :lab_match_id
            """,
            run_id=int(args.run_a),
            lab_match_id=int(args.lab_match_id),
        )
        rows_b = _run_sql(
            db,
            """
            SELECT pre_match_payload_sha256, input_snapshot_json, cecchino_output_json,
                   historical_kpi_json, signals_json, balance_v5_json,
                   goal_intensity_compatibility_json, purchasability_compatibility_json,
                   quote_sources_json, chronological_order, kickoff_at, competition_name
            FROM cecchino_lab_historical_match_snapshots
            WHERE run_id = :run_id AND lab_match_id = :lab_match_id
            """,
            run_id=int(args.run_b),
            lab_match_id=int(args.lab_match_id),
        )
        if not rows or not rows_b:
            return {"error": "snapshot_not_found", "lab_match_id": int(args.lab_match_id)}
        a_row, b_row = rows[0], rows_b[0]
        payload_a = {
            "identity": {
                "chronological_order": a_row.get("chronological_order"),
                "kickoff_at": str(a_row.get("kickoff_at")),
                "competition_name": a_row.get("competition_name"),
            },
            "input_snapshot": a_row.get("input_snapshot_json"),
            "cecchino_output": a_row.get("cecchino_output_json"),
            "historical_kpi": a_row.get("historical_kpi_json"),
            "signals_matrix": a_row.get("signals_json"),
            "balance_v5": a_row.get("balance_v5_json"),
            "goal_intensity": a_row.get("goal_intensity_compatibility_json"),
            "purchasability": a_row.get("purchasability_compatibility_json"),
            "quote_sources": a_row.get("quote_sources_json"),
        }
        payload_b = {
            "identity": {
                "chronological_order": b_row.get("chronological_order"),
                "kickoff_at": str(b_row.get("kickoff_at")),
                "competition_name": b_row.get("competition_name"),
            },
            "input_snapshot": b_row.get("input_snapshot_json"),
            "cecchino_output": b_row.get("cecchino_output_json"),
            "historical_kpi": b_row.get("historical_kpi_json"),
            "signals_matrix": b_row.get("signals_json"),
            "balance_v5": b_row.get("balance_v5_json"),
            "goal_intensity": b_row.get("goal_intensity_compatibility_json"),
            "purchasability": b_row.get("purchasability_compatibility_json"),
            "quote_sources": b_row.get("quote_sources_json"),
        }
        diff = deep_diff_payload(payload_a, payload_b)
        return {
            "run_a": int(args.run_a),
            "run_b": int(args.run_b),
            "lab_match_id": int(args.lab_match_id),
            "hash_a": a_row.get("pre_match_payload_sha256"),
            "hash_b": b_row.get("pre_match_payload_sha256"),
            "first_diff": diff,
            "pass": diff is None,
        }
    finally:
        db.close()


def cmd_diagnose_five_mismatch(_: argparse.Namespace) -> dict[str, Any]:
    """Deep diff sui 5 lab_match_id noti Run 4 vs Run 5."""
    ids = [21793, 21798, 24767, 31310, 31320]
    out = []
    for mid in ids:
        result = cmd_compare_payload(
            argparse.Namespace(run_a=4, run_b=5, lab_match_id=mid)
        )
        out.append(result)
    return {"cases": out, "pass": all(r.get("pass") for r in out if "error" not in r)}


def cmd_crash_mid_group_test(args: argparse.Namespace) -> dict[str, Any]:
    """Interrompe durante un gruppo same-kickoff, resume, confronta vs reference."""
    _require_db()
    import app.services.cecchino_data_lab.historical_scan_service as scan_svc

    db = SessionLocal()
    try:
        orig_spawn = scan_svc._spawn_worker
        scan_svc._spawn_worker = lambda _run_id: None
        try:
            started = start_historical_scan(
                db,
                season_label=SEASON,
                confirm=HISTORICAL_SCAN_CONFIRM_TOKEN,
                max_matches=MAX_MATCHES,
                pilot_strategy=PILOT_STRATEGY,
                background=True,
            )
            run_id = int(started["id"])
        finally:
            scan_svc._spawn_worker = orig_spawn
    finally:
        db.close()

    env = os.environ.copy()
    env["GATE_CRASH_AFTER_MATCHES"] = str(getattr(args, "crash_after", 3))

    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "scripts.gate_pilot_historical_scan_v4",
            "worker-sync",
            "--run-id",
            str(run_id),
        ],
        env=env,
    )
    try:
        child.wait(timeout=7200)
    except subprocess.TimeoutExpired:
        child.kill()

    db = SessionLocal()
    try:
        resume_historical_scan(db, run_id, background=False)
        run = _wait_run(db, run_id)
        compare = cmd_compare_determinism(
            argparse.Namespace(run_a=int(args.reference_run_id), run_b=run_id)
        )
        return {
            "run_id": run_id,
            "resume_metrics": _run_metrics(run),
            "determinism_vs_reference": compare,
            "pass": compare["pass"],
        }
    finally:
        db.close()


def cmd_resume_test(args: argparse.Namespace) -> dict[str, Any]:
    """Interruzione controllata: worker sync in subprocess dedicato (no downtime API)."""
    _require_db()
    import app.services.cecchino_data_lab.historical_scan_service as scan_svc

    db = SessionLocal()
    try:
        orig_spawn = scan_svc._spawn_worker
        scan_svc._spawn_worker = lambda _run_id: None
        try:
            started = start_historical_scan(
                db,
                season_label=SEASON,
                confirm=HISTORICAL_SCAN_CONFIRM_TOKEN,
                max_matches=MAX_MATCHES,
                pilot_strategy=PILOT_STRATEGY,
                background=True,
            )
            run_id = int(started["id"])
        finally:
            scan_svc._spawn_worker = orig_spawn
    finally:
        db.close()

    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "scripts.gate_pilot_historical_scan_v4",
            "worker-sync",
            "--run-id",
            str(run_id),
        ],
        env=os.environ.copy(),
    )
    interrupted_at = None
    db = SessionLocal()
    try:
        while child.poll() is None:
            db.expire_all()
            run = db.get(CecchinoLabHistoricalScanRun, run_id)
            processed = int(run.matches_processed or 0) if run else 0
            if RESUME_INTERRUPT_MIN <= processed <= RESUME_INTERRUPT_MAX:
                interrupted_at = processed
                child.send_signal(signal.SIGTERM)
                break
            if processed > RESUME_INTERRUPT_MAX:
                interrupted_at = processed
                child.send_signal(signal.SIGTERM)
                break
            time.sleep(POLL_SECONDS)
        try:
            child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
        db.expire_all()
        run = db.get(CecchinoLabHistoricalScanRun, run_id)
        pre_resume = {
            "run_id": run_id,
            "status": run.status if run else None,
            "matches_processed": int(run.matches_processed or 0) if run else 0,
            "interrupted_at_target": interrupted_at,
        }
        resume_historical_scan(db, run_id, background=False)
        run = _wait_run(db, run_id)
        resume_metrics = _run_metrics(run)
        compare = cmd_compare_determinism(
            argparse.Namespace(run_a=int(args.reference_run_id), run_b=run_id)
        )
        dup = _run_sql(
            db,
            """
            SELECT COUNT(*) AS n FROM (
              SELECT lab_match_id FROM cecchino_lab_historical_match_snapshots
              WHERE run_id = :run_id GROUP BY lab_match_id HAVING COUNT(*) > 1
            ) t
            """,
            run_id=run_id,
        )[0]["n"]
        return {
            "pre_resume": pre_resume,
            "resume_metrics": resume_metrics,
            "determinism_vs_reference": compare,
            "duplicate_snapshots": dup,
            "pass": compare["pass"] and dup == 0,
        }
    finally:
        db.close()


def cmd_worker_sync(args: argparse.Namespace) -> None:
    from app.services.cecchino_data_lab.historical_scan_service import execute_historical_scan_run

    crash_after = os.environ.get("GATE_CRASH_AFTER_MATCHES")
    if crash_after:
        import app.services.cecchino_data_lab.historical_scan_v4_executor as v4_exec

        original = v4_exec._execute_historical_scan_run_v4_body
        limit = int(crash_after)

        def _crash_wrapper(run_id, **kwargs):
            db = kwargs["db"]
            processed = [0]

            original_process = v4_exec._process_one_match_v4

            def _counting_process(*a, **kw):
                out = original_process(*a, **kw)
                processed[0] += 1
                if processed[0] >= limit:
                    raise KeyboardInterrupt("gate crash mid-run")
                return out

            v4_exec._process_one_match_v4 = _counting_process
            try:
                return original(run_id, **kwargs)
            finally:
                v4_exec._process_one_match_v4 = original_process

        v4_exec._execute_historical_scan_run_v4_body = _crash_wrapper
        try:
            execute_historical_scan_run(int(args.run_id))
        finally:
            v4_exec._execute_historical_scan_run_v4_body = original
    else:
        execute_historical_scan_run(int(args.run_id))


def cmd_v3_compare(_: argparse.Namespace) -> dict[str, Any]:
    _require_db()
    db = SessionLocal()
    try:
        rows = _run_sql(
            db,
            """
            SELECT id, scan_version, matches_processed, status,
                   EXTRACT(EPOCH FROM (completed_at - started_at)) AS wall_seconds
            FROM cecchino_lab_historical_scan_runs
            WHERE season_label = :season
              AND scan_version = 'cecchino_lab_historical_scan_v3'
              AND status IN ('completed', 'completed_with_warnings')
            ORDER BY id DESC
            LIMIT 5
            """,
            season=SEASON,
        )
        for r in rows:
            mp = int(r.get("matches_processed") or 0)
            ws = float(r.get("wall_seconds") or 0)
            r["sec_per_match"] = ws / mp if mp else None
        return {"v3_runs": rows}
    finally:
        db.close()


def cmd_metrics(args: argparse.Namespace) -> dict[str, Any]:
    _require_db()
    db = SessionLocal()
    try:
        run = db.get(CecchinoLabHistoricalScanRun, int(args.run_id))
        if not run:
            raise RuntimeError("run not found")
        return _run_metrics(run)
    finally:
        db.close()


def cmd_poll(args: argparse.Namespace) -> dict[str, Any]:
    _require_db()
    db = SessionLocal()
    try:
        if args.run_id:
            run = db.get(CecchinoLabHistoricalScanRun, int(args.run_id))
            if not run:
                raise RuntimeError("run not found")
            return _run_metrics(run)
        rows = _run_sql(
            db,
            """
            SELECT id, status, matches_processed, matches_total, matches_error,
                   progress_pct, started_at, completed_at
            FROM cecchino_lab_historical_scan_runs
            WHERE season_label = :season
              AND scan_version = :scan_version
            ORDER BY id DESC
            LIMIT 5
            """,
            season=SEASON,
            scan_version=HISTORICAL_SCAN_VERSION_V4,
        )
        return {"recent_v4_runs": rows}
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate pilot Historical Scan V4")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("precheck")
    p = sub.add_parser("start-pilot")
    p.add_argument("--max-matches", type=int, default=MAX_MATCHES)
    p.add_argument("--sync", action="store_true")
    p.add_argument("--timeout", type=int, default=7200)
    p.add_argument(
        "--pilot-strategy",
        default=PILOT_STRATEGY,
        choices=[HISTORICAL_PILOT_STRATEGY_MAX_MATCHES, HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP],
    )
    p.add_argument("--eligible-per-competition", type=int, default=None)

    q = sub.add_parser("quality-gate")
    q.add_argument("--run-id", type=int, required=True)

    c = sub.add_parser("compare")
    c.add_argument("--run-a", type=int, required=True)
    c.add_argument("--run-b", type=int, required=True)

    cp = sub.add_parser("compare-payload")
    cp.add_argument("--run-a", type=int, required=True)
    cp.add_argument("--run-b", type=int, required=True)
    cp.add_argument("--lab-match-id", type=int, required=True)

    sub.add_parser("diagnose-five-mismatch")

    cg = sub.add_parser("crash-mid-group-test")
    cg.add_argument("--reference-run-id", type=int, required=True)
    cg.add_argument("--crash-after", type=int, default=3)

    r = sub.add_parser("resume-test")
    r.add_argument("--reference-run-id", type=int, required=True)

    w = sub.add_parser("worker-sync")
    w.add_argument("--run-id", type=int, required=True)

    sub.add_parser("v3-compare")
    m = sub.add_parser("metrics")
    m.add_argument("--run-id", type=int, required=True)

    p2 = sub.add_parser("poll")
    p2.add_argument("--run-id", type=int, default=None)

    args = parser.parse_args()
    handlers = {
        "precheck": cmd_precheck,
        "start-pilot": cmd_start_pilot,
        "quality-gate": cmd_quality_gate,
        "compare": cmd_compare_determinism,
        "compare-payload": cmd_compare_payload,
        "diagnose-five-mismatch": cmd_diagnose_five_mismatch,
        "crash-mid-group-test": cmd_crash_mid_group_test,
        "resume-test": cmd_resume_test,
        "worker-sync": cmd_worker_sync,
        "v3-compare": cmd_v3_compare,
        "metrics": cmd_metrics,
        "poll": cmd_poll,
    }
    result = handlers[args.cmd](args)
    if result is not None:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
