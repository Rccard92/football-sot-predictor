"""Riallineamento derived V3 su run storico Cecchino Lab (solo artifact derivati).

Ricostruisce signals_json e market results da payload già persistiti.
Nessuna API esterna, nessun full-scan restart, nessuna modifica a input congelati.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.models.cecchino_lab_historical_scan_run import (
    ACTIVE_STATUSES,
    CecchinoLabHistoricalScanRun,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    SIGNAL_AUDIT_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    get_current_signal_contract,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import (
    ELIGIBLE_CORE,
    EXCLUDED_LEAKAGE,
)
from app.services.cecchino_data_lab.historical_settlement import (
    settle_historical_markets,
    settlement_summary,
)
from app.services.cecchino_data_lab.historical_signal_models import (
    build_historical_signal_models,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

logger = logging.getLogger(__name__)

CONFIRM_TOKEN = "REBUILD_CECCHINO_LAB_DERIVED_V3"
MARKET_REGISTRY_COUNT = len(KPI_V2_ROW_DEFS)  # 19
DERIVED_REBUILD_SCHEMA_VERSION = "cecchino_lab_historical_derived_rebuild_v1"

CLASS_REBUILDABLE = "rebuildable"
CLASS_PARTIAL = "partial"
CLASS_BLOCKED = "blocked"

REASON_MISSING_INPUT = "missing_input_snapshot"
REASON_MISSING_CECCHINO = "missing_cecchino_output"
REASON_MISSING_QUOTES = "missing_quotes"
REASON_MISSING_RESULT = "missing_result_for_settlement"
REASON_MISSING_FORMULA = "missing_formula_inputs"
REASON_KPI_MISSING = "missing_kpi_panel"
REASON_MARKET_NOT_REBUILDABLE = "market_results_not_rebuildable"
REASON_LEAKAGE = "leakage_concern"
REASON_RUN_ACTIVE = "run_active"
REASON_RUN_NOT_FOUND = "run_not_found"

_RUN_LOCKS: dict[int, threading.Lock] = {}
_RUN_LOCKS_GUARD = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utcnow().isoformat().replace("+00:00", "Z")


def _lock_for_run(run_id: int) -> threading.Lock:
    with _RUN_LOCKS_GUARD:
        lock = _RUN_LOCKS.get(run_id)
        if lock is None:
            lock = threading.Lock()
            _RUN_LOCKS[run_id] = lock
        return lock


def _as_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _has_nonempty_dict(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _picchetti_present(cecchino_output: dict[str, Any] | None) -> bool:
    if not isinstance(cecchino_output, dict):
        return False
    pic = cecchino_output.get("picchetti")
    if isinstance(pic, dict) and pic:
        return True
    # alcuni payload serializzano già i blocchi al top-level
    for key in ("totals", "home_away", "last6_totals", "last5_home_away"):
        if isinstance(cecchino_output.get(key), dict) and cecchino_output.get(key):
            return True
    return False


def _extract_under_odd(
    *,
    cecchino_output: dict[str, Any] | None,
    historical_kpi: dict[str, Any] | None,
    signals_json: dict[str, Any] | None,
) -> float | None:
    if isinstance(signals_json, dict):
        inputs = signals_json.get("inputs") or {}
        if isinstance(inputs, dict) and inputs.get("under_2_5_cecchino_odd") is not None:
            try:
                return float(inputs["under_2_5_cecchino_odd"])
            except (TypeError, ValueError):
                pass
    if isinstance(cecchino_output, dict):
        gm = cecchino_output.get("goal_markets") or {}
        if isinstance(gm, dict):
            under = gm.get("UNDER_2_5") or {}
            if isinstance(under, dict) and under.get("final_odd") is not None:
                try:
                    return float(under["final_odd"])
                except (TypeError, ValueError):
                    pass
    if isinstance(historical_kpi, dict):
        for row in historical_kpi.get("rows") or []:
            if not isinstance(row, dict):
                continue
            if row.get("market_key") == "UNDER_2_5" and row.get("quota_cecchino") is not None:
                try:
                    return float(row["quota_cecchino"])
                except (TypeError, ValueError):
                    pass
    return None


def _quote_bundle_usable(bundle: Any) -> bool:
    if not isinstance(bundle, dict):
        return False
    quotes = bundle.get("quotes")
    return isinstance(quotes, dict) and len(quotes) > 0


def _reconstruct_quote_bundle_from_market_rows(
    rows: list[Any],
) -> dict[str, Any] | None:
    if not rows:
        return None
    quotes: dict[str, Any] = {}
    real_n = derived_n = unavailable_n = 0
    for row in rows:
        mk = getattr(row, "market_key", None)
        if not mk:
            continue
        qb = getattr(row, "quota_book", None)
        value = float(qb) if qb is not None else None
        is_real = bool(getattr(row, "is_real_book_quote", False))
        is_derived = bool(getattr(row, "is_derived_quote", False))
        if value is None:
            unavailable_n += 1
        elif is_real:
            real_n += 1
        elif is_derived:
            derived_n += 1
        else:
            unavailable_n += 1
        quotes[str(mk)] = {
            "value": value,
            "source_type": getattr(row, "quote_source_type", None),
            "is_real_book_quote": is_real,
            "is_derived": is_derived,
            "derivation_method": getattr(row, "derivation_method", None),
            "prob_raw": (
                float(getattr(row, "prob_book_raw"))
                if getattr(row, "prob_book_raw", None) is not None
                else None
            ),
            "prob_fair": (
                float(getattr(row, "prob_book_fair"))
                if getattr(row, "prob_book_fair", None) is not None
                else None
            ),
        }
    if not quotes:
        return None
    return {
        "quotes": quotes,
        "counts": {
            "real_quote_markets_count": real_n,
            "derived_quote_markets_count": derived_n,
            "unavailable_quote_markets_count": unavailable_n,
        },
        "kpi_1x2_real_available": any(
            quotes.get(k, {}).get("is_real_book_quote") for k in ("HOME", "DRAW", "AWAY")
        ),
        "kpi_ou25_real_available": any(
            quotes.get(k, {}).get("is_real_book_quote") for k in ("OVER_2_5", "UNDER_2_5")
        ),
        "reconstructed_from_market_results": True,
    }


def _resolve_quote_bundle(
    snap: Any,
    market_rows: list[Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Ritorna (bundle, source_tag). Preferisce quote_sources_json persistito."""
    persisted = _as_dict(getattr(snap, "quote_sources_json", None))
    if _quote_bundle_usable(persisted):
        return persisted, "quote_sources_json"
    reconstructed = _reconstruct_quote_bundle_from_market_rows(market_rows or [])
    if _quote_bundle_usable(reconstructed):
        return reconstructed, "reconstructed_from_market_results"
    return None, None


