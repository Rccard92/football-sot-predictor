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
