"""Facade canonico Intensità Goal Avanzata v5.

Delega al motore preview frozen senza duplicare formule.
API pubbliche per Today, monitoring, settlement fail-soft.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    SNAPSHOT_COMPLETED,
    SNAPSHOT_ERROR,
    SNAPSHOT_INCOMPLETE,
    SNAPSHOT_LOCKED,
    SNAPSHOT_PENDING,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_intensity_v5_dimension_registry import (
    GOAL_INTENSITY_V5_DIMENSION_REGISTRY_VERSION,
    build_dimensions_from_snapshots,
)
from app.services.cecchino.cecchino_goal_intensity_v5_monitoring_adapter import (
    normalize_goal_v5_monitoring_contract,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    MINIMUM_PROSPECTIVE_MATCHES,
    VERSION as BUNDLE_VERSION,
    _bundle_summary,
    _utc_now,
    build_prospective_monitoring,
    compute_snapshot_for_today_row,
    get_active_bundle,
    get_preview_detail,
    list_preview_snapshots,
    safe_preview_after_today_scan,
)
from app.services.cecchino.cecchino_goal_intensity_v5_readiness_policy import (
    GOAL_INTENSITY_V5_EXPORT_VERSION,
    GOAL_INTENSITY_V5_MONITORING_VERSION,
    GOAL_INTENSITY_V5_READINESS_POLICY_VERSION,
    GOAL_INTENSITY_V5_READINESS_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

logger = logging.getLogger(__name__)

__all__ = [
    "BUNDLE_VERSION",
    "GOAL_INTENSITY_V5_MONITORING_VERSION",
    "GOAL_INTENSITY_V5_READINESS_VERSION",
    "GOAL_INTENSITY_V5_READINESS_POLICY_VERSION",
    "GOAL_INTENSITY_V5_EXPORT_VERSION",
    "MINIMUM_PROSPECTIVE_MATCHES",
    "get_active_bundle",
    "get_snapshot_for_today",
    "build_today_payload",
    "compute_snapshot",
    "safe_after_today_scan",
    "attach_results_for_rows",
    "build_overview",
    "build_dimensions",
    "build_candidates",
    "build_prospective_results",
    "build_calibration",
    "build_stability",
    "build_data_health",
    "list_snapshots",
]


def get_snapshot_for_today(db: Session, today_fixture_id: int) -> dict[str, Any]:
    return get_preview_detail(db, today_fixture_id)


def build_today_payload(db: Session, today_fixture_id: int) -> dict[str, Any]:
    """Payload canonico Today: una sola lettura DB."""
    detail = get_preview_detail(db, today_fixture_id)
    if detail.get("status") == "error":
        err = detail.get("error")
        if err in {"bundle_missing", "snapshot_not_found"}:
            base = {
                "status": "unavailable",
                "error": err,
                "message": "Snapshot prospettico non disponibile",
                "version": BUNDLE_VERSION,
                "operational_status": "preview_monitored",
                "operational_status_label_it": "Preview monitorata",
                "signals_integration_status": "blocked",
                "no_betting_signals": True,
            }
        else:
            base = {
                **detail,
                "operational_status": "preview_monitored",
                "operational_status_label_it": "Preview monitorata",
                "signals_integration_status": "blocked",
            }
    else:
        base = {
            **detail,
            "banner": (
                "Quattro dimensioni distinte della struttura goal, monitorate su "
                "snapshot prospettici pre-match."
            ),
            "operational_status": "preview_monitored",
            "operational_status_label_it": "Preview monitorata",
            "signals_integration_status": "blocked",
            "signals_integration_status_label_it": "Bloccata",
            "calibrated_estimate_label_it": "Stima calibrata research",
        }
    return make_json_safe(base)


def compute_snapshot(db: Session, today_row: CecchinoTodayFixture) -> dict[str, Any]:
    return compute_snapshot_for_today_row(db, today_row)


def safe_after_today_scan(db: Session, today_fixture_id: int) -> dict[str, Any]:
    return safe_preview_after_today_scan(db, today_fixture_id)


def attach_results_for_rows(
    db: Session,
    rows: list[CecchinoTodayFixture],
    *,
    commit: bool = False,
) -> dict[str, Any]:
    """Collega FT agli snapshot senza ricalcolare score. Fail-soft per riga.

    Non chiama commit interni del helper preview (evita interferenze con la sessione Today).
    """
    from datetime import timedelta

    from app.models.cecchino_today_fixture import MATCH_FINISHED
    from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
        _ensure_utc,
        _load_fixture,
    )
    from app.services.cecchino.cecchino_goal_intensity_v5_readiness import (
        clear_goal_intensity_v5_readiness_cache,
    )

    bundle = get_active_bundle(db)
    if bundle is None:
        return {
            "status": "skipped",
            "reason": "bundle_missing",
            "attached": 0,
            "skipped_by_reason": {"bundle_missing": len(rows)},
        }
    now = _utc_now()
    attached = 0
    errors = 0
    skipped_by_reason: dict[str, int] = defaultdict(int)
    for row in rows:
        try:
            snap = db.scalars(
                select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                    CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id,
                    CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id
                    == int(row.id),
                )
            ).first()
            if snap is None:
                skipped_by_reason["snapshot_missing"] += 1
                continue
            if snap.result_attached_at is not None:
                skipped_by_reason["already_attached"] += 1
                continue
            if str(snap.snapshot_status or "") in {
                SNAPSHOT_ERROR,
            }:
                skipped_by_reason["snapshot_error"] += 1
                continue
            home = getattr(row, "goals_home", None)
            away = getattr(row, "goals_away", None)
            if home is None:
                home = getattr(row, "score_fulltime_home", None)
                away = getattr(row, "score_fulltime_away", None)
            match_status = str(
                getattr(row, "match_display_status", "")
                or getattr(row, "fixture_status", "")
                or ""
            )
            local = _load_fixture(db, snap.local_fixture_id)
            if home is None and local is not None:
                home = getattr(local, "goals_home", None)
                away = getattr(local, "goals_away", None)
            if home is None or away is None:
                skipped_by_reason["score_missing"] += 1
                continue
            finished_codes = {
                MATCH_FINISHED,
                "finished",
                "FT",
                "AET",
                "PEN",
                "Match Finished",
            }
            local_status = str(getattr(local, "status_short", "") or "")
            if match_status not in finished_codes and local_status not in {
                "FT",
                "AET",
                "PEN",
            }:
                kickoff = _ensure_utc(snap.kickoff)
                if kickoff is None or now < kickoff + timedelta(hours=1.5):
                    skipped_by_reason["pre_kickoff_or_not_finished"] += 1
                    continue
            total = int(home) + int(away)
            snap.goals_home_ft = int(home)
            snap.goals_away_ft = int(away)
            snap.total_goals_ft = total
            snap.goals_ge_2 = int(total >= 2)
            snap.goals_ge_3 = int(total >= 3)
            snap.btts_ft = int(int(home) > 0 and int(away) > 0)
            snap.result_attached_at = now
            snap.snapshot_status = SNAPSHOT_COMPLETED
            if snap.locked_at is None:
                snap.locked_at = now
            attached += 1
        except Exception:
            errors += 1
            skipped_by_reason["exception"] += 1
            logger.exception(
                "goal_intensity_v5 attach skipped today_fixture_id=%s",
                getattr(row, "id", None),
            )
    if attached:
        db.flush()
        clear_goal_intensity_v5_readiness_cache()
    if commit and attached:
        try:
            db.commit()
        except Exception:
            logger.exception("goal_intensity_v5 attach commit failed")
    return {
        "status": "ok",
        "attached": attached,
        "errors": errors,
        "bundle_id": bundle.id,
        "skipped_by_reason": dict(skipped_by_reason),
    }


def _filter_snaps(
    snaps: list[CecchinoGoalIntensityV5PreviewSnapshot],
    *,
    date_from: date | None,
    date_to: date | None,
    competition_id: int | None,
    snapshot_status: str | None,
) -> list[CecchinoGoalIntensityV5PreviewSnapshot]:
    out = []
    for s in snaps:
        if date_from and s.scan_date and s.scan_date < date_from:
            continue
        if date_to and s.scan_date and s.scan_date > date_to:
            continue
        if competition_id is not None and s.competition_id != competition_id:
            continue
        if snapshot_status and s.snapshot_status != snapshot_status:
            continue
        out.append(s)
    return out


def _goal_monitoring_context(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> tuple[Any, dict[str, Any], list[CecchinoGoalIntensityV5PreviewSnapshot], dict[str, Any]]:
    bundle = get_active_bundle(db)
    monitoring = build_prospective_monitoring(db, bundle)
    if bundle is None:
        normalized = normalize_goal_v5_monitoring_contract(monitoring=monitoring)
        return None, monitoring, [], normalized
    all_snaps = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
            )
        ).all()
    )
    summary = _bundle_summary(bundle, db)
    normalized = normalize_goal_v5_monitoring_contract(
        monitoring=monitoring,
        snapshots=all_snaps,
        bundle_summary=summary,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return bundle, monitoring, all_snaps, normalized


def build_overview(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    bundle, monitoring, all_snaps, normalized = _goal_monitoring_context(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    if bundle is None:
        return make_json_safe(
            {
                "status": "error",
                "error": "bundle_missing",
                "operational_status": "preview_monitored",
                "operational_status_label_it": "Preview monitorata",
                "scientific_maturity": "prospective_not_started",
                "signals_integration_status": "blocked",
                "current_decision": "continue_monitoring",
                "monitoring_version": GOAL_INTENSITY_V5_MONITORING_VERSION,
            }
        )
    period = _filter_snaps(
        all_snaps,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        snapshot_status=None,
    )
    completed = [
        s
        for s in all_snaps
        if s.snapshot_status == SNAPSHOT_COMPLETED and s.result_attached_at
    ]
    n_completed = normalized.get("completed_snapshots", len(completed))
    if len(all_snaps) == 0:
        maturity = "prospective_not_started"
        maturity_it = "Raccolta prospettica non iniziata"
    elif n_completed == 0:
        maturity = "prospective_collecting"
        maturity_it = "Raccolta prospettica in corso"
    elif n_completed < MINIMUM_PROSPECTIVE_MATCHES:
        maturity = "insufficient_completed_sample"
        maturity_it = "Campione completed insufficiente"
    else:
        maturity = "validation_in_progress"
        maturity_it = "Valutazione in corso"

    scan_dates = sorted(s.scan_date for s in all_snaps if s.scan_date)
    completed_dates = sorted(
        (s.result_attached_at.date() if s.result_attached_at else s.scan_date)
        for s in completed
        if s.result_attached_at or s.scan_date
    )
    summary = _bundle_summary(bundle, db)
    return make_json_safe(
        {
            "status": "ok",
            "monitoring_version": GOAL_INTENSITY_V5_MONITORING_VERSION,
            "bundle_version": bundle.version,
            "operational_status": "preview_monitored",
            "operational_status_label_it": "Preview monitorata",
            "scientific_maturity": maturity,
            "scientific_maturity_label_it": maturity_it,
            "signals_integration_status": "blocked",
            "signals_integration_status_label_it": "Bloccata",
            "current_decision": "continue_monitoring",
            "current_decision_label_it": "Continua monitoraggio",
            "coverage_global": normalized.get("coverage_global"),
            "coverage_in_period": normalized.get("coverage_in_period"),
            "coverage": {
                "snapshots_global": normalized.get("total_snapshots", len(all_snaps)),
                "snapshots_in_period": len(period),
                "pending": normalized.get("pending_snapshots", 0),
                "completed": normalized.get("completed_snapshots", n_completed),
                "incomplete_or_error": int(normalized.get("incomplete_snapshots", 0))
                + int(normalized.get("error_snapshots", 0)),
                "minimum_prospective_matches": MINIMUM_PROSPECTIVE_MATCHES,
            },
            "candidates": {
                "primary": summary.get("primary_candidate") or "GI_A_STRICT_CORE",
                "challenger": "GI_B_RECENCY",
                "benchmark": "MT1_LONG_TERM",
                "diagnostic": "GI_A_without_volatility",
            },
            "period": {
                "first_snapshot": scan_dates[0].isoformat() if scan_dates else None,
                "last_snapshot": scan_dates[-1].isoformat() if scan_dates else None,
                "first_completed": completed_dates[0].isoformat()
                if completed_dates
                else None,
                "prospective_calendar_days": (
                    (scan_dates[-1] - scan_dates[0]).days + 1 if len(scan_dates) >= 2 else len(scan_dates)
                ),
            },
            "monitoring_normalized": normalized,
            "prospective_monitoring": monitoring,
            "filters": {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "competition_id": competition_id,
            },
        }
    )


def build_dimensions(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    bundle = get_active_bundle(db)
    if bundle is None:
        return make_json_safe({"status": "error", "error": "bundle_missing"})
    snaps = _filter_snaps(
        list(
            db.scalars(
                select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                    CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
                )
            ).all()
        ),
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        snapshot_status=None,
    )
    dims = build_dimensions_from_snapshots(snaps)
    dims_list = [
        {
            "key": d.get("key"),
            "label": d.get("label_it"),
            "components": [
                {
                    "key": m.get("key"),
                    "label": m.get("label"),
                    "description": (
                        f"n={m.get('n')} missing={m.get('missing')} "
                        f"mean={m.get('mean')} median={m.get('median')}"
                        if m.get("n") is not None
                        else None
                    ),
                }
                for m in (d.get("metrics") or [])
            ],
        }
        for d in dims.values()
    ]
    return make_json_safe(
        {
            "status": "ok",
            "terminology": "quattro dimensioni distinte",
            "registry_version": GOAL_INTENSITY_V5_DIMENSION_REGISTRY_VERSION,
            "snapshot_count": len(snaps),
            "dimensions": dims,
            "dimensions_list": dims_list,
            "dependency_note": "Le dimensioni sono distinte; indipendenza statistica non assunta.",
            "filters": {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "competition_id": competition_id,
            },
        }
    )


def build_candidates(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    _, monitoring, _, normalized = _goal_monitoring_context(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    metrics = (monitoring.get("metrics_by_candidate") or {}) if isinstance(monitoring, dict) else {}
    completed_n = int(normalized.get("completed_n") or 0)
    pending_n = int(normalized.get("pending_n") or 0)
    total_snapshots = int(normalized.get("total_snapshots") or 0)
    roles = {
        "GI_A_STRICT_CORE": "Primary",
        "GI_B_RECENCY": "Challenger",
        "MT1_LONG_TERM": "Benchmark",
        "GI_A_without_volatility": "Diagnostic",
    }
    items = []
    for cid, role in roles.items():
        if candidate_id and cid != candidate_id:
            continue
        m = metrics.get(cid) or {}
        items.append(
            {
                "candidate_id": cid,
                "role": role,
                "metrics": m,
                "warning": "Nessun vincitore automatico sotto i gate readiness",
            }
        )
    return make_json_safe(
        {
            "status": monitoring.get("status", "ok"),
            "completed_n": completed_n,
            "pending_n": pending_n,
            "total_snapshots": total_snapshots,
            "minimum_prospective_matches": MINIMUM_PROSPECTIVE_MATCHES,
            "candidates": items,
            "auto_winner": False,
            "filters": {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "competition_id": competition_id,
                "candidate_id": candidate_id,
            },
        }
    )


def build_prospective_results(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    snapshot_status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    _, _, _, normalized = _goal_monitoring_context(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    payload = list_preview_snapshots(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        status=snapshot_status,
        limit=limit,
        offset=offset,
    )
    cov = normalized.get("coverage_in_period") or normalized.get("coverage_global") or {}
    total = int(normalized.get("total_snapshots") or cov.get("snapshots") or 0)
    completed = int(normalized.get("completed_snapshots") or cov.get("completed") or 0)
    pending = int(normalized.get("pending_snapshots") or cov.get("pending") or 0)
    return make_json_safe(
        {
            **payload,
            "snapshots_count": total,
            "completed_count": completed,
            "pending_count": pending,
            "completed_progress": round(completed / total, 6) if total else 0.0,
            "collection_progress": round((total - pending) / total, 6) if total else 0.0,
            "coverage_global": normalized.get("coverage_global"),
            "coverage_in_period": normalized.get("coverage_in_period"),
            "note": "Solo snapshot prospettici persistiti; nessuna ricostruzione retroattiva.",
        }
    )


def build_calibration(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    _, monitoring, _, normalized = _goal_monitoring_context(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    completed_n = int(normalized.get("completed_n") or 0)
    if completed_n == 0:
        return make_json_safe(
            {
                "status": "empty",
                "message": "Nessun risultato completed: metriche non calcolabili.",
                "completed_n": 0,
                "metrics_by_candidate": {},
                "filters": {
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "competition_id": competition_id,
                },
            }
        )
    if completed_n < 5:
        return make_json_safe(
            {
                "status": "insufficient_sample",
                "message": "Campione completed insufficiente per metriche di calibrazione.",
                "completed_n": completed_n,
                "metrics_by_candidate": {},
                "filters": {
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "competition_id": competition_id,
                },
            }
        )
    return make_json_safe(
        {
            "status": "ok",
            "completed_n": completed_n,
            "metrics_by_candidate": monitoring.get("metrics_by_candidate") or {},
            "phase_2b_readiness": monitoring.get("phase_2b_readiness"),
            "calibrated_estimate_label_it": "Stima calibrata research",
            "filters": {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "competition_id": competition_id,
            },
        }
    )


def build_stability(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    bundle = get_active_bundle(db)
    if bundle is None:
        return make_json_safe({"status": "error", "error": "bundle_missing"})
    completed = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id,
                CecchinoGoalIntensityV5PreviewSnapshot.result_attached_at.is_not(None),
            )
        ).all()
    )
    completed = _filter_snaps(
        completed,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        snapshot_status=None,
    )
    if len(completed) < 5:
        return make_json_safe(
            {
                "status": "insufficient_sample",
                "message": "Campione insufficiente per analisi di stabilità.",
                "completed_n": len(completed),
                "by_month": [],
            }
        )
    by_month: dict[str, list[float]] = {}
    for s in completed:
        d = s.scan_date
        if not d:
            continue
        key = f"{d.year:04d}-{d.month:02d}"
        score = s.primary_candidate_score
        if score is not None:
            by_month.setdefault(key, []).append(float(score))
    rows = [
        {
            "month": k,
            "n": len(v),
            "primary_mean": round(sum(v) / len(v), 6) if v else None,
        }
        for k, v in sorted(by_month.items())
    ]
    return make_json_safe(
        {
            "status": "ok",
            "completed_n": len(completed),
            "by_month": rows,
            "note": "Analisi limitata al campione prospettico completed; niente nuove soglie.",
        }
    )


def build_data_health(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    bundle = get_active_bundle(db)
    if bundle is None:
        return make_json_safe(
            {
                "status": "error",
                "error": "bundle_missing",
                "issues": [
                    {
                        "reason_code": "bundle_missing",
                        "count": 1,
                        "severity": "blocking",
                    }
                ],
            }
        )
    snaps = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
            )
        ).all()
    )
    snaps = _filter_snaps(
        snaps,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        snapshot_status=None,
    )
    freeze_at = bundle.frozen_at
    issues = []
    dup = (
        db.query(
            CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id,
            func.count(),
        )
        .filter(CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id)
        .group_by(CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id)
        .having(func.count() > 1)
        .count()
    )
    if dup:
        issues.append(
            {
                "reason_code": "duplicate_snapshot_per_fixture",
                "count": dup,
                "severity": "blocking",
            }
        )
    after_fail = 0
    before_fail = 0
    target_used = 0
    for s in snaps:
        if freeze_at and s.source_snapshot_at and s.source_snapshot_at <= freeze_at:
            after_fail += 1
        if s.kickoff and s.source_snapshot_at and s.source_snapshot_at >= s.kickoff:
            before_fail += 1
        if s.no_target_used_in_score is False:
            target_used += 1
    if after_fail:
        issues.append(
            {
                "reason_code": "source_snapshot_not_after_freeze",
                "count": after_fail,
                "severity": "blocking",
            }
        )
    if before_fail:
        issues.append(
            {
                "reason_code": "source_snapshot_not_before_kickoff",
                "count": before_fail,
                "severity": "blocking",
            }
        )
    if target_used:
        issues.append(
            {
                "reason_code": "target_used_in_score",
                "count": target_used,
                "severity": "blocking",
            }
        )
    by_status = {
        SNAPSHOT_PENDING: 0,
        SNAPSHOT_LOCKED: 0,
        SNAPSHOT_COMPLETED: 0,
        SNAPSHOT_INCOMPLETE: 0,
        SNAPSHOT_ERROR: 0,
    }
    for s in snaps:
        by_status[s.snapshot_status] = by_status.get(s.snapshot_status, 0) + 1
    return make_json_safe(
        {
            "status": "ok" if not any(i["severity"] == "blocking" for i in issues) else "degraded",
            "bundle": {
                "id": bundle.id,
                "version": bundle.version,
                "candidate_definition_hash": bundle.candidate_definition_hash,
                "frozen_at": bundle.frozen_at.isoformat() if bundle.frozen_at else None,
                "is_active": bundle.is_active,
            },
            "by_status": by_status,
            "issues": issues,
            "snapshot_count": len(snaps),
        }
    )


def list_snapshots(
    db: Session,
    **kwargs: Any,
) -> dict[str, Any]:
    return list_preview_snapshots(db, **kwargs)
