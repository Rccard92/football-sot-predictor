"""Adapter canonico contratto monitoring Goal Intensity v5."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.models.cecchino_goal_intensity_v5_preview import (
    SNAPSHOT_COMPLETED,
    SNAPSHOT_ERROR,
    SNAPSHOT_INCOMPLETE,
    SNAPSHOT_LOCKED,
    SNAPSHOT_PENDING,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe


def _snap_scan_date(s: CecchinoGoalIntensityV5PreviewSnapshot) -> date | None:
    return s.scan_date


def _snap_completed_at(s: CecchinoGoalIntensityV5PreviewSnapshot) -> datetime | None:
    return s.result_attached_at


def _count_by_status(
    snapshots: list[CecchinoGoalIntensityV5PreviewSnapshot],
) -> dict[str, int]:
    counts = {
        "completed": 0,
        "pending": 0,
        "locked": 0,
        "incomplete": 0,
        "error": 0,
    }
    for s in snapshots:
        st = str(s.snapshot_status or "")
        if st == SNAPSHOT_COMPLETED:
            counts["completed"] += 1
        elif st == SNAPSHOT_PENDING:
            counts["pending"] += 1
        elif st == SNAPSHOT_LOCKED:
            counts["locked"] += 1
        elif st == SNAPSHOT_INCOMPLETE:
            counts["incomplete"] += 1
        elif st == SNAPSHOT_ERROR:
            counts["error"] += 1
    return counts


def _filter_snapshots(
    snapshots: list[CecchinoGoalIntensityV5PreviewSnapshot],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> list[CecchinoGoalIntensityV5PreviewSnapshot]:
    out: list[CecchinoGoalIntensityV5PreviewSnapshot] = []
    for s in snapshots:
        sd = _snap_scan_date(s)
        if date_from and sd and sd < date_from:
            continue
        if date_to and sd and sd > date_to:
            continue
        if competition_id is not None and s.competition_id != competition_id:
            continue
        out.append(s)
    return out


def _coverage_block(
    snapshots: list[CecchinoGoalIntensityV5PreviewSnapshot],
) -> dict[str, Any]:
    counts = _count_by_status(snapshots)
    scan_dates = sorted(
        d for d in (_snap_scan_date(s) for s in snapshots) if isinstance(d, date)
    )
    completed_dates = sorted(
        d
        for d in (
            (_snap_completed_at(s).date() if _snap_completed_at(s) else _snap_scan_date(s))
            for s in snapshots
            if s.snapshot_status == SNAPSHOT_COMPLETED and _snap_completed_at(s)
        )
        if isinstance(d, date)
    )
    total = len(snapshots)
    return {
        "snapshots": total,
        "pending": counts["pending"],
        "completed": counts["completed"],
        "locked": counts["locked"],
        "incomplete": counts["incomplete"],
        "error": counts["error"],
        "first_snapshot": scan_dates[0].isoformat() if scan_dates else None,
        "last_snapshot": scan_dates[-1].isoformat() if scan_dates else None,
        "first_completed": completed_dates[0].isoformat() if completed_dates else None,
        "last_completed": completed_dates[-1].isoformat() if completed_dates else None,
    }


def normalize_goal_v5_monitoring_contract(
    *,
    monitoring: dict[str, Any],
    snapshots: list[CecchinoGoalIntensityV5PreviewSnapshot] | None = None,
    bundle_summary: dict[str, Any] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Normalizza conteggi monitoring senza chiavi legacy inesistenti."""
    snaps = list(snapshots or [])
    global_snaps = snaps
    period_snaps = _filter_snapshots(
        snaps,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )

    protocol = monitoring.get("prospective_protocol") or {}
    completed_from_monitoring = int(monitoring.get("completed_prospective_matches") or 0)
    total_from_protocol = int(protocol.get("prospective_matches_collected") or 0)

    global_counts = _count_by_status(global_snaps) if global_snaps else {}
    period_counts = _count_by_status(period_snaps) if period_snaps else {}

    if global_snaps:
        completed = global_counts.get("completed", 0)
        pending = global_counts.get("pending", 0)
        locked = global_counts.get("locked", 0)
        incomplete = global_counts.get("incomplete", 0)
        error = global_counts.get("error", 0)
        total = len(global_snaps)
    elif bundle_summary:
        completed = int(bundle_summary.get("completed") or 0)
        pending = int(bundle_summary.get("pending") or 0)
        locked = int(bundle_summary.get("locked") or 0)
        incomplete = int(bundle_summary.get("incomplete") or 0)
        error = int(bundle_summary.get("error") or 0)
        total = int(bundle_summary.get("collected") or bundle_summary.get("prospective_matches_collected") or 0)
    else:
        completed = completed_from_monitoring
        pending = max(0, total_from_protocol - completed)
        locked = 0
        incomplete = 0
        error = 0
        total = total_from_protocol

    if total_from_protocol and not global_snaps and not bundle_summary:
        total = total_from_protocol
        if pending == 0 and total > completed:
            pending = max(0, total - completed)

    warning_codes: list[str] = []
    status_sum = completed + pending + locked + incomplete + error
    if global_snaps and status_sum != total:
        warning_codes.append("status_count_mismatch")

    phase = monitoring.get("phase_2b_readiness") or {}
    minimum = int(monitoring.get("minimum_prospective_matches") or protocol.get("minimum_prospective_matches") or 200)

    return make_json_safe(
        {
            "total_snapshots": int(total),
            "completed_snapshots": int(completed),
            "pending_snapshots": int(pending),
            "locked_snapshots": int(locked),
            "incomplete_snapshots": int(incomplete),
            "error_snapshots": int(error),
            "metrics_by_candidate": dict(monitoring.get("metrics_by_candidate") or {}),
            "comparisons": dict(monitoring.get("comparisons") or {}),
            "phase_2b_readiness": dict(phase),
            "minimum_prospective_matches": minimum,
            "status": str(monitoring.get("status") or "ok"),
            "warning_codes": warning_codes,
            "coverage_global": _coverage_block(global_snaps),
            "coverage_in_period": _coverage_block(period_snaps),
            "completed_n": int(completed),
            "pending_n": int(pending),
        }
    )
