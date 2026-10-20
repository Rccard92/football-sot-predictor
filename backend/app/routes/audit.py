"""Audit del Cecchino in SOLA LETTURA (dal 20/10/2026), usato dal server MCP.

Protetto da una chiave dedicata (`AUDIT_API_TOKEN`, header `Authorization: Bearer <chiave>`): senza
chiave configurata l'accesso e' spento. Ogni richiesta lavora in una transazione READ ONLY con limite di
tempo (vedi app/services/audit/readonly.py): da qui non si puo' scrivere ne' cancellare nulla.
"""

from __future__ import annotations

import hmac
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.audit import infra
from app.services.audit.models_compare import compare_engines
from app.services.audit.readonly import readonly_session, run_readonly_sql


def require_audit_token(authorization: str | None = Header(default=None)) -> None:
    expected = (get_settings().audit_api_token or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Audit non attivo: AUDIT_API_TOKEN non configurato.")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not given or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Chiave di audit mancante o errata.")


router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_audit_token)])


class SqlBody(BaseModel):
    sql: str = Field(..., description="Una sola lettura: SELECT / WITH / EXPLAIN / SHOW")
    limit: int = Field(500, ge=1, le=2000)
    params: dict[str, Any] | None = None


@router.get("/overview")
def audit_overview(db: Session = Depends(readonly_session)) -> dict[str, Any]:
    return infra.overview(db)


@router.get("/database/tables")
def audit_tables(db: Session = Depends(readonly_session)) -> dict[str, Any]:
    return infra.database_tables(db)


@router.get("/database/tables/{table}/columns")
def audit_table_columns(table: str, db: Session = Depends(readonly_session)) -> dict[str, Any]:
    return {"table": table, "columns": infra.table_columns(db, table)}


@router.post("/sql")
def audit_sql(body: SqlBody, db: Session = Depends(readonly_session)) -> dict[str, Any]:
    try:
        return run_readonly_sql(db, body.sql, limit=body.limit, params=body.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DBAPIError as exc:
        # errore di Postgres (sintassi, timeout, tentativo di scrittura in transazione READ ONLY...)
        raise HTTPException(status_code=400, detail=str(exc.orig).strip()[:600]) from exc


@router.get("/models/compare")
def audit_models_compare(
    date_from: date = Query(...),
    date_to: date = Query(...),
    group_by: str = Query("engine"),
    min_plays: int = Query(1, ge=1),
    db: Session = Depends(readonly_session),
) -> dict[str, Any]:
    try:
        return compare_engines(db, date_from=date_from, date_to=date_to, group_by=group_by, min_plays=min_plays)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api-usage")
def audit_api_usage(days: int = Query(14, ge=1, le=90), db: Session = Depends(readonly_session)) -> dict[str, Any]:
    return infra.api_usage(db, days=days)


@router.get("/jobs")
def audit_jobs(days: int = Query(7, ge=1, le=60), db: Session = Depends(readonly_session)) -> dict[str, Any]:
    return infra.recent_jobs(db, days=days)


@router.get("/data-health")
def audit_data_health(days: int = Query(30, ge=1, le=120), db: Session = Depends(readonly_session)) -> dict[str, Any]:
    return infra.data_health(db, days=days)
