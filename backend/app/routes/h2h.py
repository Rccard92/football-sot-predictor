import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Fixture
from app.services.h2h_service import build_h2h_summary_for_fixture

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/h2h", tags=["h2h"])


@router.get("/fixture/{fixture_id}", response_model=None)
def h2h_for_fixture(fixture_id: int, db: Session = Depends(get_db)):
    try:
        fx = db.get(Fixture, fixture_id)
        excl = int(fx.api_fixture_id) if fx else None
        payload = build_h2h_summary_for_fixture(db, fixture_id, exclude_api_fixture_id=excl)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("h2h: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    if payload.get("error"):
        raise HTTPException(status_code=404, detail=payload)
    return jsonable_encoder(payload)
