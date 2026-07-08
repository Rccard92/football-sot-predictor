"""Route admin Cecchino — ricalcolo offline e strumenti manuali."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_recompute import CecchinoRecomputeBody
from app.schemas.cecchino_signal_min_book_odds import (
    SignalMinBookOddsSaveAndBacktestBody,
    SignalMinBookOddsUpdateBody,
)
from app.services.cecchino.cecchino_api_raw_inspector import build_api_raw_inspector
from app.services.cecchino.cecchino_current_season_xg import backfill_current_season_xg_for_today_fixture
from app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache import rebuild_kpi_panels_from_cache
from app.services.cecchino.cecchino_recompute_service import recompute_cecchino_range
from app.services.cecchino.cecchino_signal_min_book_odd_settings_service import (
    SignalMinBookOddValidationError,
    list_signal_min_book_odds_settings,
    reset_signal_min_book_odds_defaults,
    save_signal_min_book_odds,
)
from app.services.cecchino.cecchino_signal_min_book_odds_backtest_service import (
    save_signal_min_book_odds_and_backtest,
)

router = APIRouter(prefix="/admin/cecchino", tags=["admin-cecchino"])


class BackfillCurrentSeasonXgBody(BaseModel):
    force_refresh: bool = False


class RebuildKpiPanelsFromCacheBody(BaseModel):
    date_from: date
    date_to: date
    include_xpt: bool = True
    rebuild_signals_after: bool = False
    evaluate_after: bool = False


@router.get("/signal-min-book-odds")
def get_signal_min_book_odds_settings(db: Session = Depends(get_db)):
    items = list_signal_min_book_odds_settings(db)
    return JSONResponse(content=jsonable_encoder({"status": "ok", "items": items}))


@router.put("/signal-min-book-odds")
def put_signal_min_book_odds_settings(
    body: SignalMinBookOddsUpdateBody,
    db: Session = Depends(get_db),
):
    try:
        payload = save_signal_min_book_odds(
            db,
            [item.model_dump() for item in body.items],
        )
        db.commit()
    except SignalMinBookOddValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc), "field": exc.field},
        )
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/signal-min-book-odds/reset-defaults")
def post_signal_min_book_odds_reset_defaults(db: Session = Depends(get_db)):
    payload = reset_signal_min_book_odds_defaults(db)
    db.commit()
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/signal-min-book-odds/save-and-backtest")
def post_signal_min_book_odds_save_and_backtest(
    body: SignalMinBookOddsSaveAndBacktestBody,
    db: Session = Depends(get_db),
):
    try:
        payload = save_signal_min_book_odds_and_backtest(
            db,
            date_from=body.date_from,
            date_to=body.date_to,
            items=[item.model_dump() for item in body.items],
            rebuild_kpi_from_cache=body.rebuild_kpi_from_cache,
            include_xpt=body.include_xpt,
            force_remap_signals=body.force_remap_signals,
            evaluate_after=body.evaluate_after,
        )
    except SignalMinBookOddValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc), "field": exc.field},
        )
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/rebuild-kpi-panels-from-cache")
def cecchino_rebuild_kpi_panels_from_cache(
    body: RebuildKpiPanelsFromCacheBody,
    db: Session = Depends(get_db),
):
    """Rebuild offline Pannello KPI da snapshot/cache — nessuna API esterna."""
    payload = rebuild_kpi_panels_from_cache(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        include_xpt=body.include_xpt,
        rebuild_signals_after=body.rebuild_signals_after,
        evaluate_after=body.evaluate_after,
    )
    return JSONResponse(content=jsonable_encoder(payload))


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


@router.post("/fixtures/{today_fixture_id}/backfill-current-season-xg")
def backfill_current_season_xg(
    today_fixture_id: int,
    body: BackfillCurrentSeasonXgBody,
    db: Session = Depends(get_db),
):
    """Backfill manuale xG fixture prior campionato corrente — non invocare da scan automatici."""
    payload = backfill_current_season_xg_for_today_fixture(
        db,
        today_fixture_id,
        force_refresh=body.force_refresh,
    )
    if payload.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=payload.get("message"))
    if payload.get("status") == "error":
        return JSONResponse(status_code=400, content=jsonable_encoder(payload))
    return JSONResponse(content=jsonable_encoder(payload))
