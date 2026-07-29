"""Snapshot Acquistabilità v3 — chiave separata purchasability_preview_v3."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_AUDIT_VERSION,
    PURCHASABILITY_V3_CANDIDATE_NAME,
    PURCHASABILITY_V3_CANDIDATE_VERSION,
    PURCHASABILITY_V3_CONTRACT_VERSION,
    PURCHASABILITY_V3_FEATURE_VERSION,
    PURCHASABILITY_V3_FORMULA_VERSION,
    PURCHASABILITY_V3_REGISTRY_STATUS,
    PURCHASABILITY_V3_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v3_candidate import (
    calculate_purchasability_v3_batch,
    canonical_v3_candidate_sha256,
)


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    penalties = item.get("penalties") if isinstance(item.get("penalties"), dict) else {}
    family = item.get("family") if isinstance(item.get("family"), dict) else {}
    linked = item.get("linked_market_context")
    return {
        "market_key": item.get("market_key"),
        "market_label": item.get("market_label"),
        "market_family": item.get("market_family"),
        "period": item.get("period"),
        "line": item.get("line"),
        "status": item.get("status"),
        "calculation_quality": item.get("calculation_quality"),
        "score": item.get("score"),
        "raw_score": item.get("raw_score"),
        "score_display": item.get("score_display"),
        "class": item.get("class"),
        "gate_status": item.get("gate_status") or gate.get("gate_status"),
        "gate_reason_codes": list(
            item.get("gate_reason_codes") or gate.get("gate_reason_codes") or []
        ),
        "value_score": item.get("value_score"),
        "quality_score": item.get("quality_score"),
        "quality_start": item.get("quality_start"),
        "total_penalty": item.get("total_penalty"),
        "penalties": penalties,
        "family": family,
        "opposite_market_key": item.get("opposite_market_key"),
        "opposite_fair_probability": item.get("opposite_fair_probability"),
        "opposite_pressure_penalty": item.get("opposite_pressure_penalty"),
        "linked_market_context": linked,
        "reading_short": item.get("reading_short"),
        "reading_detailed": item.get("reading_detailed"),
        "strengths": list(item.get("strengths") or []),
        "risks": list(item.get("risks") or []),
        "reason_codes": list(item.get("reason_codes") or []),
        "warnings": list(item.get("warnings") or []),
        "formula_steps": list(item.get("formula_steps") or []),
        "input": item.get("input") if isinstance(item.get("input"), dict) else {},
        "dependency_meta": item.get("dependency_meta"),
        "historical_profile_used": False,
        "fixed_scales_used": True,
        "formula_version": item.get("formula_version") or PURCHASABILITY_V3_FORMULA_VERSION,
        "candidate_version": item.get("candidate_version")
        or PURCHASABILITY_V3_CANDIDATE_VERSION,
    }


def build_purchasability_preview_v3_snapshot(
    *,
    batch: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    source_mode: str | None = None,
    warnings: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    snap = snapshot_info or {}
    items = [
        _compact_item(it) for it in (batch.get("items") or []) if isinstance(it, dict)
    ]
    status = batch.get("status") or "unavailable"
    now = generated_at
    if now is None:
        now = datetime.now(timezone.utc).isoformat()
    return make_json_safe(
        {
            "snapshot_version": PURCHASABILITY_V3_SNAPSHOT_VERSION,
            "contract_version": PURCHASABILITY_V3_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_V3_FEATURE_VERSION,
            "candidate_version": PURCHASABILITY_V3_CANDIDATE_VERSION,
            "candidate_name": PURCHASABILITY_V3_CANDIDATE_NAME,
            "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
            "audit_version": PURCHASABILITY_V3_AUDIT_VERSION,
            "registry_status": PURCHASABILITY_V3_REGISTRY_STATUS,
            "status": status,
            "items": items,
            "summary": dict(batch.get("summary") or {}),
            "full_candidate_payload_sha256": canonical_v3_candidate_sha256(batch),
            "generated_at": now,
            "source_snapshot_at": snap.get("snapshot_at"),
            "source_snapshot_verified": snap.get("snapshot_timestamp_verified"),
            "source_snapshot_before_kickoff": snap.get("source_snapshot_before_kickoff"),
            "source_mode": source_mode,
            "pre_match_only": True,
            "historical_profile_used": False,
            "fixed_scales_used": True,
            "current_operational_version": False,
            "parallel_candidate": True,
            "contains_post_match_fields": False,
            "signals_integration": False,
            "warnings": list(warnings or []),
        }
    )


def validate_purchasability_preview_v3_snapshot(
    snapshot: Any,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"ok": False, "reason": "not_a_dict"}
    if snapshot.get("snapshot_version") != PURCHASABILITY_V3_SNAPSHOT_VERSION:
        return {"ok": False, "reason": "snapshot_version_mismatch"}
    if snapshot.get("candidate_version") != PURCHASABILITY_V3_CANDIDATE_VERSION:
        return {"ok": False, "reason": "candidate_version_mismatch"}
    items = snapshot.get("items")
    if not isinstance(items, list):
        return {"ok": False, "reason": "items_not_list"}
    return {"ok": True, "reason": None}


def _existing_valid_preview_v3(existing: Any) -> dict[str, Any] | None:
    check = validate_purchasability_preview_v3_snapshot(existing)
    if check.get("ok") and isinstance(existing, dict):
        return existing
    return None


def build_unavailable_purchasability_preview_v3(
    *,
    today_fixture_id: Any = None,
    reason: str = "unavailable",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return make_json_safe(
        {
            "snapshot_version": PURCHASABILITY_V3_SNAPSHOT_VERSION,
            "contract_version": PURCHASABILITY_V3_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_V3_FEATURE_VERSION,
            "candidate_version": PURCHASABILITY_V3_CANDIDATE_VERSION,
            "candidate_name": PURCHASABILITY_V3_CANDIDATE_NAME,
            "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
            "audit_version": PURCHASABILITY_V3_AUDIT_VERSION,
            "registry_status": PURCHASABILITY_V3_REGISTRY_STATUS,
            "status": "unavailable",
            "items": [],
            "summary": {"reason": reason, "today_fixture_id": today_fixture_id},
            "pre_match_only": True,
            "historical_profile_used": False,
            "fixed_scales_used": True,
            "current_operational_version": False,
            "parallel_candidate": True,
            "contains_post_match_fields": False,
            "signals_integration": False,
            "warnings": list(warnings or [reason]),
        }
    )


def build_candidate_and_compact_snapshot_v3(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
    snapshot_info: dict[str, Any] | None = None,
    source_mode: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    batch = calculate_purchasability_v3_batch(
        kpi_panel=kpi_panel,
        fixture_meta=fixture_meta,
    )
    snapshot = build_purchasability_preview_v3_snapshot(
        batch=batch,
        snapshot_info=snapshot_info,
        source_mode=source_mode,
    )
    return batch, snapshot


def attach_purchasability_preview_v3_to_output(
    *,
    cecchino_output: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    existing_preview_v3: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scrive purchasability_preview_v3 senza toccare v1.1 né v2."""
    if not isinstance(cecchino_output, dict):
        return cecchino_output

    preserved = _existing_valid_preview_v3(existing_preview_v3)
    if preserved is None:
        preserved = _existing_valid_preview_v3(
            cecchino_output.get("purchasability_preview_v3")
        )

    snap = snapshot_info or {}
    verified = bool(snap.get("snapshot_timestamp_verified"))

    def _parse(dt: Any) -> datetime | None:
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if isinstance(dt, str):
            try:
                raw = dt.replace("Z", "+00:00")
                out = datetime.fromisoformat(raw)
                return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    snap_dt = _parse(snap.get("snapshot_at"))
    kick_dt = _parse(fixture_meta.get("kickoff"))
    before: bool | None = None
    if snap_dt is not None and kick_dt is not None:
        before = snap_dt < kick_dt

    warnings: list[str] = []

    if before is False:
        if preserved is not None:
            cecchino_output["purchasability_preview_v3"] = preserved
        return cecchino_output

    if not verified:
        if preserved is not None:
            cecchino_output["purchasability_preview_v3"] = preserved
        return cecchino_output

    try:
        _candidate, snapshot = build_candidate_and_compact_snapshot_v3(
            kpi_panel=kpi_panel,
            fixture_meta=fixture_meta,
            snapshot_info={
                **snap,
                "source_snapshot_before_kickoff": before,
            },
            source_mode=None,
        )
    except Exception as exc:  # noqa: BLE001 — non bloccante
        warnings.append(f"purchasability_v3_attach_failed:{type(exc).__name__}")
        if preserved is not None:
            out = dict(preserved)
            out_warnings = list(out.get("warnings") or [])
            out_warnings.extend(warnings)
            out["warnings"] = out_warnings
            cecchino_output["purchasability_preview_v3"] = out
        else:
            cecchino_output["purchasability_preview_v3"] = (
                build_unavailable_purchasability_preview_v3(
                    today_fixture_id=fixture_meta.get("today_fixture_id"),
                    reason="purchasability_v3_attach_failed",
                    warnings=warnings,
                )
            )
        return cecchino_output

    if snapshot.get("source_snapshot_verified") is None:
        snapshot["source_snapshot_verified"] = verified
    if snapshot.get("source_snapshot_before_kickoff") is None and before is not None:
        snapshot["source_snapshot_before_kickoff"] = before
    if snapshot.get("source_snapshot_at") is None and snap.get("snapshot_at"):
        at = snap.get("snapshot_at")
        snapshot["source_snapshot_at"] = (
            at.isoformat() if isinstance(at, datetime) else at
        )
    if warnings:
        snapshot["warnings"] = list(snapshot.get("warnings") or []) + warnings

    cecchino_output["purchasability_preview_v3"] = snapshot
    return cecchino_output


