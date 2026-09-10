"""Recovery purchasability DC V2 su run_id=4.

Modes:
  plan       — artefatto recovery plan (18924 rows attese) READ ONLY
  backup     — dump lossless campi WRITE READ ONLY
  revalidate — shadow-lite + plan regen + pre-state vs backup (ZERO WRITE)
  apply      — UNA transazione atomica (richiede --confirm-apply + SHA gate)
  postverify — verifiche post-COMMIT (distribuzioni, leakage, checksum protetti)

Uso production:
  /app/.venv/bin/python scripts/recover_run_v2_dc_purchasability_run4.py plan
  /app/.venv/bin/python scripts/recover_run_v2_dc_purchasability_run4.py backup
  /app/.venv/bin/python scripts/recover_run_v2_dc_purchasability_run4.py revalidate \\
      --plan /path/recovery_plan_run4.json.gz \\
      --backup /path/recovery_backup_run4.json.gz \\
      --expected-plan-sha a757971e... \\
      --expected-backup-sha fc9f65e3... \\
      --expected-code-sha <deployed>
  /app/.venv/bin/python scripts/recover_run_v2_dc_purchasability_run4.py apply \\
      --confirm-apply --plan ... --backup ... \\
      --expected-plan-sha ... --expected-backup-sha ... --expected-code-sha ...
  /app/.venv/bin/python scripts/recover_run_v2_dc_purchasability_run4.py postverify \\
      --protected-checksum-pre <sha>
"""

from __future__ import annotations

import argparse
import copy
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

from sqlalchemy import create_engine, func, select, text
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
EXPECTED_MARKET_RESULTS = 107236
EXPECTED_DC_PER_SNAPSHOT = 3
EXPECTED_PLAN_ROWS = EXPECTED_SNAPSHOTS * EXPECTED_DC_PER_SNAPSHOT

EXPECTED_STATUS_AFTER = {
    "score": 1803,
    "gate_failed": 11443,
    "not_calculable": 5678,
}
EXPECTED_PER_MARKET = {
    SEL_ONE_X: {"score": 343, "gate_failed": 4071, "not_calculable": 1894},
    SEL_ONE_TWO: {"score": 353, "gate_failed": 4063, "not_calculable": 1892},
    SEL_X_TWO: {"score": 1107, "gate_failed": 3309, "not_calculable": 1892},
}
EXPECTED_MISSING_FAIR_DC_REAL = 21

FROZEN_PLAN_SHA = "a757971e2b1197b61f24d00a929bf882585004f76dcef9e4b6952ec8ea59555a"
FROZEN_BACKUP_SHA = "fc9f65e3f25631fa8e7c2add7eceb1a81931f2d73e273c4caa3d94e257745b75"

