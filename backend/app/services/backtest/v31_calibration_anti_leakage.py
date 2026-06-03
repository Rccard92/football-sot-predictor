"""Validazione anti-leakage dataset calibrazione v3.1."""

from __future__ import annotations

import re
from typing import Any

FORBIDDEN_KEY_PATTERNS = (
    re.compile(r"^actual_", re.I),
    re.compile(r"actual_total", re.I),
    re.compile(r"actual_home", re.I),
    re.compile(r"actual_away", re.I),
    re.compile(r"^outcome$", re.I),
    re.compile(r"^win$", re.I),
    re.compile(r"^loss$", re.I),
    re.compile(r"betting_outcome", re.I),
    re.compile(r"final_score", re.I),
    re.compile(r"predicted_total_sot", re.I),
    re.compile(r"predicted_home_sot", re.I),
    re.compile(r"predicted_away_sot", re.I),
    re.compile(r"cautious_outcome", re.I),
    re.compile(r"aggressive_outcome", re.I),
    re.compile(r"v1_1_predicted", re.I),
    re.compile(r"v2_0_predicted", re.I),
    re.compile(r"v2_1_predicted", re.I),
    re.compile(r"v3_0_", re.I),
)

FORBIDDEN_EXACT = frozenset(
    {
        "actual_total_sot",
        "actual_home_sot",
        "actual_away_sot",
        "outcome",
        "win",
        "loss",
        "final_score",
    },
)


def _key_forbidden(key: str) -> bool:
    k = str(key)
    if k.lower() in FORBIDDEN_EXACT:
        return True
    return any(p.search(k) for p in FORBIDDEN_KEY_PATTERNS)


def _walk(obj: Any, path: str, found: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else str(k)
            if _key_forbidden(str(k)):
                found.append(child)
            _walk(v, child, found)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _walk(item, f"{path}[{i}]", found)


def validate_v31_features_no_leakage(features: dict[str, Any]) -> dict[str, Any]:
    """Scansiona solo `features` (non comparisons)."""
    found: list[str] = []
    _walk(features, "features", found)
    uniq = sorted(set(found))
    return {
        "status": "failed" if uniq else "ok",
        "forbidden_fields_found": uniq,
    }


def validate_v31_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_found: list[str] = []
    for i, row in enumerate(rows):
        feats = row.get("features") or {}
        check = validate_v31_features_no_leakage(feats if isinstance(feats, dict) else {})
        for p in check.get("forbidden_fields_found") or []:
            all_found.append(f"rows[{i}].{p}")
    uniq = sorted(set(all_found))
    return {
        "status": "failed" if uniq else "ok",
        "forbidden_fields_found": uniq,
    }