def _result_present(result_json: Any) -> bool:
    if not isinstance(result_json, dict):
        return False
    ft = result_json.get("fulltime") or {}
    if isinstance(ft, dict) and ft.get("home") is not None and ft.get("away") is not None:
        return True
    # fallback flat
    return result_json.get("ft_home_goals") is not None and result_json.get("ft_away_goals") is not None


def _match_proxy_from_snapshot(snap: Any) -> SimpleNamespace:
    result = _as_dict(getattr(snap, "result_json", None)) or {}
    ft = result.get("fulltime") if isinstance(result.get("fulltime"), dict) else {}
    ht = result.get("halftime") if isinstance(result.get("halftime"), dict) else {}
    return SimpleNamespace(
        id=getattr(snap, "lab_match_id", None),
        home_team=getattr(snap, "home_team", None),
        away_team=getattr(snap, "away_team", None),
        kickoff_at=getattr(snap, "kickoff_at", None),
        ft_home_goals=ft.get("home", result.get("ft_home_goals")),
        ft_away_goals=ft.get("away", result.get("ft_away_goals")),
        ht_home_goals=ht.get("home", result.get("ht_home_goals")),
        ht_away_goals=ht.get("away", result.get("ht_away_goals")),
        ft_result=result.get("ft_result"),
        ht_result=result.get("ht_result"),
    )


def _leakage_concern(snap: Any) -> bool:
    elig = getattr(snap, "historical_eligibility_status", None)
    if elig == EXCLUDED_LEAKAGE:
        return True
    blockers = getattr(snap, "blocking_reasons_json", None) or []
    if isinstance(blockers, list):
        for b in blockers:
            if b in ("leakage_detected", "leakage_concern") or (
                isinstance(b, str) and "leakage" in b.lower()
            ):
                return True
    inp = _as_dict(getattr(snap, "input_snapshot_json", None))
    if inp is not None and inp.get("leakage_ok") is False:
        return True
    return False


