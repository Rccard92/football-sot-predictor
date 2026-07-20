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


class BalanceEmpiricalSyncBody(BaseModel):
    date_from: date
    date_to: date
    competition_id: int | None = None
    source_cohort: str = "all"


class BalanceEmpiricalSyncRunBody(BalanceEmpiricalSyncBody):
    confirm: str | None = None


@admin_router.post("/balance-v5/empirical-sync/plan")
def balance_empirical_sync_plan(
    body: BalanceEmpiricalSyncBody,
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        sync_balance_empirical_dataset,
    )

    try:
        payload = sync_balance_empirical_dataset(
            db,
            date_from=body.date_from,
            date_to=body.date_to,
            competition_id=body.competition_id,
            source_cohort=body.source_cohort,
            dry_run=True,
            commit=False,
        )
        return JSONResponse(content=jsonable_encoder(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"balance_empirical_sync_plan_failed:{type(exc).__name__}",
        ) from exc


@admin_router.post("/balance-v5/empirical-sync/run")
def balance_empirical_sync_run(
    body: BalanceEmpiricalSyncRunBody,
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        BALANCE_EMPIRICAL_SYNC_CONFIRM_TOKEN,
        sync_balance_empirical_dataset,
    )

    if body.confirm != BALANCE_EMPIRICAL_SYNC_CONFIRM_TOKEN:
        raise HTTPException(status_code=400, detail="invalid_confirm_token")
    try:
        payload = sync_balance_empirical_dataset(
            db,
            date_from=body.date_from,
            date_to=body.date_to,
            competition_id=body.competition_id,
            source_cohort=body.source_cohort,
            dry_run=False,
            commit=True,
            confirm=body.confirm,
        )
        return JSONResponse(content=jsonable_encoder(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"balance_empirical_sync_run_failed:{type(exc).__name__}",
        ) from exc


class BalanceReadinessRefreshBody(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    competition_id: int | None = None


class BalanceGovernanceDecisionBody(BaseModel):
    decision: str
    decision_reason: str | None = None
    confirm: str
    requested_by: str | None = None
    confirmed_by: str | None = None


@admin_router.post("/balance-v5/readiness/refresh")
def balance_readiness_refresh(
    body: BalanceReadinessRefreshBody,
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_readiness import (
        build_balance_readiness_full_report,
        upsert_balance_readiness_daily_snapshot,
    )

    filters = {
        "date_from": body.date_from,
        "date_to": body.date_to,
        "competition_id": body.competition_id,
    }
    report = build_balance_readiness_full_report(db, filters=filters)
    snap = upsert_balance_readiness_daily_snapshot(
        db,
        competition_id=body.competition_id,
        date_from=body.date_from,
        date_to=body.date_to,
        commit=True,
    )
    return JSONResponse(
        content=jsonable_encoder({"status": "ok", "snapshot": snap, "report": report})
    )


class GoalIntensityReadinessRefreshBody(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    competition_id: int | None = None


@admin_router.post("/goal-intensity-v5/readiness/refresh")
def goal_intensity_v5_readiness_refresh(
    body: GoalIntensityReadinessRefreshBody,
    db: Session = Depends(get_db),
):
    """Ricalcola readiness/cache; non crea snapshot né muta bundle/score/Signals."""
    from app.services.cecchino.cecchino_goal_intensity_v5_readiness import (
        build_goal_intensity_v5_readiness,
        clear_goal_intensity_v5_readiness_cache,
    )

    clear_goal_intensity_v5_readiness_cache()
    report = build_goal_intensity_v5_readiness(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
    )
    return JSONResponse(content=jsonable_encoder({"status": "ok", "report": report}))


@admin_router.post("/balance-v5/governance/decisions")
def balance_governance_decisions(
    body: BalanceGovernanceDecisionBody,
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_readiness import (
        record_balance_governance_decision,
    )

    result = record_balance_governance_decision(
        db,
        decision=body.decision,
        decision_reason=body.decision_reason,
        confirm_token=body.confirm,
        requested_by=body.requested_by,
        confirmed_by=body.confirmed_by,
        commit=True,
    )
    if result.get("status") == "rejected":
        code = int(result.get("http_status") or 422)
        raise HTTPException(
            status_code=code,
            detail={"error": result.get("error")},
        )
    return JSONResponse(content=jsonable_encoder(result))


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
