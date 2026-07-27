"""Guardia storica condivisa Acquistabilità v2 — solo pre-match verificato."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_purchasability_audit import (
    FIDELITY_FALLBACK,
    FIDELITY_MISSING,
    _parse_ts,
    resolve_purchasability_snapshot_timestamp,
)

REASON_FIXTURE_NOT_ELIGIBLE = "fixture_not_eligible"
REASON_KPI_PANEL_MISSING = "kpi_panel_missing"
REASON_KPI_ROWS_MISSING = "kpi_rows_missing"
REASON_SNAPSHOT_TIMESTAMP_UNVERIFIED = "snapshot_timestamp_unverified"
REASON_SNAPSHOT_TIMESTAMP_MISSING = "snapshot_timestamp_missing"
REASON_KICKOFF_MISSING = "kickoff_missing"
REASON_SNAPSHOT_NOT_BEFORE_KICKOFF = "snapshot_not_before_kickoff"


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _reject(
    *,
    reason_code: str,
    eligibility_verified: bool = False,
    kpi_rows_verified: bool = False,
    snap: dict[str, Any] | None = None,
    kickoff: datetime | None = None,
    source_snapshot_before_kickoff: bool = False,
) -> dict[str, Any]:
    snap = snap or {}
    snapshot_at = snap.get("snapshot_at")
    if isinstance(snapshot_at, datetime):
        snapshot_at_out: str | None = _iso(snapshot_at)
    else:
        snapshot_at_out = _iso(_parse_ts(snapshot_at)) if snapshot_at else None
    return {
        "accepted": False,
        "reason_code": reason_code,
        "eligibility_verified": eligibility_verified,
        "kpi_rows_verified": kpi_rows_verified,
        "snapshot_at": snapshot_at_out,
        "snapshot_source": snap.get("snapshot_source"),
        "snapshot_fidelity": snap.get("snapshot_fidelity"),
        "snapshot_timestamp_verified": bool(snap.get("snapshot_timestamp_verified")),
        "kickoff": _iso(kickoff),
        "source_snapshot_before_kickoff": bool(source_snapshot_before_kickoff),
    }


def evaluate_purchasability_v2_historical_source(fixture: Any) -> dict[str, Any]:
    """Unica guardia storica per profilo, backfill e controlli v2.

    Accetta solo fixture eligible con KPI rows, timestamp verificato e
    snapshot_at strettamente precedente al kickoff.
    """
    status = getattr(fixture, "eligibility_status", None)
    if status != ELIGIBILITY_ELIGIBLE:
        return _reject(reason_code=REASON_FIXTURE_NOT_ELIGIBLE)

    panel = getattr(fixture, "kpi_panel_json", None)
    if not isinstance(panel, dict):
        return _reject(
            reason_code=REASON_KPI_PANEL_MISSING,
            eligibility_verified=True,
        )

    rows = panel.get("rows")
    if not isinstance(rows, list) or len(rows) == 0:
        return _reject(
            reason_code=REASON_KPI_ROWS_MISSING,
            eligibility_verified=True,
        )

    snap = resolve_purchasability_snapshot_timestamp(fixture)
    fidelity = snap.get("snapshot_fidelity")
    verified = bool(snap.get("snapshot_timestamp_verified"))
    snapshot_at = snap.get("snapshot_at")
    if isinstance(snapshot_at, datetime):
        snapshot_dt = _parse_ts(snapshot_at)
    else:
        snapshot_dt = _parse_ts(snapshot_at)

    if not verified:
        if fidelity == FIDELITY_MISSING or snapshot_dt is None:
            return _reject(
                reason_code=REASON_SNAPSHOT_TIMESTAMP_MISSING,
                eligibility_verified=True,
                kpi_rows_verified=True,
                snap=snap,
            )
        # generic_updated_at_fallback o altro non verificato
        if fidelity == FIDELITY_FALLBACK or not verified:
            return _reject(
                reason_code=REASON_SNAPSHOT_TIMESTAMP_UNVERIFIED,
                eligibility_verified=True,
                kpi_rows_verified=True,
                snap=snap,
            )

    if snapshot_dt is None:
        return _reject(
            reason_code=REASON_SNAPSHOT_TIMESTAMP_MISSING,
            eligibility_verified=True,
            kpi_rows_verified=True,
            snap=snap,
        )

    kickoff_dt = _parse_ts(getattr(fixture, "kickoff", None))
    if kickoff_dt is None:
        return _reject(
            reason_code=REASON_KICKOFF_MISSING,
            eligibility_verified=True,
            kpi_rows_verified=True,
            snap={**snap, "snapshot_at": snapshot_dt},
        )

    if not (snapshot_dt < kickoff_dt):
        return _reject(
            reason_code=REASON_SNAPSHOT_NOT_BEFORE_KICKOFF,
            eligibility_verified=True,
            kpi_rows_verified=True,
            snap={**snap, "snapshot_at": snapshot_dt},
            kickoff=kickoff_dt,
            source_snapshot_before_kickoff=False,
        )

    return {
        "accepted": True,
        "reason_code": None,
        "eligibility_verified": True,
        "kpi_rows_verified": True,
        "snapshot_at": _iso(snapshot_dt),
        "snapshot_source": snap.get("snapshot_source"),
        "snapshot_fidelity": snap.get("snapshot_fidelity"),
        "snapshot_timestamp_verified": True,
        "kickoff": _iso(kickoff_dt),
        "source_snapshot_before_kickoff": True,
    }
