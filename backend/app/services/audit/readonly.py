"""Accesso di audit in SOLA LETTURA al database (dal 20/10/2026).

Ogni sessione di audit apre una transazione `READ ONLY` con un tempo massimo per istruzione: Postgres
rifiuta qualunque scrittura (INSERT/UPDATE/DELETE/DDL) anche se la richiesta la contenesse, e una query
pesante si ferma da sola invece di rallentare il backend. La sessione si chiude sempre con un rollback.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from collections.abc import Generator
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

STATEMENT_TIMEOUT_MS = 20_000
MAX_ROWS = 2_000

# solo letture: una sola istruzione SELECT / WITH / EXPLAIN / SHOW / VALUES / TABLE
_ALLOWED_START = re.compile(r"^\s*(select|with|explain|show|values|table)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant|revoke|vacuum|analyze|copy|call|do|"
    r"lock|refresh|reindex|cluster|comment|security|set\s+role|set\s+session|listen|notify|prepare|execute)\b",
    re.IGNORECASE,
)


def readonly_session() -> Generator[Session, None, None]:
    """Dipendenza FastAPI: sessione in transazione di sola lettura con timeout, sempre annullata."""
    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
        yield db
    finally:
        try:
            db.rollback()
        finally:
            db.close()


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def check_readonly_sql(sql: str) -> str:
    """Controllo preventivo (la transazione READ ONLY resta la vera garanzia). Ritorna la query pulita."""
    cleaned = _strip_comments(sql or "").strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("query vuota")
    if ";" in cleaned:
        raise ValueError("una sola istruzione per richiesta")
    if not _ALLOWED_START.match(cleaned):
        raise ValueError("sono ammesse solo letture: SELECT, WITH, EXPLAIN, SHOW, VALUES, TABLE")
    # le parole vietate contano fuori dalle stringhe tra apici
    outside_strings = re.sub(r"'(?:[^']|'')*'", "''", cleaned)
    m = _FORBIDDEN.search(outside_strings)
    if m:
        raise ValueError(f"parola non ammessa in una lettura: {m.group(1)}")
    return cleaned


def json_value(v: Any) -> Any:
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(v))} byte>"
    if isinstance(v, dict):
        return {str(k): json_value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [json_value(x) for x in v]
    return v


def run_readonly_sql(db: Session, sql: str, *, limit: int = 500, params: dict[str, Any] | None = None) -> dict[str, Any]:
    cleaned = check_readonly_sql(sql)
    limit = max(1, min(int(limit or 500), MAX_ROWS))
    started = dt.datetime.now(dt.timezone.utc)
    result = db.execute(text(cleaned), params or {})
    columns = list(result.keys())
    rows = result.fetchmany(limit + 1)
    truncated = len(rows) > limit
    rows = rows[:limit]
    elapsed_ms = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    return {
        "columns": columns,
        "rows": [[json_value(v) for v in r] for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
    }
