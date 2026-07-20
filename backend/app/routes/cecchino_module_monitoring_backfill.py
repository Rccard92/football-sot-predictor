"""Admin + status routes — historical backfill Monitoraggio Moduli."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino.cecchino_module_monitoring_historical_backfill import (
    MODULE_HISTORICAL_BACKFILL_CONFIRM_TOKEN,
    build_module_historical_backfill_status,
    plan_module_historical_backfill,
    run_module_historical_backfill,
)

admin_router = APIRouter(
    prefix="/admin/cecchino/module-monitoring",
    tags=["admin-cecchino-module-monitoring"],
)

status_router = APIRouter(
    prefix="/cecchino/module-monitoring",
    tags=["cecchino-module-monitoring"],
)


class HistoricalBackfillPlanBody(BaseModel):
    module_keys: list[str] = Field(
        default_factory=lambda: [
            "purchasability",
            "balance-v5",
            "goal-intensity-v5",
            "signals",
        ]
    )
    date_from: date
    date_to: date
    competition_id: int | None = None
    include_unverified_diagnostic: bool = True


class HistoricalBackfillRunBody(HistoricalBackfillPlanBody):
    evaluate_after: bool = True
    confirm: str | None = None


@admin_router.post("/historical-backfill/plan")
def historical_backfill_plan(
    body: HistoricalBackfillPlanBody,
    db: Session = Depends(get_db),
):
    try:
        payload = plan_module_historical_backfill(
            db,
            module_keys=body.module_keys,
            date_from=body.date_from,
            date_to=body.date_to,
            competition_id=body.competition_id,
            include_unverified_diagnostic=body.include_unverified_diagnostic,
        )
        return JSONResponse(content=jsonable_encoder(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"historical_backfill_plan_failed:{type(exc).__name__}",
        ) from exc


@admin_router.post("/historical-backfill/run")
def historical_backfill_run(
    body: HistoricalBackfillRunBody,
    db: Session = Depends(get_db),
):
    if body.confirm != MODULE_HISTORICAL_BACKFILL_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail="invalid_confirm_token",
        )
    try:
        payload = run_module_historical_backfill(
            db,
            module_keys=body.module_keys,
            date_from=body.date_from,
            date_to=body.date_to,
            competition_id=body.competition_id,
            evaluate_after=body.evaluate_after,
            include_unverified_diagnostic=body.include_unverified_diagnostic,
            confirm=body.confirm,
        )
        return JSONResponse(content=jsonable_encoder(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"historical_backfill_run_failed:{type(exc).__name__}",
        ) from exc


@status_router.get("/historical-backfill/status")
def historical_backfill_status(
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    db: Session = Depends(get_db),
):
    payload = build_module_historical_backfill_status(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))
