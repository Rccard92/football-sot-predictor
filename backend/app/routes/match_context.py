import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.match_context_service import MatchContextService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["match-context"])


@router.get("/match-context/fixture/{fixture_id}", response_model=None)
def get_match_context(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    svc = MatchContextService()
    try:
        payload = svc.build_match_context(db, fixture_id)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("match context: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)
