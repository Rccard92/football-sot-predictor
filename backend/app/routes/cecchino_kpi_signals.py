"""Route Segnali KPI Cecchino (modulo separato da Monitoraggio Segnali)."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_kpi_signals import (
    CecchinoKpiSignalsBackfillBody,
    CecchinoKpiSignalsRevaluateBody,
)
from app.services.cecchino.cecchino_kpi_signals import (
    backfill_kpi_signals,
    revaluate_kpi_signals_for_range,
)
from app.services.cecchino.cecchino_kpi_signals_aggregation import (
    build_kpi_signals_summary,
    export_kpi_signals_csv,
    list_kpi_signal_activations,
)

router = APIRouter(prefix="/cecchino/kpi-signals", tags=["cecchino-kpi-signals"])
admin_router = APIRouter(prefix="/admin/cecchino/kpi-signals", tags=["admin-cecchino-kpi-signals"])
logger = logging.getLogger(__name__)


def _summary_payload(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    rating_bucket: str | None,
    selection_key: str | None,
    normalized_market: str | None,
    evaluation_status: str | None,
    league_name: str | None,
    country_name: str | None,
    only_current: bool,
    include_diagnostics: bool,
) -> dict:
    return build_kpi_signals_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        include_diagnostics=include_diagnostics,
    )


@router.get("/summary")
def kpi_signals_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    rating_bucket: str | None = Query(None),
    selection_key: str | None = Query(None),
    normalized_market: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    league_name: str | None = Query(None),
    country_name: str | None = Query(None),
    only_current: bool = Query(True),
    include_diagnostics: bool = Query(True),
    db: Session = Depends(get_db),
):
    payload = _summary_payload(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        include_diagnostics=include_diagnostics,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/activations")
def kpi_signals_activations(
    date_from: date = Query(...),
    date_to: date = Query(...),
    rating_bucket: str | None = Query(None),
    selection_key: str | None = Query(None),
    normalized_market: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    league_name: str | None = Query(None),
    country_name: str | None = Query(None),
    only_current: bool = Query(True),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    payload = list_kpi_signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/export.csv")
def kpi_signals_export_csv(
    date_from: date = Query(...),
    date_to: date = Query(...),
    rating_bucket: str | None = Query(None),
    selection_key: str | None = Query(None),
    normalized_market: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    league_name: str | None = Query(None),
    country_name: str | None = Query(None),
    only_current: bool = Query(True),
    db: Session = Depends(get_db),
):
    csv_text = export_kpi_signals_csv(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
    )
    return PlainTextResponse(content=csv_text, media_type="text/csv")


@admin_router.post("/backfill")
def kpi_signals_backfill(
    body: CecchinoKpiSignalsBackfillBody,
    db: Session = Depends(get_db),
):
    try:
        payload = backfill_kpi_signals(
            db,
            date_from=body.date_from,
            date_to=body.date_to,
            only_missing=body.only_missing,
            evaluate_after=body.evaluate_after,
        )
        return JSONResponse(content=jsonable_encoder(payload))
    except Exception as exc:
        logger.exception("KPI signals backfill fatal error")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "code": "kpi_signals_backfill_failed",
                "message": str(exc)[:500],
                "errors": [],
            },
        )


@admin_router.post("/revaluate")
def kpi_signals_revaluate(
    body: CecchinoKpiSignalsRevaluateBody,
    db: Session = Depends(get_db),
):
    payload = revaluate_kpi_signals_for_range(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
    )
    return JSONResponse(content=jsonable_encoder(payload))
