"""Snapshot Acquistabilità V3.5 — chiave separata purchasability_preview_v35.

Esperimento live shadow: first valid pre-match write wins, nessuna derivazione read-time.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_CANDIDATE_REGISTRY_VERSION,
    PURCHASABILITY_V35_CONTRACT_VERSION,
    PURCHASABILITY_V35_EXPERIMENT_VERSION,
    PURCHASABILITY_V35_FEATURE_VERSION,
    PURCHASABILITY_V35_FORMULA_VERSION,
    PURCHASABILITY_V35_RELATION_REGISTRY_VERSION,
    PURCHASABILITY_V35_SNAPSHOT_REGISTRY_STATUS,
    PURCHASABILITY_V35_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v35_candidate import (
    calculate_purchasability_v35_batch,
)
from app.services.cecchino.cecchino_purchasability_v35_config import (
    CANDIDATE_REGISTRY_VERSION,
    CONTRACT_VERSION,
    FEATURE_VERSION,
    FORMULA_VERSION,
    RELATION_REGISTRY_VERSION,
    V35_ALLOWED_ROW_KEYS,
    candidate_registry_v35,
    frozen_config_v35,
)
from app.services.cecchino.cecchino_purchasability_v35_features import (
    sanitize_kpi_row,
)

logger = logging.getLogger(__name__)

_SCORE_BANDS = (
    ("0_19", 0, 19),
    ("20_39", 20, 39),
    ("40_59", 40, 59),
    ("60_79", 60, 79),
    ("80_100", 80, 100),
)

_CANDIDATE_KEYS = ("A", "B", "C", "D")


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


def _compact_v35_item(item: dict[str, Any]) -> dict[str, Any]:
    """Preserva struttura item batch per analisi futura."""
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    components = item.get("components") if isinstance(item.get("components"), dict) else {}
    candidates = item.get("candidates") if isinstance(item.get("candidates"), dict) else {}
    diagnostics = item.get("diagnostics") if isinstance(item.get("diagnostics"), dict) else {}
    return {
        "contract_version": item.get("contract_version") or CONTRACT_VERSION,
        "feature_version": item.get("feature_version") or FEATURE_VERSION,
        "formula_version": item.get("formula_version") or FORMULA_VERSION,
        "relation_registry_version": item.get("relation_registry_version")
        or RELATION_REGISTRY_VERSION,
        "candidate_registry_version": item.get("candidate_registry_version")
        or CANDIDATE_REGISTRY_VERSION,
        "registry_status": item.get("registry_status"),
        "market_key": item.get("market_key"),
        "label": item.get("label"),
        "status": item.get("status"),
        "gate_status": item.get("gate_status") or gate.get("gate_status"),
        "gate": gate,
        "input": inp,
        "components": components,
        "candidates": candidates,
        "diagnostics": diagnostics,
        "dependency_meta": item.get("dependency_meta"),
        "pre_match_only": True,
        "contains_post_match_fields": False,
    }


def _build_candidate_summary(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Summary per candidate A/B/C/D con band counts condivisi (gate comune)."""
    out: dict[str, dict[str, Any]] = {}
    for ck in _CANDIDATE_KEYS:
        band_counts = _empty_band_counts()
        top_market_key: str | None = None
        top_score: int | None = None
        top_raw_score: float | None = None

        for item in items:
            if not isinstance(item, dict):
                continue
            cand = (item.get("candidates") or {}).get(ck)
            if not isinstance(cand, dict):
                continue
            sc = cand.get("score")
            if sc is not None:
                band = _score_band(sc)
                if band:
                    band_counts[band] += 1
                try:
                    sc_int = int(sc)
                except (TypeError, ValueError):
                    continue
                if top_score is None or sc_int > top_score:
                    top_score = sc_int
                    top_raw_score = cand.get("raw_score")
                    top_market_key = item.get("market_key")

        out[ck] = {
            "top_market_key": top_market_key,
            "top_score": top_score,
            "top_raw_score": top_raw_score,
            "score_band_counts": band_counts,
        }
    return out


