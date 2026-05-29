"""Lookup pesi/source_path manifest v2.1 per trace."""

from __future__ import annotations

from functools import lru_cache

from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS


@lru_cache(maxsize=1)
def v21_macro_weight_by_key() -> dict[str, int]:
    return {m.key: m.macro_weight for m in V21_MANIFEST_DEFINITIONS if not m.is_quality_only}


@lru_cache(maxsize=1)
def v21_micro_meta_by_key() -> dict[tuple[str, str], dict[str, object]]:
    out: dict[tuple[str, str], dict[str, object]] = {}
    for macro in V21_MANIFEST_DEFINITIONS:
        for micro in macro.micros:
            out[(macro.key, micro.key)] = {
                "label": micro.label,
                "micro_weight": micro.micro_weight,
                "source_path": micro.source_path,
                "initial_status": micro.initial_status,
                "is_quality_only": macro.is_quality_only,
            }
    return out
