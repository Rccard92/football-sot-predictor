"""Lock globale per scansioni Cecchino Today (manuale + auto).

Produzione PostgreSQL: advisory lock session-level su connessione dedicata.
Test / non-PG: fallback process-local con threading.Lock.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Generator, Iterator

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Chiave advisory fissa (non usare hash() di Python): namespace Cecchino Today scan.
# 0xCEC5C4A0 = "CECSCA0" mnemonic per Cecchino Scan Advisory 0.
CECCHINO_TODAY_SCAN_LOCK_KEY = 0xCEC5C4A0

_process_lock = threading.Lock()
_process_lock_holder: threading.Lock | None = None


class ScanLockNotAcquired(Exception):
    """Il lock globale non è disponibile."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__("cecchino_scan_lock_not_acquired")


def _is_postgres(engine: Engine) -> bool:
    name = (engine.dialect.name or "").lower()
    return name in {"postgresql", "postgres"}


def _lock_payload(
    *,
    acquired: bool,
    backend: str,
    lock_key: int,
    waited_seconds: float,
) -> dict[str, Any]:
    return {
        "acquired": acquired,
        "backend": backend,
        "lock_key": lock_key,
        "waited_seconds": round(float(waited_seconds), 3),
    }


@contextmanager
def acquire_cecchino_scan_lock(
    *,
    engine: Engine | None = None,
    lock_key: int = CECCHINO_TODAY_SCAN_LOCK_KEY,
    blocking: bool = False,
    wait_timeout_seconds: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Acquisisce il lock globale Cecchino Today.

    Yields un payload ``{acquired, backend, lock_key, waited_seconds}``.
    Se non acquisito solleva ``ScanLockNotAcquired`` (dopo aver rilasciato risorse).
    """
    if engine is None:
        from app.core.database import engine as default_engine

        engine = default_engine

    started = time.monotonic()
    if _is_postgres(engine):
        yield from _acquire_pg_lock(
            engine,
            lock_key=lock_key,
            blocking=blocking,
            wait_timeout_seconds=wait_timeout_seconds,
            started=started,
        )
    else:
        yield from _acquire_process_lock(
            lock_key=lock_key,
            blocking=blocking,
            wait_timeout_seconds=wait_timeout_seconds,
            started=started,
        )


def _acquire_pg_lock(
    engine: Engine,
    *,
    lock_key: int,
    blocking: bool,
    wait_timeout_seconds: float,
    started: float,
) -> Generator[dict[str, Any], None, None]:
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    acquired = False
    try:
        deadline = started + max(0.0, float(wait_timeout_seconds))
        while True:
            row = conn.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": int(lock_key)},
            ).scalar()
            acquired = bool(row)
            if acquired:
                break
            if not blocking or time.monotonic() >= deadline:
                break
            time.sleep(0.05)

        waited = time.monotonic() - started
        payload = _lock_payload(
            acquired=acquired,
            backend="postgresql_advisory",
            lock_key=lock_key,
            waited_seconds=waited,
        )
        if not acquired:
            raise ScanLockNotAcquired(payload)

        logger.info(
            "Cecchino scan lock acquired backend=postgresql_advisory lock_key=%s waited=%s",
            lock_key,
            payload["waited_seconds"],
        )
        try:
            yield payload
        finally:
            try:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": int(lock_key)},
                )
                logger.info(
                    "Cecchino scan lock released backend=postgresql_advisory lock_key=%s",
                    lock_key,
                )
            except Exception:
                logger.exception(
                    "Failed to release PostgreSQL advisory lock lock_key=%s", lock_key
                )
    finally:
        try:
            conn.close()
        except Exception:
            logger.exception("Failed to close advisory lock connection")


def _acquire_process_lock(
    *,
    lock_key: int,
    blocking: bool,
    wait_timeout_seconds: float,
    started: float,
) -> Generator[dict[str, Any], None, None]:
    global _process_lock_holder
    acquired = False
    try:
        deadline = started + max(0.0, float(wait_timeout_seconds))
        while True:
            acquired = _process_lock.acquire(blocking=False)
            if acquired:
                break
            if not blocking or time.monotonic() >= deadline:
                break
            time.sleep(0.05)

        waited = time.monotonic() - started
        payload = _lock_payload(
            acquired=acquired,
            backend="process_threading",
            lock_key=lock_key,
            waited_seconds=waited,
        )
        if not acquired:
            raise ScanLockNotAcquired(payload)

        _process_lock_holder = _process_lock
        logger.info(
            "Cecchino scan lock acquired backend=process_threading lock_key=%s waited=%s",
            lock_key,
            payload["waited_seconds"],
        )
        try:
            yield payload
        finally:
            try:
                _process_lock.release()
                _process_lock_holder = None
                logger.info(
                    "Cecchino scan lock released backend=process_threading lock_key=%s",
                    lock_key,
                )
            except RuntimeError:
                logger.exception("Failed to release process lock lock_key=%s", lock_key)
    except ScanLockNotAcquired:
        raise
