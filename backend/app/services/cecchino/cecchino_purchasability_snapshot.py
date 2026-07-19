"""Compact snapshot Acquistabilità V1 Preview — Fase 4/5.

Versione: cecchino_purchasability_snapshot_v1

Persiste un sottoinsieme versionato del candidate batch in
cecchino_output_json["purchasability_preview"]. Nessun settlement/post-match.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_FEATURE_VERSION,
    PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
    PURCHASABILITY_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_candidate import (
    ACTIVE_PURCHASABILITY_CANDIDATE_NAME,
    ACTIVE_PURCHASABILITY_CANDIDATE_VERSION,
)

COMPACT_ITEM_KEYS = (
    "market_key",
    "selection",
    "status",
    "calculation_quality",
    "score",
    "raw_score",
    "class",
    "reading",
    "phase_1_score",
    "phase_2_score",
    "reason_codes",
)


def canonical_candidate_batch_sha256(candidate_batch: dict[str, Any]) -> str:
    """SHA256 del candidate batch completo (JSON canonico)."""
    payload = make_json_safe(candidate_batch)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    phase1 = item.get("phase_1_value") if isinstance(item.get("phase_1_value"), dict) else {}
    phase2 = item.get("phase_2_quality") if isinstance(item.get("phase_2_quality"), dict) else {}
    return {
        "market_key": item.get("market_key"),
        "selection": item.get("selection") or item.get("market_key"),
        "status": item.get("status"),
        "calculation_quality": item.get("calculation_quality"),
        "score": item.get("score"),
        "raw_score": item.get("raw_score"),
        "class": item.get("class"),
        "reading": item.get("reading"),
        "phase_1_score": phase1.get("score"),
        "phase_2_score": phase2.get("score"),
        "reason_codes": list(item.get("reason_codes") or []),
    }


def build_purchasability_preview_snapshot(
    candidate_batch: dict[str, Any],
    *,
    source_mode: str | None = None,
) -> dict[str, Any]:
    """Costruisce lo snapshot compatto dal candidate batch completo."""
    items_in = candidate_batch.get("items") if isinstance(candidate_batch, dict) else None
    if not isinstance(items_in, list):
        items_in = []

    compact_items = [
        _compact_item(it) for it in items_in if isinstance(it, dict)
    ]

    # Source meta: preferisci data_quality del primo item con info
    source_snapshot_at = None
    source_verified = None
    source_before_kickoff = None
    for it in items_in:
        if not isinstance(it, dict):
            continue
        dq = it.get("data_quality") if isinstance(it.get("data_quality"), dict) else {}
        if source_snapshot_at is None and dq.get("snapshot_at") is not None:
            source_snapshot_at = dq.get("snapshot_at")
        if source_verified is None and "snapshot_timestamp_verified" in dq:
            source_verified = dq.get("snapshot_timestamp_verified")
        if source_before_kickoff is None and "snapshot_before_kickoff" in dq:
            source_before_kickoff = dq.get("snapshot_before_kickoff")
        if (
            source_snapshot_at is not None
            and source_verified is not None
            and source_before_kickoff is not None
        ):
            break

    summary = candidate_batch.get("summary") if isinstance(candidate_batch.get("summary"), dict) else {}
    compact_summary = {
        "total": summary.get("total", len(compact_items)),
        "available": summary.get("available"),
        "partial": summary.get("partial"),
        "unavailable": summary.get("unavailable"),
        "score_min": summary.get("score_min"),
        "score_max": summary.get("score_max"),
        "score_mean": summary.get("score_mean"),
        "class_distribution": summary.get("class_distribution"),
    }

    snap: dict[str, Any] = {
        "snapshot_version": PURCHASABILITY_SNAPSHOT_VERSION,
        "contract_version": PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_FEATURE_VERSION,
        "candidate_version": candidate_batch.get("candidate_version")
        or ACTIVE_PURCHASABILITY_CANDIDATE_VERSION,
        "candidate_name": candidate_batch.get("candidate_name")
        or ACTIVE_PURCHASABILITY_CANDIDATE_NAME,
        "status": candidate_batch.get("status") or "unavailable",
        "today_fixture_id": candidate_batch.get("today_fixture_id"),
        "source": "stored_pre_match_kpi_panel",
        "source_snapshot_at": source_snapshot_at,
        "source_snapshot_verified": source_verified,
        "source_snapshot_before_kickoff": source_before_kickoff,
        "items": compact_items,
        "summary": compact_summary,
        "full_candidate_payload_sha256": canonical_candidate_batch_sha256(
            candidate_batch
        ),
        "pre_match_only": True,
        "contains_result_fields": False,
        "contains_settlement_fields": False,
        "signals_integration": False,
    }
    if source_mode:
        snap["source_mode"] = source_mode

    safe = make_json_safe(snap)
    json.dumps(safe, allow_nan=False)
    return safe


def validate_purchasability_preview_snapshot(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Valida struttura minima dello snapshot. Restituisce {ok, reason_codes}."""
    reasons: list[str] = []
    if not isinstance(snapshot, dict):
        return {"ok": False, "reason_codes": ["snapshot_not_a_dict"]}
    if snapshot.get("snapshot_version") != PURCHASABILITY_SNAPSHOT_VERSION:
        reasons.append("snapshot_version_mismatch")
    if not snapshot.get("candidate_version"):
        reasons.append("candidate_version_missing")
    if not isinstance(snapshot.get("items"), list):
        reasons.append("items_missing")
    if snapshot.get("contains_settlement_fields") is True:
        reasons.append("settlement_fields_forbidden")
    if snapshot.get("contains_result_fields") is True:
        reasons.append("result_fields_forbidden")
    if snapshot.get("signals_integration") is True:
        reasons.append("signals_integration_forbidden")
    return {"ok": len(reasons) == 0, "reason_codes": reasons}


