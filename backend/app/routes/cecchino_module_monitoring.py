"""Route Monitoraggio Moduli Cecchino — overview + analysis pack."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino.cecchino_module_monitoring_exports import (
    VALID_MODULE_KEYS,
    build_module_analysis_pack_zip,
    build_module_monitoring_overview,
    build_module_rows_csv,
    build_module_summary_payload,
)

router = APIRouter(
    prefix="/cecchino/module-monitoring",
    tags=["cecchino-module-monitoring"],
)


@router.get("/overview")
def module_monitoring_overview(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    payload = build_module_monitoring_overview(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/{module_key}/analysis-pack.zip")
def module_monitoring_analysis_pack(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        data, filename = build_module_analysis_pack_zip(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            include_rows=include_rows,
            include_debug=include_debug,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{module_key}/summary.json")
def module_monitoring_summary_json(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        payload = build_module_summary_payload(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    raw = jsonable_encoder(payload)
    body = __import__("json").dumps(raw, ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="SOT_MONITOR_{module_key}_summary.json"'
            )
        },
    )


@router.get("/{module_key}/rows.csv")
def module_monitoring_rows_csv(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    db: Session = Depends(get_db),
):
    _ = include_rows, include_debug
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        data, filename = build_module_rows_csv(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
