"""Lettura/scrittura cache JSON ultimo scan catalogo API diretto."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def direct_catalog_cache_path() -> Path:
    """File cache sotto `app/data/cache/` (può essere ignorato da git)."""
    app_dir = Path(__file__).resolve().parent.parent
    cache_dir = app_dir / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "api_football_direct_catalog_latest.json"


def load_direct_catalog_cache() -> dict[str, Any] | None:
    path = direct_catalog_cache_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_direct_catalog_cache(payload: dict[str, Any]) -> Path:
    path = direct_catalog_cache_path()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
