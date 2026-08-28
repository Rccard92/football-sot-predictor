"""Orchestratore scansione storica Cecchino Lab (job resumibile, offline)."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.models.cecchino_lab_historical_scan_run import (
    ACTIVE_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    CecchinoLabHistoricalScanRun,
)
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION,
    HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
    HISTORICAL_PILOT_STRATEGY_MAX_MATCHES,
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
    HISTORICAL_QUOTE_REFERENCE_TIMING,
    HISTORICAL_SCAN_CONFIRM_TOKEN,
    HISTORICAL_SCAN_VERSION,
    HISTORICAL_SCAN_VERSION_V4,
    PARSER_VERSION,
)

from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_scan_preflight import (
    STATUS_BLOCKED,
    run_historical_scan_preflight,
)
from app.services.cecchino_data_lab.historical_scan_v3_executor import (
    build_run_summary_v3,
    execute_historical_scan_run_v3,
)
from app.services.cecchino_data_lab.historical_scan_v4_executor import (
    execute_historical_scan_run_v4,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_source_revision() -> dict[str, str | None]:
    """Compat: alias legacy source_* per persistenza run (comportamento invariato)."""
    from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields

    return revision_as_source_fields()


def _git_commit() -> str | None:
    return _resolve_source_revision().get("source_git_commit")


def _run_scope_meta(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
    policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
    return {
        "run_scope": policy.get("run_scope") or "full",
        "is_partial_run": bool(policy.get("is_partial_run")),
        "not_full_season_report": bool(policy.get("not_full_season_report")),
        "max_matches": policy.get("max_matches"),
        "pilot_strategy": policy.get("pilot_strategy"),
        "eligible_per_competition": policy.get("eligible_per_competition"),
        "module_policy": policy,
    }


def run_to_dict(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
    meta = _run_scope_meta(run)
    progress_detail = None
    if isinstance(run.summary_json, dict):
        progress_detail = run.summary_json.get("progress_detail")
    if progress_detail is None and isinstance(run.module_policy_json, dict):
        progress_detail = (run.module_policy_json or {}).get("progress_detail")
    return {
        "id": int(run.id),
        "season_label": run.season_label,
        "status": run.status,
        "scan_version": run.scan_version,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "current_dataset_id": run.current_dataset_id,
        "current_match_id": run.current_match_id,
        "current_competition": run.current_competition,
        "matches_total": int(run.matches_total or 0),
        "matches_processed": int(run.matches_processed or 0),
        "matches_eligible_core": int(run.matches_eligible_core or 0),
        "matches_excluded": int(run.matches_excluded or 0),
        "matches_error": int(run.matches_error or 0),
        "progress_pct": float(run.progress_pct) if run.progress_pct is not None else None,
        "progress_detail": progress_detail,
        "preflight": run.preflight_json,
        "summary": run.summary_json,
        "error": run.error_json,
        "source_git_commit": run.source_git_commit,
        "source_git_commit_source": getattr(run, "source_git_commit_source", None),
        "source_revision_status": getattr(run, "source_revision_status", None),
        "cancel_requested": bool(run.cancel_requested),
        "run_scope": meta["run_scope"],
        "is_partial_run": meta["is_partial_run"],
        "not_full_season_report": meta["not_full_season_report"],
        "max_matches": meta["max_matches"],
        "pilot_strategy": meta["pilot_strategy"],
        "eligible_per_competition": meta["eligible_per_competition"],
        "module_policy": meta["module_policy"],
    }


def list_historical_scans(db: Session, *, season_label: str | None = None) -> list[dict[str, Any]]:
    q = select(CecchinoLabHistoricalScanRun).order_by(CecchinoLabHistoricalScanRun.id.desc())
    if season_label:
        q = q.where(CecchinoLabHistoricalScanRun.season_label == season_label)
    return [run_to_dict(r) for r in db.scalars(q).all()]


def get_historical_scan(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    return run_to_dict(run)


def _normalize_max_matches(max_matches: Any) -> int | None:
    if max_matches is None or max_matches == "":
        return None
    try:
        value = int(max_matches)
    except (TypeError, ValueError) as exc:
        raise CecchinoLabImportError(
            "invalid_max_matches",
            "max_matches deve essere un intero positivo o null",
            status_code=400,
        ) from exc
    if value <= 0:
        raise CecchinoLabImportError(
            "invalid_max_matches",
            "max_matches deve essere un intero positivo o null",
            status_code=400,
        )
    return value


def _normalize_eligible_per_competition(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise CecchinoLabImportError(
            "invalid_eligible_per_competition",
            "eligible_per_competition deve essere un intero positivo",
            status_code=400,
        ) from exc
    if n <= 0:
        raise CecchinoLabImportError(
            "invalid_eligible_per_competition",
            "eligible_per_competition deve essere un intero positivo",
            status_code=400,
        )
    return n


def _rating_band_for_summary(rating: Any) -> str | None:
    """Fasce summary run: allineate a rating_band_dashboard (100 esclusivo)."""
    from app.services.cecchino_data_lab.historical_analytics_agg import rating_band_dashboard

    if rating is None:
        return None
    band = rating_band_dashboard(rating)
    return None if band == "unavailable" else band


def _purch_band_for_summary(score: Any) -> str | None:
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s < 20:
        return "0-19"
    if s < 40:
        return "20-39"
    if s < 60:
        return "40-59"
    if s < 80:
        return "60-79"
    return "80-100"


def _empty_profit_bucket() -> dict[str, Any]:
    return {
        "sample_size": 0,
        "real_quote_count": 0,
        "derived_quote_count": 0,
        "real_profit_1u": 0.0,
        "synthetic_profit_1u": 0.0,
    }


def _finalize_profit_bucket(b: dict[str, Any]) -> dict[str, Any]:
    real_n = int(b["real_quote_count"])
    der_n = int(b["derived_quote_count"])
    real_p = round(float(b["real_profit_1u"]), 4)
    synth_p = round(float(b["synthetic_profit_1u"]), 4)
    return {
        "sample_size": int(b["sample_size"]),
        "real_quote_count": real_n,
        "derived_quote_count": der_n,
        "real_profit_1u": real_p,
        "synthetic_profit_1u": synth_p,
        "real_roi_pct": round(100.0 * real_p / real_n, 2) if real_n else None,
        "synthetic_roi_pct": round(100.0 * synth_p / der_n, 2) if der_n else None,
    }


def _bump_profit_bucket(b: dict[str, Any], *, real: float | None, synthetic: float | None) -> None:
    b["sample_size"] += 1
    if real is not None:
        b["real_quote_count"] += 1
        b["real_profit_1u"] += float(real)
    if synthetic is not None:
        b["derived_quote_count"] += 1
        b["synthetic_profit_1u"] += float(synthetic)


def start_historical_scan(
    db: Session,
    *,
    season_label: str,
    confirm: str | None,
    max_matches: int | None = None,
    pilot_strategy: str | None = None,
    eligible_per_competition: int | None = None,
    background: bool = True,
) -> dict[str, Any]:
    if confirm != HISTORICAL_SCAN_CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "confirm_required",
            f"Conferma richiesta: {HISTORICAL_SCAN_CONFIRM_TOKEN}",
            status_code=400,
        )

    strategy = (pilot_strategy or "").strip() or None
    if strategy and strategy not in (
        HISTORICAL_PILOT_STRATEGY_MAX_MATCHES,
        HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
    ):
        raise CecchinoLabImportError(
            "invalid_pilot_strategy",
            "pilot_strategy non supportata",
            status_code=400,
        )

    normalized_max = _normalize_max_matches(max_matches)
    per_comp = None
    if strategy == HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP:
        per_comp = _normalize_eligible_per_competition(
            eligible_per_competition
            if eligible_per_competition is not None
            else HISTORICAL_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION
        )
        normalized_max = None
    elif normalized_max is not None and not strategy:
        strategy = HISTORICAL_PILOT_STRATEGY_MAX_MATCHES

    revision = _resolve_source_revision()
    is_partial = bool(strategy) or normalized_max is not None
    is_full = not is_partial
    if is_full and revision.get("source_revision_status") != "resolved":
        raise CecchinoLabImportError(
            "source_revision_unknown",
            "Revisione codice sconosciuta: impossibile avviare la scansione completa. "
            "Impostare RAILWAY_GIT_COMMIT_SHA / SOURCE_VERSION / GIT_COMMIT_SHA "
            "oppure eseguire in ambiente con repository git.",
            status_code=400,
            details=revision,
        )

    preflight = run_historical_scan_preflight(
        db,
        season_label=season_label,
        quote_policy_version=HISTORICAL_QUOTE_POLICY_VERSION_V4,
    )
    if preflight.get("status") == STATUS_BLOCKED:
        raise CecchinoLabImportError(
            "preflight_blocked",
            "Preflight bloccato: impossibile avviare la scansione",
            status_code=400,
            details=preflight,
        )

    active = db.scalars(
        select(CecchinoLabHistoricalScanRun).where(
            CecchinoLabHistoricalScanRun.season_label == season_label,
            CecchinoLabHistoricalScanRun.status.in_(tuple(ACTIVE_STATUSES)),
        )
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste già un run attivo (id={active.id}) per {season_label}",
            status_code=409,
            details={"active_run_id": int(active.id)},
        )

    datasets = list(
        db.scalars(
            select(CecchinoLabDataset).where(CecchinoLabDataset.season_label == season_label)
        ).all()
    )
    dataset_ids = [int(d.id) for d in datasets]
    season_match_count = (
        len(
            db.scalars(
                select(CecchinoLabMatch.id).where(CecchinoLabMatch.dataset_id.in_(dataset_ids))
            ).all()
        )
        if dataset_ids
        else 0
    )
    competitions = sorted({d.competition_name for d in datasets})
    n_comp = len(competitions)

    if strategy == HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP:
        run_scope = "balanced_pilot"
        matches_total = int(per_comp or 0) * max(n_comp, 1)
        is_partial = True
    elif normalized_max is not None:
        run_scope = "pilot"
        matches_total = min(season_match_count, normalized_max)
        is_partial = True
    else:
        run_scope = "full"
        matches_total = season_match_count
        is_partial = False

    policy_warnings: list[str] = []
    if is_partial and revision.get("source_revision_status") != "resolved":
        policy_warnings.append(
            "source_revision_unknown_on_pilot: revisione codice sconosciuta; "
            "il run pilota è consentito ma la riproducibilità è limitata"
        )

    eligible_target_total = None
    if strategy == HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP:
        eligible_target_total = int(per_comp) * n_comp

    run = CecchinoLabHistoricalScanRun(
        season_label=season_label,
        status=STATUS_PENDING,
        scan_version=HISTORICAL_SCAN_VERSION_V4,
        requested_at=_utcnow(),
        matches_total=matches_total,
        quote_policy_json={
            "version": HISTORICAL_QUOTE_POLICY_VERSION_V4,
            "reference_timing": HISTORICAL_QUOTE_REFERENCE_TIMING,
            "bookmaker": "Bet365",
            "provider_source": "football-data.co.uk / Bet365",
            "operational_today_bookmaker": "Betfair",
            "no_closing_fallback": True,
        },
        module_policy_json={
            "goal_intensity": "historical_v4_canonical_pillars",
            "purchasability": "historical_v4_v35_v2_canonical",
            "signal_models": "A-F",
            "parser_version": PARSER_VERSION,
            "scan_version": HISTORICAL_SCAN_VERSION_V4,
            "feature_contract_version": "cecchino_lab_historical_feature_contract_v4",
            "max_matches": normalized_max,
            "pilot_strategy": strategy,
            "eligible_per_competition": per_comp,
            "is_partial_run": is_partial,
            "not_full_season_report": is_partial,
            "run_scope": run_scope,
            "season_matches_available": season_match_count,
            "competitions_total": n_comp,
            "eligible_target_total": eligible_target_total,
            "revision_warnings": policy_warnings,
            "note": (
                "Run parziale: non confondere con report stagione completa"
                if is_partial
                else "Run stagione completa"
            ),
        },
        preflight_json=preflight,
        source_git_commit=revision.get("source_git_commit"),
        source_git_commit_source=revision.get("source_git_commit_source"),
        source_revision_status=revision.get("source_revision_status"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if background:
        _spawn_worker(int(run.id))
    else:
        execute_historical_scan_run(int(run.id))
        db.refresh(run)

    return run_to_dict(run)


def resume_historical_scan(db: Session, run_id: int, *, background: bool = True) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    if run.status in (STATUS_COMPLETED, STATUS_COMPLETED_WITH_WARNINGS):
        raise CecchinoLabImportError("run_already_completed", "Run già completato", status_code=400)
    if run.status == STATUS_CANCELLED:
        raise CecchinoLabImportError("run_cancelled", "Run cancellato", status_code=400)

    active = db.scalars(
        select(CecchinoLabHistoricalScanRun).where(
            CecchinoLabHistoricalScanRun.season_label == run.season_label,
            CecchinoLabHistoricalScanRun.status.in_(tuple(ACTIVE_STATUSES)),
            CecchinoLabHistoricalScanRun.id != run_id,
        )
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Altro run attivo sulla stagione (id={active.id})",
            status_code=409,
        )

    run.cancel_requested = False
    if run.status == STATUS_FAILED:
        run.status = STATUS_PENDING
    db.commit()

    if background:
        _spawn_worker(run_id)
    else:
        execute_historical_scan_run(run_id)
    db.refresh(run)
    return run_to_dict(run)


def cancel_historical_scan(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    run.cancel_requested = True
    if run.status in ACTIVE_STATUSES:
        run.status = STATUS_CANCELLED
        run.completed_at = _utcnow()
    db.commit()
    db.refresh(run)
    return run_to_dict(run)


def _spawn_worker(run_id: int) -> None:
    with _lock:
        t_existing = _active_threads.get(run_id)
        if t_existing and t_existing.is_alive():
            return
        t = threading.Thread(
            target=execute_historical_scan_run,
            args=(run_id,),
            name=f"cecchino-lab-hist-scan-{run_id}",
            daemon=True,
        )
        _active_threads[run_id] = t
        t.start()


def execute_historical_scan_run(run_id: int) -> None:
    """Router per scan_version — V3 congelato, V4 stream cronologico globale."""
    db = SessionLocal()
    try:
        run = db.get(CecchinoLabHistoricalScanRun, run_id)
        if not run:
            return
        version = str(run.scan_version or HISTORICAL_SCAN_VERSION)
    finally:
        db.close()
    if version == HISTORICAL_SCAN_VERSION_V4:
        execute_historical_scan_run_v4(run_id)
    else:
        execute_historical_scan_run_v3(run_id)
    with _lock:
        _active_threads.pop(run_id, None)


def _build_run_summary(db: Session, run_id: int) -> dict[str, Any]:
    return build_run_summary_v3(db, run_id)


def list_run_matches(
    db: Session,
    run_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
    eligibility: str | None = None,
) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    q = (
        select(CecchinoLabHistoricalMatchSnapshot)
        .where(CecchinoLabHistoricalMatchSnapshot.run_id == run_id)
        .order_by(CecchinoLabHistoricalMatchSnapshot.chronological_order.asc().nulls_last())
    )
    if eligibility:
        q = q.where(
            CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status == eligibility
        )
    rows = list(db.scalars(q.offset(offset).limit(limit)).all())
    return {
        "run_id": run_id,
        "items": [
            {
                "id": int(s.id),
                "lab_match_id": int(s.lab_match_id),
                "competition_name": s.competition_name,
                "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                "home_team": s.home_team,
                "away_team": s.away_team,
                "eligibility": s.historical_eligibility_status,
                "reason": s.historical_eligibility_reason,
                "pre_match_payload_sha256": s.pre_match_payload_sha256,
                "settlement_summary": s.settlement_summary_json,
            }
            for s in rows
        ],
        "limit": limit,
        "offset": offset,
    }
