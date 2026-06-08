"""Route admin monitoraggio segnali Cecchino."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_signals import CecchinoSignalsRevaluateBody
from app.services.cecchino.cecchino_signal_aggregation import (
    build_signals_summary,
    export_signals_csv,
    list_signal_activations,
)
from app.services.cecchino.cecchino_signal_evaluation import revaluate_signal_activations

router = APIRouter(prefix="/admin/cecchino/signals", tags=["admin-cecchino-signals"])


@router.get("/summary")
def cecchino_signals_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    source_column: str | None = Query(default=None),
    signal_group: str | None = Query(default=None),
    league_name: str | None = Query(default=None),
    country_name: str | None = Query(default=None),
    evaluation_status: str | None = Query(default=None),
    only_current: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    payload = build_signals_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        source_column=source_column,
        signal_group=signal_group,
        league_name=league_name,
        country_name=country_name,
        evaluation_status=evaluation_status,
        only_current=only_current,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/activations")
def cecchino_signals_activations(
    date_from: date = Query(...),
    date_to: date = Query(...),
    source_column: str | None = Query(default=None),
    signal_group: str | None = Query(default=None),
    league_name: str | None = Query(default=None),
    country_name: str | None = Query(default=None),
    evaluation_status: str | None = Query(default=None),
    only_current: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    payload = list_signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        source_column=source_column,
        signal_group=signal_group,
        league_name=league_name,
        country_name=country_name,
        evaluation_status=evaluation_status,
        only_current=only_current,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/export.csv")
def cecchino_signals_export_csv(
    date_from: date = Query(...),
    date_to: date = Query(...),
    source_column: str | None = Query(default=None),
    signal_group: str | None = Query(default=None),
    league_name: str | None = Query(default=None),
    country_name: str | None = Query(default=None),
    evaluation_status: str | None = Query(default=None),
    only_current: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    csv_text = export_signals_csv(
        db,
        date_from=date_from,
        date_to=date_to,
        source_column=source_column,
        signal_group=signal_group,
        league_name=league_name,
        country_name=country_name,
        evaluation_status=evaluation_status,
        only_current=only_current,
    )
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=cecchino_signals_export.csv"},
    )


@router.post("/revaluate")
def cecchino_signals_revaluate(
    body: CecchinoSignalsRevaluateBody,
    db: Session = Depends(get_db),
):
    payload = revaluate_signal_activations(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        force=body.force,
    )
    return JSONResponse(content=jsonable_encoder({"status": "ok", **payload}))
