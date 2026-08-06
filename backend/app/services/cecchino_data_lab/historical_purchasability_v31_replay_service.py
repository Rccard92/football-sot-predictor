"""Replay Acquistabilità V3.1 — riusa infrastruttura V3, formula e HR walk-forward."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_lab_historical_market_result import (
    CecchinoLabHistoricalMarketResult,
)
from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.models.cecchino_lab_purchasability_v3_replay_result import (
    CecchinoLabPurchasabilityV3ReplayResult,
)
from app.models.cecchino_lab_purchasability_v3_replay_run import (
    ACTIVE_STATUSES,
    COMPLETED_STATUSES,
    RESUMABLE_STATUSES,
    STATUS_CANCEL_REQUESTED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    CecchinoLabPurchasabilityV3ReplayRun,
)
from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_AUDIT_VERSION,
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION,
)
from app.services.cecchino.cecchino_purchasability_v31_opposition import (
    is_v31_supported_market,
    market_family_for as v31_market_family_for,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.historical_purchasability_replay_formula_registry import (
    FORMULA_ID_V31,
    INTEGRITY_POLICY_VERSION,
    V31_MARKET_ORDER,
    get_replay_formula_config,
    invoke_formula,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_replay_hr import (
    WalkForwardHRStore,
    collect_settled_events_for_snapshot,
    resolve_hr_as_of,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_replay_preflight import (
    run_purchasability_v31_replay_preflight,
)
from app.services.cecchino_data_lab import historical_purchasability_v3_replay_service as v3svc
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight import (
    FORMULA_PAYLOAD_ALLOWED_FIELDS,
    MARKET_STREAM_COLS,
    SNAPSHOT_LEAN_COLS,
    build_adapter_panel_row,
    classify_performance,
    classify_quote_quality,
    evaluate_historical_integrity_policy,
    map_score_status_to_workload_key,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}

# Rating obbligatorio per gate V3.1 / HR
_V31_MARKET_EXTRA_COLS = (
    CecchinoLabHistoricalMarketResult.rating,
    CecchinoLabHistoricalMarketResult.lab_match_id,
)


def build_adapter_panel_row_v31(m: Any) -> dict[str, Any]:
    row = build_adapter_panel_row(m)
    rating = getattr(m, "rating", None)
    try:
        row["rating"] = int(rating) if rating is not None else None
    except (TypeError, ValueError):
        row["rating"] = None
    return row


def classify_score_replay_v31(
    *,
    market_key: str,
    m: Any | None,
    by_mk: dict[str, Any],
    integrity: str,
    integrity_reasons: list[str],
    duplicate: bool,
) -> tuple[str, list[str]]:
    """Classificazione V3.1: mercati assenti dal source → source_market_unavailable."""
    if not is_v31_supported_market(market_key):
        return "unsupported_market", ["unsupported_market"]
    if duplicate:
        return "ambiguous_market_join", ["duplicate_market_key"]
    if integrity == "invalid":
        return "invalid_integrity", list(integrity_reasons)
    if m is None:
        return "source_market_unavailable", ["source_market_unavailable"]
    return _classify_extended_market(
        market_key=market_key,
        m=m,
        by_mk=by_mk,
        integrity=integrity,
        integrity_reasons=integrity_reasons,
    )


def _classify_extended_market(
    *,
    market_key: str,
    m: Any,
    by_mk: dict[str, Any],
    integrity: str,
    integrity_reasons: list[str],
) -> tuple[str, list[str]]:
    from app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight import (
        _safe_float,
        _quota_valid,
    )

    reasons: list[str] = []
    edge = _safe_float(getattr(m, "edge_pct", None))
    vant = _safe_float(getattr(m, "vantaggio_prob", None))
    prob_c = _safe_float(getattr(m, "prob_cecchino", None))
    quota_b = _safe_float(getattr(m, "quota_book", None))
    fair = _safe_float(getattr(m, "prob_book_fair", None))
    quote_class, quote_reasons = classify_quote_quality(m)
    reasons.extend(quote_reasons)
    gate_ok = edge is not None and vant is not None
    score_core = (
        gate_ok
        and prob_c is not None
        and (_quota_valid(quota_b) or quote_class == "derived")
        and (fair is not None or _quota_valid(quota_b))
        and quote_class in ("real", "derived")
    )
    if integrity in ("missing", "incomplete"):
        if score_core:
            return "score_replay_ready_with_warning", reasons + integrity_reasons
        if gate_ok:
            return "gate_only_replay_ready", reasons + ["missing_score_inputs"] + integrity_reasons
        return "not_replayable_missing_inputs", reasons + integrity_reasons
    if not gate_ok:
        return "not_replayable_missing_inputs", reasons + ["missing_gate_inputs"]
    if not score_core:
        if quote_class == "unavailable":
            reasons.append("quote_unavailable")
        return "gate_only_replay_ready", reasons + ["missing_score_inputs"]
    if quote_class == "derived":
        return "score_replay_ready_with_warning", reasons + ["derived_quote"]
    return "exact_replay_ready", reasons


def start_purchasability_v31_replay(
    db: Session,
    run_id: int,
    *,
    confirmed: bool,
    expected_formula_version: str | None = None,
    expected_preflight_schema_version: str | None = None,
    expected_integrity_policy_version: str | None = None,
    background: bool = True,
) -> dict[str, Any]:
    if confirmed is not True:
        raise CecchinoLabImportError(
            "confirm_required",
            "Conferma richiesta: confirmed deve essere true",
            status_code=400,
        )

    cfg = get_replay_formula_config(FORMULA_ID_V31)
    scan = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not scan:
        raise CecchinoLabImportError("run_not_found", "Run storico non trovato", status_code=404)

    preflight = run_purchasability_v31_replay_preflight(db, run_id, include_probe=False)
    v3svc.validate_preflight_for_start(
        preflight,
        expected_formula_version=expected_formula_version or cfg.formula_version,
        expected_preflight_schema_version=expected_preflight_schema_version
        or cfg.preflight_schema_version,
        expected_integrity_policy_version=expected_integrity_policy_version
        or INTEGRITY_POLICY_VERSION,
    )

    formula_version = cfg.formula_version
    key = v3svc.build_idempotency_key(
        source_scan_run_id=run_id,
        source_scan_version=scan.scan_version,
        source_scan_git_commit=scan.source_git_commit,
        formula_version=formula_version,
        replay_schema_version=cfg.replay_schema_version,
        integrity_policy_version=cfg.integrity_policy_version,
    )

    existing = db.scalars(
        select(CecchinoLabPurchasabilityV3ReplayRun).where(
            CecchinoLabPurchasabilityV3ReplayRun.idempotency_key == key
        )
    ).first()
    if existing:
        if existing.status in COMPLETED_STATUSES or existing.status in ACTIVE_STATUSES:
            if existing.status in ACTIVE_STATUSES:
                _spawn_v31_worker(int(existing.id))
            return v3svc.replay_run_to_dict(existing, reused_existing=True)
        return v3svc.replay_run_to_dict(existing, reused_existing=True)

    si = preflight.get("source_integrity") or {}
    wl = preflight.get("workload") or {}
    qq = preflight.get("quote_quality") or {}
    revision = resolve_code_revision()

    replay = CecchinoLabPurchasabilityV3ReplayRun(
        source_scan_run_id=run_id,
        status=STATUS_QUEUED,
        replay_schema_version=cfg.replay_schema_version,
        replay_engine_version=cfg.replay_engine_version,
        candidate_version=PURCHASABILITY_V31_CANDIDATE_VERSION,
        formula_version=PURCHASABILITY_V31_FORMULA_VERSION,
        audit_version=PURCHASABILITY_V31_AUDIT_VERSION,
        preflight_schema_version=cfg.preflight_schema_version,
        integrity_policy_version=cfg.integrity_policy_version,
        source_scan_git_commit=scan.source_git_commit,
        runtime_git_commit=revision.get("git_commit"),
        runtime_git_commit_source=revision.get("git_commit_source"),
        source_scan_version=scan.scan_version,
        requested_at=datetime.now(timezone.utc),
        snapshots_total=int(si.get("snapshots_eligible_core") or 0),
        evaluations_total=int(wl.get("theoretical_evaluations") or 0),
        exact_source_count=int(wl.get("exact_replay_ready") or 0),
        warning_source_count=int(wl.get("ready_with_warning") or 0),
        non_replayable_source_count=int(wl.get("not_replayable") or 0)
        + int(wl.get("source_market_unavailable") or 0),
        real_quote_count=0,
        derived_quote_count=0,
        unavailable_quote_count=0,
        cancel_requested=False,
        resume_count=0,
        attempt_count=1,
        idempotency_key=key,
        preflight_snapshot_json=v3svc.compact_preflight_snapshot(preflight),
    )
    replay.summary_json = {
        "formula_id": FORMULA_ID_V31,
        "walk_forward_hr": True,
        "preflight_quote_quality": {
            "real": qq.get("real"),
            "derived": qq.get("derived"),
            "unavailable": qq.get("unavailable"),
            "source_market_unavailable": qq.get("source_market_unavailable"),
        },
    }
    db.add(replay)
    db.commit()
    db.refresh(replay)

    if background:
        _spawn_v31_worker(int(replay.id))
    else:
        execute_purchasability_v31_replay(int(replay.id))
        db.refresh(replay)

    return v3svc.replay_run_to_dict(replay, reused_existing=False)


def _spawn_v31_worker(replay_id: int) -> None:
    with _lock:
        t_existing = _active_threads.get(replay_id)
        if t_existing and t_existing.is_alive():
            return
        t = threading.Thread(
            target=execute_purchasability_v31_replay,
            args=(replay_id,),
            name=f"cecchino-lab-p31-replay-{replay_id}",
            daemon=True,
        )
        _active_threads[replay_id] = t
        t.start()


def resume_purchasability_v31_replay(
    db: Session,
    replay_id: int,
    *,
    background: bool = True,
) -> dict[str, Any]:
    run = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
    if not run:
        raise CecchinoLabImportError("replay_not_found", "Replay non trovato", status_code=404)
    if run.formula_version != PURCHASABILITY_V31_FORMULA_VERSION:
        raise CecchinoLabImportError(
            "formula_mismatch",
            "Replay non è V3.1",
            status_code=409,
        )
    if run.status not in RESUMABLE_STATUSES:
        raise CecchinoLabImportError(
            "resume_not_allowed",
            f"Status non riprendibile: {run.status}",
            status_code=409,
        )
    run.cancel_requested = False
    run.status = STATUS_QUEUED
    run.resume_count = int(run.resume_count or 0) + 1
    run.attempt_count = int(run.attempt_count or 0) + 1
    run.error_json = None
    run.completed_at = None
    db.commit()
    if background:
        _spawn_v31_worker(replay_id)
    else:
        execute_purchasability_v31_replay(replay_id)
    db.refresh(run)
    return v3svc.replay_run_to_dict(run)


def _load_done_snapshot_ids_v31(db: Session, replay_id: int) -> set[int]:
    rows = db.execute(
        select(
            CecchinoLabPurchasabilityV3ReplayResult.source_snapshot_id,
            func.count(),
        )
        .where(CecchinoLabPurchasabilityV3ReplayResult.replay_run_id == replay_id)
        .group_by(CecchinoLabPurchasabilityV3ReplayResult.source_snapshot_id)
    ).all()
    expected = len(V31_MARKET_ORDER)
    return {int(sid) for sid, cnt in rows if int(cnt) >= expected}


def _fetch_next_kickoff_batch(
    db: Session,
    source_run_id: int,
    *,
    after_kickoff: datetime | None,
    after_snapshot_id: int,
    batch_size: int,
) -> list[SimpleNamespace]:
    """Keyset cronologico: kickoff ASC, id ASC (anti-leakage HR)."""
    size = max(1, min(int(batch_size), v3svc.REPLAY_BATCH_SNAPSHOTS))
    conds = [
        CecchinoLabHistoricalMatchSnapshot.run_id == source_run_id,
        CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status == ELIGIBLE_CORE,
    ]
    if after_kickoff is not None:
        conds.append(
            (CecchinoLabHistoricalMatchSnapshot.kickoff_at > after_kickoff)
            | (
                (CecchinoLabHistoricalMatchSnapshot.kickoff_at == after_kickoff)
                & (CecchinoLabHistoricalMatchSnapshot.id > after_snapshot_id)
            )
        )
    elif after_snapshot_id > 0:
        conds.append(CecchinoLabHistoricalMatchSnapshot.id > after_snapshot_id)

    stmt = (
        select(*SNAPSHOT_LEAN_COLS)
        .where(*conds)
        .order_by(
            CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc().nulls_last(),
            CecchinoLabHistoricalMatchSnapshot.id.asc(),
        )
        .limit(size)
    )
    return [v3svc._row_to_ns(row) for row in db.execute(stmt).all()]


def _load_markets_v31(
    db: Session, run_id: int, snapshot_ids: list[int]
) -> dict[int, list[SimpleNamespace]]:
    if not snapshot_ids:
        return {}
    cols = MARKET_STREAM_COLS + _V31_MARKET_EXTRA_COLS
    stmt = (
        select(*cols)
        .where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.match_snapshot_id.in_(snapshot_ids),
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V31_MARKET_ORDER)),
        )
        .order_by(
            CecchinoLabHistoricalMarketResult.match_snapshot_id.asc(),
            CecchinoLabHistoricalMarketResult.market_key.asc(),
            CecchinoLabHistoricalMarketResult.id.asc(),
        )
    )
    out: dict[int, list[SimpleNamespace]] = {sid: [] for sid in snapshot_ids}
    for row in db.execute(stmt).all():
        ns = v3svc._row_to_ns(row)
        sid = int(ns.match_snapshot_id)
        if sid in out:
            out[sid].append(ns)
    return out


def _rebuild_hr_store_from_done(
    db: Session,
    source_run_id: int,
    done_ids: set[int],
) -> WalkForwardHRStore:
    store = WalkForwardHRStore()
    if not done_ids:
        return store
    # carica snapshot+markets done in ordine kickoff
    ids = sorted(done_ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i : i + 200]
        snaps = {
            int(s.id): s
            for s in [
                v3svc._row_to_ns(r)
                for r in db.execute(
                    select(*SNAPSHOT_LEAN_COLS).where(
                        CecchinoLabHistoricalMatchSnapshot.id.in_(chunk)
                    )
                ).all()
            ]
        }
        markets_map = _load_markets_v31(db, source_run_id, chunk)
        ordered = sorted(
            snaps.values(),
            key=lambda s: (
                getattr(s, "kickoff_at", None) or datetime.min.replace(tzinfo=timezone.utc),
                int(s.id),
            ),
        )
        for snap in ordered:
            store.append_many(
                collect_settled_events_for_snapshot(snap, markets_map.get(int(snap.id), []))
            )
    return store


def _process_snapshot_v31(
    *,
    replay: CecchinoLabPurchasabilityV3ReplayRun,
    snap: SimpleNamespace,
    markets: list[SimpleNamespace],
    hr_store: WalkForwardHRStore,
    same_kickoff_group_size: int,
    formula_call_counter: list[int],
    cfg,
) -> list[dict[str, Any]]:
    by_mk: dict[str, SimpleNamespace] = {}
    duplicates: set[str] = set()
    for m in markets:
        mk = str(m.market_key)
        if mk in by_mk:
            duplicates.add(mk)
        else:
            by_mk[mk] = m
    if duplicates:
        raise v3svc.ReplayWorkerError(
            "ambiguous_market_join",
            "Join mercato ambiguo",
            details={"snapshot_id": int(snap.id), "duplicate_market_keys": sorted(duplicates)},
        )

    policy = evaluate_historical_integrity_policy(snap)
    gate = str(policy.get("integrity_gate") or "invalid")
    integrity_reasons = list(policy.get("reasons") or [])
    if gate == "ok":
        integrity = "ok"
    elif gate == "incomplete":
        integrity = "missing"
    else:
        integrity = "invalid"

    score_statuses: dict[str, tuple[str, list[str]]] = {}
    for mk in V31_MARKET_ORDER:
        score_statuses[mk] = classify_score_replay_v31(
            market_key=mk,
            m=by_mk.get(mk),
            by_mk=by_mk,
            integrity=integrity,
            integrity_reasons=integrity_reasons,
            duplicate=False,
        )

    panel_markets: list[SimpleNamespace] = []
    panel_keys: list[str] = []
    for mk in V31_MARKET_ORDER:
        st, _ = score_statuses[mk]
        if st == "source_market_unavailable":
            continue
        wl = map_score_status_to_workload_key(st) if st != "source_market_unavailable" else None
        if wl in ("not_replayable", "invalid_integrity", "ambiguous_market_join"):
            continue
        m = by_mk.get(mk)
        if m is None:
            continue
        panel_markets.append(m)
        panel_keys.append(mk)

    items_by_mk: dict[str, dict[str, Any]] = {}
    formula_sha: str | None = None
    panel_fields = list(FORMULA_PAYLOAD_ALLOWED_FIELDS) + ["rating"]
    hr_audit_by_mk: dict[str, dict[str, Any]] = {}

    if panel_markets:
        panel_rows = [build_adapter_panel_row_v31(m) for m in panel_markets]
        v3svc.assert_panel_whitelist(panel_rows)
        # rating è ammesso in V3.1 (gate); verifica no post-match
        for r in panel_rows:
            for forbidden in ("won", "profit_1u_real", "profit_1u_synthetic", "result_reason"):
                if forbidden in r:
                    raise v3svc.ReplayWorkerError(
                        "leakage_in_formula_payload",
                        f"Campo post-match nel payload: {forbidden}",
                        details={"snapshot_id": int(snap.id)},
                    )
        formula_sha = v3svc.formula_payload_sha256(panel_rows)
        kickoff = getattr(snap, "kickoff_at", None)
        competition_id = getattr(snap, "competition_name", None) or "unknown"
        hr_map = resolve_hr_as_of(
            panel_rows=panel_rows,
            competition_id=competition_id,
            kickoff=kickoff,
            prior_events=hr_store.events,
            same_kickoff_group_size=same_kickoff_group_size,
        )
        hr_audit_by_mk = hr_map
        formula_call_counter[0] += 1
        batch = invoke_formula(
            cfg,
            kpi_panel={"rows": panel_rows},
            fixture_meta={
                "today_fixture_id": getattr(snap, "lab_match_id", None),
                "snapshot_at": getattr(snap, "pre_match_locked_at", None),
            },
            historical_by_market=hr_map,
        )
        items = list(batch.get("items") or [])
        v3svc.validate_formula_items(expected_keys=panel_keys, items=items)
        for it in items:
            items_by_mk[str(it.get("market_key"))] = it

    results: list[dict[str, Any]] = []
    for mk in V31_MARKET_ORDER:
        st, reasons = score_statuses[mk]
        market = by_mk.get(mk)
        item = items_by_mk.get(mk)
        if st == "source_market_unavailable":
            row = _build_unavailable_source_row(
                replay=replay,
                snap=snap,
                market_key=mk,
                reasons=reasons,
            )
            results.append(row)
            continue
        wl = map_score_status_to_workload_key(st) or st
        if wl in ("not_replayable",) or str(st).startswith("not_replayable"):
            item = None
        row = v3svc._build_result_row(
            replay=replay,
            snap=snap,
            market_key=mk,
            market=market,
            item=item,
            score_status=wl if wl else st,
            score_reasons=reasons,
            formula_sha=formula_sha if item is not None else None,
            panel_fields=panel_fields if item is not None else panel_fields,
        )
        # Override family con mappa V3.1
        row["market_family"] = v31_market_family_for(mk)
        # quote_quality_penalty: derived blocks score → null/0 motivato
        if item is not None and str(item.get("status")) == "non_calculable":
            codes = item.get("reason_codes") or []
            if "derived_quote_not_executable" in codes or bool(row.get("is_derived_quote")):
                row["quote_quality_penalty"] = Decimal("0")
                warnings = list(row.get("warnings_json") or [])
                warnings.append("quote_quality_penalty_null_derived_blocks_score_v31")
                row["warnings_json"] = warnings
        # HR audit nei warnings (versionato, non colonna nuova)
        hr_item = hr_audit_by_mk.get(mk)
        if hr_item:
            warnings = list(row.get("warnings_json") or [])
            warnings.append(
                {
                    "hr_walk_forward_audit": {
                        "historical_cutoff": hr_item.get("historical_cutoff"),
                        "prior_events_count": hr_item.get("prior_events_count"),
                        "same_kickoff_group_size": hr_item.get("same_kickoff_group_size"),
                        "same_kickoff_results_excluded": hr_item.get(
                            "same_kickoff_results_excluded"
                        ),
                        "future_events_excluded": hr_item.get("future_events_excluded"),
                        "cohort_scope": hr_item.get("cohort_scope"),
                        "rating_band": hr_item.get("rating_band"),
                        "selected_sample_size": hr_item.get("selected_sample_size"),
                        "hr_score": hr_item.get("hr_score") or hr_item.get("score"),
                        "historical_factor": hr_item.get("historical_factor"),
                    }
                }
            )
            row["warnings_json"] = warnings
        results.append(row)
    return results


def _build_unavailable_source_row(
    *,
    replay: CecchinoLabPurchasabilityV3ReplayRun,
    snap: SimpleNamespace,
    market_key: str,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "replay_run_id": int(replay.id),
        "source_scan_run_id": int(replay.source_scan_run_id),
        "source_snapshot_id": int(snap.id),
        "source_market_result_id": None,
        "lab_match_id": getattr(snap, "lab_match_id", None),
        "competition_name": getattr(snap, "competition_name", None),
        "kickoff_at": getattr(snap, "kickoff_at", None),
        "chronological_order": getattr(snap, "chronological_order", None),
        "market_key": market_key,
        "market_family": v31_market_family_for(market_key),
        "quote_source": None,
        "quote_quality": "unavailable",
        "performance_type": "not_applicable",
        "is_real_book_quote": False,
        "is_derived_quote": False,
        "derivation_method": None,
        "quota_book": None,
        "quota_cecchino": None,
        "prob_book_raw": None,
        "prob_book_fair": None,
        "prob_cecchino": None,
        "edge_pct": None,
        "vantaggio_prob": None,
        "calculation_status": "source_market_unavailable",
        "gate_status": None,
        "gate_reason_codes_json": list(reasons),
        "score": None,
        "raw_score": None,
        "score_class": None,
        "value_score": None,
        "quality_score": None,
        "total_penalty": None,
        "probability_risk_penalty": None,
        "opposite_market_pressure_penalty": None,
        "extreme_divergence_penalty": None,
        "family_ambiguity_penalty": None,
        "quote_quality_penalty": None,
        "opposite_market_key": None,
        "opposite_fair_probability": None,
        "selected_is_family_edge_leader": None,
        "family_edge_gap_or_deficit": None,
        "calculation_quality": None,
        "reason_codes_json": list(reasons) + ["source_market_unavailable"],
        "warnings_json": ["source_market_unavailable_excluded_from_real_roi"],
        "performance_evaluation_status": "not_applicable",
        "won": None,
        "profit_1u_real": None,
        "profit_1u_synthetic": None,
        "result_reason": None,
        "source_pre_match_payload_sha256": getattr(snap, "pre_match_payload_sha256", None),
        "source_pre_match_locked_at": getattr(snap, "pre_match_locked_at", None),
        "formula_payload_sha256": None,
        "formula_payload_fields_json": list(FORMULA_PAYLOAD_ALLOWED_FIELDS),
        "pre_match_only": True,
        "post_match_fields_excluded": True,
    }


def execute_purchasability_v31_replay(replay_id: int) -> None:
    """Worker V3.1: ordine kickoff + HR walk-forward + calculate_purchasability_v31_batch."""
    db = SessionLocal()
    cfg = get_replay_formula_config(FORMULA_ID_V31)
    formula_calls = [0]
    last_cancel_check = 0.0
    after_kickoff: datetime | None = None
    after_id = 0
    try:
        replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
        if not replay:
            return
        if replay.cancel_requested:
            replay.status = STATUS_CANCELLED
            replay.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        replay.status = STATUS_RUNNING
        replay.started_at = replay.started_at or datetime.now(timezone.utc)
        replay.heartbeat_at = datetime.now(timezone.utc)
        if not (replay.summary_json or {}).get("resource_profile"):
            v3svc._set_resource_profile(replay, v3svc._empty_resource_profile())
        db.commit()

        done_ids = _load_done_snapshot_ids_v31(db, replay_id)
        source_run_id = int(replay.source_scan_run_id)
        hr_store = _rebuild_hr_store_from_done(db, source_run_id, done_ids)

        # cursore: ultimo kickoff tra done
        if done_ids:
            last_done = db.execute(
                select(
                    CecchinoLabHistoricalMatchSnapshot.kickoff_at,
                    CecchinoLabHistoricalMatchSnapshot.id,
                )
                .where(CecchinoLabHistoricalMatchSnapshot.id.in_(list(done_ids)))
                .order_by(
                    CecchinoLabHistoricalMatchSnapshot.kickoff_at.desc().nulls_last(),
                    CecchinoLabHistoricalMatchSnapshot.id.desc(),
                )
                .limit(1)
            ).first()
            if last_done:
                after_kickoff = last_done[0]
                after_id = int(last_done[1])

        while True:
            snap_batch = _fetch_next_kickoff_batch(
                db,
                source_run_id,
                after_kickoff=after_kickoff,
                after_snapshot_id=after_id,
                batch_size=v3svc.REPLAY_BATCH_SNAPSHOTS,
            )
            if not snap_batch:
                break
            after_kickoff = getattr(snap_batch[-1], "kickoff_at", None)
            after_id = int(snap_batch[-1].id)

            if v3svc._is_cancelled(db, replay_id):
                replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
                if replay:
                    v3svc._mark_cancelled(db, replay, reconcile=True)
                return

            pending = [s for s in snap_batch if int(s.id) not in done_ids]
            if not pending:
                continue

            markets_map = _load_markets_v31(
                db, source_run_id, [int(s.id) for s in pending]
            )
            replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
            if not replay:
                return

            # Raggruppa per kickoff
            groups: dict[Any, list[SimpleNamespace]] = defaultdict(list)
            for s in pending:
                groups[getattr(s, "kickoff_at", None)].append(s)

            batch_rows: list[dict[str, Any]] = []
            try:
                for _ko, group in sorted(
                    groups.items(),
                    key=lambda kv: (
                        kv[0] or datetime.min.replace(tzinfo=timezone.utc),
                    ),
                ):
                    gsize = len(group)
                    for snap in group:
                        now = time.monotonic()
                        if (now - last_cancel_check) >= v3svc.REPLAY_HEARTBEAT_SECONDS:
                            if v3svc._is_cancelled(db, replay_id):
                                db.rollback()
                                replay = db.get(
                                    CecchinoLabPurchasabilityV3ReplayRun, replay_id
                                )
                                if replay:
                                    v3svc._mark_cancelled(db, replay, reconcile=True)
                                return
                            last_cancel_check = now
                            replay.heartbeat_at = datetime.now(timezone.utc)

                        markets = markets_map.get(int(snap.id), [])
                        rows = _process_snapshot_v31(
                            replay=replay,
                            snap=snap,
                            markets=markets,
                            hr_store=hr_store,
                            same_kickoff_group_size=gsize,
                            formula_call_counter=formula_calls,
                            cfg=cfg,
                        )
                        batch_rows.extend(rows)

                    # Dopo l'intero gruppo stesso kickoff: aggiorna HR store
                    for snap in group:
                        hr_store.append_many(
                            collect_settled_events_for_snapshot(
                                snap, markets_map.get(int(snap.id), [])
                            )
                        )
            except v3svc.ReplayWorkerError as exc:
                db.rollback()
                replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
                if replay:
                    replay.status = STATUS_FAILED
                    replay.error_json = {
                        "error": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    }
                    replay.completed_at = datetime.now(timezone.utc)
                    try:
                        v3svc._reconcile_counts_from_db(db, replay)
                    except Exception:
                        pass
                    db.commit()
                return

            try:
                v3svc._upsert_results(db, batch_rows)
                delta = v3svc.summarize_result_rows(batch_rows)
                v3svc._apply_counter_deltas(replay, delta)
                for s in pending:
                    done_ids.add(int(s.id))
                profile = v3svc._get_resource_profile(replay)
                profile["formula_invocations"] = formula_calls[0]
                profile["walk_forward_hr"] = True
                profile["formula_order_independent"] = False
                profile["snapshot_pagination_strategy"] = "keyset_by_kickoff_at"
                profile["hr_prior_events"] = hr_store.count
                v3svc._set_resource_profile(replay, profile)
                replay.heartbeat_at = datetime.now(timezone.utc)
                db.commit()
            except Exception:
                db.rollback()
                replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
                if replay:
                    replay.status = STATUS_FAILED
                    replay.error_json = {
                        "error": "batch_persist_failed",
                        "message": "Fallimento persistenza batch V3.1",
                    }
                    replay.completed_at = datetime.now(timezone.utc)
                    db.commit()
                raise

        # Completamento + reconcile
        replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
        if not replay:
            return
        v3svc._reconcile_counts_from_db(db, replay)
        # Invarianti
        if int(replay.unclassified_count or 0) != 0:
            replay.status = STATUS_FAILED
            replay.error_json = {
                "error": "unclassified_nonzero",
                "message": "Riconciliazione: unclassified != 0",
            }
        else:
            warnings = bool(replay.warning_source_count)
            replay.status = (
                STATUS_COMPLETED_WITH_WARNINGS if warnings else STATUS_COMPLETED
            )
        profile = v3svc._get_resource_profile(replay)
        profile["formula_invocations"] = formula_calls[0]
        profile["completed_at"] = datetime.now(timezone.utc).isoformat()
        v3svc._set_resource_profile(replay, profile)
        replay.completed_at = datetime.now(timezone.utc)
        replay.progress_pct = Decimal("100")
        db.commit()
    except Exception:
        logger.exception("purchasability_v31_replay_failed replay_id=%s", replay_id)
        try:
            db.rollback()
            replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
            if replay and replay.status not in COMPLETED_STATUSES:
                replay.status = STATUS_FAILED
                replay.error_json = {
                    "error": "worker_exception",
                    "message": "Eccezione worker V3.1",
                }
                replay.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        with _lock:
            _active_threads.pop(replay_id, None)