def resolve_purchasability_preview_v3_for_detail(
    *,
    row: Any,
    kpi_panel: dict[str, Any] | None,
) -> dict[str, Any]:
    """Detail read-only: persisted v3 → derived → unavailable. Nessuna scrittura."""
    output = getattr(row, "cecchino_output_json", None)
    today_id = getattr(row, "id", None)
    persisted = None
    if isinstance(output, dict):
        persisted = _existing_valid_preview_v3(output.get("purchasability_preview_v3"))
    if persisted is not None:
        out = dict(persisted)
        out["source_mode"] = "persisted_pre_match_snapshot"
        return make_json_safe(out)

    from app.services.cecchino.cecchino_purchasability_audit import (
        resolve_purchasability_snapshot_timestamp,
    )

    snap_info = resolve_purchasability_snapshot_timestamp(row)
    snap_at = snap_info.get("snapshot_at")
    if isinstance(snap_at, datetime):
        snap_info = {**snap_info, "snapshot_at": snap_at.isoformat()}

    fixture_meta = {
        "today_fixture_id": today_id,
        "local_fixture_id": getattr(row, "local_fixture_id", None),
        "provider_fixture_id": getattr(row, "provider_fixture_id", None),
        "competition_id": getattr(row, "competition_id", None),
        "scan_date": getattr(row, "scan_date", None),
        "kickoff": getattr(row, "kickoff", None),
    }

    if not snap_info.get("snapshot_timestamp_verified"):
        unavail = build_unavailable_purchasability_preview_v3(
            today_fixture_id=today_id,
            reason="snapshot_timestamp_unverified",
        )
        unavail["source_mode"] = "derived_read_only_from_stored_snapshot"
        return unavail

    try:
        _cand, snapshot = build_candidate_and_compact_snapshot_v3(
            kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else None,
            fixture_meta=fixture_meta,
            snapshot_info=snap_info,
            source_mode="derived_read_only_from_stored_snapshot",
        )
    except Exception:
        return build_unavailable_purchasability_preview_v3(
            today_fixture_id=today_id,
            reason="purchasability_v3_derive_failed",
        )

    if snapshot.get("source_snapshot_before_kickoff") is False:
        return build_unavailable_purchasability_preview_v3(
            today_fixture_id=today_id,
            reason="snapshot_not_before_kickoff",
        )

    snapshot["source_mode"] = "derived_read_only_from_stored_snapshot"
    return make_json_safe(snapshot)


def index_purchasability_v3_snapshot_by_market(
    snapshot: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(snapshot, dict):
        return out
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict):
            continue
        mk = item.get("market_key") or item.get("selection")
        if isinstance(mk, str) and mk:
            out[mk] = item
    return out