def classify_snapshot_for_derived_rebuild(
    snap: Any,
    *,
    market_rows: list[Any] | None = None,
    run_active: bool = False,
) -> dict[str, Any]:
    """Classifica uno snapshot: rebuildable / partial / blocked."""
    reasons: list[str] = []
    if run_active:
        reasons.append(REASON_RUN_ACTIVE)

    input_ok = _has_nonempty_dict(getattr(snap, "input_snapshot_json", None))
    cecchino = _as_dict(getattr(snap, "cecchino_output_json", None))
    cecchino_ok = _has_nonempty_dict(cecchino)
    kpi = _as_dict(getattr(snap, "historical_kpi_json", None))
    kpi_ok = _has_nonempty_dict(kpi) and isinstance(kpi.get("rows"), list)
    result_ok = _result_present(getattr(snap, "result_json", None))
    formula_ok = _picchetti_present(cecchino)
    leakage = _leakage_concern(snap)
    quote_bundle, quote_source = _resolve_quote_bundle(snap, market_rows)
    quotes_ok = _quote_bundle_usable(quote_bundle)

    if not input_ok:
        reasons.append(REASON_MISSING_INPUT)
    if not cecchino_ok:
        reasons.append(REASON_MISSING_CECCHINO)
    if not quotes_ok:
        reasons.append(REASON_MISSING_QUOTES)
    if leakage:
        reasons.append(REASON_LEAKAGE)
    if not formula_ok:
        reasons.append(REASON_MISSING_FORMULA)

    signals_ok = bool(input_ok and cecchino_ok and quotes_ok and formula_ok and not leakage)
    markets_ok = bool(signals_ok and result_ok and kpi_ok)
    if signals_ok and not result_ok:
        reasons.append(REASON_MISSING_RESULT)
    if signals_ok and not kpi_ok:
        reasons.append(REASON_KPI_MISSING)
    if signals_ok and result_ok and kpi_ok and not markets_ok:
        reasons.append(REASON_MARKET_NOT_REBUILDABLE)

    if run_active or leakage or not input_ok or not cecchino_ok or not quotes_ok or not formula_ok:
        classification = CLASS_BLOCKED
    elif signals_ok and markets_ok:
        classification = CLASS_REBUILDABLE
    elif signals_ok:
        classification = CLASS_PARTIAL
    else:
        classification = CLASS_BLOCKED

    elig = getattr(snap, "historical_eligibility_status", None)
    return {
        "snapshot_id": getattr(snap, "id", None),
        "lab_match_id": getattr(snap, "lab_match_id", None),
        "classification": classification,
        "reasons": reasons,
        "signals_rebuildable": signals_ok and not run_active,
        "market_results_rebuildable": markets_ok and not run_active,
        "kpi_rebuildable": markets_ok and not run_active,
        "quote_source": quote_source,
        "eligibility_status": elig,
        "core_eligible": elig == ELIGIBLE_CORE,
    }


def _empty_missing_reasons() -> dict[str, int]:
    return defaultdict(int)


def _base_preflight_payload(
    *,
    run_id: int,
    run: CecchinoLabHistoricalScanRun | None = None,
) -> dict[str, Any]:
    contract = get_current_signal_contract()
    derived = None
    if run is not None:
        summary = _as_dict(getattr(run, "summary_json", None)) or {}
        derived = summary.get("derived_refresh")
        if derived is None:
            # fallback: primo snapshot con module_availability derived_refresh
            derived = None
    return {
        "status": "preview",
        "schema_version": DERIVED_REBUILD_SCHEMA_VERSION,
        "run_id": run_id,
        "run_status": getattr(run, "status", None) if run is not None else None,
        "snapshots_found": 0,
        "snapshots_rebuildable": 0,
        "snapshots_partial": 0,
        "snapshots_blocked": 0,
        "market_results_to_replace": 0,
        "signals_to_rebuild": 0,
        "kpi_to_rebuild": 0,
        "missing_inputs_by_reason": {},
        "external_api_calls": 0,
        "full_scan_required": False,
        "full_scan_restarted": False,
        "signal_contract": contract,
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "audit_version": SIGNAL_AUDIT_VERSION,
        "market_registry_count": MARKET_REGISTRY_COUNT,
        "confirm_token_required": CONFIRM_TOKEN,
        "derived_refresh": derived,
        "classifications": [],
        "dry_run": True,
    }


