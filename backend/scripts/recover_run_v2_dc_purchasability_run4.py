"""Recovery plan + backup READ-ONLY per purchasability DC V2 su run_id=4.

Modes:
  plan    — artefatto recovery plan (18924 rows attese)
  backup  — dump lossless dei soli campi che un futuro WRITE toccherebbe

ZERO WRITE. Nessun mode apply in questo script.

Uso production (obbligatorio):
  /app/.venv/bin/python scripts/recover_run_v2_dc_purchasability_run4.py plan
  /app/.venv/bin/python scripts/recover_run_v2_dc_purchasability_run4.py backup
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

root = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(root / ".env")
    load_dotenv(root / ".env.local", override=True)
except Exception:
    pass

ON_RAILWAY = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    or os.environ.get("RAILWAY_SERVICE_NAME")
)

db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not db_url:
    print("SKIP: DATABASE_URL missing")
    raise SystemExit(2)
if "railway.internal" in db_url and not ON_RAILWAY:
    print("SKIP: railway.internal not reachable from local; run inside Railway")
    raise SystemExit(2)
os.environ["DATABASE_URL"] = db_url
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.models.cecchino_run_v2 import (
    OBSERVATION_LAYER_CORE_STRICT,
    CecchinoRunV2MarketResult,
    CecchinoRunV2MatchSnapshot,
    CecchinoRunV2Run,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_X_TWO,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision
from app.services.cecchino_data_lab.run_v2.purchasability_v2 import (
    SOURCE_DC_FAIR_V2,
    build_run_v2_purchasability,
)

RECOVERY_TYPE = "purchasability_dc_v2_fair_fix"
DC_KEYS = (SEL_ONE_X, SEL_ONE_TWO, SEL_X_TWO)
EXPECTED_SNAPSHOTS = 6308
EXPECTED_DC_PER_SNAPSHOT = 3
EXPECTED_PLAN_ROWS = EXPECTED_SNAPSHOTS * EXPECTED_DC_PER_SNAPSHOT


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _markets_by_key(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in (_as_dict(payload).get("markets") or []):
        if isinstance(m, dict) and m.get("market_key"):
            out[str(m["market_key"])] = m
    return out


def _item_reasons(item: dict[str, Any]) -> list[str]:
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    codes = gate.get("gate_reason_codes") or item.get("gate_reason_codes") or []
    if isinstance(codes, list):
        return [str(c) for c in codes]
    return []


def _before_dc_from_payload(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    batch = _as_dict(_as_dict(payload).get("engine_batch"))
    items = batch.get("items") if isinstance(batch.get("items"), list) else []
    by: dict[str, dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        mk = str(it.get("market_key") or "")
        if mk not in DC_KEYS:
            continue
        ref = it.get("reference") if isinstance(it.get("reference"), dict) else {}
        inp = it.get("input") if isinstance(it.get("input"), dict) else {}
        by[mk] = {
            "status": it.get("status"),
            "score": ref.get("score"),
            "class": ref.get("class"),
            "reason_codes": _item_reasons(it),
            "fair_probability": inp.get("fair_book_probability"),
        }
    if by:
        return by
    for mk, m in _markets_by_key(payload).items():
        if mk in DC_KEYS:
            by[mk] = {
                "status": m.get("status"),
                "score": m.get("score"),
                "class": m.get("class"),
                "reason_codes": list(m.get("gate_reason_codes") or []),
                "fair_probability": m.get("fair_book_probability"),
            }
    return by


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _default_out(kind: str, run_id: int) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{kind}_run{run_id}_{stamp}.json.gz"
    if ON_RAILWAY:
        return Path("/tmp") / name
    return Path(__file__).resolve().parents[2] / ".tmp_recovery_dc_run4" / name


def _open_session():
    engine = create_engine(db_url, pool_pre_ping=True)
    return sessionmaker(bind=engine)()


def _begin_readonly(db) -> None:
    db.execute(text("SET TRANSACTION READ ONLY, ISOLATION LEVEL REPEATABLE READ"))


def cmd_plan(args: argparse.Namespace) -> int:
    out_path = Path(args.out) if args.out else _default_out("recovery_plan", args.run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rev = resolve_code_revision()

    rows: list[dict[str, Any]] = []
    transitions = Counter()
    reason_before: Counter[str] = Counter()
    reason_after: Counter[str] = Counter()
    status_after: Counter[str] = Counter()
    errors: list[str] = []
    snaps_total = 0
    snaps_with_dc_mr = 0

    with _open_session() as db:
        _begin_readonly(db)
        run = db.get(CecchinoRunV2Run, args.run_id)
        if run is None:
            print(f"FAIL: run_id={args.run_id} non trovata")
            return 1

        snapshots = list(
            db.scalars(
                select(CecchinoRunV2MatchSnapshot)
                .where(CecchinoRunV2MatchSnapshot.run_id == args.run_id)
                .order_by(CecchinoRunV2MatchSnapshot.id)
            ).all()
        )
        snaps_total = len(snapshots)
        snap_ids = [int(s.id) for s in snapshots]

        mr_by_snap: dict[int, dict[str, CecchinoRunV2MarketResult]] = {
            sid: {} for sid in snap_ids
        }
        if snap_ids:
            # chunk to avoid oversized IN
            chunk = 500
            for i in range(0, len(snap_ids), chunk):
                part = snap_ids[i : i + chunk]
                mrs = db.scalars(
                    select(CecchinoRunV2MarketResult).where(
                        CecchinoRunV2MarketResult.match_snapshot_id.in_(part),
                        CecchinoRunV2MarketResult.observation_layer
                        == OBSERVATION_LAYER_CORE_STRICT,
                        CecchinoRunV2MarketResult.market_key.in_(list(DC_KEYS)),
                    )
                ).all()
                for mr in mrs:
                    mr_by_snap[int(mr.match_snapshot_id)][str(mr.market_key)] = mr

        for snap in snapshots:
            kpi = _as_dict(snap.kpi_json)
            qb = _as_dict(snap.quote_bundle_json)
            strict = (
                qb.get("strict_by_market")
                if isinstance(qb.get("strict_by_market"), dict)
                else {}
            )
            purch_before = _as_dict(snap.purchasability_json)
            before_dc = _before_dc_from_payload(purch_before)
            mr_map = mr_by_snap.get(int(snap.id)) or {}

            if len(mr_map) == EXPECTED_DC_PER_SNAPSHOT:
                snaps_with_dc_mr += 1

            match = SimpleNamespace(
                id=int(snap.lab_match_id),
                kickoff_at=snap.kickoff_at,
                home_team=snap.home_team,
                away_team=snap.away_team,
            )
            try:
                shadow = build_run_v2_purchasability(
                    kpi_panel=kpi,
                    match=match,
                    season_label=snap.season_label,
                    competition_name=snap.competition_name,
                    strict_by_market=strict,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"snap={snap.id}: {exc}")
                continue

            after_dc = _markets_by_key(shadow)
            for mk in DC_KEYS:
                old = before_dc.get(mk) or {}
                new = after_dc.get(mk) or {}
                mr = mr_map.get(mk)
                old_status = old.get("status")
                new_status = new.get("status")
                old_score = old.get("score")
                new_score = new.get("score")
                old_codes = list(old.get("reason_codes") or [])
                new_codes = list(new.get("gate_reason_codes") or [])
                for c in old_codes:
                    reason_before[str(c)] += 1
                for c in new_codes:
                    reason_after[str(c)] += 1
                if new_status:
                    status_after[str(new_status)] += 1
                if old_score is None and new_status == "score":
                    transitions["null_to_score"] += 1
                elif old_score is None and new_status == "gate_failed":
                    transitions["null_to_gate_failed"] += 1
                elif new_status == "not_calculable":
                    transitions["still_not_calculable"] += 1
                transitions[f"{old_status!s}->{new_status!s}"] += 1

                rows.append(
                    {
                        "match_snapshot_id": int(snap.id),
                        "market_result_id": int(mr.id) if mr is not None else None,
                        "market_key": mk,
                        "old_status": old_status,
                        "new_status": new_status,
                        "old_score": _jsonable(old_score),
                        "new_score": _jsonable(new.get("score")),
                        "old_class": old.get("class"),
                        "new_class": new.get("class"),
                        "old_reason_codes": old_codes,
                        "new_reason_codes": new_codes,
                        "old_fair_probability": _jsonable(old.get("fair_probability")),
                        "new_fair_probability": _jsonable(
                            new.get("fair_book_probability")
                        ),
                        "kickoff_at": snap.kickoff_at.isoformat()
                        if snap.kickoff_at
                        else None,
                        "lab_match_id": int(snap.lab_match_id),
                    }
                )

    plan_rows = len(rows)
    cardinality_ok = (
        snaps_total == EXPECTED_SNAPSHOTS
        and plan_rows == EXPECTED_PLAN_ROWS
        and snaps_with_dc_mr == EXPECTED_SNAPSHOTS
        and all(r.get("market_result_id") is not None for r in rows)
        and not errors
    )
    missing_mr = sum(1 for r in rows if r.get("market_result_id") is None)

    artifact = {
        "recovery_type": RECOVERY_TYPE,
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_PLAN",
        "writes": False,
        "on_railway": ON_RAILWAY,
        "code_sha": rev.get("git_commit"),
        "code_sha_source": rev.get("git_commit_source"),
        "railway_git_commit_sha": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
        "isolation": "READ ONLY, REPEATABLE READ",
        "dc_fair_probability_source": SOURCE_DC_FAIR_V2,
        "expected_cardinality": {
            "snapshots": EXPECTED_SNAPSHOTS,
            "dc_per_snapshot": EXPECTED_DC_PER_SNAPSHOT,
            "plan_rows": EXPECTED_PLAN_ROWS,
        },
        "snapshots_total": snaps_total,
        "snapshots_with_full_dc_market_results": snaps_with_dc_mr,
        "plan_rows": plan_rows,
        "missing_market_result_id": missing_mr,
        "cardinality_ok": cardinality_ok,
        "error_count": len(errors),
        "errors_sample": errors[:20],
        "transitions": dict(transitions),
        "status_after": dict(status_after),
        "top_reason_codes_before": reason_before.most_common(20),
        "top_reason_codes_after": reason_after.most_common(20),
        "rows": rows,
    }

    raw = json.dumps(artifact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9)
    out_path.write_bytes(compressed)
    sha = _sha256_bytes(compressed)

    summary = {
        "WROTE_PLAN": str(out_path),
        "PLAN_BYTES": len(compressed),
        "PLAN_ROWS": plan_rows,
        "PLAN_SHA256": sha,
        "SNAPSHOTS": snaps_total,
        "CARDINALITY_OK": cardinality_ok,
        "CODE_SHA": rev.get("git_commit"),
        "TRANSITIONS": dict(transitions),
        "STATUS_AFTER": dict(status_after),
        "ERROR_COUNT": len(errors),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if cardinality_ok else 1


def cmd_backup(args: argparse.Namespace) -> int:
    out_path = Path(args.out) if args.out else _default_out("recovery_backup", args.run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rev = resolve_code_revision()

    snapshot_rows: list[dict[str, Any]] = []
    market_rows: list[dict[str, Any]] = []

    with _open_session() as db:
        _begin_readonly(db)
        run = db.get(CecchinoRunV2Run, args.run_id)
        if run is None:
            print(f"FAIL: run_id={args.run_id} non trovata")
            return 1

        snapshots = list(
            db.scalars(
                select(CecchinoRunV2MatchSnapshot)
                .where(CecchinoRunV2MatchSnapshot.run_id == args.run_id)
                .order_by(CecchinoRunV2MatchSnapshot.id)
            ).all()
        )
        snap_ids = [int(s.id) for s in snapshots]
        for snap in snapshots:
            snapshot_rows.append(
                {
                    "snapshot_id": int(snap.id),
                    "old_purchasability_json": snap.purchasability_json,
                }
            )

        if snap_ids:
            chunk = 500
            for i in range(0, len(snap_ids), chunk):
                part = snap_ids[i : i + chunk]
                mrs = db.scalars(
                    select(CecchinoRunV2MarketResult)
                    .where(
                        CecchinoRunV2MarketResult.match_snapshot_id.in_(part),
                        CecchinoRunV2MarketResult.observation_layer
                        == OBSERVATION_LAYER_CORE_STRICT,
                        CecchinoRunV2MarketResult.market_key.in_(list(DC_KEYS)),
                    )
                    .order_by(
                        CecchinoRunV2MarketResult.match_snapshot_id,
                        CecchinoRunV2MarketResult.market_key,
                    )
                ).all()
                for mr in mrs:
                    market_rows.append(
                        {
                            "market_result_id": int(mr.id),
                            "match_snapshot_id": int(mr.match_snapshot_id),
                            "market_key": mr.market_key,
                            "old_buyability_score": _jsonable(mr.buyability_score),
                            "old_buyability_class": mr.buyability_class,
                        }
                    )

    snaps_n = len(snapshot_rows)
    mr_n = len(market_rows)
    cardinality_ok = snaps_n == EXPECTED_SNAPSHOTS and mr_n == EXPECTED_PLAN_ROWS

    artifact = {
        "recovery_type": RECOVERY_TYPE,
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_BACKUP",
        "writes": False,
        "on_railway": ON_RAILWAY,
        "code_sha": rev.get("git_commit"),
        "code_sha_source": rev.get("git_commit_source"),
        "railway_git_commit_sha": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
        "isolation": "READ ONLY, REPEATABLE READ",
        "fields_backed_up": [
            "cecchino_run_v2_match_snapshots.id",
            "cecchino_run_v2_match_snapshots.purchasability_json",
            "cecchino_run_v2_market_results.id",
            "cecchino_run_v2_market_results.buyability_score",
            "cecchino_run_v2_market_results.buyability_class",
        ],
        "expected_cardinality": {
            "snapshots": EXPECTED_SNAPSHOTS,
            "dc_market_rows": EXPECTED_PLAN_ROWS,
        },
        "snapshot_rows": snaps_n,
        "market_rows": mr_n,
        "cardinality_ok": cardinality_ok,
        "snapshots": snapshot_rows,
        "market_results": market_rows,
    }

    raw = json.dumps(artifact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9)
    out_path.write_bytes(compressed)
    sha = _sha256_bytes(compressed)

    summary = {
        "WROTE_BACKUP": str(out_path),
        "BACKUP_BYTES": len(compressed),
        "BACKUP_SNAPSHOT_ROWS": snaps_n,
        "BACKUP_MARKET_ROWS": mr_n,
        "BACKUP_SHA256": sha,
        "CARDINALITY_OK": cardinality_ok,
        "CODE_SHA": rev.get("git_commit"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if cardinality_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recovery plan/backup READ-ONLY (no apply) for run_id=4 DC V2"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Build recovery plan artifact (READ ONLY)")
    p_plan.add_argument("--run-id", type=int, default=4)
    p_plan.add_argument("--out", type=str, default="")
    p_plan.set_defaults(func=cmd_plan)

    p_bak = sub.add_parser("backup", help="Lossless pre-recovery backup (READ ONLY)")
    p_bak.add_argument("--run-id", type=int, default=4)
    p_bak.add_argument("--out", type=str, default="")
    p_bak.set_defaults(func=cmd_backup)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