def index_purchasability_snapshot_by_market(
    snapshot: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Indice market_key → item compatto."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(snapshot, dict):
        return out
    items = snapshot.get("items")
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        key = it.get("market_key") or it.get("selection")
        if key:
            out[str(key)] = it
    return out


def build_unavailable_purchasability_preview(
    *,
    today_fixture_id: int | None = None,
    reason: str = "purchasability_snapshot_unavailable",
) -> dict[str, Any]:
    return make_json_safe(
        {
            "snapshot_version": PURCHASABILITY_SNAPSHOT_VERSION,
            "contract_version": PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_FEATURE_VERSION,
            "candidate_version": ACTIVE_PURCHASABILITY_CANDIDATE_VERSION,
            "candidate_name": ACTIVE_PURCHASABILITY_CANDIDATE_NAME,
            "status": "unavailable",
            "today_fixture_id": today_fixture_id,
            "source": "stored_pre_match_kpi_panel",
            "source_snapshot_at": None,
            "source_snapshot_verified": False,
            "source_snapshot_before_kickoff": None,
            "items": [],
            "summary": {
                "total": 0,
                "available": 0,
                "partial": 0,
                "unavailable": 0,
                "score_min": None,
                "score_max": None,
                "score_mean": None,
                "class_distribution": {},
            },
            "full_candidate_payload_sha256": None,
            "pre_match_only": True,
            "contains_result_fields": False,
            "contains_settlement_fields": False,
            "signals_integration": False,
            "reason_codes": [reason],
        }
    )


def _existing_valid_preview(existing: Any) -> dict[str, Any] | None:
    if not isinstance(existing, dict):
        return None
    check = validate_purchasability_preview_snapshot(existing)
    if check["ok"]:
        return existing
    return None


def build_candidate_and_compact_snapshot(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    context_meta: dict[str, Any] | None = None,
    source_mode: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Feature → candidate_2 → compact snapshot (in-memory)."""
    from app.services.cecchino.cecchino_purchasability_candidate import (
        calculate_purchasability_candidate_batch,
    )
    from app.services.cecchino.cecchino_purchasability_features import (
        build_purchasability_features_for_panel,
    )

    features = build_purchasability_features_for_panel(
        kpi_panel=kpi_panel,
        fixture_meta=fixture_meta,
        context_meta=context_meta,
        snapshot_info=snapshot_info,
    )
    candidate = calculate_purchasability_candidate_batch(features)
    snapshot = build_purchasability_preview_snapshot(
        candidate, source_mode=source_mode
    )
    return candidate, snapshot


def attach_purchasability_preview_to_output(
    *,
    cecchino_output: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    existing_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scrive purchasability_preview su cecchino_output se pre-match verificato.

    Post-kickoff: preserva existing_preview se valido; non inventa score.
    """
    from datetime import datetime, timezone

    if not isinstance(cecchino_output, dict):
        return cecchino_output

    preserved = _existing_valid_preview(existing_preview)
    if preserved is None:
        preserved = _existing_valid_preview(
            cecchino_output.get("purchasability_preview")
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

    if before is False:
        if preserved is not None:
            cecchino_output["purchasability_preview"] = preserved
        return cecchino_output

    if not verified:
        if preserved is not None:
            cecchino_output["purchasability_preview"] = preserved
        return cecchino_output

    try:
        _candidate, snapshot = build_candidate_and_compact_snapshot(
            kpi_panel=kpi_panel,
            fixture_meta=fixture_meta,
            snapshot_info=snapshot_info,
            source_mode=None,
        )
    except Exception:
        if preserved is not None:
            cecchino_output["purchasability_preview"] = preserved
        return cecchino_output

    # Enrich source meta from gate if items lacked it
    if snapshot.get("source_snapshot_verified") is None:
        snapshot["source_snapshot_verified"] = verified
    if snapshot.get("source_snapshot_before_kickoff") is None and before is not None:
        snapshot["source_snapshot_before_kickoff"] = before
    if snapshot.get("source_snapshot_at") is None and snap.get("snapshot_at"):
        at = snap.get("snapshot_at")
        snapshot["source_snapshot_at"] = (
            at.isoformat() if isinstance(at, datetime) else at
        )

    cecchino_output["purchasability_preview"] = snapshot
    return cecchino_output


def resolve_purchasability_preview_for_detail(
    *,
    row: Any,
    kpi_panel: dict[str, Any] | None,
) -> dict[str, Any]:
    """Detail read-only: persisted → derived → unavailable."""
    output = getattr(row, "cecchino_output_json", None)
    today_id = getattr(row, "id", None)
    persisted = None
    if isinstance(output, dict):
        persisted = _existing_valid_preview(output.get("purchasability_preview"))
    if persisted is not None:
        out = dict(persisted)
        out["source_mode"] = "persisted_pre_match_snapshot"
        return make_json_safe(out)

    # Derive from stored panel/odds — no commit
    from app.services.cecchino.cecchino_purchasability_audit import (
        resolve_purchasability_snapshot_timestamp,
    )

    snap_info = resolve_purchasability_snapshot_timestamp(row)
    snap_at = snap_info.get("snapshot_at")
    from datetime import datetime

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

    # Se timestamp non verificabile come pre-match → unavailable
    if not snap_info.get("snapshot_timestamp_verified"):
        # Ancora: se kickoff/snapshot dicono post-match, unavailable
        unavail = build_unavailable_purchasability_preview(
            today_fixture_id=today_id,
            reason="snapshot_timestamp_unverified",
        )
        unavail["source_mode"] = "derived_read_only_from_stored_snapshot"
        return unavail

    try:
        _cand, snapshot = build_candidate_and_compact_snapshot(
            kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else None,
            fixture_meta=fixture_meta,
            snapshot_info=snap_info,
            source_mode="derived_read_only_from_stored_snapshot",
        )
    except Exception:
        return build_unavailable_purchasability_preview(
            today_fixture_id=today_id,
            reason="purchasability_derive_failed",
        )

    if snapshot.get("source_snapshot_before_kickoff") is False:
        return build_unavailable_purchasability_preview(
            today_fixture_id=today_id,
            reason="snapshot_not_before_kickoff",
        )

    snapshot["source_mode"] = "derived_read_only_from_stored_snapshot"
    return make_json_safe(snapshot)
