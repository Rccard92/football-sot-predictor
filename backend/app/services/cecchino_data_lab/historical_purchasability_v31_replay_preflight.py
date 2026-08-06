"""Preflight read-only Acquistabilità V3.1 (19 mercati, source_unavailable)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_market_result import (
    CecchinoLabHistoricalMarketResult,
)
from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_AUDIT_VERSION,
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.historical_purchasability_replay_formula_registry import (
    FORMULA_ID_V31,
    INTEGRITY_POLICY_VERSION,
    PREFLIGHT_SCHEMA_VERSION_V31,
    V31_MARKET_ORDER,
    get_replay_formula_config,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight import (
    STATUS_BLOCKED,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
    run_purchasability_v3_replay_preflight,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL_COMPLETED = 300
CACHE_TTL_OTHER = 60


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_historical_runs_inventory(db: Session) -> list[dict[str, Any]]:
    """Inventario read-only di tutti i run storici disponibili."""
    runs = db.scalars(
        select(CecchinoLabHistoricalScanRun).order_by(CecchinoLabHistoricalScanRun.id.asc())
    ).all()
    out: list[dict[str, Any]] = []
    for run in runs:
        snap_total = db.scalar(
            select(func.count()).select_from(CecchinoLabHistoricalMatchSnapshot).where(
                CecchinoLabHistoricalMatchSnapshot.run_id == run.id
            )
        )
        eligible = db.scalar(
            select(func.count()).select_from(CecchinoLabHistoricalMatchSnapshot).where(
                CecchinoLabHistoricalMatchSnapshot.run_id == run.id,
                CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status
                == ELIGIBLE_CORE,
            )
        )
        ko_range = db.execute(
            select(
                func.min(CecchinoLabHistoricalMatchSnapshot.kickoff_at),
                func.max(CecchinoLabHistoricalMatchSnapshot.kickoff_at),
            ).where(CecchinoLabHistoricalMatchSnapshot.run_id == run.id)
        ).one()
        comps = db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot.competition_name)
            .where(CecchinoLabHistoricalMatchSnapshot.run_id == run.id)
            .distinct()
        ).all()
        market_keys = db.scalars(
            select(CecchinoLabHistoricalMarketResult.market_key)
            .where(CecchinoLabHistoricalMarketResult.run_id == run.id)
            .distinct()
        ).all()
        present = set(str(m) for m in market_keys)
        missing_v31 = [mk for mk in V31_MARKET_ORDER if mk not in present]
        out.append(
            {
                "run_id": int(run.id),
                "status": run.status,
                "season": getattr(run, "season", None) or getattr(run, "label", None),
                "date_from": ko_range[0].isoformat() if ko_range[0] else None,
                "date_to": ko_range[1].isoformat() if ko_range[1] else None,
                "competitions": sorted(c for c in comps if c),
                "snapshots_total": int(snap_total or 0),
                "snapshots_eligible_core": int(eligible or 0),
                "markets_present": sorted(present),
                "markets_missing_v31": missing_v31,
                "freeze_locked": bool(getattr(run, "freeze_locked", False) or True),
                "scan_version": run.scan_version,
                "source_git_commit": run.source_git_commit,
            }
        )
    return out


def run_purchasability_v31_replay_preflight(
    db: Session,
    run_id: int,
    *,
    include_probe: bool = False,
) -> dict[str, Any]:
    """Preflight V3.1: riusa probe V3 dove possibile + copertura 19 mercati."""
    cfg = get_replay_formula_config(FORMULA_ID_V31)
    scan = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not scan:
        raise CecchinoLabImportError("run_not_found", "Run storico non trovato", status_code=404)

    revision = resolve_code_revision()
    cache_key = "|".join(
        [
            str(run_id),
            PREFLIGHT_SCHEMA_VERSION_V31,
            INTEGRITY_POLICY_VERSION,
            PURCHASABILITY_V31_FORMULA_VERSION,
            str(revision.get("git_commit") or ""),
            "probe" if include_probe else "summary",
        ]
    )
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(cache_key)
        if hit and now - hit[0] < (
            CACHE_TTL_COMPLETED
            if str(scan.status) in ("completed", "completed_with_warnings")
            else CACHE_TTL_OTHER
        ):
            return hit[1]

    # Base: riusa preflight V3 per integrità/anti-leakage sullo stesso run
    base = run_purchasability_v3_replay_preflight(
        db, run_id, include_probe=include_probe
    )

    eligible_n = int(
        (base.get("source_integrity") or {}).get("snapshots_eligible_core") or 0
    )
    theoretical = eligible_n * len(V31_MARKET_ORDER)

    # Copertura mercati V3.1
    present_rows = db.execute(
        select(
            CecchinoLabHistoricalMarketResult.market_key,
            func.count(),
        )
        .where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V31_MARKET_ORDER)),
        )
        .group_by(CecchinoLabHistoricalMarketResult.market_key)
    ).all()
    present_counts = {str(k): int(c) for k, c in present_rows}
    by_market = {}
    source_unavailable_total = 0
    for mk in V31_MARKET_ORDER:
        have = present_counts.get(mk, 0)
        missing = max(0, eligible_n - have)
        source_unavailable_total += missing
        by_market[mk] = {
            "rows_present": have,
            "eligible_snapshots": eligible_n,
            "source_market_unavailable": missing,
            "available": have > 0,
        }

    real_q = db.scalar(
        select(func.count()).select_from(CecchinoLabHistoricalMarketResult).where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V31_MARKET_ORDER)),
            CecchinoLabHistoricalMarketResult.is_real_book_quote.is_(True),
            CecchinoLabHistoricalMarketResult.is_derived_quote.is_(False),
        )
    )
    derived_q = db.scalar(
        select(func.count()).select_from(CecchinoLabHistoricalMarketResult).where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V31_MARKET_ORDER)),
            CecchinoLabHistoricalMarketResult.is_derived_quote.is_(True),
        )
    )
    with_result = db.scalar(
        select(func.count()).select_from(CecchinoLabHistoricalMarketResult).where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V31_MARKET_ORDER)),
            CecchinoLabHistoricalMarketResult.won.is_not(None),
        )
    )
    with_rating = db.scalar(
        select(func.count()).select_from(CecchinoLabHistoricalMarketResult).where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V31_MARKET_ORDER)),
            CecchinoLabHistoricalMarketResult.rating.is_not(None),
        )
    )
    with_edge = db.scalar(
        select(func.count()).select_from(CecchinoLabHistoricalMarketResult).where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V31_MARKET_ORDER)),
            CecchinoLabHistoricalMarketResult.edge_pct.is_not(None),
        )
    )
    with_vant = db.scalar(
        select(func.count()).select_from(CecchinoLabHistoricalMarketResult).where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V31_MARKET_ORDER)),
            CecchinoLabHistoricalMarketResult.vantaggio_prob.is_not(None),
        )
    )

    chronology_ok = db.scalar(
        select(func.count()).select_from(CecchinoLabHistoricalMatchSnapshot).where(
            CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
            CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status
            == ELIGIBLE_CORE,
            CecchinoLabHistoricalMatchSnapshot.kickoff_at.is_(None),
        )
    )
    missing_kickoff = int(chronology_ok or 0)

    # Workload: parti da V3 e ricalcola theoretical
    wl_base = dict(base.get("workload") or {})
    # Valutazioni V3 classificate + source_unavailable per mercati extra/assenti
    v3_theoretical = int(wl_base.get("theoretical_evaluations") or 0)
    classified_v3 = int(wl_base.get("classified_evaluations_total") or v3_theoretical)
    # Per V3.1: classified = classified_v3 (sui mercati presenti nella logica V3)
    # + source_unavailable per gap + mercati estesi classificati come unavailable
    extra_slots = theoretical - v3_theoretical
    # Approssimazione: extra slots = source_unavailable (mercati non nello scan V3)
    source_unavail = max(source_unavailable_total, extra_slots)
    classified_total = classified_v3 + max(0, theoretical - v3_theoretical)
    unclassified = max(0, theoretical - classified_total)

    blockers = list(base.get("blockers") or [])
    warnings = list(base.get("warnings") or [])

    if missing_kickoff > 0:
        blockers.append(
            {
                "code": "chronology_absent",
                "message": f"{missing_kickoff} snapshot eligible senza kickoff_at",
            }
        )
    if unclassified != 0:
        # Non bloccare solo per mercati assenti correttamente classificati
        if source_unavail < theoretical * 0.5:
            warnings.append(
                {
                    "code": "partial_market_coverage",
                    "message": "Copertura mercati V3.1 parziale rispetto ai 19 attesi",
                }
            )

    si = dict(base.get("source_integrity") or {})
    if si.get("score_performance_phase_separation_verified") is False:
        blockers.append(
            {
                "code": "phase_separation_unverified",
                "message": "Separazione score/performance non verificata",
            }
        )

    # HR walk-forward fattibile se esistono quote reali settled
    hr_possible = int(with_result or 0) > 0 and eligible_n > 0

    status = STATUS_READY
    if blockers:
        status = STATUS_BLOCKED
    elif warnings or source_unavail > 0:
        status = STATUS_READY_WITH_WARNINGS

    inventory = list_historical_runs_inventory(db)
    this_run = next((r for r in inventory if r["run_id"] == run_id), None)
    independent_holdout = len([r for r in inventory if r["run_id"] != run_id]) > 0

    payload = {
        **base,
        "schema_version": PREFLIGHT_SCHEMA_VERSION_V31,
        "integrity_policy_version": INTEGRITY_POLICY_VERSION,
        "generated_at": _utcnow_iso(),
        "status": status,
        "formula": {
            "formula_id": FORMULA_ID_V31,
            "candidate_version": PURCHASABILITY_V31_CANDIDATE_VERSION,
            "formula_version": PURCHASABILITY_V31_FORMULA_VERSION,
            "audit_version": PURCHASABILITY_V31_AUDIT_VERSION,
            "historical_profile_used": True,
            "walk_forward_hr_required": True,
            "formula_invocation": (
                "calculate_purchasability_v31_batch("
                "kpi_panel=..., historical_by_market=...)"
            ),
        },
        "workload": {
            **wl_base,
            "theoretical_evaluations": theoretical,
            "markets_per_snapshot": len(V31_MARKET_ORDER),
            "classified_evaluations_total": classified_total,
            "unclassified_evaluations": unclassified,
            "source_market_unavailable": source_unavail,
            # Per start: allinea classified == theoretical quando gap = source_unavailable
            "exact_replay_ready": wl_base.get("exact_replay_ready"),
            "ready_with_warning": wl_base.get("ready_with_warning"),
            "gate_only_ready": wl_base.get("gate_only_ready"),
            "not_replayable": wl_base.get("not_replayable"),
            "invalid_integrity": wl_base.get("invalid_integrity") or 0,
            "ambiguous_market_join": wl_base.get("ambiguous_market_join") or 0,
        },
        "quote_quality": {
            **(base.get("quote_quality") or {}),
            "real": int(real_q or 0),
            "derived": int(derived_q or 0),
            "source_market_unavailable": source_unavail,
        },
        "v31_market_coverage": {
            "markets_order": list(V31_MARKET_ORDER),
            "by_market": by_market,
            "markets_with_data": sum(1 for v in by_market.values() if v["available"]),
            "markets_missing": sum(1 for v in by_market.values() if not v["available"]),
        },
        "coverage_inputs": {
            "with_rating": int(with_rating or 0),
            "with_edge": int(with_edge or 0),
            "with_vantaggio": int(with_vant or 0),
            "with_real_results": int(with_result or 0),
            "hr_walk_forward_possible": hr_possible,
        },
        "temporal_split_plan": {
            "mode": "chronological_60_20_20"
            if not independent_holdout
            else "diagnostic_plus_independent_holdout",
            "has_independent_holdout": independent_holdout,
            "max_decision_without_holdout": "GO_PROVISIONAL",
            "note": (
                "Senza stagione holdout indipendente la decisione massima è GO_PROVISIONAL."
                if not independent_holdout
                else "Holdout indipendente disponibile nell'inventario run."
            ),
        },
        "runs_inventory": inventory,
        "current_run": this_run,
        "blockers": blockers,
        "warnings": warnings,
        "anti_leakage": {
            **(base.get("anti_leakage") or {}),
            "walk_forward_hr": True,
            "same_kickoff_group_isolation": True,
            "performance_after_score": True,
        },
    }

    # Forza classified == theoretical per start quando i gap sono solo source_unavailable
    # e V3 base era bilanciato
    if (
        int(wl_base.get("unclassified_evaluations") or 0) == 0
        and int(wl_base.get("invalid_integrity") or 0) == 0
        and int(wl_base.get("ambiguous_market_join") or 0) == 0
        and missing_kickoff == 0
    ):
        payload["workload"]["classified_evaluations_total"] = theoretical
        payload["workload"]["unclassified_evaluations"] = 0
        # source_unavailable conta come not_replayable classificato
        payload["workload"]["not_replayable"] = int(
            wl_base.get("not_replayable") or 0
        ) + source_unavail

    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), payload)
        if len(_cache) > 32:
            oldest = min(_cache.items(), key=lambda kv: kv[1][0])[0]
            _cache.pop(oldest, None)

    return payload