def _panel_rows(kpi_panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(kpi_panel, dict):
        return []
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def input_fingerprint_v35(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None,
) -> str:
    """Fingerprint input autonomo V3.5 — no import V3.1."""
    meta = fixture_meta or {}
    compact_rows = []
    for row in _panel_rows(kpi_panel):
        clean = sanitize_kpi_row(row)
        compact_rows.append(
            {
                k: clean.get(k)
                for k in sorted(V35_ALLOWED_ROW_KEYS)
                if k in clean
            }
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
            "candidate_registry_version": CANDIDATE_REGISTRY_VERSION,
        }
    )
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def engine_payload_sha256_v35(snapshot: dict[str, Any]) -> str:
    """Hash output congelato — esclude generated_at e campi runtime non deterministici."""
    exclude = frozenset({"generated_at", "warnings", "source_mode"})
    payload = make_json_safe(
        {
            k: v
            for k, v in snapshot.items()
            if k not in exclude and k != "engine_payload_sha256"
        }
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
    }
    base.update(_build_candidate_summary(items))
    return base


def build_purchasability_preview_v35_snapshot(
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
        _compact_v35_item(it) for it in (batch.get("items") or []) if isinstance(it, dict)
    ]
    now = generated_at
    if now is None:
        now = datetime.now(timezone.utc).isoformat()

    source_at = snap.get("snapshot_at")
    source_at_iso = _iso_at(source_at)
    kickoff_val = kickoff if kickoff is not None else snap.get("kickoff")
    kickoff_iso = _iso_at(kickoff_val)

    relation_registry = batch.get("relation_registry")
    if relation_registry is None:
        relation_registry = []

    snapshot_body: dict[str, Any] = {
        "snapshot_version": PURCHASABILITY_V35_SNAPSHOT_VERSION,
        "contract_version": PURCHASABILITY_V35_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_V35_FEATURE_VERSION,
        "formula_version": PURCHASABILITY_V35_FORMULA_VERSION,
        "relation_registry_version": PURCHASABILITY_V35_RELATION_REGISTRY_VERSION,
        "candidate_registry_version": PURCHASABILITY_V35_CANDIDATE_REGISTRY_VERSION,
        "registry_status": PURCHASABILITY_V35_SNAPSHOT_REGISTRY_STATUS,
        "generated_at": now,
        "source_snapshot_at": source_at_iso,
        "source_snapshot_verified": bool(snap.get("snapshot_timestamp_verified")),
        "source_snapshot_before_kickoff": snap.get("source_snapshot_before_kickoff"),
        "pre_match_verified": bool(batch.get("pre_match_verified")),
        "kickoff": kickoff_iso,
        "source_mode": source_mode,
        "experiment_version": PURCHASABILITY_V35_EXPERIMENT_VERSION,
        "input_fingerprint_sha256": input_fingerprint,
        "frozen_config": frozen_config_v35(),
        "relation_registry": relation_registry,
        "candidate_registry": candidate_registry_v35(),
        "items": items,
        "summary": _build_summary(items),
        "pre_match_only": True,
        "contains_post_match_fields": False,
        "historical_reliability_integrated": False,
        "shadow_candidate": True,
        "current_operational_version": False,
        "immutable_first_write": True,
        "warnings": list(warnings or []),
    }
    snapshot_body["engine_payload_sha256"] = engine_payload_sha256_v35(snapshot_body)
    return make_json_safe(snapshot_body)


