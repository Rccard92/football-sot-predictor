"""Classificazione scientifica di indipendenza run Lab vs bundle di sviluppo."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import CecchinoGoalIntensityV5PreviewBundle
from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.services.cecchino.cecchino_goal_intensity_v5_preview import get_active_bundle

INDEPENDENCE_EXTERNAL = "external_independent"
INDEPENDENCE_PARTIAL = "partial_development_overlap"
INDEPENDENCE_FULL = "full_development_overlap"
INDEPENDENCE_UNKNOWN = "independence_unknown"

SCIENTIFIC_EXTERNAL_VALIDATION = "external_validation"
SCIENTIFIC_DIAGNOSTIC_REPLAY = "historical_diagnostic_replay"


def _sha256_canonical(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_int_set(values: Iterable[Any] | None) -> set[int]:
    out: set[int] = set()
    for v in values or []:
        try:
            if v is None:
                continue
            out.add(int(v))
        except (TypeError, ValueError):
            continue
    return out


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def collect_run_identities(
    snapshots: list[CecchinoLabHistoricalMatchSnapshot],
) -> dict[str, Any]:
    lab_ids: list[int] = []
    today_ids: list[int] = []
    local_ids: list[int] = []
    provider_ids: list[int] = []
    kickoffs: list[date] = []
    for s in snapshots:
        if s.lab_match_id is not None:
            lab_ids.append(int(s.lab_match_id))
        # Optional crosswalks if ever persisted in JSON
        for blob_name in ("input_snapshot_json", "module_availability_json", "cecchino_output_json"):
            blob = getattr(s, blob_name, None)
            if not isinstance(blob, dict):
                continue
            for key, bucket in (
                ("today_fixture_id", today_ids),
                ("local_fixture_id", local_ids),
                ("provider_fixture_id", provider_ids),
            ):
                v = blob.get(key)
                if v is None and isinstance(blob.get("identity"), dict):
                    v = blob["identity"].get(key)
                try:
                    if v is not None:
                        bucket.append(int(v))
                except (TypeError, ValueError):
                    pass
        if s.kickoff_at is not None:
            kickoffs.append(s.kickoff_at.date() if isinstance(s.kickoff_at, datetime) else s.kickoff_at)
    lab_sorted = sorted(set(lab_ids))
    return {
        "lab_match_ids": lab_sorted,
        "today_fixture_ids": sorted(set(today_ids)),
        "local_fixture_ids": sorted(set(local_ids)),
        "provider_fixture_ids": sorted(set(provider_ids)),
        "run_fixture_count": len(lab_sorted),
        "run_fixture_ids_hash": _sha256_canonical(lab_sorted),
        "kickoff_min": min(kickoffs).isoformat() if kickoffs else None,
        "kickoff_max": max(kickoffs).isoformat() if kickoffs else None,
    }


def _parent_development_sets(
    parent: CecchinoGoalIntensityV5PreviewBundle | None,
) -> dict[str, Any]:
    if parent is None:
        return {
            "available": False,
            "today_fixture_ids": [],
            "local_fixture_ids": [],
            "provider_fixture_ids": [],
            "fixture_ids_hash": None,
            "date_from": None,
            "date_to": None,
        }
    defs = parent.candidate_definitions_payload or {}
    guard = defs.get("prospective_guard") if isinstance(defs.get("prospective_guard"), dict) else {}
    return {
        "available": True,
        "today_fixture_ids": list(guard.get("retrospective_today_fixture_ids") or []),
        "local_fixture_ids": list(guard.get("retrospective_local_fixture_ids") or []),
        "provider_fixture_ids": list(guard.get("retrospective_provider_fixture_ids") or []),
        "fixture_ids_hash": parent.fixture_ids_hash or guard.get("fixture_ids_hash"),
        "date_from": parent.retrospective_date_from.isoformat()
        if parent.retrospective_date_from
        else None,
        "date_to": parent.retrospective_date_to.isoformat() if parent.retrospective_date_to else None,
        "targets_hash": parent.targets_hash,
    }


def _phase2c_development_sets(bundle: CecchinoGoalIntensityV5PreviewBundle) -> dict[str, Any]:
    defs = bundle.candidate_definitions_payload or {}
    split = defs.get("split_metadata") if isinstance(defs.get("split_metadata"), dict) else {}
    # Collect fixture ids from split meta if present
    today_ids: list[int] = []
    for part in ("train", "validation", "holdout"):
        block = split.get(part) if isinstance(split.get(part), dict) else {}
        for key in ("today_fixture_ids", "fixture_ids", "ids"):
            vals = block.get(key)
            if isinstance(vals, list):
                today_ids.extend([int(x) for x in vals if x is not None])
    return {
        "available": True,
        "today_fixture_ids": sorted(set(today_ids)),
        "fixture_ids_hash": bundle.fixture_ids_hash,
        "targets_hash": bundle.targets_hash,
        "no_2021_22_usage": bool(defs.get("no_2021_22_usage")),
        "parent_bundle_id": defs.get("parent_bundle_id"),
        "split_hashes": {
            part: ((split.get(part) or {}) if isinstance(split.get(part), dict) else {}).get(
                "fixture_ids_hash"
            )
            for part in ("train", "validation", "holdout")
        },
    }


def assess_independence(
    *,
    db: Session,
    run: CecchinoLabHistoricalScanRun,
    snapshots: list[CecchinoLabHistoricalMatchSnapshot],
    candidate_bundle: CecchinoGoalIntensityV5PreviewBundle,
) -> dict[str, Any]:
    run_ids = collect_run_identities(snapshots)
    parent = get_active_bundle(db)
    # Prefer parent referenced by candidate bundle when it is a real ORM row
    defs = candidate_bundle.candidate_definitions_payload or {}
    parent_id = defs.get("parent_bundle_id")
    if parent_id is not None:
        linked = db.get(CecchinoGoalIntensityV5PreviewBundle, int(parent_id))
        if isinstance(linked, CecchinoGoalIntensityV5PreviewBundle):
            parent = linked

    parent_sets = _parent_development_sets(parent)
    phase2c_sets = _phase2c_development_sets(candidate_bundle)

    run_today = _as_int_set(run_ids["today_fixture_ids"])
    run_local = _as_int_set(run_ids["local_fixture_ids"])
    run_provider = _as_int_set(run_ids["provider_fixture_ids"])

    parent_today = _as_int_set(parent_sets["today_fixture_ids"])
    parent_local = _as_int_set(parent_sets["local_fixture_ids"])
    parent_provider = _as_int_set(parent_sets["provider_fixture_ids"])
    phase_today = _as_int_set(phase2c_sets["today_fixture_ids"])

    overlap_today = sorted(run_today & (parent_today | phase_today))
    overlap_local = sorted(run_local & parent_local)
    overlap_provider = sorted(run_provider & parent_provider)
    overlap_all = sorted(set(overlap_today) | set(overlap_local) | set(overlap_provider))

    parent_overlap_count = len(
        (run_today & parent_today) | (run_local & parent_local) | (run_provider & parent_provider)
    )
    phase_overlap_count = len(run_today & phase_today)
    overlap_count = len(overlap_all)
    run_n = int(run_ids["run_fixture_count"] or 0)
    overlap_pct = round(100.0 * overlap_count / run_n, 4) if run_n else 0.0

    # Temporal heuristic when no shared identity namespace
    has_crosswalk = bool(run_today or run_local or run_provider)
    run_min = _parse_date(run_ids.get("kickoff_min"))
    run_max = _parse_date(run_ids.get("kickoff_max"))
    parent_from = _parse_date(parent_sets.get("date_from"))
    parent_to = _parse_date(parent_sets.get("date_to"))
    temporal_overlap = False
    if run_min and run_max and parent_from and parent_to:
        temporal_overlap = not (run_max < parent_from or run_min > parent_to)

    season = (run.season_label or "").strip()
    season_is_2021_22 = season in {"2021/22", "2021-22", "2021_22"}
    no_2021_flag = bool(phase2c_sets.get("no_2021_22_usage"))

    status = INDEPENDENCE_UNKNOWN
    rationale: list[str] = []

    if overlap_count > 0:
        if run_n > 0 and (overlap_pct >= 80.0 or overlap_count >= run_n):
            status = INDEPENDENCE_FULL
            rationale.append("identity_overlap_near_complete")
        else:
            status = INDEPENDENCE_PARTIAL
            rationale.append("identity_overlap_partial")
    elif has_crosswalk:
        # Identities comparable and no overlap
        status = INDEPENDENCE_EXTERNAL
        rationale.append("crosswalk_present_zero_identity_overlap")
    elif not parent_sets.get("available") and not phase2c_sets.get("fixture_ids_hash"):
        status = INDEPENDENCE_UNKNOWN
        rationale.append("development_identities_unavailable")
    else:
        # Lab IDs vs Today IDs — namespaces disjoint
        if season_is_2021_22 and no_2021_flag and not temporal_overlap:
            status = INDEPENDENCE_EXTERNAL
            rationale.append("lab_season_2021_22_excluded_from_development")
            rationale.append("no_shared_identity_namespace")
            rationale.append("temporal_range_disjoint_from_parent_retrospective")
        elif not temporal_overlap and parent_from and parent_to and run_min and run_max:
            status = INDEPENDENCE_EXTERNAL
            rationale.append("no_shared_identity_namespace")
            rationale.append("temporal_range_disjoint_from_parent_retrospective")
        elif temporal_overlap and not has_crosswalk:
            status = INDEPENDENCE_UNKNOWN
            rationale.append("temporal_overlap_without_identity_crosswalk")
        else:
            status = INDEPENDENCE_EXTERNAL
            rationale.append("no_shared_identity_namespace")
            rationale.append("lab_football_data_ids_vs_today_ids")

    scientific_label = (
        SCIENTIFIC_EXTERNAL_VALIDATION
        if status == INDEPENDENCE_EXTERNAL
        else SCIENTIFIC_DIAGNOSTIC_REPLAY
    )
    if status == INDEPENDENCE_UNKNOWN:
        scientific_label = SCIENTIFIC_DIAGNOSTIC_REPLAY

    return {
        "status": status,
        "scientific_label": scientific_label,
        "overlap_count": overlap_count,
        "overlap_pct": overlap_pct,
        "run_fixture_count": run_n,
        "parent_development_overlap_count": parent_overlap_count,
        "phase_2c_development_overlap_count": phase_overlap_count,
        "overlap_by_identity_type": {
            "today_fixture_id": len(overlap_today),
            "local_fixture_id": len(overlap_local),
            "provider_fixture_id": len(overlap_provider),
            "lab_match_id": 0,
        },
        "overlap_fixture_ids_hash": _sha256_canonical(overlap_all),
        "parent_fixture_ids_hash": parent_sets.get("fixture_ids_hash"),
        "phase_2c_fixture_ids_hash": phase2c_sets.get("fixture_ids_hash"),
        "run_fixture_ids_hash": run_ids["run_fixture_ids_hash"],
        "details": {
            "rationale": rationale,
            "run": {
                "season_label": season,
                "kickoff_min": run_ids.get("kickoff_min"),
                "kickoff_max": run_ids.get("kickoff_max"),
                "today_ids_n": len(run_today),
                "local_ids_n": len(run_local),
                "provider_ids_n": len(run_provider),
                "lab_ids_n": run_n,
            },
            "parent": parent_sets,
            "phase_2c": {
                "fixture_ids_hash": phase2c_sets.get("fixture_ids_hash"),
                "targets_hash": phase2c_sets.get("targets_hash"),
                "no_2021_22_usage": no_2021_flag,
                "split_hashes": phase2c_sets.get("split_hashes"),
                "development_today_ids_n": len(phase_today),
            },
            "temporal_overlap_with_parent": temporal_overlap,
            "has_identity_crosswalk": has_crosswalk,
        },
    }
