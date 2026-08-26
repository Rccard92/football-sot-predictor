"""Audit read-only holdout window Structural V2 — no repair/backfill/overwrite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    SNAPSHOT_OUTPUT_KEY,
    classify_existing_v35_v2_snapshot,
    validate_purchasability_preview_v35_v2_snapshot,
)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            raw = value.replace("Z", "+00:00")
            out = datetime.fromisoformat(raw)
            return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def classify_v2_snapshot_creation_timing(snapshot: Any) -> dict[str, Any]:
    """Classify one persisted V2 value for holdout eligibility (read-only)."""
    classified = classify_existing_v35_v2_snapshot(snapshot)
    base: dict[str, Any] = {
        "classify_status": classified.status,
        "generated_at": None,
        "source_snapshot_at": None,
        "kickoff": None,
        "generated_before_kickoff": None,
        "holdout_eligible": False,
        "bucket": None,
    }

    if classified.status == "absent":
        base["bucket"] = "absent"
        return base

    if classified.status == "present_but_invalid" or not isinstance(snapshot, dict):
        base["bucket"] = "invalid"
        if isinstance(snapshot, dict):
            base["generated_at"] = snapshot.get("generated_at")
            base["source_snapshot_at"] = snapshot.get("source_snapshot_at")
            base["kickoff"] = snapshot.get("kickoff")
            gen = _parse_dt(snapshot.get("generated_at"))
            kick = _parse_dt(snapshot.get("kickoff"))
            if gen is None:
                base["bucket"] = "missing_generated_at"
            elif kick is not None and gen >= kick:
                base["bucket"] = "generated_at_or_after_kickoff"
                base["generated_before_kickoff"] = False
        return base

    # valid-looking dict — still bucket by timing / completeness
    gen_raw = snapshot.get("generated_at")
    src_raw = snapshot.get("source_snapshot_at")
    kick_raw = snapshot.get("kickoff")
    base["generated_at"] = gen_raw
    base["source_snapshot_at"] = src_raw
    base["kickoff"] = kick_raw

    gen = _parse_dt(gen_raw)
    kick = _parse_dt(kick_raw)
    if gen is None:
        base["bucket"] = "missing_generated_at"
        return base
    if kick is None:
        base["bucket"] = "invalid"
        return base
    if gen >= kick:
        base["bucket"] = "generated_at_or_after_kickoff"
        base["generated_before_kickoff"] = False
        base["holdout_eligible"] = False
        return base

    # Re-validate fully (includes creation_not_before_kickoff)
    check = validate_purchasability_preview_v35_v2_snapshot(snapshot)
    if not check.get("ok"):
        base["bucket"] = "invalid"
        base["validation_reason"] = check.get("reason")
        return base

    base["generated_before_kickoff"] = True
    base["holdout_eligible"] = True
    base["bucket"] = "generated_before_kickoff"
    return base


def summarize_v2_creation_timing(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate timing buckets for a list of {fixture_id, snapshot} dicts."""
    summary = {
        "total_v2_snapshots": 0,
        "generated_before_kickoff": 0,
        "generated_at_or_after_kickoff": 0,
        "invalid": 0,
        "missing_generated_at": 0,
        "holdout_eligible": 0,
        "holdout_excluded": 0,
        "items": [],
    }
    for row in rows:
        snap = row.get("snapshot")
        if SNAPSHOT_OUTPUT_KEY in row and "snapshot" not in row:
            snap = row.get(SNAPSHOT_OUTPUT_KEY)
        # Count only when key was present on fixture
        if snap is None and row.get("key_present") is False:
            continue
        summary["total_v2_snapshots"] += 1
        timing = classify_v2_snapshot_creation_timing(snap)
        bucket = timing["bucket"]
        if bucket == "generated_before_kickoff":
            summary["generated_before_kickoff"] += 1
            summary["holdout_eligible"] += 1
        elif bucket == "generated_at_or_after_kickoff":
            summary["generated_at_or_after_kickoff"] += 1
            summary["holdout_excluded"] += 1
        elif bucket == "missing_generated_at":
            summary["missing_generated_at"] += 1
            summary["holdout_excluded"] += 1
        else:
            summary["invalid"] += 1
            summary["holdout_excluded"] += 1
        summary["items"].append(
            {
                "today_fixture_id": row.get("today_fixture_id"),
                "provider_fixture_id": row.get("provider_fixture_id"),
                **timing,
            }
        )
    return summary


def audit_deployed_v2_snapshots_creation_window(
    db: Session,
) -> dict[str, Any]:
    """Scan DB read-only for all fixtures with V2 key present. No mutations."""
    stmt = select(CecchinoTodayFixture).order_by(CecchinoTodayFixture.id.asc())
    fixtures = list(db.scalars(stmt).all())
    rows: list[dict[str, Any]] = []
    for fx in fixtures:
        output = fx.cecchino_output_json if isinstance(fx.cecchino_output_json, dict) else {}
        if SNAPSHOT_OUTPUT_KEY not in output:
            continue
        rows.append(
            {
                "today_fixture_id": int(fx.id),
                "provider_fixture_id": int(fx.provider_fixture_id)
                if fx.provider_fixture_id is not None
                else None,
                "key_present": True,
                "snapshot": output.get(SNAPSHOT_OUTPUT_KEY),
            }
        )
    report = summarize_v2_creation_timing(rows)
    report["audited_at"] = datetime.now(timezone.utc).isoformat()
    report["note"] = (
        "Read-only audit. Snapshots with generated_at >= kickoff are "
        "preserved but excluded from holdout analysis. No backfill/repair."
    )
    return report


__all__ = [
    "audit_deployed_v2_snapshots_creation_window",
    "classify_v2_snapshot_creation_timing",
    "summarize_v2_creation_timing",
]
