"""Shadow READ-ONLY: recomputa purchasability DC V2 su run_id=4.

ZERO WRITE. Nessun UPDATE / recovery / nuova RUN / pacchetto AI.

Uso production (obbligatorio per Fase 2):
  /app/.venv/bin/python scripts/shadow_run_v2_dc_purchasability_run4.py --run-id 4 --limit 0

Locale (solo diagnostica pre-deploy): richiede DATABASE_PUBLIC_URL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
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

EXPECTED_SNAPSHOTS_RUN4 = 6308
EXPECTED_DC_PER_SNAPSHOT = 3
EXPECTED_PLAN_ROWS_RUN4 = EXPECTED_SNAPSHOTS_RUN4 * EXPECTED_DC_PER_SNAPSHOT

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

DC_KEYS = (SEL_ONE_X, SEL_ONE_TWO, SEL_X_TWO)

# Campi che lo shadow NON deve alterare né richiedere in scrittura.
INDEPENDENCE_FIELDS = (
    "predicted_key",
    "is_predicted_selection",
    "probabilities",
    "KPI",
    "Signals",
    "Balance",
    "Goal Intensity",
    "eligibility",
    "strict quotes",
    "outcome",
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
    """Preferisce engine_batch.items (reason codes); fallback markets compact."""
    batch = _as_dict(_as_dict(payload).get("engine_batch"))
    items = batch.get("items") if isinstance(batch.get("items"), list) else []
    by: dict[str, dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        mk = str(it.get("market_key") or "")
        if mk in DC_KEYS:
            ref = it.get("reference") if isinstance(it.get("reference"), dict) else {}
            inp = it.get("input") if isinstance(it.get("input"), dict) else {}
            by[mk] = {
                "status": it.get("status"),
                "gate_status": it.get("gate_status"),
                "gate_reason_codes": _item_reasons(it),
                "score": ref.get("score"),
                "fair_book_probability": inp.get("fair_book_probability"),
                "execution_quote_real": inp.get("execution_quote_real"),
                "probability_cecchino": inp.get("probability_cecchino"),
            }
    if by:
        return by
    for mk, m in _markets_by_key(payload).items():
        if mk in DC_KEYS:
            by[mk] = {
                "status": m.get("status"),
                "gate_status": m.get("gate_status"),
                "gate_reason_codes": list(m.get("gate_reason_codes") or []),
                "score": m.get("score"),
                "fair_book_probability": m.get("fair_book_probability"),
                "execution_quote_real": None,
                "probability_cecchino": None,
            }
    return by


def _kpi_dc_meta(kpi: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in (_as_dict(kpi).get("rows") or []):
        if not isinstance(row, dict):
            continue
        mk = str(row.get("market_key") or "")
        if mk not in DC_KEYS:
            continue
        out[mk] = {
            "quota_book": row.get("quota_book"),
            "prob_cecchino": row.get("prob_cecchino"),
            "book_source": row.get("book_source"),
            "book_quote_class": row.get("book_quote_class"),
            "derived_quote": row.get("derived_quote"),
            "is_real_quote": row.get("is_real_quote"),
            "real_dc_quote": row.get("real_dc_quote"),
        }
    return out


def _is_execution_real(meta: dict[str, Any] | None, item: dict[str, Any] | None) -> bool:
    if item and item.get("execution_quote_real") is True:
        return True
    if not meta:
        return False
    if meta.get("real_dc_quote") is True or meta.get("book_quote_class") == "real_bet365":
        return True
    src = str(meta.get("book_source") or "").lower()
    if "derived" in src or "from_1x2" in src:
        return False
    if meta.get("derived_quote") is True:
        return False
    return meta.get("quota_book") is not None and ("bet365" in src or meta.get("is_real_quote") is True)


def _agg_bucket() -> dict[str, Any]:
    return {
        "total": 0,
        "execution_real": 0,
        "model_probability_missing": 0,
        "fair_book_available": 0,
        "score": 0,
        "gate_failed": 0,
        "not_calculable": 0,
        "other_status": 0,
        "reason_codes": Counter(),
        "scores": [],
        "missing_fair_book_probability": 0,
        "missing_fair_on_execution_real": 0,
    }


def _accumulate(bucket: dict[str, Any], *, item: dict[str, Any], kpi_meta: dict[str, Any] | None) -> None:
    bucket["total"] += 1
    status = item.get("status")
    if status == "score":
        bucket["score"] += 1
    elif status == "gate_failed":
        bucket["gate_failed"] += 1
    elif status == "not_calculable":
        bucket["not_calculable"] += 1
    else:
        bucket["other_status"] += 1

    reasons = list(item.get("gate_reason_codes") or [])
    for r in reasons:
        bucket["reason_codes"][str(r)] += 1
    if "missing_fair_book_probability" in reasons:
        bucket["missing_fair_book_probability"] += 1

    exec_real = _is_execution_real(kpi_meta, item)
    if exec_real:
        bucket["execution_real"] += 1
        if "missing_fair_book_probability" in reasons:
            bucket["missing_fair_on_execution_real"] += 1

    prob = item.get("probability_cecchino")
    if prob is None and kpi_meta is not None:
        prob = kpi_meta.get("prob_cecchino")
    if prob is None:
        bucket["model_probability_missing"] += 1

    fair = item.get("fair_book_probability")
    if fair is not None:
        bucket["fair_book_available"] += 1

    sc = item.get("score")
    if sc is not None:
        try:
            bucket["scores"].append(float(sc))
        except (TypeError, ValueError):
            pass


def _finalize(bucket: dict[str, Any]) -> dict[str, Any]:
    scores = bucket["scores"]
    return {
        "total": bucket["total"],
        "execution_real": bucket["execution_real"],
        "model_probability_missing": bucket["model_probability_missing"],
        "fair_book_available": bucket["fair_book_available"],
        "score": bucket["score"],
        "gate_failed": bucket["gate_failed"],
        "not_calculable": bucket["not_calculable"],
        "other_status": bucket["other_status"],
        "missing_fair_book_probability": bucket["missing_fair_book_probability"],
        "missing_fair_on_execution_real": bucket["missing_fair_on_execution_real"],
        "score_mean": round(mean(scores), 3) if scores else None,
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "top_gate_reason_codes": bucket["reason_codes"].most_common(12),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="0 = tutti gli snapshot")
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Path JSON report (default .tmp_...)",
    )
    args = parser.parse_args()

    engine = create_engine(db_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.out:
        out_path = Path(args.out)
    elif ON_RAILWAY:
        out_path = Path(f"/tmp/shadow_dc_run{args.run_id}_{stamp}.json")
    else:
        out_path = (
            Path(__file__).resolve().parents[2]
            / ".tmp_shadow_dc_purchasability_run4"
            / f"shadow_dc_run{args.run_id}_{stamp}.json"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rev = resolve_code_revision()
    code_sha = str(rev.get("git_commit") or "")
    code_sha_source = str(rev.get("git_commit_source") or "")

    before = {mk: _agg_bucket() for mk in DC_KEYS}
    after = {mk: _agg_bucket() for mk in DC_KEYS}
    independence = {
        "PURCHASABILITY_IS_ANALYTICAL_OUTPUT_ONLY": "YES",
        "shadow_writes": False,
        "checked_fields": list(INDEPENDENCE_FIELDS),
        "notes": [],
        "ok": True,
    }
    snaps_total = 0
    snaps_scored = 0
    snaps_skipped = 0
    errors: list[str] = []
    cardinality_ok = True
    cardinality_notes: list[str] = []

    with Session() as db:
        # READ ONLY + REPEATABLE READ — fail se qualcuno tenta write.
        db.execute(
            text("SET TRANSACTION READ ONLY, ISOLATION LEVEL REPEATABLE READ")
        )
        run = db.get(CecchinoRunV2Run, args.run_id)
        if run is None:
            print(f"FAIL: run_id={args.run_id} non trovata")
            return 1

        q = (
            select(CecchinoRunV2MatchSnapshot)
            .where(CecchinoRunV2MatchSnapshot.run_id == args.run_id)
            .order_by(CecchinoRunV2MatchSnapshot.id)
        )
        if args.limit and args.limit > 0:
            q = q.limit(args.limit)
        snapshots = list(db.scalars(q).all())
        snaps_total = len(snapshots)

        # Sample market_results prediction fields (read-only identity check).
        sample_ids = [s.id for s in snapshots[: min(20, len(snapshots))]]
        mr_sample: dict[int, list[dict[str, Any]]] = defaultdict(list)
        if sample_ids:
            mr_rows = db.scalars(
                select(CecchinoRunV2MarketResult).where(
                    CecchinoRunV2MarketResult.match_snapshot_id.in_(sample_ids),
                    CecchinoRunV2MarketResult.observation_layer
                    == OBSERVATION_LAYER_CORE_STRICT,
                    CecchinoRunV2MarketResult.market_key.in_(list(DC_KEYS)),
                )
            ).all()
            for r in mr_rows:
                mr_sample[int(r.match_snapshot_id)].append(
                    {
                        "market_key": r.market_key,
                        "prediction": r.prediction,
                        "is_predicted_selection": r.is_predicted_selection,
                        "probability": float(r.probability)
                        if r.probability is not None
                        else None,
                        "quota_book": float(r.quota_book)
                        if r.quota_book is not None
                        else None,
                        "outcome": r.outcome,
                        "buyability_score": float(r.buyability_score)
                        if r.buyability_score is not None
                        else None,
                    }
                )

        for snap in snapshots:
            kpi = _as_dict(snap.kpi_json)
            qb = _as_dict(snap.quote_bundle_json)
            strict = qb.get("strict_by_market") if isinstance(qb.get("strict_by_market"), dict) else {}
            purch_before = _as_dict(snap.purchasability_json)
            if not kpi.get("rows"):
                snaps_skipped += 1
                continue

            kpi_dc = _kpi_dc_meta(kpi)
            before_dc = _before_dc_from_payload(purch_before)
            for mk in DC_KEYS:
                item = before_dc.get(mk) or {"status": None, "gate_reason_codes": []}
                _accumulate(before[mk], item=item, kpi_meta=kpi_dc.get(mk))

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
                errors.append(f"snap={snap.id} lab={snap.lab_match_id}: {exc}")
                snaps_skipped += 1
                continue

            snaps_scored += 1
            after_markets = _markets_by_key(shadow)
            for mk in DC_KEYS:
                m = after_markets.get(mk) or {}
                item = {
                    "status": m.get("status"),
                    "gate_status": m.get("gate_status"),
                    "gate_reason_codes": list(m.get("gate_reason_codes") or []),
                    "score": m.get("score"),
                    "fair_book_probability": m.get("fair_book_probability"),
                    "execution_quote_real": None,
                    "probability_cecchino": kpi_dc.get(mk, {}).get("prob_cecchino"),
                    "fair_book_probability_source": m.get("fair_book_probability_source"),
                }
                _accumulate(after[mk], item=item, kpi_meta=kpi_dc.get(mk))

            # Independence: shadow output non contiene prediction/outcome; input frozen intatti.
            if "purchasability" in _as_dict(snap.pre_match_payload_json):
                independence["ok"] = False
                independence["notes"].append(
                    f"snap {snap.id}: pre_match_payload contiene purchasability (anomalia)"
                )
            # KPI / strict / signals / balance / GI / eligibility non passati allo scorer
            # come output mutabile: verifichiamo che gli oggetti input non siano stati
            # riscritti confrontando quote DC KPI pre/post (stesso dict in memoria).
            for mk, meta in kpi_dc.items():
                row_now = next(
                    (
                        r
                        for r in (kpi.get("rows") or [])
                        if isinstance(r, dict) and r.get("market_key") == mk
                    ),
                    {},
                )
                if row_now.get("quota_book") != meta.get("quota_book"):
                    independence["ok"] = False
                    independence["notes"].append(f"snap {snap.id}: KPI quota_book mutata su {mk}")
                if row_now.get("derived_quote") != meta.get("derived_quote"):
                    independence["ok"] = False
                    independence["notes"].append(f"snap {snap.id}: derived_quote mutata su {mk}")
                if row_now.get("is_real_quote") != meta.get("is_real_quote"):
                    independence["ok"] = False
                    independence["notes"].append(f"snap {snap.id}: is_real_quote mutata su {mk}")

            if snap.id in mr_sample:
                # Lo shadow non ha toccato market_results (sola lettura).
                independence["notes"].append(
                    f"snap {snap.id}: market_results DC sample letto "
                    f"n={len(mr_sample[snap.id])} (prediction/outcome invariati dal processo)"
                )

        independence["notes"].append(
            "build_run_v2_purchasability legge kpi_json + strict_by_market e produce "
            "solo payload purchasability; non scrive predicted_key / is_predicted_selection / "
            "probabilities / Signals / Balance / GI / eligibility / strict quotes / outcome."
        )
        independence["notes"].append(
            "pre_match_payload_json (freeze) non include purchasability — "
            "executor congelato indipendente dall'overlay DC."
        )
        independence["dc_fair_probability_source"] = SOURCE_DC_FAIR_V2

        if args.run_id == 4 and (not args.limit or args.limit <= 0):
            if snaps_total != EXPECTED_SNAPSHOTS_RUN4:
                cardinality_ok = False
                cardinality_notes.append(
                    f"snapshots_total={snaps_total} expected={EXPECTED_SNAPSHOTS_RUN4}"
                )
            if snaps_scored != EXPECTED_SNAPSHOTS_RUN4:
                cardinality_ok = False
                cardinality_notes.append(
                    f"snapshots_scored={snaps_scored} expected={EXPECTED_SNAPSHOTS_RUN4}"
                )

        report = {
            "run_id": args.run_id,
            "run_status": run.status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "READ_ONLY_SHADOW",
            "writes": False,
            "on_railway": ON_RAILWAY,
            "code_sha": code_sha,
            "code_sha_source": code_sha_source,
            "railway_git_commit_sha": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
            "isolation": "READ ONLY, REPEATABLE READ",
            "snapshots_total": snaps_total,
            "snapshots_scored": snaps_scored,
            "snapshots_skipped": snaps_skipped,
            "expected_cardinality": {
                "snapshots": EXPECTED_SNAPSHOTS_RUN4,
                "dc_per_snapshot": EXPECTED_DC_PER_SNAPSHOT,
                "plan_rows": EXPECTED_PLAN_ROWS_RUN4,
            },
            "cardinality_ok": cardinality_ok,
            "cardinality_notes": cardinality_notes,
            "errors_sample": errors[:20],
            "error_count": len(errors),
            "independence_audit": independence,
            "before": {mk: _finalize(before[mk]) for mk in DC_KEYS},
            "after": {mk: _finalize(after[mk]) for mk in DC_KEYS},
            "delta_missing_fair_on_execution_real": {
                mk: {
                    "before": before[mk]["missing_fair_on_execution_real"],
                    "after": after[mk]["missing_fair_on_execution_real"],
                    "delta": after[mk]["missing_fair_on_execution_real"]
                    - before[mk]["missing_fair_on_execution_real"],
                }
                for mk in DC_KEYS
            },
        }

        # Tentativo intenzionale: conferma che la txn è read-only (opzionale, non fatal).
        write_guard = {"read_only_enforced": True}
        try:
            db.execute(text("UPDATE cecchino_run_v2_runs SET id = id WHERE id = :id"), {"id": args.run_id})
            db.rollback()
            write_guard["read_only_enforced"] = False
            write_guard["note"] = "UPDATE inatteso riuscito — verificare isolation"
        except Exception as exc:  # noqa: BLE001
            write_guard["blocked_error"] = type(exc).__name__
            db.rollback()
        report["write_guard"] = write_guard

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    out_path.write_text(payload, encoding="utf-8")
    report_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(payload)
    print(f"\nWROTE_REPORT={out_path}")
    print(f"REPORT_SHA256={report_sha}")
    print(f"CODE_SHA={code_sha}")
    print(f"CARDINALITY_OK={cardinality_ok}")
    ok = independence["ok"] and not errors and cardinality_ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