PROTECTED_SNAPSHOT_FIELDS = (
    "kpi_json",
    "signals_json",
    "balance_v5_json",
    "goal_intensity_json",
    "eligibility_status",
    "eligibility_reason",
    "quote_bundle_json",
    "cecchino_output_json",
    "actuals_json",
)


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


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json_sha(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return _sha256_bytes(raw)


def _load_gzip_json(path: Path) -> dict[str, Any]:
    payload = json.loads(gzip.decompress(path.read_bytes()))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact non-dict: {path}")
    return payload


def _scores_equal(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return a == b


def _norm_score_for_db(v: Any) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(float(v)))


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


def _code_sha() -> str | None:
    rev = resolve_code_revision()
    return rev.get("git_commit") or os.environ.get("RAILWAY_GIT_COMMIT_SHA")


def _count_run_card(db, run_id: int) -> tuple[int, int]:
    snaps = int(
        db.execute(
            select(func.count())
            .select_from(CecchinoRunV2MatchSnapshot)
            .where(CecchinoRunV2MatchSnapshot.run_id == run_id)
        ).scalar_one()
    )
    mrs = int(
        db.execute(
            select(func.count())
            .select_from(CecchinoRunV2MarketResult)
            .where(CecchinoRunV2MarketResult.run_id == run_id)
        ).scalar_one()
    )
    return snaps, mrs


def _protected_checksum(db, run_id: int) -> str:
    """Hash deterministico dei campi protetti (non buyability DC)."""
    h = hashlib.sha256()
    snapshots = db.scalars(
        select(CecchinoRunV2MatchSnapshot)
        .where(CecchinoRunV2MatchSnapshot.run_id == run_id)
        .order_by(CecchinoRunV2MatchSnapshot.id)
    ).all()
    for snap in snapshots:
        h.update(f"S:{snap.id}\n".encode())
        for field in PROTECTED_SNAPSHOT_FIELDS:
            val = getattr(snap, field, None)
            h.update(field.encode())
            h.update(b"=")
            h.update(
                json.dumps(val, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str).encode(
                    "utf-8"
                )
            )
            h.update(b"\n")
    mrs = db.scalars(
        select(CecchinoRunV2MarketResult)
        .where(CecchinoRunV2MarketResult.run_id == run_id)
        .order_by(CecchinoRunV2MarketResult.id)
    ).all()
    for mr in mrs:
        h.update(f"M:{mr.id}:{mr.market_key}:{mr.observation_layer}\n".encode())
        for field in (
            "probability",
            "is_predicted_selection",
            "prediction",
            "quota_book",
            "prob_book_raw",
            "prob_book_fair",
            "is_real_quote",
            "is_derived_quote",
            "derivation_method",
            "quote_source",
            "source_column",
            "quote_snapshot_type",
            "outcome",
            "won",
            "flat_stake_profit",
            "kpi_rating",
            "edge_pct",
            "vantaggio_prob",
            "signal_active",
            "equilibrium_state",
            "goal_intensity_score",
        ):
            val = getattr(mr, field, None)
            h.update(f"{field}={_jsonable(val)}\n".encode())
        # buyability non-DC entra nel checksum protetto; DC escluso (verra' scritto).
        if str(mr.market_key) not in DC_KEYS or mr.observation_layer != OBSERVATION_LAYER_CORE_STRICT:
            h.update(
                f"buyability_score={_jsonable(mr.buyability_score)};"
                f"buyability_class={mr.buyability_class}\n".encode()
            )
    return h.hexdigest()


def _patch_purchasability_dc(
    old_payload: dict[str, Any] | None, shadow: dict[str, Any]
) -> dict[str, Any]:
    out = copy.deepcopy(_as_dict(old_payload))
    shadow_dc = {mk: m for mk, m in _markets_by_key(shadow).items() if mk in DC_KEYS}

    markets = list(out.get("markets") or [])
    replaced: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in markets:
        if not isinstance(m, dict):
            continue
        mk = str(m.get("market_key") or "")
        if mk in shadow_dc:
            replaced.append(copy.deepcopy(shadow_dc[mk]))
            seen.add(mk)
        else:
            replaced.append(m)
    for mk, compact in shadow_dc.items():
        if mk not in seen:
            replaced.append(copy.deepcopy(compact))
    out["markets"] = replaced

    eb = out.get("engine_batch")
    if isinstance(eb, dict) and isinstance(eb.get("items"), list):
        new_items: list[Any] = []
        for it in eb["items"]:
            if not isinstance(it, dict):
                new_items.append(it)
                continue
            mk = str(it.get("market_key") or "")
            if mk not in shadow_dc:
                new_items.append(it)
                continue
            m = shadow_dc[mk]
            it2 = copy.deepcopy(it)
            it2["status"] = m.get("status")
            it2["gate_status"] = m.get("gate_status")
            ref = it2.get("reference") if isinstance(it2.get("reference"), dict) else {}
            ref = dict(ref)
            ref["score"] = m.get("score")
            ref["class"] = m.get("class")
            it2["reference"] = ref
            gate = it2.get("gate") if isinstance(it2.get("gate"), dict) else {}
            gate = dict(gate)
            gate["gate_reason_codes"] = list(m.get("gate_reason_codes") or [])
            it2["gate"] = gate
            it2["gate_reason_codes"] = list(m.get("gate_reason_codes") or [])
            inp = it2.get("input") if isinstance(it2.get("input"), dict) else {}
            inp = dict(inp)
            inp["fair_book_probability"] = m.get("fair_book_probability")
            it2["input"] = inp
            new_items.append(it2)
        eb = dict(eb)
        eb["items"] = new_items
        out["engine_batch"] = eb

    out["run_v2_dc_fair_strict_overlay"] = True
    out["dc_fair_probability_source"] = SOURCE_DC_FAIR_V2
    return out


def _build_plan_rows(db, run_id: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stessa logica di cmd_plan; ritorna (rows, meta)."""
    rows: list[dict[str, Any]] = []
    transitions: Counter[str] = Counter()
    reason_before: Counter[str] = Counter()
    reason_after: Counter[str] = Counter()
    status_after: Counter[str] = Counter()
    errors: list[str] = []
    snaps_with_dc_mr = 0

    snapshots = list(
        db.scalars(
            select(CecchinoRunV2MatchSnapshot)
            .where(CecchinoRunV2MatchSnapshot.run_id == run_id)
            .order_by(CecchinoRunV2MatchSnapshot.id)
        ).all()
    )
    snaps_total = len(snapshots)
    snap_ids = [int(s.id) for s in snapshots]
    mr_by_snap: dict[int, dict[str, CecchinoRunV2MarketResult]] = {sid: {} for sid in snap_ids}
    if snap_ids:
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
            qb.get("strict_by_market") if isinstance(qb.get("strict_by_market"), dict) else {}
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
                    "new_fair_probability": _jsonable(new.get("fair_book_probability")),
                    "kickoff_at": snap.kickoff_at.isoformat() if snap.kickoff_at else None,
                    "lab_match_id": int(snap.lab_match_id),
                }
            )

    meta = {
        "snapshots_total": snaps_total,
        "snapshots_with_full_dc_market_results": snaps_with_dc_mr,
        "plan_rows": len(rows),
        "missing_market_result_id": sum(1 for r in rows if r.get("market_result_id") is None),
        "error_count": len(errors),
        "errors_sample": errors[:20],
        "transitions": dict(transitions),
        "status_after": dict(status_after),
        "top_reason_codes_before": reason_before.most_common(20),
        "top_reason_codes_after": reason_after.most_common(20),
        "cardinality_ok": (
            snaps_total == EXPECTED_SNAPSHOTS
            and len(rows) == EXPECTED_PLAN_ROWS
            and snaps_with_dc_mr == EXPECTED_SNAPSHOTS
            and all(r.get("market_result_id") is not None for r in rows)
            and not errors
        ),
    }
    return rows, meta


def _verify_artifact_gates(
    *,
    plan_path: Path,
    backup_path: Path,
    expected_plan_sha: str,
    expected_backup_sha: str,
    expected_code_sha: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    rev = resolve_code_revision()
    code = rev.get("git_commit") or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    railway = os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    plan_sha = _sha256_file(plan_path)
    backup_sha = _sha256_file(backup_path)
    plan = _load_gzip_json(plan_path)
    backup = _load_gzip_json(backup_path)

    failures: list[str] = []
    if code != expected_code_sha:
        failures.append(f"code_sha={code} != expected={expected_code_sha}")
    if railway and railway != expected_code_sha:
        failures.append(f"RAILWAY_GIT_COMMIT_SHA={railway} != expected={expected_code_sha}")
    if plan_sha != expected_plan_sha:
        failures.append(f"plan_file_sha={plan_sha} != expected={expected_plan_sha}")
    if backup_sha != expected_backup_sha:
        failures.append(f"backup_file_sha={backup_sha} != expected={expected_backup_sha}")
    if plan.get("recovery_type") != RECOVERY_TYPE:
        failures.append("plan recovery_type mismatch")
    if backup.get("recovery_type") != RECOVERY_TYPE:
        failures.append("backup recovery_type mismatch")
    if int(plan.get("run_id") or -1) != 4 or int(backup.get("run_id") or -1) != 4:
        failures.append("run_id != 4")
    if int(plan.get("plan_rows") or -1) != EXPECTED_PLAN_ROWS:
        failures.append(f"plan_rows={plan.get('plan_rows')}")
    if len(plan.get("rows") or []) != EXPECTED_PLAN_ROWS:
        failures.append("plan rows len mismatch")
    if int(backup.get("snapshot_rows") or -1) != EXPECTED_SNAPSHOTS:
        failures.append("backup snapshot_rows mismatch")
    if int(backup.get("market_rows") or -1) != EXPECTED_PLAN_ROWS:
        failures.append("backup market_rows mismatch")

    gate = {
        "code_sha": code,
        "railway_git_commit_sha": railway,
        "expected_code_sha": expected_code_sha,
        "plan_sha": plan_sha,
        "backup_sha": backup_sha,
        "failures": failures,
        "ok": not failures,
    }
    return plan, backup, gate


def _prestate_matches_backup(
    db, backup: dict[str, Any], plan: dict[str, Any]
) -> dict[str, Any]:
    snap_bak = {
        int(r["snapshot_id"]): r.get("old_purchasability_json")
        for r in (backup.get("snapshots") or [])
    }
    mr_bak = {
        int(r["market_result_id"]): r
        for r in (backup.get("market_results") or [])
    }
    mismatches = 0
    samples: list[str] = []

    for sid, old_purch in snap_bak.items():
        snap = db.get(CecchinoRunV2MatchSnapshot, sid)
        if snap is None:
            mismatches += 1
            if len(samples) < 10:
                samples.append(f"missing snapshot {sid}")
            continue
        cur = snap.purchasability_json
        if json.dumps(cur, sort_keys=True, default=str) != json.dumps(
            old_purch, sort_keys=True, default=str
        ):
            mismatches += 1
            if len(samples) < 10:
                samples.append(f"purchasability drift snap={sid}")

    for mid, row in mr_bak.items():
        mr = db.get(CecchinoRunV2MarketResult, mid)
        if mr is None:
            mismatches += 1
            if len(samples) < 10:
                samples.append(f"missing mr {mid}")
            continue
        if not _scores_equal(mr.buyability_score, row.get("old_buyability_score")):
            mismatches += 1
            if len(samples) < 10:
                samples.append(f"score drift mr={mid}")
            continue
        if (mr.buyability_class or None) != (row.get("old_buyability_class") or None):
            mismatches += 1
            if len(samples) < 10:
                samples.append(f"class drift mr={mid}")

    # plan old_* vs current payload/MR
    for r in plan.get("rows") or []:
        sid = int(r["match_snapshot_id"])
        snap = db.get(CecchinoRunV2MatchSnapshot, sid)
        if snap is None:
            mismatches += 1
            continue
        before = _before_dc_from_payload(_as_dict(snap.purchasability_json)).get(
            str(r["market_key"])
        ) or {}
        if before.get("status") != r.get("old_status"):
            mismatches += 1
            if len(samples) < 10:
                samples.append(
                    f"plan old_status drift snap={sid} mk={r['market_key']}"
                )
            continue
        if not _scores_equal(before.get("score"), r.get("old_score")):
            mismatches += 1
            if len(samples) < 10:
                samples.append(f"plan old_score drift snap={sid} mk={r['market_key']}")
            continue
        if (before.get("class") or None) != (r.get("old_class") or None):
            mismatches += 1
            if len(samples) < 10:
                samples.append(f"plan old_class drift snap={sid} mk={r['market_key']}")

    return {
        "ok": mismatches == 0,
        "mismatches": mismatches,
        "samples": samples,
        "backup_snapshots": len(snap_bak),
        "backup_market_results": len(mr_bak),
    }


def cmd_plan(args: argparse.Namespace) -> int:
    out_path = Path(args.out) if args.out else _default_out("recovery_plan", args.run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rev = resolve_code_revision()

    with _open_session() as db:
        _begin_readonly(db)
        run = db.get(CecchinoRunV2Run, args.run_id)
        if run is None:
            print(f"FAIL: run_id={args.run_id} non trovata")
            return 1
        rows, meta = _build_plan_rows(db, args.run_id)

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
        "snapshots_total": meta["snapshots_total"],
        "snapshots_with_full_dc_market_results": meta[
            "snapshots_with_full_dc_market_results"
        ],
        "plan_rows": meta["plan_rows"],
        "missing_market_result_id": meta["missing_market_result_id"],
        "cardinality_ok": meta["cardinality_ok"],
        "error_count": meta["error_count"],
        "errors_sample": meta["errors_sample"],
        "transitions": meta["transitions"],
        "status_after": meta["status_after"],
        "top_reason_codes_before": meta["top_reason_codes_before"],
        "top_reason_codes_after": meta["top_reason_codes_after"],
        "rows": rows,
    }

    raw = json.dumps(artifact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9)
    out_path.write_bytes(compressed)
    sha = _sha256_bytes(compressed)
    rows_sha = _canonical_json_sha(rows)

    summary = {
        "WROTE_PLAN": str(out_path),
        "PLAN_BYTES": len(compressed),
        "PLAN_ROWS": meta["plan_rows"],
        "PLAN_SHA256": sha,
        "PLAN_ROWS_CONTENT_SHA256": rows_sha,
        "SNAPSHOTS": meta["snapshots_total"],
        "CARDINALITY_OK": meta["cardinality_ok"],
        "CODE_SHA": rev.get("git_commit"),
        "TRANSITIONS": meta["transitions"],
        "STATUS_AFTER": meta["status_after"],
        "ERROR_COUNT": meta["error_count"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if meta["cardinality_ok"] else 1


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


def cmd_revalidate(args: argparse.Namespace) -> int:
    """ZERO WRITE: confronta plan rigenerato (rows) col freeze + pre-state backup."""
    plan_path = Path(args.plan)
    backup_path = Path(args.backup)
    expected_plan_sha = args.expected_plan_sha or FROZEN_PLAN_SHA
    expected_backup_sha = args.expected_backup_sha or FROZEN_BACKUP_SHA
    expected_code_sha = args.expected_code_sha
    if not expected_code_sha:
        print("FAIL: --expected-code-sha obbligatorio")
        return 1

    frozen_plan, backup, gate = _verify_artifact_gates(
        plan_path=plan_path,
        backup_path=backup_path,
        expected_plan_sha=expected_plan_sha,
        expected_backup_sha=expected_backup_sha,
        expected_code_sha=expected_code_sha,
    )
    if not gate["ok"]:
        print(json.dumps({"REVALIDATE": "FAIL", "gate": gate}, indent=2, ensure_ascii=False))
        return 1

    frozen_rows_sha = _canonical_json_sha(frozen_plan.get("rows") or [])

    with _open_session() as db:
        _begin_readonly(db)
        run = db.get(CecchinoRunV2Run, args.run_id)
        if run is None:
            print("FAIL: run missing")
            return 1
        snaps_n, mrs_n = _count_run_card(db, args.run_id)
        rows, meta = _build_plan_rows(db, args.run_id)
        prestate = _prestate_matches_backup(db, backup, frozen_plan)
        protected_pre = _protected_checksum(db, args.run_id)

    regen_rows_sha = _canonical_json_sha(rows)
    rows_match = regen_rows_sha == frozen_rows_sha
    status_match = dict(meta.get("status_after") or {}) == dict(
        frozen_plan.get("status_after") or {}
    )
    # Transizioni chiave freeze
    tr = meta.get("transitions") or {}
    transitions_match = (
        int(tr.get("null_to_score") or 0) == 1803
        and int(tr.get("null_to_gate_failed") or 0) == 11443
        and int(tr.get("still_not_calculable") or 0) == 5678
    )
    card_ok = (
        snaps_n == EXPECTED_SNAPSHOTS
        and mrs_n == EXPECTED_MARKET_RESULTS
        and meta.get("cardinality_ok") is True
    )

    # Nota: il gzip completo rigenerato NON puo' eguagliare a757971e perche'
    # include generated_at + code_sha nuovi. Il gate di identita' e' sul contenuto
    # rows (+ status/transitions) e sul file congelato usato per apply (= a757971e).
    ok = (
        card_ok
        and rows_match
        and status_match
        and transitions_match
        and prestate.get("ok") is True
        and gate["ok"]
    )
    summary = {
        "REVALIDATE": "OK" if ok else "FAIL",
        "writes": False,
        "gate": gate,
        "cardinality": {
            "snapshots": snaps_n,
            "market_results": mrs_n,
            "plan_rows": meta.get("plan_rows"),
            "ok": card_ok,
        },
        "frozen_plan_file_sha": expected_plan_sha,
        "frozen_plan_rows_content_sha": frozen_rows_sha,
        "regenerated_plan_rows_content_sha": regen_rows_sha,
        "plan_rows_content_match": rows_match,
        "status_after_match": status_match,
        "transitions_match": transitions_match,
        "status_after": meta.get("status_after"),
        "transitions": {
            "null_to_score": tr.get("null_to_score"),
            "null_to_gate_failed": tr.get("null_to_gate_failed"),
            "still_not_calculable": tr.get("still_not_calculable"),
        },
        "prestate": prestate,
        "protected_checksum_pre": protected_pre,
        "note": (
            "Apply deve usare il file plan congelato (SHA a757971e). "
            "Il gzip rigenerato cambia per metadata volatile; "
            "il gate e' rows_content_sha + status/transitions + prestate."
        ),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def cmd_apply(args: argparse.Namespace) -> int:
    if not args.confirm_apply:
        print("FAIL: serve --confirm-apply")
        return 1
    plan_path = Path(args.plan)
    backup_path = Path(args.backup)
    expected_plan_sha = args.expected_plan_sha or FROZEN_PLAN_SHA
    expected_backup_sha = args.expected_backup_sha or FROZEN_BACKUP_SHA
    expected_code_sha = args.expected_code_sha
    if not expected_code_sha:
        print("FAIL: --expected-code-sha obbligatorio")
        return 1

    plan, backup, gate = _verify_artifact_gates(
        plan_path=plan_path,
        backup_path=backup_path,
        expected_plan_sha=expected_plan_sha,
        expected_backup_sha=expected_backup_sha,
        expected_code_sha=expected_code_sha,
    )
    if not gate["ok"]:
        print(json.dumps({"APPLY": "STOP", "gate": gate}, indent=2, ensure_ascii=False))
        return 1

    plan_by_snap: dict[int, dict[str, dict[str, Any]]] = {}
    for r in plan.get("rows") or []:
        sid = int(r["match_snapshot_id"])
        plan_by_snap.setdefault(sid, {})[str(r["market_key"])] = r

    snap_ids_ordered = sorted(plan_by_snap.keys())
    if len(snap_ids_ordered) != EXPECTED_SNAPSHOTS:
        print(
            json.dumps(
                {
                    "APPLY": "STOP",
                    "reason": "plan snapshot cardinality",
                    "n": len(snap_ids_ordered),
                },
                indent=2,
            )
        )
        return 1

    updated_snaps = 0
    updated_mrs = 0
    protected_pre = None

    db = _open_session()
    try:
        # Transazione WRITE unica
        run = db.get(CecchinoRunV2Run, args.run_id)
        if run is None:
            raise RuntimeError("run missing")

        snaps_n, mrs_n = _count_run_card(db, args.run_id)
        if snaps_n != EXPECTED_SNAPSHOTS or mrs_n != EXPECTED_MARKET_RESULTS:
            raise RuntimeError(f"cardinality snaps={snaps_n} mrs={mrs_n}")

        prestate = _prestate_matches_backup(db, backup, plan)
        if not prestate.get("ok"):
            raise RuntimeError(f"prestate mismatch: {prestate}")

        protected_pre = _protected_checksum(db, args.run_id)

        # Lock stabile
        snapshots = list(
            db.scalars(
                select(CecchinoRunV2MatchSnapshot)
                .where(CecchinoRunV2MatchSnapshot.run_id == args.run_id)
                .order_by(CecchinoRunV2MatchSnapshot.id)
                .with_for_update()
            ).all()
        )
        if len(snapshots) != EXPECTED_SNAPSHOTS:
            raise RuntimeError("snapshot lock cardinality")

        snap_ids = [int(s.id) for s in snapshots]
        mr_by_snap: dict[int, dict[str, CecchinoRunV2MarketResult]] = {
            sid: {} for sid in snap_ids
        }
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
                .with_for_update()
            ).all()
            for mr in mrs:
                mr_by_snap[int(mr.match_snapshot_id)][str(mr.market_key)] = mr

        for snap in snapshots:
            sid = int(snap.id)
            plan_dc = plan_by_snap.get(sid) or {}
            if set(plan_dc.keys()) != set(DC_KEYS):
                raise RuntimeError(f"plan DC keys incomplete snap={sid}")

            kpi = _as_dict(snap.kpi_json)
            qb = _as_dict(snap.quote_bundle_json)
            strict = (
                qb.get("strict_by_market")
                if isinstance(qb.get("strict_by_market"), dict)
                else {}
            )
            match = SimpleNamespace(
                id=int(snap.lab_match_id),
                kickoff_at=snap.kickoff_at,
                home_team=snap.home_team,
                away_team=snap.away_team,
            )
            shadow = build_run_v2_purchasability(
                kpi_panel=kpi,
                match=match,
                season_label=snap.season_label,
                competition_name=snap.competition_name,
                strict_by_market=strict,
            )
            after_dc = _markets_by_key(shadow)
            for mk in DC_KEYS:
                prow = plan_dc[mk]
                new = after_dc.get(mk) or {}
                if new.get("status") != prow.get("new_status"):
                    raise RuntimeError(
                        f"status mismatch snap={sid} mk={mk} "
                        f"{new.get('status')}!={prow.get('new_status')}"
                    )
                if not _scores_equal(new.get("score"), prow.get("new_score")):
                    raise RuntimeError(f"score mismatch snap={sid} mk={mk}")
                if (new.get("class") or None) != (prow.get("new_class") or None):
                    raise RuntimeError(f"class mismatch snap={sid} mk={mk}")

            snap.purchasability_json = _patch_purchasability_dc(
                snap.purchasability_json, shadow
            )
            updated_snaps += 1

            mr_map = mr_by_snap.get(sid) or {}
            for mk in DC_KEYS:
                mr = mr_map.get(mk)
                if mr is None:
                    raise RuntimeError(f"missing MR snap={sid} mk={mk}")
                prow = plan_dc[mk]
                new = after_dc.get(mk) or {}
                mr.buyability_score = _norm_score_for_db(new.get("score"))
                mr.buyability_class = new.get("class")
                # sanity vs plan
                if not _scores_equal(mr.buyability_score, prow.get("new_score")):
                    raise RuntimeError(f"mr score!=plan snap={sid} mk={mk}")
                if (mr.buyability_class or None) != (prow.get("new_class") or None):
                    raise RuntimeError(f"mr class!=plan snap={sid} mk={mk}")
                updated_mrs += 1

        db.commit()
        committed = True
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(
            json.dumps(
                {
                    "APPLY": "ROLLBACK",
                    "error": str(exc),
                    "committed": False,
                    "gate": gate,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        db.close()
        return 1
    finally:
        if db.is_active:
            pass

    db.close()
    summary = {
        "APPLY": "COMMITTED",
        "committed": True,
        "updated_snapshots": updated_snaps,
        "updated_market_results": updated_mrs,
        "protected_checksum_pre": protected_pre,
        "code_sha": gate.get("code_sha"),
        "plan_sha": gate.get("plan_sha"),
        "backup_sha": gate.get("backup_sha"),
        "recovery_type": RECOVERY_TYPE,
        "run_id": args.run_id,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _dc_status_distribution(db, run_id: int) -> dict[str, Any]:
    per_market: dict[str, Counter[str]] = {mk: Counter() for mk in DC_KEYS}
    missing_fair_real = 0
    snapshots = db.scalars(
        select(CecchinoRunV2MatchSnapshot)
        .where(CecchinoRunV2MatchSnapshot.run_id == run_id)
        .order_by(CecchinoRunV2MatchSnapshot.id)
    ).all()
    for snap in snapshots:
        markets = _markets_by_key(_as_dict(snap.purchasability_json))
        qb = _as_dict(snap.quote_bundle_json)
        strict = (
            qb.get("strict_by_market") if isinstance(qb.get("strict_by_market"), dict) else {}
        )
        for mk in DC_KEYS:
            m = markets.get(mk) or {}
            st = str(m.get("status") or "missing")
            per_market[mk][st] += 1
            reasons = list(m.get("gate_reason_codes") or [])
            sq = strict.get(mk) if isinstance(strict.get(mk), dict) else {}
            is_real = bool(sq.get("is_real_quote")) and not bool(sq.get("is_derived"))
            if is_real and "missing_fair_book_probability" in reasons:
                missing_fair_real += 1
    totals: Counter[str] = Counter()
    out_per = {}
    for mk, ctr in per_market.items():
        out_per[mk] = dict(ctr)
        totals.update(ctr)
    return {
        "per_market": out_per,
        "totals": dict(totals),
        "missing_fair_book_probability_dc_real": missing_fair_real,
    }


def cmd_postverify(args: argparse.Namespace) -> int:
    with _open_session() as db:
        _begin_readonly(db)
        run = db.get(CecchinoRunV2Run, args.run_id)
        if run is None:
            print("FAIL: run missing")
            return 1
        snaps_n, mrs_n = _count_run_card(db, args.run_id)
        protected_post = _protected_checksum(db, args.run_id)
        dist = _dc_status_distribution(db, args.run_id)
        leakage = int(run.leakage_violations or 0)

    expected_code = args.expected_code_sha
    code = _code_sha()
    failures: list[str] = []
    if snaps_n != EXPECTED_SNAPSHOTS:
        failures.append(f"snapshots={snaps_n}")
    if mrs_n != EXPECTED_MARKET_RESULTS:
        failures.append(f"market_results={mrs_n}")
    if leakage != 0:
        failures.append(f"leakage_violations={leakage}")
    if expected_code and code != expected_code:
        failures.append(f"code_sha={code}")
    if args.protected_checksum_pre and protected_post != args.protected_checksum_pre:
        failures.append("protected_checksum_changed")

    totals = dist.get("totals") or {}
    for k, v in EXPECTED_STATUS_AFTER.items():
        if int(totals.get(k) or 0) != v:
            failures.append(f"total {k}={totals.get(k)} expected {v}")
    for mk, exp in EXPECTED_PER_MARKET.items():
        got = dist.get("per_market", {}).get(mk) or {}
        for st, n in exp.items():
            if int(got.get(st) or 0) != n:
                failures.append(f"{mk}.{st}={got.get(st)} expected {n}")
    if int(dist.get("missing_fair_book_probability_dc_real") or -1) != EXPECTED_MISSING_FAIR_DC_REAL:
        failures.append(
            f"missing_fair_dc_real={dist.get('missing_fair_book_probability_dc_real')}"
        )

    ok = not failures
    summary = {
        "POSTVERIFY": "OK" if ok else "FAIL",
        "failures": failures,
        "snapshots": snaps_n,
        "market_results": mrs_n,
        "leakage_violations": leakage,
        "distribution": dist,
        "protected_checksum_pre": args.protected_checksum_pre,
        "protected_checksum_post": protected_post,
        "protected_checksum_match": (
            (not args.protected_checksum_pre)
            or protected_post == args.protected_checksum_pre
        ),
        "code_sha": code,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recovery DC V2 run_id=4 (plan/backup/revalidate/apply/postverify)"
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

    p_rev = sub.add_parser(
        "revalidate",
        help="READ ONLY: regen plan rows vs freeze + pre-state vs backup",
    )
    p_rev.add_argument("--run-id", type=int, default=4)
    p_rev.add_argument("--plan", type=str, required=True)
    p_rev.add_argument("--backup", type=str, required=True)
    p_rev.add_argument("--expected-plan-sha", type=str, default=FROZEN_PLAN_SHA)
    p_rev.add_argument("--expected-backup-sha", type=str, default=FROZEN_BACKUP_SHA)
    p_rev.add_argument("--expected-code-sha", type=str, required=True)
    p_rev.set_defaults(func=cmd_revalidate)

    p_app = sub.add_parser("apply", help="Atomic WRITE (requires --confirm-apply)")
    p_app.add_argument("--run-id", type=int, default=4)
    p_app.add_argument("--plan", type=str, required=True)
    p_app.add_argument("--backup", type=str, required=True)
    p_app.add_argument("--expected-plan-sha", type=str, default=FROZEN_PLAN_SHA)
    p_app.add_argument("--expected-backup-sha", type=str, default=FROZEN_BACKUP_SHA)
    p_app.add_argument("--expected-code-sha", type=str, required=True)
    p_app.add_argument("--confirm-apply", action="store_true")
    p_app.set_defaults(func=cmd_apply)

    p_post = sub.add_parser("postverify", help="Post-COMMIT verification")
    p_post.add_argument("--run-id", type=int, default=4)
    p_post.add_argument("--expected-code-sha", type=str, default="")
    p_post.add_argument("--protected-checksum-pre", type=str, default="")
    p_post.set_defaults(func=cmd_postverify)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
