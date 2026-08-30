"""Profiling memoria Segnali KPI — attivo solo con KPI_SIGNALS_MEMORY_PROFILE=true.

Non altera output funzionale. Usato per baseline BEFORE / AFTER.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_ENV_FLAG = "KPI_SIGNALS_MEMORY_PROFILE"
_LAST_PROFILE: dict[str, Any] | None = None


def memory_profile_enabled() -> bool:
    raw = (os.environ.get(_ENV_FLAG) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def store_last_profile(payload: dict[str, Any]) -> None:
    global _LAST_PROFILE
    if memory_profile_enabled():
        _LAST_PROFILE = dict(payload)


def get_last_profile() -> dict[str, Any] | None:
    return dict(_LAST_PROFILE) if _LAST_PROFILE else None


def clear_last_profile() -> None:
    global _LAST_PROFILE
    _LAST_PROFILE = None


def _rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2)
    except Exception:
        try:
            import resource

            # Linux: ru_maxrss in KB; macOS: bytes
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys_platform_is_darwin():
                return round(usage / (1024 * 1024), 2)
            return round(usage / 1024.0, 2)
        except Exception:
            return None


def sys_platform_is_darwin() -> bool:
    return os.name == "posix" and sys_uname_sysname() == "Darwin"


def sys_uname_sysname() -> str:
    try:
        import platform

        return platform.system()
    except Exception:
        return ""


@dataclass
class KpiSignalsMemoryProfiler:
    """Contatore locale per una singola operazione (summary / activations / diagnostics)."""

    label: str
    enabled: bool = field(default_factory=memory_profile_enabled)
    t0: float = 0.0
    rss_enter: float | None = None
    rss_peak: float | None = None
    checkpoints: dict[str, float | None] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    sql_count: int = 0
    _engine: Engine | None = None
    _listen: bool = False

    def mark(self, name: str) -> None:
        if not self.enabled:
            return
        rss = _rss_mb()
        self.checkpoints[name] = rss
        if rss is not None:
            if self.rss_peak is None or rss > self.rss_peak:
                self.rss_peak = rss

    def set_counter(self, name: str, value: int) -> None:
        if not self.enabled:
            return
        self.counters[name] = int(value)

    def incr(self, name: str, delta: int = 1) -> None:
        if not self.enabled:
            return
        self.counters[name] = int(self.counters.get(name, 0)) + int(delta)

    def _on_cursor(self, *args: Any, **kwargs: Any) -> None:
        self.sql_count += 1

    def start_sql_listen(self, engine: Engine) -> None:
        if not self.enabled or self._listen:
            return
        if not isinstance(engine, Engine):
            return
        self._engine = engine
        event.listen(engine, "before_cursor_execute", self._on_cursor)
        self._listen = True

    def stop_sql_listen(self) -> None:
        if not self._listen or self._engine is None:
            return
        try:
            event.remove(self._engine, "before_cursor_execute", self._on_cursor)
        except Exception:
            pass
        self._listen = False
        self._engine = None

    def as_dict(self) -> dict[str, Any]:
        elapsed_ms = round((time.perf_counter() - self.t0) * 1000.0, 1) if self.t0 else None
        return {
            "label": self.label,
            "rss_enter_mb": self.rss_enter,
            "rss_peak_mb": self.rss_peak,
            "checkpoints_mb": dict(self.checkpoints),
            "counters": dict(self.counters),
            "sql_count": self.sql_count,
            "elapsed_ms": elapsed_ms,
        }

    def emit_log(self) -> dict[str, Any]:
        payload = self.as_dict()
        if self.enabled:
            logger.info("kpi_signals_memory_profile %s", payload)
        return payload


@contextmanager
def profile_kpi_signals_memory(label: str, *, engine: Engine | None = None) -> Iterator[KpiSignalsMemoryProfiler]:
    prof = KpiSignalsMemoryProfiler(label=label)
    if not prof.enabled:
        yield prof
        return
    prof.t0 = time.perf_counter()
    prof.rss_enter = _rss_mb()
    prof.rss_peak = prof.rss_enter
    prof.mark("enter")
    if engine is not None:
        prof.start_sql_listen(engine)
    try:
        yield prof
    finally:
        prof.mark("before_response")
        prof.stop_sql_listen()
        store_last_profile(prof.as_dict())
        prof.emit_log()
