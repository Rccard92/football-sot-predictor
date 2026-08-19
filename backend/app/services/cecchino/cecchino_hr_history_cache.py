"""Cache in-process read-only per history context Affidabilità storica."""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_purchasability_audit import DATASET_VERSION
from app.services.cecchino.cecchino_purchasability_v31_hr import build_hr_history_context

# TTL breve — allineato al frontend (90s).
_HR_HISTORY_CACHE_TTL_S = 90
_HR_HISTORY_CACHE_MAX = 16
_hr_history_cache: OrderedDict[tuple[str, str], tuple[float, dict[str, Any]]] = OrderedDict()
_hr_history_cache_lock = threading.Lock()


def _hr_history_cache_key(*, date_to: date) -> tuple[str, str]:
    return (DATASET_VERSION, date_to.isoformat())


def clear_hr_history_cache() -> None:
    """Svuota la cache — usata dai test e a cambio dataset version."""
    with _hr_history_cache_lock:
        _hr_history_cache.clear()


def get_or_build_hr_history_context(
    db: Session,
    *,
    date_to: date,
) -> dict[str, Any]:
    """Restituisce history context cached o lo ricostruisce (cache miss)."""
    key = _hr_history_cache_key(date_to=date_to)
    now = time.monotonic()

    with _hr_history_cache_lock:
        entry = _hr_history_cache.get(key)
        if entry is not None:
            stored_at, payload = entry
            if now - stored_at <= _HR_HISTORY_CACHE_TTL_S and key[0] == DATASET_VERSION:
                _hr_history_cache.move_to_end(key)
                return copy.deepcopy(payload)
            _hr_history_cache.pop(key, None)

    built = build_hr_history_context(db, date_to=date_to)
    built = {
        **built,
        "cache_key": key,
        "cache_hit": False,
    }

    with _hr_history_cache_lock:
        stale = [k for k in _hr_history_cache if k[0] != DATASET_VERSION]
        for k in stale:
            _hr_history_cache.pop(k, None)
        _hr_history_cache[key] = (time.monotonic(), copy.deepcopy(built))
        _hr_history_cache.move_to_end(key)
        while len(_hr_history_cache) > _HR_HISTORY_CACHE_MAX:
            _hr_history_cache.popitem(last=False)

    return built


def get_hr_history_cache_stats() -> dict[str, Any]:
    """Metadati cache — utile per test e profiling."""
    with _hr_history_cache_lock:
        return {
            "entries": len(_hr_history_cache),
            "ttl_s": _HR_HISTORY_CACHE_TTL_S,
            "max_entries": _HR_HISTORY_CACHE_MAX,
            "dataset_version": DATASET_VERSION,
        }
