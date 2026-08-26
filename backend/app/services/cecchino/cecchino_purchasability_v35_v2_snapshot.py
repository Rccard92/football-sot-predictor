"""Snapshot Acquistabilità V3.5 Structural V2 — chiave purchasability_preview_v35_v2.

First valid pre-match write wins. runtime_meta escluso da tutti gli hash.
Math freeze SHA non modificabile (Phase A).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.schemas.cecchino_purchasability_v35_v2 import (
    PURCHASABILITY_V35_V2_CONTRACT_VERSION,
    PURCHASABILITY_V35_V2_EXPERIMENT_VERSION,
    PURCHASABILITY_V35_V2_FEATURE_VERSION,
    PURCHASABILITY_V35_V2_FORMULA_VERSION,
    PURCHASABILITY_V35_V2_REFERENCE_ID,
    PURCHASABILITY_V35_V2_REFERENCE_LABEL,
    PURCHASABILITY_V35_V2_RELATION_REGISTRY_VERSION,
    PURCHASABILITY_V35_V2_SNAPSHOT_REGISTRY_STATUS,
    PURCHASABILITY_V35_V2_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    CONTRACT_VERSION,
    FEATURE_VERSION,
    FORMULA_VERSION,
    RELATION_REGISTRY_VERSION,
    compute_v2_formula_freeze_sha256,
    frozen_config_v35_v2,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_engine import (
    calculate_purchasability_v35_v2_batch,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_features import (
    sanitize_kpi_row_v2,
)

logger = logging.getLogger(__name__)

SNAPSHOT_OUTPUT_KEY = "purchasability_preview_v35_v2"
EXPECTED_FORMULA_FREEZE_SHA256 = (
    "3488f0d8e97f52b3db126ff96758c51adef0acfc8fd98f953b2443e629cd0bfe"
)

_SCORE_BANDS = (
    ("0_39", 0, 39),
    ("40_49", 40, 49),
    ("50_59", 50, 59),
    ("60_69", 60, 69),
    ("70_79", 70, 79),
    ("80_100", 80, 100),
)

_SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")
_PANEL_MARKET_KEY_SET = frozenset(PANEL_MARKET_KEYS)

# Fingerprint: only immutable pre-match row fields (not in math freeze).
_V2_FINGERPRINT_ROW_KEYS = frozenset(
    {
        "market_key",
        "segno",
        "label",
        "quota_book",
        "quota_cecchino",
        "prob_cecchino",
        "prob_book",
        "rating",
        "book_source",
        "odds_source",
        "quote_source",
        "book_fallback_used",
        "derived_quote",
        "not_real_book_quote",
        "force_derived_quote",
    }
)

# Excluded from engine_payload_sha256 — runtime / non-deterministic only.
_ENGINE_HASH_EXCLUDE = frozenset(
    {"generated_at", "warnings", "source_mode", "runtime_meta", "engine_payload_sha256"}
)

V35V2ExistingSnapshotStatus = Literal["absent", "valid", "present_but_invalid"]


@dataclass(frozen=True)
class ClassifiedExistingV35V2Snapshot:
    status: V35V2ExistingSnapshotStatus
    snapshot: Any | None
    validation: dict[str, Any] | None


def _is_valid_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_HEX_RE.match(value))


def _log_v35_v2_snapshot_conflict(existing: Any, reason: Any) -> None:
    if isinstance(existing, dict) and existing.get("snapshot_version"):
        logger.warning(
            "purchasability_v35_v2_snapshot_conflict reason=%s",
            reason,
        )


def build_runtime_meta_v35_v2() -> dict[str, Any]:
    """Runtime truth — NEVER included in formula/engine/input hashes."""
    return {
        "active_v35_structural_version": "v2",
        "runtime_wired": True,
        "holdout_mode": "paired_v1_v2",
        "note": (
            "frozen_math_config.active_v35_structural_version_wired=False "
            "is Phase A design-freeze historical metadata, not runtime truth"
        ),
    }


def _validate_v2_items_integrity(items: list[Any]) -> dict[str, Any] | None:
    expected_count = len(PANEL_MARKET_KEYS)
    if len(items) != expected_count:
        return {"ok": False, "reason": "items_count_mismatch"}
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            return {"ok": False, "reason": "invalid_market_item"}
        mk = item.get("market_key")
        if not isinstance(mk, str) or not mk:
            return {"ok": False, "reason": "missing_market_key"}
        if mk not in _PANEL_MARKET_KEY_SET:
            return {"ok": False, "reason": "invalid_market_key"}
        if mk in seen:
            return {"ok": False, "reason": "duplicate_market_key"}
        seen.add(mk)
    if seen != _PANEL_MARKET_KEY_SET:
        return {"ok": False, "reason": "market_set_mismatch"}
    return None


def _parse_dt(dt: Any) -> datetime | None:
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


def _iso_at(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _score_band(score: Any) -> str | None:
    if score is None:
        return None
    try:
        n = int(round(float(score)))
    except (TypeError, ValueError):
        return None
    for label, lo, hi in _SCORE_BANDS:
        if lo <= n <= hi:
            return label
    return None


def _empty_band_counts() -> dict[str, int]:
    return {label: 0 for label, _, _ in _SCORE_BANDS}


def _compact_v2_item(item: dict[str, Any]) -> dict[str, Any]:
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    components = item.get("components") if isinstance(item.get("components"), dict) else {}
    reference = item.get("reference") if isinstance(item.get("reference"), dict) else {}
    return {
        "contract_version": item.get("contract_version") or CONTRACT_VERSION,
        "feature_version": item.get("feature_version") or FEATURE_VERSION,
        "formula_version": item.get("formula_version") or FORMULA_VERSION,
        "relation_registry_version": item.get("relation_registry_version")
        or RELATION_REGISTRY_VERSION,
        "registry_status": item.get("registry_status"),
        "market_key": item.get("market_key"),
        "label": item.get("label"),
        "status": item.get("status"),
        "gate_status": item.get("gate_status") or gate.get("gate_status"),
        "gate": gate,
        "input": inp,
        "components": components,
        "value_core": item.get("value_core"),
        "acquisition_core": item.get("acquisition_core"),
        "structural_factor": item.get("structural_factor"),
        "quality_factor": item.get("quality_factor"),
        "adjusted_confidence": item.get("adjusted_confidence"),
        "structural_missing_penalty_applied": item.get(
            "structural_missing_penalty_applied"
        ),
        "reference": reference,
        "score": item.get("score"),
        "raw_score": item.get("raw_score"),
        "class": item.get("class"),
        "dependency_meta": item.get("dependency_meta"),
        "pre_match_only": True,
        "contains_post_match_fields": False,
    }


def _build_reference_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    band_counts = _empty_band_counts()
    top_market_key: str | None = None
    top_score: int | None = None
    top_raw_score: float | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        sc = item.get("score")
        if sc is None:
            continue
        band = _score_band(sc)
        if band:
            band_counts[band] += 1
        try:
            sc_int = int(sc)
        except (TypeError, ValueError):
            continue
        if top_score is None or sc_int > top_score:
            top_score = sc_int
            top_raw_score = item.get("raw_score")
            top_market_key = item.get("market_key")
    return {
        "reference_id": PURCHASABILITY_V35_V2_REFERENCE_ID,
        "reference_label": PURCHASABILITY_V35_V2_REFERENCE_LABEL,
        "top_market_key": top_market_key,
        "top_score": top_score,
        "top_raw_score": top_raw_score,
        "score_band_counts": band_counts,
    }


def _panel_rows(kpi_panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(kpi_panel, dict):
        return []
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def input_fingerprint_v35_v2(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None,
) -> str:
    """SHA256 input pre-match immutabile — no runtime_meta."""
    meta = fixture_meta or {}
    compact_rows = []
    for row in _panel_rows(kpi_panel):
        clean = sanitize_kpi_row_v2(row)
        compact_rows.append(
            {k: clean.get(k) for k in sorted(_V2_FINGERPRINT_ROW_KEYS) if k in clean}
        )
    compact_rows.sort(key=lambda r: str(r.get("market_key") or ""))
    payload = make_json_safe(
        {
            "today_fixture_id": meta.get("today_fixture_id"),
            "provider_fixture_id": meta.get("provider_fixture_id"),
            "local_fixture_id": meta.get("local_fixture_id"),
            "competition_id": meta.get("competition_id"),
            "scan_date": str(meta.get("scan_date") or ""),
            "source_snapshot_at": str(meta.get("snapshot_at") or ""),
            "kickoff": str(meta.get("kickoff") or ""),
            "rows": compact_rows,
            "contract_version": CONTRACT_VERSION,
            "feature_version": FEATURE_VERSION,
            "formula_version": FORMULA_VERSION,
            "relation_registry_version": RELATION_REGISTRY_VERSION,
        }
    )
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def engine_payload_sha256_v35_v2(snapshot: dict[str, Any]) -> str:
    """Hash engine immutabile — esclude runtime_meta e campi non deterministici."""
    payload = make_json_safe(
        {k: v for k, v in snapshot.items() if k not in _ENGINE_HASH_EXCLUDE}
    )
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    base = {
        "rows_total": len(items),
        "score_count": sum(1 for it in items if it.get("status") == "score"),
        "gate_failed_count": sum(
            1 for it in items if it.get("status") == "gate_failed"
        ),
        "non_calculable_count": sum(
            1 for it in items if it.get("status") == "not_calculable"
        ),
        "reference": _build_reference_summary(items),
    }
    return base


def build_purchasability_preview_v35_v2_snapshot(
    *,
    batch: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    source_mode: str = "persisted_pre_match_snapshot",
    warnings: list[str] | None = None,
    generated_at: str | None = None,
    input_fingerprint: str | None = None,
    kickoff: Any = None,
) -> dict[str, Any]:
    snap = snapshot_info or {}
    items = [
        _compact_v2_item(it)
        for it in (batch.get("items") or [])
        if isinstance(it, dict)
    ]
    now = generated_at or datetime.now(timezone.utc).isoformat()
    source_at_iso = _iso_at(snap.get("snapshot_at"))
    kickoff_val = kickoff if kickoff is not None else snap.get("kickoff")
    kickoff_iso = _iso_at(kickoff_val)
    relation_registry = batch.get("relation_registry")
    if relation_registry is None:
        relation_registry = []

    frozen = frozen_config_v35_v2()
    freeze_sha = frozen.get("formula_freeze_sha256") or compute_v2_formula_freeze_sha256()

    snapshot_body: dict[str, Any] = {
        "snapshot_version": PURCHASABILITY_V35_V2_SNAPSHOT_VERSION,
        "contract_version": PURCHASABILITY_V35_V2_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_V35_V2_FEATURE_VERSION,
        "formula_version": PURCHASABILITY_V35_V2_FORMULA_VERSION,
        "relation_registry_version": PURCHASABILITY_V35_V2_RELATION_REGISTRY_VERSION,
        "registry_status": PURCHASABILITY_V35_V2_SNAPSHOT_REGISTRY_STATUS,
        "generated_at": now,
        "source_snapshot_at": source_at_iso,
        "source_snapshot_verified": bool(snap.get("snapshot_timestamp_verified")),
        "source_snapshot_before_kickoff": snap.get("source_snapshot_before_kickoff"),
        "pre_match_verified": bool(batch.get("pre_match_verified")),
        "kickoff": kickoff_iso,
        "source_mode": source_mode,
        "experiment_version": PURCHASABILITY_V35_V2_EXPERIMENT_VERSION,
        "input_fingerprint_sha256": input_fingerprint,
        "formula_freeze_sha256": freeze_sha,
        "frozen_config": frozen,
        "relation_registry": relation_registry,
        "reference": {
            "id": PURCHASABILITY_V35_V2_REFERENCE_ID,
            "label": PURCHASABILITY_V35_V2_REFERENCE_LABEL,
        },
        "items": items,
        "summary": _build_summary(items),
        "pre_match_only": True,
        "contains_post_match_fields": False,
        "historical_reliability_integrated": False,
        "shadow_candidate": True,
        "current_operational_version": False,
        "immutable_first_write": True,
        "warnings": list(warnings or []),
        # Runtime truth — excluded from engine_payload_sha256
        "runtime_meta": build_runtime_meta_v35_v2(),
    }
    snapshot_body["engine_payload_sha256"] = engine_payload_sha256_v35_v2(snapshot_body)
    return make_json_safe(snapshot_body)


def validate_purchasability_preview_v35_v2_snapshot(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"ok": False, "reason": "not_a_dict"}

    if snapshot.get("snapshot_version") != PURCHASABILITY_V35_V2_SNAPSHOT_VERSION:
        return {"ok": False, "reason": "snapshot_version_mismatch"}

    for field, expected in (
        ("contract_version", PURCHASABILITY_V35_V2_CONTRACT_VERSION),
        ("feature_version", PURCHASABILITY_V35_V2_FEATURE_VERSION),
        ("formula_version", PURCHASABILITY_V35_V2_FORMULA_VERSION),
        (
            "relation_registry_version",
            PURCHASABILITY_V35_V2_RELATION_REGISTRY_VERSION,
        ),
    ):
        if snapshot.get(field) != expected:
            return {"ok": False, "reason": f"{field}_mismatch"}

    if snapshot.get("source_snapshot_verified") is not True:
        return {"ok": False, "reason": "source_snapshot_not_verified"}
    if not snapshot.get("source_snapshot_at"):
        return {"ok": False, "reason": "missing_source_snapshot_at"}
    if not snapshot.get("kickoff"):
        return {"ok": False, "reason": "missing_kickoff"}

    snap_dt = _parse_dt(snapshot.get("source_snapshot_at"))
    kick_dt = _parse_dt(snapshot.get("kickoff"))
    if snap_dt is None or kick_dt is None:
        return {"ok": False, "reason": "unparseable_timestamps"}
    if snap_dt >= kick_dt:
        return {"ok": False, "reason": "source_snapshot_not_before_kickoff"}

    if snapshot.get("pre_match_verified") is not True:
        return {"ok": False, "reason": "pre_match_not_verified"}
    if snapshot.get("contains_post_match_fields") is True:
        return {"ok": False, "reason": "contains_post_match_fields"}

    items = snapshot.get("items")
    if not isinstance(items, list):
        return {"ok": False, "reason": "items_not_list"}

    fingerprint = snapshot.get("input_fingerprint_sha256")
    if not fingerprint:
        return {"ok": False, "reason": "missing_input_fingerprint_sha256"}
    if not _is_valid_sha256_hex(fingerprint):
        return {"ok": False, "reason": "invalid_input_fingerprint_sha256"}

    freeze_sha = snapshot.get("formula_freeze_sha256")
    if freeze_sha != EXPECTED_FORMULA_FREEZE_SHA256:
        return {"ok": False, "reason": "formula_freeze_sha256_mismatch"}

    frozen_config = snapshot.get("frozen_config")
    if not isinstance(frozen_config, dict):
        return {"ok": False, "reason": "missing_or_invalid_frozen_config"}
    if frozen_config.get("formula_freeze_sha256") != EXPECTED_FORMULA_FREEZE_SHA256:
        return {"ok": False, "reason": "frozen_config_formula_freeze_mismatch"}

    if snapshot.get("relation_registry") is None or not isinstance(
        snapshot.get("relation_registry"), list
    ):
        return {"ok": False, "reason": "missing_or_invalid_relation_registry"}

    if snapshot.get("summary") is None or not isinstance(snapshot.get("summary"), dict):
        return {"ok": False, "reason": "missing_or_invalid_summary"}

    items_error = _validate_v2_items_integrity(items)
    if items_error is not None:
        return items_error

    persisted_hash = snapshot.get("engine_payload_sha256")
    if not persisted_hash:
        return {"ok": False, "reason": "missing_engine_payload_sha256"}
    if not _is_valid_sha256_hex(persisted_hash):
        return {"ok": False, "reason": "invalid_engine_payload_sha256"}

    expected_hash = engine_payload_sha256_v35_v2(snapshot)
    if expected_hash != persisted_hash:
        return {"ok": False, "reason": "engine_payload_sha256_mismatch"}

    return {"ok": True, "reason": None}


def classify_existing_v35_v2_snapshot(existing: Any) -> ClassifiedExistingV35V2Snapshot:
    """ABSENT / VALID / PRESENT_BUT_INVALID."""
    if existing is None:
        return ClassifiedExistingV35V2Snapshot("absent", None, None)
    check = validate_purchasability_preview_v35_v2_snapshot(existing)
    if check.get("ok"):
        return ClassifiedExistingV35V2Snapshot("valid", existing, check)
    return ClassifiedExistingV35V2Snapshot("present_but_invalid", existing, check)


def _resolve_existing_v2_from_sources(
    existing_preview_v35_v2: Any,
    cecchino_output: dict[str, Any],
) -> ClassifiedExistingV35V2Snapshot:
    if existing_preview_v35_v2 is not None:
        return classify_existing_v35_v2_snapshot(existing_preview_v35_v2)
    if SNAPSHOT_OUTPUT_KEY in cecchino_output:
        return classify_existing_v35_v2_snapshot(cecchino_output[SNAPSHOT_OUTPUT_KEY])
    return classify_existing_v35_v2_snapshot(None)


def resolve_valid_persisted_purchasability_v35_v2(
    existing: Any,
) -> dict[str, Any] | None:
    classified = classify_existing_v35_v2_snapshot(existing)
    if classified.status == "valid" and isinstance(classified.snapshot, dict):
        return classified.snapshot
    if classified.status == "present_but_invalid":
        _log_v35_v2_snapshot_conflict(
            existing,
            classified.validation.get("reason") if classified.validation else None,
        )
    return None


def build_candidate_and_compact_snapshot_v35_v2(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
    snapshot_info: dict[str, Any] | None = None,
    source_mode: str = "persisted_pre_match_snapshot",
    warnings: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    meta = dict(fixture_meta or {})
    batch = calculate_purchasability_v35_v2_batch(
        kpi_panel=kpi_panel,
        fixture_meta=meta,
    )
    if not batch.get("pre_match_verified"):
        return batch, None

    fp = input_fingerprint_v35_v2(kpi_panel=kpi_panel, fixture_meta=meta)
    snapshot = build_purchasability_preview_v35_v2_snapshot(
        batch=batch,
        snapshot_info=snapshot_info,
        source_mode=source_mode,
        warnings=warnings,
        input_fingerprint=fp,
        kickoff=meta.get("kickoff"),
    )
    return batch, snapshot


def attach_purchasability_preview_v35_v2_to_output(
    *,
    cecchino_output: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    existing_preview_v35_v2: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scrive purchasability_preview_v35_v2 — first valid pre-match write wins."""
    if not isinstance(cecchino_output, dict):
        return cecchino_output

    existing = _resolve_existing_v2_from_sources(
        existing_preview_v35_v2, cecchino_output
    )

    if existing.status == "valid":
        cecchino_output[SNAPSHOT_OUTPUT_KEY] = existing.snapshot
        return cecchino_output

    if existing.status == "present_but_invalid":
        _log_v35_v2_snapshot_conflict(
            existing.snapshot,
            existing.validation.get("reason") if existing.validation else None,
        )
        cecchino_output[SNAPSHOT_OUTPUT_KEY] = existing.snapshot
        return cecchino_output

    # ABSENT — may create only if pre-match gate OK
    snap = snapshot_info or {}
    verified = bool(snap.get("snapshot_timestamp_verified"))
    snap_dt = _parse_dt(snap.get("snapshot_at"))
    kick_dt = _parse_dt(fixture_meta.get("kickoff"))
    before: bool | None = None
    if snap_dt is not None and kick_dt is not None:
        before = snap_dt < kick_dt

    warnings: list[str] = []

    if before is False:
        return cecchino_output
    if not verified or before is not True:
        return cecchino_output

    try:
        _batch, snapshot = build_candidate_and_compact_snapshot_v35_v2(
            kpi_panel=kpi_panel,
            fixture_meta={
                **fixture_meta,
                "snapshot_at": snap.get("snapshot_at"),
                "kickoff": fixture_meta.get("kickoff"),
            },
            snapshot_info={
                **snap,
                "source_snapshot_before_kickoff": before,
            },
            source_mode="persisted_pre_match_snapshot",
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001 — non bloccante
        warnings.append(f"purchasability_v35_v2_attach_failed:{type(exc).__name__}")
        logger.warning(
            "purchasability_v35_v2_attach_failed fixture=%s error=%s",
            fixture_meta.get("today_fixture_id"),
            type(exc).__name__,
            exc_info=True,
        )
        return cecchino_output

    if snapshot is None:
        return cecchino_output

    if snapshot.get("source_snapshot_verified") is None:
        snapshot["source_snapshot_verified"] = verified
    if snapshot.get("source_snapshot_before_kickoff") is None and before is not None:
        snapshot["source_snapshot_before_kickoff"] = before
    if snapshot.get("source_snapshot_at") is None and snap.get("snapshot_at"):
        snapshot["source_snapshot_at"] = _iso_at(snap.get("snapshot_at"))
    if warnings:
        snapshot["warnings"] = list(snapshot.get("warnings") or []) + warnings
        # warnings excluded from engine hash — recompute hash after warning mutate? 
        # Keep hash from build time; warnings are excluded so hash stays valid.
        # But if we mutate warnings after hash, validation still OK since excluded.

    cecchino_output[SNAPSHOT_OUTPUT_KEY] = snapshot
    return cecchino_output


def index_purchasability_v35_v2_snapshot_by_market(
    snapshot: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(snapshot, dict):
        return out
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict):
            continue
        mk = item.get("market_key")
        if isinstance(mk, str) and mk:
            out[mk] = item
    return out


def fixture_has_v35_v2_score(snapshot: dict[str, Any] | None) -> bool:
    if not isinstance(snapshot, dict):
        return False
    for item in snapshot.get("items") or []:
        if isinstance(item, dict) and item.get("status") == "score":
            return True
    return False


def resolve_purchasability_preview_v35_v2_for_detail(*, row: Any) -> dict[str, Any]:
    """Detail read-only — no V2 recalculation."""
    output = getattr(row, "cecchino_output_json", None)
    persisted = None
    if isinstance(output, dict):
        persisted = output.get(SNAPSHOT_OUTPUT_KEY)

    classified = classify_existing_v35_v2_snapshot(persisted)

    if classified.status == "absent":
        return {
            "purchasability_preview_v35_v2": None,
            "purchasability_v35_v2_snapshot_status": "absent",
            "purchasability_v35_v2_snapshot_reason": "snapshot_unavailable",
        }

    if classified.status == "valid" and isinstance(classified.snapshot, dict):
        return {
            "purchasability_preview_v35_v2": make_json_safe(dict(classified.snapshot)),
            "purchasability_v35_v2_snapshot_status": "valid",
            "purchasability_v35_v2_snapshot_reason": None,
        }

    reason: str | None = None
    if classified.validation and isinstance(classified.validation, dict):
        raw_reason = classified.validation.get("reason")
        if isinstance(raw_reason, str):
            reason = raw_reason
    return {
        "purchasability_preview_v35_v2": None,
        "purchasability_v35_v2_snapshot_status": "present_but_invalid",
        "purchasability_v35_v2_snapshot_reason": reason or "invalid_snapshot",
    }


__all__ = [
    "EXPECTED_FORMULA_FREEZE_SHA256",
    "SNAPSHOT_OUTPUT_KEY",
    "ClassifiedExistingV35V2Snapshot",
    "attach_purchasability_preview_v35_v2_to_output",
    "build_candidate_and_compact_snapshot_v35_v2",
    "build_purchasability_preview_v35_v2_snapshot",
    "build_runtime_meta_v35_v2",
    "classify_existing_v35_v2_snapshot",
    "engine_payload_sha256_v35_v2",
    "fixture_has_v35_v2_score",
    "index_purchasability_v35_v2_snapshot_by_market",
    "input_fingerprint_v35_v2",
    "resolve_purchasability_preview_v35_v2_for_detail",
    "resolve_valid_persisted_purchasability_v35_v2",
    "validate_purchasability_preview_v35_v2_snapshot",
]
