"""Profiling memoria update-results — attivo solo con CECCHINO_UPDATE_RESULTS_MEMORY_PROFILE=true.

Non altera output funzionale. Non serializza JSONB in-process (evita peak RSS artificiali).
Usato per baseline BEFORE / AFTER.
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
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ENV_FLAG = "CECCHINO_UPDATE_RESULTS_MEMORY_PROFILE"
_LAST_PROFILE: dict[str, Any] | None = None

# Stage per-fixture loggati solo sul campione obbligatorio.
STAGE_SAMPLE_MARKS = (
    "after_apply_result",
    "after_signals_evaluation",
    "after_kpi_revaluation",
    "after_purchasability_validation",
    "after_balance_settlement",
)


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


def session_uow_counts(db: Session | None) -> dict[str, int] | None:
    """Contatori unit-of-work SQLAlchemy (leggeri — solo len, nessun dump payload)."""
    if db is None:
        return None
    try:
        return {
            "identity_map": len(db.identity_map),
            "new": len(db.new),
            "dirty": len(db.dirty),
            "deleted": len(db.deleted),
        }
    except Exception:
        return None


def stage_sample_indices(n: int) -> set[int]:
    """Indici 0-based del campione obbligatorio: prime 3 + centrale + ultima."""
    if n <= 0:
        return set()
    idxs = {0, 1, 2, n // 2, n - 1}
    return {i for i in idxs if 0 <= i < n}


@dataclass
class UpdateResultsMemoryProfiler:
    """Profiler locale per una singola run di update_today_fixture_results."""

    label: str
    enabled: bool = field(default_factory=memory_profile_enabled)
    t0: float = 0.0
    rss_enter: float | None = None
    rss_peak: float | None = None
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    stage_samples: list[dict[str, Any]] = field(default_factory=list)
    uow_peak: dict[str, int] = field(default_factory=dict)
    sql_count: int = 0
    _engine: Engine | None = None
    _listen: bool = False
    _sample_indices: set[int] = field(default_factory=set)
    _current_sample: dict[str, Any] | None = None

    def set_sample_indices(self, indices: set[int]) -> None:
        if not self.enabled:
            return
        self._sample_indices = set(indices)

    def is_stage_sample(self, fixture_index: int) -> bool:
        """True se questa fixture (0-based tra quelle elaborate nel path completo) è nel campione."""
        if not self.enabled:
            return False
        return fixture_index in self._sample_indices

    def _update_uow_peak(self, uow: dict[str, int] | None) -> None:
        if not uow:
            return
        for key, value in uow.items():
            prev = self.uow_peak.get(key)
            if prev is None or value > prev:
                self.uow_peak[key] = value

    def mark(self, name: str, *, db: Session | None = None) -> None:
        if not self.enabled:
            return
        rss = _rss_mb()
        uow = session_uow_counts(db)
        self.checkpoints[name] = {
            "rss_mb": rss,
            "elapsed_ms": round((time.perf_counter() - self.t0) * 1000.0, 1) if self.t0 else None,
            "uow": uow,
        }
        if rss is not None:
            if self.rss_peak is None or rss > self.rss_peak:
                self.rss_peak = rss
        self._update_uow_peak(uow)

    def touch_peak(self, *, db: Session | None = None) -> None:
        """Aggiorna solo peak RSS/UoW senza aggiungere un checkpoint nominato (loop non-campione)."""
        if not self.enabled:
            return
        rss = _rss_mb()
        if rss is not None:
            if self.rss_peak is None or rss > self.rss_peak:
                self.rss_peak = rss
        self._update_uow_peak(session_uow_counts(db))

    def begin_stage_sample(self, *, fixture_index: int, fixture_id: int | None) -> None:
        if not self.enabled:
            return
        self._current_sample = {
            "fixture_index": fixture_index,
            "fixture_id": fixture_id,
            "stages": {},
        }

    def mark_stage(self, name: str, *, db: Session | None = None) -> None:
        """Checkpoint per-stage: solo se begin_stage_sample è attivo."""
        if not self.enabled or self._current_sample is None:
            return
        rss = _rss_mb()
        uow = session_uow_counts(db)
        self._current_sample["stages"][name] = {
            "rss_mb": rss,
            "elapsed_ms": round((time.perf_counter() - self.t0) * 1000.0, 1) if self.t0 else None,
            "uow": uow,
        }
        if rss is not None:
            if self.rss_peak is None or rss > self.rss_peak:
                self.rss_peak = rss
        self._update_uow_peak(uow)

    def end_stage_sample(self) -> None:
        if not self.enabled or self._current_sample is None:
            return
        self.stage_samples.append(self._current_sample)
        self._current_sample = None

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
            "checkpoints": dict(self.checkpoints),
            "stage_samples": list(self.stage_samples),
            "sample_indices": sorted(self._sample_indices),
            "uow_peak": dict(self.uow_peak),
            "counters": dict(self.counters),
            "sql_count": self.sql_count,
            "elapsed_ms": elapsed_ms,
        }

    def emit_log(self) -> dict[str, Any]:
        payload = self.as_dict()
        if self.enabled:
            logger.info("update_results_memory_profile %s", payload)
        return payload


@contextmanager
def profile_update_results_memory(
    label: str = "update_today_fixture_results",
    *,
    engine: Engine | None = None,
    db: Session | None = None,
) -> Iterator[UpdateResultsMemoryProfiler]:
    prof = UpdateResultsMemoryProfiler(label=label)
    if not prof.enabled:
        yield prof
        return
    prof.t0 = time.perf_counter()
    prof.rss_enter = _rss_mb()
    prof.rss_peak = prof.rss_enter
    prof.mark("enter", db=db)
    if engine is not None:
        prof.start_sql_listen(engine)
    try:
        yield prof
    finally:
        # before_return è responsabilità del caller (dopo commit); qui chiudiamo solo listen/store.
        prof.stop_sql_listen()
        store_last_profile(prof.as_dict())
        prof.emit_log()