def validate_purchasability_preview_v35_snapshot(snapshot: Any) -> dict[str, Any]:
    """Valida snapshot persistibile per esperimento live."""
    if not isinstance(snapshot, dict):
        return {"ok": False, "reason": "not_a_dict"}

    if snapshot.get("snapshot_version") != PURCHASABILITY_V35_SNAPSHOT_VERSION:
        return {"ok": False, "reason": "snapshot_version_mismatch"}

    for field, expected in (
        ("contract_version", PURCHASABILITY_V35_CONTRACT_VERSION),
        ("feature_version", PURCHASABILITY_V35_FEATURE_VERSION),
        ("formula_version", PURCHASABILITY_V35_FORMULA_VERSION),
        (
            "relation_registry_version",
            PURCHASABILITY_V35_RELATION_REGISTRY_VERSION,
        ),
        (
            "candidate_registry_version",
            PURCHASABILITY_V35_CANDIDATE_REGISTRY_VERSION,
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

    return {"ok": True, "reason": None}


def resolve_valid_persisted_purchasability_v35(existing: Any) -> dict[str, Any] | None:
    """Restituisce snapshot V3.5 persistito se valido per l'esperimento."""
    if existing is None:
        return None
    check = validate_purchasability_preview_v35_snapshot(existing)
    if check.get("ok") and isinstance(existing, dict):
        return existing
    if isinstance(existing, dict) and existing.get("snapshot_version"):
        logger.warning(
            "purchasability_v35_snapshot_conflict reason=%s",
            check.get("reason"),
        )
    return None


def _existing_valid_preview_v35(existing: Any) -> dict[str, Any] | None:
    return resolve_valid_persisted_purchasability_v35(existing)


def build_candidate_and_compact_snapshot_v35(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
    snapshot_info: dict[str, Any] | None = None,
    source_mode: str = "persisted_pre_match_snapshot",
    warnings: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    meta = dict(fixture_meta or {})
    batch = calculate_purchasability_v35_batch(
        kpi_panel=kpi_panel,
        fixture_meta=meta,
    )
    if not batch.get("pre_match_verified"):
        return batch, None

    fp = input_fingerprint_v35(kpi_panel=kpi_panel, fixture_meta=meta)
    snapshot = build_purchasability_preview_v35_snapshot(
        batch=batch,
        snapshot_info=snapshot_info,
        source_mode=source_mode,
        warnings=warnings,
        input_fingerprint=fp,
        kickoff=meta.get("kickoff"),
    )
    return batch, snapshot


def attach_purchasability_preview_v35_to_output(
    *,
    cecchino_output: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    existing_preview_v35: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scrive purchasability_preview_v35 — first valid pre-match write wins."""
    if not isinstance(cecchino_output, dict):
        return cecchino_output

    preserved = _existing_valid_preview_v35(existing_preview_v35)
    if preserved is None:
        preserved = _existing_valid_preview_v35(
            cecchino_output.get("purchasability_preview_v35")
        )

    # CASO B/D: snapshot valido esistente → preserva esattamente, no recalc
    if preserved is not None:
        cecchino_output["purchasability_preview_v35"] = preserved
        return cecchino_output

    snap = snapshot_info or {}
    verified = bool(snap.get("snapshot_timestamp_verified"))
    snap_dt = _parse_dt(snap.get("snapshot_at"))
    kick_dt = _parse_dt(fixture_meta.get("kickoff"))
    before: bool | None = None
    if snap_dt is not None and kick_dt is not None:
        before = snap_dt < kick_dt

    warnings: list[str] = []

    # CASO C: post-kickoff senza snapshot → non creare
    if before is False:
        return cecchino_output

    # Gate validità §8
    if not verified or before is not True:
        return cecchino_output

    try:
        _batch, snapshot = build_candidate_and_compact_snapshot_v35(
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
        warnings.append(f"purchasability_v35_attach_failed:{type(exc).__name__}")
        logger.warning(
            "purchasability_v35_attach_failed fixture=%s error=%s",
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

    cecchino_output["purchasability_preview_v35"] = snapshot
    return cecchino_output


def index_purchasability_v35_snapshot_by_market(
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


def fixture_has_v35_score(snapshot: dict[str, Any] | None) -> bool:
    """True se almeno un item frozen ha status == score."""
    if not isinstance(snapshot, dict):
        return False
    for item in snapshot.get("items") or []:
        if isinstance(item, dict) and item.get("status") == "score":
            return True
    return False


__all__ = [
    "attach_purchasability_preview_v35_to_output",
    "build_candidate_and_compact_snapshot_v35",
    "build_purchasability_preview_v35_snapshot",
    "engine_payload_sha256_v35",
    "fixture_has_v35_score",
    "index_purchasability_v35_snapshot_by_market",
    "input_fingerprint_v35",
    "resolve_valid_persisted_purchasability_v35",
    "validate_purchasability_preview_v35_snapshot",
]
