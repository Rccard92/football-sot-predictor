"""Route Bet Builder — opportunity aggregator read-only (BET-01) + Results (BET-RESULTS-01)."""

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
from app.services.cecchino.cecchino_bet_builder_results import (
    SORT_RECENT,
    aggregate_bet_builder_results,
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


@router.get("/results")
def get_bet_builder_results(
    date_from: date_type | None = Query(
        None,
        description="Inizio intervallo (>= 2026-08-08). Default: oggi Europe/Rome.",
    ),
    date_to: date_type | None = Query(
        None,
        description="Fine intervallo. Default: oggi Europe/Rome.",
    ),
    outcome: str | None = Query(
        None,
        description="won | lost | pending | result_missing | not_evaluable",
    ),
    market_key: str | None = Query(None, description="Filtro market_key sulla primary"),
    origin: str | None = Query(
        None,
        description="price | signals | price_and_signals (sulla primary)",
    ),
    min_purchasability: float | None = Query(
        None,
        description="Acquistabilità V3.1 minima sulla primary",
    ),
    sort: str = Query(
        SORT_RECENT,
        description="recent | lost_first | purchasability_desc",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Outcome Monitor — read-only su snapshot Today. Nessuna API esterna."""
    payload = aggregate_bet_builder_results(
        db,
        date_from=date_from,
        date_to=date_to,
        outcome=outcome,
        market_key=market_key,
        origin=origin,
        min_purchasability=min_purchasability,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=jsonable_encoder(payload))
