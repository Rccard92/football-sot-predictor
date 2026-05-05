import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/refresh", tags=["admin-refresh"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


@router.post("/serie-a/{season}/post-matchday", response_model=None)
def admin_refresh_post_matchday(
    season: int,
    db: Session = Depends(get_db),
    force_update: bool = Query(default=False),
):
    _require_api_football_key()
    svc = IngestionService()
    try:
        summary = svc.run_post_matchday_refresh(db, season, force_update=force_update)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("post-matchday refresh: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    if summary.get("status") != "success":
        return JSONResponse(status_code=502, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)
