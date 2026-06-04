"""Admin: coverage e sync quote bookmaker per competizione."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.bookmakers import BookmakerSyncNextRoundBody
from app.services.bookmakers.bookmaker_coverage_service import BookmakerCoverageService
from app.services.bookmakers.bookmaker_sync_next_round_service import BookmakerSyncNextRoundService
from app.services.sportapi.sportapi_client import SportApiDisabledError, SportApiError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/competitions/{competition_id}/bookmakers",
    tags=["admin-competition-bookmakers"],
)


@router.get("/coverage", response_model=None)
def competition_bookmaker_coverage(
    competition_id: int,
    fixture_id: int | None = Query(default=None),
    only_next_round: bool = Query(default=True),
    market: str = Query(default="MATCH_WINNER_1X2"),
    provider_source: str | None = Query(default=None),
    bookmaker_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        out = BookmakerCoverageService().get_coverage(
            db,
            competition_id,
            fixture_id=fixture_id,
            only_next_round=only_next_round,
            market=market,
            provider_source=provider_source,
            bookmaker_name=bookmaker_name,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("bookmaker coverage DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.post("/sync-next-round-odds", response_model=None)
def competition_sync_next_round_odds(
    competition_id: int,
    body: BookmakerSyncNextRoundBody | None = None,
    db: Session = Depends(get_db),
):
    sync_body = body or BookmakerSyncNextRoundBody()
    try:
        out = BookmakerSyncNextRoundService().sync(
            db,
            competition_id,
            market=sync_body.market,
            provider_source=sync_body.provider_source,
            bookmaker_name=sync_body.bookmaker_name,
            provider_slug=sync_body.provider_slug,
        )
    except HTTPException:
        raise
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sync next round odds DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync next round odds failed")
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc
    return jsonable_encoder(out)
