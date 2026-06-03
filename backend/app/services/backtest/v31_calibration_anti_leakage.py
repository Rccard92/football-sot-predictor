"""Validazione anti-leakage dataset calibrazione v3.1 — solo blocco features."""

from __future__ import annotations

from typing import Any

# Chiavi vietate solo come leaf key dentro row.features (non target/comparisons/metadata).
FORBIDDEN_FEATURE_KEYS = frozenset(
    {
        "actual_total_sot",
        "actual_home_sot",
        "actual_away_sot",
        "final_score",
        "outcome",
        "win",
        "loss",
        "betting_outcome",
        "predicted_total_sot",
        "predicted_home_sot",
        "predicted_away_sot",
        "v1_1_predicted_total",
        "v2_0_predicted_total",
        "v2_1_predicted_total",
        "v3_0_decision",
        "v3_0_selected_line",
        "v3_0_outcome",
        "cautious_outcome",
        "aggressive_outcome",
        "selected_line",
        "betting_advice",
        "cautious_advice",
    },
)


def _key_forbidden(key: str) -> bool:
    return str(key) in FORBIDDEN_FEATURE_KEYS


def _walk_features(obj: Any, path: str, found: list[tuple[str, str]]) -> None:
    """Accumula (path_rel, field_name) per ogni chiave vietata."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else str(k)
            if _key_forbidden(str(k)):
                rel = child[10:] if child.startswith("features.") else child
                found.append((rel, str(k)))
            _walk_features(v, child, found)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _walk_features(item, f"{path}[{i}]", found)


def find_forbidden_in_features(features: dict[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(features, dict):
        _walk_features(features, "", found)
    return found


def validate_v31_features_no_leakage(features: dict[str, Any]) -> dict[str, Any]:
    """Scansiona solo il dict features della riga."""
    pairs = find_forbidden_in_features(features if isinstance(features, dict) else {})
    paths = sorted({p for p, _ in pairs})
    return {
        "status": "failed" if paths else "ok",
        "forbidden_fields_found": paths,
        "forbidden_fields_found_count": len(paths),
    }


def collect_leakage_samples(
    rows: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        if len(samples) >= limit:
            break
        meta = row.get("metadata") or {}
        fid = meta.get("fixture_id")
        feats = row.get("features") or {}
        for path, field in find_forbidden_in_features(feats if isinstance(feats, dict) else {}):
            if len(samples) >= limit:
                break
            samples.append(
                {
                    "fixture_id": fid,
                    "path": path,
                    "field": field,
                },
            )
    return samples


def validate_v31_rows(
    rows: list[dict[str, Any]],
    *,
    sample_limit: int = 20,
) -> dict[str, Any]:
    all_paths: list[str] = []
    for i, row in enumerate(rows):
        feats = row.get("features") or {}
        check = validate_v31_features_no_leakage(feats if isinstance(feats, dict) else {})
        for p in check.get("forbidden_fields_found") or []:
            all_paths.append(f"rows[{i}].features.{p}" if not p.startswith("features.") else f"rows[{i}].{p}")

    uniq = sorted(set(all_paths))
    samples = collect_leakage_samples(rows, limit=sample_limit)
    return {
        "status": "failed" if uniq else "ok",
        "forbidden_fields_found": uniq,
        "forbidden_fields_found_count": len(uniq),
        "sample_forbidden_fields": samples,
        "scope": "row.features",
    }


def build_anti_leakage_report_payload(
    rows: list[dict[str, Any]],
    *,
    competition_id: int,
    season_year: int,
    sample_limit: int = 20,
) -> dict[str, Any]:
    anti = validate_v31_rows(rows, sample_limit=sample_limit)
    return {
        "report_type": "v31_anti_leakage_report",
        "competition_id": int(competition_id),
        "season_year": int(season_year),
        "fixtures_checked": len(rows),
        "anti_leakage_check": anti,
        "exportable": anti.get("status") == "ok",
    }
