"""Impostazioni della V4 lette dall'ambiente, senza toccare `app.core.config`."""

from __future__ import annotations

import os


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "si", "sì"}


def v4_enabled() -> bool:
    return _flag("CECCHINO_V4_ENABLED", default=False)


def api_daily_stop() -> int:
    raw = os.environ.get("CECCHINO_V4_API_DAILY_STOP")
    try:
        return int(raw) if raw else 7000
    except ValueError:
        return 7000


def cap_workers(requested: int | None) -> int:
    """Processi paralleli dei motori: `CECCHINO_V4_WORKERS` li limita (su Railway 1). Senza variabile: quello richiesto."""
    raw = os.environ.get("CECCHINO_V4_WORKERS")
    try:
        cap = int(raw) if raw else None
    except ValueError:
        cap = None
    n = max(1, int(requested or 1))
    return max(1, min(n, cap)) if cap else n
