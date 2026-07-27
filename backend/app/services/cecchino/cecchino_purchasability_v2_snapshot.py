"""Snapshot Acquistabilità v2 — chiave separata purchasability_preview_v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.cecchino_purchasability_v2 import (
    PURCHASABILITY_DECISION_V2_CANDIDATE_NAME,
    PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
    PURCHASABILITY_V2_CONTRACT_VERSION,
    PURCHASABILITY_V2_FEATURE_VERSION,
    PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
    PURCHASABILITY_V2_REGISTRY_STATUS,
    PURCHASABILITY_V2_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v2_candidate import (
    calculate_purchasability_v2_batch,
    canonical_v2_candidate_sha256,
)
from app.services.cecchino.cecchino_purchasability_v2_normalization import (
    get_or_build_normalization_profile,
)


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    p1 = item.get("phase_1_value") if isinstance(item.get("phase_1_value"), dict) else {}
    p2 = item.get("phase_2_quality") if isinstance(item.get("phase_2_quality"), dict) else {}
    gate = item.get("positive_value_gate") if isinstance(item.get("positive_value_gate"), dict) else {}
    comps1 = p1.get("components") if isinstance(p1.get("components"), dict) else {}
    comps2 = p2.get("components") if isinstance(p2.get("components"), dict) else {}
    trace = p2.get("competitor_trace") if isinstance(p2.get("competitor_trace"), dict) else {}
    norm_meta = (
        item.get("normalization_profile")
        if isinstance(item.get("normalization_profile"), dict)
        else {}
    )

    raw_components: dict[str, Any] = {}
    normalized_components: dict[str, Any] = {}
    for name, block in {**comps1, **comps2}.items():
        if not isinstance(block, dict):
            continue
        raw_components[name] = block.get("raw_value")
        normalized_components[name] = block.get("normalized_value")

    return {
        "market_key": item.get("market_key"),
        "selection": item.get("selection") or item.get("market_key"),
        "status": item.get("status"),
        "calculation_quality": item.get("calculation_quality"),
        "score": item.get("score"),
        "raw_score": item.get("raw_score"),
        "raw_pre_gate_score": item.get("raw_pre_gate_score"),
        "class": item.get("class"),
        "reading": item.get("reading"),
        "phase_1_score": p1.get("score"),
        "phase_2_score": p2.get("score"),
        "positive_value_gate": {
            "status": gate.get("status"),
            "reason_codes": list(gate.get("reason_codes") or []),
        },
        "configured_weights_phase_1": dict(p1.get("configured_weights") or {}),
        "applied_weights_phase_1": dict(p1.get("applied_weights") or {}),
        "coverage_ratio_phase_1": p1.get("coverage_ratio"),
        "configured_weights_phase_2": dict(p2.get("configured_weights") or {}),
        "applied_weights_phase_2": dict(p2.get("applied_weights") or {}),
        "coverage_ratio_phase_2": p2.get("coverage_ratio"),
        "raw_components": raw_components,
        "normalized_components": normalized_components,
        "best_competitor_keys": {
            "rating": trace.get("best_competitor_rating_market"),
            "edge": trace.get("best_competitor_edge_market"),
            "probability": trace.get("best_competitor_probability_market"),
        },
        "opposite_selection": trace.get("opposite_selection"),
        "normalization_profile_version": norm_meta.get("version"),
        "normalization_profile_hash": norm_meta.get("hash"),
        "reason_codes": list(item.get("reason_codes") or []),
        # Audit-friendly compact extras (no full dump)
        "phase_1_status": p1.get("status"),
        "phase_2_status": p2.get("status"),
        "decision_group": trace.get("decision_group"),
        "probability_subgroup": trace.get("probability_subgroup"),
    }


def build_purchasability_preview_v2_snapshot(
    *,
    batch: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    source_mode: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    snap = snapshot_info or {}
    items = [_compact_item(it) for it in (batch.get("items") or []) if isinstance(it, dict)]
    status = batch.get("status") or "unavailable"
    return make_json_safe(
        {
            "snapshot_version": PURCHASABILITY_V2_SNAPSHOT_VERSION,
            "contract_version": PURCHASABILITY_V2_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_V2_FEATURE_VERSION,
            "candidate_version": PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
            "candidate_name": PURCHASABILITY_DECISION_V2_CANDIDATE_NAME,
            "registry_status": PURCHASABILITY_V2_REGISTRY_STATUS,
            "status": status,
            "items": items,
            "summary": dict(batch.get("summary") or {}),
            "normalization_profile_version": batch.get("normalization_profile_version"),
            "normalization_profile_hash": batch.get("normalization_profile_hash"),
            "normalization_profile_cutoff": batch.get("normalization_profile_cutoff")
            or PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
            "normalization_profile_summary": batch.get("normalization_profile_summary"),
            "full_candidate_payload_sha256": canonical_v2_candidate_sha256(batch),
            "source_snapshot_at": snap.get("snapshot_at"),
            "source_snapshot_verified": snap.get("snapshot_timestamp_verified"),
            "source_snapshot_before_kickoff": snap.get("source_snapshot_before_kickoff"),
            "source_mode": source_mode,
            "pre_match_only": True,
            "contains_post_match_fields": False,
            "signals_integration": False,
            "warnings": list(warnings or []),
        }
    )


def validate_purchasability_preview_v2_snapshot(
    snapshot: Any,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"ok": False, "reason": "not_a_dict"}
    if snapshot.get("snapshot_version") != PURCHASABILITY_V2_SNAPSHOT_VERSION:
        return {"ok": False, "reason": "snapshot_version_mismatch"}
    if snapshot.get("candidate_version") != PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION:
        return {"ok": False, "reason": "candidate_version_mismatch"}
    items = snapshot.get("items")
    if not isinstance(items, list):
        return {"ok": False, "reason": "items_not_list"}
    return {"ok": True, "reason": None}


def _existing_valid_preview_v2(existing: Any) -> dict[str, Any] | None:
    check = validate_purchasability_preview_v2_snapshot(existing)
    if check.get("ok") and isinstance(existing, dict):
        return existing
    return None


def build_unavailable_purchasability_preview_v2(
    *,
    today_fixture_id: Any = None,
    reason: str = "unavailable",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return make_json_safe(
        {
            "snapshot_version": PURCHASABILITY_V2_SNAPSHOT_VERSION,
            "contract_version": PURCHASABILITY_V2_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_V2_FEATURE_VERSION,
            "candidate_version": PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
            "candidate_name": PURCHASABILITY_DECISION_V2_CANDIDATE_NAME,
            "registry_status": PURCHASABILITY_V2_REGISTRY_STATUS,
            "status": "unavailable",
            "items": [],
            "summary": {"reason": reason, "today_fixture_id": today_fixture_id},
            "normalization_profile_version": None,
            "normalization_profile_hash": None,
            "normalization_profile_cutoff": PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
            "pre_match_only": True,
            "contains_post_match_fields": False,
            "signals_integration": False,
            "warnings": list(warnings or [reason]),
        }
    )


def build_candidate_and_compact_snapshot_v2(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
    snapshot_info: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    db: Any | None = None,
    source_mode: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    batch = calculate_purchasability_v2_batch(
        kpi_panel=kpi_panel,
        profile=profile,
        fixture_meta=fixture_meta,
        db=db,
    )
    snapshot = build_purchasability_preview_v2_snapshot(
        batch=batch,
        snapshot_info=snapshot_info,
        source_mode=source_mode,
    )
    return batch, snapshot


def attach_purchasability_preview_v2_to_output(
    *,
    cecchino_output: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    existing_preview_v2: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    db: Any | None = None,
) -> dict[str, Any]:
    """Scrive purchasability_preview_v2 senza toccare purchasability_preview."""
    if not isinstance(cecchino_output, dict):
        return cecchino_output

    preserved = _existing_valid_preview_v2(existing_preview_v2)
    if preserved is None:
        preserved = _existing_valid_preview_v2(
            cecchino_output.get("purchasability_preview_v2")
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
            cecchino_output["purchasability_preview_v2"] = preserved
        return cecchino_output

    if not verified:
        if preserved is not None:
            cecchino_output["purchasability_preview_v2"] = preserved
        return cecchino_output

    try:
        _candidate, snapshot = build_candidate_and_compact_snapshot_v2(
            kpi_panel=kpi_panel,
            fixture_meta=fixture_meta,
            snapshot_info={
                **snap,
                "source_snapshot_before_kickoff": before,
            },
            profile=profile,
            db=db,
            source_mode=None,
        )
    except Exception as exc:  # noqa: BLE001 — non bloccante
        warnings.append(f"purchasability_v2_attach_failed:{type(exc).__name__}")
        if preserved is not None:
            out = dict(preserved)
            out_warnings = list(out.get("warnings") or [])
            out_warnings.extend(warnings)
            out["warnings"] = out_warnings
            cecchino_output["purchasability_preview_v2"] = out
        else:
            cecchino_output["purchasability_preview_v2"] = (
                build_unavailable_purchasability_preview_v2(
                    today_fixture_id=fixture_meta.get("today_fixture_id"),
                    reason="purchasability_v2_attach_failed",
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

    cecchino_output["purchasability_preview_v2"] = snapshot
    return cecchino_output


def resolve_purchasability_preview_v2_for_detail(
    *,
    row: Any,
    kpi_panel: dict[str, Any] | None,
    profile: dict[str, Any] | None = None,
    db: Any | None = None,
) -> dict[str, Any]:
    """Detail read-only: persisted v2 → derived → unavailable. Nessuna scrittura."""
    output = getattr(row, "cecchino_output_json", None)
    today_id = getattr(row, "id", None)
    persisted = None
    if isinstance(output, dict):
        persisted = _existing_valid_preview_v2(output.get("purchasability_preview_v2"))
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
        unavail = build_unavailable_purchasability_preview_v2(
            today_fixture_id=today_id,
            reason="snapshot_timestamp_unverified",
        )
        unavail["source_mode"] = "derived_read_only_from_stored_snapshot"
        return unavail

    try:
        norm_profile = profile or get_or_build_normalization_profile(db)
        _cand, snapshot = build_candidate_and_compact_snapshot_v2(
            kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else None,
            fixture_meta=fixture_meta,
            snapshot_info=snap_info,
            profile=norm_profile,
            db=db,
            source_mode="derived_read_only_from_stored_snapshot",
        )
    except Exception:
        return build_unavailable_purchasability_preview_v2(
            today_fixture_id=today_id,
            reason="purchasability_v2_derive_failed",
        )

    if snapshot.get("source_snapshot_before_kickoff") is False:
        return build_unavailable_purchasability_preview_v2(
            today_fixture_id=today_id,
            reason="snapshot_not_before_kickoff",
        )

    snapshot["source_mode"] = "derived_read_only_from_stored_snapshot"
    return make_json_safe(snapshot)


def index_purchasability_v2_snapshot_by_market(
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


def build_purchasability_comparison(
    preview_v1: dict[str, Any] | None,
    preview_v2: dict[str, Any] | None,
) -> dict[str, Any]:
    """Confronto read-only v2 − v1.1 per mercato. Non persistito."""
    from app.services.cecchino.cecchino_purchasability_snapshot import (
        index_purchasability_snapshot_by_market,
    )

    v1_idx = index_purchasability_snapshot_by_market(preview_v1)
    v2_idx = index_purchasability_v2_snapshot_by_market(preview_v2)
    markets = sorted(set(v1_idx.keys()) | set(v2_idx.keys()))
    items: dict[str, Any] = {}
    for mk in markets:
        s1 = (v1_idx.get(mk) or {}).get("score")
        s2 = (v2_idx.get(mk) or {}).get("score")
        try:
            s1_i = int(s1) if s1 is not None else None
        except (TypeError, ValueError):
            s1_i = None
        try:
            s2_i = int(s2) if s2 is not None else None
        except (TypeError, ValueError):
            s2_i = None
        if s1_i is not None and s2_i is not None:
            delta = s2_i - s1_i
            status = "available"
        elif s1_i is None and s2_i is None:
            delta = None
            status = "unavailable"
        else:
            delta = None
            status = "partial"
        items[mk] = {
            "v1_1_score": s1_i,
            "v2_score": s2_i,
            "delta_v2_minus_v1_1": delta,
            "comparison_status": status,
        }
    return {"items": items}
