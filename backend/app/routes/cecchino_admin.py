"""Route admin Cecchino — ricalcolo offline e strumenti manuali."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_recompute import CecchinoRecomputeBody
from app.services.cecchino.cecchino_api_raw_inspector import build_api_raw_inspector
from app.services.cecchino.cecchino_recompute_service import recompute_cecchino_range

router = APIRouter(prefix="/admin/cecchino", tags=["admin-cecchino"])


@router.post("/recompute")
def cecchino_recompute(
    body: CecchinoRecomputeBody,
    db: Session = Depends(get_db),
):
    if body.scope != "cecchino":
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Unsupported scope: {body.scope}"},
        )
    payload = recompute_cecchino_range(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        refresh_bookmaker_odds=body.refresh_bookmaker_odds,
        use_existing_bookmaker_odds=body.use_existing_bookmaker_odds,
        force_remap_signals=body.force_remap_signals,
        sync_signal_activations=body.sync_signal_activations,
        evaluate_signals_after=body.evaluate_signals_after,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/fixtures/{today_fixture_id}/api-raw-inspector")
def api_raw_inspector(
    today_fixture_id: int,
    force_refresh: bool = Query(False),
    include_raw: bool = Query(False),
    endpoints: str = Query("all"),
    db: Session = Depends(get_db),
):
    """Ispezione manuale dati raw/cache/API — non invocare da scan automatici."""
    payload = build_api_raw_inspector(
        db,
        today_fixture_id,
        force_refresh=force_refresh,
        include_raw=include_raw,
        endpoints=endpoints,
    )
    if payload.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=payload.get("message"))
    return JSONResponse(content=jsonable_encoder(payload))
