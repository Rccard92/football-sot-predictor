"""Route Bet Builder — opportunity aggregator read-only (BET-01)."""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino.cecchino_bet_builder_opportunity_aggregator import (
    aggregate_bet_builder_opportunities,
)

router = APIRouter(prefix="/cecchino/bet-builder", tags=["cecchino-bet-builder"])


@router.get("/opportunities")
def get_bet_builder_opportunities(
    date: date_type = Query(..., description="Scan date YYYY-MM-DD (Cecchino Today)"),
    market_key: str | None = Query(None, description="Filtro opzionale market_key"),
    origin: str | None = Query(
        None,
        description="Filtro opzionale: price | signals | price_and_signals",
    ),
    db: Session = Depends(get_db),
):
    """Lista opportunity Bet Builder — read-only, nessuna write, nessuna API esterna."""
    payload = aggregate_bet_builder_opportunities(
        db,
        scan_date=date,
        market_key=market_key,
        origin=origin,
    )
    return JSONResponse(content=jsonable_encoder(payload))
