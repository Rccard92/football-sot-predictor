"""Route admin Cecchino — ricalcolo offline."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_recompute import CecchinoRecomputeBody
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