def preflight_historical_run_derived_rebuild(
    db: Session,
    run_id: int,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Analisi read-only readiness rebuild derived. dry_run non scrive mai."""
    _ = dry_run  # esplicito: preflight non scrive
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if run is None:
        raise CecchinoLabImportError(
            REASON_RUN_NOT_FOUND,
            f"Run storico {run_id} non trovato",
            status_code=404,
        )

    payload = _base_preflight_payload(run_id=run_id, run=run)
    run_active = run.status in ACTIVE_STATUSES

    snaps = list(
        db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot)
            .where(CecchinoLabHistoricalMatchSnapshot.run_id == run_id)
            .order_by(CecchinoLabHistoricalMatchSnapshot.id.asc())
        ).all()
    )
    payload["snapshots_found"] = len(snaps)

    snap_ids = [int(s.id) for s in snaps]
    market_by_snap: dict[int, list[Any]] = defaultdict(list)
    if snap_ids:
        mrows = list(
            db.scalars(
                select(CecchinoLabHistoricalMarketResult).where(
                    CecchinoLabHistoricalMarketResult.run_id == run_id,
                    CecchinoLabHistoricalMarketResult.match_snapshot_id.in_(snap_ids),
                )
            ).all()
        )
        for row in mrows:
            market_by_snap[int(row.match_snapshot_id)].append(row)

    missing: dict[str, int] = _empty_missing_reasons()
    classifications: list[dict[str, Any]] = []
    rebuildable = partial = blocked = 0
    market_to_replace = signals_n = kpi_n = 0

    for snap in snaps:
        rows = market_by_snap.get(int(snap.id), [])
        cls = classify_snapshot_for_derived_rebuild(
            snap, market_rows=rows, run_active=run_active
        )
        classifications.append(cls)
        for reason in cls["reasons"]:
            missing[reason] += 1
        if cls["classification"] == CLASS_REBUILDABLE:
            rebuildable += 1
            if cls["signals_rebuildable"]:
                signals_n += 1
            if cls["market_results_rebuildable"]:
                kpi_n += 1
                market_to_replace += max(len(rows), MARKET_REGISTRY_COUNT)
        elif cls["classification"] == CLASS_PARTIAL:
            partial += 1
            if cls["signals_rebuildable"]:
                signals_n += 1
        else:
            blocked += 1

    payload["snapshots_rebuildable"] = rebuildable
    payload["snapshots_partial"] = partial
    payload["snapshots_blocked"] = blocked
    payload["market_results_to_replace"] = market_to_replace
    payload["signals_to_rebuild"] = signals_n
    payload["kpi_to_rebuild"] = kpi_n
    payload["missing_inputs_by_reason"] = dict(sorted(missing.items()))
    payload["classifications"] = classifications
    payload["run_active"] = run_active
    payload["external_api_calls"] = 0
    payload["full_scan_required"] = False
    payload["full_scan_restarted"] = False
    return payload


def _replace_market_results(
    db: Session,
    *,
    run_id: int,
    snap: CecchinoLabHistoricalMatchSnapshot,
    market_rows: list[dict[str, Any]],
) -> int:
    db.execute(
        delete(CecchinoLabHistoricalMarketResult).where(
            CecchinoLabHistoricalMarketResult.match_snapshot_id == int(snap.id),
            CecchinoLabHistoricalMarketResult.run_id == run_id,
        )
    )
    for row in market_rows:
        db.add(
            CecchinoLabHistoricalMarketResult(
                run_id=run_id,
                match_snapshot_id=int(snap.id),
                lab_match_id=int(snap.lab_match_id),
                market_key=row["market_key"],
                market_label=row.get("market_label"),
                period=row.get("period"),
                line=row.get("line"),
                quota_cecchino=row.get("quota_cecchino"),
                prob_cecchino=row.get("prob_cecchino"),
                quota_book=row.get("quota_book"),
                prob_book_raw=row.get("prob_book_raw"),
                prob_book_fair=row.get("prob_book_fair"),
                quote_source_type=row.get("quote_source_type"),
                is_real_book_quote=bool(row.get("is_real_book_quote")),
                is_derived_quote=bool(row.get("is_derived_quote")),
                derivation_method=row.get("derivation_method"),
                edge_pct=row.get("edge_pct"),
                vantaggio_prob=row.get("vantaggio_prob"),
                rating=row.get("rating"),
                signal_active=bool(row.get("signal_active")),
                signal_sources_json=row.get("signal_sources_json"),
                evaluation_status=row.get("evaluation_status"),
                won=row.get("won"),
                profit_1u_real=row.get("profit_1u_real"),
                profit_1u_synthetic=row.get("profit_1u_synthetic"),
                result_reason=row.get("result_reason"),
                profit_category=row.get("profit_category"),
            )
        )
    return len(market_rows)


def _apply_derived_refresh_meta(
    run: CecchinoLabHistoricalScanRun,
    *,
    applied_at: str,
    revision: dict[str, Any],
    snapshots_rebuilt: int,
) -> dict[str, Any]:
    meta = {
        "status": "completed",
        "applied_at": applied_at,
        "applied_git_commit": revision.get("git_commit"),
        "applied_git_commit_source": revision.get("git_commit_source"),
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "audit_version": SIGNAL_AUDIT_VERSION,
        "market_registry_count": MARKET_REGISTRY_COUNT,
        "source_run_git_commit": run.source_git_commit,
        "external_api_calls": 0,
        "full_scan_restarted": False,
        "snapshots_rebuilt": snapshots_rebuilt,
        "schema_version": DERIVED_REBUILD_SCHEMA_VERSION,
    }
    summary = dict(run.summary_json or {})
    summary["derived_refresh"] = meta
    run.summary_json = summary
    return meta


def _rebuild_one_snapshot(
    db: Session,
    *,
    run_id: int,
    snap: CecchinoLabHistoricalMatchSnapshot,
    market_rows_existing: list[Any],
) -> dict[str, Any]:
    cls = classify_snapshot_for_derived_rebuild(
        snap, market_rows=market_rows_existing, run_active=False
    )
    if cls["classification"] != CLASS_REBUILDABLE:
        return {"snapshot_id": snap.id, "status": "skipped", "classification": cls["classification"]}

    cecchino = _as_dict(snap.cecchino_output_json) or {}
    kpi = _as_dict(snap.historical_kpi_json) or {}
    quote_bundle, _src = _resolve_quote_bundle(snap, market_rows_existing)
    assert quote_bundle is not None
    under_odd = _extract_under_odd(
        cecchino_output=cecchino,
        historical_kpi=kpi,
        signals_json=_as_dict(snap.signals_json),
    )
    match = _match_proxy_from_snapshot(snap)

    # Freeze fields: non toccare input / hash / raw
    frozen_input = snap.input_snapshot_json
    frozen_hash = snap.pre_match_payload_sha256
    frozen_locked = snap.pre_match_locked_at

    signals = build_historical_signal_models(
        cecchino_output=cecchino,
        quote_bundle=quote_bundle,
        under_2_5_cecchino_odd=under_odd,
        contexts=None,
        match=match,
        settle=True,
    )
    market_rows = settle_historical_markets(
        match=match,
        kpi_panel=kpi,
        quote_bundle=quote_bundle,
        signals_json=signals,
    )
    sett_sum = settlement_summary(market_rows)

    snap.signals_json = signals
    snap.settlement_summary_json = sett_sum
    snap.settlement_status = "settled"
    # analytics summary su module_availability (senza sovrascrivere il resto)
    mod = dict(snap.module_availability_json or {})
    mod["signals_observation"] = (
        signals.get("observation_status") if isinstance(signals, dict) else None
    )
    mod["derived_refresh"] = {
        "status": "completed",
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "audit_version": SIGNAL_AUDIT_VERSION,
        "market_registry_count": MARKET_REGISTRY_COUNT,
        "external_api_calls": 0,
        "full_scan_restarted": False,
    }
    snap.module_availability_json = mod

    # Invarianti freeze
    snap.input_snapshot_json = frozen_input
    snap.pre_match_payload_sha256 = frozen_hash
    snap.pre_match_locked_at = frozen_locked

    n = _replace_market_results(db, run_id=run_id, snap=snap, market_rows=market_rows)
    return {
        "snapshot_id": int(snap.id),
        "status": "rebuilt",
        "markets_written": n,
        "signals_observation": signals.get("observation_status"),
    }


def rebuild_historical_run_derived_modules(
    db: Session,
    run_id: int,
    *,
    dry_run: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Preflight (dry_run) o apply rebuild derived V3 (confirm token richiesto)."""
    if dry_run:
        out = preflight_historical_run_derived_rebuild(db, run_id, dry_run=True)
        out["dry_run"] = True
        out["external_api_calls"] = 0
        out["full_scan_restarted"] = False
        return out

    if confirm != CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "confirm_required",
            f"Conferma richiesta: {CONFIRM_TOKEN}",
            status_code=400,
            details={"confirm_token_required": CONFIRM_TOKEN},
        )

    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if run is None:
        raise CecchinoLabImportError(
            REASON_RUN_NOT_FOUND,
            f"Run storico {run_id} non trovato",
            status_code=404,
        )
    if run.status in ACTIVE_STATUSES:
        raise CecchinoLabImportError(
            REASON_RUN_ACTIVE,
            f"Run in stato {run.status}: rebuild derived non consentito",
            status_code=409,
            details={"run_id": run_id, "run_status": run.status},
        )

    lock = _lock_for_run(run_id)
    if not lock.acquire(blocking=False):
        raise CecchinoLabImportError(
            "rebuild_in_progress",
            f"Rebuild derived già in corso per run {run_id}",
            status_code=409,
            details={"run_id": run_id},
        )

    try:
        # flag in summary per concurrency cross-process soft
        summary = dict(run.summary_json or {})
        existing = summary.get("derived_refresh") or {}
        if existing.get("status") == "running":
            raise CecchinoLabImportError(
                "rebuild_in_progress",
                f"Rebuild derived già in corso per run {run_id}",
                status_code=409,
            )
        summary["derived_refresh"] = {
            "status": "running",
            "started_at": _iso_now(),
            "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
            "external_api_calls": 0,
            "full_scan_restarted": False,
        }
        run.summary_json = summary
        db.flush()

        preflight = preflight_historical_run_derived_rebuild(db, run_id, dry_run=True)
        snaps = list(
            db.scalars(
                select(CecchinoLabHistoricalMatchSnapshot)
                .where(CecchinoLabHistoricalMatchSnapshot.run_id == run_id)
                .order_by(CecchinoLabHistoricalMatchSnapshot.id.asc())
            ).all()
        )
        snap_ids = [int(s.id) for s in snaps]
        market_by_snap: dict[int, list[Any]] = defaultdict(list)
        if snap_ids:
            mrows = list(
                db.scalars(
                    select(CecchinoLabHistoricalMarketResult).where(
                        CecchinoLabHistoricalMarketResult.run_id == run_id,
                        CecchinoLabHistoricalMarketResult.match_snapshot_id.in_(snap_ids),
                    )
                ).all()
            )
            for row in mrows:
                market_by_snap[int(row.match_snapshot_id)].append(row)

        rebuilt: list[dict[str, Any]] = []
        for snap in snaps:
            cls = classify_snapshot_for_derived_rebuild(
                snap,
                market_rows=market_by_snap.get(int(snap.id), []),
                run_active=False,
            )
            if cls["classification"] != CLASS_REBUILDABLE:
                continue
            result = _rebuild_one_snapshot(
                db,
                run_id=run_id,
                snap=snap,
                market_rows_existing=market_by_snap.get(int(snap.id), []),
            )
            rebuilt.append(result)

        # Non modificare source_git_commit del run
        original_commit = run.source_git_commit
        revision = resolve_code_revision()
        applied_at = _iso_now()
        meta = _apply_derived_refresh_meta(
            run,
            applied_at=applied_at,
            revision=revision,
            snapshots_rebuilt=len(rebuilt),
        )
        assert run.source_git_commit == original_commit

        db.commit()

        out = {
            **preflight,
            "status": "completed",
            "dry_run": False,
            "snapshots_rebuilt": len(rebuilt),
            "rebuilt": rebuilt,
            "derived_refresh": meta,
            "external_api_calls": 0,
            "full_scan_restarted": False,
            "full_scan_required": False,
            "signal_contract": get_current_signal_contract(),
            "confirm_token_required": CONFIRM_TOKEN,
        }
        return out
    except CecchinoLabImportError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("derived rebuild failed run_id=%s", run_id)
        try:
            run2 = db.get(CecchinoLabHistoricalScanRun, run_id)
            if run2 is not None:
                summary = dict(run2.summary_json or {})
                summary["derived_refresh"] = {
                    "status": "failed",
                    "failed_at": _iso_now(),
                    "error": str(exc)[:500],
                    "external_api_calls": 0,
                    "full_scan_restarted": False,
                }
                run2.summary_json = summary
                db.commit()
        except Exception:
            db.rollback()
        raise CecchinoLabImportError(
            "derived_rebuild_failed",
            f"Rebuild derived fallito: {exc}",
            status_code=500,
            details={"run_id": run_id},
        ) from exc
    finally:
        lock.release()
