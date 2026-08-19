"""Snapshot Acquistabilità V3.1 — chiave separata purchasability_preview_v31."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_AUDIT_VERSION,
    PURCHASABILITY_V31_CANDIDATE_NAME,
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_CANDIDATE_VERSION_V1,
    PURCHASABILITY_V31_CONTRACT_VERSION,
    PURCHASABILITY_V31_FEATURE_VERSION,
    PURCHASABILITY_V31_FORMULA_CONFIG_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION,
    PURCHASABILITY_V31_REGISTRY_STATUS,
    PURCHASABILITY_V31_SNAPSHOT_VERSION,
    PURCHASABILITY_V31_SNAPSHOT_VERSION_V1,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v31_candidate import (
    calculate_purchasability_v31_batch,
    canonical_v31_candidate_sha256,
    input_fingerprint_v31,
)
from app.services.cecchino.cecchino_purchasability_v3_snapshot import (
    index_purchasability_v3_snapshot_by_market,
)


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    theoretical = item.get("theoretical") if isinstance(item.get("theoretical"), dict) else {}
    historical = item.get("historical") if isinstance(item.get("historical"), dict) else {}
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    fair = item.get("fair_book_audit") if isinstance(item.get("fair_book_audit"), dict) else {}
    return {
        "formula_version": item.get("formula_version") or PURCHASABILITY_V31_FORMULA_VERSION,
        "formula_config_version": item.get("formula_config_version")
        or PURCHASABILITY_V31_FORMULA_CONFIG_VERSION,
        "candidate_name": item.get("candidate_name") or PURCHASABILITY_V31_CANDIDATE_NAME,
        "registry_status": item.get("registry_status") or PURCHASABILITY_V31_REGISTRY_STATUS,
        "market_key": item.get("market_key"),
        "label": item.get("label") or item.get("market_label"),
        "market_label": item.get("market_label") or item.get("label"),
        "market_family": item.get("market_family"),
        "period": item.get("period"),
        "line": item.get("line"),
        "status": item.get("status"),
        "calculation_quality": item.get("calculation_quality"),
        "gate": gate,
        "gate_status": item.get("gate_status") or gate.get("gate_status"),
        "gate_reason_codes": list(
            item.get("gate_reason_codes") or gate.get("gate_reason_codes") or []
        ),
        "score": item.get("score"),
        "raw_score": item.get("raw_score"),
        "score_v31": item.get("score_v31"),
        "raw_score_v31": item.get("raw_score_v31"),
        "class": item.get("class"),
        "class_v31": item.get("class_v31"),
        "score_display": item.get("score_display"),
        "reading_short": item.get("reading_short"),
        "reading_detailed": item.get("reading_detailed"),
        "reason_codes": list(item.get("reason_codes") or []),
        "warnings": list(item.get("warnings") or []),
        "dependency_meta": item.get("dependency_meta"),
        "pre_match_only": True,
        "snapshot_at": item.get("snapshot_at"),
        "kickoff": item.get("kickoff"),
        "historical_as_of": item.get("historical_as_of"),
        "input": inp,
        "fair_book_audit": fair,
        "theoretical": theoretical,
        "historical": historical,
        "historical_multiplier": item.get("historical_multiplier")
        or historical.get("historical_multiplier"),
        "historical_adjustment_points": item.get("historical_adjustment_points")
        or historical.get("historical_adjustment_points"),
        "historical_adjustment_pct": item.get("historical_adjustment_pct")
        or historical.get("historical_adjustment_pct"),
        "historical_reason_codes": list(
            item.get("historical_reason_codes")
            or historical.get("historical_reason_codes")
            or []
        ),
        "theoretical_raw_score": item.get("theoretical_raw_score")
        or theoretical.get("theoretical_raw_score"),
        "formula_steps": list(item.get("formula_steps") or []),
        "rounding": item.get("rounding"),
        "comparison_with_v3": item.get("comparison_with_v3"),
        "penalties": item.get("penalties") or theoretical.get("penalties"),
        "value_score": item.get("value_score") or theoretical.get("value_score"),
        "quality_score": item.get("quality_score")
        or theoretical.get("theoretical_quality_score"),
        "total_penalty": item.get("total_penalty")
        or theoretical.get("theoretical_penalty_total"),
        "shadow_candidate": True,
        "current_operational_version": False,
        "candidate_version": item.get("candidate_version"),
        "audit_version": item.get("audit_version"),
    }


def build_purchasability_preview_v31_snapshot(
    *,
    batch: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    source_mode: str | None = None,
    warnings: list[str] | None = None,
    generated_at: str | None = None,
    input_fingerprint: str | None = None,
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
            "snapshot_version": PURCHASABILITY_V31_SNAPSHOT_VERSION,
            "contract_version": PURCHASABILITY_V31_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_V31_FEATURE_VERSION,
            "candidate_version": PURCHASABILITY_V31_CANDIDATE_VERSION,
            "candidate_name": PURCHASABILITY_V31_CANDIDATE_NAME,
            "formula_version": PURCHASABILITY_V31_FORMULA_VERSION,
            "formula_config_version": PURCHASABILITY_V31_FORMULA_CONFIG_VERSION,
            "audit_version": PURCHASABILITY_V31_AUDIT_VERSION,
            "registry_status": PURCHASABILITY_V31_REGISTRY_STATUS,
            "status": status,
            "items": items,
            "summary": dict(batch.get("summary") or {}),
            "shadow_summary": dict(batch.get("shadow_summary") or {}),
            "full_candidate_payload_sha256": canonical_v31_candidate_sha256(batch),
            "input_fingerprint": input_fingerprint,
            "generated_at": now,
            "source_snapshot_at": snap.get("snapshot_at"),
            "source_snapshot_verified": snap.get("snapshot_timestamp_verified"),
            "source_snapshot_before_kickoff": snap.get("source_snapshot_before_kickoff"),
            "source_mode": source_mode,
            "pre_match_only": True,
            "historical_reliability_integrated": True,
            "fixed_scales_used": True,
            "current_operational_version": False,
            "shadow_candidate": True,
            "contains_post_match_fields": False,
            "signals_integration": False,
            "warnings": list(warnings or []),
        }
    )


def validate_purchasability_preview_v31_snapshot(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"ok": False, "reason": "not_a_dict"}
    snap_v = snapshot.get("snapshot_version")
    # Accetta snapshot v2 correnti e v1 già persistiti (non sovrascrivere a caldo).
    if snap_v not in (
        PURCHASABILITY_V31_SNAPSHOT_VERSION,
        PURCHASABILITY_V31_SNAPSHOT_VERSION_V1,
    ):
        return {"ok": False, "reason": "snapshot_version_mismatch"}
    cand_v = snapshot.get("candidate_version")
    if cand_v not in (
        PURCHASABILITY_V31_CANDIDATE_VERSION,
        PURCHASABILITY_V31_CANDIDATE_VERSION_V1,
    ):
        return {"ok": False, "reason": "candidate_version_mismatch"}
    items = snapshot.get("items")
    if not isinstance(items, list):
        return {"ok": False, "reason": "items_not_list"}
    return {"ok": True, "reason": None}


def resolve_valid_persisted_purchasability_v31(existing: Any) -> dict[str, Any] | None:
    """Restituisce lo snapshot V3.1 persistito se valido, altrimenti None."""
    check = validate_purchasability_preview_v31_snapshot(existing)
    if check.get("ok") and isinstance(existing, dict):
        return existing
    return None


def _existing_valid_preview_v31(existing: Any) -> dict[str, Any] | None:
    return resolve_valid_persisted_purchasability_v31(existing)


def build_unavailable_purchasability_preview_v31(
    *,
    today_fixture_id: Any = None,
    reason: str = "unavailable",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return make_json_safe(
        {
            "snapshot_version": PURCHASABILITY_V31_SNAPSHOT_VERSION,
            "contract_version": PURCHASABILITY_V31_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_V31_FEATURE_VERSION,
            "candidate_version": PURCHASABILITY_V31_CANDIDATE_VERSION,
            "candidate_name": PURCHASABILITY_V31_CANDIDATE_NAME,
            "formula_version": PURCHASABILITY_V31_FORMULA_VERSION,
            "formula_config_version": PURCHASABILITY_V31_FORMULA_CONFIG_VERSION,
            "audit_version": PURCHASABILITY_V31_AUDIT_VERSION,
            "registry_status": PURCHASABILITY_V31_REGISTRY_STATUS,
            "status": "unavailable",
            "items": [],
            "summary": {"reason": reason, "today_fixture_id": today_fixture_id},
            "shadow_summary": {},
            "pre_match_only": True,
            "historical_reliability_integrated": True,
            "fixed_scales_used": True,
            "current_operational_version": False,
            "shadow_candidate": True,
            "contains_post_match_fields": False,
            "signals_integration": False,
            "warnings": list(warnings or [reason]),
        }
    )


def build_candidate_and_compact_snapshot_v31(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
    snapshot_info: dict[str, Any] | None = None,
    source_mode: str | None = None,
    historical_by_market: dict[str, dict[str, Any]] | None = None,
    v3_preview: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    v3_by = index_purchasability_v3_snapshot_by_market(v3_preview)
    batch = calculate_purchasability_v31_batch(
        kpi_panel=kpi_panel,
        fixture_meta=fixture_meta,
        historical_by_market=historical_by_market,
        v3_items_by_market=v3_by,
    )
    fp = input_fingerprint_v31(
        kpi_panel=kpi_panel,
        historical_by_market=historical_by_market,
        fixture_meta=fixture_meta,
    )
    snapshot = build_purchasability_preview_v31_snapshot(
        batch=batch,
        snapshot_info=snapshot_info,
        source_mode=source_mode,
        input_fingerprint=fp,
    )
    return batch, snapshot


def attach_purchasability_preview_v31_to_output(
    *,
    cecchino_output: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    existing_preview_v31: dict[str, Any] | None = None,
    historical_by_market: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Scrive purchasability_preview_v31 senza toccare V3."""
    if not isinstance(cecchino_output, dict):
        return cecchino_output

    preserved = _existing_valid_preview_v31(existing_preview_v31)
    if preserved is None:
        preserved = _existing_valid_preview_v31(
            cecchino_output.get("purchasability_preview_v31")
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
            cecchino_output["purchasability_preview_v31"] = preserved
        return cecchino_output

    if not verified:
        if preserved is not None:
            cecchino_output["purchasability_preview_v31"] = preserved
        return cecchino_output

    v3_preview = cecchino_output.get("purchasability_preview_v3")
    if not isinstance(v3_preview, dict):
        v3_preview = None

    try:
        _candidate, snapshot = build_candidate_and_compact_snapshot_v31(
            kpi_panel=kpi_panel,
            fixture_meta={
                **fixture_meta,
                "snapshot_at": snap.get("snapshot_at"),
                "snapshot_timestamp_verified": verified,
                "kickoff_required": True,
            },
            snapshot_info={
                **snap,
                "source_snapshot_before_kickoff": before,
            },
            source_mode=None,
            historical_by_market=historical_by_market,
            v3_preview=v3_preview,
        )
    except Exception as exc:  # noqa: BLE001 — non bloccante
        warnings.append(f"purchasability_v31_attach_failed:{type(exc).__name__}")
        if preserved is not None:
            out = dict(preserved)
            out_warnings = list(out.get("warnings") or [])
            out_warnings.extend(warnings)
            out["warnings"] = out_warnings
            cecchino_output["purchasability_preview_v31"] = out
        else:
            cecchino_output["purchasability_preview_v31"] = (
                build_unavailable_purchasability_preview_v31(
                    today_fixture_id=fixture_meta.get("today_fixture_id"),
                    reason="purchasability_v31_attach_failed",
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

    cecchino_output["purchasability_preview_v31"] = snapshot
    return cecchino_output


def resolve_purchasability_preview_v31_for_detail(
    *,
    row: Any,
    kpi_panel: dict[str, Any] | None,
    historical_by_market: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Detail read-only: persisted v31 → derived → unavailable."""
    output = getattr(row, "cecchino_output_json", None)
    today_id = getattr(row, "id", None)
    persisted = None
    if isinstance(output, dict):
        persisted = _existing_valid_preview_v31(
            output.get("purchasability_preview_v31")
        )
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
        "snapshot_timestamp_verified": snap_info.get("snapshot_timestamp_verified"),
        "kickoff_required": True,
    }

    if not snap_info.get("snapshot_timestamp_verified"):
        unavail = build_unavailable_purchasability_preview_v31(
            today_fixture_id=today_id,
            reason="snapshot_timestamp_unverified",
        )
        unavail["source_mode"] = "derived_read_only_from_stored_snapshot"
        return unavail

    v3_preview = None
    if isinstance(output, dict):
        v3_preview = output.get("purchasability_preview_v3")

    try:
        _cand, snapshot = build_candidate_and_compact_snapshot_v31(
            kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else None,
            fixture_meta=fixture_meta,
            snapshot_info=snap_info,
            source_mode="derived_read_only_from_stored_snapshot",
            historical_by_market=historical_by_market,
            v3_preview=v3_preview if isinstance(v3_preview, dict) else None,
        )
    except Exception:
        return build_unavailable_purchasability_preview_v31(
            today_fixture_id=today_id,
            reason="purchasability_v31_derive_failed",
        )

    if snapshot.get("source_snapshot_before_kickoff") is False:
        return build_unavailable_purchasability_preview_v31(
            today_fixture_id=today_id,
            reason="snapshot_not_before_kickoff",
        )

    snapshot["source_mode"] = "derived_read_only_from_stored_snapshot"
    return make_json_safe(snapshot)


def index_purchasability_v31_snapshot_by_market(
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
